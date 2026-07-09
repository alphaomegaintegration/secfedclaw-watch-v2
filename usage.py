#!/usr/bin/env python3
"""LLM usage & cost tracking for SECFEDCLAW v0.2.

A small, dependency-free ledger any LLM-using component can call to record a
model call (model, input/output tokens, component), with cost computed from a
configurable pricing table. Aggregates by model / component / day for the
dashboard's LLM cost panel.

The v0.2 scoring core is rules + numpy (no LLM calls), so this starts empty and
is the place where future LLM-backed agents (e.g. an LLM explanation/adversary
agent) record their spend. Prices are list-price approximations (USD per 1M
tokens) and can be overridden by out/usage/pricing.json.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import threading
from config import output_root

USAGE_DIR = output_root() / "usage"
LEDGER = USAGE_DIR / "llm_usage.jsonl"
PRICING_OVERRIDE = USAGE_DIR / "pricing.json"

# USD per 1,000,000 tokens (input, output). Approximate public list prices;
# adjust in out/usage/pricing.json. Keys are matched by substring (lowercased).
DEFAULT_PRICING: dict[str, tuple[float, float]] = {
    "opus": (15.0, 75.0),
    "sonnet": (3.0, 15.0),
    "haiku": (0.80, 4.0),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.0),
    "o3": (10.0, 40.0),
    "gemini-1.5-pro": (1.25, 5.0),
    "gemini-1.5-flash": (0.075, 0.30),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini": (1.25, 5.0),
    # Local models run on the operator's machine (Ollama) — genuinely $0. Listed
    # so they price as known-free instead of "unknown pricing".
    "ollama": (0.0, 0.0),
    "local": (0.0, 0.0),
}


_APPEND_LOCK = threading.Lock()  # serialize JSONL appends (threaded serve.py)

def _pricing() -> dict[str, tuple[float, float]]:
    p = dict(DEFAULT_PRICING)
    if PRICING_OVERRIDE.exists():
        try:
            for k, v in json.loads(PRICING_OVERRIDE.read_text()).items():
                p[k.lower()] = (float(v[0]), float(v[1]))
        except Exception:
            pass
    return p


def price_for(model: str) -> tuple[float, float, bool]:
    """Return (in_per_1M, out_per_1M, known)."""
    m = (model or "").lower()
    pricing = _pricing()
    # longest matching key wins (so 'gpt-4o-mini' beats 'gpt-4o')
    best = None
    for key, val in pricing.items():
        if key in m and (best is None or len(key) > len(best[0])):
            best = (key, val)
    if best:
        return best[1][0], best[1][1], True
    return 0.0, 0.0, False


def is_free(model: str) -> bool:
    """True when the model matched a known zero-price (local) entry."""
    pin, pout, known = price_for(model)
    return known and pin == 0.0 and pout == 0.0


def cost(model: str, input_tokens: int, output_tokens: int) -> float:
    pin, pout, _ = price_for(model)
    return round(input_tokens / 1e6 * pin + output_tokens / 1e6 * pout, 6)


def record(model: str, input_tokens: int, output_tokens: int, component: str = "",
           meta: dict[str, Any] | None = None, path: Path | None = None) -> dict[str, Any]:
    p = path or LEDGER
    p.parent.mkdir(parents=True, exist_ok=True)
    _, _, known = price_for(model)
    row = {
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "model": model, "component": component,
        "input_tokens": int(input_tokens), "output_tokens": int(output_tokens),
        "cost_usd": cost(model, input_tokens, output_tokens), "pricing_known": known,
        "meta": meta or {},
    }
    with _APPEND_LOCK:
        with p.open("a") as f:
            f.write(json.dumps(row, default=str) + "\n")
    return row


def load(path: Path | None = None) -> list[dict[str, Any]]:
    p = path or LEDGER
    if not p.exists():
        return []
    rows = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    return rows


def summary(path: Path | None = None) -> dict[str, Any]:
    rows = load(path)

    def agg(key):
        d: dict[str, dict[str, float]] = {}
        for r in rows:
            k = r.get(key) or "unknown"
            a = d.setdefault(k, {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0})
            a["calls"] += 1
            a["input_tokens"] += r.get("input_tokens", 0)
            a["output_tokens"] += r.get("output_tokens", 0)
            a["cost_usd"] = round(a["cost_usd"] + r.get("cost_usd", 0.0), 6)
        return d

    # Paid vs local-free split: a recorded call is "free" when its model matched
    # a known zero-price (local) entry. Everything else with cost is "paid".
    free_calls = sum(1 for r in rows if is_free(r.get("model", "")))
    return {
        "n_calls": len(rows),
        "total_cost_usd": round(sum(r.get("cost_usd", 0.0) for r in rows), 4),
        "paid_cost_usd": round(sum(r.get("cost_usd", 0.0) for r in rows), 4),
        "paid_calls": len(rows) - free_calls,
        "local_free_calls": free_calls,
        "total_input_tokens": sum(r.get("input_tokens", 0) for r in rows),
        "total_output_tokens": sum(r.get("output_tokens", 0) for r in rows),
        "by_model": agg("model"),
        "by_component": agg("component"),
        "by_day": {r["ts"][:10]: 1 for r in rows} and _by_day(rows),
        "any_unknown_pricing": any(not r.get("pricing_known", True) for r in rows),
    }


def _by_day(rows):
    d: dict[str, float] = {}
    for r in rows:
        day = (r.get("ts") or "")[:10]
        d[day] = round(d.get(day, 0.0) + r.get("cost_usd", 0.0), 4)
    return d


def main() -> int:
    ap = argparse.ArgumentParser(description="SECFEDCLAW LLM usage / cost tracker")
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--record", nargs=3, metavar=("MODEL", "IN", "OUT"))
    ap.add_argument("--component", default="")
    args = ap.parse_args()
    if args.record:
        print(json.dumps(record(args.record[0], int(args.record[1]), int(args.record[2]),
                                component=args.component), indent=2))
        return 0
    print(json.dumps(summary(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
