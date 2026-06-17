#!/usr/bin/env python3
"""Phase 4 guard: the dashboard surfaces social_intel evidence in package cards.

Render-only. social_intel is null unless the Phase 2/3 flags ran, so the block
appears only when present. Verdict is shown as advisory (it is never scored).
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import dashboard_v2


def _pkg(social_intel):
    return {
        "ticker": "ABC", "review_priority": "MEDIUM", "watch_score": 40,
        "anomaly_evidence_score": 30, "evidence_quality_score": 50,
        "security_class": {"class": "small_cap"}, "data_mode": "live",
        "component_scores": {"coordination_score": 42, "market_anomaly_score": 30},
        "corroboration": {"families_active": ["coordination", "market"], "corroboration_multiplier": 1.2},
        "score_caps_applied": [], "adversarial_review": {"caveats": []},
        "coordination_detail": {"near_duplicate_clusters": []},
        "non_accusatory_rationale": "context only",
        "social_intel": social_intel,
    }


APPLIED = {
    "enabled": True, "coordinated_push": True, "market_verified": True, "applied": True,
    "n_cross_platform_clusters": 1, "max_unique_authors": 3, "coordination_bump": 9.0,
    "cross_platform_clusters": [{"platforms": ["x", "reddit", "stocktwits"],
                                 "n_unique_authors": 3, "n_posts": 3, "post_ids": ["1", "2", "3"]}],
    "llm": {"model": "fake-haiku", "verdict": "likely", "n_signals_verified": 2, "n_dropped": 1,
            "urgency_ratio": 0.67, "urgency_bump": 4.0,
            "verified_signals": [{"post_id": "1", "phrase": "next 100x gem", "category": "fomo"}]},
}


class TestDashboardSocialIntel(unittest.TestCase):
    def test_applied_card_surfaces_clusters_and_llm(self):
        html = dashboard_v2.package_cards([_pkg(APPLIED)])
        self.assertIn("Social-intel", html)
        self.assertIn("coordinated push", html)
        self.assertIn("market-verified", html)
        self.assertIn("reddit", html)            # platform spread shown
        self.assertIn("LLM urgency (advisory)", html)   # verdict explicitly labelled advisory
        self.assertIn("likely", html)
        self.assertIn("next 100x gem", html)     # verified phrase cited

    def test_null_social_intel_renders_no_block(self):
        html = dashboard_v2.package_cards([_pkg(None)])
        self.assertNotIn("Social-intel", html)

    def test_push_without_market_shows_no_bump(self):
        si = dict(APPLIED, market_verified=False, applied=False, coordination_bump=0.0, llm=None)
        html = dashboard_v2.package_cards([_pkg(si)])
        self.assertIn("Social-intel", html)
        self.assertIn("no market confirm", html)
        self.assertNotIn("LLM urgency (advisory)", html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
