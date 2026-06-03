#!/usr/bin/env python3
"""Per-source live-readiness preflight check for SECFEDCLAW v0.2.

Probes each data source for reachability and reports a verdict:
  GO_LIVE       — all key sources reachable
  DEGRADED      — some sources reachable (partial live)
  REPLAY_ONLY   — no live sources; will replay from cached artifacts

  python3 preflight.py          # print verdict + per-source status
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import load_env, fed_claw_root  # noqa: E402
from connectors import DataConnector       # noqa: E402


def run_preflight(prefer_live: bool = True) -> dict[str, Any]:
    """Probe each data source and return a preflight report."""
    dc = DataConnector(prefer_live=prefer_live)
    env = dc.env

    sources: dict[str, dict[str, Any]] = {}

    # Polygon (market data)
    polygon_ok = dc.live_available()
    sources["polygon"] = {"live": polygon_ok, "key_present": bool(env.get("POLYGON_API_KEY"))}

    # Polygon Flat Files (historical)
    ff_key = bool(env.get("MASSIVE_FLATFILES_ACCESS_KEY_ID") or env.get("POLYGON_FLATFILES_ACCESS_KEY_ID"))
    sources["flatfiles"] = {"key_present": ff_key, "live": ff_key}  # can't probe S3 cheaply

    # SEC EDGAR
    sec_ua = env.get("SEC_USER_AGENT", "")
    sec_ok = dc.live_available_sec(sec_ua) if (prefer_live and sec_ua) else False
    sources["sec_edgar"] = {"live": sec_ok, "key_present": bool(sec_ua)}

    # X / Twitter
    x_key = bool(env.get("X_BEARER_TOKEN") or env.get("TWITTER_BEARER_TOKEN"))
    sources["x"] = {"key_present": x_key, "live": x_key}  # bearer auth, assume reachable if key present

    # Reddit OAuth
    reddit_key = bool(env.get("REDDIT_CLIENT_ID") and env.get("REDDIT_CLIENT_SECRET"))
    sources["reddit"] = {"key_present": reddit_key, "live": reddit_key}

    # StockTwits (public, no auth)
    sources["stocktwits"] = {"key_present": True, "live": prefer_live}

    # FINRA / Nasdaq (replay-only currently)
    sources["finra_nasdaq"] = {"key_present": True, "live": False, "note": "replay-only sources"}

    # Summarize
    live_count = sum(1 for s in sources.values() if s.get("live"))
    total = len(sources)
    key_sources = {"polygon", "sec_edgar"}  # minimum for GO_LIVE
    key_live = all(sources.get(k, {}).get("live") for k in key_sources)

    if key_live and live_count >= 4:
        verdict = "GO_LIVE"
    elif live_count > 0:
        verdict = "DEGRADED"
    else:
        verdict = "REPLAY_ONLY"

    return {
        "verdict": verdict,
        "sources_live": live_count,
        "sources_total": total,
        "sources": sources,
    }


def main() -> int:
    report = run_preflight()
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
