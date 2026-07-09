#!/usr/bin/env python3
"""SECFEDCLAW v0.2 operator dashboard — orchestrator. Assembles panel
fragments into the self-contained offline HTML. Helpers -> dashboard_common,
panels -> dashboard_panels, CSS/JS -> dashboard_assets."""
from dashboard_common import *  # noqa: F401,F403
from dashboard_panels import *  # noqa: F401,F403
from dashboard_assets import CSS, JS

def build_html(queue: dict, packages: list, bt: dict) -> str:
    gen = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    mode = queue.get("data_mode", "?")
    n_pkg = len([p for p in packages if p])
    # Three labeled sections, examiner-facing output first (wayfinding > a flat
    # 12-item list). Review = the meat (queue, packages, agent output, network
    # evidence, calibration); Operations = run + model health; Reference = the
    # explainers. Panel order below is reordered to match.
    tabs = (
        _nav_section("Review")
        + _tab("Overview", "overview", True) + _tab("Packages", "packages")
        + _tab("Agents", "agents") + _tab("Network", "network")
        + _tab("Entities", "entities") + _tab("Backtest", "backtest")
        + _nav_section("Operations")
        + _tab("Status", "status") + _tab("Runs", "runs")
        + _tab("Learning", "learning") + _tab("LLM cost", "llm")
        + _nav_section("Reference")
        + _tab("How it works", "howitworks") + _tab("Methodology", "methodology")
        + _tab("SEC case studies", "cases")
    )
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>SECFEDCLAW v0.2 — Surveillance Review Console</title>"
        # Inline SVG favicon — suppresses the /favicon.ico 404 regardless of how
        # the file is served (serve.py, file://, any static server). Navy tile +
        # a magnifier-eye glyph; <, >, # are URL-encoded for a valid data URI.
        "<link rel='icon' href=\"data:image/svg+xml,"
        "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E"
        "%3Crect width='32' height='32' rx='6' fill='%23112e51'/%3E"
        "%3Ccircle cx='14' cy='14' r='6' fill='none' stroke='white' stroke-width='2.5'/%3E"
        "%3Cline x1='18.5' y1='18.5' x2='24' y2='24' stroke='white' stroke-width='2.5' stroke-linecap='round'/%3E"
        "%3C/svg%3E\">"
        f"<style>{CSS}</style></head><body>"
        # Sidebar nav drawer
        "<nav id='sidebar' class='sidebar'>"
        "<div class='sidebar-header'>"
        "<button id='navToggle' class='sidebar-toggle' onclick='toggleNav()' title='Toggle navigation'>&#10005;</button>"
        "</div>"
        f"<div class='tabs'>{tabs}</div>"
        "</nav>"
        # Page shell (shifts right of sidebar)
        "<div id='pageShell' class='page-shell'>"
        "<div class='govbanner'><div class='govbanner-inner'>"
        "&#127482;&#127480;&nbsp;"
        "<span>An official surveillance review tool — WATCH context only, not enforcement.</span>"
        "</div></div>"
        "<div class='topbar'><div class='brand-row'>"
        "<span class='brand'>SECFEDCLAW <span class='v'>v0.2</span></span>"
        "<span class='subtitle'>Pump-and-dump WATCH · Social × Market × SEC/FINRA fusion</span>"
        f"<span class='meta'>{esc(gen)} · {esc(mode)} · {n_pkg} packages</span></div>"
        f"<div class='boundary'>&#9888; {esc(BOUNDARY)}</div></div>"
        "<div class='wrap'>"
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
        f"<section id='entities' class='panel'><h2>Entities &amp; recurrence</h2>{entities_panel()}</section>"
        f"<section id='network' class='panel'><h2>Coordination network</h2>"
        f"{network_graph_panel([p for p in packages if p])}</section>"
        # how it works
        f"<section id='howitworks' class='panel'><h2>How it works</h2>{how_it_works_panel()}</section>"
        # agents
        f"<section id='agents' class='panel'><h2>Agents &amp; orchestration</h2>{agents_panel(queue)}</section>"
        # learning
        f"<section id='learning' class='panel'><h2>Learning pipeline</h2>{learning_panel()}</section>"
        # status
        f"<section id='status' class='panel'><h2>Agent &amp; integration status</h2>{agent_status_panel(queue)}</section>"
        # runs (live control plane)
        f"<section id='runs' class='panel'><h2>Runs &amp; live status</h2>{runs_panel()}</section>"
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
        f"</div></div><script>{JS}</script></body></html>")



def render(out_dir: Path | None = None, out_path: Path | None = None) -> tuple[Path, dict]:
    """Read run artifacts from `out_dir` and write the self-contained dashboard
    HTML to `out_path`. Reusable entrypoint so a scan (CLI or serve.py rerun)
    can regenerate the static dashboard and keep its baked-in panels — Status/
    SRE, overview, agents — in sync with the latest run. Returns (path, stats)."""
    d = Path(out_dir) if out_dir else OUT
    out = Path(out_path) if out_path else (d / "dashboard_v2.html")
    queue = load(d / "review_queue.json", {})
    bt = load(d / "backtest_results.json", {})
    # Keep only the LATEST package per ticker — the out/ dir accumulates every
    # historical run, so without this the examiner reviews (and could label)
    # weeks-old evidence as if current, with duplicate tickers crowding the view.
    by_ticker: dict[str, dict[str, Any]] = {}
    for p in sorted(d.glob("*_watch_v2.json")):
        pkg = load(p, {})
        if not pkg:
            continue
        pkg["_source_file"] = p.name  # so a card can label this exact package
        tk = pkg.get("ticker")
        ts = pkg.get("generated_utc") or ""
        prev = by_ticker.get(tk)
        if prev is None or ts >= (prev.get("generated_utc") or ""):
            by_ticker[tk] = pkg
    packages = list(by_ticker.values())
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_html(queue, packages, bt))
    return out, {"queue_rows": len(queue.get("review_queue", [])),
                 "packages": len(packages), "backtest": bool(bt)}



def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Render the SECFEDCLAW v0.2 operator dashboard as a self-contained HTML file. "
            "Reads review_queue.json, *_watch_v2.json packages, and backtest_results.json "
            "from the out/ directory (or --out parent). Produces a single offline HTML file "
            "with inline CSS/JS — no external resources or callbacks."
        )
    )
    ap.add_argument("--out", default=str(OUT / "dashboard_v2.html"),
                    help="Output path for the rendered HTML file (default: out/dashboard_v2.html)")
    args = ap.parse_args()
    out, stats = render(out_path=Path(args.out))
    print(f"dashboard: {out}")
    print(f"  queue rows: {stats['queue_rows']}  packages: {stats['packages']}  backtest: {'yes' if stats['backtest'] else 'no'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
