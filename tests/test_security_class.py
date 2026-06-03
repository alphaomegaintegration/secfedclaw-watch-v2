#!/usr/bin/env python3
"""Tests for per-security-class calibrated thresholds."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "features"))

from features import security_class as sc
import scoring_v2


class TestClassify(unittest.TestCase):
    def test_classes(self):
        self.assertEqual(sc.classify(0.5, 200_000), "thin_microcap")     # penny
        self.assertEqual(sc.classify(12, 2_000_000), "thin_microcap")    # thin turnover
        self.assertEqual(sc.classify(20, 20_000_000), "small_cap")
        self.assertEqual(sc.classify(50, 200_000_000), "mid_cap")
        self.assertEqual(sc.classify(200, 5_000_000_000), "large_cap")
        self.assertEqual(sc.classify(None, None), "unknown")

    def test_params_ordering(self):
        # liquid names need higher z + higher floor; microcaps more social weight
        self.assertLess(sc.params("thin_microcap")["z_confirm"], sc.params("large_cap")["z_confirm"])
        self.assertLess(sc.params("thin_microcap")["floor"], sc.params("large_cap")["floor"])
        self.assertGreater(sc.params("thin_microcap")["social_weight"], sc.params("large_cap")["social_weight"])


def _daily(n, base, dvol_close, vol, jump=False):
    res = []
    price = base
    for i in range(n):
        o = price; c = price * (1.001 if i % 2 else 0.999); v = vol
        if jump and i == n - 1:
            c = price * 1.5; v = vol * 20
        res.append({"o": o, "c": c, "h": max(o, c) * 1.01, "l": min(o, c) * 0.99,
                    "v": v, "vw": (o + c) / 2, "n": int(v / 90), "t": 1700000000000 + i * 86400000})
        price = c
    return {"results": res}


class TestClassAwareScoring(unittest.TestCase):
    def _f(self, data):
        class F:
            def __init__(s): s.name = "t"; s.data = data; s.mode = "replay"; s.status = 200
            def ok(s): return data is not None
            artifact_path = None; sha256 = None; source_url_redacted = None
        return F()

    def _pkg(self, daily):
        fetches = {k: self._f(None) for k in
                   ("grouped", "snapshot", "trades", "quotes", "x", "reddit", "stocktwits",
                    "otc_threshold", "reg_sho", "halts", "submissions", "edgar")}
        fetches["daily_range"] = self._f(daily)
        fetches["reddit_unavailable"] = True
        return scoring_v2.build_package("T", fetches)

    def test_large_cap_classified_and_high_floor(self):
        # $300 name, ~1.5B daily dollar-volume, flat -> large cap, high floor, LOW
        pkg = self._pkg(_daily(40, 300.0, None, 5_000_000))
        self.assertEqual(pkg["security_class"]["class"], "large_cap")
        self.assertEqual(pkg["security_class"]["routine_context_floor"], 33.0)
        self.assertEqual(pkg["review_priority"], "LOW")

    def test_microcap_lower_z_confirm(self):
        pkg = self._pkg(_daily(40, 0.5, None, 2_000_000, jump=True))
        self.assertEqual(pkg["security_class"]["class"], "thin_microcap")
        self.assertEqual(pkg["security_class"]["z_confirm"], 2.5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
