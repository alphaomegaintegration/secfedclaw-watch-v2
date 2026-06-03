#!/usr/bin/env python3
"""SEC enforcement-history feature for SECFEDCLAW v0.2.

Parses the SEC litigation-releases / administrative-proceedings feed and checks
whether the ticker or issuer appears in recent enforcement actions. This is the
design doc's family E (halt / regulatory context).

CRITICAL framing: enforcement history is BACKWARD-LOOKING and must NOT imply
current misconduct. A prior action against an issuer/promoter raises review
attention and is recorded as context with the cited release — never as proof
that today's activity is fraudulent. The score is deliberately modest and
gated; matched releases are emitted for human verification.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any

_TAG = re.compile(r"<[^>]+>")


def parse_releases(xml_text: str) -> list[dict[str, Any]]:
    """Parse an SEC RSS/Atom litigation feed into {title, link, date, summary}."""
    out: list[dict[str, Any]] = []
    if not xml_text:
        return out
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return out
    for el in root.iter():
        tag = el.tag.rsplit("}", 1)[-1].lower()
        if tag != "item" and tag != "entry":
            continue
        rec = {"title": "", "link": "", "date": "", "summary": ""}
        for ch in el:
            t = ch.tag.rsplit("}", 1)[-1].lower()
            txt = (ch.text or "").strip()
            if t == "title":
                rec["title"] = txt
            elif t == "link":
                rec["link"] = txt or ch.attrib.get("href", "")
            elif t in ("pubdate", "updated", "published", "date"):
                rec["date"] = rec["date"] or txt
            elif t in ("description", "summary", "content"):
                rec["summary"] = _TAG.sub(" ", txt)[:400]
        if rec["title"]:
            out.append(rec)
    return out


def match_releases(items: list[dict[str, Any]], ticker: str,
                   issuer_name: str | None = None) -> list[dict[str, Any]]:
    t = ticker.upper().lstrip("$")
    name = (issuer_name or "").lower().strip()
    # strip common corporate suffixes for a looser issuer-name match
    for suf in (" inc", " inc.", " corp", " corp.", " corporation", " ltd", " llc", ", inc."):
        if name.endswith(suf):
            name = name[: -len(suf)].strip()
    matched = []
    for it in items:
        blob = f"{it.get('title','')} {it.get('summary','')}"
        up = blob.upper()
        hit_ticker = bool(re.search(rf"(^|[^A-Z]){re.escape(t)}([^A-Z]|$)", up)) and len(t) >= 3
        hit_name = bool(name) and len(name) >= 4 and name in blob.lower()
        if hit_ticker or hit_name:
            matched.append({**it, "match": "ticker" if hit_ticker else "issuer_name"})
    return matched[:10]


def enforcement_score(matched: list[dict[str, Any]]) -> tuple[float, list[str]]:
    """Modest, gated 0..60 score. Backward-looking context only."""
    if not matched:
        return 0.0, ["no enforcement-history match in recent releases"]
    n = len(matched)
    # ticker matches weigh a bit more than loose issuer-name matches
    strong = sum(1 for m in matched if m.get("match") == "ticker")
    score = min(30 + strong * 15 + (n - strong) * 8, 60)
    basis = [f"{n} recent enforcement release(s) reference this issuer/ticker "
             f"({strong} ticker-match) — BACKWARD-LOOKING context, not current misconduct"]
    basis += [f"· {m.get('title','')[:90]}" for m in matched[:3]]
    return float(score), basis
