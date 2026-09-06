#!/usr/bin/env python3
"""
Point the mirror at its public origin: rewrites <link rel="canonical"> and
<meta property="og:url"> on every page, and the Sitemap line in robots.txt and
every <loc> in sitemap.xml.

Usage: python3 tools/set_origin.py site https://annaromeo.design
"""
import os
import re
import sys


def main():
    root, origin = sys.argv[1], sys.argv[2].rstrip("/")
    n = 0
    for d, _, files in os.walk(root):
        for fn in files:
            if not fn.endswith(".html"):
                continue
            p = os.path.join(d, fn)
            rel = os.path.relpath(p, root)
            if rel == "index.html":
                path = ""
            elif rel.endswith("/index.html"):
                path = "/" + rel[: -len("/index.html")]
            else:
                path = "/" + rel
            canon = origin + path
            doc = open(p, encoding="utf-8").read()
            new = re.sub(r'(<link rel="canonical" href=")[^"]*(")', r"\g<1>" + canon + r"\g<2>", doc)
            new = re.sub(r'(<meta property="og:url" content=")[^"]*(")', r"\g<1>" + canon + r"\g<2>", new)
            if new != doc:
                open(p, "w", encoding="utf-8").write(new)
                n += 1
    for fn in ("robots.txt", "sitemap.xml"):
        p = os.path.join(root, fn)
        if os.path.exists(p):
            txt = open(p, encoding="utf-8").read()
            txt = re.sub(r"https?://[a-zA-Z0-9.-]+(?=/sitemap\.xml|/|<)", origin, txt)
            open(p, "w", encoding="utf-8").write(txt)
    print(f"origin set to {origin} on {n} pages + robots.txt/sitemap.xml")


if __name__ == "__main__":
    main()
