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
import json
import re
import secrets
import socketserver
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

OUT = Path(__file__).resolve().parent / "out"
DEFAULT_PORT = 8787

# Tickers accepted by the control endpoint: uppercase alnum + . and -, bounded.
_TICKER_RE = re.compile(r"^[A-Z0-9.\-]{1,12}$")
_MAX_UNIVERSE = 50

# Injected at server start. _RUN_MANAGER backs the POST /api/rerun control plane.
_REQUIRED_TOKEN: str | None = None
_RUN_MANAGER: "RunManager | None" = None


def _failed_tickers(out_dir: Path) -> list[str]:
    """Tickers whose status was 'error' in the last run_manifest.json."""
    try:
        m = json.loads((Path(out_dir) / "run_manifest.json").read_text())
    except Exception:
        return []
    return [t for t, info in (m.get("tickers") or {}).items()
            if isinstance(info, dict) and info.get("status") == "error"]


class RunManager:
    """Serializes dashboard-triggered scans. One run at a time; the run executes
    in a daemon thread so the HTTP request returns immediately. The run writes
    out/run_manifest.json incrementally, which the dashboard polls for status.

    `runner(universe, live, out_dir)` is injectable for tests; the default calls
    scan.run_scan (imported lazily so a plain static server pays no import cost).
    """

    def __init__(self, out_dir, runner=None):
        self.out_dir = Path(out_dir)
        self._runner = runner or self._default_runner
        self._lock = threading.Lock()
        self._running = False
        self.last_run_id: str | None = None

    def is_running(self) -> bool:
        with self._lock:
            return self._running

    def start(self, universe: list[str], live: bool = False) -> str | None:
        """Begin a run; return its run_id, or None if a run is already active."""
        with self._lock:
            if self._running:
                return None
            self._running = True
        run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        self.last_run_id = run_id
        t = threading.Thread(target=self._run, args=(list(universe), bool(live)), daemon=True)
        t.start()
        return run_id

    def _run(self, universe, live):
        try:
            self._runner(universe, live, self.out_dir)
        except Exception:  # a failed run must still release the lock
            pass
        finally:
            with self._lock:
                self._running = False

    @staticmethod
    def _default_runner(universe, live, out_dir):
        import scan  # lazy: avoids pulling the whole pipeline into a static serve
        scan.run_scan(list(universe), prefer_live=live, out_dir=out_dir)


class Handler(http.server.SimpleHTTPRequestHandler):
    def _authorized(self) -> bool:
        """True if no token is configured, or the request carries a valid one
        (?token= query param or Authorization: Bearer header)."""
        if not _REQUIRED_TOKEN:
            return True
        qs = parse_qs(urlparse(self.path).query)
        bearer = (self.headers.get("Authorization") or "").removeprefix("Bearer ").strip()
        provided = (qs.get("token") or [""])[0] or bearer
        return secrets.compare_digest(provided, _REQUIRED_TOKEN)

    def _send(self, code: int, ctype: str, body: bytes):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        if not self._authorized():
            return self._send(401, "text/plain", b"401 Unauthorized: missing or invalid token\n")
        if self.path.split("?")[0] in ("/", "/index.html"):
            dest = "/dashboard_v2.html"
            if _REQUIRED_TOKEN:
                dest += f"?token={_REQUIRED_TOKEN}"
            self.send_response(302)
            self.send_header("Location", dest)
            self.end_headers()
            return
        return super().do_GET()

    def do_POST(self):  # noqa: N802
        # Control plane: trigger a re-run. Same token gate as GET.
        if not self._authorized():
            return self._send(401, "text/plain", b"401 Unauthorized: missing or invalid token\n")
        if self.path.split("?")[0] != "/api/rerun":
            return self._send(404, "text/plain", b"404 Not Found\n")
        # application/json only: a cross-origin JSON POST triggers a CORS
        # preflight this server never answers, so this blocks form-based CSRF
        # from a page open in the operator's browser.
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype != "application/json":
            return self._send(415, "text/plain", b"415 Unsupported Media Type: send application/json\n")
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0 or length > 10_000:
            return self._send(400, "text/plain", b"400 Bad Request: empty or oversized body\n")
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            assert isinstance(body, dict)
        except Exception:
            return self._send(400, "text/plain", b"400 Bad Request: invalid JSON object\n")

        live = bool(body.get("live", False))
        if body.get("failed"):
            universe = _failed_tickers(_RUN_MANAGER.out_dir) if _RUN_MANAGER else []
            if not universe:
                return self._send(400, "text/plain", b"400 Bad Request: no failed tickers in last run\n")
        else:
            raw = body.get("tickers")
            if not isinstance(raw, list) or not raw:
                return self._send(400, "text/plain", b"400 Bad Request: tickers must be a non-empty list\n")
            if len(raw) > _MAX_UNIVERSE:
                return self._send(400, "text/plain", f"400 Bad Request: at most {_MAX_UNIVERSE} tickers\n".encode())
            universe = []
            for t in raw:
                tu = t.strip().upper() if isinstance(t, str) else ""
                if not _TICKER_RE.match(tu):
                    return self._send(400, "text/plain", f"400 Bad Request: invalid ticker {t!r}\n".encode())
                universe.append(tu)

        if _RUN_MANAGER is None:
            return self._send(503, "text/plain", b"503 control plane unavailable\n")
        run_id = _RUN_MANAGER.start(universe, live=live)
        if run_id is None:
            return self._send(409, "application/json",
                              json.dumps({"error": "a run is already in progress"}).encode())
        return self._send(202, "application/json", json.dumps({
            "status": "started", "run_id": run_id,
            "universe": universe, "mode": "live" if live else "replay",
        }).encode())

    def log_message(self, *args):  # quiet
        pass


def make_server(directory: Path, host: str = "127.0.0.1", port: int = 0,
                token: str | None = None,
                run_manager: "RunManager | None" = None) -> socketserver.TCPServer:
    global _REQUIRED_TOKEN, _RUN_MANAGER
    _REQUIRED_TOKEN = token
    _RUN_MANAGER = run_manager or RunManager(out_dir=directory)
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
