#!/usr/bin/env python3
"""Label known SEC cases through the full multi-source scoring pipeline.

Runs each case from cases.json through the Orchestrator (Scout→Analyst→
Adversary→Explainer→Packager) to pull ALL available sources — social,
EDGAR, FINRA/Nasdaq, market — not just flat-file market data. Then
labels each package with the known ground-truth label (pump/control) in
the calibration ledger so the model can learn from multi-source features.

  python3 label_cases.py                    # process all cases
  python3 label_cases.py --cases-file x.json
  python3 label_cases.py --dry-run          # preview without labeling

Historical social data (tweets, Reddit posts from 2021) may not be available
via live APIs, but EDGAR filings, SEC litigation, FINRA/Nasdaq feeds, and
current StockTwits provide additional signal beyond market-only flat files.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from connectors import DataConnector  # noqa: E402
from agents import Orchestrator  # noqa: E402
import model as M  # noqa: E402
import ledger as L  # noqa: E402
from flatfiles import FlatFilesClient  # noqa: E402
import scoring_v2  # noqa: E402

OUT = Path(__file__).resolve().parent / "out"
LABEL_MAP = {"pump": "useful_watch", "control": "benign_explained", "benign_news": "benign_explained"}


def enrich_with_flatfiles(ticker: str, event_date: str, fetches: dict, lookback: int = 60) -> dict:
    """Overlay flat-file historical market data onto the fetches if live data is thin."""
    client = FlatFilesClient(prefer_live=True)
    mf = client.market_fetches(ticker, event_date, lookback_days=lookback)
    if mf.get("n_days_with_bars", 0) > 5:
        # Use flat-file data for daily_range and grouped if they have more history
        if not fetches.get("daily_range") or not fetches["daily_range"].ok():
            fetches["daily_range"] = mf["daily_range"]
        if not fetches.get("grouped") or not fetches["grouped"].ok():
            fetches["grouped"] = mf["grouped"]
    return fetches


def score_case(case: dict, connector: DataConnector, dry_run: bool = False) -> dict[str, Any]:
    """Score a single case through the full pipeline and label it."""
    ticker = case["ticker"].upper()
    event_date = case["event_date"]
    label = case["label"]
    label_name = LABEL_MAP.get(label, "insufficient_evidence")

    # Run through the full agent pipeline (pulls all live sources)
    try:
        orch = Orchestrator(connector=connector, out_dir=OUT / "cases")
        result = orch.run(ticker)
    except Exception as e:
        return {"ticker": ticker, "event_date": event_date, "error": str(e)}

    # Load the generated package
    pkg_path = result.get("package_path")
    if not pkg_path or not Path(pkg_path).exists():
        return {"ticker": ticker, "event_date": event_date, "error": "no package generated"}

    package = json.loads(Path(pkg_path).read_text())

    # Extract key features for comparison
    cs = package.get("component_scores", {})
    summary = {
        "ticker": ticker,
        "event_date": event_date,
        "label": label,
        "label_name": label_name,
        "review_priority": package.get("review_priority"),
        "watch_score": package.get("watch_score", 0),
        "anomaly_evidence": package.get("anomaly_evidence_score", 0),
        "market_anomaly": cs.get("market_anomaly_score", 0),
        "coordination": cs.get("coordination_score", 0),
        "social_burst": cs.get("social_issuer_specific_burst", 0),
        "issuer_event": cs.get("issuer_event_score", 0),
        "enforcement": cs.get("enforcement_history_score", 0),
        "n_families": package.get("corroboration", {}).get("n_families_active", 0),
        "n_platforms": package.get("social_metrics", {}).get("n_platforms", 0),
        "data_mode": package.get("data_mode"),
        "sources_ok": sum(1 for v in package.get("source_health", {}).values() if v.get("ok")),
        "sources_total": len(package.get("source_health", {})),
    }

    # Label in the ledger (unless dry run)
    if not dry_run:
        note = f"{label} case — {case.get('case', '')} ({case.get('src', '')}) {event_date}"
        L.add_label(package, label_name, note=note)
        summary["labeled"] = True
    else:
        summary["labeled"] = False

    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description="Label SEC cases through multi-source pipeline")
    ap.add_argument("--cases-file", default="cases.json")
    ap.add_argument("--dry-run", action="store_true", help="Preview without labeling")
    ap.add_argument("--no-live", action="store_true")
    args = ap.parse_args()

    cases = json.loads(Path(args.cases_file).read_text())
    connector = DataConnector(prefer_live=not args.no_live)

    print(f"SECFEDCLAW case labeling — {len(cases)} cases, live={'yes' if not args.no_live else 'no'}")
    print(f"{'TICKER':8s}{'DATE':12s}{'LABEL':10s}{'PRI':8s}{'SCORE':>7s}{'ANOM':>6s}{'COORD':>6s}{'SOC':>6s}{'EDGAR':>6s}{'FAM':>4s}{'PLAT':>5s}{'SRC':>5s}")
    print("-" * 86)

    results = []
    for case in cases:
        r = score_case(case, connector, dry_run=args.dry_run)
        results.append(r)
        if "error" in r:
            print(f"{r['ticker']:8s}{r['event_date']:12s} ERROR: {r['error'][:40]}")
        else:
            print(f"{r['ticker']:8s}{r['event_date']:12s}{r['label']:10s}{r.get('review_priority','?'):8s}"
                  f"{r.get('watch_score',0):7.1f}{r.get('anomaly_evidence',0):6.1f}"
                  f"{r.get('coordination',0):6.1f}{r.get('social_burst',0):6.1f}"
                  f"{r.get('issuer_event',0):6.1f}{r.get('n_families',0):4d}{r.get('n_platforms',0):5d}"
                  f"{r.get('sources_ok',0):3d}/{r.get('sources_total',0)}")

    print("-" * 86)

    # Summary
    labeled = sum(1 for r in results if r.get("labeled"))
    errors = sum(1 for r in results if "error" in r)
    pumps = [r for r in results if r.get("label") == "pump" and "error" not in r]
    controls = [r for r in results if r.get("label") == "control" and "error" not in r]

    if pumps and controls:
        pump_mean = sum(r.get("watch_score", 0) for r in pumps) / len(pumps)
        ctrl_mean = sum(r.get("watch_score", 0) for r in controls) / len(controls)
        print(f"Mean watch_score: pump={pump_mean:.1f} control={ctrl_mean:.1f} separation={pump_mean-ctrl_mean:.1f}")

    s = L.summary()
    print(f"Ledger: {s['n_labels']} labels ({s['n_positive']} pos, {s['n_negative']} neg)")
    print(f"Labeled: {labeled}, Errors: {errors}")

    if not args.dry_run and labeled > 0:
        print("\nTo retrain the model with these labels: python3 train_model.py")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
