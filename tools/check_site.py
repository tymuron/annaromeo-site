#!/usr/bin/env python3
"""
Static integrity check of the mirrored site. For every HTML page it collects
every local reference (src, href, srcset, data-original, data-bg, data-img,
data-poster, inline style url(), CSS url() inside local stylesheets) and
verifies the file exists on disk. Also reports any remaining *.tildacdn.*
references and any internal link that has no page.

Usage: python3 tools/check_site.py site  -> prints JSON summary, exit 1 on problems
"""
import html
import json
import os
import re
import sys
import urllib.parse

ATTR_RE = re.compile(r'\b(?:src|href|data-original|data-bg|data-img|data-poster|data-content-cover-bg|data-lazy-src|data-imgsrc|poster)=["\']([^"\']+)["\']', re.I)
SRCSET_RE = re.compile(r'\bsrcset=["\']([^"\']+)["\']', re.I)
STYLE_URL_RE = re.compile(r"url\(\s*['\"]?([^)'\"]+)['\"]?\s*\)")
CDN_RE = re.compile(r"[a-z0-9.-]*tildacdn\.[a-z]+[^\s\"'<>()]{0,100}")
EXT_SKIP = re.compile(r"^(https?:)?//|^mailto:|^tel:|^javascript:|^#|^data:|^blob:", re.I)


def local_exists(root, ref, page_dir):
    ref = html.unescape(ref).strip().strip("\"'").split("#")[0].split("?")[0]
    if not ref or ref.isdigit():
        return True
    ref = urllib.parse.unquote(ref)
    if ref.startswith("/"):
        disk = os.path.join(root, ref.lstrip("/"))
    else:
        disk = os.path.normpath(os.path.join(page_dir, ref))
    if os.path.isfile(disk):
        return True
    if os.path.isdir(disk) and os.path.isfile(os.path.join(disk, "index.html")):
        return True
    if os.path.isfile(disk + ".html"):
        return True
    if os.path.isfile(disk.rstrip("/") + "/index.html"):
        return True
    return False


def main():
    root = sys.argv[1]
    problems = {"missing": {}, "cdn_refs": {}, "pages": 0, "refs_checked": 0}
    checked_css = set()
    for d, _, files in os.walk(root):
        for fn in files:
            if not fn.endswith(".html"):
                continue
            p = os.path.join(d, fn)
            rel = os.path.relpath(p, root)
            with open(p, encoding="utf-8", errors="replace") as f:
                doc = f.read()
            problems["pages"] += 1
            refs = set(ATTR_RE.findall(doc))
            for ss in SRCSET_RE.findall(doc):
                for part in ss.split(","):
                    u = part.strip().split(" ")[0]
                    if u:
                        refs.add(u)
            for u in STYLE_URL_RE.findall(doc):
                refs.add(u)
            missing = []
            for r in sorted(refs):
                if EXT_SKIP.search(r):
                    continue
                problems["refs_checked"] += 1
                if not local_exists(root, r, d):
                    missing.append(r)
                # descend into local css
                rr = html.unescape(r).split("?")[0]
                if rr.endswith(".css") and rr.startswith("/"):
                    css_path = os.path.join(root, rr.lstrip("/"))
                    if css_path not in checked_css and os.path.isfile(css_path):
                        checked_css.add(css_path)
                        with open(css_path, encoding="utf-8", errors="replace") as f:
                            css = f.read()
                        cm = []
                        for u in STYLE_URL_RE.findall(css):
                            if EXT_SKIP.search(u):
                                continue
                            problems["refs_checked"] += 1
                            if not local_exists(root, u, os.path.dirname(css_path)):
                                cm.append(u)
                        if cm:
                            problems["missing"][os.path.relpath(css_path, root)] = cm
                        cdn = sorted(set(CDN_RE.findall(css)))
                        if cdn:
                            problems["cdn_refs"][os.path.relpath(css_path, root)] = cdn[:10]
            if missing:
                problems["missing"][rel] = missing
            cdn = sorted(set(CDN_RE.findall(doc)))
            if cdn:
                problems["cdn_refs"][rel] = cdn[:10]
    print(json.dumps(problems, ensure_ascii=False, indent=2))
    sys.exit(1 if problems["missing"] or problems["cdn_refs"] else 0)


if __name__ == "__main__":
    main()
