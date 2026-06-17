#!/usr/bin/env python3
"""Phase 2 deterministic social intelligence: cross-platform coordinated-push
detection over already-normalized posts, gated against a real market move.

NO LLM here — that is Phase 3. Off by default; enabled with
``SECFEDCLAW_SOCIAL_INTEL=1``. The output is a bounded, cited feature that feeds
ONLY ``coordination_score``; it never lights an independent concern-family (the
G3 quarantine). So a social-only coordinated push still cannot reach HIGH
without independent market/issuer corroboration — and the boost is only applied
when the push aligns with a confirmed market move (the same threshold that lights
the market family on its own), which keeps the signal honest and reproducible.

Reuses the existing k-shingle Jaccard clustering in ``coordination`` and just
annotates clusters with platform spread + distinct-author counts.
"""
from __future__ import annotations

import os
from typing import Any

from features import coordination as coord

MIN_UNIQUE_AUTHORS = 3          # a "push" needs >= this many distinct accounts
MIN_PLATFORMS = 2               # cross-platform = a cluster spanning >= 2 platforms
MARKET_VERIFY_THRESHOLD = 25.0  # mirrors temporal.corroboration's market-family threshold
MAX_BUMP = 18.0                 # cap on the coordination_score contribution


def enabled() -> bool:
    """True only when the operator opts in via SECFEDCLAW_SOCIAL_INTEL=1."""
    return os.environ.get("SECFEDCLAW_SOCIAL_INTEL") == "1"


def coordination_intel(posts: list[dict[str, Any]],
                       market_anomaly_score: float = 0.0) -> dict[str, Any]:
    """Detect cross-platform near-duplicate pushes by many distinct accounts.

    Returns bounded features + cited evidence. ``applied`` is True (and
    ``coordination_bump`` > 0) only when a coordinated push is BOTH present and
    aligned with a confirmed market move.
    """
    out: dict[str, Any] = {
        "enabled": True,
        "cross_platform_clusters": [],
        "n_cross_platform_clusters": 0,
        "max_unique_authors": 0,
        "coordinated_push": False,
        "market_verified": float(market_anomaly_score or 0.0) >= MARKET_VERIFY_THRESHOLD,
        "coordination_bump": 0.0,
        "applied": False,
        "basis": "",
        "evidence": [],
    }
    if not posts:
        return out

    feat = coord.coordination_features(posts)
    by_id = {p.get("id"): p for p in posts if p.get("id") is not None}
    for cl in feat.get("near_duplicate_clusters", []):
        members = [by_id[i] for i in cl.get("post_ids", []) if i in by_id]
        platforms = sorted({p.get("platform") for p in members if p.get("platform")})
        authors = {p.get("author_id") for p in members if p.get("author_id")}
        if len(platforms) >= MIN_PLATFORMS:
            out["cross_platform_clusters"].append({
                "platforms": platforms,
                "n_unique_authors": len(authors),
                "n_posts": cl.get("size", len(members)),
                "post_ids": cl.get("post_ids", [])[:20],
                "sample_text": cl.get("sample_text", ""),
            })
            out["max_unique_authors"] = max(out["max_unique_authors"], len(authors))

    out["n_cross_platform_clusters"] = len(out["cross_platform_clusters"])
    out["coordinated_push"] = (out["n_cross_platform_clusters"] >= 1
                               and out["max_unique_authors"] >= MIN_UNIQUE_AUTHORS)

    if out["coordinated_push"] and out["market_verified"]:
        bump = min(6.0 + 3.0 * (out["max_unique_authors"] - MIN_UNIQUE_AUTHORS), MAX_BUMP)
        out["coordination_bump"] = round(bump, 2)
        out["applied"] = True
        out["evidence"] = [pid for cl in out["cross_platform_clusters"]
                           for pid in cl["post_ids"]][:40]
        out["basis"] = (
            f"cross-platform coordinated push: {out['n_cross_platform_clusters']} cluster(s) "
            f"spanning >={MIN_PLATFORMS} platforms, up to {out['max_unique_authors']} distinct "
            f"accounts, aligned with a confirmed market move "
            f"(anomaly={round(float(market_anomaly_score), 1)})")
    return out
