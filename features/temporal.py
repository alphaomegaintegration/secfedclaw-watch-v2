#!/usr/bin/env python3
"""Temporal-fusion feature for SECFEDCLAW v0.2.

v0.1 summed component scores without requiring that the signals line up in
time. The pump-and-dump typology is fundamentally temporal: promotion burst
-> abnormal market response -> reversal. This module produces a
cross-source corroboration multiplier in [0,1] describing how many INDEPENDENT
source families are simultaneously active, which the composite uses to gate
escalation (corroboration is required for HIGH/CRITICAL per the design doc).
"""
from __future__ import annotations

from typing import Any


def corroboration(component_scores: dict[str, float],
                  social_feat: dict[str, Any]) -> dict[str, Any]:
    families_active = []
    # Social burst corroborates a manipulation concern ONLY when it carries a
    # coordination or promotional signature. Benign issuer discussion volume
    # (e.g. earnings chatter) is NOT a corroborating family — counting it as
    # one is what makes a benign-news move look like a pump. This materially
    # improves precision without sacrificing recall on coordinated pumps.
    promo_noisy = social_feat.get("n_promotional_noise", 0) >= 2
    coordinated = component_scores.get("coordination_score", 0) >= 30
    if component_scores.get("social_issuer_specific_burst", 0) >= 25 and (coordinated or promo_noisy):
        families_active.append("social")
    if component_scores.get("market_anomaly_score", 0) >= 25:
        families_active.append("market")
    if component_scores.get("market_structure_score", 0) > 0:
        families_active.append("market_structure")
    if component_scores.get("issuer_context_score", 0) >= 30:
        families_active.append("issuer")
    if component_scores.get("halt_regulatory_score", 0) > 0:
        families_active.append("halt")
    if component_scores.get("coordination_score", 0) >= 30:
        families_active.append("coordination")
    # EDGAR issuer-event family: insiders/issuer selling or diluting into demand.
    if component_scores.get("issuer_event_score", 0) >= 30:
        families_active.append("issuer_event")

    n = len(families_active)
    # Corroboration multiplier applied to the concern-bearing anomaly-evidence
    # anchor. A single family is heavily discounted (cannot establish concern
    # alone); broad multi-family corroboration is allowed a slight boost so a
    # genuinely corroborated event can reach CRITICAL_REVIEW for a human.
    mult = {0: 0.4, 1: 0.6, 2: 0.85, 3: 1.0}.get(n, 1.1)
    return {
        "families_active": families_active,
        "n_families_active": n,
        "corroboration_multiplier": mult,
        "note": "HIGH/CRITICAL review priority requires >=2 independent active families per design.",
    }
