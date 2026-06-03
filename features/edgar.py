#!/usr/bin/env python3
"""EDGAR issuer-event features for SECFEDCLAW v0.2.

Pure, testable functions for the EDGAR daily-diff pipeline (`edgar_pipeline.py`):
parse the SEC daily-index master file, classify filings into pump-relevant
categories, and turn a CIK's recent filings into an issuer-event feature set +
a concern-bearing score.

Why this matters for pump-and-dump review: issuers/insiders SELLING or
DILUTING into promoted demand is a classic tell. So unlike `issuer_context`
(reviewability/context), the `issuer_event` score here is treated as
concern-bearing and can corroborate a social/market move.

Everything is WATCH-level context. SEC filings are official records, not proof
of misconduct; insider sales and registrations are lawful and routine in
isolation.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

# Form-type categories relevant to pump-and-dump issuer context.
INSIDER_FORMS = {"3", "4", "5", "144"}
DILUTION_FORMS = {"S-1", "S-1/A", "S-3", "S-3/A", "F-1", "F-3", "424B1", "424B2",
                  "424B3", "424B4", "424B5", "EFFECT", "S-8", "S-8 POS", "POS AM"}
MATERIAL_FORMS = {"8-K", "8-K/A", "6-K"}
LATE_FORMS = {"NT 10-K", "NT 10-Q", "NT 20-F"}
DELIST_FORMS = {"25", "25-NSE", "15-12B", "15-12G", "15-15D"}
REGISTRATION_FORMS = {"S-1", "F-1", "10-12B", "10-12G", "1-A"}

RELEVANT_FORMS = (INSIDER_FORMS | DILUTION_FORMS | MATERIAL_FORMS | LATE_FORMS
                  | DELIST_FORMS | REGISTRATION_FORMS)


def classify_form(form: str) -> list[str]:
    f = form.strip().upper()
    cats = []
    if f in {x.upper() for x in INSIDER_FORMS}:
        cats.append("insider")
    if f in {x.upper() for x in DILUTION_FORMS}:
        cats.append("dilution")
    if f in {x.upper() for x in MATERIAL_FORMS}:
        cats.append("material")
    if f in {x.upper() for x in LATE_FORMS}:
        cats.append("late")
    if f in {x.upper() for x in DELIST_FORMS}:
        cats.append("delist")
    if f in {x.upper() for x in REGISTRATION_FORMS}:
        cats.append("registration")
    return cats


def parse_master_idx(text: str) -> list[dict[str, Any]]:
    """Parse a SEC daily-index master.idx (pipe-delimited).

    Columns: CIK|Company Name|Form Type|Date Filed|Filename
    The accession number is derivable from the filename.
    """
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or "|" not in line:
            continue
        parts = line.split("|")
        if len(parts) < 5:
            continue
        cik, name, form, filed, filename = parts[0], parts[1], parts[2], parts[3], parts[4]
        if not cik.isdigit():
            continue  # skip header rows
        accession = filename.rsplit("/", 1)[-1].replace(".txt", "")
        rows.append({
            "cik": cik.zfill(10),
            "company": name.strip(),
            "form": form.strip(),
            "date_filed": filed.strip(),
            "accession": accession,
            "categories": classify_form(form),
        })
    return rows


def _days_since(d: str, asof: str | None) -> int | None:
    try:
        f = datetime.strptime(d, "%Y-%m-%d").date()
    except Exception:
        return None
    base = date.today() if not asof else datetime.strptime(asof, "%Y-%m-%d").date()
    return (base - f).days


def build_issuer_features(filings: list[dict[str, Any]], asof: str | None = None) -> dict[str, Any]:
    """Aggregate a CIK's recent filings into an issuer-event feature set."""
    cats = {"insider": 0, "dilution": 0, "material": 0, "late": 0, "delist": 0, "registration": 0}
    recency: dict[str, int] = {}
    for fl in filings:
        for c in fl.get("categories", []):
            cats[c] = cats.get(c, 0) + 1
            ds = _days_since(fl.get("date_filed", ""), asof)
            if ds is not None and (c not in recency or ds < recency[c]):
                recency[c] = ds
    return {
        "n_filings": len(filings),
        "counts": cats,
        "days_since": recency,
        "has_recent_insider": cats["insider"] > 0,
        "has_recent_dilution": cats["dilution"] > 0,
        "has_delisting_signal": cats["delist"] > 0,
        "has_late_filing": cats["late"] > 0,
        "forms": sorted({fl.get("form") for fl in filings if fl.get("form")})[:30],
    }


def issuer_event_score(features: dict[str, Any]) -> tuple[float, list[str]]:
    """Concern-bearing 0..100 score: dilution + insider + delist weighted highest."""
    if not features:
        return 0.0, []
    c = features.get("counts", {})
    ds = features.get("days_since", {})
    basis: list[str] = []
    score = 0.0

    def recency_mult(cat: str) -> float:
        d = ds.get(cat)
        if d is None:
            return 0.6
        if d <= 7:
            return 1.0
        if d <= 30:
            return 0.8
        if d <= 90:
            return 0.55
        return 0.3

    if c.get("dilution"):
        v = min(c["dilution"] * 14, 35) * recency_mult("dilution")
        score += v
        basis.append(f"dilution/financing filings={c['dilution']} (S-1/S-3/424B/EFFECT/S-8)")
    if c.get("insider"):
        v = min(c["insider"] * 8, 25) * recency_mult("insider")
        score += v
        basis.append(f"insider forms (3/4/5/144)={c['insider']}")
    if c.get("delist"):
        score += 15
        basis.append("delisting/deregistration form present (25/15-12B)")
    if c.get("late"):
        score += 10
        basis.append("late-filing notification (NT 10-K/10-Q)")
    if c.get("material"):
        score += min(c["material"] * 4, 12)
        basis.append(f"material 8-K filings={c['material']}")
    if not basis:
        basis.append("no pump-relevant issuer filings in window")
    return min(score, 100.0), basis
