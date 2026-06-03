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
                return Fetch(name=f"polygon_daily_range_{ticker}", mode="live", status=status, data=data,
                             source_url_redacted=redact(url), note=f"{days}d daily aggregates")
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
                return Fetch(name=f"polygon_prev_{ticker}", mode="live", status=status, data=data,
                             source_url_redacted=redact(url))
        return self._replay(f"polygon_prev_{ticker}", f"*/polygon_prev_{ticker}.json", f"*prev_aggregate_{ticker.lower()}*.json")

    def polygon_grouped_daily(self) -> Fetch:
        """Whole-market one-day OHLCV: the cross-sectional baseline population."""
        if self.live_available():
            pk = self.env.get("POLYGON_API_KEY", "")
            day = time.strftime("%Y-%m-%d", time.gmtime(time.time() - 86400))
            url = f"https://api.polygon.io/v2/aggs/grouped/locale/us/market/stocks/{day}?adjusted=true&apiKey={pk}"
            status, data = self._http_json(url)
            if status == 200 and data:
                return Fetch(name="polygon_grouped_daily", mode="live", status=status, data=data,
                             source_url_redacted=redact(url))
        return self._replay("polygon_grouped_daily", "*grouped_daily*.json", "*grouped_daily_market*.json")

    def polygon_snapshot(self, ticker: str) -> Fetch:
        ticker = ticker.upper()
        if self.live_available():
            pk = self.env.get("POLYGON_API_KEY", "")
            url = f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}?apiKey={pk}"
            status, data = self._http_json(url)
            if status == 200 and data:
                return Fetch(name=f"polygon_snapshot_{ticker}", mode="live", status=status, data=data,
                             source_url_redacted=redact(url))
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
                    return Fetch(name=f"x_recent_{ticker}", mode="live", status=status, data=data,
                                 source_url_redacted=redact(url))
        return self._replay(f"x_recent_{ticker}", f"*/x_recent_search_{ticker}.json", f"*x_recent_search*{ticker.lower()}*.json")

    def sec_submissions(self, cik10: str) -> Fetch:
        if self.live_available():
            ua = self.env.get("SEC_USER_AGENT", "secfedclaw research")
            url = f"https://data.sec.gov/submissions/CIK{cik10}.json"
            status, data = self._http_json(url, {"User-Agent": ua})
            if status == 200 and data:
                return Fetch(name=f"sec_submissions_{cik10}", mode="live", status=status, data=data,
                             source_url_redacted=url)
        return self._replay(f"sec_submissions_{cik10}", "*/sec_aapl_submissions.json", "*sec_aapl_submissions*")

    def finra_otc_threshold(self) -> Fetch:
        return self._replay("finra_otc_threshold", "*/finra_otc_threshold_sample.json", "*/finra_data_otc_threshold.json")

    def nasdaq_halts(self) -> Fetch:
        return self._replay("nasdaq_halts", "*/nasdaq_trade_halts_current_sample.json")

    def reg_sho_threshold(self) -> Fetch:
        return self._replay("reg_sho_threshold", "*/nasdaq_reg_sho_*_sample.json")

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
                return Fetch(name=f"sec_daily_index_{day}", mode="live", status=status, data=data,
                             source_url_redacted=url, note="SEC daily-index master.idx")
        # replay: a cached daily index if the operator saved one
        return self._replay(f"sec_daily_index_{day}", f"*daily_index*{y}{m}{d}*",
                            "*sec_daily_index*", note="cached daily index (if present)")

    def sec_company_tickers(self) -> Fetch:
        ua = self.env.get("SEC_USER_AGENT", "secfedclaw research robert.david.brown@gmail.com")
        if self.live_available_sec(ua):
            status, data = self._http_json("https://www.sec.gov/files/company_tickers.json",
                                           {"User-Agent": ua})
            if status == 200 and data:
                return Fetch(name="sec_company_tickers", mode="live", status=status, data=data)
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
