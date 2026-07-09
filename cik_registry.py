"""Ticker → SEC CIK registry, shared by the agent pipeline and edgar_pipeline.

Lives outside agents.py so the EDGAR ETL (edgar_pipeline) doesn't import the
whole agent/scoring stack just to resolve a CIK — that was a cross-layer import
cycle (edgar_pipeline → agents → connectors → config). Dynamic population from
SEC company_tickers.json is guarded by a lock, because the ticker-parallel scan
calls load_cik_map() from multiple worker threads (the old flag was unguarded).
"""
from __future__ import annotations

import threading
from typing import Any

# Static seed; extended dynamically at runtime from SEC company_tickers.json.
CIK_MAP: dict[str, str] = {
    "AAPL": "0000320193", "TSLA": "0001318605", "AMC": "0001411579",
    "GME": "0001326380", "AMD": "0000002488", "NVDA": "0001045810",
    "ALB": "0000915913",
}
_lock = threading.Lock()
_loaded = False


def load_cik_map(connector: Any) -> None:
    """Populate CIK_MAP from SEC company_tickers.json once (no API key needed).
    Thread-safe: the lock serializes the check-and-load so concurrent scan
    workers can't double-fetch or see a half-populated dict mid-update."""
    global _loaded
    with _lock:
        if _loaded:
            return
        _loaded = True
        try:
            f = connector.sec_company_tickers()
            if f.ok() and isinstance(f.data, dict):
                for v in f.data.values():
                    if isinstance(v, dict) and v.get("ticker") and v.get("cik_str"):
                        CIK_MAP[v["ticker"].upper()] = str(v["cik_str"]).zfill(10)
        except Exception:
            pass


def cik_for(ticker: str) -> str | None:
    return CIK_MAP.get(ticker.upper())
