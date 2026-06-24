#!/usr/bin/env python3
"""LLM-backed explanation agent for SECFEDCLAW v0.2.

Writes a short, plain-language WATCH review narrative for a scored package —
grounded ONLY in the package's own evidence — to speed human triage. It is:

  * connection-aware: calls an LLM (OpenRouter or Anthropic, key from .env) when
    reachable AND opted in (SECFEDCLAW_LLM_EXPLAIN=1); otherwise produces a
    deterministic template narrative. Offline, it always returns the template.
  * cost-tracked: every LLM call is recorded via usage.record(...) so the
    dashboard LLM-cost tab reflects real spend.
  * guardrailed: the prompt forbids fraud/accusation/trading language, and a
    post-check REJECTS any model output that drifts into it, falling back to the
    safe template. Every narrative ends with the WATCH disclaimer.

It never introduces facts beyond the package, never concludes wrongdoing, and is
never a trading recommendation.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import load_env, fed_claw_root  # noqa: E402
import usage  # noqa: E402

DISCLAIMER = ("WATCH-level review priority only — not a determination of wrongdoing, "
              "manipulation, or a trading recommendation. Verify cited artifacts before any escalation.")

# Post-check: reject LLM output containing accusation / trading / guarantee language.
_FORBIDDEN = [
    r"\bfraud(ulent)?\b", r"\bguilty\b", r"\bscam\b", r"\bmanipulat(ed|ion)\b",
    r"\bpump[- ]and[- ]dump\b", r"\bguarantee", r"\b(buy|sell|short)\s+(now|the\s+stock|shares|it)\b",
    r"\b(i|we)\s+recommend\b", r"\byou\s+should\s+(buy|sell|invest|trade)\b", r"\bprice\s+target\b",
]
_FORBIDDEN_RE = [re.compile(p, re.I) for p in _FORBIDDEN]


def _facts(package: dict[str, Any]) -> dict[str, Any]:
    cs = package.get("component_scores", {})
    corr = package.get("corroboration", {})
    sc = package.get("security_class", {})
    enf = package.get("enforcement_history", {})
    return {
        "ticker": package.get("ticker"),
        "review_priority": package.get("review_priority"),
        "watch_score": package.get("watch_score"),
        "anomaly_evidence_score": package.get("anomaly_evidence_score"),
        "evidence_quality_score": package.get("evidence_quality_score"),
        "liquidity_class": sc.get("class"),
        "families_active": corr.get("families_active", []),
        "component_scores": {k: v for k, v in cs.items() if v},
        "caps_applied": package.get("score_caps_applied", []),
        "benign_indicators": (package.get("benign_explanation_review") or {}).get("indicators", [])[:3],
        "enforcement_matches": len(enf.get("matched_releases", [])),
        "evidence_gaps": package.get("evidence_gaps", []),
        "data_mode": package.get("data_mode"),
    }


def template_explain(package: dict[str, Any]) -> str:
    f = _facts(package)
    fams = ", ".join(f["families_active"]) or "no corroborating families"
    top = sorted(f["component_scores"].items(), key=lambda kv: -kv[1])[:3]
    top_str = "; ".join(f"{k.replace('_',' ')} {v:.0f}" for k, v in top) or "no material component signal"
    parts = [
        f"{f['ticker']} is assigned {f['review_priority']} review priority "
        f"(watch score {f['watch_score']:.0f}, anomaly-evidence {f['anomaly_evidence_score']:.0f}, "
        f"evidence-quality {f['evidence_quality_score']:.0f}; {f['liquidity_class']} class).",
        f"Active families: {fams}. Top signals: {top_str}.",
    ]
    if f["enforcement_matches"]:
        parts.append(f"{f['enforcement_matches']} prior SEC enforcement release(s) reference this issuer "
                     "(backward-looking context, not current proof).")
    if f["caps_applied"]:
        parts.append(f"Caps applied: {'; '.join(f['caps_applied'])}.")
    if f["benign_indicators"]:
        parts.append("Benign checks: " + " ".join(f["benign_indicators"][:2]))
    if f["evidence_gaps"]:
        parts.append("Evidence gaps: " + "; ".join(f["evidence_gaps"][:2]) + ".")
    parts.append(DISCLAIMER)
    return " ".join(parts)


def _build_messages(package: dict[str, Any]) -> tuple[str, str]:
    system = (
        "You are a securities-surveillance review assistant. Write a concise (3-5 sentence) "
        "plain-language summary of a WATCH-level review package to help a human reviewer triage. "
        "STRICT RULES: use ONLY the facts provided; introduce no new facts; do NOT conclude fraud, "
        "manipulation, or wrongdoing; do NOT give buy/sell/short/hold or any trading advice; frame "
        "everything as review priority and open questions; note benign explanations and evidence gaps. "
        "End with the exact sentence provided as the disclaimer.")
    user = ("Summarize this WATCH review package for a human reviewer.\n\n"
            f"FACTS (JSON):\n{json.dumps(_facts(package), indent=2, default=str)}\n\n"
            f"Required closing sentence (verbatim): {DISCLAIMER}")
    return system, user


def _call_openrouter(system: str, user: str, env: dict, model: str, timeout: int = 30):
    key = env.get("OPENROUTER_API_KEY")
    if not key:
        return None
    body = json.dumps({"model": model, "max_tokens": 320, "temperature": 0.2,
                       "messages": [{"role": "system", "content": system},
                                    {"role": "user", "content": user}]}).encode()
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=body,
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                                          "X-Title": "SECFEDCLAW"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read())
    text = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
    u = data.get("usage") or {}
    return {"text": text, "model": model, "input_tokens": u.get("prompt_tokens", 0),
            "output_tokens": u.get("completion_tokens", 0)}


def _call_anthropic(system: str, user: str, env: dict, model: str, timeout: int = 30):
    key = env.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    body = json.dumps({"model": model, "max_tokens": 320, "system": system,
                       "messages": [{"role": "user", "content": user}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body,
                                 headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read())
    text = "".join(b.get("text", "") for b in (data.get("content") or []) if isinstance(b, dict)).strip()
    u = data.get("usage") or {}
    return {"text": text, "model": model, "input_tokens": u.get("input_tokens", 0),
            "output_tokens": u.get("output_tokens", 0)}


def _call_bedrock(system: str, user: str, env: dict, model: str, timeout: int = 30):
    """AWS Bedrock via boto3 (no API key — boto3 resolves creds from the standard
    chain: instance role on EC2, SSO, or env). Only fires for a 'bedrock/<id>'
    model; returns None otherwise or if boto3/Bedrock is unavailable, so it slots
    harmlessly into the provider chain alongside OpenRouter/Anthropic."""
    if not model.lower().startswith(("bedrock/", "bedrock_converse/")):
        return None
    try:
        import boto3
    except Exception:
        return None
    model_id = model.split("/", 1)[1]
    region = env.get("AWS_REGION") or env.get("AWS_DEFAULT_REGION")
    try:
        client = boto3.client("bedrock-runtime", region_name=region) if region else boto3.client("bedrock-runtime")
        resp = client.converse(
            modelId=model_id,
            system=[{"text": system}],
            messages=[{"role": "user", "content": [{"text": user}]}],
            inferenceConfig={"maxTokens": 320, "temperature": 0.2},
        )
    except Exception:
        return None
    blocks = (((resp.get("output") or {}).get("message") or {}).get("content")) or []
    text = "".join(b.get("text", "") for b in blocks if isinstance(b, dict)).strip()
    u = resp.get("usage") or {}
    return {"text": text, "model": model_id, "input_tokens": u.get("inputTokens", 0),
            "output_tokens": u.get("outputTokens", 0)}


def _passes_guardrail(text: str) -> bool:
    if not text or len(text) < 40:
        return False
    # The trusted disclaimer legitimately contains "manipulation"/"wrongdoing";
    # exclude it before scanning the model's own prose.
    scan = text.replace(DISCLAIMER, " ")
    return not any(rx.search(scan) for rx in _FORBIDDEN_RE)


def llm_enabled() -> bool:
    return os.environ.get("SECFEDCLAW_LLM_EXPLAIN", "").strip() in ("1", "true", "yes")


def explain(package: dict[str, Any], env: dict | None = None, prefer_llm: bool | None = None,
            caller=None) -> dict[str, Any]:
    """Return {text, source, model?}. Records usage when an LLM call is used.

    `caller` is an optional injected provider callable(system,user,env,model) for
    tests; otherwise OpenRouter then Anthropic are tried (when opted in).
    """
    env = env if env is not None else load_env(fed_claw_root())
    use_llm = llm_enabled() if prefer_llm is None else prefer_llm
    if use_llm:
        system, user = _build_messages(package)
        model = os.environ.get("SECFEDCLAW_LLM_MODEL") or "anthropic/claude-3.5-haiku"
        providers = [caller] if caller else [
            lambda s, u, e, m: _call_bedrock(s, u, e, m),   # fires only for bedrock/* models
            lambda s, u, e, m: _call_openrouter(s, u, e, m),
            lambda s, u, e, m: _call_anthropic(s, u, e, m.split("/")[-1] if "/" in m else m),
        ]
        for prov in providers:
            try:
                res = prov(system, user, env, model)
            except Exception:
                res = None
            if res and _passes_guardrail(res.get("text", "")):
                txt = res["text"].strip()
                if DISCLAIMER not in txt:
                    txt = txt + " " + DISCLAIMER
                usage.record(res.get("model", model), res.get("input_tokens", 0),
                             res.get("output_tokens", 0), component="explainer",
                             meta={"ticker": package.get("ticker")})
                return {"text": txt, "source": "llm", "model": res.get("model", model)}
    # offline / not opted in / guardrail-rejected -> safe template
    return {"text": template_explain(package), "source": "template", "model": None}
