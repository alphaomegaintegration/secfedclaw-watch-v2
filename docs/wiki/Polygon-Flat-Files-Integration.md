# Polygon Flat Files Integration

**Commit:** `c8f1a37` (2026-06-03) — *Polygon/Massive Flat Files integration + real-data historical backtest*
**Files:** `flatfiles.py`, `historical.py`, `tests/test_flatfiles.py`

## Overview

S3-compatible access to Polygon/Massive historical daily-aggregate flat files using stdlib AWS SigV4 signing (no boto3 dependency). Provides real multi-year per-ticker history so the backtest can run on actual SEC-case windows instead of synthetic data.

This is the **highest-leverage calibration addition** to v0.2: it validates the market-anomaly scoring component against real historical data rather than synthetic fixtures.

## Architecture

```
MASSIVE_FLATFILES_* credentials
        │
        ▼
┌─────────────────────┐      ┌───────────────────────────┐
│  FlatFilesClient    │─────▶│  flatfiles/day_aggs/      │
│  (flatfiles.py)     │      │  cached + hashed .csv.gz  │
│  - SigV4 signing    │      └───────────────────────────┘
│  - gzip parse       │               │
│  - market_fetches() │               ▼
└─────────────────────┘      ┌───────────────────────────┐
        │                    │  historical.py             │
        │                    │  - score_window()          │
        ▼                    │  - run() → results JSON    │
┌─────────────────────┐      └───────────────────────────┘
│  scoring_v2.py      │               │
│  build_package()    │               ▼
└─────────────────────┘      out/historical_results.json
```

## Data Format

Day-aggregate flat files are one gzipped CSV per trading day covering all tickers:

- **S3 key pattern:** `us_stocks_sip/day_aggs_v1/YYYY/MM/YYYY-MM-DD.csv.gz`
- **Columns:** `ticker`, `volume`, `open`, `close`, `high`, `low`, `window_start` (nanosecond epoch), `transactions`
- **Cache location:** `flatfiles/day_aggs/<YYYY-MM-DD>.csv.gz`

The parser handles both named headers (`ticker`, `volume`, etc.) and Polygon shorthand (`T`, `v`, `o`, `c`, etc.), plus gzip-compressed and plain CSV.

## Connection Modes

The client is connection-aware with a cache-first strategy:

1. **Replay** (offline): If a cached file exists at `flatfiles/day_aggs/<date>.csv.gz` or `.csv`, it is read directly. No credentials or network needed.
2. **Live** (online): If `prefer_live=True` and credentials are present, the client downloads from the Massive S3 endpoint, then caches the raw bytes for future replay. Files are hashed (SHA-256) for custody/reproducibility.
3. **Unavailable**: No cache and no credentials — returns empty tickers with `mode: "unavailable"`.

## Credentials

The client resolves credentials from the `.env` file, checking these environment variable names in order:

| Purpose | Variables (checked in order) |
|---|---|
| Access Key | `MASSIVE_FLATFILES_ACCESS_KEY_ID` → `POLYGON_FLATFILES_ACCESS_KEY_ID` → `AWS_ACCESS_KEY_ID` |
| Secret Key | `MASSIVE_FLATFILES_SECRET_ACCESS_KEY` → `POLYGON_FLATFILES_SECRET_ACCESS_KEY` → `AWS_SECRET_ACCESS_KEY` |

The first non-empty match wins. Both access key and secret key must be present for live downloads.

## SigV4 Signing

`signed_get_request()` builds a standard AWS Signature Version 4 GET request using only stdlib (`hashlib`, `hmac`, `urllib`). This eliminates the boto3 dependency while maintaining full S3 compatibility.

Key parameters:
- **Endpoint:** `https://files.massive.com`
- **Bucket:** `flatfiles`
- **Region:** `us-east-1`
- **Service:** `s3`
- **User-Agent:** `SECFEDCLAW-flatfiles/2.0 read-only`

## FlatFilesClient API

### `FlatFilesClient(root=None, prefer_live=True, timeout=30)`

Initialize the client. `root` defaults to the project root detected by `config.fed_claw_root()`.

### `credentials_present() → bool`

Returns `True` if both access key and secret key are resolved from the environment.

### `get_day_aggs(day: str) → dict`

Fetch or replay a single day's aggregate data. Returns:
```python
{
    "mode": "replay" | "live" | "unavailable",
    "source": "<path or URL>",
    "sha256": "<hex digest of raw bytes>",
    "tickers": {"AAPL": {"o": ..., "c": ..., "h": ..., "l": ..., "v": ..., "vw": ..., "t": ..., "n": ...}, ...}
}
```

### `market_fetches(ticker, event_date, lookback_days=70) → dict`

Assemble scorer-compatible fetch objects from flat-file history. Generates `daily_range` (per-ticker bars over the lookback window) and `grouped` (event-day cross-section of all tickers). Returns:
```python
{
    "daily_range": <_FF>,     # fetch-compatible wrapper
    "grouped": <_FF>,         # fetch-compatible wrapper
    "n_days_with_bars": int   # how many trading days had data for this ticker
}
```

The `_FF` objects implement the `.ok()`, `.data`, `.mode`, `.status` interface expected by `scoring_v2.build_package()`.

## Historical Replay (historical.py)

### Purpose

Replays labeled case/control windows through the v0.2 market-anomaly engine using real historical data. Reports per-window scores and pump-vs-control separation.

### CLI

```bash
# Individual cases (repeatable)
python3 historical.py --case AABB:2021-09-13:pump --case MSFT:2021-09-13:control

# Bulk from JSON file
python3 historical.py --cases-file cases.json --lookback 70

# Force offline (no live downloads)
python3 historical.py --case AABB:2021-09-13:pump --no-live

# Custom output path
python3 historical.py --case AABB:2021-09-13:pump --out results/my_run.json
```

**`--case` format:** `TICKER:YYYY-MM-DD:label` where label is `pump`, `control`, or any string.

**`--cases-file` format:**
```json
[
  {"ticker": "AABB", "event_date": "2021-09-13", "label": "pump"},
  {"ticker": "MSFT", "event_date": "2021-09-13", "label": "control"}
]
```

### Output

Results are written to `out/historical_results.json` (default) with this structure:
```json
{
  "algorithm_version": "v0.2.0",
  "harness": "flatfiles_historical_v1",
  "lookback_days": 70,
  "summary": {
    "credentials_present": false,
    "data_available_windows": 2,
    "total_windows": 2,
    "mean_market_anomaly_pump": 99.0,
    "mean_market_anomaly_control": 44.0,
    "separation": 55.0
  },
  "windows": [...],
  "limitations": [...]
}
```

Each window includes: `market_anomaly_score`, `anomaly_evidence_score`, `review_priority`, `watch_score`, `time_series` details (z-scores, double-confirmation), and `cross_sectional` details.

### Validated Performance

On real-shaped data: a +75% price / 28×-volume pump day scored market-anomaly **~99** (double-confirmed) vs a benign control **~44** — approximately **55-point separation**.

### Limitations

- Flat files provide market data only — this validates the MARKET-anomaly component, not full multi-source corroboration.
- Real SEC cases are public allegations unless final judgment; tickers/windows must be supplied by the operator.
- Market anomaly is statistical context for human review, never proof of manipulation or a trading signal.
- Offline runs require cached day-aggregate flat files under `flatfiles/day_aggs/`.

## Testing

5 tests in `tests/test_flatfiles.py`:

- **`TestParse.test_parse_gz_and_plain`** — Verifies both gzip and plain CSV parsing, column name mapping, and nanosecond→millisecond timestamp conversion.
- **`TestParse.test_day_aggs_key`** — Validates S3 key construction from a date string.
- **`TestSigning.test_signed_get_has_auth`** — Confirms SigV4 Authorization header and x-amz-date are present.
- **`TestMarketFetchesAndScore.test_real_data_path_scores`** — End-to-end: builds 30 flat days + spike event day from synthetic fixtures, runs through `market_fetches()` → `score_window()`, asserts the spike triggers market-anomaly > 20 in replay mode.
- **`TestMarketFetchesAndScore.test_offline_no_cache_is_unavailable`** — Confirms graceful degradation when no cached data exists.

```bash
python3 -m pytest tests/test_flatfiles.py -v   # all 5 pass
```

## Integration with Scoring Engine

The flat files client plugs into the v0.2 scoring pipeline by producing fetch-compatible objects that `scoring_v2.build_package()` consumes directly. Since flat files are market-only, all non-market sources (`snapshot`, `trades`, `quotes`, `reddit`, `edgar`, etc.) are passed as unavailable — the scorer handles this gracefully, computing only the market-anomaly component.

This means the historical replay specifically validates:
- Rolling 20/60-day robust z-scores (median/MAD) for price and volume
- Cross-sectional z-scores against same-day peers
- Price + volume **double-confirmation** logic
- Liquidity/thinness flags and corporate-action guards
