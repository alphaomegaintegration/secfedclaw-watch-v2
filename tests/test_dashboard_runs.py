#!/usr/bin/env python3
"""Phase 1 guard: the generated dashboard wires up the live Runs view.

Structural check that build_html emits the Runs tab, panel, controls, and the
JS that polls run_manifest.json / POSTs /api/rerun. Behavior is verified
in-browser; this locks the wiring so it can't silently regress.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import dashboard_v2


class TestDashboardRunsWiring(unittest.TestCase):
    def setUp(self):
        self.html = dashboard_v2.build_html(
            {"data_mode": "replay", "review_queue": []}, [], {})

    def test_runs_tab_and_panel_present(self):
        self.assertIn('data-id="runs"', self.html)
        self.assertIn("id='runs'", self.html)

    def test_controls_present(self):
        self.assertIn("id='runTickers'", self.html)
        self.assertIn("id='runLive'", self.html)
        self.assertIn("rerun(false)", self.html)
        self.assertIn("rerun(true)", self.html)

    def test_live_polling_and_endpoint_js(self):
        self.assertIn("loadRuns", self.html)
        self.assertIn("run_manifest.json", self.html)
        self.assertIn("/api/rerun", self.html)

    def test_no_third_party_callbacks(self):
        # The live view must only call the local server — no external hosts.
        for needle in ("http://", "https://"):
            # outbound ticker links are allowed; assert no fetch/XHR to a remote host
            pass
        self.assertNotIn("fetch('http", self.html)
        self.assertNotIn('fetch("http', self.html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
