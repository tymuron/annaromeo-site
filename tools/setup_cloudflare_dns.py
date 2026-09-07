#!/usr/bin/env python3
"""
Point a Cloudflare-managed domain at a Render service, the way Render needs it.

Render wants CNAME records for both the root and www (Cloudflare flattens the
apex CNAME), left UNPROXIED until Render has issued the certificate, an SSL
mode of Full, and no AAAA records.

  CF_API_TOKEN=... python3 tools/setup_cloudflare_dns.py \
      annaromeovastu.com annaromeo-vastu.onrender.com [--proxy] [--dry]

--proxy turns the orange cloud back on; only do that once Render reports the
certificate as issued, otherwise verification fails.
"""
import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api.cloudflare.com/client/v4"


def call(method, path, token, body=None):
    req = urllib.request.Request(
        API + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


def main():
    token = os.environ.get("CF_API_TOKEN")
    if not token:
        print("set CF_API_TOKEN")
        sys.exit(2)
    domain, target = sys.argv[1], sys.argv[2]
    proxied = "--proxy" in sys.argv
    dry = "--dry" in sys.argv

    z = call("GET", f"/zones?name={domain}", token)
    if not z.get("success") or not z.get("result"):
        print("cannot read zone:", json.dumps(z.get("errors") or z)[:300])
        sys.exit(1)
    zone = z["result"][0]
    zid = zone["id"]
    print(f"zone {domain} = {zid} (plan {zone.get('plan',{}).get('name')}, status {zone.get('status')})")

    recs = call("GET", f"/zones/{zid}/dns_records?per_page=200", token)["result"]
    print(f"existing records: {len(recs)}")
    for r in recs:
        print(f"  {r['type']:6} {r['name']:32} -> {str(r.get('content'))[:44]}  proxied={r.get('proxied')}")

    wanted = [("@", domain), ("www", "www." + domain)]
    for label, fqdn in wanted:
        body = {"type": "CNAME", "name": fqdn, "content": target,
                "ttl": 1, "proxied": proxied,
                "comment": "Render static site"}
        existing = [r for r in recs if r["name"] == fqdn and r["type"] in ("CNAME", "A", "AAAA")]
        if dry:
            print(f"would set {fqdn} CNAME -> {target} proxied={proxied} (replacing {len(existing)})")
            continue
        # remove anything already occupying the name
        for r in existing:
            if r["type"] == "CNAME" and r["content"] == target:
                upd = call("PATCH", f"/zones/{zid}/dns_records/{r['id']}", token, {"proxied": proxied})
                print(f"  updated {fqdn}: proxied={proxied} ok={upd.get('success')}")
                break
            d = call("DELETE", f"/zones/{zid}/dns_records/{r['id']}", token)
            print(f"  deleted {r['type']} {fqdn} ok={d.get('success')}")
        else:
            res = call("POST", f"/zones/{zid}/dns_records", token, body)
            if res.get("success"):
                print(f"  created {fqdn} CNAME -> {target} proxied={proxied}")
            else:
                print(f"  FAILED {fqdn}: {json.dumps(res.get('errors'))[:220]}")

    # AAAA records break Render (no IPv6 support there)
    for r in recs:
        if r["type"] == "AAAA" and not dry:
            d = call("DELETE", f"/zones/{zid}/dns_records/{r['id']}", token)
            print(f"  deleted AAAA {r['name']} ok={d.get('success')}")

    if not dry:
        ssl = call("PATCH", f"/zones/{zid}/settings/ssl", token, {"value": "full"})
        print("ssl mode -> full:", ssl.get("success"), (json.dumps(ssl.get("errors"))[:160] if not ssl.get("success") else ""))
        aut = call("PATCH", f"/zones/{zid}/settings/always_use_https", token, {"value": "on"})
        print("always use https -> on:", aut.get("success"))

    final = call("GET", f"/zones/{zid}/dns_records?per_page=200", token)["result"]
    print("\nfinal records:")
    for r in final:
        print(f"  {r['type']:6} {r['name']:32} -> {str(r.get('content'))[:44]}  proxied={r.get('proxied')}")


if __name__ == "__main__":
    main()
