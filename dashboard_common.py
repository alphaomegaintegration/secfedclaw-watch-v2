"""Shared helpers + constants for the SECFEDCLAW dashboard: esc/load/info/
pill/bar/ticker_links/_dd, the DEFS data dictionary, AGENTS, CASES, and
formatting helpers. Imported by dashboard_panels and dashboard_v2."""
from __future__ import annotations
import argparse
import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
sys.path.insert(0, str(Path(__file__).resolve().parent))
import agent_status as agentstatus  # noqa: E402
import usage as usage_mod  # noqa: E402
from config import output_root

__all__ = ['AGENTS', 'Any', 'BOUNDARY', 'CASES', 'CLASS_ABBR', 'DEFS', 'OUT', 'PRI', 'Path', '_MED_PLUS', '_dd', '_fmt_age', '_fmt_ms', '_search_model_short', '_state_dot', 'agentstatus', 'argparse', 'bar', 'datetime', 'esc', 'html', 'info', 'json', 'load', 'output_root', 'pill', 'sys', 'ticker_links', 'timezone', 'usage_mod']

OUT = output_root()


PRI = {"CRITICAL_REVIEW": ("crit", "Critical review"), "HIGH": ("high", "High"),
       "MEDIUM": ("med", "Medium"), "LOW": ("low", "Low")}

CLASS_ABBR = {"thin_microcap": "thin / microcap", "small_cap": "small cap",
              "mid_cap": "mid cap", "large_cap": "large cap", "unknown": "unknown"}

BOUNDARY = ("WATCH ceiling — SECFEDCLAW produces review-priority context for authorized human "
            "review only. It does not assert fraud, recommend trades, contact anyone, freeze "
            "assets, or initiate legal process. Any escalation requires separate lawful authorization.")

# Plain-language definitions surfaced as tooltips + the data dictionary.

DEFS = {
    "watch_score": "Composite 0–100 review-priority score. Bands: LOW <25, MEDIUM 25–49, HIGH 50–74, CRITICAL_REVIEW ≥75.",
    "anomaly_evidence": "Concern-bearing evidence (market anomaly, coordination, market-structure, halt, issuer-event, issuer-specific social). Separated from how complete the evidence is.",
    "evidence_quality": "Reviewability: how complete, fresh and independent the evidence is (source families present, artifacts, gaps). Not a measure of concern.",
    "families": "Independent source families currently active (market, coordination, social, issuer, halt, issuer_event). HIGH/CRITICAL requires ≥2 — single-source signals are capped.",
    "market_anomaly_score": "Robust price+volume abnormality vs the ticker's own 20/60-day baseline AND vs the same-day market cross-section; high only when BOTH price and volume confirm.",
    "coordination_score": "Near-duplicate post clusters, shared promotional domains, burst synchronization, author concentration, and unanimous-bullish+promo sentiment across X/Reddit/StockTwits.",
    "social_intel": "Opt-in (SECFEDCLAW_SOCIAL_INTEL): cross-platform coordinated-push detection. Boosts coordination ONLY when a near-duplicate push spans ≥2 platforms by ≥3 distinct accounts AND aligns with a confirmed market move. The optional LLM urgency layer is substring-grounded and advisory — never scored. Never lights an independent family.",
    "issuer_event_score": "EDGAR daily-diff issuer signal: recent insider sales (Form 4/144), dilution/financing (S-1/S-3/424B/EFFECT), delisting or late filings — selling/diluting into promoted demand.",
    "market_structure_score": "FINRA/Nasdaq context: Reg SHO threshold, OTC threshold, short-sale volume. Context only, not proof of naked shorting.",
    "security_class": "Liquidity class (thin/microcap → small → mid → large) that calibrates thresholds: microcaps are more sensitive, large caps need stronger confirmation.",
    "model_advisory": "Optional calibrated review-priority probability from the gradient-boosted model. Advisory only — it never changes the rules-based priority and is never a guilt label.",
    "enforcement_history_score": "Whether the ticker/issuer appears in recent SEC litigation releases. BACKWARD-LOOKING context that raises review attention — never proof of current misconduct.",
    "options_flow_score": "Unusual options activity: call/put open-interest skew (≥3:1 is a pump tell), near-term expiry clustering (>60% contracts ≤30 days), and implied volatility >150%. Requires Polygon options entitlement; 0 when unavailable.",
    "needs_adjustment_review": "Recent stock split detected within 60 days. Price/volume baseline comparisons may be unreliable; watch_score capped at MEDIUM when market_anomaly_score is primary driver.",
    "promo_disclosure": "SEC-required paid-promotion filing found on OTC Markets. Paid promoters are a hallmark of pump-and-dump schemes; +20 added to issuer_event_score.",
}



def esc(v: Any) -> str:
    return html.escape(str(v), quote=True)



def load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(errors="replace"))
    except Exception:
        return default



def info(key: str) -> str:
    d = DEFS.get(key, "")
    return (f'<span class="info" tabindex="0" aria-label="{esc(d)}">ⓘ'
            f'<span class="tooltip">{esc(d)}</span></span>') if d else ""



def pill(priority: str) -> str:
    cls, label = PRI.get(priority, ("low", priority))
    return f'<span class="pill {cls}">{esc(label)}</span>'



def bar(value: float, cls: str = "", cap: float = 100.0) -> str:
    pct = max(0.0, min(100.0, (value or 0) / cap * 100))
    return (f'<div class="bar" role="img" aria-label="{value:.0f} of 100">'
            f'<div class="bar-fill {cls}" style="width:{pct:.0f}%"></div>'
            f'<span class="bar-num">{value:.0f}</span></div>')



def ticker_links(t: str) -> str:
    t = esc(t)
    refs = [
        (f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&ticker={t}&type=&dateb=&owner=include&count=40",
         "EDGAR", "SEC filings (3/4/8-K/S-1…)"),
        (f"https://www.nasdaq.com/market-activity/stocks/{t.lower()}", "Nasdaq", "Quote, halts, short interest"),
        (f"https://finance.yahoo.com/quote/{t}", "Market", "Price / volume / profile"),
        (f"https://stocktwits.com/symbol/{t}", "Social", "StockTwits stream"),
    ]
    a = "".join(f'<a href="{u}" target="_blank" rel="noopener noreferrer" title="{esc(d)}">{lbl}</a>'
                for u, lbl, d in refs)
    return f'<span class="reflinks">{a}</span>'


# --------------------------------------------------------------------------- #
# Overview: KPIs + review queue + source health
# --------------------------------------------------------------------------- #

_MED_PLUS = {"CRITICAL_REVIEW", "HIGH", "MEDIUM"}



def _dd(title: str, n: int | str, body: str) -> str:
    """One collapsible drill-down block (count in the summary, detail on expand)."""
    if not body:
        return ""
    return (f'<details class="dd"><summary>{esc(title)} '
            f'<span class="dd-n">{esc(str(n))}</span></summary>{body}</details>')



AGENTS = [
    ("01", "Scout", "Data feeds",
     "Pulls each source live (or replays cached custody artifacts): Polygon aggregates/grouped/snapshot, "
     "Flat-Files history, X / Reddit / StockTwits, SEC EDGAR submissions + daily-diff, FINRA/Nasdaq.",
     "Source health per feed; raw responses persisted with SHA256 for custody."),
    ("02", "Analyst", "Data engineering + algorithms",
     "Normalizes & deduplicates posts across platforms; computes robust rolling 20/60-day & cross-sectional "
     "z-scores (median/MAD) with price+volume double-confirmation; builds the coordination graph "
     "(near-duplicate clustering, shared domains, burst sync); classifies liquidity class & applies its thresholds; "
     "folds in EDGAR issuer-event + sentiment.",
     "Component scores, anomaly-evidence, corroboration multiplier, composite watch score + caps."),
    ("03", "Adversary", "Red-team review",
     "Tests benign explanations, enforces ≥2-family corroboration, checks coordination clusters are real, "
     "flags promotional-noise dominance and replay staleness.",
     "May only LOWER priority or add caveats — never raises it."),
    ("04", "Explainer", "Plain-language summary",
     "Writes a 3–5 sentence review narrative grounded ONLY in the package evidence (LLM when opted in, else a "
     "deterministic template). Guardrail rejects any fraud/accusation/trading language; usage + cost are recorded.",
     "review_explanation (source: llm | template) + LLM-cost ledger entry."),
    ("05", "Packager", "Evidence package",
     "Assembles the WATCH package with custody (artifact paths + SHA256), review questions, limitations, and "
     "the explicit prohibited-actions list.",
     "Non-accusatory review-priority package written to out/ + the ranked queue."),
]



CASES = [
    {"id": "Coordinated social influencers", "src": "SEC 2022-221",
     "url": "https://www.sec.gov/newsroom/press-releases/2022-221",
     "pattern": "Influencers built large Twitter/Discord audiences, bought stocks, urged followers to buy with "
                "price targets, then sold without disclosing intent to sell.",
     "thresholds": "coordination_score ≥30 (near-duplicate promos across accounts/platforms) + market double-"
                   "confirmation around promotion windows ⇒ ≥2 families ⇒ MEDIUM/HIGH.",
     "explain": "Social-only would be capped; pairing coordinated promotion with a confirmed price+volume move is "
                "what lifts review priority.",
     "training": "Label resolved cases useful_watch to teach the model that coordination + market confirmation matters."},
    {"id": "Single promoter, penny stock", "src": "SEC 2021-214",
     "url": "https://www.sec.gov/newsroom/press-releases/2021-214",
     "pattern": "One account made thousands of tweets promoting microcaps the promoter secretly held, selling into "
                "the inflated demand.",
     "thresholds": "thin/microcap class (z_confirm 2.5) + abnormal volume + promotional-language burst; reversal after "
                   "the promotion window.",
     "explain": "Microcap calibration raises sensitivity so a thin-name ramp is not lost against large-cap noise.",
     "training": "Reversal-after-burst windows are strong positives for the temporal pattern."},
    {"id": "Newsletter microcap promotion", "src": "SEC 2014-256",
     "url": "https://www.sec.gov/newsroom/press-releases/2014-256",
     "pattern": "Promoters controlled large share blocks, pushed stocks via paid newsletters, and dumped at elevated "
                "prices without disclosing compensation.",
     "thresholds": "issuer_event (dilution/insider via EDGAR daily-diff) + market-structure context + promotion burst.",
     "explain": "Issuer selling/diluting into promoted demand is a classic tell; EDGAR daily-diff makes it a "
                "first-class corroborating family.",
     "training": "Pairs promotion windows with filing events for multi-family positives."},
    {"id": "Offshore nominee pump-and-dump", "src": "SEC 2022-62",
     "url": "https://www.sec.gov/newsroom/press-releases/2022-62",
     "pattern": "Secret accumulation via offshore nominees, funded promotions, multi-week ramps in thin securities, "
                "then dumping.",
     "thresholds": "multi-day market anomaly in thin names + threshold/FTD context; promotion where public.",
     "explain": "SECFEDCLAW surfaces the public-market symptoms and explicitly flags the evidence gap (hidden "
                "ownership needs lawful records).",
     "training": "Teaches the system to record evidence gaps, not overclaim from public data."},
]



def _state_dot(state: str) -> str:
    cls = {"live": "ok", "ok": "ok", "replay": "warn-d", "degraded": "warn-d",
           "unavailable": "bad", "idle": "idle"}.get(state, "idle")
    return f'<span class="dot {cls}"></span>{esc(state)}'



def _fmt_age(s: int | None) -> str:
    if s is None:
        return "—"
    if s < 90:
        return f"{s}s"
    if s < 5400:
        return f"{round(s / 60)}m"
    return f"{round(s / 3600)}h"



def _fmt_ms(ms) -> str:
    """Human-readable latency: ms under 1s, s under 1m, else m."""
    if ms is None:
        return "—"
    ms = float(ms)
    if ms < 1000:
        return f"{round(ms)}ms"
    if ms < 60_000:
        return f"{ms / 1000:.1f}s"
    return f"{ms / 60_000:.1f}m"



def _search_model_short(model: str) -> str:
    """Short label for the search LLM card: bare model name + free/cloud tag."""
    if not model:
        return "—"
    bare = model.split("/")[-1]
    return f"{bare} · free" if model.startswith("ollama/") else bare


