#!/usr/bin/env python3
"""Tiny CORS-enabled receiver: the browser POSTs rendered HTML here so it lands
on disk without passing through the chat. POST /save?name=<file> body=<text>.
Files are written under tools/rendered/. Usage: python3 tools/receiver.py 8765"""
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rendered")
os.makedirs(OUT, exist_ok=True)


class H(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_POST(self):
        q = parse_qs(urlsplit(self.path).query)
        name = os.path.basename(q.get("name", ["out.html"])[0])
        n = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(n)
        with open(os.path.join(OUT, name), "wb") as f:
            f.write(body)
        self.send_response(200)
        self._cors()
        self.end_headers()
        self.wfile.write(f"saved {name} {n} bytes".encode())

    def log_message(self, *a):
        sys.stderr.write("%s - %s\n" % (self.address_string(), a[0] % a[1:]))


HTTPServer(("127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 8765), H).serve_forever()
