#!/usr/bin/env python3
"""Phase 2 unit tests: features/social_intel.coordination_intel (deterministic).

Cross-platform coordinated-push detection over normalized posts, gated by a real
market move. No LLM. The signal feeds only coordination_score (G3 quarantine).
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from features import social_intel as si

PUMP = "buy ABC now next 100x gem load up your bags before the exchange listing huge news"


def _post(pid, text, platform, author, ts="2026-06-08T12:00:00Z"):
    return {"id": pid, "text": text, "platform": platform, "author_id": author, "created_at": ts}


class TestCoordinationIntel(unittest.TestCase):
    def test_cross_platform_push_detected_and_applied(self):
        posts = [
            _post("1", PUMP, "x", "a1"),
            _post("2", PUMP, "reddit", "a2"),
            _post("3", PUMP, "stocktwits", "a3"),
        ]
        out = si.coordination_intel(posts, market_anomaly_score=40)
        self.assertGreaterEqual(out["n_cross_platform_clusters"], 1)
        self.assertGreaterEqual(out["max_unique_authors"], 3)
        self.assertTrue(out["coordinated_push"])
        self.assertTrue(out["market_verified"])
        self.assertTrue(out["applied"])
        self.assertGreater(out["coordination_bump"], 0)
        self.assertTrue(out["evidence"])  # cites post ids

    def test_single_platform_is_not_cross_platform(self):
        posts = [_post(str(i), PUMP, "x", f"a{i}") for i in range(4)]
        out = si.coordination_intel(posts, market_anomaly_score=40)
        self.assertEqual(out["n_cross_platform_clusters"], 0)
        self.assertFalse(out["coordinated_push"])
        self.assertFalse(out["applied"])

    def test_market_gate_blocks_bump(self):
        posts = [
            _post("1", PUMP, "x", "a1"),
            _post("2", PUMP, "reddit", "a2"),
            _post("3", PUMP, "stocktwits", "a3"),
        ]
        out = si.coordination_intel(posts, market_anomaly_score=5)  # no real move
        self.assertTrue(out["coordinated_push"])
        self.assertFalse(out["market_verified"])
        self.assertFalse(out["applied"])
        self.assertEqual(out["coordination_bump"], 0.0)

    def test_unique_author_threshold_not_met(self):
        # cross-platform near-dup but only 2 distinct accounts
        posts = [
            _post("1", PUMP, "x", "a1"),
            _post("2", PUMP, "reddit", "a1"),
            _post("3", PUMP, "stocktwits", "a2"),
        ]
        out = si.coordination_intel(posts, market_anomaly_score=40)
        self.assertFalse(out["coordinated_push"])
        self.assertFalse(out["applied"])

    def test_bump_is_capped(self):
        posts = [_post(str(i), PUMP, p, f"a{i}")
                 for i, p in enumerate(["x", "reddit", "stocktwits", "discord",
                                        "x", "reddit", "stocktwits", "discord"])]
        out = si.coordination_intel(posts, market_anomaly_score=80)
        self.assertTrue(out["applied"])
        self.assertLessEqual(out["coordination_bump"], si.MAX_BUMP)

    def test_empty_posts_safe(self):
        out = si.coordination_intel([], market_anomaly_score=40)
        self.assertFalse(out["coordinated_push"])
        self.assertEqual(out["coordination_bump"], 0.0)
        self.assertEqual(out["evidence"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
