#!/usr/bin/env python3
"""Tests for LLM usage/cost tracking + agent status."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import usage
import agent_status


class TestUsage(unittest.TestCase):
    def test_cost_math(self):
        # sonnet (3 in / 15 out per 1M): 1M in + 1M out = 3 + 15 = 18
        self.assertAlmostEqual(usage.cost("claude-sonnet-4", 1_000_000, 1_000_000), 18.0, places=4)
        # haiku
        self.assertAlmostEqual(usage.cost("claude-haiku-4.5", 1_000_000, 0), 0.80, places=4)

    def test_price_longest_match(self):
        pin, pout, known = usage.price_for("gpt-4o-mini")
        self.assertEqual((pin, pout, known), (0.15, 0.60, True))

    def test_unknown_pricing(self):
        _, _, known = usage.price_for("some-future-model-x")
        self.assertFalse(known)

    def test_record_and_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "u.jsonl"
            usage.record("claude-haiku-4.5", 1000, 500, component="digest", path=p)
            usage.record("claude-sonnet-4", 2000, 800, component="explain", path=p)
            s = usage.summary(p)
            self.assertEqual(s["n_calls"], 2)
            self.assertGreater(s["total_cost_usd"], 0)
            self.assertIn("claude-haiku-4.5", s["by_model"])
            self.assertIn("digest", s["by_component"])


class TestAgentStatus(unittest.TestCase):
    def test_build_shapes(self):
        queue = {"data_mode": "live", "review_queue": [
            {"ticker": "AMC", "review_priority": "HIGH",
             "source_health": {"polygon_prev_AMC": {"mode": "live", "ok": True},
                               "x_recent_AMC": {"mode": "replay", "ok": True},
                               "reddit_AMC": {"mode": "unavailable", "ok": False}}}]}
        st = agent_status.build(queue)
        self.assertEqual([a["name"] for a in st["agents"]], ["Scout", "Analyst", "Adversary", "Packager"])
        scout = next(a for a in st["agents"] if a["name"] == "Scout")
        self.assertEqual(scout["state"], "live")  # >=1 live integration
        names = {i["integration"] for i in st["integrations"]}
        self.assertIn("polygon_prev_AMC", names)
        self.assertIn("llm", st)
        self.assertIn("model", st)


if __name__ == "__main__":
    unittest.main(verbosity=2)
