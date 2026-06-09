#!/usr/bin/env python3
"""Agentic pipeline for SECFEDCLAW v0.2.

Four role-bounded agents run in sequence per ticker, mirroring the SOUL.md
operating model (detect -> analyze -> adversarially review -> package). Each
agent has a narrow mandate and explicit prohibitions; none may trade, contact
external parties, or emit conclusions above WATCH.

  ScoutAgent     -> gathers source data (live or replay), reports source health
  AnalystAgent   -> runs the v0.2 scoring engine
  AdversaryAgent -> red-teams the result: benign tests, coordination sanity,
                    corroboration enforcement; can only LOWER priority or add
                    caveats, never raise it
  PackagerAgent  -> writes the custody-preserving review package
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import fed_claw_root  # noqa: E402
from connectors import DataConnector  # noqa: E402
import scoring_v2  # noqa: E402

# Minimal CIK map for issuer-context lookups; extended dynamically at runtime.
CIK_MAP = {
    "AAPL": "0000320193", "TSLA": "0001318605", "AMC": "0001411579",
    "GME": "0001326380", "AMD": "0000002488", "NVDA": "0001045810",
    "ALB": "0000915913",
}
_CIK_LOADED = False


def _load_cik_map(connector: DataConnector) -> None:
    """Populate CIK_MAP dynamically from SEC company_tickers.json (no key needed)."""
    global _CIK_LOADED
    if _CIK_LOADED:
        return
    _CIK_LOADED = True
    try:
        f = connector.sec_company_tickers()
        if f.ok() and isinstance(f.data, dict):
            for v in f.data.values():
                if isinstance(v, dict) and v.get("ticker") and v.get("cik_str"):
                    CIK_MAP[v["ticker"].upper()] = str(v["cik_str"]).zfill(10)
    except Exception:
        pass

PROHIBITIONS = [
    "no trading signals", "no market actions", "no external contact",
    "no accusations", "no findings above WATCH", "no autonomous escalation",
]


class ScoutAgent:
    role = "scout"

    def __init__(self, connector: DataConnector):
        self.c = connector

    def gather(self, ticker: str) -> dict[str, Any]:
        c = self.c
        _load_cik_map(c)
        cik = CIK_MAP.get(ticker.upper())
        fetches = {
            "daily_range": c.polygon_daily_range(ticker),
            "grouped": c.polygon_grouped_daily(),
            "prev": c.polygon_prev(ticker),
            "snapshot": c.polygon_snapshot(ticker),
            "trades": c.polygon_trades(ticker),
            "quotes": c.polygon_quotes(ticker),
            "x": c.x_recent(ticker),
            "reddit": c.reddit_oauth(ticker),
            "stocktwits": c.stocktwits(ticker),
            "otc_threshold": c.finra_otc_threshold(),
            "reg_sho": c.reg_sho_threshold(),
            "halts": c.nasdaq_halts(),
            "submissions": c.sec_submissions(cik) if cik else type("F", (), {"data": None, "mode": "unavailable", "ok": lambda self: False})(),
            "edgar": c.edgar_issuer_features(ticker),
            "litigation": c.sec_litigation_releases(),
            "discord": c.discord_search(ticker),
            "instagram": c.instagram_hashtag(ticker),
            "facebook": c.facebook_search(ticker),
            "social_web": c.social_web_search(ticker),
            "fmp_quote": c.fmp_quote(ticker),
            "fmp_profile": c.fmp_profile(ticker),
            "fmp_historical": c.fmp_historical(ticker),
            "splits": c.polygon_splits(ticker),
            "options": c.polygon_options_snapshot(ticker),
            "otc_promo": c.otc_promotion_disclosure(ticker),
            "openinsider": c.openinsider_trades(ticker),
            "glint": c.glint_trade_signals(ticker),
            "myfxbook": c.myfxbook_community(ticker),
        }
        # Reddit availability depends on OAuth creds + reachability; reflect it.
        fetches["reddit_unavailable"] = not fetches["reddit"].ok()
        health = {k: {"mode": getattr(v, "mode", "n/a"), "status": getattr(v, "status", None),
                      "ok": v.ok() if hasattr(v, "ok") else False}
                  for k, v in fetches.items() if hasattr(v, "mode")}
        return {"fetches": fetches, "source_health": health}


class AnalystAgent:
    role = "analyst"

    def score(self, ticker: str, fetches: dict[str, Any]) -> dict[str, Any]:
        return scoring_v2.build_package(ticker, fetches)


class AdversaryAgent:
    """Red-team: may only LOWER priority or add caveats, never raise it."""
    role = "adversary"

    def review(self, package: dict[str, Any]) -> dict[str, Any]:
        caveats = []
        order = ["LOW", "MEDIUM", "HIGH", "CRITICAL_REVIEW"]
        priority = package["review_priority"]

        # 1. Corroboration enforcement: HIGH+ needs >=2 families.
        if package["corroboration"]["n_families_active"] < 2 and order.index(priority) >= 2:
            priority = "MEDIUM"
            caveats.append("adversary: downgraded to MEDIUM — fewer than 2 independent families.")

        # 2. Coordination authenticity: a coordination score with no clusters is suspect.
        cd = package.get("coordination_detail", {})
        if package["component_scores"]["coordination_score"] >= 30 and not cd.get("near_duplicate_clusters") and not cd.get("shared_domain_groups"):
            caveats.append("adversary: coordination score lacks concrete clusters; treat as weak.")

        # 3. Promotional-noise dominance: if promo >> issuer-specific, caveat spam.
        cs = package["component_scores"]
        if cs["social_promotional_noise"] > 2 * max(cs["social_issuer_specific_burst"], 1):
            caveats.append("adversary: social dominated by promotional noise / cashtag-stuffing, likely spam not issuer signal.")

        # 4. Replay staleness caveat.
        if package.get("data_mode") in ("replay", "unavailable"):
            caveats.append("adversary: scored from cached/replayed artifacts; confirm against live data before any human escalation.")

        # 5. Benign dominance.
        if package["benign_explanation_review"]["benign_explanation_strength"] >= 70 and package["anomaly_evidence_score"] < 25 and order.index(priority) >= 1:
            priority = order[max(0, order.index(priority) - 1)]
            caveats.append("adversary: strong benign explanation + weak anomaly — reduced one band.")

        package["review_priority"] = priority
        package["adversarial_review"] = {
            "caveats": caveats or ["adversary: no additional downgrade warranted; standard human review applies."],
            "may_only_lower_priority": True,
        }
        return package


class ExplainerAgent:
    """Writes a plain-language WATCH review narrative (LLM if opted in, else
    a deterministic template). Adds no facts, asserts no wrongdoing, gives no
    trading advice; LLM output is guardrail-checked or discarded."""
    role = "explainer"

    def __init__(self, env: dict | None = None):
        self.env = env

    def explain(self, package: dict[str, Any]) -> dict[str, Any]:
        import explainer
        res = explainer.explain(package, env=self.env)
        package["review_explanation"] = res
        return package


class PackagerAgent:
    role = "packager"

    def __init__(self, out_dir: Path | None = None):
        # Write next to this package's out/ — the same dir the dashboard reads.
        # (Avoids a layout-dependent fed_claw_root()/secfedclaw_v2/out mismatch.)
        self.out_dir = out_dir or (Path(__file__).resolve().parent / "out")

    def write(self, package: dict[str, Any]) -> dict[str, Any]:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        ts = package["generated_utc"].replace(":", "").replace("-", "")
        path = self.out_dir / f"{package['ticker']}_{ts}_watch_v2.json"
        blob = json.dumps(package, indent=2, sort_keys=True, default=str) + "\n"
        path.write_text(blob)
        return {
            "ticker": package["ticker"],
            "review_priority": package["review_priority"],
            "watch_score": package["watch_score"],
            "anomaly_evidence_score": package["anomaly_evidence_score"],
            "evidence_quality_score": package["evidence_quality_score"],
            "n_families_active": package["corroboration"]["n_families_active"],
            "security_class": package.get("security_class", {}).get("class"),
            "data_mode": package["data_mode"],
            "package_path": str(path),
            "package_sha256": hashlib.sha256(blob.encode()).hexdigest(),
        }


class Orchestrator:
    """Runs the full agent loop for one ticker."""

    def __init__(self, connector: DataConnector | None = None, out_dir: Path | None = None):
        self.connector = connector or DataConnector()
        self.scout = ScoutAgent(self.connector)
        self.analyst = AnalystAgent()
        self.adversary = AdversaryAgent()
        self.explainer = ExplainerAgent(env=self.connector.env)
        self.packager = PackagerAgent(out_dir)

    def run(self, ticker: str) -> dict[str, Any]:
        gathered = self.scout.gather(ticker)
        package = self.analyst.score(ticker, gathered["fetches"])
        package["source_health"] = gathered["source_health"]
        package = self.adversary.review(package)
        package = self.explainer.explain(package)
        summary = self.packager.write(package)
        summary["source_health"] = gathered["source_health"]
        summary["explanation_source"] = (package.get("review_explanation") or {}).get("source")
        return summary
