#!/usr/bin/env python3
"""Tests for the local dashboard server + digest deep-link."""
import os
import sys
import threading
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import serve
import notify


class TestServe(unittest.TestCase):
    def test_serves_out_and_redirects_root(self):
        out = serve.OUT
        out.mkdir(parents=True, exist_ok=True)
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
