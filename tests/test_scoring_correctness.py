#!/usr/bin/env python3
"""Wave 3 scoring-correctness fixes: issuer-specific wiring, issuer recency gate,
monotonic market map, and the de-circularized backtest vocabulary."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from features.social import social_features, PROMO_TERMS
from features.official import official_context, official_scores


class TestIssuerSpecificWired(unittest.TestCase):
    """Off-ticker / irrelevant chatter must NOT count as issuer-specific (it fed
    the corroboration gate). _is_issuer_specific is now actually applied."""
    def test_only_this_issuer_counts(self):
        posts = [
            {"platform": "x", "id": "1", "text": "$ACME strong quarterly numbers"},   # this issuer
            {"platform": "x", "id": "2", "text": "$OTHR had a decent day"},           # other ticker
            {"platform": "reddit", "id": "3", "text": "general market musings today"}, # no ticker
        ]
        feat = social_features(posts, "ACME", reddit_unavailable=False)
        self.assertEqual(feat["n_issuer_specific"], 1)         # only $ACME
        self.assertEqual(feat["n_promotional_noise"], 0)
        self.assertFalse(feat["cross_platform_issuer_specific"])  # not 2+ platforms of THIS issuer


class TestIssuerRecencyGate(unittest.TestCase):
    """A year-old filing must not light the issuer-event family; only <=90d does."""
    def _subs(self, forms, dates):
        return {"name": "ACME", "filings": {"recent": {"form": forms, "filingDate": dates}}}

    def test_old_filings_excluded(self):
        today = datetime.now(timezone.utc).date().isoformat()
        old = (datetime.now(timezone.utc) - timedelta(days=400)).date().isoformat()
        # old S-3 + old 8-K would add 14 pts; only the recent Form 4 (6 pts) should count
        ctx = official_context("ACME", None, None, None,
                               self._subs(["S-3", "8-K", "4"], [old, old, today]))
        flagged = ctx["families"].get("sec_recent_forms", [])
        self.assertEqual(len(flagged), 1)
        self.assertEqual(flagged[0]["form"], "4")
        self.assertEqual(official_scores(ctx)["issuer_context_score"], 6.0)  # not 20

    def test_recent_filings_still_light_family(self):
        today = datetime.now(timezone.utc).date().isoformat()
        ctx = official_context("ACME", None, None, None, self._subs(["S-3", "4"], [today, today]))
        self.assertGreater(official_scores(ctx)["issuer_context_score"], 0)


class TestMarketMonotonic(unittest.TestCase):
    """An extreme (raw>100) market state must clamp to 100, not fold back below
    a weaker state (the old squash mapped raw 100.1 -> ~84)."""
    def test_extreme_state_caps_at_100_and_is_monotonic(self):
        from features.market import market_anomaly_score
        micro = {"available": True, "large_trade_share": 0.5, "median_spread_bps": 200}
        strong, _ = market_anomaly_score(
            {"available": True, "price_z": 20.0, "volume_z": 20.0},
            {"available": True, "abs_return_xz": 20.0, "log_volume_xz": 20.0}, micro, z_confirm=2.5)
        weak, _ = market_anomaly_score(
            {"available": True, "price_z": 3.0, "volume_z": 3.0},
            {"available": False}, {"available": False}, z_confirm=2.5)
        self.assertEqual(strong, 100.0)      # raw>100 clamps to 100 (not folded down)
        self.assertLessEqual(weak, strong)   # monotonic: weaker never scores higher


class TestBacktestDecircularized(unittest.TestCase):
    """Synthetic pump text must share no token with the detector's PROMO_TERMS,
    so the backtest measures structural detection, not lexicon memorization."""
    def test_independent_vocabulary(self):
        import backtest
        text = (backtest._INDEP_PROMO_BASE + " " + " ".join(backtest._INDEP_PROMO_TAIL)).lower()
        for term in PROMO_TERMS:
            self.assertNotIn(term, text, f"backtest promo text leaks detector term {term!r}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
