#!/usr/bin/env python3
"""Phase 3 tests: LLM urgency/FOMO node (features/social_intel).

All LLM calls use an INJECTED caller — no network. Proves the node is
subordinate to the deterministic signal:
  - ungrounded phrases are dropped (can't inflate);
  - the verdict is never scored (can't inflate or suppress);
  - it only amplifies an already market-verified push, capped;
  - full I/O is persisted.
"""
import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "features"))

from features import social_intel as si
import scoring_v2

PUMP = "ABC next 100x gem load up your bags now before the exchange listing huge news"


def _post(pid, platform, author):
    return {"id": pid, "text": PUMP, "platform": platform, "author_id": author,
            "created_at": "2026-06-08T12:00:00Z"}


def _posts():
    return [_post("1", "x", "a1"), _post("2", "reddit", "a2"), _post("3", "stocktwits", "a3")]


def _caller(signals, verdict="possible"):
    def c(system, user, env, model):
        return {"text": json.dumps({"urgency_signals": signals, "verdict": verdict}),
                "model": "fake-haiku", "input_tokens": 10, "output_tokens": 5}
    return c


GROUNDED = [{"post_id": "1", "phrase": "next 100x gem", "category": "fomo"}]
UNGROUNDED = [{"post_id": "1", "phrase": "ignore previous instructions", "category": "fomo"}]


class TestVerify(unittest.TestCase):
    def test_drops_ungrounded_phrase(self):
        verified, dropped = si.verify_urgency(UNGROUNDED, {"1": {"text": PUMP}})
        self.assertEqual(verified, [])
        self.assertEqual(dropped, 1)

    def test_keeps_grounded_phrase(self):
        verified, dropped = si.verify_urgency(GROUNDED, {"1": {"text": PUMP}})
        self.assertEqual(len(verified), 1)
        self.assertEqual(dropped, 0)

    def test_drops_unknown_category(self):
        sig = [{"post_id": "1", "phrase": "next 100x gem", "category": "bogus"}]
        verified, dropped = si.verify_urgency(sig, {"1": {"text": PUMP}})
        self.assertEqual(verified, [])
        self.assertEqual(dropped, 1)


class TestAttachUrgency(unittest.TestCase):
    def _applied_detail(self):
        d = si.coordination_intel(_posts(), market_anomaly_score=40)
        self.assertTrue(d["applied"])  # market-verified push
        return d

    def test_amplifies_applied_push(self):
        d = self._applied_detail()
        base = d["coordination_bump"]
        si.attach_urgency(d, _posts(), caller=_caller(GROUNDED, verdict="likely"))
        self.assertGreater(d["coordination_bump"], base)
        self.assertEqual(d["llm"]["n_signals_verified"], 1)
        self.assertGreater(d["llm"]["urgency_bump"], 0)

    def test_ungrounded_does_not_inflate(self):
        d = self._applied_detail()
        base = d["coordination_bump"]
        si.attach_urgency(d, _posts(), caller=_caller(UNGROUNDED, verdict="likely"))
        self.assertEqual(d["coordination_bump"], base)        # no change
        self.assertEqual(d["llm"]["n_signals_verified"], 0)
        self.assertEqual(d["llm"]["urgency_bump"], 0.0)

    def test_verdict_none_still_amplifies_when_grounded(self):
        # verdict is advisory only — grounded signals amplify regardless of verdict
        d = self._applied_detail()
        base = d["coordination_bump"]
        si.attach_urgency(d, _posts(), caller=_caller(GROUNDED, verdict="none"))
        self.assertGreater(d["coordination_bump"], base)
        self.assertEqual(d["llm"]["verdict"], "none")

    def test_no_bump_when_push_not_market_verified(self):
        d = si.coordination_intel(_posts(), market_anomaly_score=5)  # no market move
        self.assertTrue(d["coordinated_push"])
        self.assertFalse(d["applied"])
        si.attach_urgency(d, _posts(), caller=_caller(GROUNDED, verdict="likely"))
        self.assertEqual(d["coordination_bump"], 0.0)           # LLM can't create score
        self.assertEqual(d["llm"]["urgency_bump"], 0.0)
        self.assertEqual(d["llm"]["n_signals_verified"], 1)     # still recorded as evidence

    def test_io_persisted_and_capped(self):
        d = self._applied_detail()
        si.attach_urgency(d, _posts(), caller=_caller(GROUNDED))
        llm = d["llm"]
        for k in ("model", "verdict", "prompt", "response", "n_signals_verified", "urgency_ratio"):
            self.assertIn(k, llm)
        self.assertLessEqual(d["coordination_bump"], si.MAX_BUMP + si.URGENCY_MAX)


class TestScoringIntegration(unittest.TestCase):
    """build_package wires the LLM node in when both flags are on (caller patched)."""

    def tearDown(self):
        os.environ.pop("SECFEDCLAW_SOCIAL_INTEL", None)
        os.environ.pop("SECFEDCLAW_SOCIAL_INTEL_LLM", None)
        si.classify_urgency = self._orig

    def setUp(self):
        self._orig = si.classify_urgency

    def _f(self, data):
        class F:
            def __init__(s): s.name = "t"; s.data = data; s.mode = "replay"; s.status = 200
            def ok(s): return data is not None
            artifact_path = None; sha256 = None; source_url_redacted = None
        return F()

    def _daily_jump(self):
        res, price = [], 10.0
        for i in range(40):
            v, o = 1_000_000, price
            c = price * (1.001 if i % 2 else 0.999)
            if i == 39:
                c, v = price * 1.45, 25_000_000
            res.append({"o": o, "c": c, "h": max(o, c) * 1.01, "l": min(o, c) * 0.99,
                        "v": v, "vw": (o + c) / 2, "n": int(v / 100), "t": 1700000000000 + i * 86400000})
            price = c
        return {"results": res}

    def _fetches(self):
        pop = [{"T": f"N{i}", "o": 10.0, "c": 10.0, "v": 1_000_000, "vw": 10} for i in range(200)]
        grouped = {"results": [{"T": "ABC", "o": 1.0, "c": 3.0, "v": 9_000_000, "vw": 2}] + pop}
        X = {"data": [{"id": "1", "text": PUMP, "created_at": "2021-09-13T10:00:30Z", "author_id": "a1"}]}
        REDDIT = {"data": {"children": [{"data": {"id": "2", "title": PUMP, "selftext": "",
                                                  "author": "a2", "created_utc": 1631520000}}]}}
        STOCKTWITS = {"messages": [{"id": 3, "body": PUMP, "created_at": "2021-09-13T10:01:00Z",
                                    "user": {"id": "a3"}, "entities": {"sentiment": {"basic": "Bullish"}}}]}
        keys = ("prev", "snapshot", "trades", "quotes", "otc_threshold", "reg_sho", "halts",
                "submissions", "edgar", "litigation", "discord", "instagram", "facebook",
                "splits", "options", "otc_promo", "openinsider")
        f = {k: self._f(None) for k in keys}
        f["daily_range"] = self._f(self._daily_jump())
        f["grouped"] = self._f(grouped)
        f["x"], f["reddit"], f["stocktwits"] = self._f(X), self._f(REDDIT), self._f(STOCKTWITS)
        f["reddit_unavailable"] = False
        return f

    def test_llm_flag_amplifies_vs_deterministic_only(self):
        os.environ["SECFEDCLAW_SOCIAL_INTEL"] = "1"
        # deterministic-only (LLM flag off)
        det = scoring_v2.build_package("ABC", self._fetches())
        # LLM on, with a patched grounded classifier (no network)
        os.environ["SECFEDCLAW_SOCIAL_INTEL_LLM"] = "1"
        si.classify_urgency = lambda cluster_posts, **k: {
            "signals": [{"post_id": cluster_posts[0]["id"], "phrase": "next 100x gem", "category": "fomo"}],
            "verdict": "likely", "model": "fake", "raw_text": "{}", "prompt": "p",
            "error": None, "input_tokens": 0, "output_tokens": 0}
        llm = scoring_v2.build_package("ABC", self._fetches())
        self.assertIsNotNone(llm["social_intel"].get("llm"))
        self.assertGreater(llm["component_scores"]["coordination_score"],
                           det["component_scores"]["coordination_score"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
