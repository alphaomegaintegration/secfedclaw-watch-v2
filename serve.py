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
import secrets
import socketserver
from pathlib import Path
from urllib.parse import parse_qs, urlparse

OUT = Path(__file__).resolve().parent / "out"
DEFAULT_PORT = 8787

# Token is injected at server start via closure — no global state.
_REQUIRED_TOKEN: str | None = None


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        # Token gate: check ?token= query param or Authorization: Bearer header.
        if _REQUIRED_TOKEN:
            qs = parse_qs(urlparse(self.path).query)
            bearer = (self.headers.get("Authorization") or "").removeprefix("Bearer ").strip()
            provided = (qs.get("token") or [""])[0] or bearer
            if not secrets.compare_digest(provided, _REQUIRED_TOKEN):
                self.send_response(401)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"401 Unauthorized: missing or invalid token\n")
                return
        if self.path.split("?")[0] in ("/", "/index.html"):
            dest = f"/dashboard_v2.html"
            if _REQUIRED_TOKEN:
                dest += f"?token={_REQUIRED_TOKEN}"
            self.send_response(302)
            self.send_header("Location", dest)
            self.end_headers()
            return
        return super().do_GET()

    def log_message(self, *args):  # quiet
        pass


def make_server(directory: Path, host: str = "127.0.0.1", port: int = 0,
                token: str | None = None) -> socketserver.TCPServer:
    global _REQUIRED_TOKEN
    _REQUIRED_TOKEN = token
    OUT.mkdir(parents=True, exist_ok=True)
    handler = functools.partial(Handler, directory=str(directory))
    socketserver.TCPServer.allow_reuse_address = True
    return socketserver.TCPServer((host, port), handler)


def main() -> int:
    ap = argparse.ArgumentParser(description="Serve the SECFEDCLAW dashboard locally")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--token", default=None,
                    help="Shared-secret token required on all requests (?token=… or "
                         "Authorization: Bearer …). Auto-generated when --host is not localhost.")
    args = ap.parse_args()
    token = args.token
    if args.host not in ("127.0.0.1", "localhost"):
        print(f"WARNING: binding to {args.host} exposes WATCH content beyond localhost. "
              "Ensure this is an authorized, trusted network.")
        if not token:
            token = secrets.token_urlsafe(16)
            print(f"Auto-generated access token: {token}")
    if not (OUT / "dashboard_v2.html").exists():
        print("dashboard_v2.html not found in out/. Run: python3 dashboard_v2.py")
    srv = make_server(OUT, args.host, args.port, token=token)
    url = f"http://{args.host}:{srv.server_address[1]}/"
    dashboard_url = f"{url}dashboard_v2.html"
    if token:
        dashboard_url += f"?token={token}"
    print(f"SECFEDCLAW dashboard at {dashboard_url}  (Ctrl-C to stop)")
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
