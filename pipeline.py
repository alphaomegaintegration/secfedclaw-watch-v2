#!/usr/bin/env python3
"""One-command SECFEDCLAW v0.2 pipeline: scan -> backtest -> dashboard.

Runs the agentic multi-ticker scan, the calibration backtest, and renders the
self-contained dashboard. Live on a networked machine (uses .env), replay
otherwise. WATCH-only throughout.

  python3 pipeline.py                       # default universe, live if available
  python3 pipeline.py --no-live --discover 10
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _run(args: list[str]) -> None:
    print(f"\n$ {' '.join(args)}")
    subprocess.run([sys.executable, *args], cwd=str(HERE), check=False)


def main() -> int:
    ap = argparse.ArgumentParser(description="SECFEDCLAW v0.2 full pipeline")
    ap.add_argument("--tickers", nargs="*", default=["AAPL", "TSLA", "AMC", "GME", "AMD", "ALB"])
    ap.add_argument("--discover", type=int, default=8)
    ap.add_argument("--no-live", action="store_true")
    ap.add_argument("--bt-n", type=int, default=50)
    args = ap.parse_args()

    if not args.no_live:
        _run(["preflight.py"])
    scan = ["scan.py", "--tickers", *args.tickers, "--discover", str(args.discover)]
    if args.no_live:
        scan.append("--no-live")
    else:
        scan.append("--live")
    _run(scan)
    _run(["backtest.py", "--n", str(args.bt_n)])
    _run(["dashboard_v2.py"])
    print(f"\nOpen: {HERE / 'out' / 'dashboard_v2.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
