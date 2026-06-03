#!/usr/bin/env python3
"""Scheduled daily run for SECFEDCLAW v0.2 (launchd / cron entrypoint).

One idempotent, lock-protected pass intended to run once per trading day after
the close:
  1. preflight  -> record live verdict (GO_LIVE / DEGRADED / REPLAY_ONLY)
  2. EDGAR daily-diff ingest (incremental issuer-event features)
  3. multi-ticker scan (live if available, else replay) + discovery
  4. calibration backtest
  5. offline dashboard render
It writes a machine-readable run summary (out/daily_run_summary.json) and a
dated log (logs/daily_<UTC>.log), and uses a lockfile so overlapping runs
can't collide. WATCH-only; never trades or escalates.

  python3 daily.py                      # live if reachable, default universe
  python3 daily.py --no-live --tickers AAPL AMC
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
LOGS = HERE / "logs"
LOCK = OUT / ".daily.lock"
SUMMARY = OUT / "daily_run_summary.json"
LOCK_STALE_SEC = 6 * 3600


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _log(fh, msg: str) -> None:
    line = f"[{_now()}] {msg}"
    print(line)
    fh.write(line + "\n")
    fh.flush()


def _acquire_lock() -> bool:
    OUT.mkdir(parents=True, exist_ok=True)
    if LOCK.exists():
        try:
            age = time.time() - LOCK.stat().st_mtime
            if age < LOCK_STALE_SEC:
                return False
        except OSError:
            pass
    LOCK.write_text(_now())
    return True


def _release_lock() -> None:
    try:
        LOCK.unlink()
    except OSError:
        pass


def _run(args: list[str], fh) -> int:
    _log(fh, "$ " + " ".join(args))
    p = subprocess.run([sys.executable, *args], cwd=str(HERE),
                       capture_output=True, text=True)
    if p.stdout:
        fh.write(p.stdout + "\n")
    if p.returncode != 0:
        _log(fh, f"  exit {p.returncode}: {p.stderr[:300]}")
    return p.returncode


def run(no_live: bool, tickers: list[str], discover: int) -> dict:
    LOGS.mkdir(parents=True, exist_ok=True)
    started = _now()
    log_path = LOGS / f"daily_{started.replace(':', '').replace('-', '')}.log"
    summary: dict = {"started_utc": started, "steps": {}, "errors": []}
    with log_path.open("w") as fh:
        _log(fh, f"SECFEDCLAW daily run start (no_live={no_live})")

        # 1. preflight
        try:
            sys.path.insert(0, str(HERE))
            import preflight
            rep = preflight.run_preflight()
            summary["preflight_verdict"] = rep["verdict"]
            summary["sources_live"] = rep["sources_live"]
            live = (rep["verdict"] != "REPLAY_ONLY") and not no_live
            _log(fh, f"preflight: {rep['verdict']} ({rep['sources_live']}/{rep['sources_total']} live)")
        except Exception as e:
            summary["preflight_verdict"] = "ERROR"
            summary["errors"].append(f"preflight: {e}")
            live = not no_live
            _log(fh, f"preflight error: {e}")

        # 2. EDGAR daily-diff
        summary["steps"]["edgar"] = _run(
            ["edgar_pipeline.py", "--tickers", *tickers] + ([] if live else ["--no-live"]), fh)

        # 3. scan (live or replay)
        scan = ["scan.py", "--tickers", *tickers, "--discover", str(discover)]
        if not live:
            scan += ["--no-live"]
        summary["steps"]["scan"] = _run(scan, fh)

        # 4. backtest
        summary["steps"]["backtest"] = _run(["backtest.py", "--n", "50"], fh)

        # 5. dashboard
        summary["steps"]["dashboard"] = _run(["dashboard_v2.py"], fh)

        # collect review-queue stats
        try:
            q = json.loads((OUT / "review_queue.json").read_text())
            rows = [r for r in q.get("review_queue", []) if "error" not in r]
            dist = {}
            for r in rows:
                dist[r.get("review_priority")] = dist.get(r.get("review_priority"), 0) + 1
            summary["data_mode"] = q.get("data_mode")
            summary["universe_size"] = q.get("universe_size")
            summary["priority_distribution"] = dist
            summary["flagged_ge_medium"] = sum(v for k, v in dist.items()
                                               if k in ("MEDIUM", "HIGH", "CRITICAL_REVIEW"))
        except Exception as e:
            summary["errors"].append(f"queue parse: {e}")

        summary["finished_utc"] = _now()
        summary["ok"] = all(rc == 0 for rc in summary["steps"].values()) and not summary["errors"]
        summary["log"] = str(log_path)
        _log(fh, f"daily run done ok={summary['ok']} flagged>=MED={summary.get('flagged_ge_medium')}")
    SUMMARY.write_text(json.dumps(summary, indent=2, default=str) + "\n")
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description="SECFEDCLAW v0.2 scheduled daily run")
    ap.add_argument("--tickers", nargs="*", default=["AAPL", "TSLA", "AMC", "GME", "AMD", "ALB"])
    ap.add_argument("--discover", type=int, default=15)
    ap.add_argument("--no-live", action="store_true")
    args = ap.parse_args()

    if os.environ.get("SECFEDCLAW_DAILY_NOLOCK") != "1" and not _acquire_lock():
        print(json.dumps({"skipped": True, "reason": "another daily run holds the lock", "lock": str(LOCK)}))
        return 0
    try:
        summary = run(args.no_live, args.tickers, args.discover)
    finally:
        if os.environ.get("SECFEDCLAW_DAILY_NOLOCK") != "1":
            _release_lock()
    print(json.dumps({k: summary.get(k) for k in
                      ("ok", "preflight_verdict", "data_mode", "priority_distribution",
                       "flagged_ge_medium", "log")}, indent=2, default=str))
    return 0 if summary.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
