#!/usr/bin/env python3
"""Tests for the SEC enforcement-history family + per-class backtest."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "features"))

from features import enforcement as enf
import scoring_v2
import backtest

RSS = """<?xml version="1.0"?><rss><channel>
<item><title>SEC Charges ABCD Corp and CEO with Pump-and-Dump</title>
<link>https://www.sec.gov/litigation/litreleases/lr1.htm</link>
<pubDate>2024-01-02</pubDate><description>The SEC charged ABCD Corp ...</description></item>
<item><title>SEC Obtains Judgment in Unrelated Matter</title>
<link>https://www.sec.gov/litigation/litreleases/lr2.htm</link>
<pubDate>2024-01-03</pubDate><description>Some other company.</description></item>
</channel></rss>"""


class TestEnforcement(unittest.TestCase):
    def test_parse_and_match_ticker(self):
        items = enf.parse_releases(RSS)
        self.assertEqual(len(items), 2)
        matched = enf.match_releases(items, "ABCD")
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["match"], "ticker")
        score, basis = enf.enforcement_score(matched)
        self.assertGreaterEqual(score, 30)
        self.assertTrue(any("BACKWARD-LOOKING" in b for b in basis))

    def test_no_match_zero(self):
        score, _ = enf.enforcement_score([])
        self.assertEqual(score, 0.0)

    def test_issuer_name_match(self):
        items = enf.parse_releases(RSS)
        matched = enf.match_releases(items, "ZZ", issuer_name="ABCD Corporation")
        self.assertTrue(any(m["match"] == "issuer_name" for m in matched))


class TestScoringFamily(unittest.TestCase):
    def _f(self, data):
        class F:
            def __init__(s): s.name = "t"; s.data = data; s.mode = "replay"; s.status = 200
            def ok(s): return data is not None
            artifact_path = None; sha256 = None; source_url_redacted = None
        return F()

    def test_enforcement_in_package(self):
        fetches = {k: self._f(None) for k in
                   ("daily_range", "grouped", "snapshot", "trades", "quotes", "x", "reddit",
                    "stocktwits", "otc_threshold", "reg_sho", "halts", "submissions", "edgar")}
        fetches["reddit_unavailable"] = True
        fetches["litigation"] = self._f(RSS)
        pkg = scoring_v2.build_package("ABCD", fetches)
        self.assertIn("enforcement_history_score", pkg["component_scores"])
        self.assertGreaterEqual(pkg["component_scores"]["enforcement_history_score"], 30)
        self.assertTrue(pkg["enforcement_history"]["matched_releases"])
        self.assertTrue(any("BACKWARD-LOOKING" in lim for lim in pkg["limitations"]))


class TestPerClass(unittest.TestCase):
    def test_per_class_breakdown_spans_classes(self):
        out = backtest.per_class_breakdown(n_per_class=20, seed=1, threshold="MEDIUM")
        self.assertGreaterEqual(len(out), 2)  # multiple liquidity classes represented
        for cls, c in out.items():
            for k in ("precision", "recall", "f1", "n"):
                self.assertIn(k, c)


if __name__ == "__main__":
    unittest.main(verbosity=2)
