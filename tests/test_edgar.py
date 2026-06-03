#!/usr/bin/env python3
"""Tests for the EDGAR daily-diff pipeline + scoring integration."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "features"))

from features import edgar
import scoring_v2

MASTER_IDX = """Description: Master Index of EDGAR Dissemination Feed
CIK|Company Name|Form Type|Date Filed|Filename
--------------------------------------------------------------------------------
320193|Apple Inc|4|2026-06-01|edgar/data/320193/0000320193-26-000111.txt
1318605|Tesla Inc|S-3|2026-06-01|edgar/data/1318605/0001318605-26-000222.txt
1318605|Tesla Inc|424B5|2026-06-02|edgar/data/1318605/0001318605-26-000223.txt
1318605|Tesla Inc|4|2026-06-02|edgar/data/1318605/0001318605-26-000224.txt
999999|Some Shell Co|25-NSE|2026-06-02|edgar/data/999999/0000999999-26-000001.txt
111111|Random Co|10-Q|2026-06-02|edgar/data/111111/0000111111-26-000009.txt
"""


class TestParse(unittest.TestCase):
    def test_parse_master_idx(self):
        rows = edgar.parse_master_idx(MASTER_IDX)
        self.assertEqual(len(rows), 6)
        self.assertEqual(rows[0]["cik"], "0000320193")
        self.assertEqual(rows[0]["accession"], "0000320193-26-000111")
        self.assertIn("insider", rows[0]["categories"])

    def test_classify(self):
        self.assertIn("dilution", edgar.classify_form("424B5"))
        self.assertIn("insider", edgar.classify_form("4"))
        self.assertIn("delist", edgar.classify_form("25-NSE"))
        self.assertEqual(edgar.classify_form("10-Q"), [])  # not pump-relevant here


class TestFeatures(unittest.TestCase):
    def test_issuer_features_and_score(self):
        rows = [r for r in edgar.parse_master_idx(MASTER_IDX) if r["cik"] == "0001318605"]
        feats = edgar.build_issuer_features(rows, asof="2026-06-03")
        self.assertTrue(feats["has_recent_dilution"])
        self.assertTrue(feats["has_recent_insider"])
        score, basis = edgar.issuer_event_score(feats)
        self.assertGreater(score, 0)
        self.assertTrue(any("dilution" in b for b in basis))

    def test_empty_features_zero(self):
        score, basis = edgar.issuer_event_score({})
        self.assertEqual(score, 0.0)


class TestScoringIntegration(unittest.TestCase):
    def _f(self, data):
        class F:
            def __init__(s): s.name = "edgar"; s.data = data; s.mode = "replay"; s.status = 200
            def ok(s): return data is not None
            artifact_path = None; sha256 = None; source_url_redacted = None
        return F()

    def test_issuer_event_flows_into_score(self):
        # strong dilution+insider issuer-event payload (as edgar_pipeline writes)
        payload = {"asof": "2026-06-03", "issuer_event_score": 0,
                   "features": {"counts": {"dilution": 3, "insider": 2, "material": 1,
                                            "late": 0, "delist": 1, "registration": 0},
                                "days_since": {"dilution": 2, "insider": 1, "delist": 2}}}
        fetches = {k: self._f(None) for k in
                   ("daily_range", "grouped", "snapshot", "trades", "quotes", "x", "reddit",
                    "otc_threshold", "reg_sho", "halts", "submissions")}
        fetches["reddit_unavailable"] = True
        fetches["edgar"] = self._f(payload)
        pkg = scoring_v2.build_package("TSLA", fetches)
        self.assertGreater(pkg["component_scores"]["issuer_event_score"], 30)
        self.assertIn("issuer_event_score", pkg["component_scores"])
        self.assertEqual(pkg["edgar_issuer_event"]["score"], pkg["component_scores"]["issuer_event_score"])

    def test_absent_edgar_is_zero_and_safe(self):
        fetches = {k: self._f(None) for k in
                   ("daily_range", "grouped", "snapshot", "trades", "quotes", "x", "reddit",
                    "otc_threshold", "reg_sho", "halts", "submissions", "edgar")}
        fetches["reddit_unavailable"] = True
        pkg = scoring_v2.build_package("ZZZZ", fetches)
        self.assertEqual(pkg["component_scores"]["issuer_event_score"], 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
