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

import json
import os
import re
from typing import Any

from features import coordination as coord

MIN_UNIQUE_AUTHORS = 3          # a "push" needs >= this many distinct accounts
MIN_PLATFORMS = 2               # cross-platform = a cluster spanning >= 2 platforms
MARKET_VERIFY_THRESHOLD = 25.0  # mirrors temporal.corroboration's market-family threshold
MAX_BUMP = 18.0                 # cap on the deterministic coordination_score contribution

# --- Phase 3 (LLM urgency/FOMO node) -------------------------------------------
URGENCY_MAX = 6.0               # cap on the LLM's additional contribution (subordinate)
URGENCY_CATEGORIES = {"fomo", "exit-urgency", "listing-hype", "price-target"}


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


# === Phase 3: LLM urgency/FOMO node ===========================================
# Subordinate to the deterministic signal: the LLM may only AMPLIFY an already
# market-verified coordinated push (never create score), its phrases are
# substring-grounded against the cited posts (ungrounded ones are dropped), and
# its free-text verdict is advisory ONLY — never used in scoring. Off unless
# SECFEDCLAW_SOCIAL_INTEL_LLM=1 (and SECFEDCLAW_SOCIAL_INTEL=1).

def llm_enabled() -> bool:
    return os.environ.get("SECFEDCLAW_SOCIAL_INTEL_LLM", "").strip() in ("1", "true", "yes")


def _default_providers(model: str):
    """OpenRouter then Anthropic, reusing explainer's HTTP callers (lazy import)."""
    import explainer
    return [
        lambda s, u, e, m: explainer._call_openrouter(s, u, e, m),
        lambda s, u, e, m: explainer._call_anthropic(s, u, e, m.split("/")[-1] if "/" in m else m),
    ]


def _build_urgency_messages(cluster_posts: list[dict[str, Any]]) -> tuple[str, str]:
    system = (
        "You are a market-surveillance assistant. Identify ONLY manufactured-urgency / FOMO "
        "language in the posts below (e.g. 'next 100x gem', 'buy before the listing', 'load up "
        "now', 'last chance'). Return STRICT JSON: {\"urgency_signals\":[{\"post_id\":\"..\","
        "\"phrase\":\"<exact substring copied verbatim from that post>\",\"category\":"
        "\"fomo|exit-urgency|listing-hype|price-target\"}],\"verdict\":\"none|possible|likely\"}. "
        "Every phrase MUST be copied verbatim from the cited post. Do NOT accuse anyone, do NOT "
        "give trading advice, do NOT infer fraud. If there is no urgency language, return an empty "
        "list and verdict 'none'."
    )
    posts_json = json.dumps([{"post_id": p.get("id"), "text": (p.get("text") or "")[:400]}
                             for p in cluster_posts])
    return system, "Posts:\n" + posts_json


def _parse_json_obj(text: str) -> dict | None:
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.S)
    try:
        return json.loads(m.group(0)) if m else None
    except Exception:
        return None


def classify_urgency(cluster_posts: list[dict[str, Any]], env: dict | None = None,
                     model: str | None = None, caller=None) -> dict[str, Any]:
    """Call the LLM to extract urgency phrases. `caller` is an injected provider
    callable(system,user,env,model)->{text,model,...} for tests; otherwise the
    real providers are used and the call is cost-tracked via usage.record."""
    model = model or os.environ.get("SECFEDCLAW_LLM_MODEL") or "anthropic/claude-3.5-haiku"
    out = {"signals": [], "verdict": "none", "model": None, "raw_text": "", "prompt": "",
           "error": None, "input_tokens": 0, "output_tokens": 0}
    if not cluster_posts:
        return out
    if env is None and caller is None:
        from config import load_env, fed_claw_root
        env = load_env(fed_claw_root())
    system, user = _build_urgency_messages(cluster_posts)
    out["prompt"] = system + "\n\n" + user
    providers = [caller] if caller else _default_providers(model)
    for prov in providers:
        try:
            res = prov(system, user, env, model)
        except Exception as e:
            out["error"] = f"{type(e).__name__}: {str(e)[:80]}"
            res = None
        if res and res.get("text"):
            out["raw_text"] = res.get("text", "")[:4000]
            out["model"] = res.get("model", model)
            out["input_tokens"] = res.get("input_tokens", 0)
            out["output_tokens"] = res.get("output_tokens", 0)
            obj = _parse_json_obj(res.get("text", ""))
            if obj is not None:
                sig = obj.get("urgency_signals")
                out["signals"] = sig if isinstance(sig, list) else []
                v = str(obj.get("verdict", "none")).lower()
                out["verdict"] = v if v in ("none", "possible", "likely") else "none"
                if caller is None:  # cost-track only the real path (no test-ledger pollution)
                    try:
                        import usage
                        usage.record(out["model"], out["input_tokens"], out["output_tokens"],
                                     component="social_intel_urgency")
                    except Exception:
                        pass
                return out
    return out


def verify_urgency(signals, posts_by_id) -> tuple[list[dict], int]:
    """Keep only signals whose phrase is a verbatim substring of the cited post
    and whose category is known. Returns (verified, n_dropped)."""
    verified, dropped = [], 0
    for s in signals or []:
        pid = s.get("post_id") if isinstance(s, dict) else None
        phrase = (s.get("phrase") or "").strip() if isinstance(s, dict) else ""
        cat = (s.get("category") or "").strip().lower() if isinstance(s, dict) else ""
        post = posts_by_id.get(pid)
        if post and phrase and cat in URGENCY_CATEGORIES and phrase.lower() in (post.get("text") or "").lower():
            verified.append({"post_id": pid, "phrase": phrase[:160], "category": cat})
        else:
            dropped += 1
    return verified, dropped


def attach_urgency(detail: dict[str, Any], posts: list[dict[str, Any]],
                   env: dict | None = None, model: str | None = None, caller=None) -> dict[str, Any]:
    """Run the LLM urgency node over a detected push and attach results to detail.

    The LLM can only AMPLIFY an already-applied (market-verified) push, capped at
    URGENCY_MAX; the verdict is recorded but never scored; full I/O is persisted.
    """
    posts_by_id = {p.get("id"): p for p in posts if p.get("id") is not None}
    ids: list = []
    for cl in detail.get("cross_platform_clusters", []):
        for pid in cl.get("post_ids", []):
            if pid in posts_by_id and pid not in ids:
                ids.append(pid)
    cluster_posts = [posts_by_id[i] for i in ids]

    raw = classify_urgency(cluster_posts, env=env, model=model, caller=caller)
    verified, dropped = verify_urgency(raw["signals"], posts_by_id)
    cited = {v["post_id"] for v in verified}
    urgency_ratio = round(min(1.0, len(cited) / max(1, len(cluster_posts))), 3)
    # Subordinate: only amplify an already market-verified push; never create score.
    urgency_bump = round(min(URGENCY_MAX, URGENCY_MAX * urgency_ratio), 2) if detail.get("applied") else 0.0
    if urgency_bump > 0:
        detail["coordination_bump"] = round(min(detail["coordination_bump"] + urgency_bump,
                                                 MAX_BUMP + URGENCY_MAX), 2)
        detail["basis"] += (f"; LLM-verified urgency in {len(cited)} post(s) "
                            f"(+{urgency_bump}, ratio {urgency_ratio})")
    detail["llm"] = {
        "model": raw["model"],
        "verdict": raw["verdict"],            # advisory only — NEVER used in scoring
        "n_signals_raw": len(raw["signals"]),
        "n_signals_verified": len(verified),
        "n_dropped": dropped,
        "urgency_ratio": urgency_ratio,
        "urgency_bump": urgency_bump,
        "verified_signals": verified,
        "prompt": raw["prompt"][:4000],       # full I/O persisted as recorded evidence
        "response": raw["raw_text"],
        "error": raw["error"],
    }
    return detail
