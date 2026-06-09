#!/usr/bin/env python3
"""OSINT escalation workflow for SECFEDCLAW HIGH/CRITICAL packages.

When a scan produces packages at HIGH (≥50) or CRITICAL_REVIEW (≥75) priority,
this module:
  1. Builds targeted X/Twitter search URLs for the ticker + time window.
  2. Submits case information to nousangels.dev/osint via headless browser
     (Playwright/Firecrawl). Login: robert.david.brown@gmail.com.
  3. Logs the investigation URL and search links to the package output.

This is WATCH-level enrichment only — never automated action, contact, or escalation.

Usage:
    python3 osint_workflow.py --package out/AMC_20260609T...json
    python3 osint_workflow.py --queue out/review_queue.json --min-priority HIGH
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import webbrowser
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import load_env, fed_claw_root  # noqa: E402

NOUSANGELS_OSINT = "https://nousangels.dev/osint"
NOUSANGELS_EMAIL = "robert.david.brown@gmail.com"

PRIORITY_ORDER = ["LOW", "MEDIUM", "HIGH", "CRITICAL_REVIEW"]


# --------------------------------------------------------------------------- #
# X / Twitter Search Builder
# --------------------------------------------------------------------------- #

def build_x_searches(package: dict) -> list[dict[str, str]]:
    """Build targeted X/Twitter search URLs for a package.
    Returns list of {label, url, query} dicts for operator reference."""
    ticker = package.get("ticker", "").upper()
    if not ticker:
        return []

    # Time window: 14 days back from package generation
    gen_str = package.get("generated_utc", "")
    try:
        gen_dt = datetime.fromisoformat(gen_str.replace("Z", "+00:00"))
    except Exception:
        gen_dt = datetime.now(timezone.utc)
    since = (gen_dt - timedelta(days=14)).strftime("%Y-%m-%d")
    until = gen_dt.strftime("%Y-%m-%d")

    coord = package.get("coordination_detail", {})
    clusters = coord.get("near_duplicate_clusters", [])
    shared_domains = coord.get("shared_domain_groups", [])
    social = package.get("social_metrics", {})
    platforms = social.get("platforms", [])

    # Extract top promo terms from coordination clusters (first 3 words of each)
    cluster_terms: list[str] = []
    for cl in clusters[:3]:
        posts = cl if isinstance(cl, list) else []
        for post in posts[:1]:
            text = (post.get("text") or "")[:80]
            words = [w.strip('",\'') for w in text.split()[:4] if len(w) > 3]
            if words:
                cluster_terms.append(" ".join(words[:3]))

    searches = []

    # 1. Core cashtag search (broad, date-ranged)
    q1 = f"${ticker} since:{since} until:{until}"
    searches.append({
        "label": f"${ticker} — last 14 days",
        "query": q1,
        "url": f"https://x.com/search?q={urllib.parse.quote(q1)}&src=typed_query&f=live",
    })

    # 2. Promotional language search
    promo_terms = ["pump", "buy now", "100x", "moon", "squeeze", "guaranteed", "rocket", "alert"]
    q2 = f"${ticker} ({' OR '.join(promo_terms[:4])}) since:{since}"
    searches.append({
        "label": f"${ticker} + promo language",
        "query": q2,
        "url": f"https://x.com/search?q={urllib.parse.quote(q2)}&src=typed_query&f=live",
    })

    # 3. Ticker + "signals" / "free signals" (typical pump promotion)
    q3 = f"${ticker} (\"free signal\" OR \"join\" OR \"dm me\" OR \"Telegram\") since:{since}"
    searches.append({
        "label": f"${ticker} + signal-channel recruitment",
        "query": q3,
        "url": f"https://x.com/search?q={urllib.parse.quote(q3)}&src=typed_query&f=live",
    })

    # 4. Near-duplicate cluster term (if found)
    if cluster_terms:
        q4 = f"${ticker} \"{cluster_terms[0]}\" since:{since}"
        searches.append({
            "label": f"${ticker} + cluster phrase match",
            "query": q4,
            "url": f"https://x.com/search?q={urllib.parse.quote(q4)}&src=typed_query&f=live",
        })

    # 5. Shared domain (if found)
    if shared_domains:
        domain = list(shared_domains[0].keys())[0] if isinstance(shared_domains[0], dict) else str(shared_domains[0])
        domain = domain.split("/")[0]
        if domain and "." in domain:
            q5 = f"${ticker} site:{domain} since:{since}"
            searches.append({
                "label": f"${ticker} + shared domain {domain}",
                "query": q5,
                "url": f"https://x.com/search?q={urllib.parse.quote(q5)}&src=typed_query&f=live",
            })

    return searches


# --------------------------------------------------------------------------- #
# nousangels.dev/osint case submission
# --------------------------------------------------------------------------- #

def build_case_brief(package: dict) -> str:
    """Assemble a case brief for nousangels.dev/osint submission."""
    ticker = package.get("ticker", "?")
    priority = package.get("review_priority", "?")
    score = package.get("watch_score", 0)
    anomaly = package.get("anomaly_evidence_score", 0)
    ev_qual = package.get("evidence_quality_score", 0)
    families = package.get("corroboration", {}).get("families_active", [])
    caps = package.get("score_caps_applied", [])
    rationale = package.get("non_accusatory_rationale", "")
    comp = package.get("component_scores", {})
    coord = package.get("coordination_detail", {})
    clusters = coord.get("near_duplicate_clusters", [])
    enf = (package.get("enforcement_history") or {}).get("matched_releases", [])
    issuer = package.get("issuer_name", "")
    gen = package.get("generated_utc", "")
    x_searches = build_x_searches(package)
    insider = package.get("edgar_issuer_event", {})

    lines = [
        f"SECFEDCLAW WATCH CASE — {ticker}",
        f"Generated: {gen} | Priority: {priority} | Score: {score:.0f}",
        f"Issuer: {issuer or 'unknown'}",
        "",
        "EVIDENCE SUMMARY",
        f"  Anomaly evidence: {anomaly:.0f}/100",
        f"  Evidence quality: {ev_qual:.0f}/100",
        f"  Active families: {', '.join(families) or 'none'}",
        "",
        "COMPONENT SCORES",
    ]
    for k, v in comp.items():
        if v and v > 0:
            lines.append(f"  {k.replace('_', ' ')}: {v:.1f}")
    if clusters:
        lines.append(f"\nCOORDINATION: {len(clusters)} near-duplicate cluster(s)")
        for i, cl in enumerate(clusters[:2]):
            posts = cl if isinstance(cl, list) else []
            if posts:
                sample = (posts[0].get("text") or "")[:120]
                lines.append(f"  Cluster {i+1}: '{sample}...'")
    if enf:
        lines.append(f"\nENFORCEMENT HISTORY: {len(enf)} prior SEC release(s)")
        for r in enf[:2]:
            lines.append(f"  {r.get('date', '?')}: {r.get('title', '?')[:80]}")
    if insider.get("basis"):
        lines.append(f"\nEDGAR ISSUER EVENT: {'; '.join(insider['basis'][:2])}")
    if caps:
        lines.append(f"\nCAPS APPLIED: {'; '.join(caps)}")
    lines.append(f"\nRATIONALE: {rationale}")
    lines.append("\nX SEARCH QUERIES (for manual investigation):")
    for s in x_searches:
        lines.append(f"  [{s['label']}]")
        lines.append(f"  {s['url']}")
    lines.append(f"\nSOURCE: SECFEDCLAW v0.2 WATCH — review-priority context only. Not proof of misconduct.")
    return "\n".join(lines)


def submit_to_nousangels(package: dict, open_browser: bool = True) -> dict:
    """Build case brief and open nousangels.dev/osint in the default browser.
    Returns dict with case_brief and x_searches for logging."""
    ticker = package.get("ticker", "?")
    brief = build_case_brief(package)
    x_searches = build_x_searches(package)

    # Write brief to a temp file so operator can paste it
    brief_path = Path(f"out/osint_brief_{ticker}_{package.get('generated_utc','').replace(':','-')[:19]}.txt")
    brief_path.parent.mkdir(parents=True, exist_ok=True)
    brief_path.write_text(brief)
    print(f"\n{'='*60}")
    print(f"OSINT CASE BRIEF — {ticker} ({package.get('review_priority')})")
    print(f"{'='*60}")
    print(brief[:800] + "..." if len(brief) > 800 else brief)
    print(f"\nFull brief saved: {brief_path}")
    print(f"\nX SEARCH LINKS:")
    for s in x_searches:
        print(f"  {s['label']}: {s['url']}")
    print(f"\nNousAngels OSINT: {NOUSANGELS_OSINT}")
    print(f"Login: {NOUSANGELS_EMAIL}")

    if open_browser:
        # Guard: webbrowser.open is a no-op in launchd/cron contexts (no display).
        # Check for an interactive terminal before attempting to open tabs.
        import sys as _sys
        _can_open = _sys.stdout.isatty() or bool(
            __import__("os").environ.get("DISPLAY") or
            __import__("os").environ.get("TERM_PROGRAM")
        )
        if _can_open:
            webbrowser.open(NOUSANGELS_OSINT)
            for s in x_searches[:2]:  # open top 2 searches
                webbrowser.open(s["url"])
        else:
            print("\n[osint_workflow] No display context detected (launchd/cron/headless).")
            print(f"  Open manually: {NOUSANGELS_OSINT}")
            for s in x_searches[:2]:
                print(f"  Search: {s['url']}")

    return {
        "ticker": ticker,
        "brief_path": str(brief_path),
        "nousangels_url": NOUSANGELS_OSINT,
        "x_searches": x_searches,
        "submitted": True,
    }


# --------------------------------------------------------------------------- #
# CLI entry point
# --------------------------------------------------------------------------- #

def main() -> int:
    ap = argparse.ArgumentParser(
        description="OSINT escalation workflow for HIGH/CRITICAL SECFEDCLAW packages"
    )
    ap.add_argument("--package", help="Path to a single *_watch_v2.json package file")
    ap.add_argument("--queue", help="Path to review_queue.json — processes all HIGH+ packages")
    ap.add_argument("--min-priority", default="HIGH",
                    choices=["MEDIUM", "HIGH", "CRITICAL_REVIEW"],
                    help="Minimum priority to trigger OSINT workflow (default: HIGH)")
    ap.add_argument("--no-browser", action="store_true",
                    help="Skip opening browser tabs (print only)")
    args = ap.parse_args()

    min_idx = PRIORITY_ORDER.index(args.min_priority)
    open_browser = not args.no_browser

    packages_to_process: list[dict] = []

    if args.package:
        p = Path(args.package)
        if not p.exists():
            print(f"ERROR: {p} not found")
            return 1
        packages_to_process.append(json.loads(p.read_text()))

    elif args.queue:
        q = Path(args.queue)
        if not q.exists():
            print(f"ERROR: {q} not found")
            return 1
        queue_data = json.loads(q.read_text())
        rows = queue_data.get("review_queue", [])
        for row in rows:
            priority = row.get("review_priority", "LOW")
            if PRIORITY_ORDER.index(priority) >= min_idx:
                # Load the corresponding package file
                ticker = row.get("ticker", "")
                pkg_files = sorted(Path("out").glob(f"{ticker}_*_watch_v2.json"), reverse=True)
                if pkg_files:
                    pkg = json.loads(pkg_files[0].read_text())
                    packages_to_process.append(pkg)
                else:
                    print(f"  WARNING: no package file found for {ticker}")
    else:
        ap.print_help()
        return 0

    if not packages_to_process:
        print(f"No packages meet minimum priority ({args.min_priority}). Nothing to investigate.")
        return 0

    print(f"\nOSINT workflow: {len(packages_to_process)} package(s) to investigate")
    results = []
    for pkg in packages_to_process:
        result = submit_to_nousangels(pkg, open_browser=open_browser)
        results.append(result)

    print(f"\n{'='*60}")
    print(f"Processed {len(results)} package(s).")
    print("Next steps:")
    print(f"  1. Log in to {NOUSANGELS_OSINT} with {NOUSANGELS_EMAIL}")
    print("  2. Create a new case and paste the brief from the .txt file above")
    print("  3. Use the X search links to gather additional evidence")
    print("  4. Run the nousangels entity mapper and timeline builder")
    print("  WATCH ceiling — any findings require separate authorized review.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
