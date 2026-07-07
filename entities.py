#!/usr/bin/env python3
"""Cross-run entity resolution for SECFEDCLAW.

Pump-and-dump detection hinges on recognizing that the SAME actors — promoter
accounts, domains, issuers, and above all recurring promotional *scripts* —
reappear ACROSS tickers, platforms, and time. The per-run coordination features
find within-ticker structure; this module makes identity persist BETWEEN runs so
"this promoter cluster has appeared on N tickers over M weeks" becomes answerable.

Design (deliberately simple, mirrors ledger.py):
  * out/entities/observations.jsonl — append-only log, one row per
    (entity, ticker, run). Lock-guarded; idempotent (re-observing a package adds
    nothing new). This is the single source of truth.
  * Entities are AGGREGATED on read (no separate mutable store to race on).

Entity types + identity keys:
  content_cluster : the near-duplicate cluster's content_fingerprint (same script)
  domain          : registrable domain (www. stripped, lowercased)
  account         : a promoter author_id seen in a coordinated cluster
  issuer          : SEC CIK

WATCH posture: recurrence is backward-looking context for human review, never
proof of misconduct — same discipline as the enforcement-history family.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

HERE = Path(__file__).resolve().parent
OBS_PATH = HERE / "out" / "entities" / "observations.jsonl"
_APPEND_LOCK = threading.Lock()  # serialize appends under the threaded server

TYPES = ("content_cluster", "domain", "account", "issuer")

# Ubiquitous platform / link-shortener / data domains are NOT promoter
# infrastructure — they'd recur across every ticker and drown the real signal.
# Excluded from `domain` entities (a shared *promoter* domain is the signal).
_GENERIC_DOMAINS = {
    "x.com", "twitter.com", "t.co", "reddit.com", "redd.it", "youtube.com",
    "youtu.be", "stockanalysis.com", "finance.yahoo.com", "google.com",
    "bit.ly", "stocktwits.com", "facebook.com", "instagram.com", "t.me",
    "discord.com", "discord.gg", "sec.gov", "finra.org", "nasdaq.com",
    "marketwatch.com", "bloomberg.com", "seekingalpha.com", "benzinga.com",
}


def entity_id(etype: str, key: str) -> str:
    return hashlib.sha1(f"{etype}|{key}".encode()).hexdigest()[:16]


def _norm_domain(dom: str) -> str:
    dom = (dom or "").strip().lower()
    dom = re.sub(r"^https?://", "", dom).split("/")[0]
    return dom[4:] if dom.startswith("www.") else dom


def observations_for(package: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract entity observations from ONE package (no IO). One row per distinct
    entity seen on this ticker in this run."""
    ticker = package.get("ticker")
    run = package.get("source_run_id") or package.get("generated_utc") or ""
    ts = package.get("generated_utc") or run
    if not ticker:
        return []
    cd = package.get("coordination_detail") or {}
    seen: dict[str, dict[str, Any]] = {}

    def add(etype: str, key: str, label: str, evidence: str):
        if not key:
            return
        eid = entity_id(etype, key)
        seen.setdefault(eid, {"entity_id": eid, "type": etype, "key": key,
                              "label": label[:160], "ticker": ticker, "run": run,
                              "ts": ts, "evidence": evidence})

    for c in (cd.get("near_duplicate_clusters") or []):
        add("content_cluster", c.get("content_fingerprint", ""),
            c.get("sample_text", ""), f"cluster size {c.get('size')}")
        for a in (c.get("author_ids") or []):
            add("account", str(a), str(a), "coordinated cluster author")
    for g in (cd.get("shared_domain_groups") or []):
        d = _norm_domain(g.get("domain", ""))
        if d and d not in _GENERIC_DOMAINS:   # only genuine promoter domains
            add("domain", d, d, f"shared across {g.get('count')} posts")
    cik = package.get("issuer_cik")
    if cik:
        add("issuer", str(cik), package.get("issuer_name") or str(cik), "issuer (CIK)")
    return list(seen.values())


def _load_seen(path: Path) -> set[tuple[str, str, str]]:
    if not path.exists():
        return set()
    out: set[tuple[str, str, str]] = set()
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
            out.add((r["entity_id"], r.get("ticker", ""), r.get("run", "")))
        except Exception:
            pass
    return out


def observe(packages: Iterable[dict[str, Any]], path: Path | None = None) -> int:
    """Append observations for the given packages; idempotent on
    (entity, ticker, run). Returns the number of NEW rows written."""
    p = path or OBS_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    with _APPEND_LOCK:
        seen = _load_seen(p)
        new_rows = []
        for pkg in packages:
            for obs in observations_for(pkg):
                key = (obs["entity_id"], obs["ticker"], obs["run"])
                if key in seen:
                    continue
                seen.add(key)
                new_rows.append(obs)
        if new_rows:
            with p.open("a") as f:
                for r in new_rows:
                    f.write(json.dumps(r, default=str) + "\n")
    return len(new_rows)


def _load_packages(out_dir: Path) -> list[dict[str, Any]]:
    pkgs = []
    for f in sorted(out_dir.glob("*_watch_v2.json")):
        try:
            pkgs.append(json.loads(f.read_text()))
        except Exception:
            pass
    return pkgs


def observe_dir(out_dir: Path | str, path: Path | None = None) -> int:
    """Observe every package written under out_dir (idempotent)."""
    return observe(_load_packages(Path(out_dir)), path=path)


def aggregate(path: Path | None = None) -> dict[str, dict[str, Any]]:
    """Fold the observation log into per-entity aggregates (computed on read)."""
    p = path or OBS_PATH
    ents: dict[str, dict[str, Any]] = {}
    if not p.exists():
        return ents
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        e = ents.setdefault(r["entity_id"], {
            "entity_id": r["entity_id"], "type": r["type"], "key": r["key"],
            "label": r.get("label", r["key"]), "tickers": set(), "runs": set(),
            "first_seen": r.get("ts", ""), "last_seen": r.get("ts", ""), "n_obs": 0})
        e["tickers"].add(r.get("ticker", ""))
        e["runs"].add(r.get("run", ""))
        e["n_obs"] += 1
        ts = r.get("ts", "")
        if ts and (not e["first_seen"] or ts < e["first_seen"]):
            e["first_seen"] = ts
        if ts and ts > e["last_seen"]:
            e["last_seen"] = ts
    return ents


def _span_days(first: str, last: str) -> int:
    try:
        f = datetime.fromisoformat(first.replace("Z", "+00:00"))
        l = datetime.fromisoformat(last.replace("Z", "+00:00"))
        return max(0, (l - f).days)
    except Exception:
        return 0


def recurring(min_tickers: int = 2, path: Path | None = None) -> list[dict[str, Any]]:
    """Entities seen on >= min_tickers distinct tickers, richest first — the
    'same actor across the watch' list that powers the Entities tab."""
    rows = []
    for e in aggregate(path).values():
        tickers = sorted(t for t in e["tickers"] if t)
        if len(tickers) < min_tickers:
            continue
        rows.append({
            "entity_id": e["entity_id"], "type": e["type"], "key": e["key"],
            "label": e["label"], "n_tickers": len(tickers), "tickers": tickers,
            "n_runs": len([r for r in e["runs"] if r]), "n_obs": e["n_obs"],
            "first_seen": e["first_seen"], "last_seen": e["last_seen"],
            "span_days": _span_days(e["first_seen"], e["last_seen"]),
        })
    rows.sort(key=lambda r: (r["n_tickers"], r["n_obs"]), reverse=True)
    return rows


def recurrence_for_package(package: dict[str, Any], path: Path | None = None) -> list[dict[str, Any]]:
    """For each entity in this package, its cross-ticker footprint EXCLUDING the
    current ticker — powers the per-package 'also seen on X, Y' cross-links."""
    agg = aggregate(path)
    ticker = package.get("ticker")
    out = []
    for obs in observations_for(package):
        e = agg.get(obs["entity_id"])
        if not e:
            continue
        others = sorted(t for t in e["tickers"] if t and t != ticker)
        if not others:
            continue
        out.append({"type": obs["type"], "key": obs["key"], "label": obs["label"],
                    "also_seen_on": others, "n_tickers": len(e["tickers"]),
                    "span_days": _span_days(e["first_seen"], e["last_seen"])})
    out.sort(key=lambda r: r["n_tickers"], reverse=True)
    return out


def summary(path: Path | None = None) -> dict[str, Any]:
    agg = aggregate(path)
    by_type = {t: 0 for t in TYPES}
    recurring_ct = 0
    for e in agg.values():
        by_type[e["type"]] = by_type.get(e["type"], 0) + 1
        if len([t for t in e["tickers"] if t]) >= 2:
            recurring_ct += 1
    return {"n_entities": len(agg), "by_type": by_type,
            "n_recurring": recurring_ct}


def main() -> int:
    ap = argparse.ArgumentParser(description="SECFEDCLAW cross-run entity resolution")
    ap.add_argument("--rebuild", action="store_true",
                    help="(idempotently) observe every package in out/ so the graph has history")
    ap.add_argument("--out", default=str(HERE / "out"), help="output dir holding *_watch_v2.json")
    ap.add_argument("--min-tickers", type=int, default=2)
    args = ap.parse_args()
    if args.rebuild:
        n = observe_dir(args.out)
        print(f"observed {n} new (entity, ticker, run) rows from {args.out}")
    s = summary()
    print(json.dumps(s, indent=2))
    top = recurring(min_tickers=args.min_tickers)
    print(f"\nTop recurring entities (>= {args.min_tickers} tickers): {len(top)}")
    for r in top[:15]:
        print(f"  [{r['type']:<15}] {r['label'][:48]:<48} {r['n_tickers']} tickers / "
              f"{r['span_days']}d  {', '.join(r['tickers'][:6])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
