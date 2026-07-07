#!/usr/bin/env python3
"""Official-source context features (market-structure / issuer / halt).

Reuses v0.1 semantics but generalizes ticker matching so the multi-ticker
scan works for any symbol (v0.1 hard-coded several AAPL-only branches).
All official data is CONTEXT for review, never proof.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

# Only filings within this window light the issuer-event family. Without it,
# nearly any active filer scores issuer_context >= 30 from a year of "recent"
# forms, handing every ticker a near-free second corroborating family and
# collapsing the >=2-family HIGH/CRITICAL gate to effectively one.
_ISSUER_RECENCY_DAYS = 90


def _records(fetch_data: Any) -> list[dict]:
    if isinstance(fetch_data, dict):
        for key in ("records_sample", "results", "data"):
            v = fetch_data.get(key)
            if isinstance(v, list):
                return [r for r in v if isinstance(r, dict)]
    if isinstance(fetch_data, list):
        return [r for r in fetch_data if isinstance(r, dict)]
    return []


def _matches(records: list[dict], ticker: str) -> list[dict]:
    t = ticker.upper().lstrip("$")
    out = []
    for r in records:
        sym = str(r.get("symbol") or r.get("ticker") or r.get("Symbol")
                  or r.get("issueSymbolIdentifier") or "").upper().lstrip("$")
        if sym == t:
            out.append(r)
    return out


def official_context(ticker: str, otc_threshold: Any, reg_sho: Any, halts: Any,
                     submissions: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"families": {}, "evidence": []}
    fam = out["families"]

    otc = _matches(_records(otc_threshold), ticker)
    sho = _matches(_records(reg_sho), ticker)
    halt = _matches(_records(halts), ticker)
    if otc:
        fam["finra_otc_threshold"] = otc
    if sho:
        fam["nasdaq_reg_sho"] = sho
    if halt:
        fam["nasdaq_halts"] = halt

    # issuer context from SEC submissions (recent forms 3/4/5/8-K/S-1/424B)
    if isinstance(submissions, dict):
        recent = (((submissions.get("filings") or {}).get("recent")) or {})
        forms = recent.get("form") or []
        dates = recent.get("filingDate") or []
        cutoff = datetime.now(timezone.utc) - timedelta(days=_ISSUER_RECENCY_DAYS)
        flagged = []
        for f, d in zip(forms, dates):
            if f in {"3", "4", "5", "8-K", "S-1", "S-3", "424B5", "424B4", "EFFECT", "144"}:
                try:
                    fd = datetime.fromisoformat(str(d)).replace(tzinfo=timezone.utc)
                    if fd < cutoff:
                        continue  # too old to count as a current issuer event
                except Exception:
                    pass  # unparseable date: keep (conservative)
                flagged.append({"form": f, "date": d})
        if flagged:
            fam["sec_recent_forms"] = flagged[:25]
            out["issuer_name"] = submissions.get("name")
    return out


def official_scores(ctx: dict[str, Any]) -> dict[str, float]:
    fam = ctx.get("families", {})
    ms = 0.0
    ms += 25 if fam.get("finra_otc_threshold") else 0
    ms += 25 if fam.get("nasdaq_reg_sho") else 0
    ms = min(ms, 100)
    issuer = 0.0
    forms = fam.get("sec_recent_forms", [])
    # insider (4) + financing/resale (S-1/S-3/424B) + material (8-K) weighting
    insider = sum(1 for f in forms if f["form"] in {"3", "4", "5", "144"})
    financing = sum(1 for f in forms if f["form"] in {"S-1", "S-3", "424B5", "424B4", "EFFECT"})
    material = sum(1 for f in forms if f["form"] == "8-K")
    issuer += min(insider * 6, 35) + min(financing * 10, 35) + min(material * 4, 20)
    halt = min(len(fam.get("nasdaq_halts", [])) * 35, 70)
    return {
        "market_structure_score": float(round(ms, 2)),
        "issuer_context_score": float(round(min(issuer, 100), 2)),
        "halt_regulatory_score": float(round(halt, 2)),
    }
