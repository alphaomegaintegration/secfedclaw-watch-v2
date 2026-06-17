#!/usr/bin/env python3
"""Phase 2 integration: social_intel wired into scoring_v2 (gated + quarantined).

Proves:
  - OFF by default → package.social_intel is null (no behavior change);
  - ON + cross-platform coordinated push + real market move → coordination_score
    gets a capped, cited bump;
  - G3 quarantine → with NO market move, turning the flag ON does NOT raise
    coordination_score or the review priority (social-only can't escalate).
"""
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "features"))

import scoring_v2

PUMP = "ABC guaranteed moon rocket squeeze buy now 100x before the exchange listing huge"

X = {"data": [{"id": "x1", "text": PUMP, "created_at": "2021-09-13T10:00:30Z",
               "author_id": "a1", "public_metrics": {"like_count": 2}}]}
REDDIT = {"data": {"children": [{"data": {"id": "r1", "title": PUMP, "selftext": "",
                                          "author": "a2", "created_utc": 1631520000,
                                          "score": 12, "num_comments": 4}}]}}
STOCKTWITS = {"messages": [{"id": 1, "body": PUMP, "created_at": "2021-09-13T10:01:00Z",
                            "user": {"id": "a3"}, "entities": {"sentiment": {"basic": "Bullish"}}}]}

# Flat market vs a price+volume spike on the last day.
def _daily(jump):
    res, price = [], 10.0
    for i in range(40):
        v, o = 1_000_000, price
        c = price * (1.001 if i % 2 else 0.999)
        if jump and i == 39:
            c, v = price * 1.45, 25_000_000
        res.append({"o": o, "c": c, "h": max(o, c) * 1.01, "l": min(o, c) * 0.99,
                    "v": v, "vw": (o + c) / 2, "n": int(v / 100), "t": 1700000000000 + i * 86400000})
        price = c
    return {"results": res}

_POP = [{"T": f"N{i}", "o": 10.0, "c": 10.0, "v": 1_000_000, "vw": 10} for i in range(200)]
GROUPED_OUTLIER = {"results": [{"T": "ABC", "o": 1.0, "c": 3.0, "v": 9_000_000, "vw": 2}] + _POP}


def _f(data):
    class F:
        def __init__(s): s.name = "t"; s.data = data; s.mode = "replay"; s.status = 200
        def ok(s): return data is not None
        artifact_path = None; sha256 = None; source_url_redacted = None
    return F()


def _fetches(jump):
    keys = ("daily_range", "grouped", "prev", "snapshot", "trades", "quotes",
            "otc_threshold", "reg_sho", "halts", "submissions", "edgar",
            "litigation", "discord", "instagram", "facebook", "splits",
            "options", "otc_promo", "openinsider")
    f = {k: _f(None) for k in keys}
    f["daily_range"] = _f(_daily(jump))
    f["grouped"] = _f(GROUPED_OUTLIER if jump else None)
    f["x"], f["reddit"], f["stocktwits"] = _f(X), _f(REDDIT), _f(STOCKTWITS)
    f["reddit_unavailable"] = False
    return f


class TestSocialIntelScoring(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("SECFEDCLAW_SOCIAL_INTEL", None)

    def _pkg(self, jump, flag):
        if flag:
            os.environ["SECFEDCLAW_SOCIAL_INTEL"] = "1"
        else:
            os.environ.pop("SECFEDCLAW_SOCIAL_INTEL", None)
        return scoring_v2.build_package("ABC", _fetches(jump))

    def test_off_by_default_is_null(self):
        pkg = self._pkg(jump=True, flag=False)
        self.assertIsNone(pkg["social_intel"])

    def test_on_with_market_move_boosts_coordination(self):
        off = self._pkg(jump=True, flag=False)
        on = self._pkg(jump=True, flag=True)
        si = on["social_intel"]
        self.assertIsNotNone(si)
        self.assertTrue(si["coordinated_push"])
        self.assertTrue(si["market_verified"])
        self.assertTrue(si["applied"])
        self.assertGreater(on["component_scores"]["coordination_score"],
                           off["component_scores"]["coordination_score"])
        self.assertTrue(any("cross-platform coordinated push" in b
                            for b in on["coordination_detail"]["basis"]))

    def test_quarantine_no_market_no_escalation(self):
        # G3: with no market move, enabling the flag must NOT raise the score or priority.
        off = self._pkg(jump=False, flag=False)
        on = self._pkg(jump=False, flag=True)
        self.assertTrue(on["social_intel"]["coordinated_push"])     # push detected...
        self.assertFalse(on["social_intel"]["market_verified"])     # ...but no market move
        self.assertFalse(on["social_intel"]["applied"])             # so no bump
        self.assertEqual(on["component_scores"]["coordination_score"],
                         off["component_scores"]["coordination_score"])
        self.assertEqual(on["review_priority"], off["review_priority"])
        self.assertNotIn(on["review_priority"], ("HIGH", "CRITICAL_REVIEW"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
