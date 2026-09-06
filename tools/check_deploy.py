#!/usr/bin/env python3
"""
Confirm the deployed site actually serves every file in site/.

Render's static upload has silently dropped a handful of files on us before:
the build log said "Your site is live" while seven files, including 404.html
and a stylesheet the whole site loads, returned 404. Nothing in the Render
dashboard reports it, so check after every deploy.

  python3 tools/check_deploy.py https://annaromeo-design.onrender.com [--root site]
      [--workers 16] [--retries 2]

Exits non-zero and lists the paths if anything is missing. A clean redeploy
(Render dashboard "Clear build cache & deploy", or the API with
{"clearCache":"clear"}) has fixed it every time.
"""
import concurrent.futures
import os
import sys

import requests

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.0 Safari/605.1.15")


def arg(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def main():
    if len(sys.argv) < 2 or sys.argv[1].startswith("--"):
        print(__doc__)
        sys.exit(2)
    base = sys.argv[1].rstrip("/")
    root = arg("--root", "site")
    workers = int(arg("--workers", "16"))
    retries = int(arg("--retries", "2"))

    files = []
    for d, _, fs in os.walk(root):
        files.extend(os.path.join(d, f) for f in fs)
    print(f"checking {len(files)} files against {base}", flush=True)

    sess = requests.Session()
    sess.headers["User-Agent"] = UA

    def check(p):
        rel = os.path.relpath(p, root).replace(os.sep, "/")
        url = f"{base}/{rel}"
        last = None
        for attempt in range(retries):
            try:
                r = sess.head(url, timeout=30, allow_redirects=True)
                if r.status_code == 200:
                    return None
                last = r.status_code
            except requests.RequestException as e:  # noqa: PERF203
                last = type(e).__name__
        return (last, rel, os.path.getsize(p))

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        missing = [r for r in ex.map(check, files) if r]

    if not missing:
        print("all files serve 200")
        return
    print(f"NOT SERVING 200: {len(missing)} of {len(files)}")
    for status, rel, size in sorted(missing, key=lambda x: x[1]):
        print(f"  {status} {size:>9}  /{rel}")
    print("\nRedeploy with the build cache cleared, then run this again.")
    sys.exit(1)


if __name__ == "__main__":
    main()
