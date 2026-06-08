#!/usr/bin/env python3
"""SECFEDCLAW WATCH scoring engine v0.2.

Composes the v0.2 feature families into a non-accusatory review-priority
package. Key changes vs v0.1:

  1. Concern-bearing anomaly evidence is the scored quantity; source
     availability / reviewability (evidence_quality) is a GATE, not an
     additive term. This removes the "routine large-cap floats at MEDIUM"
     artifact the algorithms agent flagged in 9/9 AAPL runs.
  2. Cross-source temporal corroboration multiplier gates escalation:
     HIGH/CRITICAL requires >= 2 independent active families.
  3. Real coordination score (no longer a 0.0 placeholder).
  4. Promotional noise deflates rather than inflates social.
  5. Robust rolling + cross-sectional market anomaly with double confirmation.

Output remains LOW / MEDIUM / HIGH / CRITICAL_REVIEW review priority only.
Never a trading signal, never proof of misconduct.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "features"))

from config import ALGORITHM_VERSION, FINDING_CEILING, PROHIBITED_ACTIONS  # noqa: E402
import robust_stats as rs  # noqa: E402
from features import market as mkt  # noqa: E402
from features import social as soc  # noqa: E402
from features import coordination as coord  # noqa: E402
from features import official as off  # noqa: E402
from features import temporal as temporal  # noqa: E402
from features import edgar as edgar_feat  # noqa: E402
from features import security_class as secclass  # noqa: E402
from features import enforcement as enf  # noqa: E402
import social_import  # noqa: E402
import model as gbm_model  # noqa: E402

def score_to_priority(score: float) -> str:
    if score >= 75:
        return "CRITICAL_REVIEW"
    if score >= 50:
        return "HIGH"
    if score >= 25:
        return "MEDIUM"
    return "LOW"


def _band_down(priority: str) -> str:
    order = ["LOW", "MEDIUM", "HIGH", "CRITICAL_REVIEW"]
    i = order.index(priority)
    return order[max(0, i - 1)]


def evidence_quality(bundle: dict[str, Any]) -> tuple[float, list[str]]:
    """Reviewability: how complete/fresh/independent is the evidence."""
    gaps: list[str] = []
    families = 0
    for k in ("market", "social", "official"):
        if bundle.get(k, {}).get("present"):
            families += 1
    artifacts = bundle.get("n_artifacts", 0)
    score = min(families * 18, 54) + min(artifacts * 6, 36)
    if bundle.get("reddit_unavailable"):
        gaps.append("reddit social platform unavailable (single-platform social corroboration)")
        score -= 8
    if not bundle.get("market", {}).get("rolling_available"):
        gaps.append("rolling daily baseline unavailable; using cross-sectional/limited history")
    return rs.squash(max(score, 0), scale=70, cap=100) if score > 100 else max(0.0, min(score, 100.0)), gaps


def build_package(ticker: str, fetches: dict[str, Any]) -> dict[str, Any]:
    ticker = ticker.upper().lstrip("$")

    # ---- market ----
    ts = mkt.time_series_anomaly(fetches["daily_range"].data if fetches.get("daily_range") else None)
    xs = mkt.cross_sectional_anomaly(fetches["grouped"].data if fetches.get("grouped") else None, ticker)
    micro = mkt.microstructure(
        fetches["snapshot"].data if fetches.get("snapshot") else None,
        fetches["trades"].data if fetches.get("trades") else None,
        fetches["quotes"].data if fetches.get("quotes") else None,
    )
    # Per-security-class calibration (thresholds differ by liquidity class).
    price = ts.get("last_close")
    dollar_volume = (xs.get("dollar_volume") if xs.get("available") else None) or ts.get("last_dollar_volume")
    cls = secclass.classify(price, dollar_volume)
    sec_cls = {"class": cls, **secclass.params(cls), "price": price, "dollar_volume": dollar_volume}
    market_anomaly, market_detail = mkt.market_anomaly_score(ts, xs, micro, z_confirm=sec_cls["z_confirm"])

    # ---- social ----
    reddit_unavailable = bool(fetches.get("reddit_unavailable", True))
    posts = soc.normalize_posts(
        fetches["x"].data if fetches.get("x") else None,
        fetches["reddit"].data if fetches.get("reddit") else None,
        fetches["stocktwits"].data if fetches.get("stocktwits") else None,
        discord_fetch_data=fetches["discord"].data if fetches.get("discord") else None,
        instagram_fetch_data=fetches["instagram"].data if fetches.get("instagram") else None,
        facebook_fetch_data=fetches["facebook"].data if fetches.get("facebook") else None,
        imported_posts=(fetches.get("social_import")
                        if isinstance(fetches.get("social_import"), list)
                        else social_import.load_authorized(ticker)),
    )
    social_feat = soc.social_features(posts, ticker, reddit_unavailable)
    social_scores = soc.social_scores(social_feat)

    # ---- coordination ----
    coord_feat = coord.coordination_features(posts)
    coordination_score, coord_basis = coord.coordination_score(coord_feat)
    # Sentiment mania: unanimous-bullish StockTwits + promotional language is a
    # recognized coordination/hype tell; nudge coordination (capped, explained).
    if social_feat.get("sentiment", {}).get("unanimous_bullish") and social_feat["n_promotional_noise"] >= 2:
        coordination_score = min(coordination_score + 12, 100.0)
        coord_basis.append(
            f"unanimous bullish sentiment ({social_feat['sentiment']['bullish_ratio']}) + promotional posts")

    # ---- official ----
    ctx = off.official_context(
        ticker,
        fetches["otc_threshold"].data if fetches.get("otc_threshold") else None,
        fetches["reg_sho"].data if fetches.get("reg_sho") else None,
        fetches["halts"].data if fetches.get("halts") else None,
        fetches["submissions"].data if fetches.get("submissions") else None,
    )
    off_scores = off.official_scores(ctx)

    # ---- SEC enforcement-history (backward-looking context, family E) ----
    lit_fetch = fetches.get("litigation")
    lit_items = enf.parse_releases(lit_fetch.data) if (lit_fetch and getattr(lit_fetch, "data", None) and isinstance(lit_fetch.data, str)) else []
    enf_matched = enf.match_releases(lit_items, ticker, ctx.get("issuer_name")) if lit_items else []
    enforcement_score_val, enforcement_basis = enf.enforcement_score(enf_matched)

    # ---- EDGAR issuer-event signal (concern-bearing) ----
    edgar_fetch = fetches.get("edgar")
    edgar_payload = edgar_fetch.data if (edgar_fetch and hasattr(edgar_fetch, "data")) else None
    edgar_features = edgar_payload.get("features") if isinstance(edgar_payload, dict) else None
    issuer_event_val, issuer_event_basis = edgar_feat.issuer_event_score(edgar_features or {})

    component_scores = {
        "social_issuer_specific_burst": round(min(
            social_scores["social_issuer_specific_burst"] * sec_cls["social_weight"], 100), 2),
        "social_promotional_noise": social_scores["social_promotional_noise"],
        "market_anomaly_score": round(market_anomaly, 2),
        "market_structure_score": off_scores["market_structure_score"],
        "issuer_context_score": off_scores["issuer_context_score"],
        "halt_regulatory_score": off_scores["halt_regulatory_score"],
        "coordination_score": round(coordination_score, 2),
        "issuer_event_score": round(issuer_event_val, 2),
        "enforcement_history_score": round(enforcement_score_val, 2),
    }

    # ---- concern-bearing anomaly evidence (separate from reviewability) ----
    # This is the scored ANCHOR: a weighted blend of only the concern-bearing
    # families (weights sum to 1.0 so a single maxed family can still register
    # meaningful concern instead of being averaged toward zero).
    anomaly_evidence = round(min(
        0.34 * component_scores["market_anomaly_score"] +
        0.20 * component_scores["coordination_score"] +
        0.14 * component_scores["market_structure_score"] +
        0.14 * component_scores["issuer_event_score"] +
        0.10 * component_scores["halt_regulatory_score"] +
        0.08 * component_scores["social_issuer_specific_burst"], 100), 2)

    # ---- corroboration ----
    corr = temporal.corroboration(component_scores, social_feat)

    # ---- composite: anchor on anomaly evidence, gate by corroboration, then
    # add a small issuer-context bonus. Avoids both v0.1's routine-context
    # floor AND a pure weighted-average that dilutes a strong single family.
    issuer_bonus = min(0.12 * component_scores["issuer_context_score"], 12.0)
    # Enforcement history is backward-looking: a small attention bonus only.
    enforcement_bonus = min(0.10 * enforcement_score_val, 8.0)
    raw = round(min(anomaly_evidence * corr["corroboration_multiplier"] + issuer_bonus + enforcement_bonus, 100.0), 2)

    # ---- evidence quality (reviewability gate) ----
    n_artifacts = sum(1 for f in fetches.values() if hasattr(f, "ok") and f.ok())
    eq_bundle = {
        "market": {"present": ts.get("available") or xs.get("available"),
                   "rolling_available": ts.get("available")},
        "social": {"present": bool(posts)},
        "official": {"present": bool(ctx.get("families"))},
        "n_artifacts": n_artifacts,
        "reddit_unavailable": reddit_unavailable,
    }
    ev_quality, ev_gaps = evidence_quality(eq_bundle)

    # ---- caps & overrides ----
    caps: list[str] = []
    score = raw
    active = corr["n_families_active"]
    if active <= 1:
        score = min(score, 24)
        caps.append("single source-family cap (LOW): corroboration requires >=2 families")
    if (component_scores["social_issuer_specific_burst"] > 0 and
            component_scores["market_anomaly_score"] == 0 and
            component_scores["market_structure_score"] == 0 and
            component_scores["halt_regulatory_score"] == 0):
        score = min(score, 49)
        caps.append("social-only cap (<=MEDIUM)")
    if component_scores["market_anomaly_score"] == 0 and not ts.get("available") and not xs.get("available"):
        score = min(score, 49)
        caps.append("no-market-context cap (<=MEDIUM)")
    if ev_quality < 35:
        score = min(score, 49)
        caps.append("low-evidence-quality cap (<=MEDIUM)")
    if reddit_unavailable and component_scores["social_issuer_specific_burst"] > 0 and active <= 1:
        score = min(score, 24)
        caps.append("social-corroboration-unavailable cap (LOW)")
    if anomaly_evidence < sec_cls["floor"] and component_scores["market_structure_score"] == 0 and component_scores["halt_regulatory_score"] == 0:
        score = min(score, 24)
        caps.append(f"routine-context floor cap (LOW): anomaly_evidence<{sec_cls['floor']} for {sec_cls['class']} class")

    priority = score_to_priority(score)

    # ---- optional model advisory (does NOT change the rules-based priority) ----
    model_advisory = None
    _model = gbm_model.load_scorer()
    if _model:
        _pseudo = {"component_scores": component_scores, "social_metrics": social_feat,
                   "anomaly_evidence_score": anomaly_evidence,
                   "evidence_quality_score": round(ev_quality, 2), "corroboration": corr,
                   "security_class": {"class": sec_cls["class"]}}
        model_advisory = gbm_model.score_package(_pseudo, _model)

    # ---- benign explanation review (now actuating) ----
    benign = _benign_review(ctx, ts, xs, anomaly_evidence)
    benign_adjusted = False
    if benign["benign_explanation_strength"] >= 60 and anomaly_evidence < 30 and priority in ("MEDIUM", "HIGH"):
        priority = _band_down(priority)
        benign_adjusted = True
        caps.append("benign-explanation band reduction")

    return {
        "ticker": ticker,
        "generated_utc": _now(),
        "algorithm_version": ALGORITHM_VERSION,
        "finding_ceiling": FINDING_CEILING,
        "data_mode": _mode(fetches),
        "watch_score": round(score, 2),
        "raw_score_before_caps": raw,
        "review_priority": priority,
        "anomaly_evidence_score": anomaly_evidence,
        "evidence_quality_score": round(ev_quality, 2),
        "security_class": {
            "class": sec_cls["class"], "label": sec_cls["label"],
            "z_confirm": sec_cls["z_confirm"], "routine_context_floor": sec_cls["floor"],
            "social_weight": sec_cls["social_weight"],
            "price": round(price, 4) if isinstance(price, (int, float)) else None,
            "dollar_volume": round(dollar_volume, 2) if isinstance(dollar_volume, (int, float)) else None,
        },
        "corroboration": corr,
        "model_advisory": model_advisory,
        "component_scores": {k: component_scores[k] for k in (
            "social_issuer_specific_burst", "social_promotional_noise",
            "market_anomaly_score", "market_structure_score",
            "issuer_context_score", "halt_regulatory_score", "coordination_score",
            "issuer_event_score", "enforcement_history_score")},
        "enforcement_history": {
            "score": round(enforcement_score_val, 2), "basis": enforcement_basis,
            "matched_releases": [{"title": m.get("title"), "link": m.get("link"),
                                  "date": m.get("date"), "match": m.get("match")} for m in enf_matched[:5]],
        },
        "edgar_issuer_event": {
            "score": component_scores["issuer_event_score"],
            "basis": issuer_event_basis,
            "asof": edgar_payload.get("asof") if isinstance(edgar_payload, dict) else None,
            "source": edgar_fetch.name if (edgar_fetch and hasattr(edgar_fetch, "name")) else None,
        },
        "score_caps_applied": caps,
        "benign_explanation_review": {**benign, "band_reduction_applied": benign_adjusted},
        "market_detail": {"time_series": ts, "cross_sectional": xs, "microstructure": micro,
                          "anomaly_basis": market_detail.get("basis", [])},
        "social_metrics": {k: v for k, v in social_feat.items() if not k.startswith("_")},
        "coordination_detail": {"basis": coord_basis,
                                 "near_duplicate_clusters": coord_feat.get("near_duplicate_clusters", []),
                                 "shared_domain_groups": coord_feat.get("shared_domain_groups", []),
                                 "max_posts_in_burst": coord_feat.get("max_posts_in_burst", 0)},
        "official_context_families": sorted(ctx.get("families", {}).keys()),
        "issuer_name": ctx.get("issuer_name"),
        "evidence": _evidence_rows(fetches, component_scores),
        "evidence_gaps": ev_gaps,
        "non_accusatory_rationale": _rationale(component_scores, corr, anomaly_evidence),
        "review_questions": [
            "Do social, market, and official signals align in TIME, or is timing coincidental?",
            "Is the market move abnormal vs the ticker's own 20/60d baseline AND vs the same-day market?",
            "Are near-duplicate posts / shared domains genuine coordination or unrelated spam?",
            "Is there legitimate issuer news, earnings, filing, sector, or corporate-action explanation?",
            "Are FTD/threshold/short-volume observations routine plumbing or temporally aligned with the move?",
            "Are artifacts fresh, complete, hash-preserved, and source URLs redacted?",
        ],
        "limitations": [
            "WATCH-level review-priority package only; not a trading signal or proof of misconduct.",
            "Coordination and social features have high false-positive rates and require human verification of the cited clusters.",
            "Cross-sectional/rolling anomaly is statistical context, not evidence of manipulation.",
            "Market-structure, threshold, FTD and halt data are context, not proof of naked shorting or manipulation.",
            "Enforcement-history matches are BACKWARD-LOOKING (prior SEC releases) and never imply current misconduct; verify the cited releases.",
            "Replay mode uses cached custody artifacts; live mode uses .env credentials. Both preserve provenance.",
        ],
        "prohibited_actions": PROHIBITED_ACTIONS,
    }


def _benign_review(ctx, ts, xs, anomaly_evidence) -> dict[str, Any]:
    fam = ctx.get("families", {})
    indicators = []
    strength = 20
    if fam.get("sec_recent_forms"):
        indicators.append("Recent SEC filings exist (8-K/registration/insider); review whether they explain the move.")
        strength += 20
    if ts.get("available") and (ts.get("price_z") or 0) < 2 and (ts.get("volume_z") or 0) < 2:
        indicators.append("Move is within the ticker's own 20/60d robust baseline (benign for a liquid name).")
        strength += 25
    if xs.get("available") and (xs.get("abs_return_xz") or 0) < 2:
        indicators.append("Move is unremarkable versus the same-day market cross-section.")
        strength += 20
    if anomaly_evidence < 20:
        indicators.append("Concern-bearing anomaly evidence is weak; package is mostly reviewability/context.")
        strength += 10
    if not indicators:
        indicators.append("No strong benign explanation found in current artifacts; collect issuer news/filings before escalation.")
    return {"benign_explanation_strength": min(strength, 100), "indicators": indicators}


def _evidence_rows(fetches: dict[str, Any], components: dict[str, float]) -> list[dict[str, Any]]:
    rows = []
    for key, f in fetches.items():
        if not hasattr(f, "ok"):
            continue
        if f.data is None:
            continue
        rows.append({
            "source": f.name,
            "mode": f.mode,
            "status": f.status,
            "artifact_path": f.artifact_path,
            "artifact_sha256": f.sha256,
            "source_url_redacted": f.source_url_redacted,
            "limitation": "Context for human review; not proof of misconduct or a trading signal.",
        })
    return rows[:60]


def _rationale(components, corr, anomaly_evidence) -> str:
    parts = []
    for k, v in components.items():
        if v and k != "social_promotional_noise":
            parts.append(f"{k}={v}")
    if components.get("social_promotional_noise"):
        parts.append(f"promotional_noise(deflator)={components['social_promotional_noise']}")
    base = "; ".join(parts) if parts else "no material ticker-specific anomaly observed"
    return (f"{base}. {corr['n_families_active']} independent family(ies) active; "
            f"anomaly-evidence={anomaly_evidence}. Review priority only; not proof of misconduct.")


def _mode(fetches: dict[str, Any]) -> str:
    modes = {f.mode for f in fetches.values() if hasattr(f, "mode")}
    if modes == {"live"}:
        return "live"
    if "live" in modes:
        return "mixed_live_replay"
    if "replay" in modes:
        return "replay"
    return "unavailable"


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
