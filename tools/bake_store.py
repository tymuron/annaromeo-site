#!/usr/bin/env python3
"""
Replace the JS-rendered services catalog on /main with the markup Tilda's
catalog script produced in a real browser (tools/rendered/store-main.html),
and disable the t_store_init call so the page no longer asks Tilda's store
API for the product list.

Usage: python3 tools/bake_store.py site/main/index.html tools/rendered/store-main.html
"""
import re
import sys

START = '<div class="t-store js-store">'


def find_block_end(doc, start):
    """Index just past the </div> that closes the div opened at `start`."""
    depth = 0
    pos = start
    tag_re = re.compile(r"<div\b|</div\s*>", re.I)
    while True:
        m = tag_re.search(doc, pos)
        if not m:
            raise RuntimeError("unbalanced div")
        if m.group(0).lower().startswith("<div"):
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                return m.end()
        pos = m.end()


def main():
    page, rendered = sys.argv[1], sys.argv[2]
    doc = open(page, encoding="utf-8").read()
    new_block = open(rendered, encoding="utf-8").read().strip()
    i = doc.find(START)
    if i < 0:
        raise SystemExit("store block not found")
    j = find_block_end(doc, i)
    old_block = doc[i:j]
    doc = doc[:i] + new_block + doc[j:]
    # stop the catalog script from re-rendering the grid from Tilda's API
    n_init = len(re.findall(r"t_onFuncLoad\('t_store_init',\s*function\(\)\s*\{\s*t_store_init\('\d+',options\);\s*\}\);", doc))
    doc = re.sub(r"t_onFuncLoad\('t_store_init',\s*function\(\)\s*\{\s*t_store_init\('\d+',options\);\s*\}\);", "", doc)
    open(page, "w", encoding="utf-8").write(doc)
    print(f"replaced {len(old_block)} chars with {len(new_block)}; removed {n_init} t_store_init call(s)")


if __name__ == "__main__":
    main()
