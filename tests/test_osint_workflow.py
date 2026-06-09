#!/usr/bin/env python3
"""Tests for osint_workflow: X search builder and case brief generation."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from osint_workflow import build_x_searches, build_case_brief

FAKE_PACKAGE = {
    "ticker": "PUMP",
    "review_priority": "HIGH",
    "watch_score": 68.0,
    "anomaly_evidence_score": 62.0,
    "evidence_quality_score": 80.0,
    "generated_utc": "2026-06-09T14:00:00Z",
    "issuer_name": "PumpCo Inc.",
    "data_mode": "mixed_live_replay",
    "corroboration": {"families_active": ["market", "social"], "corroboration_multiplier": 1.5},
    "component_scores": {
        "market_anomaly_score": 72.0,
        "coordination_score": 55.0,
        "issuer_event_score": 30.0,
        "enforcement_history_score": 0.0,
        "market_structure_score": 10.0,
        "halt_regulatory_score": 0.0,
        "options_flow_score": 0.0,
        "issuer_context_score": 20.0,
        "social_issuer_specific_burst": 45.0,
        "social_promotional_noise": 60.0,
    },
    "coordination_detail": {
        "near_duplicate_clusters": [[{"text": "buy PUMP now free signals guaranteed moon"}]],
        "shared_domain_groups": [{"pumpalerts.com": 3}],
    },
    "enforcement_history": {"matched_releases": []},
    "edgar_issuer_event": {"basis": []},
    "score_caps_applied": [],
    "non_accusatory_rationale": "Market anomaly + social coordination detected. Human review recommended.",
}


class TestBuildXSearches(unittest.TestCase):

    def test_returns_at_least_3_searches(self):
        searches = build_x_searches(FAKE_PACKAGE)
        self.assertGreaterEqual(len(searches), 3)

    def test_cashtag_present_in_all_queries(self):
        searches = build_x_searches(FAKE_PACKAGE)
        for s in searches:
            self.assertIn("PUMP", s["query"].upper())

    def test_urls_are_valid_x_search_urls(self):
        searches = build_x_searches(FAKE_PACKAGE)
        for s in searches:
            self.assertIn("x.com/search", s["url"])

    def test_date_range_in_first_query(self):
        searches = build_x_searches(FAKE_PACKAGE)
        first = searches[0]["query"]
        self.assertIn("since:", first)
        self.assertIn("until:", first)

    def test_cluster_phrase_search_generated(self):
        searches = build_x_searches(FAKE_PACKAGE)
        labels = [s["label"] for s in searches]
        self.assertTrue(any("cluster" in l for l in labels))

    def test_shared_domain_search_generated(self):
        searches = build_x_searches(FAKE_PACKAGE)
        labels = [s["label"] for s in searches]
        self.assertTrue(any("domain" in l or "pumpalerts" in l.lower() for l in labels))

    def test_empty_ticker_returns_empty(self):
        pkg = {**FAKE_PACKAGE, "ticker": ""}
        self.assertEqual(build_x_searches(pkg), [])


class TestBuildCaseBrief(unittest.TestCase):

    def test_contains_ticker(self):
        brief = build_case_brief(FAKE_PACKAGE)
        self.assertIn("PUMP", brief)

    def test_contains_priority(self):
        brief = build_case_brief(FAKE_PACKAGE)
        self.assertIn("HIGH", brief)

    def test_contains_watch_score(self):
        brief = build_case_brief(FAKE_PACKAGE)
        self.assertIn("68", brief)

    def test_contains_x_search_links(self):
        brief = build_case_brief(FAKE_PACKAGE)
        self.assertIn("x.com/search", brief)

    def test_contains_watch_ceiling_disclaimer(self):
        brief = build_case_brief(FAKE_PACKAGE)
        self.assertIn("WATCH", brief)
        self.assertIn("Not proof of misconduct", brief)

    def test_is_string(self):
        brief = build_case_brief(FAKE_PACKAGE)
        self.assertIsInstance(brief, str)
        self.assertGreater(len(brief), 200)


if __name__ == "__main__":
    unittest.main(verbosity=2)
