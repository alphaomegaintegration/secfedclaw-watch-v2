#!/usr/bin/env python3
"""Polygon / Massive Flat Files client for SECFEDCLAW v0.2.

S3-compatible access to historical daily-aggregate flat files using stdlib AWS
SigV4 (no boto3 dependency) and the MASSIVE_FLATFILES_* credentials. Provides
real multi-year per-ticker history so the backtest can run on actual SEC-case
windows instead of synthetic data.

Connection-aware: downloads live when credentials + network are available;
otherwise replays from cached flat files under `flatfiles/day_aggs/`. Raw
downloads are cached + hashed for custody/reproducibility.

Day-aggregate flat files (one gzipped CSV per trading day, all tickers):
  key: us_stocks_sip/day_aggs_v1/YYYY/MM/YYYY-MM-DD.csv.gz
  columns (parsed by header): ticker, volume, open, close, high, low,
                              window_start (ns epoch), transactions

WATCH-only: historical market data is anomaly *context*, never a trading signal
or proof of misconduct.
"""
from __future__ import annotations

import csv
import datetime as dt
import gzip
import hashlib
import hmac
import io
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import load_env, fed_claw_root  # noqa: E402

ENDPOINT = "https://files.massive.com"
HOST = "files.massive.com"
BUCKET = "flatfiles"
REGION = "us-east-1"
SERVICE = "s3"
ACCESS_KEY_ENVS = ["MASSIVE_FLATFILES_ACCESS_KEY_ID", "POLYGON_FLATFILES_ACCESS_KEY_ID", "AWS_ACCESS_KEY_ID"]
SECRET_KEY_ENVS = ["MASSIVE_FLATFILES_SECRET_ACCESS_KEY", "POLYGON_FLATFILES_SECRET_ACCESS_KEY", "AWS_SECRET_ACCESS_KEY"]


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def day_aggs_key(day: str) -> str:
    y, m, _ = day.split("-")
    return f"us_stocks_sip/day_aggs_v1/{y}/{m}/{day}.csv.gz"


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def _sigv4_key(secret: str, date_stamp: str) -> bytes:
    k = _sign(("AWS4" + secret).encode(), date_stamp)
    k = _sign(k, REGION)
    k = _sign(k, SERVICE)
    return _sign(k, "aws4_request")


def signed_get_request(access_key: str, secret_key: str, key: str,
                       now: dt.datetime | None = None) -> urllib.request.Request:
    now = now or dt.datetime.now(dt.timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    canonical_uri = "/" + BUCKET + "/" + urllib.parse.quote(key)
    payload_hash = hashlib.sha256(b"").hexdigest()
    canonical_headers = f"host:{HOST}\nx-amz-content-sha256:{payload_hash}\nx-amz-date:{amz_date}\n"
    signed_headers = "host;x-amz-content-sha256;x-amz-date"
    canonical_request = "\n".join(["GET", canonical_uri, "", canonical_headers, signed_headers, payload_hash])
    scope = f"{date_stamp}/{REGION}/{SERVICE}/aws4_request"
    string_to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope,
                                hashlib.sha256(canonical_request.encode()).hexdigest()])
    signature = hmac.new(_sigv4_key(secret_key, date_stamp), string_to_sign.encode(), hashlib.sha256).hexdigest()
    authorization = (f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, "
                     f"SignedHeaders={signed_headers}, Signature={signature}")
    return urllib.request.Request(ENDPOINT + canonical_uri, headers={
        "Host": HOST, "x-amz-date": amz_date, "x-amz-content-sha256": payload_hash,
        "Authorization": authorization, "User-Agent": "SECFEDCLAW-flatfiles/2.0 read-only",
    })


def parse_day_aggs_csv(raw_gz_or_csv: bytes) -> dict[str, dict[str, Any]]:
    """Parse a day_aggs CSV(.gz) into {ticker: {o,h,l,c,v,vw,t,n}} keyed by header."""
    data = raw_gz_or_csv
    if data[:2] == b"\x1f\x8b":  # gzip magic
        data = gzip.decompress(data)
    text = data.decode("utf-8", "replace")
    out: dict[str, dict[str, Any]] = {}
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        t = (row.get("ticker") or row.get("T") or "").upper()
        if not t:
            continue
        try:
            o = float(row.get("open") or row.get("o") or 0)
            c = float(row.get("close") or row.get("c") or 0)
            h = float(row.get("high") or row.get("h") or 0)
            low = float(row.get("low") or row.get("l") or 0)
            v = float(row.get("volume") or row.get("v") or 0)
            n = float(row.get("transactions") or row.get("n") or 0)
            ws = row.get("window_start") or row.get("t") or 0
            t_ms = int(int(ws) / 1_000_000) if str(ws).isdigit() and len(str(ws)) > 13 else int(float(ws or 0))
        except (ValueError, TypeError):
            continue
        out[t] = {"o": o, "c": c, "h": h, "l": low, "v": v,
                  "vw": (o + c) / 2 if (o and c) else c, "t": t_ms, "n": n}
    return out


class FlatFilesClient:
    def __init__(self, root: Path | None = None, prefer_live: bool = True, timeout: int = 30):
        self.root = root or fed_claw_root()
        self.env = load_env(self.root)
        self.prefer_live = prefer_live
        self.timeout = timeout
        self.cache_dir = self.root / "flatfiles" / "day_aggs"
        self._creds = self._resolve_creds()

    def _resolve_creds(self) -> tuple[str | None, str | None]:
        ak = next((self.env[n] for n in ACCESS_KEY_ENVS if self.env.get(n)), None)
        sk = next((self.env[n] for n in SECRET_KEY_ENVS if self.env.get(n)), None)
        return ak, sk

    def credentials_present(self) -> bool:
        return all(self._creds)

    def get_day_aggs(self, day: str) -> dict[str, Any]:
        """Return {'mode','source','sha256','tickers':{...}} for a trading day."""
        # 1) cache / replay
        for cached in (self.cache_dir / f"{day}.csv.gz", self.cache_dir / f"{day}.csv"):
            if cached.exists():
                raw = cached.read_bytes()
                return {"mode": "replay", "source": str(cached), "sha256": sha256_bytes(raw),
                        "tickers": parse_day_aggs_csv(raw)}
        # 2) live download
        if self.prefer_live and self.credentials_present():
            raw = self._download(day_aggs_key(day))
            if raw:
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                (self.cache_dir / f"{day}.csv.gz").write_bytes(raw)
                return {"mode": "live", "source": ENDPOINT + "/" + BUCKET + "/" + day_aggs_key(day),
                        "sha256": sha256_bytes(raw), "tickers": parse_day_aggs_csv(raw)}
        return {"mode": "unavailable", "source": None, "sha256": None, "tickers": {}}

    def _download(self, key: str) -> bytes | None:
        ak, sk = self._creds
        try:
            req = signed_get_request(ak, sk, key)
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return r.read() if r.status == 200 else None
        except (urllib.error.HTTPError, urllib.error.URLError, Exception):
            return None

    # ---- assemble v0.2 market fetches from flat files -------------------
    def market_fetches(self, ticker: str, event_date: str, lookback_days: int = 70) -> dict[str, Any]:
        """Build daily_range (ticker bars) + grouped (event-day cross-section)
        Fetch-like objects for scoring_v2, from real flat-file history."""
        ticker = ticker.upper()
        dates = _trading_days_back(event_date, lookback_days)
        bars: list[dict[str, Any]] = []
        grouped_event: dict[str, Any] | None = None
        modes = set()
        srcs = []
        for d in dates:
            day = self.get_day_aggs(d)
            modes.add(day["mode"])
            if day["tickers"].get(ticker):
                bars.append(day["tickers"][ticker])
            if d == event_date and day["tickers"]:
                grouped_event = {"results": [{"T": t, **b} for t, b in day["tickers"].items()]}
                srcs.append(day["source"])
        daily_range = _FF(f"flatfiles_daily_{ticker}", {"results": bars} if bars else None,
                          "live" if "live" in modes else ("replay" if "replay" in modes else "unavailable"))
        grouped = _FF("flatfiles_grouped", grouped_event,
                      "live" if "live" in modes else ("replay" if "replay" in modes else "unavailable"),
                      source=srcs[0] if srcs else None)
        return {"daily_range": daily_range, "grouped": grouped, "n_days_with_bars": len(bars)}


class _FF:
    """Fetch-compatible wrapper for flat-file-derived data."""
    def __init__(self, name, data, mode, source=None):
        self.name = name
        self.data = data
        self.mode = mode
        self.status = 200 if data is not None else None
        self.artifact_path = source
        self.sha256 = None
        self.source_url_redacted = source

    def ok(self) -> bool:
        return self.data is not None


def _trading_days_back(end: str, n: int) -> list[str]:
    e = dt.datetime.strptime(end, "%Y-%m-%d").date()
    days, d, count = [], e, 0
    while count < n + 1:
        if d.weekday() < 5:
            days.append(d.isoformat())
            count += 1
        d -= dt.timedelta(days=1)
    return sorted(days)
