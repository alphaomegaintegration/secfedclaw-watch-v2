#!/usr/bin/env python3
"""Cross-run entity resolution (entities.py) + the content_fingerprint primitive."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import entities
from features.coordination import content_fingerprint


def _pkg(ticker, run, *, domains=(), fp=None, authors=(), cik=None):
    cd = {"near_duplicate_clusters": [], "shared_domain_groups": [
        {"domain": d, "count": 3, "post_ids": ["a", "b"]} for d in domains]}
    if fp is not None:
        cd["near_duplicate_clusters"].append(
            {"size": 3, "post_ids": ["1", "2"], "sample_text": "buy now moon",
             "author_ids": list(authors), "content_fingerprint": fp})
    p = {"ticker": ticker, "generated_utc": run, "coordination_detail": cd}
    if cik:
        p["issuer_cik"] = cik
    return p


class TestContentFingerprint(unittest.TestCase):
    def test_same_script_same_fingerprint(self):
        a = content_fingerprint("Guaranteed 100x moon rocket, buy now, join telegram!")
        b = content_fingerprint("guaranteed 100x MOON rocket buy now join telegram")
        self.assertTrue(a)
        self.assertEqual(a, b)              # normalization collapses case/punct
        self.assertNotEqual(a, content_fingerprint("quarterly earnings beat expectations"))

    def test_empty_text_empty(self):
        self.assertEqual(content_fingerprint(""), "")
        self.assertEqual(content_fingerprint("   "), "")


class TestObserve(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.path = Path(self._td.name) / "obs.jsonl"

    def tearDown(self):
        self._td.cleanup()

    def test_extract_and_idempotent(self):
        pkgs = [_pkg("AAA", "r1", domains=["promo.biz"], fp="fp123", authors=["u1"], cik="0001"),
                _pkg("BBB", "r1", domains=["promo.biz"], fp="fp123", authors=["u1"])]
        n1 = entities.observe(pkgs, path=self.path)
        n2 = entities.observe(pkgs, path=self.path)   # re-observe
        self.assertGreater(n1, 0)
        self.assertEqual(n2, 0)                        # idempotent

    def test_recurring_across_tickers(self):
        entities.observe([
            _pkg("AAA", "r1", domains=["promo.biz"], fp="fp1"),
            _pkg("BBB", "r1", domains=["promo.biz"], fp="fp1"),
            _pkg("CCC", "r2", domains=["promo.biz"]),
        ], path=self.path)
        rec = entities.recurring(min_tickers=2, path=self.path)
        dom = [r for r in rec if r["type"] == "domain" and r["key"] == "promo.biz"]
        self.assertEqual(len(dom), 1)
        self.assertEqual(dom[0]["n_tickers"], 3)
        self.assertEqual(dom[0]["tickers"], ["AAA", "BBB", "CCC"])
        # the content-cluster script recurred on AAA+BBB
        clus = [r for r in rec if r["type"] == "content_cluster"]
        self.assertEqual(clus[0]["n_tickers"], 2)

    def test_generic_domains_excluded(self):
        entities.observe([
            _pkg("AAA", "r1", domains=["x.com", "t.co", "promo.biz"]),
            _pkg("BBB", "r1", domains=["x.com", "promo.biz"]),
        ], path=self.path)
        keys = {r["key"] for r in entities.recurring(min_tickers=2, path=self.path)}
        self.assertIn("promo.biz", keys)
        self.assertNotIn("x.com", keys)     # generic infra filtered out
        self.assertNotIn("t.co", keys)

    def test_recurrence_for_package_excludes_self(self):
        entities.observe([
            _pkg("AAA", "r1", domains=["promo.biz"]),
            _pkg("BBB", "r1", domains=["promo.biz"]),
        ], path=self.path)
        rec = entities.recurrence_for_package(_pkg("AAA", "r1", domains=["promo.biz"]), path=self.path)
        self.assertEqual(len(rec), 1)
        self.assertEqual(rec[0]["also_seen_on"], ["BBB"])   # not AAA itself

    def test_summary_counts(self):
        entities.observe([_pkg("AAA", "r1", domains=["promo.biz"], cik="0009")], path=self.path)
        s = entities.summary(path=self.path)
        self.assertEqual(s["by_type"]["domain"], 1)
        self.assertEqual(s["by_type"]["issuer"], 1)
        self.assertEqual(s["n_entities"], 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
