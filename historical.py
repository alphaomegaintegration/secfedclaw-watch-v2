#!/usr/bin/env python3
"""SECFEDCLAW v0.2 historical replay on real Polygon/Massive Flat Files.

Runs the v0.2 MARKET-anomaly engine over real historical day-aggregate data for
labeled case/control windows, so the rolling 20/60d and cross-sectional
baselines are computed on actual market history (e.g. SEC pump-and-dump case
windows) rather than synthetic fixtures.

Flat files contain market data only (no social/official/EDGAR), so this
specifically validates the MARKET-anomaly component and its price+volume
double-confirmation on real windows. Full multi-source corroboration still
requires the live scan. Outputs are WATCH-level context, never trading signals.

Usage (live, on a machine with MASSIVE_FLATFILES_* creds + network):
  python3 historical.py --case AABB:2021-09-13:pump --case MSFT:2021-09-13:control
  python3 historical.py --cases-file cases.json
Offline it replays from cached flat files under flatfiles/day_aggs/.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from flatfiles import FlatFilesClient, _FF  # noqa: E402
import scoring_v2  # noqa: E402

PRIORITY_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL_REVIEW": 3}


def _unavailable_fetches() -> dict[str, Any]:
    keys = ("snapshot", "trades", "quotes", "x", "reddit", "otc_threshold",
            "reg_sho", "halts", "submissions", "edgar")
    return {k: _FF(k, None, "unavailable") for k in keys}


def score_window(client: FlatFilesClient, ticker: str, event_date: str,
                 lookback: int = 70) -> dict[str, Any]:
    mf = client.market_fetches(ticker, event_date, lookback_days=lookback)
    fetches = {**_unavailable_fetches(), **mf, "reddit_unavailable": True}
    pkg = scoring_v2.build_package(ticker, fetches)
    md = pkg["market_detail"]
    return {
        "ticker": ticker, "event_date": event_date,
        "n_days_with_bars": mf.get("n_days_with_bars", 0),
        "data_mode": pkg["data_mode"],
        "market_anomaly_score": pkg["component_scores"]["market_anomaly_score"],
        "anomaly_evidence_score": pkg["anomaly_evidence_score"],
        "review_priority": pkg["review_priority"],
        "watch_score": pkg["watch_score"],
        "time_series": {k: md["time_series"].get(k) for k in ("available", "price_z", "volume_z", "double_confirmed")},
        "cross_sectional": {k: md["cross_sectional"].get(k) for k in ("available", "abs_return_xz", "log_volume_xz", "double_confirmed", "thin_liquidity")},
    }


def run(cases: list[dict[str, str]], lookback: int, prefer_live: bool) -> dict[str, Any]:
    client = FlatFilesClient(prefer_live=prefer_live)
    rows = [score_window(client, c["ticker"], c["event_date"], lookback) for c in
            [{"ticker": c["ticker"].upper(), "event_date": c["event_date"]} for c in cases]]
    for r, c in zip(rows, cases):
        r["label"] = c.get("label", "unlabeled")

    have_data = [r for r in rows if r["n_days_with_bars"] > 0]
    pumps = [r["market_anomaly_score"] for r in have_data if r["label"] == "pump"]
    ctrls = [r["market_anomaly_score"] for r in have_data if r["label"] == "control"]
    summary: dict[str, Any] = {
        "credentials_present": client.credentials_present(),
        "data_available_windows": len(have_data),
        "total_windows": len(rows),
    }
    if pumps and ctrls:
        summary["mean_market_anomaly_pump"] = round(sum(pumps) / len(pumps), 2)
        summary["mean_market_anomaly_control"] = round(sum(ctrls) / len(ctrls), 2)
        summary["separation"] = round(summary["mean_market_anomaly_pump"] - summary["mean_market_anomaly_control"], 2)
    return {
        "algorithm_version": scoring_v2.ALGORITHM_VERSION,
        "finding_ceiling": scoring_v2.FINDING_CEILING,
        "harness": "flatfiles_historical_v1",
        "lookback_days": lookback,
        "summary": summary,
        "windows": rows,
        "limitations": [
            "Flat files provide market data only; this validates the MARKET-anomaly component, not full multi-source corroboration.",
            "Real SEC cases are public allegations unless final judgment; tickers/windows must be supplied by the operator.",
            "Market anomaly is statistical context for human review, never proof of manipulation or a trading signal.",
            "Offline runs require cached day-aggregate flat files under flatfiles/day_aggs/.",
        ],
    }


def _parse_cases(args) -> list[dict[str, str]]:
    cases = []
    if args.cases_file:
        data = json.loads(Path(args.cases_file).read_text())
        for c in data:
            cases.append({"ticker": c["ticker"], "event_date": c["event_date"], "label": c.get("label", "unlabeled")})
    for spec in args.case or []:
        parts = spec.split(":")
        cases.append({"ticker": parts[0], "event_date": parts[1],
                      "label": parts[2] if len(parts) > 2 else "unlabeled"})
    return cases


def main() -> int:
    ap = argparse.ArgumentParser(description="SECFEDCLAW v0.2 Flat Files historical replay")
    ap.add_argument("--case", action="append", help="TICKER:YYYY-MM-DD:label (repeatable)")
    ap.add_argument("--cases-file", help="JSON list of {ticker,event_date,label}")
    ap.add_argument("--lookback", type=int, default=70)
    ap.add_argument("--no-live", action="store_true")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent / "out" / "historical_results.json"))
    args = ap.parse_args()
    cases = _parse_cases(args)
    if not cases:
        print("No cases. Provide --case TICKER:YYYY-MM-DD:label or --cases-file cases.json")
        return 2
    result = run(cases, args.lookback, prefer_live=not args.no_live)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, default=str) + "\n")

    s = result["summary"]
    print(f"\nSECFEDCLAW v0.2 Flat Files historical replay — "
          f"{s['data_available_windows']}/{s['total_windows']} windows had data "
          f"(creds_present={s['credentials_present']})")
    print("=" * 78)
    print(f"{'TICKER':<8}{'DATE':<12}{'LABEL':<9}{'MKT_ANOM':>9}{'ANOM_EV':>9}{'PRIORITY':>16}{'DAYS':>6}")
    print("-" * 78)
    for r in result["windows"]:
        print(f"{r['ticker']:<8}{r['event_date']:<12}{r['label']:<9}"
              f"{r['market_anomaly_score']:>9.1f}{r['anomaly_evidence_score']:>9.1f}"
              f"{r['review_priority']:>16}{r['n_days_with_bars']:>6}")
    if "separation" in s:
        print("-" * 78)
        print(f"mean market-anomaly  pump={s['mean_market_anomaly_pump']}  "
              f"control={s['mean_market_anomaly_control']}  separation={s['separation']}")
    print(f"results: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
