#!/usr/bin/env python3
"""SECFEDCLAW v0.2 multi-ticker scan orchestrator.

Runs the agentic pipeline across a ticker universe and emits a ranked
review queue (highest review priority first). The universe can be:
  * an explicit --tickers list, or
  * the DEFAULT_UNIVERSE, optionally augmented by --discover N which pulls the
    top-N cross-sectional movers from the grouped-daily market snapshot
    (the same data the scanner already loads), surfacing candidates the
    operator did not name.

WATCH-only. Produces review-priority packages, never trading signals.

Usage:
  python3 scan.py --tickers AAPL TSLA AMC GME
  python3 scan.py --discover 15
  python3 scan.py                       # default universe
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import DEFAULT_UNIVERSE, ALGORITHM_VERSION, FINDING_CEILING  # noqa: E402
from connectors import DataConnector  # noqa: E402
from agents import Orchestrator  # noqa: E402

PRIORITY_RANK = {"CRITICAL_REVIEW": 3, "HIGH": 2, "MEDIUM": 1, "LOW": 0}


def discover_movers(connector: DataConnector, n: int) -> list[str]:
    """Top-N tickers by |intraday return| from grouped-daily snapshot."""
    f = connector.polygon_grouped_daily()
    rows = (f.data or {}).get("results") if isinstance(f.data, dict) else None
    if not rows:
        return []
    scored = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        o, c, v = r.get("o"), r.get("c"), r.get("v")
        sym = r.get("T")
        if not (o and c and sym):
            continue
        dollar_vol = (v or 0) * (r.get("vw") or c)
        if dollar_vol < 500_000:  # skip illiquid noise
            continue
        ret = abs((c - o) / o)
        scored.append((ret, sym))
    scored.sort(reverse=True)
    return [s for _, s in scored[:n]]


def _iso_utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def run_scan(universe: list[str], *, prefer_live: bool, out_dir: Path | str | None = None,
             connector: DataConnector | None = None) -> dict:
    """Run the agent pipeline across `universe`, writing review_queue.json AND an
    incremental run_manifest.json, and return the queue dict.

    The review_queue.json contents are identical to the pre-Phase-0 pipeline
    (the manifest is a separate, additive operational artifact). Per-ticker
    failures never abort the scan.
    """
    connector = connector or DataConnector(prefer_live=prefer_live)
    live = connector.live_available()
    out_dir = Path(out_dir) if out_dir else (Path(__file__).resolve().parent / "out")
    out_dir.mkdir(parents=True, exist_ok=True)
    orch = Orchestrator(connector=connector, out_dir=out_dir)

    # ---- run-manifest: the durable, live operational record (architecture §5.3)
    manifest = {
        "run_id": time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()),
        "mode": "live" if live else "replay",
        "universe": list(universe),
        "started_utc": _iso_utc(),
        "finished_utc": None,
        "tickers": {},
    }
    mpath = out_dir / "run_manifest.json"

    def _write_manifest() -> None:
        # Atomic: write to a temp file then rename, so a concurrent reader (the
        # test poll, and the live dashboard polling /run_manifest.json) never sees
        # a half-written/empty file. os.replace is atomic on the same filesystem.
        tmp = mpath.with_name(mpath.name + ".tmp")
        tmp.write_text(json.dumps(manifest, indent=2, default=str) + "\n")
        tmp.replace(mpath)

    _write_manifest()
    results = []
    for ticker in universe:
        t0 = time.monotonic()
        try:
            summary = orch.run(ticker)
            results.append(summary)
            manifest["tickers"][ticker] = {
                "status": "done",
                "priority": summary.get("review_priority"),
                "watch_score": summary.get("watch_score"),
                "ms": round((time.monotonic() - t0) * 1000),
                "fetches": {k: v.get("mode") for k, v in (summary.get("source_health") or {}).items()},
            }
        except Exception as e:  # never let one ticker abort the scan
            results.append({"ticker": ticker, "error": f"{type(e).__name__}: {e}",
                            "review_priority": "LOW", "watch_score": 0})
            manifest["tickers"][ticker] = {
                "status": "error", "error": f"{type(e).__name__}: {e}",
                "ms": round((time.monotonic() - t0) * 1000),
            }
        _write_manifest()  # incremental: dashboard can watch progress live

    results.sort(key=lambda r: (PRIORITY_RANK.get(r.get("review_priority", "LOW"), 0),
                                r.get("watch_score", 0)), reverse=True)

    queue = {
        "algorithm_version": ALGORITHM_VERSION,
        "finding_ceiling": FINDING_CEILING,
        "data_mode": "live" if live else "replay",
        "universe_size": len(universe),
        "review_queue": results,
        "guardrails": "WATCH-only review priorities. Not trading signals or proof of misconduct.",
    }
    (out_dir / "review_queue.json").write_text(json.dumps(queue, indent=2, default=str) + "\n")
    manifest["finished_utc"] = _iso_utc()
    _write_manifest()
    return queue


def main() -> int:
    ap = argparse.ArgumentParser(description="SECFEDCLAW v0.2 multi-ticker WATCH scan")
    ap.add_argument("--tickers", nargs="*", help="explicit ticker universe")
    ap.add_argument("--discover", type=int, default=0, help="add top-N cross-sectional movers")
    ap.add_argument("--no-live", action="store_true", help="force replay mode (skip live fetch)")
    ap.add_argument("--live", action="store_true", help="run preflight then scan live (default is live-if-available)")
    ap.add_argument("--out", default=None, help="output dir for packages")
    args = ap.parse_args()

    if args.live and not args.no_live:
        import preflight
        rep = preflight.run_preflight()
        print(f"preflight verdict: {rep['verdict']} ({rep['sources_live']}/{rep['sources_total']} sources live)")
        for r in rep["results"]:
            print(f"  {r['source']:<12} {'live' if r['reachable'] else r['mode_if_run']}")
        if rep["verdict"] == "REPLAY_ONLY":
            print("No live sources reachable — proceeding in REPLAY mode.")

    connector = DataConnector(prefer_live=not args.no_live)

    universe = list(args.tickers) if args.tickers else list(DEFAULT_UNIVERSE)
    if args.discover:
        for sym in discover_movers(connector, args.discover):
            if sym not in universe:
                universe.append(sym)

    out_dir = Path(args.out) if args.out else (Path(__file__).resolve().parent / "out")
    queue = run_scan(universe, prefer_live=not args.no_live, out_dir=out_dir, connector=connector)
    live = queue["data_mode"] == "live"
    results = queue["review_queue"]

    # console summary
    print(f"\nSECFEDCLAW v0.2 scan — mode={'LIVE' if live else 'REPLAY'} — {len(universe)} tickers")
    print("=" * 78)
    print(f"{'TICKER':<8}{'PRIORITY':<17}{'SCORE':>7}{'ANOM':>7}{'EVQ':>6}{'FAM':>5}  {'MODE':<7}")
    print("-" * 78)
    for r in results:
        if "error" in r:
            print(f"{r['ticker']:<8}{'ERROR':<17}{'':>7}{'':>7}{'':>6}{'':>5}  {r['error'][:30]}")
            continue
        print(f"{r['ticker']:<8}{r['review_priority']:<17}{r['watch_score']:>7.1f}"
              f"{r.get('anomaly_evidence_score',0):>7.1f}{r.get('evidence_quality_score',0):>6.0f}"
              f"{r.get('n_families_active',0):>5}  {r.get('data_mode','?'):<7}")
    print("-" * 78)
    print(f"Review queue: {out_dir / 'review_queue.json'}")
    print(f"Run manifest: {out_dir / 'run_manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
