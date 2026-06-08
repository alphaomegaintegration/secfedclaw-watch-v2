#!/usr/bin/env python3
"""Tests for go-live tooling: preflight, live custody persistence, ledger CLI."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

pytestmark = pytest.mark.live

import preflight
import connectors
import ledger as L


class TestPreflight(unittest.TestCase):
    def test_go_live_when_polygon_reachable(self):
        probers = {
            "polygon": lambda: (200, {"x-ratelimit-remaining": "4"}),
            "sec_edgar": lambda: (200, {}),
            "x": lambda: (403, {}),
            "reddit": lambda: (None, {"error": "creds not set"}),
        }
        rep = preflight.run_preflight(env={}, probers=probers)
        self.assertEqual(rep["verdict"], "GO_LIVE")
        self.assertTrue(rep["core_market_live"])
        x = next(r for r in rep["results"] if r["source"] == "x")
        self.assertIn("auth", x["mode_if_run"])

    def test_replay_only_when_nothing_reachable(self):
        probers = {"polygon": lambda: (None, {"error": "blocked"}),
                   "sec_edgar": lambda: (403, {})}
        rep = preflight.run_preflight(env={}, probers=probers)
        self.assertEqual(rep["verdict"], "REPLAY_ONLY")

    def test_degraded_when_noncore_only(self):
        probers = {"polygon": lambda: (403, {}), "stocktwits": lambda: (200, {})}
        rep = preflight.run_preflight(env={}, probers=probers)
        self.assertEqual(rep["verdict"], "DEGRADED")


class TestLiveCustody(unittest.TestCase):
    def test_live_fetch_persists_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = connectors.DataConnector(root=Path(tmp), prefer_live=True)
            c._live_ok = True  # pretend Polygon reachable
            c._http_json = lambda url, headers=None: (200, {"results": [{"c": 1.0}]})
            f = c.polygon_prev("ABC")
            self.assertEqual(f.mode, "live")
            self.assertIsNotNone(f.artifact_path)
            self.assertTrue(Path(f.artifact_path).exists())
            self.assertIsNotNone(f.sha256)
            # persisted content round-trips
            self.assertEqual(json.loads(Path(f.artifact_path).read_text())["results"][0]["c"], 1.0)

    def test_text_payload_persists_verbatim(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = connectors.DataConnector(root=Path(tmp), prefer_live=True)
            f = c._live("idx", 200, "CIK|Name|Form\n123|X|4\n", "http://x")
            self.assertTrue(Path(f.artifact_path).read_text().startswith("CIK|Name|Form"))


class TestLabelLedger(unittest.TestCase):
    def test_add_via_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "labels.jsonl"
            pkg = {"ticker": "ABC", "review_priority": "HIGH",
                   "component_scores": {"coordination_score": 70},
                   "social_metrics": {}, "anomaly_evidence_score": 50,
                   "evidence_quality_score": 60, "corroboration": {"n_families_active": 3},
                   "security_class": {"class": "thin_microcap"}}
            L.add_label(pkg, "useful_watch", path=p)
            self.assertEqual(L.summary(p)["n_positive"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
