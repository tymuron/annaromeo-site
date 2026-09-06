#!/usr/bin/env python3
"""
Mirror the published Tilda site (annaromeo.tilda.ws) into a self-contained
static folder that can be served from any host (Render static site).

What it does
  1. Fetches every page from the sitemap, the store sitemap, the known hidden
     Tilda pages (header/footer/404) and every internal link it discovers.
  2. Downloads every asset hosted on *.tildacdn.* (CSS, JS, images, fonts,
     favicon, resized thumbnails) and rewrites references to root-relative
     /assets/... paths — in HTML, in CSS (url(...)) and in the per-page JS.
  3. Rewrites internal links from https://annaromeo.design/... and
     annaromeo.tilda.ws/... to root-relative paths.
  4. Drops Tilda-only plumbing that has no meaning off Tilda: the CDN
     fallback loader, dns-prefetch hints and the stats beacon.
  5. Writes 404.html (from /error-page), robots.txt and sitemap.xml.
  6. Writes a JSON report of pages, assets, dead links and any CDN references
     that could not be localised.

Usage:  python3 tools/crawl.py <out_dir> [--origin https://example.com]
"""
import html
import json
import os
import re
import sys
import time
import urllib.parse
from collections import deque

import requests

SRC = "https://annaromeo.tilda.ws"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.0 Safari/605.1.15")

# Hosts that mean "this site" — links to them become root-relative.
SITE_HOSTS = ("annaromeo.design", "www.annaromeo.design", "annaromeo.tilda.ws")

# Tilda pages that are not in the sitemap (header, footer, 404, misc).
HIDDEN_PAGES = [
    "/error-page", "/podval", "/fs",
    "/page30009513.html", "/page46705965.html",
    "/page68596975.html", "/page79481866.html",
]

# CDN hosts we localise. Everything else on tildacdn (ws., neo.) is plumbing.
ASSET_HOST_LABEL = {
    "static.tildacdn.net": "static",
    "static.tildacdn.com": "static",
    "static.tildacdn.one": "static",
    "optim.tildacdn.net": "thb",
    "optim.tildacdn.com": "thb",
    "optim.tildacdn.one": "thb",
    "thb.tildacdn.net": "thb",
    "thb.tildacdn.com": "thb",
    "thb.tildacdn.one": "thb",
    "img.tildacdn.net": "img",
    "img.tildacdn.com": "img",
    "video.tildacdn.com": "video",
    "video.tildacdn.net": "video",
}

ASSET_RE = re.compile(
    r"(?:https?:)?//([a-z0-9-]+\.tildacdn\.(?:net|com|one))(/[^\s\"'<>()\\&]+)"
)
ESC_ASSET_RE = re.compile(
    r"(?:https?:)?\\/\\/([a-z0-9-]+\.tildacdn\.(?:net|com|one))((?:\\/[^\s\"'<>()&\\]+)+)"
)
CSS_URL_RE = re.compile(r"url\(\s*['\"]?((?:https?:)?//[a-z0-9-]+\.tildacdn\.(?:net|com|one)/[^)'\"\s]+)['\"]?\s*\)")

sess = requests.Session()
sess.headers["User-Agent"] = UA


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def fetch(url, binary=False, tries=4):
    last = None
    for i in range(tries):
        try:
            r = sess.get(url, timeout=60)
            if r.status_code == 200:
                return r.content if binary else r.text
            last = r.status_code
            if r.status_code in (404, 410):
                return None
        except requests.RequestException as e:  # noqa: PERF203
            last = repr(e)
        time.sleep(1.5 * (i + 1))
    log(f"  !! failed {url}: {last}")
    return None


def page_path_to_file(path):
    """'/'->index.html, '/x.html'->x.html, '/x'->x/index.html"""
    path = path.split("?")[0].split("#")[0]
    if path in ("", "/"):
        return "index.html"
    path = path.lstrip("/")
    if path.endswith(".html"):
        return path
    return path.rstrip("/") + "/index.html"


class Mirror:
    def __init__(self, out, origin):
        self.out = out
        self.origin = origin.rstrip("/")
        self.pages = {}          # path -> local file
        self.assets = {}         # remote url (no query) -> local root path
        self.asset_bytes = 0
        self.dead_links = {}     # path -> [pages linking to it]
        self.failed_assets = []
        self.queue = deque()
        self.seen_pages = set()

    # ---------- assets ----------
    def local_asset_path(self, host, path):
        label = ASSET_HOST_LABEL.get(host)
        if not label:
            return None
        clean = urllib.parse.unquote(path.split("?")[0])
        # thb.tildacdn.net/<id>/-/resize/504x/name.jpg  -> keep the whole path
        return f"/assets/{label}{clean}"

    def download_asset(self, host, path):
        key = f"https://{host}{path.split('?')[0]}"
        if key in self.assets:
            return self.assets[key]
        local = self.local_asset_path(host, path)
        if local is None:
            return None
        disk = os.path.join(self.out, local.lstrip("/"))
        if not os.path.exists(disk):
            data = fetch(f"https://{host}{path}", binary=True)
            if data is None:
                self.failed_assets.append(key)
                return None
            os.makedirs(os.path.dirname(disk), exist_ok=True)
            with open(disk, "wb") as f:
                f.write(data)
            self.asset_bytes += len(data)
            # CSS and JS may themselves reference CDN assets
            if disk.endswith(".css"):
                self.localise_css(disk)
            elif disk.endswith(".js"):
                self.localise_text_file(disk)
        self.assets[key] = local
        return local

    def localise_css(self, disk):
        with open(disk, "r", encoding="utf-8", errors="replace") as f:
            css = f.read()
        base_dir = os.path.dirname(disk)

        def repl(m):
            url = m.group(1)
            if url.startswith("//"):
                url = "https:" + url
            u = urllib.parse.urlsplit(url)
            local = self.download_asset(u.netloc, u.path + (("?" + u.query) if u.query else ""))
            return f"url({local})" if local else m.group(0)

        new = CSS_URL_RE.sub(repl, css)
        if new != css:
            with open(disk, "w", encoding="utf-8") as f:
                f.write(new)

    def localise_text_file(self, disk):
        with open(disk, "r", encoding="utf-8", errors="replace") as f:
            txt = f.read()
        new = self.localise_text(txt)
        if new != txt:
            with open(disk, "w", encoding="utf-8") as f:
                f.write(new)

    def localise_text(self, txt):
        def repl(m):
            host, path = m.group(1), m.group(2)
            if host not in ASSET_HOST_LABEL:
                return m.group(0)
            local = self.download_asset(host, html.unescape(path))
            if not local:
                return m.group(0)
            return urllib.parse.quote(local, safe="/:@+,;=-._~!$'*")

        def repl_esc(m):
            host, path = m.group(1), m.group(2).replace("\\/", "/")
            if host not in ASSET_HOST_LABEL:
                return m.group(0)
            local = self.download_asset(host, html.unescape(path))
            if not local:
                return m.group(0)
            return urllib.parse.quote(local, safe="/:@+,;=-._~!$'*").replace("/", "\\/")
        txt = ASSET_RE.sub(repl, txt)
        return ESC_ASSET_RE.sub(repl_esc, txt)

    # ---------- pages ----------
    def enqueue(self, path, from_page="seed"):
        path = path.split("#")[0].split("?")[0]
        if not path.startswith("/"):
            return
        if path in self.seen_pages:
            return
        self.seen_pages.add(path)
        self.queue.append((path, from_page))

    def rewrite_links(self, doc):
        # https://annaromeo.design/x , https://www... , http(s)://annaromeo.tilda.ws/x
        host_re = r"https?://(?:www\.)?(?:annaromeo\.design|annaromeo\.tilda\.ws)"
        doc = re.sub(host_re + r"(?=/)", "", doc)
        doc = re.sub(host_re + r"(?=[\"'\s<>)])", "/", doc)
        return doc

    def strip_plumbing(self, doc):
        # CDN fallback loader — would try to re-point failed assets to Tilda.
        doc = re.sub(r"<script[^>]*neo\.tildacdn\.com/js/tilda-fallback[^>]*></script>\s*", "", doc)
        # dns-prefetch / preconnect hints to Tilda hosts
        doc = re.sub(r"<link[^>]*(?:dns-prefetch|preconnect)[^>]*tildacdn[^>]*>\s*", "", doc)
        # stats beacon (tilda-stat) and the x-dns-prefetch meta
        doc = re.sub(r"<script[^>]*tilda-stat-[^>]*></script>\s*", "", doc)
        return doc

    def absolutise_canonical(self, doc, path):
        canon = self.origin + ("" if path == "/" else path)
        doc = re.sub(r'(<link rel="canonical" href=")[^"]*(")', r"\g<1>" + canon + r"\g<2>", doc)
        doc = re.sub(r'(<meta property="og:url" content=")[^"]*(")', r"\g<1>" + canon + r"\g<2>", doc)
        return doc

    def discover_links(self, doc, page):
        for m in re.finditer(r'href=["\']([^"\']+)["\']', doc):
            href = html.unescape(m.group(1)).strip()
            if href.startswith("//"):
                continue
            if href.startswith("http"):
                u = urllib.parse.urlsplit(href)
                if u.netloc not in SITE_HOSTS:
                    continue
                href = u.path or "/"
            if not href.startswith("/"):
                continue
            if href.startswith("/assets/") or href.startswith("/tilda/"):
                continue
            if re.search(r"\.(css|js|png|jpe?g|gif|svg|webp|ico|xml|txt|pdf|mp4)$", href, re.I):
                continue
            self.enqueue(href, page)

    def process_page(self, path, from_page):
        log(f"page {path}")
        raw = fetch(SRC + path)
        if raw is None:
            self.dead_links.setdefault(path, []).append(from_page)
            log(f"  -> 404 (linked from {from_page})")
            return
        # A Tilda 404 comes back as 200 HTML of the error page on some paths;
        # detect by title of the error page for non-seed links.
        doc = raw
        self.discover_links(doc, path)
        doc = self.rewrite_links(doc)
        doc = self.strip_plumbing(doc)
        doc = self.localise_text(doc)
        doc = self.absolutise_canonical(doc, path)
        rel = page_path_to_file(path)
        disk = os.path.join(self.out, rel)
        os.makedirs(os.path.dirname(disk) or ".", exist_ok=True)
        with open(disk, "w", encoding="utf-8") as f:
            f.write(doc)
        self.pages[path] = rel

    # ---------- driver ----------
    def run(self, seeds):
        for s in seeds:
            self.enqueue(s)
        while self.queue:
            path, from_page = self.queue.popleft()
            self.process_page(path, from_page)

    def write_extras(self, sitemap_paths):
        # 404 page
        err = os.path.join(self.out, "error-page", "index.html")
        if os.path.exists(err):
            with open(err, encoding="utf-8") as f:
                doc = f.read()
            with open(os.path.join(self.out, "404.html"), "w", encoding="utf-8") as f:
                f.write(doc)
        # robots + sitemap
        hidden = [p for p in HIDDEN_PAGES]
        robots = ["User-agent: *"] + [f"Disallow: {p}" for p in hidden] + \
                 ["Disallow: /404.html", "", f"Sitemap: {self.origin}/sitemap.xml", ""]
        with open(os.path.join(self.out, "robots.txt"), "w") as f:
            f.write("\n".join(robots))
        urls = [p for p in sitemap_paths if p in self.pages]
        sm = ['<?xml version="1.0" encoding="UTF-8"?>',
              '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
        for p in urls:
            loc = self.origin + ("" if p == "/" else p)
            sm.append(f"  <url><loc>{html.escape(loc)}</loc></url>")
        sm.append("</urlset>\n")
        with open(os.path.join(self.out, "sitemap.xml"), "w") as f:
            f.write("\n".join(sm))

    def leftover_cdn_refs(self):
        left = {}
        for root, _, files in os.walk(self.out):
            for fn in files:
                if not fn.endswith((".html", ".css", ".js")):
                    continue
                p = os.path.join(root, fn)
                with open(p, encoding="utf-8", errors="replace") as f:
                    txt = f.read()
                hits = sorted(set(re.findall(r"[a-z0-9.-]*tildacdn\.[a-z]+[^\s\"'<>()]{0,120}", txt)))
                if hits:
                    left[os.path.relpath(p, self.out)] = hits[:20]
        return left


def sitemap_locs(url):
    txt = fetch(url) or ""
    locs = re.findall(r"<loc>([^<]+)</loc>", txt)
    out = []
    for l in locs:
        u = urllib.parse.urlsplit(l.strip())
        out.append(u.path or "/")
    return out


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    out = sys.argv[1]
    origin = "https://annaromeo-design.onrender.com"
    if "--origin" in sys.argv:
        origin = sys.argv[sys.argv.index("--origin") + 1]
    os.makedirs(out, exist_ok=True)

    if "--localise-file" in sys.argv:
        # Localise one HTML fragment/page in place (assets land in <out>/assets).
        target = sys.argv[sys.argv.index("--localise-file") + 1]
        m = Mirror(out, origin)
        with open(target, encoding="utf-8") as f:
            txt = f.read()
        new = m.localise_text(m.rewrite_links(txt))
        with open(target, "w", encoding="utf-8") as f:
            f.write(new)
        log(f"localised {target}: {len(m.assets)} assets, failed={m.failed_assets}")
        return

    pages = sitemap_locs(SRC + "/sitemap.xml")
    store = sitemap_locs(SRC + "/sitemap-store.xml")
    seeds = pages + store + HIDDEN_PAGES
    log(f"seeds: {len(pages)} sitemap + {len(store)} store + {len(HIDDEN_PAGES)} hidden")

    m = Mirror(out, origin)
    m.run(seeds)
    m.write_extras(pages + store)

    report = {
        "origin": origin,
        "pages": m.pages,
        "page_count": len(m.pages),
        "asset_count": len(m.assets),
        "asset_mb": round(m.asset_bytes / 1e6, 1),
        "dead_links": m.dead_links,
        "failed_assets": m.failed_assets,
        "leftover_cdn_refs": m.leftover_cdn_refs(),
    }
    with open(os.path.join(os.path.dirname(out.rstrip("/")) or ".", "crawl-report.json"), "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    log(json.dumps({k: v for k, v in report.items() if k not in ("pages", "leftover_cdn_refs")},
                   ensure_ascii=False, indent=2))
    log(f"leftover cdn refs in {len(report['leftover_cdn_refs'])} files")


if __name__ == "__main__":
    main()
