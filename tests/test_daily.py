#!/usr/bin/env python3
"""Tests for the scheduled daily entrypoint."""
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


class TestDaily(unittest.TestCase):
    @pytest.mark.slow
    def test_daily_run_replay_writes_summary(self):
        # daily.py and its subprocess steps write into the real out/ dir. Snapshot
        # the operator-facing artifacts and restore them afterward so running the
        # (slow) suite never clobbers a live dashboard. See obs: test pollution.
        out = ROOT / "out"
        preserve = ["review_queue.json", "run_manifest.json", "dashboard_v2.html",
                    "daily_run_summary.json", "backtest_results.json"]
        backup = {n: (out / n).read_bytes() for n in preserve if (out / n).exists()}
        env = dict(os.environ)
        env["SECFEDCLAW_DAILY_NOLOCK"] = "1"
        try:
            # point at the fed_claw data tree if present for replay; else self-contained
            p = subprocess.run(
                [sys.executable, "daily.py", "--no-live", "--tickers", "AAPL", "--discover", "0"],
                cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=180)
            self.assertEqual(p.returncode in (0, 1), True, p.stderr[:300])
            summary = out / "daily_run_summary.json"
            self.assertTrue(summary.exists())
            s = json.loads(summary.read_text())
            for k in ("started_utc", "finished_utc", "steps", "preflight_verdict"):
                self.assertIn(k, s)
            # scan/backtest/dashboard steps all recorded
            for step in ("scan", "backtest", "dashboard", "edgar"):
                self.assertIn(step, s["steps"])
        finally:
            for n, data in backup.items():
                (out / n).write_bytes(data)

    def test_lock_blocks_second_run(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("daily_mod", ROOT / "daily.py")
        daily = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(daily)
        # simulate a held lock
        daily.OUT.mkdir(parents=True, exist_ok=True)
        daily.LOCK.write_text("held")
        try:
            self.assertFalse(daily._acquire_lock())
        finally:
            try:
                daily.LOCK.unlink()
            except OSError:
                pass


if __name__ == "__main__":
    unittest.main(verbosity=2)
