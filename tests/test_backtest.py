#!/usr/bin/env python3
"""Unit tests for the backtest / calibration harness.

Uses a small deterministic synthetic fixture (no real out/ data, no network).
Exercises backtest.run() and backtest.per_class_breakdown() directly.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import backtest


class TestBacktestRunStructure(unittest.TestCase):
    """backtest.run() with a tiny corpus (3/class = 9 total) returns the
    expected top-level keys and plausible metrics."""

    def setUp(self):
        # 3 windows per class, deterministic seed.  Small enough to be fast.
        self.result = backtest.run(n_per_class=3, seed=42, threshold="MEDIUM")

    def test_top_level_keys_present(self):
        for key in ("precision", "recall", "f1", "per_class",
                    "confusion_matrix", "metrics", "n_samples",
                    "algorithm_version", "finding_ceiling", "harness"):
            # 'precision', 'recall', 'f1' live inside 'metrics'
            if key in ("precision", "recall", "f1"):
                self.assertIn(key, self.result["metrics"], f"metrics.{key} missing")
            else:
                self.assertIn(key, self.result, f"top-level key '{key}' missing")

    def test_per_class_subkeys(self):
        per_class = self.result["per_class"]
        self.assertIsInstance(per_class, dict, "per_class must be a dict keyed by class name")
        for cls, stats in per_class.items():
            for k in ("precision", "recall", "f1"):
                self.assertIn(k, stats, f"per_class[{cls}] missing '{k}'")

    def test_sample_count(self):
        # 3 labels × 3 windows = 9 total
        self.assertEqual(self.result["n_samples"], 9)

    def test_confusion_matrix_sums_to_n(self):
        cm = self.result["confusion_matrix"]
        total = cm["tp"] + cm["fp"] + cm["tn"] + cm["fn"]
        self.assertEqual(total, self.result["n_samples"])

    def test_metrics_in_range(self):
        m = self.result["metrics"]
        for k in ("precision", "recall", "f1", "accuracy"):
            self.assertGreaterEqual(m[k], 0.0, f"{k} below 0")
            self.assertLessEqual(m[k], 1.0, f"{k} above 1")

    def test_finding_ceiling_is_watch(self):
        self.assertEqual(self.result["finding_ceiling"], "WATCH")


class TestBacktestPumpFixture(unittest.TestCase):
    """A larger synthetic run (10/class) with clear pump signals should produce
    non-zero precision and recall — the scorer is not broken."""

    def setUp(self):
        # 10 per class, seed chosen to get a mix of hits/misses.
        self.result = backtest.run(n_per_class=10, seed=20260602, threshold="MEDIUM")

    def test_precision_positive(self):
        # At least some pumps should be flagged → precision > 0
        self.assertGreater(self.result["metrics"]["precision"], 0.0,
                           "precision is 0 — scorer flags no pumps at all")

    def test_recall_positive(self):
        # At least some pumps should be detected → recall > 0
        self.assertGreater(self.result["metrics"]["recall"], 0.0,
                           "recall is 0 — scorer misses every pump")

    def test_per_class_has_entries(self):
        # Per-class breakdown must have at least one liquidity class
        self.assertGreater(len(self.result["per_class"]), 0)

    def test_per_class_metrics_non_negative(self):
        for cls, stats in self.result["per_class"].items():
            self.assertGreaterEqual(stats["precision"], 0.0)
            self.assertGreaterEqual(stats["recall"], 0.0)
            self.assertGreaterEqual(stats["f1"], 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
