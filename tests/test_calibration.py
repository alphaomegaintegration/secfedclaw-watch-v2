#!/usr/bin/env python3
"""Wave-5 model calibration: Platt scaling fit on out-of-fold scores, honest
advisory surfacing (calibrated flag + n_real_labels)."""
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import model as M


def _toy():
    X = [[v] for v in [0, 0, 0, 1, 1, 2, 3, 4, 4, 5, 5, 5]]
    y = [0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1]
    return X, y


class TestPlatt(unittest.TestCase):
    def test_fit_and_monotonic_bounded(self):
        gbm = M.GradientBoosting(n_estimators=20).fit(*_toy())
        z = np.array([-3.0, -1.0, 0.0, 1.0, 3.0])
        gbm.set_platt_from_scores(z, [0, 0, 0, 1, 1])
        self.assertIsNotNone(gbm.platt)
        a, b = gbm.platt
        self.assertGreater(a, 0)                       # higher score -> higher prob
        probs = 1 / (1 + np.exp(-(a * z + b)))
        self.assertTrue(all(0 <= p <= 1 for p in probs))
        self.assertEqual(list(probs), sorted(probs))   # monotonic in z

    def test_insufficient_data_leaves_uncalibrated(self):
        gbm = M.GradientBoosting(n_estimators=5).fit(*_toy())
        gbm.set_platt_from_scores([1.0, 2.0], [1, 1])  # one class, <4 rows
        self.assertIsNone(gbm.platt)

    def test_predict_proba_applies_platt(self):
        gbm = M.GradientBoosting(n_estimators=20).fit(*_toy())
        raw = gbm.predict_proba([[5.0]])[0]
        gbm.platt = (2.0, 0.0)
        z = gbm.decision_function([[5.0]])[0]
        self.assertAlmostEqual(gbm.predict_proba([[5.0]])[0], 1 / (1 + np.exp(-2.0 * z)), places=6)
        self.assertNotAlmostEqual(gbm.predict_proba([[5.0]])[0], raw, places=6)

    def test_to_from_dict_roundtrips_platt(self):
        gbm = M.GradientBoosting(n_estimators=10).fit(*_toy())
        gbm.platt = (1.5, -0.3)
        gbm2 = M.GradientBoosting.from_dict(gbm.to_dict())
        self.assertEqual(gbm2.platt, (1.5, -0.3))

    def test_oof_decision_shape(self):
        X, y = _toy()
        oof, got = M.kfold_oof_decision(X, y, k=4)
        self.assertEqual(len(oof), len(y))
        self.assertTrue(got.any())


class TestAdvisoryHonesty(unittest.TestCase):
    def test_surfaces_calibration_and_real_labels(self):
        gbm = M.GradientBoosting(n_estimators=10).fit(*_toy())
        gbm.platt = (2.0, 0.1)
        md = {**gbm.to_dict(), "n_real_labels": 28, "model_version": "gbm_v1"}
        adv = M.score_package({"component_scores": {}, "security_class": {}, "corroboration": {}}, md)
        self.assertTrue(adv["calibrated"])
        self.assertEqual(adv["n_real_labels"], 28)
        self.assertIn("Platt-calibrated", adv["note"])

    def test_uncalibrated_is_honest(self):
        gbm = M.GradientBoosting(n_estimators=10).fit(*_toy())  # no platt
        md = {**gbm.to_dict(), "n_real_labels": 5}
        adv = M.score_package({"component_scores": {}, "security_class": {}, "corroboration": {}}, md)
        self.assertFalse(adv["calibrated"])
        self.assertIn("uncalibrated", adv["note"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
