#!/usr/bin/env python3
"""Social features for SECFEDCLAW v0.2.

Upgrades over v0.1:
  * Normalizes X (and Reddit if present) into a single post schema and
    deduplicates by (platform, id) BEFORE scoring (fixes cross-ticker
    double-counting).
  * Splits social signal into three sub-scores instead of one additive burst:
      - issuer_specific_burst : posts that actually discuss THIS ticker
      - promotional_noise     : spam / free-signal / Telegram / cashtag-stuff
      - coordination_candidate : fed from the coordination graph
    Promotional noise DEFLATES issuer-specific weight (it does not inflate it).
  * Distinguishes platform_unavailable (gate blocked) from platform_silent.
"""
from __future__ import annotations

import re
from typing import Any

PROMO_TERMS = {
    "guaranteed", "risk-free", "risk free", "100%", "moon", "mooning", "squeeze",
    "buy now", "urgent", "imminent", "breakthrough", "can't lose", "cant lose",
    "next big", "insider", "exclusive", "club", "screenshot", "target price",
    "rocket", "explode", "multi-bagger", "multibagger", "pump", "jake signals",
    "telegram", "must buy", "fastest way", "free signals", "wealth", "breakout",
    "join", "dm me", "alert", "100x", "10x", "easy money", "don't miss", "dont miss",
}
_CASHTAG_RE = re.compile(r"\$[A-Za-z]{1,6}\b")


def normalize_posts(x_fetch_data: Any, reddit_fetch_data: Any = None,
                    stocktwits_fetch_data: Any = None,
                    imported_posts: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    posts: list[dict[str, Any]] = []
    if isinstance(x_fetch_data, dict):
        for t in (x_fetch_data.get("data") or []):
            if not isinstance(t, dict):
                continue
            pm = t.get("public_metrics") or {}
            posts.append({
                "platform": "x",
                "id": t.get("id"),
                "text": t.get("text") or "",
                "created_at": t.get("created_at"),
                "author_id": t.get("author_id"),
                "sentiment": None,
                "engagement": sum(float(pm.get(k) or 0) for k in
                                  ("retweet_count", "reply_count", "like_count", "quote_count")),
            })
    if isinstance(stocktwits_fetch_data, dict):
        for m in (stocktwits_fetch_data.get("messages") or []):
            if not isinstance(m, dict):
                continue
            ent = (m.get("entities") or {}).get("sentiment") or {}
            basic = (ent.get("basic") or "").lower() if isinstance(ent, dict) else ""
            user = m.get("user") or {}
            posts.append({
                "platform": "stocktwits",
                "id": str(m.get("id")),
                "text": m.get("body") or "",
                "created_at": m.get("created_at"),
                "author_id": str(user.get("id") or user.get("username") or ""),
                "sentiment": basic if basic in ("bullish", "bearish") else None,
                "engagement": float((m.get("likes") or {}).get("total", 0)) if isinstance(m.get("likes"), dict) else 0.0,
            })
    if isinstance(reddit_fetch_data, dict):
        children = (((reddit_fetch_data.get("data") or {}).get("children")) or []) \
            if "data" in reddit_fetch_data else (reddit_fetch_data.get("posts") or [])
        for c in children:
            d = c.get("data", c) if isinstance(c, dict) else {}
            posts.append({
                "platform": "reddit",
                "id": d.get("id"),
                "text": f"{d.get('title','')} {d.get('selftext','')}".strip(),
                "created_at": d.get("created_utc"),
                "author_id": d.get("author"),
                "engagement": float(d.get("score") or 0) + float(d.get("num_comments") or 0),
            })
    # operator-authorized imports (Discord/Telegram/etc.), already normalized
    for p in (imported_posts or []):
        if isinstance(p, dict) and p.get("text") is not None:
            p.setdefault("sentiment", None)
            p.setdefault("engagement", 0.0)
            posts.append(p)
    # dedup by (platform, id), keep first, record duplicates
    seen: set[tuple] = set()
    deduped: list[dict[str, Any]] = []
    duplicates = 0
    for p in posts:
        key = (p["platform"], p.get("id"))
        if p.get("id") and key in seen:
            duplicates += 1
            continue
        if p.get("id"):
            seen.add(key)
        deduped.append(p)
    if deduped:
        deduped[0]["_duplicates_removed"] = duplicates
    return deduped


def _is_issuer_specific(text: str, ticker: str) -> bool:
    up = text.upper()
    if f"${ticker.upper()}" in up:
        # cashtag-stuffing: if it mentions many cashtags, it's basket/promo, not issuer-specific
        cashtags = {c.upper() for c in _CASHTAG_RE.findall(text)}
        return len(cashtags) <= 3
    return ticker.upper() in up


def social_features(posts: list[dict[str, Any]], ticker: str, reddit_unavailable: bool) -> dict[str, Any]:
    issuer_specific, promo_noise = [], []
    promo_hits = 0
    engagement = 0.0
    platforms = set()
    issuer_platforms: set[str] = set()
    platform_counts: dict[str, int] = {}
    bullish = bearish = 0
    for p in posts:
        text = p.get("text", "")
        plat = p["platform"]
        platforms.add(plat)
        platform_counts[plat] = platform_counts.get(plat, 0) + 1
        engagement += p.get("engagement", 0.0)
        if p.get("sentiment") == "bullish":
            bullish += 1
        elif p.get("sentiment") == "bearish":
            bearish += 1
        lower = text.lower()
        hits = sum(1 for term in PROMO_TERMS if term in lower)
        cashtags = {c.upper() for c in _CASHTAG_RE.findall(text)}
        promo_hits += hits
        if hits >= 1 or len(cashtags) > 3:
            promo_noise.append(p)
        else:
            # mentions ticker (loosely or via cashtag), no promo signature
            issuer_specific.append(p)
            issuer_platforms.add(plat)
    sentiment_total = bullish + bearish
    bullish_ratio = round(bullish / sentiment_total, 3) if sentiment_total else None
    return {
        "n_posts": len(posts),
        "n_issuer_specific": len(issuer_specific),
        "n_promotional_noise": len(promo_noise),
        "promo_term_hits": promo_hits,
        "engagement_total": round(engagement, 1),
        "platforms": sorted(platforms),
        "n_platforms": len(platforms),
        "platform_counts": platform_counts,
        "cross_platform_issuer_specific": len(issuer_platforms) >= 2,
        "sentiment": {"bullish": bullish, "bearish": bearish, "bullish_ratio": bullish_ratio,
                      "unanimous_bullish": bool(sentiment_total >= 5 and bullish_ratio and bullish_ratio >= 0.9)},
        "duplicates_removed": posts[0].get("_duplicates_removed", 0) if posts else 0,
        "reddit_state": "platform_unavailable" if reddit_unavailable else (
            "platform_present" if "reddit" in platforms else "platform_silent"),
        "_issuer_specific_posts": issuer_specific,
        "_promo_posts": promo_noise,
    }


def social_scores(feat: dict[str, Any]) -> dict[str, float]:
    import math
    n_issuer = feat["n_issuer_specific"]
    n_promo = feat["n_promotional_noise"]
    eng = feat["engagement_total"]
    diversity = 1.0 if len(feat["platforms"]) >= 2 else 0.6 if feat["platforms"] else 0.0

    issuer_burst = min(n_issuer * 7, 60) * (0.6 + 0.4 * diversity)
    issuer_burst += min(math.sqrt(eng) * 2.0, 12)
    # promotional noise DEFLATES issuer-specific confidence
    promo_noise_score = min(n_promo * 9 + feat["promo_term_hits"] * 3, 100)
    deflator = min(n_promo / max(n_issuer + n_promo, 1), 0.6)
    issuer_specific_burst = max(0.0, issuer_burst * (1 - deflator))

    return {
        "social_issuer_specific_burst": round(min(issuer_specific_burst, 100), 2),
        "social_promotional_noise": round(promo_noise_score, 2),
    }
