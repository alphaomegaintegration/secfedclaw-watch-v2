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
              "otc_threshold", "reg_sho", "halts"],
    "Analyst": ["(scout output)"],
    "Adversary": ["(analyst output)"],
    "Packager": ["(filesystem custody)"],
}
AGENT_ROLE = {
    "Scout": "Pull data feeds (live or replay), record health + custody",
    "Analyst": "Normalize, engineer features, run algorithms, score",
    "Adversary": "Red-team; may only lower priority / add caveats",
    "Packager": "Assemble custody-preserving WATCH package",
}


def _load(p: Path, default):
    try:
        return json.loads(p.read_text())
    except Exception:
        return default


def integration_health(queue: dict[str, Any]) -> list[dict[str, Any]]:
    agg: dict[str, dict[str, int]] = {}
    for r in queue.get("review_queue", []):
        for src, h in (r.get("source_health") or {}).items():
            a = agg.setdefault(src, {"ok": 0, "total": 0, "live": 0, "replay": 0, "unavailable": 0})
            a["total"] += 1
            a["ok"] += 1 if h.get("ok") else 0
            m = h.get("mode")
            a["live" if m == "live" else "replay" if m == "replay" else "unavailable"] += 1
    rows = []
    for name, v in sorted(agg.items()):
        if v["live"]:
            state = "live"
        elif v["replay"]:
            state = "replay"
        else:
            state = "unavailable"
        rows.append({"integration": name, "state": state, "ok": v["ok"], "total": v["total"],
                     "live": v["live"], "replay": v["replay"], "unavailable": v["unavailable"]})
    return rows


def build(queue: dict[str, Any] | None = None) -> dict[str, Any]:
    queue = queue if queue is not None else _load(OUT / "review_queue.json", {"review_queue": []})
    summary = _load(OUT / "daily_run_summary.json", {})
    model = _load(OUT / "model" / "model.json", {})
    integrations = integration_health(queue)
    n_live = sum(1 for i in integrations if i["state"] == "live")

    def agent_state(name: str) -> str:
        if name == "Scout":
            if not integrations:
                return "idle"
            return "live" if n_live else ("replay" if any(i["state"] == "replay" for i in integrations) else "degraded")
        # downstream agents are ok whenever a scan produced packages
        return "ok" if queue.get("review_queue") else "idle"

    agents = [{"name": n, "role": AGENT_ROLE[n], "state": agent_state(n),
               "depends_on": AGENT_DEPS[n]} for n in ("Scout", "Analyst", "Adversary", "Packager")]

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

    return {
        "generated_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "system": {
            "preflight_verdict": summary.get("preflight_verdict", "—"),
            "last_run_utc": summary.get("finished_utc") or summary.get("started_utc", "—"),
            "data_mode": queue.get("data_mode", "—"),
            "ok": summary.get("ok"),
            "flagged_ge_medium": summary.get("flagged_ge_medium"),
            "integrations_live": n_live,
            "integrations_total": len(integrations),
        },
        "agents": agents,
        "integrations": integrations,
        "model": {"trained": bool(model) and not model.get("abstain"),
                  "abstain": model.get("abstain", True), "cv_auc": model.get("cv_auc"),
                  "n_labels": led.get("n_labels", 0)},
        "llm": {"n_calls": llm.get("n_calls", 0), "total_cost_usd": llm.get("total_cost_usd", 0.0),
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
