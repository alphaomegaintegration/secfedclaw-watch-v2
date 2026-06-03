#!/usr/bin/env python3
"""Tests for the gradient-boosted model + calibration ledger."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import model as M
import ledger as L


class TestGBM(unittest.TestCase):
    def test_learns_separable(self):
        rng = np.random.default_rng(0)
        n = 200
        X = rng.normal(size=(n, len(M.FEATURE_NAMES)))
        # signal: first feature drives the label
        y = (X[:, 0] + 0.3 * rng.normal(size=n) > 0).astype(int)
        m = M.GradientBoosting(n_estimators=40).fit(X, y)
        a = M.auc(y, m.predict_proba(X))
        self.assertGreater(a, 0.85)
        self.assertEqual(int(np.argmax(m.importances)), 0)  # feature 0 most important

    def test_serialize_roundtrip(self):
        rng = np.random.default_rng(1)
        X = rng.normal(size=(60, len(M.FEATURE_NAMES))); y = (X[:, 1] > 0).astype(int)
        m = M.GradientBoosting(n_estimators=20).fit(X, y)
        d = m.to_dict()
        m2 = M.GradientBoosting.from_dict(d)
        self.assertTrue(np.allclose(m.predict_proba(X), m2.predict_proba(X)))

    def test_auc_bounds(self):
        self.assertAlmostEqual(M.auc([1, 1], [0.9, 0.8]), 0.5)  # one-class -> 0.5

    def test_feature_vector_shape(self):
        pkg = {"component_scores": {"market_anomaly_score": 50, "coordination_score": 10,
               "issuer_context_score": 60, "issuer_event_score": 0, "market_structure_score": 0,
               "halt_regulatory_score": 0, "social_issuer_specific_burst": 5,
               "social_promotional_noise": 2},
               "social_metrics": {"n_platforms": 2, "sentiment": {"bullish_ratio": 0.8}},
               "anomaly_evidence_score": 30, "evidence_quality_score": 70,
               "corroboration": {"n_families_active": 2}, "security_class": {"class": "small_cap"}}
        fv = M.feature_vector(pkg)
        self.assertEqual(len(fv), len(M.FEATURE_NAMES))


class TestLedger(unittest.TestCase):
    def test_add_and_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "labels.jsonl"
            pkg = {"ticker": "ABC", "review_priority": "MEDIUM",
                   "component_scores": {"market_anomaly_score": 80},
                   "social_metrics": {}, "anomaly_evidence_score": 40,
                   "evidence_quality_score": 60, "corroboration": {"n_families_active": 2},
                   "security_class": {"class": "thin_microcap"}}
            L.add_label(pkg, "useful_watch", path=p)
            L.add_label(pkg, "false_positive", path=p)
            rows = L.load_labels(p)
            self.assertEqual(len(rows), 2)
            X, y = L.to_xy(rows)
            self.assertEqual(y, [1, 0])
            self.assertEqual(len(X[0]), len(M.FEATURE_NAMES))

    def test_invalid_label(self):
        with self.assertRaises(ValueError):
            L.add_label({"ticker": "X"}, "guilty")


if __name__ == "__main__":
    unittest.main(verbosity=2)
