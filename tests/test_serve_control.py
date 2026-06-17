#!/usr/bin/env python3
"""Phase 1 tests: serve.py localhost control endpoint (POST /api/rerun).

The control endpoint can re-run a scan from the dashboard. It must be:
  - token-gated (same as GET) when a token is configured,
  - application/json only (blocks form-based CSRF; cross-origin JSON POST needs
    a preflight the server never grants),
  - strict on ticker input,
  - single-run (409 while a run is in progress).

Deterministic / stdlib unittest. No network — runs use injected fake runners
except the one explicit default-runner integration test (replay only).
"""
import json
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import serve


def _start(out_dir, token=None, runner=None):
    rm = serve.RunManager(out_dir, runner=runner)
    srv = serve.make_server(Path(out_dir), "127.0.0.1", 0, token=token, run_manager=rm)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv, port, rm


def _post(port, path, body, token=None, ctype="application/json"):
    data = json.dumps(body).encode() if body is not None else b""
    url = f"http://127.0.0.1:{port}{path}"
    if token:
        url += f"?token={token}"
    req = urllib.request.Request(url, data=data, method="POST")
    if ctype:
        req.add_header("Content-Type", ctype)
    return urllib.request.urlopen(req, timeout=5)


class TestControlEndpoint(unittest.TestCase):
    def setUp(self):
        self._td = __import__("tempfile").TemporaryDirectory()
        self.out = Path(self._td.name)
        self.calls = []
        self.srv = None

    def tearDown(self):
        if self.srv:
            self.srv.shutdown()
            self.srv.server_close()
        self._td.cleanup()

    def _fake_runner(self):
        def runner(universe, live, out_dir):
            self.calls.append({"universe": list(universe), "live": live})
        return runner

    def test_rerun_requires_token_when_configured(self):
        self.srv, port, _ = _start(self.out, token="sekret", runner=self._fake_runner())
        with self.assertRaises(urllib.error.HTTPError) as cm:
            _post(port, "/api/rerun", {"tickers": ["AAPL"]})  # no token
        self.assertEqual(cm.exception.code, 401)
        self.assertEqual(self.calls, [])

    def test_rerun_requires_json_content_type(self):
        self.srv, port, _ = _start(self.out, runner=self._fake_runner())
        with self.assertRaises(urllib.error.HTTPError) as cm:
            _post(port, "/api/rerun", {"tickers": ["AAPL"]}, ctype="text/plain")
        self.assertEqual(cm.exception.code, 415)
        self.assertEqual(self.calls, [])

    def test_rerun_rejects_bad_ticker(self):
        self.srv, port, _ = _start(self.out, runner=self._fake_runner())
        with self.assertRaises(urllib.error.HTTPError) as cm:
            _post(port, "/api/rerun", {"tickers": ["AAPL", "rm -rf /"]})
        self.assertEqual(cm.exception.code, 400)
        self.assertEqual(self.calls, [])

    def test_rerun_starts_and_invokes_runner(self):
        self.srv, port, _ = _start(self.out, runner=self._fake_runner())
        r = _post(port, "/api/rerun", {"tickers": ["aapl", "TSLA"]})
        self.assertEqual(r.status, 202)
        payload = json.loads(r.read())
        self.assertEqual(payload["status"], "started")
        self.assertEqual(payload["universe"], ["AAPL", "TSLA"])  # upper-cased
        self.assertEqual(payload["mode"], "replay")              # default safe
        # runner ran in a thread; give it a beat
        for _ in range(50):
            if self.calls:
                break
            time.sleep(0.02)
        self.assertEqual(self.calls, [{"universe": ["AAPL", "TSLA"], "live": False}])

    def test_rerun_conflict_while_running(self):
        gate = threading.Event()

        def blocking_runner(universe, live, out_dir):
            gate.wait(timeout=5)  # hold the run open

        self.srv, port, _ = _start(self.out, runner=blocking_runner)
        r1 = _post(port, "/api/rerun", {"tickers": ["AAPL"]})
        self.assertEqual(r1.status, 202)
        try:
            with self.assertRaises(urllib.error.HTTPError) as cm:
                _post(port, "/api/rerun", {"tickers": ["TSLA"]})
            self.assertEqual(cm.exception.code, 409)
        finally:
            gate.set()

    def test_unknown_post_path_404(self):
        self.srv, port, _ = _start(self.out, runner=self._fake_runner())
        with self.assertRaises(urllib.error.HTTPError) as cm:
            _post(port, "/api/bogus", {})
        self.assertEqual(cm.exception.code, 404)

    def test_rerun_failed_reads_manifest(self):
        manifest = {
            "run_id": "x", "mode": "replay", "universe": ["AAPL", "GME"],
            "finished_utc": "now", "tickers": {
                "AAPL": {"status": "done"},
                "GME": {"status": "error", "error": "boom"},
            },
        }
        (self.out / "run_manifest.json").write_text(json.dumps(manifest))
        self.srv, port, _ = _start(self.out, runner=self._fake_runner())
        r = _post(port, "/api/rerun", {"failed": True})
        self.assertEqual(r.status, 202)
        for _ in range(50):
            if self.calls:
                break
            time.sleep(0.02)
        self.assertEqual(self.calls, [{"universe": ["GME"], "live": False}])

    def test_rerun_failed_with_none_failed_is_400(self):
        manifest = {"tickers": {"AAPL": {"status": "done"}}}
        (self.out / "run_manifest.json").write_text(json.dumps(manifest))
        self.srv, port, _ = _start(self.out, runner=self._fake_runner())
        with self.assertRaises(urllib.error.HTTPError) as cm:
            _post(port, "/api/rerun", {"failed": True})
        self.assertEqual(cm.exception.code, 400)


class TestDefaultRunnerIntegration(unittest.TestCase):
    """One end-to-end check that the real run_scan wiring writes a manifest."""

    def test_default_runner_writes_manifest(self):
        td = __import__("tempfile").TemporaryDirectory()
        out = Path(td.name)
        srv, port, rm = _start(out)  # real RunManager → real scan.run_scan
        try:
            r = _post(port, "/api/rerun", {"tickers": ["AAPL"]})
            self.assertEqual(r.status, 202)
            manifest = None
            for _ in range(150):  # up to ~3s
                p = out / "run_manifest.json"
                if p.exists():
                    m = json.loads(p.read_text())
                    if m.get("finished_utc"):
                        manifest = m
                        break
                time.sleep(0.02)
            self.assertIsNotNone(manifest, "run_manifest.json should be written")
            self.assertIn("AAPL", manifest["tickers"])
        finally:
            srv.shutdown()
            srv.server_close()
            td.cleanup()


if __name__ == "__main__":
    unittest.main(verbosity=2)
