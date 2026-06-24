#!/usr/bin/env python3
"""Tests for the local dashboard server + digest deep-link."""
import os
import sys
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import serve
import notify


class TestServe(unittest.TestCase):
    def test_serves_out_and_redirects_root(self):
        # Serve from a TEMP dir, never serve.OUT — writing the stub into the real
        # out/ clobbered the operator's generated dashboard_v2.html on every run.
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            (out / "dashboard_v2.html").write_text("<html><body>SECFEDCLAW</body></html>")
            srv = serve.make_server(out, "127.0.0.1", 0)
            port = srv.server_address[1]
            t = threading.Thread(target=srv.serve_forever, daemon=True)
            t.start()
            try:
                # direct file
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/dashboard_v2.html", timeout=5) as r:
                    self.assertEqual(r.status, 200)
                    self.assertIn("SECFEDCLAW", r.read().decode())
                # root redirects to dashboard
                req = urllib.request.Request(f"http://127.0.0.1:{port}/")
                with urllib.request.urlopen(req, timeout=5) as r:
                    self.assertEqual(r.status, 200)  # urllib follows the 302
            finally:
                srv.shutdown()
                srv.server_close()


class TestServeHardening(unittest.TestCase):
    """Security headers on every response; no directory autoindex; generic Server."""

    def _serve(self, out):
        srv = serve.make_server(out, "127.0.0.1", 0)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        return srv, srv.server_address[1]

    def test_security_headers_and_no_version_disclosure(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            (out / "dashboard_v2.html").write_text("<html><body>SECFEDCLAW</body></html>")
            srv, port = self._serve(out)
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/dashboard_v2.html", timeout=5) as r:
                    h = r.headers
                self.assertEqual(h.get("X-Content-Type-Options"), "nosniff")
                self.assertEqual(h.get("X-Frame-Options"), "DENY")
                self.assertEqual(h.get("Referrer-Policy"), "no-referrer")
                self.assertIn("default-src 'none'", h.get("Content-Security-Policy", ""))
                self.assertNotIn("Python/", h.get("Server", ""))  # version not disclosed
            finally:
                srv.shutdown(); srv.server_close()

    def test_directory_listing_disabled(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            (out / "dashboard_v2.html").write_text("<html>x</html>")
            (out / "usage").mkdir()
            (out / "usage" / "llm_usage.jsonl").write_text('{"x":1}\n')
            srv, port = self._serve(out)
            try:
                # the directory itself must 404 (no autoindex), but a known file is still served
                with self.assertRaises(urllib.error.HTTPError) as cm:
                    urllib.request.urlopen(f"http://127.0.0.1:{port}/usage/", timeout=5)
                self.assertEqual(cm.exception.code, 404)
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/usage/llm_usage.jsonl", timeout=5) as r:
                    self.assertEqual(r.status, 200)
            finally:
                srv.shutdown(); srv.server_close()


class TestDigestLink(unittest.TestCase):
    def test_env_url_used(self):
        os.environ["SECFEDCLAW_DASHBOARD_URL"] = "http://127.0.0.1:8787/dashboard_v2.html"
        try:
            url = notify.dashboard_url({})
            self.assertEqual(url, "http://127.0.0.1:8787/dashboard_v2.html")
            q = {"review_queue": [{"ticker": "AMC", "review_priority": "HIGH", "watch_score": 60,
                                   "anomaly_evidence_score": 62, "security_class": "small_cap",
                                   "n_families_active": 3}]}
            txt = notify.compose_digest(q, None, url=url)
            self.assertIn("Dashboard: http://127.0.0.1:8787/dashboard_v2.html", txt)
        finally:
            os.environ.pop("SECFEDCLAW_DASHBOARD_URL", None)

    def test_default_file_uri(self):
        os.environ.pop("SECFEDCLAW_DASHBOARD_URL", None)
        url = notify.dashboard_url({})
        self.assertTrue(url.startswith("file://"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
