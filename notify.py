#!/usr/bin/env python3
"""Daily digest notifier for SECFEDCLAW v0.2.

Composes a concise WATCH digest of the day's flagged (>=MEDIUM) review
candidates from the latest review queue / daily run summary, and delivers it via
Telegram (TELEGRAM_BOT_TOKEN + TELEGRAM_HOME_CHANNEL in .env). Connection-aware:
if Telegram is unreachable or unconfigured, it writes the digest to
out/digest_<UTC>.txt instead — nothing is lost.

The digest is review-priority context for the authorized user only. It contains
no trading signals, accusations, or external escalation.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import load_env, fed_claw_root  # noqa: E402

OUT = Path(__file__).resolve().parent / "out"
RANK = {"CRITICAL_REVIEW": 3, "HIGH": 2, "MEDIUM": 1, "LOW": 0}


def dashboard_url(env: dict[str, str] | None = None) -> str:
    """Resolve the dashboard link: SECFEDCLAW_DASHBOARD_URL env, else local file."""
    env = env or {}
    return (os.environ.get("SECFEDCLAW_DASHBOARD_URL") or env.get("SECFEDCLAW_DASHBOARD_URL")
            or (OUT / "dashboard_v2.html").as_uri())


def compose_digest(queue: dict[str, Any], summary: dict[str, Any] | None = None,
                   url: str | None = None) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    rows = [r for r in queue.get("review_queue", []) if "error" not in r]
    flagged = sorted([r for r in rows if RANK.get(r.get("review_priority"), 0) >= 1],
                     key=lambda r: (RANK.get(r["review_priority"], 0), r.get("watch_score", 0)),
                     reverse=True)
    mode = queue.get("data_mode", "?")
    verdict = (summary or {}).get("preflight_verdict", "?")
    lines = [
        "SECFEDCLAW — daily WATCH digest",
        f"{now} · mode={mode} · preflight={verdict} · universe={queue.get('universe_size', len(rows))}",
        f"Flagged for review (≥MEDIUM): {len(flagged)}",
        "",
    ]
    if flagged:
        for r in flagged[:20]:
            lines.append(f"• {r['ticker']}  {r['review_priority']}  "
                         f"score {r.get('watch_score', 0):.0f} · anomaly {r.get('anomaly_evidence_score', 0):.0f} · "
                         f"{r.get('security_class', '?')} · {r.get('n_families_active', 0)} families")
    else:
        lines.append("No tickers reached MEDIUM today. (Routine context only.)")
    lines += [""]
    if url:
        lines.append(f"Dashboard: {url}")
    lines += ["WATCH-level review priorities only — not trading signals, not proof of misconduct.",
              "Open the dashboard for evidence packages, agents, and methodology."]
    return "\n".join(lines)


def send_telegram(text: str, env: dict[str, str], timeout: int = 12) -> dict[str, Any]:
    token = env.get("TELEGRAM_BOT_TOKEN")
    chat = env.get("TELEGRAM_HOME_CHANNEL") or env.get("TELEGRAM_ALLOWED_USERS", "").split(",")[0].strip()
    if not (token and chat):
        return {"sent": False, "reason": "TELEGRAM_BOT_TOKEN / TELEGRAM_HOME_CHANNEL not configured"}
    try:
        data = urllib.parse.urlencode({"chat_id": chat, "text": text[:4000],
                                       "disable_web_page_preview": "true"}).encode()
        req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            ok = r.status == 200
            return {"sent": ok, "status": r.status}
    except Exception as e:
        return {"sent": False, "reason": f"{type(e).__name__}: {str(e)[:80]}"}


def deliver(queue: dict[str, Any], summary: dict[str, Any] | None = None,
            env: dict[str, str] | None = None) -> dict[str, Any]:
    env = env if env is not None else load_env(fed_claw_root())
    text = compose_digest(queue, summary, url=dashboard_url(env))
    result = send_telegram(text, env)
    if not result.get("sent"):
        OUT.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        p = OUT / f"digest_{stamp}.txt"
        p.write_text(text + "\n")
        result["fallback_file"] = str(p)
    result["chars"] = len(text)
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="Send the SECFEDCLAW daily WATCH digest")
    ap.add_argument("--queue", default=str(OUT / "review_queue.json"))
    ap.add_argument("--summary", default=str(OUT / "daily_run_summary.json"))
    ap.add_argument("--print", action="store_true", help="print the digest text only (no send)")
    args = ap.parse_args()
    queue = json.loads(Path(args.queue).read_text()) if Path(args.queue).exists() else {"review_queue": []}
    summary = json.loads(Path(args.summary).read_text()) if Path(args.summary).exists() else None
    if args.print:
        print(compose_digest(queue, summary, url=dashboard_url(load_env(fed_claw_root()))))
        return 0
    print(json.dumps(deliver(queue, summary), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
