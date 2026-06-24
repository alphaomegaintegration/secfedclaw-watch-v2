#!/usr/bin/env python3
"""Agent + integration status for SECFEDCLAW v0.2.

Assembles a single status object describing the four agents, the integrations
each depends on, live/replay connection health, and overall system state
(preflight verdict, last run, model, ledger, LLM spend) — the operational view
'from an agent perspective' for the dashboard.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
sys.path.insert(0, str(HERE))

# Which integrations each agent depends on (for the per-agent view).
AGENT_DEPS = {
    "Scout": ["daily_range", "grouped", "prev", "snapshot", "trades", "quotes", "x",
              "reddit", "stocktwits", "submissions", "edgar", "litigation",
              "otc_threshold", "reg_sho", "halts",
              # web/social scrape+search via ScrapeGraphAI (primary) → Firecrawl (fallback)
              "discord", "instagram", "facebook", "social_web", "openinsider", "glint"],
    "Analyst": ["(scout output)"],
    "Adversary": ["(analyst output)"],
    "Explainer": ["local ollama / openrouter / anthropic (opt-in)", "usage ledger"],
    "Packager": ["(filesystem custody)"],
}
AGENT_ROLE = {
    "Scout": "Pull data feeds (live or replay), record health + custody",
    "Analyst": "Normalize, engineer features, run algorithms, score",
    "Adversary": "Red-team; may only lower priority / add caveats",
    "Explainer": "Plain-language review summary (LLM opt-in, else template)",
    "Packager": "Assemble custody-preserving WATCH package",
}


def _load(p: Path, default):
    try:
        return json.loads(p.read_text())
    except Exception:
        return default


def integration_health(queue: dict[str, Any]) -> list[dict[str, Any]]:
    from collections import Counter
    agg: dict[str, dict[str, int]] = {}
    provs: dict[str, Counter] = {}
    for r in queue.get("review_queue", []):
        for src, h in (r.get("source_health") or {}).items():
            a = agg.setdefault(src, {"ok": 0, "total": 0, "live": 0, "replay": 0, "unavailable": 0})
            a["total"] += 1
            a["ok"] += 1 if h.get("ok") else 0
            m = h.get("mode")
            a["live" if m == "live" else "replay" if m == "replay" else "unavailable"] += 1
            p = h.get("provider")
            if p:
                provs.setdefault(src, Counter())[p] += 1
    rows = []
    for name, v in sorted(agg.items()):
        if v["live"]:
            state = "live"
        elif v["replay"]:
            state = "replay"
        else:
            state = "unavailable"
        prov = provs[name].most_common(1)[0][0] if provs.get(name) else None
        rows.append({"integration": name, "state": state, "ok": v["ok"], "total": v["total"],
                     "success_pct": round(100 * v["ok"] / v["total"]) if v["total"] else 0,
                     "live": v["live"], "replay": v["replay"], "unavailable": v["unavailable"],
                     **({"provider": prov} if prov else {})})
    return rows


def agent_perf(manifest: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], int, int]:
    """Aggregate per-agent stage latency (p50/max ms) + run/error counts from
    the run manifest's per-ticker stage_ms. Returns (perf, runs, errors)."""
    from statistics import median
    samples: dict[str, list[float]] = {}
    runs = errors = 0
    for entry in (manifest.get("tickers") or {}).values():
        runs += 1
        if entry.get("status") == "error":
            errors += 1
        for agent, ms in (entry.get("stage_ms") or {}).items():
            samples.setdefault(agent, []).append(float(ms))
    perf = {a: {"p50_ms": round(median(v)), "max_ms": round(max(v)), "runs": len(v)}
            for a, v in samples.items()}
    return perf, runs, errors


def _age_seconds(start_iso: str, end_iso: str) -> int | None:
    try:
        fmt = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))
        return max(0, int((fmt(end_iso) - fmt(start_iso)).total_seconds()))
    except Exception:
        return None


def build(queue: dict[str, Any] | None = None) -> dict[str, Any]:
    queue = queue if queue is not None else _load(OUT / "review_queue.json", {"review_queue": []})
    summary = _load(OUT / "daily_run_summary.json", {})
    manifest = _load(OUT / "run_manifest.json", {})
    model = _load(OUT / "model" / "model.json", {})
    integrations = integration_health(queue)
    n_live = sum(1 for i in integrations if i["state"] == "live")
    perf, n_runs, n_errors = agent_perf(manifest)
    # local-Ollama search calls this run (free, not token-metered) from the
    # manifest providers map — the free-LLM signal the usage ledger can't see.
    local_search_calls = sum(
        1 for e in (manifest.get("tickers") or {}).values()
        for s, p in (e.get("providers") or {}).items()
        if s in ("x", "social_web") and p == "scrapegraphai")

    def agent_state(name: str) -> str:
        if name == "Scout":
            if not integrations:
                return "idle"
            return "live" if n_live else ("replay" if any(i["state"] == "replay" for i in integrations) else "degraded")
        # downstream agents are ok whenever a scan produced packages
        return "ok" if queue.get("review_queue") else "idle"

    def explainer_state() -> str:
        try:
            import explainer
            if explainer.llm_enabled():
                return "live" if any(self_env.get(k) for k in ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY")) else "ok"
        except Exception:
            pass
        return "ok" if queue.get("review_queue") else "idle"

    self_env = {}
    try:
        from config import load_env, fed_claw_root
        self_env = load_env(fed_claw_root())
    except Exception:
        pass

    agents = [{"name": n, "role": AGENT_ROLE[n],
               "state": (explainer_state() if n == "Explainer" else agent_state(n)),
               "depends_on": AGENT_DEPS[n],
               "latency_ms": perf.get(n, {}).get("p50_ms"),
               "max_ms": perf.get(n, {}).get("max_ms"),
               "runs": perf.get(n, {}).get("runs", 0)}
              for n in ("Scout", "Analyst", "Adversary", "Explainer", "Packager")]

    try:
        import ledger
        led = ledger.summary()
    except Exception:
        led = {"n_labels": 0}
    try:
        import usage
        llm = usage.summary()
    except Exception:
        llm = {"n_calls": 0, "total_cost_usd": 0.0}

    generated = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    # "Last run" should reflect the latest scan of any kind. The run manifest's
    # finished_utc is written by every scan (daily.py, direct scan.py, AND
    # server-triggered reruns), whereas daily_run_summary.json is only written
    # by daily.py — so prefer the manifest, falling back to the daily summary.
    last_run = (manifest.get("finished_utc") or summary.get("finished_utc")
                or manifest.get("started_utc") or summary.get("started_utc") or "—")
    return {
        "generated_utc": generated,
        "system": {
            "preflight_verdict": summary.get("preflight_verdict", "—"),
            "last_run_utc": last_run,
            "last_run_age_s": _age_seconds(last_run, generated),
            "data_mode": queue.get("data_mode", "—"),
            "ok": summary.get("ok"),
            "flagged_ge_medium": summary.get("flagged_ge_medium"),
            "integrations_live": n_live,
            "integrations_total": len(integrations),
            "integrations_live_pct": round(100 * n_live / len(integrations)) if integrations else 0,
            "runs": n_runs,
            "errors": n_errors,
            "error_rate": round(n_errors / n_runs, 3) if n_runs else 0.0,
        },
        "agents": agents,
        "integrations": integrations,
        "model": {"trained": bool(model) and not model.get("abstain"),
                  "abstain": model.get("abstain", True), "cv_auc": model.get("cv_auc"),
                  "n_labels": led.get("n_labels", 0)},
        "llm": {"n_calls": llm.get("n_calls", 0), "total_cost_usd": llm.get("total_cost_usd", 0.0),
                "paid_cost_usd": llm.get("paid_cost_usd", llm.get("total_cost_usd", 0.0)),
                "paid_calls": llm.get("paid_calls", llm.get("n_calls", 0)),
                "local_free_calls": llm.get("local_free_calls", 0),
                "search_calls": local_search_calls,
                # the model SearchGraph uses (env override or the provider default)
                "search_model": self_env.get("SGAI_MODEL") or "gemini-2.5-flash",
                "by_model": llm.get("by_model", {})},
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    st = build()
    (OUT / "agent_status.json").write_text(json.dumps(st, indent=2, default=str) + "\n")
    print(json.dumps(st, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
