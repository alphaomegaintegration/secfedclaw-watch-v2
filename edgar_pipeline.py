#!/usr/bin/env python3
"""SECFEDCLAW EDGAR daily-diff pipeline.

Ingests SEC EDGAR daily-index filings INCREMENTALLY ("just the diffs"): it
keeps a state watermark of the last processed date and the accession numbers
already seen, so each run only processes new filings. Designed to be run daily
(cron-friendly) and to accumulate issuer-event history per ticker.

Flow:
  1. Resolve a ticker -> CIK map from SEC company_tickers.json (live or cached).
  2. For each new business day since the watermark, fetch the daily-index
     master file and parse pump-relevant filings (insider / dilution / material
     / late / delisting / registration).
  3. Diff against seen accessions; append new filings to per-CIK history.
  4. Recompute issuer-event features per watched ticker and write them to
     out/edgar/issuer_features_<TICKER>.json for the scorer to consume.
  5. Advance the watermark.

Live on a networked machine (uses SEC_USER_AGENT from .env); offline it parses
any cached daily-index artifact and is otherwise a no-op that preserves state.

WATCH-only: SEC filings are official context, never proof of misconduct.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from connectors import DataConnector  # noqa: E402
from config import DEFAULT_UNIVERSE  # noqa: E402
from features import edgar  # noqa: E402

PKG = Path(__file__).resolve().parent
STATE_PATH = PKG / "state" / "edgar_state.json"
OUT_DIR = PKG / "out" / "edgar"


def _load_state() -> dict[str, Any]:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except Exception:
            pass
    return {"watermark_date": None, "seen_accessions": [], "cik_history": {}}


def _save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    # cap stored accessions/history so state cannot grow unbounded
    state["seen_accessions"] = state.get("seen_accessions", [])[-50000:]
    STATE_PATH.write_text(json.dumps(state, indent=2, default=str) + "\n")


def _business_days(since: str | None, until: date, max_days: int) -> list[str]:
    start = (datetime.strptime(since, "%Y-%m-%d").date() + timedelta(days=1)
             if since else until - timedelta(days=max_days))
    days = []
    d = start
    while d <= until and len(days) < max_days:
        if d.weekday() < 5:  # Mon-Fri
            days.append(d.isoformat())
        d += timedelta(days=1)
    return days


def _ticker_cik_map(conn: DataConnector, tickers: list[str]) -> dict[str, str]:
    f = conn.sec_company_tickers()
    out: dict[str, str] = {}
    data = f.data if f.ok() else None
    if isinstance(data, dict):
        rows = data.values() if not data.get("data") else data.get("data")
        for row in rows:
            if isinstance(row, dict):
                t = str(row.get("ticker", "")).upper()
                cik = str(row.get("cik_str") or row.get("cik") or "").zfill(10)
                if t:
                    out[t] = cik
            elif isinstance(row, list) and len(row) >= 3:
                out[str(row[2]).upper()] = str(row[0]).zfill(10)
    # restrict to the requested watch universe; fall back to the built-in map
    from agents import CIK_MAP
    wanted = {t.upper() for t in tickers}
    resolved: dict[str, str] = {}
    for t in wanted:
        cik = out.get(t) or CIK_MAP.get(t, "")
        if cik:
            resolved[t] = cik.zfill(10)
    return resolved


def run(tickers: list[str], max_days: int = 5, prefer_live: bool = True) -> dict[str, Any]:
    # Ensure state/ directory exists before any read or write attempt.
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = DataConnector(prefer_live=prefer_live)
    state = _load_state()
    seen = set(state.get("seen_accessions", []))
    cik_history: dict[str, list] = {k: list(v) for k, v in state.get("cik_history", {}).items()}

    cik_map = _ticker_cik_map(conn, tickers)
    watched_ciks = {cik_map[t] for t in (t.upper() for t in tickers) if t in cik_map}

    days = _business_days(state.get("watermark_date"), date.today(), max_days)
    new_filings = 0
    days_with_data = 0
    last_processed = state.get("watermark_date")
    for day in days:
        f = conn.sec_daily_index(day)
        if not f.ok() or not isinstance(f.data, str):
            # offline / no data for this day: still advance watermark so we don't
            # re-probe the same empty day forever, but record nothing.
            last_processed = day
            continue
        days_with_data += 1
        for filing in edgar.parse_master_idx(f.data):
            if filing["cik"] not in watched_ciks:
                continue
            if not filing["categories"]:
                continue
            if filing["accession"] in seen:
                continue
            seen.add(filing["accession"])
            cik_history.setdefault(filing["cik"], []).append(filing)
            new_filings += 1
        last_processed = day

    # recompute issuer-event features per watched ticker
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    asof = date.today().isoformat()
    written = []
    cik_to_ticker = {v: k for k, v in cik_map.items()}
    for cik, filings in cik_history.items():
        ticker = cik_to_ticker.get(cik)
        if not ticker:
            continue
        recent = [fl for fl in filings if _recent(fl.get("date_filed"), asof, 120)]
        feats = edgar.build_issuer_features(recent or filings, asof)
        score, basis = edgar.issuer_event_score(feats)
        payload = {
            "ticker": ticker, "cik": cik, "generated_utc": _now(),
            "asof": asof, "issuer_event_score": round(score, 2),
            "basis": basis, "features": feats,
            "limitation": "WATCH-level issuer context; SEC filings are official records, not proof of misconduct.",
        }
        path = OUT_DIR / f"issuer_features_{ticker}.json"
        path.write_text(json.dumps(payload, indent=2, default=str) + "\n")
        written.append({"ticker": ticker, "issuer_event_score": round(score, 2), "path": str(path)})

    state.update({
        "watermark_date": last_processed,
        "seen_accessions": sorted(seen),
        "cik_history": cik_history,
        "last_run_utc": _now(),
    })
    _save_state(state)
    return {
        "mode": "live" if conn.live_available_sec(conn.env.get("SEC_USER_AGENT", "secfedclaw")) else "offline",
        "days_scanned": len(days), "days_with_data": days_with_data,
        "new_filings": new_filings, "watched_tickers": sorted(cik_map.keys()),
        "watermark_date": last_processed, "issuer_features_written": written,
    }


def _recent(d: str | None, asof: str, window: int) -> bool:
    if not d:
        return False
    try:
        f = datetime.strptime(d, "%Y-%m-%d").date()
        return (datetime.strptime(asof, "%Y-%m-%d").date() - f).days <= window
    except Exception:
        return False


def _now() -> str:
    from datetime import timezone
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def main() -> int:
    ap = argparse.ArgumentParser(description="SECFEDCLAW EDGAR daily-diff pipeline")
    ap.add_argument("--tickers", nargs="*", default=list(DEFAULT_UNIVERSE))
    ap.add_argument("--max-days", type=int, default=5, help="max business days to advance per run")
    ap.add_argument("--no-live", action="store_true")
    args = ap.parse_args()
    result = run(args.tickers, max_days=args.max_days, prefer_live=not args.no_live)
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
