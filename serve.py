#!/usr/bin/env python3
"""Lightweight local static server for the SECFEDCLAW v0.2 dashboard.

Serves the self-contained `out/` directory over plain stdlib HTTP so the
operator can open the console in a browser at a stable URL (and the daily digest
can deep-link to it). `/` redirects to the dashboard.

Security: binds to 127.0.0.1 (localhost) BY DEFAULT — the dashboard carries
enforcement-adjacent WATCH content and must not be exposed on a network or the
public internet without a deliberate, authorized decision. `--host 0.0.0.0` is
allowed but prints a warning; do not use it on untrusted networks.

  python3 serve.py                 # http://127.0.0.1:8787/
  python3 serve.py --port 9000
"""
from __future__ import annotations

import argparse
import functools
import http.server
import socketserver
from pathlib import Path

OUT = Path(__file__).resolve().parent / "out"
DEFAULT_PORT = 8787


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path in ("/", "/index.html"):
            self.send_response(302)
            self.send_header("Location", "/dashboard_v2.html")
            self.end_headers()
            return
        return super().do_GET()

    def log_message(self, *args):  # quiet
        pass


def make_server(directory: Path, host: str = "127.0.0.1", port: int = 0) -> socketserver.TCPServer:
    OUT.mkdir(parents=True, exist_ok=True)
    handler = functools.partial(Handler, directory=str(directory))
    socketserver.TCPServer.allow_reuse_address = True
    return socketserver.TCPServer((host, port), handler)


def main() -> int:
    ap = argparse.ArgumentParser(description="Serve the SECFEDCLAW dashboard locally")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = ap.parse_args()
    if args.host not in ("127.0.0.1", "localhost"):
        print(f"WARNING: binding to {args.host} exposes WATCH content beyond localhost. "
              "Ensure this is an authorized, trusted network.")
    if not (OUT / "dashboard_v2.html").exists():
        print("dashboard_v2.html not found in out/. Run: python3 dashboard_v2.py")
    srv = make_server(OUT, args.host, args.port)
    url = f"http://{args.host}:{srv.server_address[1]}/"
    print(f"SECFEDCLAW dashboard at {url}dashboard_v2.html  (Ctrl-C to stop)")
    print("Set SECFEDCLAW_DASHBOARD_URL to this address so the daily digest deep-links to it.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
