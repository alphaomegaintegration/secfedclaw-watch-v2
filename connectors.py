#!/usr/bin/env python3
"""Connection-aware data layer for SECFEDCLAW v0.2.

Design goal: the SAME code path runs LIVE on the operator's machine (where
Polygon / X / SEC / FINRA are reachable using the .env credentials) and in
REPLAY mode against the local custody artifacts when network egress is
unavailable (e.g. a locked-down sandbox). Every returned record carries its
provenance (source, url-redacted, artifact path, sha256, mode) so custody and
reproducibility are preserved exactly as SOUL.md requires.

No secret value is ever printed. Live URLs are redacted before logging.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from config import load_env, fed_claw_root


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def redact(url: str) -> str:
    url = re.sub(r"(apiKey|api_key|token|key)=[^&\s]+", r"\1=<redacted>", url, flags=re.I)
    return url


@dataclass
class Fetch:
    """Result of a data fetch with full provenance."""
    name: str
    mode: str               # "live" | "replay" | "unavailable"
    status: int | None
    data: Any
    artifact_path: str | None = None
    sha256: str | None = None
    source_url_redacted: str | None = None
    note: str = ""
    provenance: dict[str, Any] = field(default_factory=dict)

    def ok(self) -> bool:
        return self.data is not None and (self.status in (None, 200))


class DataConnector:
    """Fetches live when possible, else replays newest matching artifact."""

    def __init__(self, root: Path | None = None, prefer_live: bool = True, timeout: int = 12):
        self.root = root or fed_claw_root()
        self.env = load_env(self.root)
        self.prefer_live = prefer_live
        self.timeout = timeout
        self._live_ok: bool | None = None
        self.artifacts = self.root / "artifacts"
        self.collections = self.root / "collections"

    # ---- live custody: persist raw responses + sha256 -------------------
    def _live(self, name: str, status: int | None, data: Any, url: str | None = None,
              note: str = "") -> "Fetch":
        """Wrap a successful LIVE response, persisting it for custody/replay."""
        path = sha = None
        try:
            import time as _t
            if getattr(self, "_lrd", None) is None:
                self._lrd = self.root / "live_cache" / _t.strftime("%Y%m%dT%H%M%SZ", _t.gmtime())
            self._lrd.mkdir(parents=True, exist_ok=True)
            if isinstance(data, (bytes, bytearray)):
                raw = bytes(data)
            elif isinstance(data, str):
                raw = data.encode()
            else:
                raw = json.dumps(data, default=str).encode()
            p = self._lrd / f"{name}.json"
            p.write_bytes(raw)
            path, sha = str(p), sha256_bytes(raw)
        except Exception:
            pass
        return Fetch(name=name, mode="live", status=status, data=data,
                     artifact_path=path, sha256=sha,
                     source_url_redacted=redact(url) if url else None, note=note or "live (persisted to live_cache)")

    # ---- live HTTP (graceful) ------------------------------------------
    def _http_json(self, url: str, headers: dict[str, str] | None = None) -> tuple[int | None, Any]:
        try:
            req = urllib.request.Request(url, headers=headers or {})
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                raw = r.read()
                try:
                    return r.status, json.loads(raw)
                except Exception:
                    return r.status, raw
        except urllib.error.HTTPError as e:
            return e.code, None
        except Exception:
            self._live_ok = False
            return None, None

    def live_available(self) -> bool:
        """Cheap probe (cached). Polygon market status is a light endpoint."""
        if self._live_ok is not None:
            return self._live_ok
        if not self.prefer_live:
            self._live_ok = False
            return False
        pk = self.env.get("POLYGON_API_KEY", "")
        if not pk:
            self._live_ok = False
            return False
        status, _ = self._http_json(f"https://api.polygon.io/v1/marketstatus/now?apiKey={pk}")
        self._live_ok = status == 200
        return self._live_ok

    # ---- replay (newest matching artifact) -----------------------------
    def _newest(self, *glob_patterns: str) -> Path | None:
        best: Path | None = None
        best_mtime = -1.0
        for pat in glob_patterns:
            for base in (self.collections, self.artifacts):
                for p in base.glob(pat):
                    if p.is_file() and p.stat().st_mtime > best_mtime:
                        best, best_mtime = p, p.stat().st_mtime
        return best

    def _replay(self, name: str, *patterns: str, note: str = "") -> Fetch:
        p = self._newest(*patterns)
        if not p:
            return Fetch(name=name, mode="unavailable", status=None, data=None,
                         note=f"no cached artifact for patterns {patterns}")
        raw = p.read_bytes()
        try:
            data = json.loads(raw)
        except Exception:
            data = raw
        return Fetch(name=name, mode="replay", status=200, data=data,
                     artifact_path=str(p), sha256=sha256_bytes(raw), note=note or "replayed from custody artifact")

    # ---- public source methods -----------------------------------------
    def polygon_daily_range(self, ticker: str, days: int = 90) -> Fetch:
        """Daily OHLCV history for rolling baselines (live preferred)."""
        ticker = ticker.upper()
        if self.live_available():
            pk = self.env.get("POLYGON_API_KEY", "")
            end = time.strftime("%Y-%m-%d")
            start = time.strftime("%Y-%m-%d", time.gmtime(time.time() - days * 86400))
            url = (f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/"
                   f"{start}/{end}?adjusted=true&sort=asc&limit=400&apiKey={pk}")
            status, data = self._http_json(url)
            if status == 200 and data:
                return self._live(f"polygon_daily_range_{ticker}", status, data, url, note=f"{days}d daily aggregates")
        # replay: single/multi-day custom aggs cached per ticker
        return self._replay(f"polygon_daily_range_{ticker}",
                            f"*custom_day_aggs_{ticker.lower()}*.json",
                            f"*custom_minute_aggs_{ticker.lower()}*.json")

    def polygon_prev(self, ticker: str) -> Fetch:
        ticker = ticker.upper()
        if self.live_available():
            pk = self.env.get("POLYGON_API_KEY", "")
            url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/prev?adjusted=true&apiKey={pk}"
            status, data = self._http_json(url)
            if status == 200 and data:
                return self._live(f"polygon_prev_{ticker}", status, data, url)
        return self._replay(f"polygon_prev_{ticker}", f"*/polygon_prev_{ticker}.json", f"*prev_aggregate_{ticker.lower()}*.json")

    def polygon_grouped_daily(self) -> Fetch:
        """Whole-market one-day OHLCV: the cross-sectional baseline population."""
        if self.live_available():
            pk = self.env.get("POLYGON_API_KEY", "")
            day = time.strftime("%Y-%m-%d", time.gmtime(time.time() - 86400))
            url = f"https://api.polygon.io/v2/aggs/grouped/locale/us/market/stocks/{day}?adjusted=true&apiKey={pk}"
            status, data = self._http_json(url)
            if status == 200 and data:
                return self._live("polygon_grouped_daily", status, data, url)
        return self._replay("polygon_grouped_daily", "*grouped_daily*.json", "*grouped_daily_market*.json")

    def polygon_snapshot(self, ticker: str) -> Fetch:
        ticker = ticker.upper()
        if self.live_available():
            pk = self.env.get("POLYGON_API_KEY", "")
            url = f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}?apiKey={pk}"
            status, data = self._http_json(url)
            if status == 200 and data:
                return self._live(f"polygon_snapshot_{ticker}", status, data, url)
        return self._replay(f"polygon_snapshot_{ticker}", f"*/polygon_snapshot_{ticker}.json", f"*snapshot_single_{ticker.lower()}*.json")

    def polygon_trades(self, ticker: str) -> Fetch:
        ticker = ticker.upper()
        return self._replay(f"polygon_trades_{ticker}", f"*/polygon_trades_{ticker}_*.json", f"*trades_{ticker.lower()}*.json")

    def polygon_quotes(self, ticker: str) -> Fetch:
        ticker = ticker.upper()
        return self._replay(f"polygon_quotes_{ticker}", f"*/polygon_quotes_{ticker}_*.json", f"*quotes_{ticker.lower()}*.json")

    def x_recent(self, ticker: str) -> Fetch:
        """X recent search for a cashtag (live preferred, replay fallback)."""
        ticker = ticker.upper()
        if self.live_available() or self.env.get("X_BEARER_TOKEN") or self.env.get("TWITTER_BEARER_TOKEN"):
            bearer = self.env.get("X_BEARER_TOKEN") or self.env.get("TWITTER_BEARER_TOKEN")
            if bearer and self.prefer_live:
                url = (f"https://api.twitter.com/2/tweets/search/recent?query=%24{ticker}"
                       f"&max_results=25&tweet.fields=public_metrics,created_at,author_id,entities")
                status, data = self._http_json(url, {"Authorization": f"Bearer {bearer}"})
                if status == 200 and data:
                    return self._live(f"x_recent_{ticker}", status, data, url)
        return self._replay(f"x_recent_{ticker}", f"*/x_recent_search_{ticker}.json", f"*x_recent_search*{ticker.lower()}*.json")

    def reddit_oauth(self, ticker: str, subreddits: list[str] | None = None) -> Fetch:
        """Reddit via authenticated OAuth (app-only client_credentials grant).

        Public JSON (old.reddit) is 403-blocked; this uses the official OAuth
        API. Requires REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET/REDDIT_USER_AGENT.
        Searches finance subreddits for the ticker; returns Reddit listing JSON.
        """
        ticker = ticker.upper()
        subs = "+".join(subreddits or ["pennystocks", "stocks", "wallstreetbets",
                                        "Shortsqueeze", "smallstreetbets", "RobinHoodPennyStocks"])
        cid = self.env.get("REDDIT_CLIENT_ID")
        csec = self.env.get("REDDIT_CLIENT_SECRET")
        ua = self.env.get("REDDIT_USER_AGENT", "secfedclaw-watch/2.0 by u/secfedclaw")
        if self.prefer_live and cid and csec:
            token = self._reddit_token(cid, csec, ua)
            if token:
                url = (f"https://oauth.reddit.com/r/{subs}/search?q=%24{ticker}%20OR%20{ticker}"
                       f"&restrict_sr=on&sort=new&limit=50&t=week")
                status, data = self._http_json(url, {"Authorization": f"bearer {token}", "User-Agent": ua})
                if status == 200 and data:
                    return self._live(f"reddit_{ticker}", status, data, url, note=f"reddit oauth r/{subs}")
        return self._replay(f"reddit_{ticker}", f"*/reddit_*{ticker}*.json", f"*reddit*{ticker.lower()}*.json",
                            note="reddit unavailable; set REDDIT_CLIENT_ID/SECRET for live OAuth")

    def _reddit_token(self, cid: str, csec: str, ua: str) -> str | None:
        import base64
        if getattr(self, "_reddit_tok", None):
            return self._reddit_tok
        try:
            basic = base64.b64encode(f"{cid}:{csec}".encode()).decode()
            body = b"grant_type=client_credentials"
            req = urllib.request.Request("https://www.reddit.com/api/v1/access_token", data=body,
                                         headers={"Authorization": f"Basic {basic}", "User-Agent": ua,
                                                  "Content-Type": "application/x-www-form-urlencoded"})
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                tok = json.loads(r.read()).get("access_token")
                self._reddit_tok = tok
                return tok
        except Exception:
            return None

    def stocktwits(self, ticker: str) -> Fetch:
        """StockTwits symbol stream — cashtag-native messages with Bullish/Bearish
        sentiment tags. Public read endpoint (rate-limited); no auth required."""
        ticker = ticker.upper()
        if self.prefer_live:
            url = f"https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json"
            status, data = self._http_json(url, {"User-Agent": "secfedclaw-watch/2.0"})
            if status == 200 and data:
                return self._live(f"stocktwits_{ticker}", status, data, url, note="stocktwits symbol stream")
        return self._replay(f"stocktwits_{ticker}", f"*/stocktwits_*{ticker}*.json", f"*stocktwits*{ticker.lower()}*.json",
                            note="stocktwits unavailable offline")

    def sec_submissions(self, cik10: str) -> Fetch:
        if self.live_available():
            ua = self.env.get("SEC_USER_AGENT", "secfedclaw research")
            url = f"https://data.sec.gov/submissions/CIK{cik10}.json"
            status, data = self._http_json(url, {"User-Agent": ua})
            if status == 200 and data:
                return self._live(f"sec_submissions_{cik10}", status, data, url)
        return self._replay(f"sec_submissions_{cik10}", "*/sec_aapl_submissions.json", "*sec_aapl_submissions*")

    def finra_otc_threshold(self) -> Fetch:
        return self._replay("finra_otc_threshold", "*/finra_otc_threshold_sample.json", "*/finra_data_otc_threshold.json")

    def nasdaq_halts(self) -> Fetch:
        return self._replay("nasdaq_halts", "*/nasdaq_trade_halts_current_sample.json")

    def reg_sho_threshold(self) -> Fetch:
        return self._replay("reg_sho_threshold", "*/nasdaq_reg_sho_*_sample.json")

    def sec_litigation_releases(self) -> Fetch:
        """SEC litigation-releases RSS feed (enforcement history). Live or replay."""
        ua = self.env.get("SEC_USER_AGENT", "secfedclaw research robert.david.brown@gmail.com")
        url = "https://www.sec.gov/rss/litigation/litreleases.xml"
        if self.live_available_sec(ua):
            status, data = self._http_text(url, {"User-Agent": ua})
            if status == 200 and data:
                return self._live("sec_litigation_releases", status, data, url, note="SEC litigation RSS")
        return self._replay("sec_litigation_releases", "*litigation*release*.xml", "*litreleases*",
                            note="enforcement feed unavailable offline")

    # ---- EDGAR daily-diff pipeline sources ------------------------------
    def sec_daily_index(self, day: str) -> Fetch:
        """SEC daily-index master file (pipe-delimited) for a YYYY-MM-DD day."""
        ua = self.env.get("SEC_USER_AGENT", "secfedclaw research robert.david.brown@gmail.com")
        y, m, d = day.split("-")
        q = (int(m) - 1) // 3 + 1
        url = f"https://www.sec.gov/Archives/edgar/daily-index/{y}/QTR{q}/master.{y}{m}{d}.idx"
        if self.live_available_sec(ua):
            status, data = self._http_text(url, {"User-Agent": ua})
            if status == 200 and data:
                return self._live(f"sec_daily_index_{day}", status, data, url, note="SEC daily-index master.idx")
        # replay: a cached daily index if the operator saved one
        return self._replay(f"sec_daily_index_{day}", f"*daily_index*{y}{m}{d}*",
                            "*sec_daily_index*", note="cached daily index (if present)")

    def sec_company_tickers(self) -> Fetch:
        ua = self.env.get("SEC_USER_AGENT", "secfedclaw research robert.david.brown@gmail.com")
        if self.live_available_sec(ua):
            status, data = self._http_json("https://www.sec.gov/files/company_tickers.json",
                                           {"User-Agent": ua})
            if status == 200 and data:
                return self._live("sec_company_tickers", status, data, "https://www.sec.gov/files/company_tickers.json")
        return self._replay("sec_company_tickers", "*/sec_company_tickers.json", "*sec_company_tickers*")

    def edgar_issuer_features(self, ticker: str) -> Fetch:
        """Load issuer-event features produced by edgar_pipeline.py (if any)."""
        path = Path(__file__).resolve().parent / "out" / "edgar" / f"issuer_features_{ticker.upper()}.json"
        if not path.exists():
            return Fetch(name=f"edgar_issuer_features_{ticker.upper()}", mode="unavailable",
                         status=None, data=None, note="no EDGAR issuer features; run edgar_pipeline.py")
        raw = path.read_bytes()
        try:
            data = json.loads(raw)
        except Exception:
            data = None
        return Fetch(name=f"edgar_issuer_features_{ticker.upper()}", mode="replay", status=200,
                     data=data, artifact_path=str(path), sha256=sha256_bytes(raw),
                     note="EDGAR issuer-event features")

    def live_available_sec(self, ua: str) -> bool:
        """Lightweight SEC reachability probe, separate from Polygon."""
        if not self.prefer_live:
            return False
        status, _ = self._http_text("https://www.sec.gov/files/company_tickers.json", {"User-Agent": ua})
        return status == 200

    def _http_text(self, url: str, headers: dict[str, str] | None = None) -> tuple[int | None, Any]:
        try:
            req = urllib.request.Request(url, headers=headers or {})
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, None
        except Exception:
            return None, None
