#!/usr/bin/env python3
"""Coordination / actor-graph features for SECFEDCLAW v0.2.

v0.1 left coordination_score hard-coded at 0.0. This module implements an
explainable coordination graph from public social posts:

  * Near-duplicate text clustering via k-shingle Jaccard similarity.
  * Shared-URL / shared-domain co-occurrence.
  * Burst synchronization (many posts inside a tight time window).
  * Author / handle concentration (HHI) where author ids are available.

These are HIGH-false-positive features by nature (per the design doc), so the
score is conservative and always emitted with the supporting evidence so a
human can verify the clusters. Coordination context never establishes
misconduct on its own.
"""
from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

_URL_RE = re.compile(r"https?://\S+")
_DOMAIN_RE = re.compile(r"https?://([^/\s]+)")
_HANDLE_RE = re.compile(r"@(\w+)")
_TOKEN_RE = re.compile(r"[a-z0-9$]+")


def _norm_tokens(text: str) -> list[str]:
    text = _URL_RE.sub(" ", text.lower())
    return _TOKEN_RE.findall(text)


def _shingles(tokens: list[str], k: int = 3) -> set[str]:
    if len(tokens) < k:
        return {" ".join(tokens)} if tokens else set()
    return {" ".join(tokens[i:i + k]) for i in range(len(tokens) - k + 1)}


def content_fingerprint(text: str) -> str:
    """Stable short hash of a message's normalized 3-shingle SET, so the same
    promotional script recurring across tickers/runs produces the same id even
    under different post ids/handles. Exact-set match (v1); fuzzy MinHash linking
    is a later step. Empty only for empty/whitespace text."""
    sh = sorted(_shingles(_norm_tokens(text)))
    if not sh:
        return ""
    return hashlib.sha1(" | ".join(sh).encode()).hexdigest()[:16]


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def coordination_features(posts: list[dict[str, Any]], dup_threshold: float = 0.6,
                          burst_window_sec: int = 1800) -> dict[str, Any]:
    """posts: list of dicts with keys text, id, created_at(optional), author_id(optional)."""
    out: dict[str, Any] = {
        "n_posts": len(posts),
        "near_duplicate_clusters": [],
        "shared_domain_groups": [],
        "burst_windows": [],
        "author_concentration_hhi": 0.0,
        "evidence": [],
    }
    if len(posts) < 2:
        return out

    texts = [str(p.get("text") or p.get("title") or "") for p in posts]
    shingle_sets = [_shingles(_norm_tokens(t)) for t in texts]

    # --- near-duplicate clustering (greedy union-find by Jaccard) ---
    parent = list(range(len(posts)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        parent[find(a)] = find(b)

    pairs_checked = 0
    for i in range(len(posts)):
        for j in range(i + 1, len(posts)):
            pairs_checked += 1
            if _jaccard(shingle_sets[i], shingle_sets[j]) >= dup_threshold:
                union(i, j)
    clusters: dict[int, list[int]] = defaultdict(list)
    for idx in range(len(posts)):
        clusters[find(idx)].append(idx)
    dup_clusters = [members for members in clusters.values() if len(members) >= 2]
    for members in dup_clusters:
        member_authors = sorted({posts[m].get("author_id") for m in members if posts[m].get("author_id")})
        out["near_duplicate_clusters"].append({
            "size": len(members),
            "post_ids": [posts[m].get("id") for m in members][:20],
            "sample_text": texts[members[0]][:160],
            # Identity fields for cross-run entity resolution (entities.py):
            "author_ids": member_authors[:20],
            "content_fingerprint": content_fingerprint(texts[members[0]]),
        })
    out["max_duplicate_cluster_size"] = max((len(m) for m in dup_clusters), default=0)
    out["duplicate_post_ratio"] = round(
        sum(len(m) for m in dup_clusters) / len(posts), 3) if posts else 0.0

    # --- shared domains ---
    domain_to_posts: dict[str, list[Any]] = defaultdict(list)
    for p, t in zip(posts, texts):
        for dom in set(_DOMAIN_RE.findall(t)):
            domain_to_posts[dom].append(p.get("id"))
    for dom, ids in domain_to_posts.items():
        if len(ids) >= 2:
            out["shared_domain_groups"].append({"domain": dom, "count": len(ids), "post_ids": ids[:20]})

    # --- burst synchronization ---
    times = []
    for p in posts:
        ts = p.get("created_at")
        if ts:
            try:
                times.append(datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp())
            except Exception:
                pass
    times.sort()
    if len(times) >= 3:
        i = 0
        for j in range(len(times)):
            while times[j] - times[i] > burst_window_sec:
                i += 1
            if j - i + 1 >= 3:
                out["burst_windows"].append({
                    "window_sec": burst_window_sec,
                    "posts_in_window": j - i + 1,
                })
        # keep the densest only
        if out["burst_windows"]:
            out["max_posts_in_burst"] = max(b["posts_in_window"] for b in out["burst_windows"])
            out["burst_windows"] = out["burst_windows"][:1]
        else:
            out["max_posts_in_burst"] = 0
    else:
        out["max_posts_in_burst"] = 0

    # --- author concentration ---
    authors = [p.get("author_id") for p in posts if p.get("author_id")]
    if authors:
        counts = list(Counter(authors).values())
        from robust_stats import hhi  # local import to avoid cycle at module load
        out["author_concentration_hhi"] = round(hhi(counts), 3)
        out["unique_authors"] = len(set(authors))

    return out


def coordination_score(feat: dict[str, Any]) -> tuple[float, list[str]]:
    """Conservative 0..100 coordination score with explanation."""
    basis: list[str] = []
    score = 0.0
    dup_ratio = feat.get("duplicate_post_ratio", 0.0)
    max_dup = feat.get("max_duplicate_cluster_size", 0)
    if max_dup >= 2:
        score += min(dup_ratio * 50, 40)
        basis.append(f"near-duplicate posts: max cluster {max_dup}, ratio {dup_ratio}")
    domains = feat.get("shared_domain_groups", [])
    if domains:
        score += min(len(domains) * 10, 25)
        basis.append(f"shared promotional domains across posts: {len(domains)} group(s)")
    burst = feat.get("max_posts_in_burst", 0)
    if burst >= 3:
        score += min(burst * 3, 20)
        basis.append(f"burst synchronization: {burst} posts in a tight window")
    hhi_val = feat.get("author_concentration_hhi", 0.0)
    if hhi_val >= 0.3:
        score += min(hhi_val * 30, 20)
        basis.append(f"author concentration HHI={hhi_val}")
    if not basis:
        basis.append("no coordination pattern detected in available public posts")
    return min(score, 100.0), basis
