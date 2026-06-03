#!/usr/bin/env python3
"""Tests for the LLM-backed explanation agent (with guardrails + fallback)."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import explainer
import usage

PKG = {
    "ticker": "ABCD", "review_priority": "HIGH", "watch_score": 58.0,
    "anomaly_evidence_score": 61.0, "evidence_quality_score": 64.0,
    "security_class": {"class": "thin_microcap"},
    "corroboration": {"families_active": ["market", "coordination", "issuer_event"]},
    "component_scores": {"market_anomaly_score": 80, "coordination_score": 70, "issuer_event_score": 40,
                         "social_promotional_noise": 30, "social_issuer_specific_burst": 8},
    "score_caps_applied": [],
    "benign_explanation_review": {"indicators": ["Check for a legitimate catalyst (earnings, contract)."]},
    "enforcement_history": {"matched_releases": [{"title": "SEC charges ABCD"}]},
    "evidence_gaps": ["reddit social platform unavailable"],
    "data_mode": "replay",
}


class TestTemplate(unittest.TestCase):
    def test_template_is_grounded_and_safe(self):
        txt = explainer.template_explain(PKG)
        self.assertIn("ABCD", txt)
        self.assertIn("HIGH", txt)
        self.assertIn(explainer.DISCLAIMER, txt)
        self.assertTrue(explainer._passes_guardrail(txt))

    def test_prefer_llm_false_uses_template(self):
        res = explainer.explain(PKG, env={}, prefer_llm=False)
        self.assertEqual(res["source"], "template")


class TestGuardrail(unittest.TestCase):
    def test_rejects_forbidden_output(self):
        bad = lambda s, u, e, m: {"text": "This is clear fraud, buy now — guaranteed returns.",
                                  "model": "x/haiku", "input_tokens": 10, "output_tokens": 20}
        res = explainer.explain(PKG, env={"OPENROUTER_API_KEY": "k"}, prefer_llm=True, caller=bad)
        self.assertEqual(res["source"], "template")  # forbidden -> fell back
        self.assertTrue(explainer._passes_guardrail(res["text"]))

    def test_forbidden_patterns(self):
        self.assertFalse(explainer._passes_guardrail("the issuer committed fraud"))
        self.assertFalse(explainer._passes_guardrail("you should buy the stock now"))
        self.assertTrue(explainer._passes_guardrail(
            "ABCD shows elevated coordinated social activity and a confirmed volume move; review for context. " + explainer.DISCLAIMER))


class TestLLMPathRecordsUsage(unittest.TestCase):
    def test_clean_llm_output_records_cost(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "u.jsonl"
            usage.LEDGER = ledger  # redirect usage ledger
            good = lambda s, u, e, m: {
                "text": "ABCD is flagged HIGH for review: a confirmed price+volume move coincides with a "
                        "coordinated promotional cluster and recent issuer filings. Verify benign catalysts first.",
                "model": "anthropic/claude-3.5-haiku", "input_tokens": 800, "output_tokens": 120}
            res = explainer.explain(PKG, env={"OPENROUTER_API_KEY": "k"}, prefer_llm=True, caller=good)
            self.assertEqual(res["source"], "llm")
            self.assertIn(explainer.DISCLAIMER, res["text"])
            rows = usage.load(ledger)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["component"], "explainer")
            self.assertGreater(rows[0]["cost_usd"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
