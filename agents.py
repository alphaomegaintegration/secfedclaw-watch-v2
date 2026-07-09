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

import concurrent.futures
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import fed_claw_root  # noqa: E402
from connectors import DataConnector  # noqa: E402
from concurrency import run_concurrent  # noqa: E402
import scoring_v2  # noqa: E402

# Scout fetches are I/O-bound; fan them out. Concurrency level does NOT affect
# results — run_concurrent preserves spec order — only latency.
SCOUT_MAX_WORKERS = 8

# The scrape/search connectors tag their custody note "... via <provider>"
# (scrapegraphai | firecrawl). Parse it so source_health — and the run
# manifest — record which provider actually served each live fetch.
_VIA_RE = re.compile(r"\bvia (\w+)")


def _provider_from_note(note: str) -> str | None:
    m = _VIA_RE.search(note or "")
    return m.group(1) if m else None

# CIK resolution lives in cik_registry (shared with edgar_pipeline, thread-safe).
from cik_registry import CIK_MAP, load_cik_map  # noqa: E402

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
        load_cik_map(c)
        cik = CIK_MAP.get(ticker.upper())

        def _stub(mode: str):
            return type("F", (), {"data": None, "mode": mode, "status": None,
                                  "ok": lambda self: False})()

        # (name, thunk) in a FIXED order. run_concurrent fans these onto a thread
        # pool (the ~25 fetches are I/O-bound) but rebuilds the dict in THIS order,
        # not completion order — so source_health / review_queue.json stay stable.
        specs = [
            ("daily_range", lambda: c.polygon_daily_range(ticker)),
            ("grouped", lambda: c.polygon_grouped_daily()),
            ("prev", lambda: c.polygon_prev(ticker)),
            ("snapshot", lambda: c.polygon_snapshot(ticker)),
            ("trades", lambda: c.polygon_trades(ticker)),
            ("quotes", lambda: c.polygon_quotes(ticker)),
            ("x", lambda: c.x_recent(ticker)),
            ("reddit", lambda: c.reddit_oauth(ticker)),
            ("stocktwits", lambda: c.stocktwits(ticker)),
            ("otc_threshold", lambda: c.finra_otc_threshold()),
            ("reg_sho", lambda: c.reg_sho_threshold()),
            ("halts", lambda: c.nasdaq_halts()),
            ("submissions", lambda: c.sec_submissions(cik) if cik else _stub("unavailable")),
            ("edgar", lambda: c.edgar_issuer_features(ticker)),
            ("litigation", lambda: c.sec_litigation_releases()),
            ("discord", lambda: c.discord_search(ticker)),
            ("instagram", lambda: c.instagram_hashtag(ticker)),
            ("facebook", lambda: c.facebook_search(ticker)),
            ("social_web", lambda: c.social_web_search(ticker)),
            ("fmp_quote", lambda: c.fmp_quote(ticker)),
            ("fmp_profile", lambda: c.fmp_profile(ticker)),
            ("fmp_historical", lambda: c.fmp_historical(ticker)),
            ("splits", lambda: c.polygon_splits(ticker)),
            ("options", lambda: c.polygon_options_snapshot(ticker)),
            ("otc_promo", lambda: c.otc_promotion_disclosure(ticker)),
            # OpenInsider: fast (2s waitFor), run for all tickers
            ("openinsider", lambda: c.openinsider_trades(ticker)),
            # Glint: slow (4s waitFor); deferred to enrich() for MEDIUM+ only
            # MyFXBook removed — forex-only platform, no signal value for equity surveillance
            ("glint", lambda: _stub("deferred")),
        ]
        fetches = run_concurrent(specs, max_workers=SCOUT_MAX_WORKERS)
        # Reddit availability depends on OAuth creds + reachability; reflect it.
        fetches["reddit_unavailable"] = not fetches["reddit"].ok()
        health = {k: {"mode": getattr(v, "mode", "n/a"), "status": getattr(v, "status", None),
                      "ok": v.ok() if hasattr(v, "ok") else False,
                      **({"provider": p} if (p := _provider_from_note(getattr(v, "note", ""))) else {})}
                  for k, v in fetches.items() if hasattr(v, "mode")}
        return {"fetches": fetches, "source_health": health}

    def enrich(self, ticker: str, fetches: dict[str, Any]) -> dict[str, Any]:
        """Fetch Glint.trade + MyFXBook concurrently (ThreadPoolExecutor).
        Called only for MEDIUM+ tickers after initial scoring — avoids burning
        Firecrawl credits and 7s waitFor time on LOW tickers.
        Updates fetches dict in-place and returns it."""
        c = self.c
        # ── data flow ─────────────────────────────────────────────────────
        #  gather() [fast: no Glint/MyFXBook]
        #     └─► score() → if MEDIUM+: enrich() [concurrent Glint+MyFXBook]
        #             └─► re-score() with enriched fetches
        # ──────────────────────────────────────────────────────────────────
        def _glint():
            return ("glint", c.glint_trade_signals(ticker))

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            futures = [pool.submit(_glint)]
            for fut in concurrent.futures.as_completed(futures):
                try:
                    key, result = fut.result()
                    fetches[key] = result
                except Exception:
                    pass  # individual enrichment failure is non-fatal; deferred stub remains
        return fetches


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

        # 1. Corroboration enforcement: HIGH+ needs >=2 concern-bearing families.
        # Only count families that carry anomaly evidence: market, coordination,
        # social, issuer_event, halt. Exclude enforcement_history (backward-looking
        # context, not anomaly) and issuer_context (OTC listing alone is not concern).
        # This closes a loophole where a stale enforcement history match or OTC listing
        # pushed n_families_active to 2 and bypassed the downgrade.
        CONCERN_FAMILIES = {"market", "coordination", "social", "issuer_event", "halt"}
        active_families = set(package["corroboration"].get("families_active", []))
        n_concern = len(active_families & CONCERN_FAMILIES)
        if n_concern < 2 and order.index(priority) >= 2:
            priority = "MEDIUM"
            caveats.append(
                f"adversary: downgraded to MEDIUM — only {n_concern} concern-bearing "
                f"family(ies) active (requires ≥2 of: market, coordination, social, "
                f"issuer_event, halt). Backward-looking context (enforcement_history, "
                f"issuer_context) does not satisfy the corroboration gate."
            )

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
        # Per-agent stage timing for the SRE dashboard (ms, accumulated by agent).
        stage_ms: dict[str, float] = {}

        def _timed(agent: str, fn):
            t0 = time.monotonic()
            try:
                return fn()
            finally:
                stage_ms[agent] = round(stage_ms.get(agent, 0.0) + (time.monotonic() - t0) * 1000, 1)

        gathered = _timed("Scout", lambda: self.scout.gather(ticker))
        # Pass 1: score without Glint/MyFXBook (they're deferred stubs)
        package = _timed("Analyst", lambda: self.analyst.score(ticker, gathered["fetches"]))
        # Pass 2: if MEDIUM+, fetch Glint concurrently and re-score.
        # Save pass-1 score for observability — operator can see if enrichment moved the needle.
        _MEDIUM_PLUS = {"MEDIUM", "HIGH", "CRITICAL_REVIEW"}
        pre_enrichment_score = package.get("watch_score")
        if package.get("review_priority") in _MEDIUM_PLUS:
            _timed("Scout", lambda: self.scout.enrich(ticker, gathered["fetches"]))
            package = _timed("Analyst", lambda: self.analyst.score(ticker, gathered["fetches"]))
            package["pre_enrichment_watch_score"] = pre_enrichment_score
            package["enrichment_delta"] = round(
                (package.get("watch_score", 0) - (pre_enrichment_score or 0)), 2)
        package["source_health"] = gathered["source_health"]
        package = _timed("Adversary", lambda: self.adversary.review(package))
        package = _timed("Explainer", lambda: self.explainer.explain(package))
        summary = _timed("Packager", lambda: self.packager.write(package))
        summary["source_health"] = gathered["source_health"]
        summary["explanation_source"] = (package.get("review_explanation") or {}).get("source")
        summary["stage_ms"] = stage_ms
        return summary
