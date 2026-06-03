#!/usr/bin/env python3
"""SECFEDCLAW v0.2 dashboard generator.

Offline-only renderer (inline CSS/JS, no external JS/CSS/images/network
callbacks — same constraint as the production dashboard) over the v0.2
artifacts: the ranked review queue, per-ticker WATCH packages, and the
backtest/calibration results.

Output: secfedclaw_v2/out/dashboard_v2.html
"""
from __future__ import annotations

import argparse
import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

OUT = Path(__file__).resolve().parent / "out"

PRIORITY_CLASS = {"CRITICAL_REVIEW": "crit", "HIGH": "high", "MEDIUM": "med", "LOW": "low"}
SOUL_BOUNDARY = ("Operational boundary: SECFEDCLAW detects, analyzes, packages, and recommends for "
                 "authorized human review only. Any freeze, legal process, regulator contact, trading "
                 "action, or external escalation requires separate lawful human authorization.")


def esc(v: Any) -> str:
    return html.escape(str(v), quote=True)


def load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(errors="replace"))
    except Exception:
        return default


def _pill(priority: str) -> str:
    cls = PRIORITY_CLASS.get(priority, "low")
    return f'<span class="pill {cls}">{esc(priority)}</span>'


def _bar(value: float, cap: float = 100.0, cls: str = "") -> str:
    pct = max(0.0, min(100.0, value / cap * 100))
    return (f'<div class="bar"><div class="bar-fill {cls}" style="width:{pct:.0f}%"></div>'
            f'<span class="bar-num">{value:.1f}</span></div>')


CLASS_ABBR = {"thin_microcap": "thin/μcap", "small_cap": "small", "mid_cap": "mid",
              "large_cap": "large", "unknown": "?"}


def queue_rows(queue: dict[str, Any]) -> str:
    rows = []
    for r in queue.get("review_queue", []):
        if "error" in r:
            rows.append(f'<tr><td>{esc(r["ticker"])}</td><td colspan="7" class="muted">error: {esc(r["error"])}</td></tr>')
            continue
        cls = CLASS_ABBR.get(r.get("security_class"), esc(r.get("security_class") or "?"))
        rows.append(
            f'<tr data-priority="{esc(r["review_priority"])}">'
            f'<td><b>{esc(r["ticker"])}</b></td>'
            f'<td>{_pill(r["review_priority"])}</td>'
            f'<td>{_bar(r.get("watch_score",0))}</td>'
            f'<td>{_bar(r.get("anomaly_evidence_score",0), cls="anom")}</td>'
            f'<td class="num">{r.get("evidence_quality_score",0):.0f}</td>'
            f'<td class="num">{r.get("n_families_active",0)}</td>'
            f'<td class="muted small">{cls}</td>'
            f'<td class="muted">{esc(r.get("data_mode","?"))}</td></tr>')
    return "".join(rows) or '<tr><td colspan="8" class="muted">No review queue found. Run scan.py first.</td></tr>'


def kpi_panel(queue: dict[str, Any], packages: list[dict[str, Any]]) -> str:
    q = queue.get("review_queue", [])
    valid = [r for r in q if "error" not in r]
    universe = queue.get("universe_size", len(q))
    dist = {p: sum(1 for r in valid if r.get("review_priority") == p)
            for p in ("CRITICAL_REVIEW", "HIGH", "MEDIUM", "LOW")}
    flagged = dist["CRITICAL_REVIEW"] + dist["HIGH"] + dist["MEDIUM"]
    mean_anom = round(sum(r.get("anomaly_evidence_score", 0) for r in valid) / len(valid), 1) if valid else 0
    score_ready = round(len(valid) / universe * 100, 0) if universe else 0
    kpis = [
        ("universe", universe), ("scored", len(valid)),
        ("score-ready %", f"{score_ready:.0f}%"), ("flagged ≥MED", flagged),
        ("CRITICAL", dist["CRITICAL_REVIEW"]), ("HIGH", dist["HIGH"]),
        ("mean anomaly", mean_anom), ("mode", queue.get("data_mode", "?")),
    ]
    cards = "".join(f'<div class="kpi"><div class="kpi-num">{esc(v)}</div>'
                    f'<div class="kpi-lbl">{esc(k)}</div></div>' for k, v in kpis)
    return f'<div class="kpis">{cards}</div>'


def source_health_panel(queue: dict[str, Any]) -> str:
    agg: dict[str, dict[str, int]] = {}
    for r in queue.get("review_queue", []):
        for src, h in (r.get("source_health") or {}).items():
            a = agg.setdefault(src, {"ok": 0, "total": 0, "live": 0, "replay": 0})
            a["total"] += 1
            if h.get("ok"):
                a["ok"] += 1
            if h.get("mode") == "live":
                a["live"] += 1
            elif h.get("mode") == "replay":
                a["replay"] += 1
    if not agg:
        return ""
    rows = "".join(
        f'<tr><td>{esc(s)}</td><td class="num">{v["ok"]}/{v["total"]}</td>'
        f'<td class="num">{v["live"]}</td><td class="num">{v["replay"]}</td></tr>'
        for s, v in sorted(agg.items()))
    return ('<div class="card"><h3>Source health (across scanned tickers)</h3>'
            '<table class="mini"><tr><th>source</th><th class="num">ok</th>'
            f'<th class="num">live</th><th class="num">replay</th></tr>{rows}</table></div>')


def package_cards(packages: list[dict[str, Any]]) -> str:
    cards = []
    for p in sorted(packages, key=lambda d: d.get("watch_score", 0), reverse=True)[:30]:
        comp = p.get("component_scores", {})
        comp_rows = "".join(
            f'<tr><td>{esc(k)}</td><td>{_bar(v)}</td></tr>' for k, v in comp.items())
        corr = p.get("corroboration", {})
        caps = p.get("score_caps_applied", []) or ["none"]
        adv = p.get("adversarial_review", {}).get("caveats", [])
        coord = p.get("coordination_detail", {})
        clusters = coord.get("near_duplicate_clusters", [])
        benign = p.get("benign_explanation_review", {})
        cards.append(
            f'<div class="card pkg" data-priority="{esc(p.get("review_priority"))}">'
            f'<div class="pkg-head"><h3>{esc(p.get("ticker"))}</h3>{_pill(p.get("review_priority","LOW"))}'
            f'<span class="muted">score {p.get("watch_score",0):.1f} · anomaly {p.get("anomaly_evidence_score",0):.1f} · '
            f'evq {p.get("evidence_quality_score",0):.0f} · {esc(p.get("data_mode","?"))}</span></div>'
            f'<table class="mini">{comp_rows}</table>'
            f'<p class="muted small">families active: {esc(", ".join(corr.get("families_active",[])) or "none")} '
            f'(×{corr.get("corroboration_multiplier","?")})</p>'
            f'<p class="small"><b>Caps:</b> {esc("; ".join(caps))}</p>'
            f'<p class="small"><b>Benign:</b> strength {benign.get("benign_explanation_strength",0)} — '
            f'{esc("; ".join(benign.get("indicators",[])[:2]))}</p>'
            + (f'<p class="small warn"><b>Coordination clusters:</b> {len(clusters)} '
               f'(max size {coord.get("max_posts_in_burst",0)} burst)</p>' if clusters else "")
            + f'<p class="small adv"><b>Adversary:</b> {esc("; ".join(adv[:2]))}</p>'
            f'<p class="small rationale">{esc(p.get("non_accusatory_rationale",""))}</p>'
            '</div>')
    return "".join(cards) or '<p class="muted">No packages yet. Run scan.py.</p>'


def backtest_panel(bt: dict[str, Any]) -> str:
    if not bt:
        return '<p class="muted">No backtest results. Run backtest.py.</p>'
    m = bt.get("metrics", {})
    cm = bt.get("confusion_matrix", {})
    ledger = bt.get("calibration_ledger", {})
    kpis = "".join(
        f'<div class="kpi"><div class="kpi-num">{m.get(k,0):.3f}</div><div class="kpi-lbl">{k}</div></div>'
        for k in ("precision", "recall", "f1", "accuracy"))
    cmrows = (f'<tr><td></td><td class="num">flagged</td><td class="num">not flagged</td></tr>'
              f'<tr><td><b>pump</b></td><td class="num tp">{cm.get("tp",0)} TP</td><td class="num fn">{cm.get("fn",0)} FN</td></tr>'
              f'<tr><td><b>benign/control</b></td><td class="num fp">{cm.get("fp",0)} FP</td><td class="num tn">{cm.get("tn",0)} TN</td></tr>')
    ledrows = "".join(f'<tr><td>{esc(k)}</td><td class="num">{v}</td></tr>' for k, v in ledger.items())
    cases = "".join(
        f'<tr><td>{esc(c["case_id"])}</td><td class="small">{esc(c["pattern"])}</td>'
        f'<td class="small">{esc(c.get("tickers") or "(supply for live run)")}</td></tr>'
        for c in bt.get("sec_case_corpus", []))
    return (
        f'<div class="kpis">{kpis}</div>'
        f'<p class="muted small">Harness: {esc(bt.get("harness"))} · {bt.get("n_samples",0)} windows '
        f'({bt.get("n_per_class",0)}/class) · flag ≥ {esc(bt.get("flag_threshold"))} · seed {bt.get("seed")}</p>'
        '<div class="grid2">'
        f'<div class="card"><h3>Confusion matrix</h3><table class="mini cm">{cmrows}</table></div>'
        f'<div class="card"><h3>Calibration ledger</h3><table class="mini">{ledrows}</table></div>'
        '</div>'
        f'<div class="card"><h3>Public SEC case corpus (metadata only)</h3>'
        f'<table class="mini"><tr><th>case</th><th>alleged pattern</th><th>tickers</th></tr>{cases}</table>'
        '<p class="muted small">Allegations unless final judgment. Supply tickers/windows for a live Polygon-backed run.</p></div>'
    )


CSS = """
*{box-sizing:border-box}body{margin:0;font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;background:#0f1115;color:#e6e9ef}
.topbar{background:#151924;border-bottom:1px solid #2a3142;padding:12px 20px;position:sticky;top:0;z-index:5}
.brand{font-weight:700;letter-spacing:.5px;font-size:16px;display:inline-block;margin-right:12px}
.wrap{max-width:1180px;margin:0 auto;padding:20px}
.pill{display:inline-block;padding:2px 9px;border-radius:99px;font-size:12px;font-weight:600;background:#243; color:#bdf}
.pill.crit{background:#5b1620;color:#ffb3bd}.pill.high{background:#5b3a16;color:#ffd6a3}
.pill.med{background:#3a4a16;color:#dfffa3}.pill.low{background:#1f2738;color:#9fb0cc}
.pill.ok{background:#143;color:#9fe}
h2{margin:6px 0 14px;font-size:18px}h3{margin:0 0 8px;font-size:15px}
.card{background:#151924;border:1px solid #2a3142;border-radius:10px;padding:16px;margin-bottom:16px}
table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:7px 8px;border-bottom:1px solid #232a39;vertical-align:middle}
th{color:#8aa;font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.4px}
.num{text-align:right;font-variant-numeric:tabular-nums}.muted{color:#7d8aaa}.small{font-size:12px}
.bar{position:relative;background:#1f2738;border-radius:5px;height:18px;min-width:120px}
.bar-fill{position:absolute;left:0;top:0;bottom:0;background:#3b6;border-radius:5px}
.bar-fill.anom{background:#c84}.bar-num{position:relative;padding-left:6px;font-size:12px;line-height:18px}
.tabs{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap}
.tab{padding:8px 14px;background:#1a2030;border:1px solid #2a3142;border-radius:8px;cursor:pointer;font-weight:600}
.tab.active{background:#26304a;color:#cfe}
.panel{display:none}.panel.active{display:block}
.kpis{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:12px}
.kpi{flex:1;min-width:120px;background:#1a2030;border:1px solid #2a3142;border-radius:10px;padding:14px;text-align:center}
.kpi-num{font-size:26px;font-weight:700;color:#8fe}.kpi-lbl{color:#8aa;font-size:12px;text-transform:uppercase}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px}@media(max-width:760px){.grid2{grid-template-columns:1fr}}
.pkg{break-inside:avoid}.pkg-head{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:8px}
.mini td,.mini th{padding:4px 6px;font-size:12px}.cm .tp{color:#7e7}.cm .tn{color:#9cf}.cm .fp{color:#fb8}.cm .fn{color:#f88}
.warn{color:#fc9}.adv{color:#9cf}.rationale{color:#aeb8cc;border-top:1px dashed #2a3142;padding-top:6px;margin-top:6px}
.notice{background:#2a1a1f;border:1px solid #5b1620;border-radius:8px;padding:12px;color:#ffb3bd;margin-bottom:16px}
.filters{margin:0 0 12px}.filters button{margin-right:6px;background:#1a2030;border:1px solid #2a3142;color:#cde;border-radius:6px;padding:5px 10px;cursor:pointer}
"""

JS = """
function show(id,el){document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));
document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
document.getElementById(id).classList.add('active');el.classList.add('active');}
function filt(p){document.querySelectorAll('[data-priority]').forEach(r=>{
r.style.display=(p==='ALL'||r.getAttribute('data-priority')===p)?'':'none';});}
"""


def build_html(queue: dict, packages: list, bt: dict) -> str:
    gen = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    mode = queue.get("data_mode", "?")
    return (
        "<!doctype html><html><head><meta charset='utf-8'><title>SECFEDCLAW v0.2</title>"
        f"<style>{CSS}</style></head><body>"
        "<div class='topbar'><span class='brand'>SECFEDCLAW v0.2</span>"
        "<span class='pill ok'>WATCH ceiling</span> <span class='pill'>local-only · no external callbacks</span>"
        f" <span class='muted'>generated {esc(gen)} · mode {esc(mode)}</span></div>"
        "<div class='wrap'>"
        f"<div class='notice'>{esc(SOUL_BOUNDARY)}</div>"
        "<div class='tabs'>"
        "<div class='tab active' onclick=\"show('q',this)\">Review Queue</div>"
        "<div class='tab' onclick=\"show('pk',this)\">Packages</div>"
        "<div class='tab' onclick=\"show('bt',this)\">Backtest / Calibration</div>"
        "</div>"
        # queue
        "<div id='q' class='panel active'>"
        f"{kpi_panel(queue, packages)}"
        "<div class='card'><h2>Ranked review queue</h2>"
        "<div class='filters'>Filter: "
        "<button onclick=\"filt('ALL')\">All</button>"
        "<button onclick=\"filt('CRITICAL_REVIEW')\">Critical</button>"
        "<button onclick=\"filt('HIGH')\">High</button>"
        "<button onclick=\"filt('MEDIUM')\">Medium</button>"
        "<button onclick=\"filt('LOW')\">Low</button></div>"
        "<table><tr><th>Ticker</th><th>Priority</th><th>Watch score</th><th>Anomaly evidence</th>"
        "<th class='num'>Ev.Q</th><th class='num'>Families</th><th>Class</th><th>Mode</th></tr>"
        f"{queue_rows(queue)}</table>"
        "<p class='muted small'>Review priority only. Not a trading signal or proof of misconduct. "
        "HIGH/CRITICAL requires ≥2 independent corroborating families. Thresholds are "
        "calibrated per liquidity class (thin/μcap → small → mid → large).</p></div>"
        f"{source_health_panel(queue)}</div>"
        # packages
        f"<div id='pk' class='panel'><h2>WATCH packages</h2>{package_cards(packages)}</div>"
        # backtest
        f"<div id='bt' class='panel'><h2>Backtest / calibration</h2>{backtest_panel(bt)}</div>"
        "</div>"
        f"<script>{JS}</script></body></html>"
    )


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
    print(f"  queue rows: {len(queue.get('review_queue', []))}  packages: {len(packages)}  "
          f"backtest: {'yes' if bt else 'no'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
