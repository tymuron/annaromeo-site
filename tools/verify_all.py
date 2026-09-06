#!/usr/bin/env python3
"""Run tools/verify_page.py over many pages with a small worker pool.

  python3 tools/verify_all.py [--pages /a /b ...] [--all] [--mobile] [--workers 3]
      [--local https://site.onrender.com] [--live https://annaromeo.tilda.ws]
      [--wait 4000] [--out tools/verify-out/summary.json]

--all takes every page from crawl-report.json. Prints a one-line summary per
page and writes the full results to the summary file.
"""
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def run(path, mobile, passthrough=()):
    cmd = [sys.executable, "-W", "ignore", os.path.join(HERE, "verify_page.py"), path]
    if mobile:
        cmd.append("--mobile")
    cmd.extend(passthrough)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        line = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
        return json.loads(line) if line.startswith("{") else {"path": path, "verdict": "error", "problems": [r.stderr[-300:]]}
    except Exception as e:  # noqa: BLE001
        return {"path": path, "verdict": "error", "problems": [repr(e)[:300]]}


def main():
    argv = sys.argv[1:]
    mobile = "--mobile" in argv
    workers = int(argv[argv.index("--workers") + 1]) if "--workers" in argv else 3
    out = argv[argv.index("--out") + 1] if "--out" in argv else os.path.join(HERE, "verify-out", "summary" + ("-mobile" if mobile else "") + ".json")
    if "--all" in argv:
        rep = json.load(open(os.path.join(ROOT, "crawl-report.json")))
        pages = sorted(rep["pages"].keys())
    else:
        i = argv.index("--pages")
        pages = [a for a in argv[i + 1:] if a.startswith("/")]
    # forward --local / --live / --wait / --out-dir to verify_page.py
    passthrough = []
    for flag in ("--local", "--live", "--wait"):
        if flag in argv:
            passthrough += [flag, argv[argv.index(flag) + 1]]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        results = list(ex.map(lambda p: run(p, mobile, passthrough), pages))
    for r in results:
        print(f"{r.get('verdict','?'):6} {r['path']:60} diff={r.get('diff_share','-')} {'; '.join(r.get('problems', []))[:160]}")
    json.dump(results, open(out, "w"), ensure_ascii=False, indent=1)
    counts = {}
    for r in results:
        counts[r.get("verdict")] = counts.get(r.get("verdict"), 0) + 1
    print("summary:", counts, "->", out)


if __name__ == "__main__":
    main()
