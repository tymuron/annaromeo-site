#!/usr/bin/env python3
"""
Parity check for one page: snapshot the live Tilda page and the local mirror
with tools/snap.mjs (headless Chrome via DevTools protocol), then compare.

  python3 tools/verify_page.py /strelna [--mobile]
      [--live https://annaromeo.tilda.ws] [--local http://127.0.0.1:8090]
      [--out tools/verify-out] [--wait 4000]

Prints one JSON object with:
  verdict           "ok" | "check" | "fail"
  problems          list of human-readable findings on the LOCAL copy
  recs_equal        same Tilda blocks in the same order
  height_live/local page heights, diff_share (pixel share differing > 24/255)
  local_console_errors, local_failed_requests, local_bad_status
  local_external     hosts the local page contacted (tildacdn = not independent)
  live_png/local_png/diff_png paths

A page is "ok" when blocks match, heights are within 2%, no local errors,
no failed/4xx requests, no tildacdn hosts contacted, and diff_share < 0.03.
"check" means it needs a human look (usually lazy-image timing or a slider
frame), "fail" means something is actually broken locally.
"""
import json
import os
import re
import subprocess
import sys

from PIL import Image, ImageChops

HERE = os.path.dirname(os.path.abspath(__file__))
# Runtime calls that still go to Tilda but fail gracefully (documented in README):
# phone-mask country lookup and the cart's active-discounts query.
ACCEPTED_TILDA = ("geo.tildaapi.one", "store.tildaapi.one", "geo.tildaapi.com", "store.tildaapi.com")
ALLOWED_EXTERNAL = ("fonts.googleapis.com", "fonts.gstatic.com", "mc.yandex.ru", "mc.yandex.com",
                    "player.vimeo.com", "i.vimeocdn.com", "f.vimeocdn.com", "vimeo.com",
                    "unpkg.com", "cdn.jsdelivr.net", "www.instagram.com", "t.me", "wa.me",
                    "www.youtube.com", "www.youtube-nocookie.com", "i.ytimg.com", "youtube.com")


def arg(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def snap(url, prefix, mobile, wait):
    cmd = ["node", os.path.join(HERE, "snap.mjs"), url, prefix, "--wait", str(wait)]
    if mobile:
        cmd.append("--mobile")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=200)
    if r.returncode != 0:
        raise RuntimeError(f"snap failed for {url}: {r.stderr[-500:]}")
    with open(prefix + ".json", encoding="utf-8") as f:
        data = json.load(f)
    # stitch the viewport slices into one tall PNG
    ims = [Image.open(p).convert("RGB") for p in data["slices"]]
    w = max(i.width for i in ims)
    h = sum(i.height for i in ims)
    full = Image.new("RGB", (w, h), (255, 255, 255))
    y = 0
    for im in ims:
        full.paste(im, (0, y))
        y += im.height
    full.save(prefix + ".png")
    for p in data["slices"]:
        os.remove(p)
    data["png"] = prefix + ".png"
    return data


def pixel_diff(a, b, d):
    ia, ib = Image.open(a).convert("RGB"), Image.open(b).convert("RGB")
    w, h = min(ia.width, ib.width), min(ia.height, ib.height)
    ia, ib = ia.crop((0, 0, w, h)), ib.crop((0, 0, w, h))
    diff = ImageChops.difference(ia, ib).convert("L")
    hist = diff.histogram()
    total = sum(hist) or 1
    share = sum(hist[25:]) / total
    diff.point(lambda v: 255 if v > 24 else 0).save(d)
    return round(share, 4)


def main():
    path = sys.argv[1]
    mobile = "--mobile" in sys.argv
    live = arg("--live", "https://annaromeo.tilda.ws").rstrip("/")
    local = arg("--local", "http://127.0.0.1:8090").rstrip("/")
    out = arg("--out", os.path.join(HERE, "verify-out"))
    wait = int(arg("--wait", "4000"))
    slug = (path.strip("/").replace("/", "_") or "home") + ("_mobile" if mobile else "")
    os.makedirs(out, exist_ok=True)
    a = snap(live + path, os.path.join(out, slug + ".live"), mobile, wait)
    b = snap(local + path, os.path.join(out, slug + ".local"), mobile, wait)
    d = os.path.join(out, slug + ".diff.png")
    share = pixel_diff(a["png"], b["png"], d)

    problems = []
    recs_equal = a["recs"] == b["recs"]
    if not recs_equal:
        problems.append(f"block list differs: live {len(a['recs'])} vs local {len(b['recs'])}")
    hdiff = abs(a["height"] - b["height"]) / max(a["height"], 1)
    if hdiff > 0.02:
        problems.append(f"height differs {a['height']} vs {b['height']}")
    if b["brokenImgs"]:
        problems.append(f"broken images locally: {b['brokenImgs'][:5]}")
    def norm(e):
        return re.sub(r"https?://[^\s)]+", "<url>", e)
    live_errs = {norm(e) for e in a["consoleErrors"]}
    new_errs = [e for e in b["consoleErrors"] if norm(e) not in live_errs]
    if new_errs:
        problems.append(f"console errors locally: {new_errs[:5]}")
    elif b["consoleErrors"]:
        problems.append(f"info: same console errors as live: {b['consoleErrors'][:2]}")
    if b["failedRequests"]:
        problems.append(f"failed requests locally: {b['failedRequests'][:5]}")
    if b["badStatus"]:
        problems.append(f"4xx/5xx locally: {b['badStatus'][:5]}")
    tilda_hosts = [h for h in b["externalHosts"] if "tilda" in h and not h.startswith(ACCEPTED_TILDA)]
    if tilda_hosts:
        problems.append(f"still contacts Tilda: {tilda_hosts}")
    accepted = [h for h in b["externalHosts"] if h.startswith(ACCEPTED_TILDA)]
    if accepted:
        problems.append(f"info: accepted Tilda runtime calls {accepted}")
    unknown_hosts = [h for h in b["externalHosts"] if "tilda" not in h and not h.startswith(" ")
                     and not any(h.startswith(x) for x in ALLOWED_EXTERNAL)]
    if unknown_hosts:
        problems.append(f"unexpected external hosts: {unknown_hosts}")
    # Tilda's screen-reader skip link (opacity:0) picks its language from a
    # race between <html lang> and window.browserLang, so it flips in both
    # directions between runs. Ignore it when comparing visible text.
    def strip_skiplink(t):
        for phrase in ("To main content", "К основному контенту"):
            t = t.replace(phrase, "")
        return t.strip()
    live_txt = strip_skiplink(open(a["textFile"], encoding="utf-8").read())
    local_txt = strip_skiplink(open(b["textFile"], encoding="utf-8").read())
    if live_txt != local_txt:
        problems.append(f"visible text differs (len {len(live_txt)} vs {len(local_txt)})")
    if share >= 0.03:
        problems.append(f"pixel diff share {share}")

    hard = [p for p in problems if p.startswith(("broken", "console", "failed", "4xx", "still contacts", "block list"))]
    soft = [p for p in problems if not p.startswith("info:") and p not in hard]
    verdict = "fail" if hard else ("check" if soft else "ok")
    print(json.dumps({
        "path": path, "mobile": mobile, "verdict": verdict, "problems": problems,
        "recs_equal": recs_equal, "height_live": a["height"], "height_local": b["height"],
        "diff_share": share, "local_console_errors": b["consoleErrors"], "local_failed_requests": b["failedRequests"],
        "local_bad_status": b["badStatus"], "local_external": b["externalHosts"], "live_external": a["externalHosts"],
        "live_png": a["png"], "local_png": b["png"], "diff_png": d,
        "live_text": a["textFile"], "local_text": b["textFile"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
