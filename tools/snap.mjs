#!/usr/bin/env node
// Deterministic page snapshot via the Chrome DevTools Protocol (no npm deps;
// needs Node >= 22 for the built-in WebSocket).
//
//   node tools/snap.mjs <url> <outPrefix> [--width 1440] [--height 900] [--wait 4000] [--mobile]
//
// Loads the page in headless Chrome, waits, scrolls through it (so lazy
// images and appear-animations fire), scrolls back, then writes
//   <outPrefix>.png   full-page screenshot
//   <outPrefix>.json  metrics: title, height, block list, broken images,
//                     text hash, console errors, failed/4xx requests,
//                     every external host that was contacted.
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createHash } from 'node:crypto';

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const UA_DESKTOP = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15';
const UA_MOBILE = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1';

const argv = process.argv.slice(2);
const url = argv[0];
const outPrefix = argv[1];
const opt = (name, def) => { const i = argv.indexOf(name); return i >= 0 ? argv[i + 1] : def; };
const mobile = argv.includes('--mobile');
const width = parseInt(opt('--width', mobile ? '390' : '1440'), 10);
const height = parseInt(opt('--height', mobile ? '844' : '900'), 10);
const waitMs = parseInt(opt('--wait', '4000'), 10);
const UA = mobile ? UA_MOBILE : UA_DESKTOP;
if (!url || !outPrefix) { console.error('usage: snap.mjs <url> <outPrefix>'); process.exit(2); }

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const DEBUG = !!process.env.SNAP_DEBUG;
const dbg = (...a) => { if (DEBUG) console.error('[snap]', ...a); };
const port = 9300 + Math.floor(Math.random() * 600);
const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'snap-'));
const chrome = spawn(CHROME, [
  '--headless=new', '--disable-gpu', '--hide-scrollbars', '--no-first-run', '--disable-extensions',
  '--mute-audio', '--disable-background-timer-throttling', `--user-data-dir=${profile}`,
  `--user-agent=${UA}`, `--window-size=${width},${height}`, `--remote-debugging-port=${port}`, 'about:blank',
], { stdio: 'ignore' });

function cleanup() {
  try { chrome.kill('SIGKILL'); } catch { /* ignore */ }
  try { fs.rmSync(profile, { recursive: true, force: true }); } catch { /* ignore */ }
}
process.on('exit', cleanup);
const die = (msg) => { console.error(msg); cleanup(); process.exit(1); };
setTimeout(() => die('snap: global timeout'), 150000).unref();

async function getJson(p) {
  const r = await fetch(`http://127.0.0.1:${port}${p}`);
  return r.json();
}
let targets = null;
for (let i = 0; i < 100 && !targets; i++) {
  try { targets = await getJson('/json'); } catch { await sleep(200); }
}
if (!targets) die('snap: chrome did not start');
dbg('chrome up on', port);
const page = targets.find((t) => t.type === 'page');
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });

let seq = 0;
const pending = new Map();
const listeners = new Map();
ws.onmessage = (ev) => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) {
    const { res, rej } = pending.get(m.id); pending.delete(m.id);
    m.error ? rej(new Error(m.error.message)) : res(m.result);
  } else if (m.method && listeners.has(m.method)) {
    for (const fn of listeners.get(m.method)) fn(m.params);
  }
};
const send = (method, params = {}) => new Promise((res, rej) => {
  const id = ++seq; pending.set(id, { res, rej }); ws.send(JSON.stringify({ id, method, params }));
});
const on = (method, fn) => { if (!listeners.has(method)) listeners.set(method, []); listeners.get(method).push(fn); };
const evaluate = async (expr) => {
  const r = await send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true });
  if (r.exceptionDetails) throw new Error('evaluate failed: ' + JSON.stringify(r.exceptionDetails).slice(0, 300));
  return r.result.value;
};

const consoleErrors = [];
const failed = [];
const badStatus = [];
const hosts = new Map();
const externalUrls = [];
const reqUrl = new Map();
on('Runtime.exceptionThrown', (p) => consoleErrors.push('exception: ' + (p.exceptionDetails.exception?.description || p.exceptionDetails.text || '').slice(0, 300)));
on('Runtime.consoleAPICalled', (p) => { if (p.type === 'error') consoleErrors.push('console.error: ' + p.args.map((a) => a.value || a.description || '').join(' ').slice(0, 300)); });
on('Log.entryAdded', (p) => { if (p.entry.level === 'error') consoleErrors.push(`log: ${p.entry.text.slice(0, 200)} ${p.entry.url || ''}`); });
on('Network.requestWillBeSent', (p) => {
  reqUrl.set(p.requestId, p.request.url);
  try { const h = new URL(p.request.url).host; hosts.set(h, (hosts.get(h) || 0) + 1); if (h !== new URL(url).host && externalUrls.length < 60) externalUrls.push(p.request.url.slice(0, 160)); } catch { /* ignore */ }
});
on('Network.loadingFailed', (p) => { if (!p.canceled) failed.push(`${reqUrl.get(p.requestId) || p.requestId} (${p.errorText})`); });
on('Network.responseReceived', (p) => { if (p.response.status >= 400) badStatus.push(`${p.response.status} ${p.response.url}`); });

dbg('ws open');
await send('Page.enable');
await send('Runtime.enable');
await send('Network.enable');
await send('Log.enable');
await send('Network.setCacheDisabled', { cacheDisabled: true });
await send('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile, screenWidth: width, screenHeight: height });
if (mobile) await send('Emulation.setTouchEmulationEnabled', { enabled: true });

const loaded = new Promise((res) => on('Page.loadEventFired', res));
dbg('navigate');
await send('Page.navigate', { url });
await Promise.race([loaded, sleep(40000)]);
dbg('loaded');
await sleep(waitMs);

// scroll through the page so lazyload + appear animations fire, then back up
const total = await evaluate('document.body.scrollHeight');
dbg('height', total);
for (let y = 0; y < total; y += Math.floor(height * 0.8)) {
  await evaluate(`window.scrollTo(0, ${y})`);
  await sleep(200);
}
await evaluate('window.scrollTo(0, document.body.scrollHeight)');
await sleep(600);
await evaluate('window.scrollTo(0, 0)');
await sleep(Math.max(1000, waitMs / 2));

const metricsJson = await evaluate(`JSON.stringify({
  title: document.title,
  height: document.body.scrollHeight,
  recs: [...document.querySelectorAll('.t-rec')].map(r => r.id + ':' + (r.getAttribute('data-record-type') || '')),
  imgs: document.images.length,
  brokenImgs: [...document.images].filter(i => i.complete && i.naturalWidth === 0 && i.getAttribute('src')).map(i => i.src).slice(0, 20),
  lazyPending: [...document.querySelectorAll('img[data-original]')].filter(i => !i.getAttribute('src')).length,
  bgImgs: [...document.querySelectorAll('[style*="background-image"]')].length,
  text: document.body.innerText.replace(/\\s+/g, ' ').trim(),
  links: [...document.querySelectorAll('a[href]')].map(a => a.getAttribute('href')),
  fonts: [...document.fonts].filter(f => f.status === 'loaded').map(f => f.family).filter((v, i, a) => a.indexOf(v) === i),
  forms: [...document.querySelectorAll('form')].map(f => (f.getAttribute('action') || '') + '|' + (f.getAttribute('data-formactiontype') || '')),
})`);
const metrics = JSON.parse(metricsJson);
dbg('metrics ok');
const text = metrics.text; delete metrics.text;
metrics.textLen = text.length;
metrics.textHash = createHash('sha1').update(text).digest('hex').slice(0, 12);
metrics.textHead = text.slice(0, 160);

// full-page screenshot as viewport-high slices (a single 16000px capture hangs
// headless Chrome); verify_page.py stitches them.
const lm = await send('Page.getLayoutMetrics');
const fullH = Math.ceil((lm.cssContentSize || lm.contentSize).height);
const MAX_SLICES = 24;
const slices = [];
for (let i = 0, y = 0; y < fullH && i < MAX_SLICES; i++, y += height) {
  const h = Math.min(height, fullH - y);
  dbg('slice', i, y, h);
  const shot = await send('Page.captureScreenshot', {
    format: 'png', captureBeyondViewport: true, fromSurface: true,
    clip: { x: 0, y, width, height: h, scale: 1 },
  });
  const f = `${outPrefix}.slice${String(i).padStart(2, '0')}.png`;
  fs.writeFileSync(f, Buffer.from(shot.data, 'base64'));
  slices.push(f);
}
const truncated = fullH > MAX_SLICES * height;

const pageHost = new URL(url).host;
const external = [...hosts.entries()].filter(([h]) => h !== pageHost).map(([h, n]) => `${h} (${n})`);
const out = {
  url, width, mobile, ...metrics, consoleErrors, failedRequests: failed, badStatus,
  externalHosts: external, externalUrls, requestCount: [...hosts.values()].reduce((a, b) => a + b, 0),
  slices, fullHeight: fullH, truncated, textFile: outPrefix + '.txt',
};
fs.writeFileSync(outPrefix + '.txt', text);
fs.writeFileSync(outPrefix + '.json', JSON.stringify(out, null, 2));
console.log(JSON.stringify({ url, height: metrics.height, recs: metrics.recs.length, broken: metrics.brokenImgs.length, errors: consoleErrors.length, failed: failed.length, bad: badStatus.length, external }));
ws.close();
cleanup();
process.exit(0);
