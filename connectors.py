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
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from config import load_env, fed_claw_root
from concurrency import RateLimiter, retry

# Per-host rate limiting (active in LIVE mode only — replay does no HTTP). Now
# that Scout fetches run concurrently, same-host bursts must respect fair-access
# limits. SEC asks for <=10 req/s; keep headroom. Others get a generous default.
_HOST_RATE = {"www.sec.gov": 8.0, "data.sec.gov": 8.0, "efts.sec.gov": 8.0}
_DEFAULT_HOST_RATE = 15.0
_host_limiters: dict[str, RateLimiter] = {}
_host_limiters_lock = threading.Lock()


def _limiter_for(url: str) -> RateLimiter:
    host = urllib.parse.urlsplit(url).netloc
    with _host_limiters_lock:
        lim = _host_limiters.get(host)
        if lim is None:
            rate = _HOST_RATE.get(host, _DEFAULT_HOST_RATE)
            lim = RateLimiter(rate, burst=max(1, int(rate)))
            _host_limiters[host] = lim
        return lim


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
        self._lock = threading.Lock()  # guards _lrd init + live_available probe under concurrent gather
        self._http_attempts = 3        # transient-error retries for live HTTP
        self._http_backoff = 0.5

    # ---- live custody: persist raw responses + sha256 -------------------
    def _live(self, name: str, status: int | None, data: Any, url: str | None = None,
              note: str = "") -> "Fetch":
        """Wrap a successful LIVE response, persisting it for custody/replay."""
        path = sha = None
        try:
            import time as _t
            with self._lock:
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
        except Exception as e:
            warnings.warn(f"live_cache write failed for {name!r}: {e}", RuntimeWarning, stacklevel=2)
        return Fetch(name=name, mode="live", status=status, data=data,
                     artifact_path=path, sha256=sha,
                     source_url_redacted=redact(url) if url else None, note=note or "live (persisted to live_cache)")

    # ---- live HTTP (graceful) ------------------------------------------
    def _http_json(self, url: str, headers: dict[str, str] | None = None) -> tuple[int | None, Any]:
        def _once() -> tuple[int | None, Any]:
            _limiter_for(url).acquire()  # per-host fair-access throttle (concurrent gather)
            req = urllib.request.Request(url, headers=headers or {})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    raw = r.read()
                    try:
                        return r.status, json.loads(raw)
                    except Exception:
                        return r.status, raw
            except urllib.error.HTTPError as e:
                return e.code, None  # definitive HTTP status — do not retry
        try:
            # Retry only transient transport errors; HTTPError is handled above
            # (returned as a value) so 4xx/5xx statuses are never retried here.
            return retry(_once, attempts=getattr(self, "_http_attempts", 3),
                         backoff=getattr(self, "_http_backoff", 0.5),
                         retry_on=(urllib.error.URLError, TimeoutError))
        except Exception:
            self._live_ok = False
            return None, None

    def live_available(self) -> bool:
        """Cheap probe (cached). Polygon market status is a light endpoint."""
        if self._live_ok is not None:
            return self._live_ok
        with self._lock:  # double-checked: only the first concurrent caller probes
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
        """X recent search for a cashtag. Tries: API → Firecrawl → replay."""
        ticker = ticker.upper()
        # Path 1: X API v2 (if bearer token + credits available)
        bearer = self.env.get("X_BEARER_TOKEN") or self.env.get("TWITTER_BEARER_TOKEN")
        if bearer and self.prefer_live:
            url = (f"https://api.twitter.com/2/tweets/search/recent?query=%24{ticker}"
                   f"&max_results=25&tweet.fields=public_metrics,created_at,author_id,entities")
            status, data = self._http_json(url, {"Authorization": f"Bearer {bearer}"})
            if status == 200 and data:
                return self._live(f"x_recent_{ticker}", status, data, url)
        # Path 2: Firecrawl via Nitter (open-source X frontend, no login needed)
        fc_key = self.env.get("FIRECRAWL_API_KEY")
        if fc_key and self.prefer_live:
            for nitter_host in ("nitter.net", "nitter.privacydev.net"):
                try:
                    x_url = f"https://{nitter_host}/search?f=tweets&q=%24{ticker}"
                    api_url = "https://api.firecrawl.dev/v1/scrape"
                    body = json.dumps({"url": x_url, "formats": ["markdown"],
                                       "waitFor": 3000}).encode()
                    req = urllib.request.Request(api_url, data=body, headers={
                        "Authorization": f"Bearer {fc_key}",
                        "Content-Type": "application/json",
                        "User-Agent": "secfedclaw-watch/2.0"})
                    with urllib.request.urlopen(req, timeout=30) as r:
                        fc_data = json.loads(r.read())
                        if r.status == 200 and fc_data.get("success"):
                            md = (fc_data.get("data") or {}).get("markdown", "")
                            if len(md) > 200:  # has actual content, not just nav
                                return self._live(f"x_recent_{ticker}", 200, fc_data,
                                                  redact(api_url), note=f"x ${ticker} via nitter+firecrawl")
                except Exception:
                    continue
        return self._replay(f"x_recent_{ticker}", f"*/x_recent_search_{ticker}.json", f"*x_recent_search*{ticker.lower()}*.json")

    def reddit_oauth(self, ticker: str, subreddits: list[str] | None = None) -> Fetch:
        """Reddit search for a ticker across finance subreddits.

        Two access paths, tried in order:
        1. Public .json endpoint (no auth needed) — appends .json to the search URL.
           Works without any API key or OAuth; just needs a User-Agent header.
        2. OAuth (client_credentials) — if REDDIT_CLIENT_ID/SECRET are set.
        Falls back to replay from cached artifacts if both fail.
        """
        ticker = ticker.upper()
        subs = "+".join(subreddits or ["pennystocks", "stocks", "wallstreetbets",
                                        "Shortsqueeze", "smallstreetbets", "RobinHoodPennyStocks"])
        ua = self.env.get("REDDIT_USER_AGENT", "secfedclaw-watch/2.0 by u/secfedclaw")
        if self.prefer_live:
            # Path 1: RSS feed (most reliable — works when .json is 403-blocked)
            rss_url = (f"https://www.reddit.com/r/{subs}/search.rss?q=%24{ticker}+OR+{ticker}"
                       f"&restrict_sr=on&sort=new&limit=25&t=week")
            rss_status, rss_data = self._http_text(rss_url, {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"})
            if rss_status == 200 and rss_data and "<entry>" in rss_data:
                return self._live(f"reddit_{ticker}", rss_status, rss_data, redact(rss_url),
                                  note=f"reddit RSS r/{subs} (no auth)")
            # Path 2: public .json endpoint (no auth, no key — blocked on some IPs)
            json_url = (f"https://www.reddit.com/r/{subs}/search.json?q=%24{ticker}+OR+{ticker}"
                        f"&restrict_sr=on&sort=new&limit=50&t=week")
            status, data = self._http_json(json_url, {"User-Agent": ua})
            if status == 200 and data:
                return self._live(f"reddit_{ticker}", status, data, redact(json_url),
                                  note=f"reddit .json r/{subs} (no auth)")
            # Path 3: OAuth fallback (if creds are available)
            cid = self.env.get("REDDIT_CLIENT_ID")
            csec = self.env.get("REDDIT_CLIENT_SECRET")
            if cid and csec:
                token = self._reddit_token(cid, csec, ua)
                if token:
                    url = (f"https://oauth.reddit.com/r/{subs}/search?q=%24{ticker}%20OR%20{ticker}"
                           f"&restrict_sr=on&sort=new&limit=50&t=week")
                    status, data = self._http_json(url, {"Authorization": f"bearer {token}", "User-Agent": ua})
                    if status == 200 and data:
                        return self._live(f"reddit_{ticker}", status, data, url, note=f"reddit oauth r/{subs}")
        return self._replay(f"reddit_{ticker}", f"*/reddit_*{ticker}*.json", f"*reddit*{ticker.lower()}*.json",
                            note="reddit unavailable offline")

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

    # ---- additional social platforms ------------------------------------
    def discord_search(self, ticker: str) -> Fetch:
        """Discord via bot API. Searches authorized servers for ticker mentions.
        Requires DISCORD_BOT_TOKEN + DISCORD_GUILD_IDS (comma-separated).
        Only reads channels the bot has access to — no unauthorized scraping."""
        ticker = ticker.upper()
        bot_token = self.env.get("DISCORD_BOT_TOKEN")
        guild_ids = [g.strip() for g in (self.env.get("DISCORD_GUILD_IDS") or "").split(",") if g.strip()]
        if self.prefer_live and bot_token and guild_ids:
            messages: list[dict] = []
            for gid in guild_ids[:5]:  # cap at 5 guilds
                # Search guild channels for ticker mentions
                url = f"https://discord.com/api/v10/guilds/{gid}/messages/search?content=%24{ticker}+OR+{ticker}&limit=25"
                status, data = self._http_json(url, {"Authorization": f"Bot {bot_token}"})
                if status == 200 and isinstance(data, dict):
                    for msg in (data.get("messages") or []):
                        if isinstance(msg, list):
                            msg = msg[0] if msg else {}
                        if isinstance(msg, dict):
                            messages.append(msg)
            if messages:
                return self._live(f"discord_{ticker}", 200, {"messages": messages}, None,
                                  note=f"discord bot search {len(messages)} msgs across {len(guild_ids)} guild(s)")
        # Fallback: scrape public Discord server listing pages via Firecrawl
        fc_key = self.env.get("FIRECRAWL_API_KEY")
        if fc_key and self.prefer_live:
            try:
                url = f"https://disboard.org/search?keyword={ticker}+stock"
                api_url = "https://api.firecrawl.dev/v1/scrape"
                body = json.dumps({"url": url, "formats": ["markdown"], "waitFor": 3000}).encode()
                req = urllib.request.Request(api_url, data=body, headers={
                    "Authorization": f"Bearer {fc_key}", "Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=30) as r:
                    data = json.loads(r.read())
                    md = (data.get("data") or {}).get("markdown", "")
                    if r.status == 200 and data.get("success") and len(md) > 200:
                        return self._live(f"discord_{ticker}", 200, data,
                                          redact(api_url), note=f"discord ${ticker} via disboard+firecrawl")
            except Exception as e:
                warnings.warn(f"discord firecrawl fetch failed for {ticker!r}: {e}", RuntimeWarning, stacklevel=2)
        return self._replay(f"discord_{ticker}", f"*/discord_*{ticker}*.json",
                            note="discord unavailable")

    def instagram_hashtag(self, ticker: str) -> Fetch:
        """Instagram hashtag search via Picuki (public IG proxy) + Firecrawl.
        Instagram.com requires login; Picuki mirrors public hashtag pages."""
        ticker = ticker.upper()
        fc_key = self.env.get("FIRECRAWL_API_KEY")
        if self.prefer_live and fc_key:
            for url in (f"https://www.picuki.com/tag/{ticker.lower()}",
                        f"https://imginn.com/tag/{ticker.lower()}/"):
                try:
                    api_url = "https://api.firecrawl.dev/v1/scrape"
                    body = json.dumps({"url": url, "formats": ["markdown"],
                                       "waitFor": 3000}).encode()
                    req = urllib.request.Request(api_url, data=body, headers={
                        "Authorization": f"Bearer {fc_key}",
                        "Content-Type": "application/json",
                        "User-Agent": "secfedclaw-watch/2.0"})
                    with urllib.request.urlopen(req, timeout=30) as r:
                        data = json.loads(r.read())
                        md = (data.get("data") or {}).get("markdown", "")
                        if r.status == 200 and data.get("success") and len(md) > 100:
                            return self._live(f"instagram_{ticker}", 200, data,
                                              redact(api_url), note=f"instagram #{ticker.lower()} via picuki+firecrawl")
                except Exception:
                    continue
        return self._replay(f"instagram_{ticker}", f"*/instagram_*{ticker}*.json",
                            note="instagram unavailable")

    def facebook_search(self, ticker: str) -> Fetch:
        """Stock forum search via Firecrawl as Facebook proxy. Facebook blocks
        direct scraping; we use public stock forums (Stockhouse, InvestorsHub)
        which aggregate the same retail discussion that FB groups carry."""
        ticker = ticker.upper()
        fc_key = self.env.get("FIRECRAWL_API_KEY")
        if self.prefer_live and fc_key:
            for url in (f"https://stockhouse.com/companies/bullboard?symbol={ticker.lower()}",
                        f"https://investorshub.advfn.com/search/search.aspx?q={ticker}"):
                try:
                    api_url = "https://api.firecrawl.dev/v1/scrape"
                    body = json.dumps({"url": url, "formats": ["markdown"]}).encode()
                    req = urllib.request.Request(api_url, data=body, headers={
                        "Authorization": f"Bearer {fc_key}",
                        "Content-Type": "application/json",
                        "User-Agent": "secfedclaw-watch/2.0"})
                    with urllib.request.urlopen(req, timeout=30) as r:
                        data = json.loads(r.read())
                        md = (data.get("data") or {}).get("markdown", "")
                        if r.status == 200 and data.get("success") and len(md) > 200:
                            return self._live(f"forums_{ticker}", 200, data,
                                              redact(api_url), note=f"stock forums ${ticker} via firecrawl")
                except Exception:
                    continue
        return self._replay(f"facebook_{ticker}", f"*/facebook_*{ticker}*.json",
                            note="stock forums unavailable")

    def social_web_search(self, ticker: str) -> Fetch:
        """Broad social-web search via Firecrawl: scrapes public stock forums,
        investing.com discussions, and other social finance sites for ticker mentions.
        Useful for catching promotion across platforms not directly integrated."""
        ticker = ticker.upper()
        fc_key = self.env.get("FIRECRAWL_API_KEY")
        if self.prefer_live and fc_key:
            # Search finance forums for the ticker
            urls = [
                f"https://www.google.com/search?q=%24{ticker}+stock+pump+promotion+site%3Areddit.com+OR+site%3Atwitter.com+OR+site%3Adiscord.com&tbs=qdr:w",
            ]
            for search_url in urls:
                try:
                    api_url = "https://api.firecrawl.dev/v1/scrape"
                    body = json.dumps({"url": search_url, "formats": ["markdown"]}).encode()
                    req = urllib.request.Request(api_url, data=body, headers={
                        "Authorization": f"Bearer {fc_key}",
                        "Content-Type": "application/json",
                        "User-Agent": "secfedclaw-watch/2.0"})
                    with urllib.request.urlopen(req, timeout=30) as r:
                        data = json.loads(r.read())
                        if r.status == 200 and data.get("success"):
                            return self._live(f"social_web_{ticker}", 200, data,
                                              redact(api_url), note=f"social web search ${ticker} via firecrawl")
                except Exception as e:
                    warnings.warn(f"social_web firecrawl fetch failed for {ticker!r}: {e}", RuntimeWarning, stacklevel=2)
        return self._replay(f"social_web_{ticker}", f"*/social_web_*{ticker}*.json",
                            note="social web search unavailable")

    # ---- FMP (Financial Modeling Prep) ------------------------------------
    def fmp_quote(self, ticker: str) -> Fetch:
        """Real-time stock quote from FMP (stable API). Provides price, volume,
        market cap, P/E, day range, year range — complements Polygon snapshot."""
        ticker = ticker.upper()
        fmp_key = self.env.get("FMP_API_KEY")
        if fmp_key and self.prefer_live:
            url = f"https://financialmodelingprep.com/stable/quote?symbol={ticker}&apikey={fmp_key}"
            status, data = self._http_json(url)
            if status == 200 and data:
                return self._live(f"fmp_quote_{ticker}", status, data, redact(url), note="FMP real-time quote")
        return self._replay(f"fmp_quote_{ticker}", f"*/fmp_quote_{ticker}*.json",
                            note="FMP quote unavailable; set FMP_API_KEY")

    def fmp_profile(self, ticker: str) -> Fetch:
        """Company profile from FMP: sector, industry, market cap, description,
        CEO, employees, IPO date. Enriches issuer context."""
        ticker = ticker.upper()
        fmp_key = self.env.get("FMP_API_KEY")
        if fmp_key and self.prefer_live:
            url = f"https://financialmodelingprep.com/stable/profile?symbol={ticker}&apikey={fmp_key}"
            status, data = self._http_json(url)
            if status == 200 and data:
                return self._live(f"fmp_profile_{ticker}", status, data, redact(url), note="FMP company profile")
        return self._replay(f"fmp_profile_{ticker}", f"*/fmp_profile_{ticker}*.json",
                            note="FMP profile unavailable")

    def fmp_historical(self, ticker: str, days: int = 90) -> Fetch:
        """Historical daily prices from FMP (up to 30 years). Provides OHLCV + VWAP
        + change%. Alternative/complement to Polygon daily range."""
        ticker = ticker.upper()
        fmp_key = self.env.get("FMP_API_KEY")
        if fmp_key and self.prefer_live:
            import time as _t
            end = _t.strftime("%Y-%m-%d")
            start = _t.strftime("%Y-%m-%d", _t.gmtime(_t.time() - days * 86400))
            url = (f"https://financialmodelingprep.com/stable/historical-price-eod/full"
                   f"?symbol={ticker}&from={start}&to={end}&apikey={fmp_key}")
            status, data = self._http_json(url)
            if status == 200 and data:
                return self._live(f"fmp_historical_{ticker}", status, data, redact(url),
                                  note=f"FMP {days}d historical daily")
        return self._replay(f"fmp_historical_{ticker}", f"*/fmp_historical_{ticker}*.json",
                            note="FMP historical unavailable")

    # ---- corporate actions (splits / name changes) -----------------------
    def polygon_splits(self, ticker: str, lookback_days: int = 60) -> Fetch:
        """Recent stock splits for a ticker via Polygon reference API.
        Used to flag needs_adjustment_review: a recent split can make
        volume/price anomaly scores artificially high (pre-split data
        vs post-split levels). No Polygon entitlement required — free tier."""
        ticker = ticker.upper()
        pk = self.env.get("POLYGON_API_KEY")
        if pk and self.prefer_live:
            import time as _t
            since = _t.strftime("%Y-%m-%d", _t.gmtime(_t.time() - lookback_days * 86400))
            url = (f"https://api.polygon.io/v3/reference/splits"
                   f"?ticker={ticker}&execution_date.gte={since}&limit=10&apiKey={pk}")
            status, data = self._http_json(url)
            if status == 200 and data:
                return self._live(f"splits_{ticker}", status, data, redact(url),
                                  note=f"Polygon splits {ticker} since {since}")
        return self._replay(f"splits_{ticker}", f"*/splits_{ticker}*.json",
                            note="splits unavailable")

    # ---- options flow (unusual activity) ----------------------------------
    def polygon_options_snapshot(self, ticker: str) -> Fetch:
        """Unusual options activity snapshot from Polygon (requires options entitlement).
        Captures call/put open interest, implied volatility skew, and expiry
        clustering — pre-pump coordinated call buying is a recognized signal."""
        ticker = ticker.upper()
        pk = self.env.get("POLYGON_API_KEY")
        if pk and self.prefer_live:
            url = (f"https://api.polygon.io/v3/snapshot/options/{ticker}"
                   f"?limit=50&sort=open_interest&order=desc&apiKey={pk}")
            status, data = self._http_json(url)
            if status == 200 and data:
                return self._live(f"options_{ticker}", status, data, redact(url),
                                  note=f"Polygon options snapshot {ticker}")
            if status == 403:
                return self._replay(f"options_{ticker}", f"*/options_{ticker}*.json",
                                    note="options data requires Polygon options entitlement (403)")
        return self._replay(f"options_{ticker}", f"*/options_{ticker}*.json",
                            note="options unavailable")

    # ---- promotion disclosures (OTC Markets) ------------------------------
    def otc_promotion_disclosure(self, ticker: str) -> Fetch:
        """Stock promotion disclosures from OTC Markets public API.
        SEC-required paid-promotion filings for OTC/Pink Sheet issuers.
        High-signal: paid promoters are a hallmark of pump-and-dump schemes."""
        ticker = ticker.upper()
        if self.prefer_live:
            url = f"https://www.otcmarkets.com/research/stock-promoters/api/search?symbol={ticker}"
            ua = self.env.get("SEC_USER_AGENT", "secfedclaw research")
            status, data = self._http_json(url, {"User-Agent": ua, "Accept": "application/json"})
            if status == 200 and data:
                return self._live(f"otc_promo_{ticker}", status, data, url,
                                  note=f"OTC Markets promotion disclosures {ticker}")
        return self._replay(f"otc_promo_{ticker}", f"*/otc_promo_{ticker}*.json",
                            note="OTC promotion disclosures unavailable")

    # ---- OpenInsider (SEC Form 4 insider trades) -------------------------
    def openinsider_trades(self, ticker: str, lookback_days: int = 90) -> Fetch:
        """Insider purchase/sale activity from openinsider.com (public SEC Form 4 data).
        High-value signal: insiders selling into promoted demand is a classic pump tell.
        No credentials required — public site with clean HTML tables."""
        ticker = ticker.upper()
        fc_key = self.env.get("FIRECRAWL_API_KEY")
        if fc_key and self.prefer_live:
            try:
                url = f"http://openinsider.com/search?q={ticker}"
                api_url = "https://api.firecrawl.dev/v1/scrape"
                body = json.dumps({
                    "url": url,
                    "formats": ["markdown"],
                    "waitFor": 2000,
                    "includeTags": ["table"],
                }).encode()
                req = urllib.request.Request(api_url, data=body, headers={
                    "Authorization": f"Bearer {fc_key}",
                    "Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=30) as r:
                    data = json.loads(r.read())
                    md = (data.get("data") or {}).get("markdown", "")
                    if r.status == 200 and data.get("success") and len(md) > 100:
                        return self._live(f"openinsider_{ticker}", 200, {"markdown": md, "url": url},
                                          redact(api_url),
                                          note=f"OpenInsider Form 4 trades for {ticker}")
            except Exception as e:
                warnings.warn(f"openinsider fetch failed for {ticker!r}: {e}", RuntimeWarning, stacklevel=2)
        return self._replay(f"openinsider_{ticker}", f"*/openinsider_{ticker}*.json",
                            note="OpenInsider unavailable — set FIRECRAWL_API_KEY")

    # ---- Glint.trade (pump/dump signal tracker) -------------------------
    def glint_trade_signals(self, ticker: str) -> Fetch:
        """Pump-and-dump signal tracker from glint.trade.
        Requires Firecrawl with JS rendering (React SPA with Cloudflare protection)."""
        ticker = ticker.upper()
        fc_key = self.env.get("FIRECRAWL_API_KEY")
        if fc_key and self.prefer_live:
            try:
                url = f"https://glint.trade/ticker/{ticker}"
                api_url = "https://api.firecrawl.dev/v1/scrape"
                body = json.dumps({
                    "url": url,
                    "formats": ["markdown"],
                    "waitFor": 4000,
                    "mobile": False,
                }).encode()
                req = urllib.request.Request(api_url, data=body, headers={
                    "Authorization": f"Bearer {fc_key}",
                    "Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=45) as r:
                    data = json.loads(r.read())
                    md = (data.get("data") or {}).get("markdown", "")
                    if r.status == 200 and data.get("success") and len(md) > 100:
                        return self._live(f"glint_{ticker}", 200, {"markdown": md, "url": url},
                                          redact(api_url),
                                          note=f"Glint.trade signals for {ticker}")
            except Exception as e:
                warnings.warn(f"glint.trade fetch failed for {ticker!r}: {e}", RuntimeWarning, stacklevel=2)
        return self._replay(f"glint_{ticker}", f"*/glint_{ticker}*.json",
                            note="Glint.trade unavailable")

    # ---- MyFXBook community sentiment ------------------------------------
    def myfxbook_community(self, ticker: str) -> Fetch:
        """MyFXBook trading community sentiment and watchlist signals.
        Account: robert.david.brown@gmail.com / profile browngeek666.
        Uses Firecrawl to access community pages; falls back to replay."""
        ticker = ticker.upper()
        fc_key = self.env.get("FIRECRAWL_API_KEY")
        if fc_key and self.prefer_live:
            try:
                # Community outlook/sentiment page — publicly accessible
                url = f"https://www.myfxbook.com/community/outlook/{ticker}"
                api_url = "https://api.firecrawl.dev/v1/scrape"
                body = json.dumps({
                    "url": url,
                    "formats": ["markdown"],
                    "waitFor": 3000,
                }).encode()
                req = urllib.request.Request(api_url, data=body, headers={
                    "Authorization": f"Bearer {fc_key}",
                    "Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=30) as r:
                    data = json.loads(r.read())
                    md = (data.get("data") or {}).get("markdown", "")
                    if r.status == 200 and data.get("success") and len(md) > 100:
                        return self._live(f"myfxbook_{ticker}", 200, {"markdown": md, "url": url},
                                          redact(api_url),
                                          note=f"MyFXBook community sentiment for {ticker}")
            except Exception as e:
                warnings.warn(f"myfxbook fetch failed for {ticker!r}: {e}", RuntimeWarning, stacklevel=2)
        return self._replay(f"myfxbook_{ticker}", f"*/myfxbook_{ticker}*.json",
                            note="MyFXBook unavailable")

    # ---- official/regulatory sources ------------------------------------
    def sec_submissions(self, cik10: str) -> Fetch:
        ua = self.env.get("SEC_USER_AGENT", "secfedclaw research robert.david.brown@gmail.com")
        if self.prefer_live and self.live_available_sec(ua):
            url = f"https://data.sec.gov/submissions/CIK{cik10}.json"
            status, data = self._http_json(url, {"User-Agent": ua})
            if status == 200 and data:
                return self._live(f"sec_submissions_{cik10}", status, data, url)
        return self._replay(f"sec_submissions_{cik10}", "*/sec_aapl_submissions.json", "*sec_aapl_submissions*")

    def finra_otc_threshold(self) -> Fetch:
        if self.prefer_live:
            url = "https://api.finra.org/data/group/otcMarket/name/thresholdList"
            status, data = self._http_json(url, {"User-Agent": "secfedclaw-watch/2.0", "Accept": "application/json"})
            if status == 200 and data:
                return self._live("finra_otc_threshold", status, data, url, note="FINRA OTC threshold list")
        return self._replay("finra_otc_threshold", "*/finra_otc_threshold_sample.json", "*/finra_data_otc_threshold.json")

    def nasdaq_halts(self) -> Fetch:
        if self.prefer_live:
            url = "https://www.nasdaqtrader.com/rss.aspx?feed=tradehalts"
            status, data = self._http_text(url, {"User-Agent": "secfedclaw-watch/2.0"})
            if status == 200 and data:
                return self._live("nasdaq_halts", status, data, url, note="Nasdaq trade halts RSS")
        return self._replay("nasdaq_halts", "*/nasdaq_trade_halts_current_sample.json")

    def reg_sho_threshold(self) -> Fetch:
        if self.prefer_live:
            for url in ("https://www.nasdaqtrader.com/dynamic/symdir/regsho/nasdaqth.txt",
                        "https://www.nasdaqtrader.com/dynamic/symdir/regsho/nyse_thrsholdlist.txt"):
                status, data = self._http_text(url, {"User-Agent": "secfedclaw-watch/2.0"})
                if status == 200 and data:
                    return self._live("reg_sho_threshold", status, data, url, note="Nasdaq Reg SHO threshold list")
        return self._replay("reg_sho_threshold", "*/nasdaq_reg_sho_*_sample.json")

    def sec_litigation_releases(self) -> Fetch:
        """SEC litigation + admin-proceeding feeds (enforcement history). No key needed."""
        ua = self.env.get("SEC_USER_AGENT", "secfedclaw research robert.david.brown@gmail.com")
        if self.prefer_live and self.live_available_sec(ua):
            # litigation releases (correct URL — /litigation/ not /rss/litigation/)
            for url in ("https://www.sec.gov/litigation/litreleases.xml",
                        "https://www.sec.gov/rss/litigation/admin.xml"):
                status, data = self._http_text(url, {"User-Agent": ua})
                if status == 200 and data:
                    return self._live("sec_litigation_releases", status, data, url, note="SEC enforcement feed")
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
