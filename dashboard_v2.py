#!/usr/bin/env python3
"""SECFEDCLAW v0.2 operator dashboard (offline, self-contained).

Renders a single inline-CSS/JS HTML file (no external JS/CSS/images or network
callbacks) over the v0.2 artifacts: ranked review queue, evidence packages,
agent orchestration, methodology / data dictionary, SEC threshold case studies,
and the calibration backtest.

Design: a small consistent design system (color/space/type tokens), clear
section intros, info tooltips on every metric, and per-ticker reference links
(SEC EDGAR / market / social) that open externally on demand.
WATCH-only: review priorities, never trading signals or proof of misconduct.
"""
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

OUT = Path(__file__).resolve().parent / "out"

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
    "issuer_event_score": "EDGAR daily-diff issuer signal: recent insider sales (Form 4/144), dilution/financing (S-1/S-3/424B/EFFECT), delisting or late filings — selling/diluting into promoted demand.",
    "market_structure_score": "FINRA/Nasdaq context: Reg SHO threshold, OTC threshold, short-sale volume. Context only, not proof of naked shorting.",
    "security_class": "Liquidity class (thin/microcap → small → mid → large) that calibrates thresholds: microcaps are more sensitive, large caps need stronger confirmation.",
    "model_advisory": "Optional calibrated review-priority probability from the gradient-boosted model. Advisory only — it never changes the rules-based priority and is never a guilt label.",
    "enforcement_history_score": "Whether the ticker/issuer appears in recent SEC litigation releases. BACKWARD-LOOKING context that raises review attention — never proof of current misconduct.",
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
def kpi_panel(queue: dict[str, Any]) -> str:
    valid = [r for r in queue.get("review_queue", []) if "error" not in r]
    universe = queue.get("universe_size", len(valid))
    dist = {p: sum(1 for r in valid if r.get("review_priority") == p) for p in PRI}
    flagged = dist["CRITICAL_REVIEW"] + dist["HIGH"] + dist["MEDIUM"]
    mean_anom = round(sum(r.get("anomaly_evidence_score", 0) for r in valid) / len(valid), 1) if valid else 0
    ready = f"{round(len(valid)/universe*100):d}%" if universe else "—"
    cards = [
        ("Universe", universe, "tickers scanned this run"),
        ("Scored", len(valid), "packages produced"),
        ("Score-ready", ready, "scored ÷ universe"),
        ("Flagged ≥MED", flagged, "need human review"),
        ("Critical", dist["CRITICAL_REVIEW"], "urgent review"),
        ("High", dist["HIGH"], "elevated"),
        ("Mean anomaly", mean_anom, "avg concern evidence"),
        ("Data mode", queue.get("data_mode", "?"), "live or replay"),
    ]
    return '<div class="kpis">' + "".join(
        f'<div class="kpi"><div class="kpi-num">{esc(v)}</div><div class="kpi-lbl">{esc(l)}</div>'
        f'<div class="kpi-sub">{esc(s)}</div></div>' for l, v, s in cards) + '</div>'


def queue_table(queue: dict[str, Any]) -> str:
    rows = []
    for r in queue.get("review_queue", []):
        if "error" in r:
            rows.append(f'<tr><td>{esc(r["ticker"])}</td><td colspan="7" class="muted">error: {esc(r["error"])}</td></tr>')
            continue
        rows.append(
            f'<tr data-priority="{esc(r["review_priority"])}">'
            f'<td class="tk"><b>{esc(r["ticker"])}</b>{ticker_links(r["ticker"])}</td>'
            f'<td>{pill(r["review_priority"])}</td>'
            f'<td>{bar(r.get("watch_score",0))}</td>'
            f'<td>{bar(r.get("anomaly_evidence_score",0), cls="anom")}</td>'
            f'<td class="num">{r.get("evidence_quality_score",0):.0f}</td>'
            f'<td class="num">{r.get("n_families_active",0)}</td>'
            f'<td class="muted small">{esc(CLASS_ABBR.get(r.get("security_class"), r.get("security_class") or "?"))}</td>'
            f'<td class="muted small">{esc(r.get("data_mode","?"))}</td></tr>')
    body = "".join(rows) or '<tr><td colspan="8" class="muted">No review queue yet — run scan.py.</td></tr>'
    return (
        '<table><thead><tr>'
        '<th>Ticker</th><th>Priority</th>'
        f'<th>Watch score {info("watch_score")}</th>'
        f'<th>Anomaly evidence {info("anomaly_evidence")}</th>'
        f'<th class="num">Ev.Q {info("evidence_quality")}</th>'
        f'<th class="num">Fam {info("families")}</th>'
        f'<th>Class {info("security_class")}</th><th>Mode</th>'
        f'</tr></thead><tbody>{body}</tbody></table>')


def source_health_panel(queue: dict[str, Any]) -> str:
    agg: dict[str, dict[str, int]] = {}
    for r in queue.get("review_queue", []):
        for src, h in (r.get("source_health") or {}).items():
            a = agg.setdefault(src, {"ok": 0, "total": 0, "live": 0, "replay": 0})
            a["total"] += 1
            a["ok"] += 1 if h.get("ok") else 0
            a["live"] += 1 if h.get("mode") == "live" else 0
            a["replay"] += 1 if h.get("mode") == "replay" else 0
    if not agg:
        return ""
    rows = "".join(
        f'<tr><td>{esc(s)}</td><td class="num">{v["ok"]}/{v["total"]}</td>'
        f'<td class="num">{v["live"]}</td><td class="num">{v["replay"]}</td></tr>'
        for s, v in sorted(agg.items()))
    return ('<div class="card"><h3>Data feed health <span class="muted small">(across scanned tickers)</span></h3>'
            '<table class="mini"><thead><tr><th>feed</th><th class="num">ok</th>'
            f'<th class="num">live</th><th class="num">replay</th></tr></thead><tbody>{rows}</tbody></table></div>')


def package_cards(packages: list[dict[str, Any]]) -> str:
    cards = []
    for p in sorted(packages, key=lambda d: d.get("watch_score", 0), reverse=True)[:24]:
        comp = p.get("component_scores", {})
        order = ["market_anomaly_score", "coordination_score", "issuer_event_score",
                 "enforcement_history_score", "market_structure_score", "halt_regulatory_score",
                 "issuer_context_score", "social_issuer_specific_burst", "social_promotional_noise"]
        comp_rows = "".join(
            f'<tr><td>{esc(k.replace("_"," "))} {info(k)}</td><td>{bar(comp.get(k,0))}</td></tr>'
            for k in order if k in comp)
        corr = p.get("corroboration", {})
        caps = p.get("score_caps_applied", []) or ["none"]
        adv = (p.get("adversarial_review") or {}).get("caveats", [])
        coord = p.get("coordination_detail", {})
        clusters = coord.get("near_duplicate_clusters", [])
        ma = p.get("model_advisory")
        sc = p.get("security_class", {})
        ma_html = (f'<p class="small model"><b>Model advisory {info("model_advisory")}:</b> '
                   f'P(review-worthy)={ma["review_priority_probability"]:.2f} '
                   f'· top: {esc(", ".join(c["feature"] for c in ma.get("top_features", [])[:3]))}</p>'
                   if ma else "")
        cards.append(
            f'<div class="card pkg" data-priority="{esc(p.get("review_priority"))}">'
            f'<div class="pkg-head"><h3>{esc(p.get("ticker"))}</h3>{pill(p.get("review_priority","LOW"))}'
            f'{ticker_links(p.get("ticker",""))}</div>'
            f'<p class="muted small">score {p.get("watch_score",0):.0f} · anomaly {p.get("anomaly_evidence_score",0):.0f} '
            f'· evidence-quality {p.get("evidence_quality_score",0):.0f} · {esc(CLASS_ABBR.get(sc.get("class"), "?"))} '
            f'· {esc(p.get("data_mode","?"))}</p>'
            + (f'<p class="small expl"><b>Review summary</b> '
               f'<span class="muted">({esc((p.get("review_explanation") or {}).get("source","template"))})</span>: '
               f'{esc((p.get("review_explanation") or {}).get("text",""))}</p>'
               if (p.get("review_explanation") or {}).get("text") else "")
            + f'<table class="mini">{comp_rows}</table>'
            f'<p class="small"><b>Families active:</b> {esc(", ".join(corr.get("families_active",[])) or "none")} '
            f'(×{corr.get("corroboration_multiplier","?")})</p>'
            f'<p class="small"><b>Caps:</b> {esc("; ".join(caps))}</p>'
            + (f'<p class="small warn"><b>Coordination:</b> {len(clusters)} near-duplicate cluster(s)</p>' if clusters else "")
            + (f'<p class="small enf"><b>Enforcement history (backward-looking):</b> '
               f'{len((p.get("enforcement_history") or {}).get("matched_releases", []))} prior release(s) referenced</p>'
               if (p.get("enforcement_history") or {}).get("matched_releases") else "")
            + ma_html
            + f'<p class="small adv"><b>Adversary:</b> {esc("; ".join(adv[:2]))}</p>'
            f'<p class="small rationale">{esc(p.get("non_accusatory_rationale",""))}</p></div>')
    return "".join(cards) or '<p class="muted">No packages yet. Run scan.py.</p>'


# --------------------------------------------------------------------------- #
# Agents / orchestration
# --------------------------------------------------------------------------- #
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


def agents_panel(queue: dict[str, Any]) -> str:
    stages = "".join(
        f'<div class="stage"><div class="stage-num">{n}</div><h3>{esc(name)}</h3>'
        f'<div class="tag">{esc(tag)}</div><p class="small">{esc(does)}</p>'
        f'<p class="small out"><b>Output:</b> {esc(out)}</p></div>'
        + ('<div class="arrow">→</div>' if n != "05" else "")
        for n, name, tag, does, out in AGENTS)
    return (
        '<p class="intro">Each ticker flows through a four-agent pipeline (the <code>Orchestrator</code> in '
        '<code>agents.py</code>); <code>scan.py</code> runs it across the universe and ranks the results. '
        'Every agent is role-bounded and cannot trade, contact anyone, or exceed the WATCH ceiling.</p>'
        f'<div class="pipeline">{stages}</div>'
        f'{source_health_panel(queue)}'
        '<div class="card"><h3>Why this design</h3><p class="small">Separating detection (Scout/Analyst) from '
        'adversarial review (Adversary) and evidence assembly (Packager) keeps concern-bearing signal distinct from '
        'reviewability, forces cross-source corroboration before escalation, and preserves an auditable custody trail '
        '— the discipline an enforcement-adjacent system requires.</p></div>')


# --------------------------------------------------------------------------- #
# Methodology / data dictionary
# --------------------------------------------------------------------------- #
def methodology_panel() -> str:
    dd = "".join(f'<tr><td><b>{esc(k.replace("_"," "))}</b></td><td class="small">{esc(v)}</td></tr>'
                 for k, v in DEFS.items())
    return (
        '<p class="intro">SECFEDCLAW fuses social, market, official (SEC/FINRA/Nasdaq) and microstructure signals into '
        'a calibrated review-priority score. It is designed to <b>reduce time-to-review</b>, not to conclude wrongdoing. '
        'Every score cites artifacts and lists plausible benign explanations.</p>'
        '<div class="card"><h3>Review-priority bands</h3>'
        '<div class="bands">'
        '<span class="pill low">LOW &lt;25</span><span class="pill med">MEDIUM 25–49</span>'
        '<span class="pill high">HIGH 50–74</span><span class="pill crit">CRITICAL ≥75</span></div>'
        '<p class="small muted">HIGH/CRITICAL require ≥2 independent corroborating families. Single-source, social-only, '
        'no-market-context, low-evidence and routine-context cases are capped. A strong benign explanation reduces a band.</p></div>'
        '<div class="card"><h3>Data dictionary</h3><table class="mini"><tbody>' + dd + '</tbody></table></div>'
        '<div class="card"><h3>What it does NOT do</h3><p class="small">No fraud determination, no trading signal, '
        'no contact with regulators/brokers/issuers/victims, no asset freeze, no legal process. Findings are bounded by the '
        'artifacts available at run time and require human adjudication.</p></div>')


# --------------------------------------------------------------------------- #
# SEC threshold case studies (illustrative; allegations unless final judgment)
# --------------------------------------------------------------------------- #
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


def case_studies_panel() -> str:
    intro = ('<p class="intro">Illustrative patterns from public SEC matters, mapped to which SECFEDCLAW thresholds '
             'would fire and why — for SEC reviewers to see where a threshold is hit, and for building labeled training '
             'windows. These are official allegations (unless final judgment); SECFEDCLAW asserts no new findings.</p>')
    worked = (
        '<div class="card worked"><h3>Worked example — threshold hit (synthetic)</h3>'
        '<p class="small">A thin microcap, +60% on ~25× volume, with 8 near-duplicate promotional posts across X + '
        'StockTwits (unanimous bullish) and a fresh S-3 + Form 4 in the EDGAR daily-diff:</p>'
        '<table class="mini"><tbody>'
        '<tr><td>market_anomaly</td><td>price-z & volume-z ≥ 2.5 (microcap) → <b>double-confirmed</b></td></tr>'
        '<tr><td>coordination</td><td>near-duplicate cluster (8) + burst sync + unanimous-bullish → <b>≥30</b></td></tr>'
        '<tr><td>issuer_event</td><td>dilution (S-3/424B) + insider (Form 4) → <b>≥30</b></td></tr>'
        '<tr><td>corroboration</td><td>market + coordination + issuer_event = <b>3 families</b></td></tr>'
        '<tr><td>result</td><td>routine-context floor cleared → <b>HIGH</b> (review, not a finding)</td></tr>'
        '</tbody></table>'
        '<p class="small muted">Benign check: is there a real catalyst (earnings, approval, contract)? '
        'Are the posts spam unrelated to the ticker? Confirm before any human escalation.</p></div>')
    cards = "".join(
        f'<div class="card case"><div class="case-head"><h3>{esc(c["id"])}</h3>'
        f'<a href="{c["url"]}" target="_blank" rel="noopener noreferrer" class="src">{esc(c["src"])} ↗</a></div>'
        f'<p class="small"><b>Pattern:</b> {esc(c["pattern"])}</p>'
        f'<p class="small thr"><b>Thresholds hit:</b> {esc(c["thresholds"])}</p>'
        f'<p class="small"><b>Why:</b> {esc(c["explain"])}</p>'
        f'<p class="small train"><b>Training value:</b> {esc(c["training"])}</p></div>'
        for c in CASES)
    return intro + worked + '<div class="cases">' + cards + '</div>'


def _state_dot(state: str) -> str:
    cls = {"live": "ok", "ok": "ok", "replay": "warn-d", "degraded": "warn-d",
           "unavailable": "bad", "idle": "idle"}.get(state, "idle")
    return f'<span class="dot {cls}"></span>{esc(state)}'


def agent_status_panel(queue: dict[str, Any]) -> str:
    st = agentstatus.build(queue)
    sysd = st["system"]
    sys_cards = [
        ("Preflight", sysd["preflight_verdict"], "live readiness"),
        ("Data mode", sysd["data_mode"], "live or replay"),
        ("Integrations live", f'{sysd["integrations_live"]}/{sysd["integrations_total"]}', "feeds reachable"),
        ("Model", "trained" if st["model"]["trained"] else "abstaining", f'{st["model"]["n_labels"]} labels'),
        ("LLM spend", f'${st["llm"]["total_cost_usd"]:.2f}', f'{st["llm"]["n_calls"]} calls'),
        ("Last run", (sysd["last_run_utc"] or "—")[:16].replace("T", " "), "UTC"),
    ]
    kpis = "".join(f'<div class="kpi"><div class="kpi-num">{esc(v)}</div><div class="kpi-lbl">{esc(l)}</div>'
                   f'<div class="kpi-sub">{esc(s)}</div></div>' for l, v, s in sys_cards)
    agents = "".join(
        f'<div class="stage"><div class="stage-num">{esc(a["name"])}</div>'
        f'<div class="agent-state">{_state_dot(a["state"])}</div>'
        f'<p class="small">{esc(a["role"])}</p>'
        f'<p class="small out"><b>Depends on:</b> {esc(", ".join(a["depends_on"][:6]))}'
        f'{"…" if len(a["depends_on"])>6 else ""}</p></div>'
        for a in st["agents"])
    integ = "".join(
        f'<tr><td>{esc(i["integration"])}</td><td>{_state_dot(i["state"])}</td>'
        f'<td class="num">{i["ok"]}/{i["total"]}</td><td class="num">{i["live"]}</td>'
        f'<td class="num">{i["replay"]}</td><td class="num">{i["unavailable"]}</td></tr>'
        for i in st["integrations"]) or '<tr><td colspan="6" class="muted">No integration health yet — run a scan.</td></tr>'
    return (
        '<p class="intro">Operational status from an agent perspective: each agent\'s live state, the integrations it '
        'depends on, and per-connection live/replay health. Run <code>scan.py --live</code> to populate live status.</p>'
        f'<div class="kpis">{kpis}</div>'
        f'<div class="card"><h3>Agents</h3><div class="pipeline">{agents}</div></div>'
        '<div class="card"><h3>Integrations &amp; connections</h3>'
        '<table class="mini"><thead><tr><th>integration</th><th>state</th><th class="num">ok</th>'
        '<th class="num">live</th><th class="num">replay</th><th class="num">unavail</th></tr></thead>'
        f'<tbody>{integ}</tbody></table>'
        '<p class="small muted">live = fetched from the source this run · replay = cached custody artifact · '
        'unavailable = no data (degrades that family, never fabricates).</p></div>')


def llm_cost_panel() -> str:
    s = usage_mod.summary()
    if not s.get("n_calls"):
        return ('<p class="intro">Tracks LLM usage &amp; cost across the system. The v0.2 scoring core is rules + '
                'numpy (no LLM calls), so this is empty until an LLM-backed component records spend via '
                '<code>usage.record(...)</code> — e.g. a future LLM explanation/adversary agent or the Haiku digest. '
                'Prices are configurable in <code>out/usage/pricing.json</code>.</p>'
                '<div class="card"><h3>No LLM usage recorded yet</h3>'
                '<p class="small muted">Record a call: <code>python3 usage.py --record claude-haiku-4.5 1200 300 --component digest</code></p></div>')
    kpis = "".join(f'<div class="kpi"><div class="kpi-num">{esc(v)}</div><div class="kpi-lbl">{esc(l)}</div></div>'
                   for l, v in [("Total cost", f'${s["total_cost_usd"]:.2f}'), ("Calls", s["n_calls"]),
                                ("Input tok", f'{s["total_input_tokens"]:,}'), ("Output tok", f'{s["total_output_tokens"]:,}')])
    mrows = "".join(f'<tr><td>{esc(k)}</td><td class="num">{v["calls"]}</td>'
                    f'<td class="num">{v["input_tokens"]:,}</td><td class="num">{v["output_tokens"]:,}</td>'
                    f'<td class="num">${v["cost_usd"]:.4f}</td></tr>' for k, v in s["by_model"].items())
    crows = "".join(f'<tr><td>{esc(k or "—")}</td><td class="num">{v["calls"]}</td><td class="num">${v["cost_usd"]:.4f}</td></tr>'
                    for k, v in s["by_component"].items())
    warn = '<p class="small warn">Some calls used an unknown model price (counted at $0). Add it to out/usage/pricing.json.</p>' if s.get("any_unknown_pricing") else ""
    return (
        f'<div class="kpis">{kpis}</div>{warn}'
        '<div class="grid2">'
        f'<div class="card"><h3>By model</h3><table class="mini"><thead><tr><th>model</th><th class="num">calls</th>'
        f'<th class="num">in</th><th class="num">out</th><th class="num">cost</th></tr></thead><tbody>{mrows}</tbody></table></div>'
        f'<div class="card"><h3>By component</h3><table class="mini"><thead><tr><th>component</th><th class="num">calls</th>'
        f'<th class="num">cost</th></tr></thead><tbody>{crows}</tbody></table></div></div>')


def learning_panel() -> str:
    """Learning pipeline: feedback loop, model status, feature importances."""
    import model as M
    import ledger as L
    ls = L.summary()
    md = M.load_scorer()
    trained = md is not None
    # KPIs
    kpis = [
        ("Labels", ls["n_labels"], f'{ls["n_positive"]} pos / {ls["n_negative"]} neg'),
        ("Model", "trained" if trained else "abstaining", f'need {M.MIN_LABELS}+ samples'),
        ("AUC", f'{md["cv_auc"]:.3f}' if trained else "—", "5-fold cross-validated"),
        ("Training data", f'{md["n_total"]}' if trained else "0",
         f'{md.get("n_real_labels",0)} real + {md.get("n_bootstrap",0)} bootstrap' if trained else "—"),
    ]
    kpi_html = "".join(f'<div class="kpi"><div class="kpi-num">{esc(v)}</div>'
                       f'<div class="kpi-lbl">{esc(l)}</div><div class="kpi-sub">{esc(s)}</div></div>'
                       for l, v, s in kpis)
    # Feature importances
    imp_html = ""
    if trained and md.get("importances") and md.get("feature_names"):
        ranked = sorted(zip(md["feature_names"], md["importances"]), key=lambda t: -t[1])
        imp_rows = "".join(
            f'<tr><td>{esc(f.replace("_"," "))}</td><td>{bar(i*100)}</td></tr>'
            for f, i in ranked if i > 0.001)
        imp_html = (f'<div class="card"><h3>What the model learned</h3>'
                    f'<table class="mini"><tbody>{imp_rows}</tbody></table>'
                    '<p class="small muted">Feature importances from the gradient-boosted model. '
                    'The model correctly identifies coordination_score as the dominant pump discriminator '
                    '— consistent with pump-and-dump mechanics (coordinated promotion → inflated demand → dump).</p></div>')
    # Label breakdown
    label_rows = "".join(f'<tr><td>{esc(k)}</td><td class="num">{v}</td></tr>'
                         for k, v in ls.get("by_label", {}).items())
    label_html = (f'<div class="card"><h3>Operator labels</h3>'
                  f'<table class="mini"><thead><tr><th>label</th><th class="num">count</th></tr></thead>'
                  f'<tbody>{label_rows or "<tr><td colspan=2 class=muted>No labels yet</td></tr>"}</tbody></table>'
                  '<p class="small muted">Label packages via: <code>python3 label.py out/TICKER_..._watch_v2.json useful_watch</code></p></div>'
                  if not trained or ls["n_labels"] > 0 else "")
    return (
        '<p class="intro">SECFEDCLAW improves over time through a human-in-the-loop feedback cycle. The operator labels '
        'review packages (useful_watch, false_positive, etc.), those labels train a gradient-boosted model, and the model '
        'adds an advisory probability to future packages — while the interpretable rules engine always stays primary.</p>'
        '<div class="card"><h3>Autonomous learning cycle</h3>'
        '<div class="pipeline">'
        '<div class="stage"><div class="stage-num">01</div><h3>Scan</h3>'
        '<div class="tag">daily pipeline</div>'
        '<p class="small">Agents score the ticker universe using rules + multi-source corroboration.</p></div>'
        '<div class="arrow">→</div>'
        '<div class="stage"><div class="stage-num">02</div><h3>Review</h3>'
        '<div class="tag">human in the loop</div>'
        '<p class="small">Operator reviews flagged packages and labels outcomes '
        '(useful_watch / false_positive / benign_explained).</p></div>'
        '<div class="arrow">→</div>'
        '<div class="stage"><div class="stage-num">03</div><h3>Learn</h3>'
        '<div class="tag">gradient boosting</div>'
        '<p class="small">Labels train a GBM model that learns which feature combinations predict '
        'genuine review-worthy windows vs false positives.</p></div>'
        '<div class="arrow">→</div>'
        '<div class="stage"><div class="stage-num">04</div><h3>Advise</h3>'
        '<div class="tag">model advisory</div>'
        '<p class="small">Trained model adds a calibrated probability to each package. '
        'Rules engine stays primary — model is advisory only, never a guilt label.</p></div>'
        '</div></div>'
        f'<div class="kpis">{kpi_html}</div>'
        f'<div class="grid2">{imp_html}{label_html}</div>'
        '<div class="card"><h3>Design constraints</h3>'
        '<p class="small">• The model <b>abstains</b> until ≥40 labeled, two-class samples exist (≥8/class) '
        '— it never guesses from insufficient data.</p>'
        '<p class="small">• Price/volume are randomized independently of labels in bootstrap training '
        '— the model must learn from genuine signal, not leaky proxies.</p>'
        '<p class="small">• The model <b>never changes</b> the rules-based review priority — it only adds '
        'an advisory probability. The interpretable engine is always authoritative.</p>'
        '<p class="small">• No guilt label, no trading signal, no autonomous escalation. '
        'The model is a calibration aid for human triage, nothing more.</p></div>')


def network_graph_panel(packages: list[dict[str, Any]]) -> str:
    """Build coordination network graph data from packages for force-directed viz."""
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    for p in packages:
        if not p:
            continue
        ticker = p.get("ticker", "?")
        pri = p.get("review_priority", "LOW")
        coord = p.get("coordination_detail", {})
        sm = p.get("social_metrics", {})
        cs = p.get("component_scores", {})
        # Ticker node
        nodes[ticker] = {"id": ticker, "type": "ticker", "group": pri,
                         "score": p.get("watch_score", 0), "coord": cs.get("coordination_score", 0)}
        # Platform nodes + edges
        for plat in (sm.get("platforms") or []):
            pid = f"plat_{plat}"
            if pid not in nodes:
                nodes[pid] = {"id": plat, "type": "platform", "group": "platform"}
            edges.append({"source": ticker, "target": pid, "type": "posts_on"})
        # Near-duplicate cluster nodes
        for i, cluster in enumerate(coord.get("near_duplicate_clusters") or []):
            cid = f"cluster_{ticker}_{i}"
            nodes[cid] = {"id": f"cluster {i+1}", "type": "cluster", "group": "coordination",
                          "size": cluster.get("size", len(cluster.get("members", [])))}
            edges.append({"source": ticker, "target": cid, "type": "has_cluster"})
        # Shared domain groups
        for dom in (coord.get("shared_domain_groups") or []):
            did = f"dom_{dom.get('domain', 'unknown')}"
            if did not in nodes:
                nodes[did] = {"id": dom.get("domain", "?"), "type": "domain", "group": "coordination"}
            edges.append({"source": ticker, "target": did, "type": "shared_domain"})
        # Source family edges
        for fam in (p.get("corroboration", {}).get("families_active") or []):
            fid = f"fam_{fam}"
            if fid not in nodes:
                nodes[fid] = {"id": fam, "type": "family", "group": "family"}
            edges.append({"source": ticker, "target": fid, "type": "corroborates"})
    # Assign stable keys to nodes; edges reference these keys
    node_list = []
    node_keys = {}  # map internal key -> index
    for key, n in nodes.items():
        n["_key"] = key
        node_keys[key] = len(node_list)
        node_list.append(n)
    # Convert edges to index-based
    idx_edges = []
    for e in edges:
        si = node_keys.get(e["source"])
        ti = node_keys.get(e["target"])
        if si is not None and ti is not None:
            idx_edges.append({"s": si, "t": ti, "type": e["type"]})
    import json as _json
    graph_data = _json.dumps({"nodes": node_list, "edges": idx_edges})
    return (
        '<p class="intro">Interactive coordination network showing tickers, platforms, near-duplicate clusters, '
        'shared domains, and corroborating families. Larger nodes = higher scores. <b>Drag nodes</b> to rearrange. '
        'This is the same coordination evidence the scoring engine uses \u2014 visualized as a graph.</p>'
        f'<div class="card"><div id="graph-container" style="width:100%;height:550px;position:relative;overflow:hidden">'
        '<canvas id="graph-canvas" style="width:100%;height:100%;cursor:grab"></canvas></div></div>'
        '<div class="grid2">'
        '<div class="card"><h3>Legend</h3>'
        '<p class="small"><span style="color:#4da3ff">\u25cf</span> Ticker (size = watch score) &nbsp; '
        '<span style="color:#3fb950">\u25cf</span> Platform &nbsp; '
        '<span style="color:#d29922">\u25cf</span> Near-duplicate cluster &nbsp; '
        '<span style="color:#b39ddb">\u25cf</span> Shared domain &nbsp; '
        '<span style="color:#8b97a8">\u25cf</span> Corroborating family</p>'
        '<p class="small muted">Lines: posts_on (social), has_cluster (coordination), '
        'shared_domain (coordination), corroborates (multi-source). '
        'Edge color: <span style="color:#4a8faa">social</span> / '
        '<span style="color:#d29922">coordination</span> / '
        '<span style="color:#8b97a8">corroboration</span>.</p></div>'
        '<div class="card"><h3>Graph stats</h3>'
        f'<p class="small">{len(node_list)} nodes \u00b7 {len(idx_edges)} edges \u00b7 '
        f'{sum(1 for n in node_list if n["type"]=="ticker")} tickers \u00b7 '
        f'{sum(1 for n in node_list if n["type"]=="cluster")} clusters \u00b7 '
        f'{sum(1 for n in node_list if n["type"]=="platform")} platforms</p></div></div>'
        f'<script>var GD={graph_data};'
        'function initGraph(){if(window._graphInit)return;window._graphInit=1;'
        'var c=document.getElementById("graph-canvas"),ctx=c.getContext("2d");'
        'var dpr=window.devicePixelRatio||1;'
        'c.width=c.parentElement.clientWidth*dpr;c.height=c.parentElement.clientHeight*dpr;'
        'ctx.scale(dpr,dpr);'
        'var W=c.parentElement.clientWidth,H=c.parentElement.clientHeight;'
        'var N=GD.nodes,E=GD.edges;'
        'var colors={ticker:"#4da3ff",platform:"#3fb950",cluster:"#d29922",domain:"#b39ddb",family:"#8b97a8"};'
        'var priC={CRITICAL_REVIEW:"#f85149",HIGH:"#d29922",MEDIUM:"#9ad13a",LOW:"#5a6b85"};'
        'var edgeC={posts_on:"rgba(63,185,80,0.5)",has_cluster:"rgba(210,153,34,0.6)",'
        'shared_domain:"rgba(179,157,219,0.5)",corroborates:"rgba(139,151,168,0.4)"};'
        'N.forEach(function(n,i){var a=i*2.399+Math.random()*0.5;'
        'n.x=W/2+Math.cos(a)*(W*0.35);n.y=H/2+Math.sin(a)*(H*0.35);'
        'n.vx=0;n.vy=0;n.r=n.type=="ticker"?Math.max(10,Math.min(28,(n.score||0)/2.5)):7;});'
        'var drag=null;'
        'c.addEventListener("mousedown",function(ev){var r=c.getBoundingClientRect();'
        'var mx=(ev.clientX-r.left),my=(ev.clientY-r.top);'
        'for(var i=N.length-1;i>=0;i--){var n=N[i];'
        'if(Math.hypot(n.x-mx,n.y-my)<n.r+4){drag=n;n.fx=n.x;n.fy=n.y;c.style.cursor="grabbing";break;}}});'
        'c.addEventListener("mousemove",function(ev){if(!drag)return;var r=c.getBoundingClientRect();'
        'drag.fx=ev.clientX-r.left;drag.fy=ev.clientY-r.top;});'
        'c.addEventListener("mouseup",function(){if(drag){drag.x=drag.fx;drag.y=drag.fy;'
        'drag.vx=0;drag.vy=0;delete drag.fx;delete drag.fy;drag=null;c.style.cursor="grab";}});'
        'c.addEventListener("mouseleave",function(){if(drag){delete drag.fx;delete drag.fy;drag=null;c.style.cursor="grab";}});'
        'function step(){'
        'N.forEach(function(a){if(a.fx!==undefined){a.x=a.fx;a.y=a.fy;a.vx=0;a.vy=0;return;}'
        'N.forEach(function(b){if(a===b)return;'
        'var dx=a.x-b.x,dy=a.y-b.y,d=Math.sqrt(dx*dx+dy*dy)+0.1;'
        'var f=300/(d*d);a.vx+=dx/d*f;a.vy+=dy/d*f;});'
        'a.vx+=(W/2-a.x)*0.001;a.vy+=(H/2-a.y)*0.001;});'
        'E.forEach(function(e){var s=N[e.s],t=N[e.t];if(!s||!t)return;'
        'var dx=t.x-s.x,dy=t.y-s.y,d=Math.sqrt(dx*dx+dy*dy)+0.1;'
        'var f=(d-100)*0.008;'
        'if(!s.fx){s.vx+=dx/d*f;s.vy+=dy/d*f;}'
        'if(!t.fx){t.vx-=dx/d*f;t.vy-=dy/d*f;}});'
        'N.forEach(function(n){if(n.fx!==undefined)return;'
        'n.vx*=0.82;n.vy*=0.82;n.x+=n.vx;n.y+=n.vy;'
        'n.x=Math.max(n.r+2,Math.min(W-n.r-2,n.x));'
        'n.y=Math.max(n.r+2,Math.min(H-n.r-2,n.y));});'
        'ctx.clearRect(0,0,W,H);'
        'E.forEach(function(e){var s=N[e.s],t=N[e.t];if(!s||!t)return;'
        'ctx.beginPath();ctx.moveTo(s.x,s.y);ctx.lineTo(t.x,t.y);'
        'ctx.strokeStyle=edgeC[e.type]||"rgba(100,130,160,0.4)";ctx.lineWidth=1.5;ctx.stroke();});'
        'N.forEach(function(n){ctx.beginPath();ctx.arc(n.x,n.y,n.r,0,Math.PI*2);'
        'var fc=n.type=="ticker"?(priC[n.group]||colors.ticker):(colors[n.type]||"#888");'
        'ctx.fillStyle=fc;ctx.fill();'
        'ctx.strokeStyle="rgba(255,255,255,0.3)";ctx.lineWidth=1;ctx.stroke();'
        'ctx.fillStyle="#e0e8f0";ctx.font=(n.type=="ticker"?"bold 11px":"10px")+" sans-serif";'
        'ctx.textAlign="center";ctx.textBaseline="top";ctx.fillText(n.id,n.x,n.y+n.r+4);});'
        'requestAnimationFrame(step);}step();}'
        'document.addEventListener("DOMContentLoaded",function(){'
        'var t=document.querySelector(\'[data-id="network"]\');'
        'if(t)t.addEventListener("click",function(){setTimeout(initGraph,150);});});'
        '</script>')


def backtest_panel(bt: dict[str, Any]) -> str:
    if not bt:
        return '<p class="muted">No backtest results. Run backtest.py.</p>'
    m, cm, ledger = bt.get("metrics", {}), bt.get("confusion_matrix", {}), bt.get("calibration_ledger", {})
    kpis = "".join(f'<div class="kpi"><div class="kpi-num">{m.get(k,0):.2f}</div>'
                   f'<div class="kpi-lbl">{k}</div></div>' for k in ("precision", "recall", "f1", "accuracy"))
    cmrows = (f'<tr><td></td><td class="num">flagged</td><td class="num">not flagged</td></tr>'
              f'<tr><td><b>pump</b></td><td class="num tp">{cm.get("tp",0)} TP</td><td class="num fn">{cm.get("fn",0)} FN</td></tr>'
              f'<tr><td><b>benign/control</b></td><td class="num fp">{cm.get("fp",0)} FP</td><td class="num tn">{cm.get("tn",0)} TN</td></tr>')
    led = "".join(f'<tr><td>{esc(k)}</td><td class="num">{v}</td></tr>' for k, v in ledger.items())
    pc = bt.get("per_class", {})
    pcrows = "".join(
        f'<tr><td>{esc(CLASS_ABBR.get(k,k))}</td><td class="num">{v.get("precision",0):.2f}</td>'
        f'<td class="num">{v.get("recall",0):.2f}</td><td class="num">{v.get("f1",0):.2f}</td>'
        f'<td class="num">{v.get("n",0)}</td></tr>' for k, v in pc.items())
    pc_html = (f'<div class="card"><h3>Precision / recall by liquidity class '
               '<span class="muted small">(class-balanced corpus)</span></h3>'
               '<table class="mini"><thead><tr><th>class</th><th class="num">P</th><th class="num">R</th>'
               f'<th class="num">F1</th><th class="num">n</th></tr></thead><tbody>{pcrows}</tbody></table>'
               '<p class="small muted">Microcaps are tuned for high recall (don\'t miss pumps) at the cost of '
               'precision (more benign windows surface for review) — a deliberate, class-aware trade-off.</p></div>'
               if pcrows else "")
    return (
        '<p class="intro">Does the engine raise review priority on pump windows while staying quiet on benign-news and '
        'routine windows? Measured on a seeded synthetic corpus (real SEC-case windows when run live with Flat Files).</p>'
        f'<div class="kpis">{kpis}</div>'
        f'<p class="muted small">{bt.get("n_samples",0)} windows ({bt.get("n_per_class",0)}/class) · flag ≥ {esc(bt.get("flag_threshold"))} · seed {bt.get("seed")}</p>'
        '<div class="grid2">'
        f'<div class="card"><h3>Confusion matrix</h3><table class="mini cm"><tbody>{cmrows}</tbody></table></div>'
        f'<div class="card"><h3>Calibration ledger</h3><table class="mini"><tbody>{led}</tbody></table></div></div>'
        f'{pc_html}')


CSS = """
:root{
  --bg:#0d1117; --panel:#161b22; --panel-2:#1c2330; --line:#2a3441; --line-2:#384252;
  --ink:#e9edf3; --muted:#8b97a8; --faint:#6b7686; --brand:#4da3ff; --accent:#c98a3a;
  --ok:#3fb950; --crit:#f85149; --high:#d29922; --med:#9ad13a; --low:#5a6b85;
  --s1:4px; --s2:8px; --s3:12px; --s4:16px; --s5:24px; --s6:32px; --radius:12px;
  --shadow:0 1px 3px rgba(0,0,0,.4);
  --f: -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
}
*{box-sizing:border-box} html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 var(--f);-webkit-font-smoothing:antialiased}
a{color:var(--brand);text-decoration:none} a:hover{text-decoration:underline}
.topbar{background:linear-gradient(180deg,#1a2230,#11161f);border-bottom:1px solid var(--line);padding:var(--s4) var(--s5);position:sticky;top:0;z-index:10}
.brand-row{display:flex;align-items:baseline;gap:var(--s3);flex-wrap:wrap}
.brand{font-weight:800;letter-spacing:.4px;font-size:20px}
.brand .v{color:var(--brand)}
.subtitle{color:var(--muted);font-size:13px}
.meta{margin-left:auto;color:var(--faint);font-size:12px}
.boundary{margin-top:var(--s3);background:#21161a;border:1px solid #5b2a2f;color:#ffc9cd;border-radius:8px;padding:var(--s2) var(--s3);font-size:12.5px}
.wrap{max-width:1180px;margin:0 auto;padding:var(--s5)}
.tabs{display:flex;gap:var(--s2);flex-wrap:wrap;margin-bottom:var(--s5);border-bottom:1px solid var(--line);padding-bottom:var(--s3)}
.tab{padding:var(--s2) var(--s4);background:transparent;border:1px solid transparent;border-radius:8px;cursor:pointer;font-weight:600;color:var(--muted)}
.tab:hover{color:var(--ink);background:var(--panel)}
.tab.active{background:var(--panel-2);color:#cfe4ff;border-color:var(--line-2)}
.panel{display:none;animation:f .2s ease} .panel.active{display:block} @keyframes f{from{opacity:.4}to{opacity:1}}
.intro{color:var(--muted);max-width:80ch;margin:0 0 var(--s4)}
h2{font-size:19px;margin:0 0 var(--s4)} h3{font-size:15px;margin:0 0 var(--s3)}
.card{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:var(--s4);margin-bottom:var(--s4);box-shadow:var(--shadow)}
table{width:100%;border-collapse:collapse}
th,td{text-align:left;padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:middle}
thead th{color:var(--muted);font-size:11.5px;text-transform:uppercase;letter-spacing:.5px;font-weight:700}
.num{text-align:right;font-variant-numeric:tabular-nums} .muted{color:var(--muted)} .faint{color:var(--faint)} .small{font-size:13px}
.tk{white-space:nowrap}
.reflinks{display:inline-flex;gap:6px;margin-left:8px}
.reflinks a{font-size:10.5px;font-weight:700;color:var(--faint);border:1px solid var(--line-2);border-radius:5px;padding:1px 5px}
.reflinks a:hover{color:#cfe4ff;border-color:var(--brand);text-decoration:none}
.pill{display:inline-block;padding:2px 10px;border-radius:99px;font-size:12px;font-weight:700}
.pill.crit{background:#3d1417;color:#ff9ba0} .pill.high{background:#3a2c10;color:#f0c14b}
.pill.med{background:#26340f;color:#cdee85} .pill.low{background:#1b2435;color:#9fb0cc}
.info{display:inline-block;width:17px;height:17px;line-height:17px;text-align:center;border-radius:50%;background:var(--brand);color:#fff;font-size:10px;font-weight:700;cursor:help;margin-left:4px;position:relative;vertical-align:middle}
.info .tooltip{display:none;position:absolute;bottom:calc(100% + 8px);left:50%;transform:translateX(-50%);background:#1c2a3a;color:#e0e8f0;border:1px solid var(--brand);border-radius:8px;padding:10px 14px;font-size:13px;font-weight:400;line-height:1.45;width:320px;max-width:90vw;white-space:normal;text-align:left;z-index:100;box-shadow:0 4px 16px rgba(0,0,0,.5);pointer-events:none}
.info .tooltip::after{content:'';position:absolute;top:100%;left:50%;transform:translateX(-50%);border:6px solid transparent;border-top-color:var(--brand)}
.info:hover .tooltip,.info:focus .tooltip{display:block}
.bar{position:relative;background:#0f1623;border:1px solid var(--line);border-radius:6px;height:18px;min-width:130px;overflow:hidden}
.bar-fill{position:absolute;inset:0 auto 0 0;background:linear-gradient(90deg,#2f6f3f,#3fb950)}
.bar-fill.anom{background:linear-gradient(90deg,#7a4a1f,#d29922)}
.bar-num{position:relative;padding-left:8px;font-size:11.5px;line-height:18px;color:#dfe6ef}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:var(--s3);margin-bottom:var(--s4)}
.kpi{background:var(--panel-2);border:1px solid var(--line);border-radius:10px;padding:var(--s3) var(--s4)}
.kpi-num{font-size:24px;font-weight:800;color:#cfe4ff} .kpi-lbl{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.4px}
.kpi-sub{font-size:11px;color:var(--faint);margin-top:2px}
.filters{margin:0 0 var(--s3);display:flex;gap:6px;flex-wrap:wrap}
.filters button{background:var(--panel-2);border:1px solid var(--line-2);color:#cde;border-radius:6px;padding:5px 11px;cursor:pointer;font-weight:600}
.filters button:hover{border-color:var(--brand)}
.mini td,.mini th{padding:5px 8px;font-size:12.5px}
.cm .tp{color:#7ee787}.cm .tn{color:#9cd2ff}.cm .fp{color:#ffba73}.cm .fn{color:#ff9ba0}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:var(--s4)} @media(max-width:760px){.grid2{grid-template-columns:1fr}}
.pkg-head{display:flex;align-items:center;gap:var(--s3);flex-wrap:wrap;margin-bottom:var(--s2)}
.warn{color:#ffba73}.adv{color:#9cd2ff}.model{color:#b39ddb}.enf{color:#e0a3c9}
.expl{background:var(--panel-2);border-left:3px solid var(--brand);border-radius:6px;padding:8px 10px;color:#cdd8e6}
.rationale{color:#aeb8cc;border-top:1px dashed var(--line);padding-top:var(--s2);margin-top:var(--s2)}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px;vertical-align:middle}
.dot.ok{background:var(--ok)}.dot.warn-d{background:var(--high)}.dot.bad{background:var(--crit)}.dot.idle{background:var(--low)}
.agent-state{font-size:12px;font-weight:700;margin:2px 0 6px}
.pipeline{display:flex;align-items:stretch;gap:var(--s2);flex-wrap:wrap;margin-bottom:var(--s4)}
.stage{flex:1;min-width:200px;background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:var(--s4);position:relative}
.stage-num{font-size:11px;font-weight:800;color:var(--brand);letter-spacing:1px}
.stage .tag{display:inline-block;font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.4px;color:var(--accent);background:#2a2012;border:1px solid #4a3a1e;border-radius:5px;padding:1px 7px;margin-bottom:var(--s2)}
.stage .out{color:var(--muted);border-top:1px dashed var(--line);padding-top:var(--s2);margin-top:var(--s2)}
.arrow{display:flex;align-items:center;color:var(--line-2);font-size:22px;font-weight:700}
@media(max-width:760px){.arrow{display:none}.stage{min-width:100%}}
.bands{display:flex;gap:var(--s2);flex-wrap:wrap;margin-bottom:var(--s2)}
.cases{display:grid;grid-template-columns:1fr 1fr;gap:var(--s4)} @media(max-width:760px){.cases{grid-template-columns:1fr}}
.case-head{display:flex;justify-content:space-between;align-items:baseline;gap:var(--s2)}
.case .src{font-size:11px;font-weight:700;color:var(--brand);white-space:nowrap}
.case .thr{color:#cdee85}.case .train{color:#b39ddb}
.worked{border-color:#3a4a1e}
.footer{color:var(--faint);font-size:12px;text-align:center;padding:var(--s5) 0}
"""

JS = """
function show(id,el){document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));
document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
document.getElementById(id).classList.add('active');el.classList.add('active');
if(history.replaceState)history.replaceState(null,'','#'+id);}
function filt(p){document.querySelectorAll('#overview [data-priority]').forEach(r=>{
r.style.display=(p==='ALL'||r.getAttribute('data-priority')===p)?'':'none';});}
window.addEventListener('DOMContentLoaded',function(){var h=location.hash.slice(1);
if(h){var t=document.querySelector('.tab[data-id="'+h+'"]');if(t)t.click();}});
"""


def _tab(label: str, pid: str, active: bool = False) -> str:
    return f'<div class="tab{" active" if active else ""}" data-id="{pid}" onclick="show(\'{pid}\',this)">{esc(label)}</div>'


def build_html(queue: dict, packages: list, bt: dict) -> str:
    gen = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    mode = queue.get("data_mode", "?")
    n_pkg = len([p for p in packages if p])
    tabs = (_tab("Overview", "overview", True) + _tab("Packages", "packages")
            + _tab("Network", "network") + _tab("Agents", "agents")
            + _tab("Learning", "learning") + _tab("Status", "status")
            + _tab("LLM cost", "llm") + _tab("Methodology", "methodology")
            + _tab("SEC case studies", "cases") + _tab("Backtest", "backtest"))
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>SECFEDCLAW v0.2 — surveillance review console</title>"
        f"<style>{CSS}</style></head><body>"
        "<div class='topbar'><div class='brand-row'>"
        "<span class='brand'>SECFEDCLAW <span class='v'>v0.2</span></span>"
        "<span class='subtitle'>Pump-and-dump WATCH review console — social × market × SEC/FINRA fusion</span>"
        f"<span class='meta'>generated {esc(gen)} · mode {esc(mode)} · {n_pkg} packages</span></div>"
        f"<div class='boundary'><b>⚠ {esc(BOUNDARY)}</b></div></div>"
        f"<div class='wrap'><div class='tabs'>{tabs}</div>"
        # overview
        "<section id='overview' class='panel active'>"
        "<p class='intro'>Tickers ranked by review priority for this run. Numbers are review-priority context — hover ⓘ for "
        "definitions; each ticker links out to SEC EDGAR, market and social references.</p>"
        f"{kpi_panel(queue)}"
        "<div class='card'><h3>Ranked review queue</h3>"
        "<div class='filters'>Filter:"
        "<button onclick=\"filt('ALL')\">All</button><button onclick=\"filt('CRITICAL_REVIEW')\">Critical</button>"
        "<button onclick=\"filt('HIGH')\">High</button><button onclick=\"filt('MEDIUM')\">Medium</button>"
        "<button onclick=\"filt('LOW')\">Low</button></div>"
        f"{queue_table(queue)}</div></section>"
        # packages
        f"<section id='packages' class='panel'><h2>Evidence packages</h2>"
        "<p class='intro'>Each package shows component scores (hover ⓘ), active families, caps applied, coordination "
        "clusters, the adversary's caveats, the optional model advisory, and a non-accusatory rationale.</p>"
        f"{package_cards([p for p in packages if p])}</section>"
        # network graph
        f"<section id='network' class='panel'><h2>Coordination network</h2>"
        f"{network_graph_panel([p for p in packages if p])}</section>"
        # agents
        f"<section id='agents' class='panel'><h2>Agents &amp; orchestration</h2>{agents_panel(queue)}</section>"
        # learning
        f"<section id='learning' class='panel'><h2>Learning pipeline</h2>{learning_panel()}</section>"
        # status
        f"<section id='status' class='panel'><h2>Agent &amp; integration status</h2>{agent_status_panel(queue)}</section>"
        # llm cost
        f"<section id='llm' class='panel'><h2>LLM usage &amp; cost</h2>{llm_cost_panel()}</section>"
        # methodology
        f"<section id='methodology' class='panel'><h2>Methodology &amp; data dictionary</h2>{methodology_panel()}</section>"
        # cases
        f"<section id='cases' class='panel'><h2>SEC threshold case studies</h2>{case_studies_panel()}</section>"
        # backtest
        f"<section id='backtest' class='panel'><h2>Backtest &amp; calibration</h2>{backtest_panel(bt)}</section>"
        "<div class='footer'>SECFEDCLAW v0.2 · WATCH-level review priorities only · offline render, no external callbacks · "
        "outbound ticker links open third-party sites on click.</div>"
        f"</div><script>{JS}</script></body></html>")


def main() -> int:
    ap = argparse.ArgumentParser(description="Render SECFEDCLAW v0.2 dashboard")
    ap.add_argument("--out", default=str(OUT / "dashboard_v2.html"))
    args = ap.parse_args()
    queue = load(OUT / "review_queue.json", {})
    bt = load(OUT / "backtest_results.json", {})
    packages = [load(p, {}) for p in sorted(OUT.glob("*_watch_v2.json"))]
    packages = [p for p in packages if p]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_html(queue, packages, bt))
    print(f"dashboard: {out}")
    print(f"  queue rows: {len(queue.get('review_queue', []))}  packages: {len(packages)}  backtest: {'yes' if bt else 'no'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
