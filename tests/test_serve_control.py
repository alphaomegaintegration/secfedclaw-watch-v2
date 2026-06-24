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
                    try:
                        m = json.loads(p.read_text())
                    except (json.JSONDecodeError, ValueError):
                        m = {}  # tolerate a transient partial read between writes
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

    def test_default_runner_regenerates_dashboard(self):
        # A server-triggered rerun must regenerate dashboard_v2.html so the
        # baked-in Status/SRE panel reflects the new run (not just the Runs tab).
        td = __import__("tempfile").TemporaryDirectory()
        out = Path(td.name)
        srv, port, rm = _start(out)  # real RunManager → real scan + dashboard render
        try:
            r = _post(port, "/api/rerun", {"tickers": ["AAPL"]})
            self.assertEqual(r.status, 202)
            html = out / "dashboard_v2.html"
            written = False
            for _ in range(250):  # up to ~5s (scan + render)
                if html.exists() and html.stat().st_size > 0:
                    written = True
                    break
                time.sleep(0.02)
            self.assertTrue(written, "rerun should regenerate dashboard_v2.html")
        finally:
            srv.shutdown()
            srv.server_close()
            td.cleanup()


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestLabelEndpoint(unittest.TestCase):
    """POST /api/label — operator records an outcome label on a package."""
    def setUp(self):
        self._td = __import__("tempfile").TemporaryDirectory()
        self.out = Path(self._td.name)
        self.srv = None

    def tearDown(self):
        if self.srv:
            self.srv.shutdown(); self.srv.server_close()
        self._td.cleanup()

    def _serve(self, token=None):
        self.srv, port, _ = _start(self.out, token=token)
        return port

    def test_label_records_to_ledger(self):
        import ledger
        (self.out / "AMC_20260101T000000Z_watch_v2.json").write_text(
            json.dumps({"ticker": "AMC", "review_priority": "MEDIUM"}))
        cap = {}
        orig_add, orig_sum = ledger.add_label, ledger.summary
        ledger.add_label = lambda pkg, label, note="": (
            cap.update(pkg=pkg, label=label, note=note)
            or {"ticker": pkg.get("ticker"), "label": label, "y": 1})
        ledger.summary = lambda *a, **k: {"n_labels": 7}
        try:
            port = self._serve()
            r = _post(port, "/api/label", {"package": "AMC_20260101T000000Z_watch_v2.json",
                                           "label": "useful_watch", "note": "promoter selling"})
            self.assertEqual(r.status, 200)
            j = json.loads(r.read())
            self.assertTrue(j["recorded"]); self.assertEqual(j["ticker"], "AMC")
            self.assertEqual(j["n_labels"], 7)
            self.assertEqual(cap["label"], "useful_watch")
            self.assertEqual(cap["pkg"]["ticker"], "AMC")  # the loaded package dict
            self.assertEqual(cap["note"], "promoter selling")
        finally:
            ledger.add_label, ledger.summary = orig_add, orig_sum

    def _expect_code(self, body, code):
        port = self._serve()
        with self.assertRaises(urllib.error.HTTPError) as cm:
            _post(port, "/api/label", body)
        self.assertEqual(cm.exception.code, code)

    def test_rejects_invalid_label(self):
        self._expect_code({"package": "AMC_x_watch_v2.json", "label": "guilty"}, 400)

    def test_rejects_path_traversal(self):
        self._expect_code({"package": "../secret.json", "label": "useful_watch"}, 400)

    def test_rejects_non_package_name(self):
        self._expect_code({"package": "evil.txt", "label": "useful_watch"}, 400)

    def test_missing_package_is_404(self):
        self._expect_code({"package": "NOPE_watch_v2.json", "label": "useful_watch"}, 404)

    def test_token_gated(self):
        port = self._serve(token="sekret")
        with self.assertRaises(urllib.error.HTTPError) as cm:
            _post(port, "/api/label", {"package": "X_watch_v2.json", "label": "useful_watch"})
        self.assertEqual(cm.exception.code, 401)


class TestRetrainEndpoint(unittest.TestCase):
    """POST /api/retrain — retrain the model on current labels (loop completion)."""
    def setUp(self):
        self._td = __import__("tempfile").TemporaryDirectory()
        self.out = Path(self._td.name)
        self.srv = None
        self._orig = serve._retrain_model

    def tearDown(self):
        serve._retrain_model = self._orig
        if self.srv:
            self.srv.shutdown(); self.srv.server_close()
        self._td.cleanup()

    def _serve(self, token=None):
        self.srv, port, _ = _start(self.out, token=token)
        return port

    def test_retrain_returns_status(self):
        serve._retrain_model = lambda out_dir: {"retrained": True, "abstain": False,
                                                "cv_auc": 0.91, "n_total": 207, "n_real_labels": 27}
        port = self._serve()
        r = _post(port, "/api/retrain", {})
        self.assertEqual(r.status, 200)
        j = json.loads(r.read())
        self.assertTrue(j["retrained"]); self.assertFalse(j["abstain"])
        self.assertEqual(j["cv_auc"], 0.91); self.assertEqual(j["n_real_labels"], 27)

    def test_retrain_abstain_status(self):
        serve._retrain_model = lambda out_dir: {"retrained": True, "abstain": True,
                                                "reason": "need >= 40 labels"}
        port = self._serve()
        j = json.loads(_post(port, "/api/retrain", {}).read())
        self.assertTrue(j["abstain"]); self.assertIn("40", j["reason"])

    def test_retrain_runner_error_is_500(self):
        def boom(out_dir): raise RuntimeError("training blew up")
        serve._retrain_model = boom
        port = self._serve()
        with self.assertRaises(urllib.error.HTTPError) as cm:
            _post(port, "/api/retrain", {})
        self.assertEqual(cm.exception.code, 500)

    def test_retrain_token_gated(self):
        serve._retrain_model = lambda out_dir: {"retrained": True, "abstain": True, "reason": "x"}
        port = self._serve(token="sekret")
        with self.assertRaises(urllib.error.HTTPError) as cm:
            _post(port, "/api/retrain", {})
        self.assertEqual(cm.exception.code, 401)
