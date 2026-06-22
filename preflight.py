#!/usr/bin/env python3
"""Live-readiness preflight for SECFEDCLAW v0.2.

Before flipping from replay to LIVE, this probes every data source with the
real .env credentials and reports, per source: reachable?, HTTP status, the
mode the scan would use (live / replay / unavailable), and any rate-limit note.
It then gives an overall GO / DEGRADED verdict so the operator knows exactly
what will run live and what will fall back to cached custody artifacts.

No secret values are printed. Read-only, bounded probes only.

  python3 preflight.py            # human-readable table
  python3 preflight.py --json     # machine-readable
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import load_env, fed_claw_root  # noqa: E402

TIMEOUT = 10


def _get(url: str, headers: dict | None = None, method: str = "GET", data: bytes | None = None):
    try:
        req = urllib.request.Request(url, headers=headers or {}, method=method, data=data)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, dict(r.headers.items())
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers.items())
    except Exception as e:
        return None, {"error": f"{type(e).__name__}: {str(e)[:60]}"}


def default_prober(env: dict[str, str]) -> dict[str, Callable[[], tuple]]:
    pk = env.get("POLYGON_API_KEY", "")
    ua = env.get("SEC_USER_AGENT", "secfedclaw research")
    xb = env.get("X_BEARER_TOKEN") or env.get("TWITTER_BEARER_TOKEN", "")

    def polygon():
        if not pk:
            return None, {"error": "POLYGON_API_KEY not set"}
        return _get(f"https://api.polygon.io/v1/marketstatus/now?apiKey={pk}")

    def flatfiles():
        ak = env.get("MASSIVE_FLATFILES_ACCESS_KEY_ID")
        sk = env.get("MASSIVE_FLATFILES_SECRET_ACCESS_KEY")
        if not (ak and sk):
            return None, {"error": "MASSIVE_FLATFILES_* not set"}
        try:
            import datetime as _dt
            import flatfiles as ff
        except Exception as e:
            return None, {"error": str(e)[:60]}
        # The creds grant object reads (s3:GetObject) but not bucket listing,
        # so probing the prefix 'us_stocks_sip/day_aggs_v1/' returns a false 403
        # NOT_AUTHORIZED even though real downloads succeed. Probe an actual
        # day-aggs object instead, walking back over the T+1 publish lag,
        # weekends, and holidays (404 = not published) until one resolves.
        last = (None, {"error": "no recent day-aggs file resolved"})
        d = _dt.date.today() - _dt.timedelta(days=2)
        for _ in range(10):
            if d.weekday() < 5:  # skip weekends
                req = ff.signed_get_request(ak, sk, ff.day_aggs_key(d.isoformat()))
                status, meta = _get(req.full_url, dict(req.headers))
                if status == 200 or status in (401, 403):
                    return status, meta  # 200 = live; 401/403 = real auth failure
                last = (status, meta)   # 404/None = unpublished day; keep walking
            d -= _dt.timedelta(days=1)
        return last

    def sec():
        return _get("https://www.sec.gov/files/company_tickers.json", {"User-Agent": ua})

    def x():
        if not xb:
            return None, {"error": "X/TWITTER bearer not set"}
        return _get("https://api.twitter.com/2/tweets/search/recent?query=%24AAPL&max_results=10",
                    {"Authorization": f"Bearer {xb}"})

    def stocktwits():
        return _get("https://api.stocktwits.com/api/2/streams/symbol/AAPL.json",
                    {"User-Agent": "secfedclaw-watch/2.0"})

    def reddit():
        # The connector reaches Reddit via the public RSS feed first (no auth);
        # OAuth (REDDIT_CLIENT_ID/SECRET) is only an optional fallback. Probe the
        # same public RSS endpoint the connector uses so health reflects real
        # behavior instead of a false negative when OAuth creds are absent.
        subs = "+".join(["pennystocks", "stocks", "wallstreetbets",
                         "Shortsqueeze", "smallstreetbets", "RobinHoodPennyStocks"])
        rss = (f"https://www.reddit.com/r/{subs}/search.rss?q=%24AAPL+OR+AAPL"
               "&restrict_sr=on&sort=new&limit=25&t=week")
        return _get(rss, {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X "
                    "10_15_7) AppleWebKit/537.36"})

    def finra():
        return _get("https://api.finra.org/metadata/group/otcMarket/name/weeklySummary")

    def fmp():
        fmp_key = env.get("FMP_API_KEY", "")
        if not fmp_key:
            return None, {"error": "FMP_API_KEY not set (optional — Financial Modeling Prep)"}
        return _get(f"https://financialmodelingprep.com/stable/quote?symbol=AAPL&apikey={fmp_key}")

    def firecrawl():
        # Firecrawl powers the openinsider / social_web / discord scrapers. The
        # credit-usage endpoint returns 200 even on an exhausted account, so a
        # bare reachability check would falsely read "live" while every scrape
        # 402s. Read the balance and report scrape capability honestly.
        fk = env.get("FIRECRAWL_API_KEY", "")
        if not fk:
            return None, {"error": "FIRECRAWL_API_KEY not set (optional — web scraping)"}
        try:
            req = urllib.request.Request("https://api.firecrawl.dev/v1/team/credit-usage",
                                         headers={"Authorization": f"Bearer {fk}"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                body = json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, {"error": f"credit-usage HTTP {e.code}"}
        except Exception as e:
            return None, {"error": f"{type(e).__name__}: {str(e)[:50]}"}
        rem = (body.get("data") or {}).get("remaining_credits")
        if rem is not None and rem <= 0:
            # account reachable but scraping disabled until credits/billing reset
            return 402, {"error": "0 credits — scrapers degrade to replay"}
        return 200, {"error": f"credits_remaining={rem}" if rem is not None else ""}

    return {"polygon": polygon, "flatfiles": flatfiles, "sec_edgar": sec, "x": x,
            "stocktwits": stocktwits, "reddit": reddit, "finra": finra, "fmp": fmp,
            "firecrawl": firecrawl}


# sources whose live availability defines "GO" for the core market engine
CORE = {"polygon"}


def run_preflight(env: dict[str, str] | None = None,
                  probers: dict[str, Callable[[], tuple]] | None = None) -> dict[str, Any]:
    env = env if env is not None else load_env(fed_claw_root())
    probers = probers or default_prober(env)
    results = []
    for name, fn in probers.items():
        status, meta = fn()
        reachable = status == 200
        if reachable:
            mode = "live"
        elif status in (401, 403):
            mode = "replay (auth/entitlement)"
        elif status is None:
            mode = "replay (unreachable)"
        else:
            mode = f"replay (HTTP {status})"
        note = meta.get("error", "")
        rl = meta.get("x-ratelimit-remaining") or meta.get("x-rate-limit-remaining")
        if rl:
            note = (note + f" rate_remaining={rl}").strip()
        results.append({"source": name, "reachable": reachable, "status": status,
                        "mode_if_run": mode, "note": note})
    core_ready = any(r["reachable"] for r in results if r["source"] in CORE)
    n_live = sum(1 for r in results if r["reachable"])
    verdict = "GO_LIVE" if core_ready else ("DEGRADED" if n_live else "REPLAY_ONLY")
    return {
        "verdict": verdict,
        "core_market_live": core_ready,
        "sources_live": n_live,
        "sources_total": len(results),
        "results": results,
        "note": "GO_LIVE = core market source reachable; others may degrade to cached custody replay. "
                "No secrets printed; all probes read-only.",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="SECFEDCLAW v0.2 live-readiness preflight")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    rep = run_preflight()
    if args.json:
        print(json.dumps(rep, indent=2))
        return 0
    print(f"\nSECFEDCLAW preflight — verdict: {rep['verdict']}  "
          f"({rep['sources_live']}/{rep['sources_total']} live)")
    print("=" * 64)
    print(f"{'SOURCE':<12}{'LIVE':<6}{'STATUS':<8}{'MODE IF RUN':<26}NOTE")
    print("-" * 64)
    for r in rep["results"]:
        print(f"{r['source']:<12}{('yes' if r['reachable'] else 'no'):<6}"
              f"{str(r['status']):<8}{r['mode_if_run']:<26}{r['note'][:24]}")
    print("-" * 64)
    print(rep["note"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
