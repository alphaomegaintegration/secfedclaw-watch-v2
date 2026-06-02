#!/usr/bin/env python3
"""Deterministic tests for SECFEDCLAW scoring v0.2 (stdlib unittest)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "features"))

import robust_stats as rs
from features import market as mkt
from features import coordination as coord
from features import social as soc
import scoring_v2


def _synthetic_daily(jump=False):
    """40 flat days, optionally a price+volume spike on the last day."""
    res = []
    price = 10.0
    for i in range(40):
        v = 1_000_000
        o = price
        c = price * (1.001 if i % 2 else 0.999)
        if jump and i == 39:
            c = price * 1.45      # +45% close
            v = 25_000_000        # 25x volume
        res.append({"o": o, "c": c, "h": max(o, c) * 1.01, "l": min(o, c) * 0.99,
                    "v": v, "vw": (o + c) / 2, "n": int(v / 100), "t": 1700000000000 + i * 86400000})
        price = c
    return {"results": res}


class TestRobustStats(unittest.TestCase):
    def test_robust_z_flags_outlier(self):
        base = [1.0, 1.1, 0.9, 1.05, 0.95, 1.0]
        self.assertGreater(rs.robust_z(5.0, base), 3.0)

    def test_robust_z_constant_then_jump(self):
        base = [2.0] * 10
        self.assertNotEqual(rs.robust_z(9.0, base), 0.0)  # finite, non-zero

    def test_squash_bounded(self):
        self.assertLessEqual(rs.squash(1e6, scale=3, cap=100), 100.0)
        self.assertAlmostEqual(rs.squash(0, scale=3), 0.0)

    def test_hhi_and_gini(self):
        self.assertAlmostEqual(rs.hhi([10, 0, 0]), 1.0)
        self.assertLess(rs.hhi([1, 1, 1, 1]), 0.3)


class TestMarket(unittest.TestCase):
    def test_time_series_double_confirmation(self):
        ts = mkt.time_series_anomaly(_synthetic_daily(jump=True))
        self.assertTrue(ts["available"])
        self.assertTrue(ts["double_confirmed"], "price+volume spike must double-confirm")

    def test_flat_series_no_confirmation(self):
        ts = mkt.time_series_anomaly(_synthetic_daily(jump=False))
        self.assertFalse(ts.get("double_confirmed"))

    def test_cross_sectional(self):
        # Realistic market cross-section: small varied moves + one big outlier.
        import random
        random.seed(7)
        pop = [{"T": f"N{i}", "o": 10.0, "c": 10.0 * (1 + random.uniform(-0.02, 0.02)),
                "v": 1_000_000, "vw": 10} for i in range(200)]
        grouped = {"results": [{"T": "XYZ", "o": 1.0, "c": 3.0, "v": 9_000_000, "vw": 2}] + pop}
        xs = mkt.cross_sectional_anomaly(grouped, "XYZ")
        self.assertTrue(xs["available"])
        self.assertGreater(xs["abs_return_xz"], 3.0)


class TestCoordination(unittest.TestCase):
    def test_near_duplicate_cluster(self):
        posts = [{"id": str(i), "text": "BUY $ABC NOW guaranteed moon rocket join telegram"} for i in range(4)]
        posts.append({"id": "x", "text": "thinking about the quarterly results for the company"})
        feat = coord.coordination_features(posts, dup_threshold=0.6)
        self.assertGreaterEqual(feat["max_duplicate_cluster_size"], 4)
        score, basis = coord.coordination_score(feat)
        self.assertGreater(score, 0)

    def test_no_coordination_when_unique(self):
        posts = [{"id": "1", "text": "apple earnings look solid this quarter"},
                 {"id": "2", "text": "tesla deliveries missed slightly"}]
        feat = coord.coordination_features(posts)
        self.assertEqual(feat["max_duplicate_cluster_size"], 0)


class TestSocial(unittest.TestCase):
    def test_dedup_across_artifacts(self):
        x = {"data": [{"id": "1", "text": "$AAPL news", "public_metrics": {}},
                      {"id": "1", "text": "$AAPL news", "public_metrics": {}}]}
        posts = soc.normalize_posts(x)
        self.assertEqual(len([p for p in posts]), 1)
        self.assertEqual(posts[0]["_duplicates_removed"], 1)

    def test_promo_deflates(self):
        posts = [{"platform": "x", "id": str(i), "text": "$AAPL guaranteed moon rocket telegram free signals", "engagement": 0}
                 for i in range(5)]
        feat = soc.social_features(posts, "AAPL", reddit_unavailable=True)
        scores = soc.social_scores(feat)
        self.assertGreater(scores["social_promotional_noise"], scores["social_issuer_specific_burst"])


class TestComposite(unittest.TestCase):
    def _fetch(self, data, mode="replay"):
        class F:
            def __init__(s): s.name = "t"; s.data = data; s.mode = mode; s.status = 200
            def ok(s): return data is not None
            artifact_path = None; sha256 = None; source_url_redacted = None
        return F()

    def test_routine_context_floor_caps_to_low(self):
        # Only issuer context present, no anomaly -> must be LOW (routine floor).
        fetches = {
            "daily_range": self._fetch(_synthetic_daily(jump=False)),
            "grouped": self._fetch(None), "snapshot": self._fetch(None),
            "trades": self._fetch(None), "quotes": self._fetch(None),
            "x": self._fetch({"data": []}),
            "reddit": self._fetch(None), "reddit_unavailable": True,
            "otc_threshold": self._fetch(None), "reg_sho": self._fetch(None),
            "halts": self._fetch(None),
            "submissions": self._fetch({"name": "X", "filings": {"recent": {"form": ["4", "4"], "filingDate": ["2024-01-01", "2024-02-01"]}}}),
        }
        pkg = scoring_v2.build_package("AAPL", fetches)
        self.assertEqual(pkg["review_priority"], "LOW")
        self.assertTrue(any("routine-context floor" in c for c in pkg["score_caps_applied"]))

    def test_required_fields_and_guardrails(self):
        fetches = {k: self._fetch(None) for k in
                   ("daily_range", "grouped", "snapshot", "trades", "quotes", "x", "reddit",
                    "otc_threshold", "reg_sho", "halts", "submissions")}
        fetches["reddit_unavailable"] = True
        pkg = scoring_v2.build_package("ZZZZ", fetches)
        for field in ("ticker", "algorithm_version", "finding_ceiling", "watch_score",
                      "review_priority", "anomaly_evidence_score", "evidence_quality_score",
                      "component_scores", "score_caps_applied", "benign_explanation_review",
                      "prohibited_actions", "corroboration", "limitations"):
            self.assertIn(field, pkg)
        self.assertEqual(pkg["finding_ceiling"], "WATCH")
        self.assertIn("trading_signal", pkg["prohibited_actions"])

    def test_pump_pattern_can_reach_higher_priority(self):
        # social coordination + market double-confirmation -> >=MEDIUM, multi-family
        posts = {"data": [{"id": str(i), "text": "$ABC guaranteed moon rocket join telegram must buy now",
                           "public_metrics": {"like_count": 5}} for i in range(6)]}
        fetches = {
            "daily_range": self._fetch(_synthetic_daily(jump=True)),
            "grouped": self._fetch({"results": [{"T": "ABC", "o": 1, "c": 1.5, "v": 9_000_000, "vw": 1.2}] +
                                    [{"T": f"N{i}", "o": 10, "c": 10.01, "v": 1_000_000, "vw": 10} for i in range(150)]}),
            "snapshot": self._fetch(None), "trades": self._fetch(None), "quotes": self._fetch(None),
            "x": self._fetch(posts), "reddit": self._fetch(None), "reddit_unavailable": True,
            "otc_threshold": self._fetch(None), "reg_sho": self._fetch(None), "halts": self._fetch(None),
            "submissions": self._fetch(None),
        }
        pkg = scoring_v2.build_package("ABC", fetches)
        self.assertGreaterEqual(pkg["component_scores"]["market_anomaly_score"], 25)
        self.assertGreaterEqual(pkg["corroboration"]["n_families_active"], 2)
        self.assertIn(pkg["review_priority"], ("MEDIUM", "HIGH", "CRITICAL_REVIEW"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
