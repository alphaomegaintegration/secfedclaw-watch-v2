#!/usr/bin/env python3
"""Tests for the daily digest notifier."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import notify

QUEUE = {"data_mode": "live", "universe_size": 20, "review_queue": [
    {"ticker": "AMC", "review_priority": "HIGH", "watch_score": 58.2,
     "anomaly_evidence_score": 61.0, "security_class": "small_cap", "n_families_active": 3},
    {"ticker": "XYZ", "review_priority": "MEDIUM", "watch_score": 33.0,
     "anomaly_evidence_score": 40.0, "security_class": "thin_microcap", "n_families_active": 2},
    {"ticker": "AAPL", "review_priority": "LOW", "watch_score": 18.0,
     "anomaly_evidence_score": 14.0, "security_class": "large_cap", "n_families_active": 1},
]}


class TestCompose(unittest.TestCase):
    def test_lists_flagged_only(self):
        txt = notify.compose_digest(QUEUE, {"preflight_verdict": "GO_LIVE"})
        self.assertIn("Flagged for review (≥MEDIUM): 2", txt)
        self.assertIn("AMC", txt)
        self.assertIn("XYZ", txt)
        self.assertNotIn("• AAPL", txt)  # LOW not listed
        self.assertIn("not trading signals", txt)

    def test_empty_flagged(self):
        q = {"review_queue": [{"ticker": "AAPL", "review_priority": "LOW", "watch_score": 5}]}
        txt = notify.compose_digest(q)
        self.assertIn("No tickers reached MEDIUM", txt)


class TestDeliverFallback(unittest.TestCase):
    def test_writes_file_when_unconfigured(self):
        # no telegram creds -> fallback file
        res = notify.deliver(QUEUE, {"preflight_verdict": "REPLAY_ONLY"}, env={})
        self.assertFalse(res["sent"])
        self.assertIn("fallback_file", res)
        self.assertTrue(Path(res["fallback_file"]).exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
