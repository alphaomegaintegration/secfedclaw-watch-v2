# Running the System

## Prerequisites

- Python 3.10+
- stdlib only (no pip dependencies)
- `.env` file with API credentials (optional — system runs in replay mode without them)

## Environment Variables

| Variable | Required | Purpose |
|---|---|---|
| `POLYGON_API_KEY` | For live market data | Polygon.io API key |
| `MASSIVE_FLATFILES_ACCESS_KEY_ID` | For historical flat files | S3 access key for Polygon flat files |
| `MASSIVE_FLATFILES_SECRET_ACCESS_KEY` | For historical flat files | S3 secret key for Polygon flat files |
| `SEC_USER_AGENT` | For live SEC data | `"Company Name email@example.com"` |
| `X_BEARER_TOKEN` | For live X data | X/Twitter API v2 bearer token |
| `REDDIT_CLIENT_ID` | For live Reddit data | Reddit app client ID (reddit.com/prefs/apps) |
| `REDDIT_CLIENT_SECRET` | For live Reddit data | Reddit app client secret |
| `REDDIT_USER_AGENT` | For live Reddit data | Optional; defaults to `secfedclaw-watch/2.0` |
| `FIRECRAWL_API_KEY` | For promotion sources | Firecrawl API key |

## CLI Reference

### Full Pipeline (one command)
```bash
python3 pipeline.py    # scan → backtest → dashboard
```

### Multi-Ticker Scan
```bash
python3 scan.py --tickers AAPL TSLA AMC GME    # score specific tickers
python3 scan.py --discover 15                   # + top 15 cross-sectional movers
python3 scan.py --no-live                       # force replay from custody artifacts
```

### EDGAR Daily-Diff Pipeline
```bash
python3 edgar_pipeline.py --tickers AAPL TSLA AMC GME    # incremental filing ingestion
python3 edgar_pipeline.py --max-days 5                   # advance up to 5 business days
```

### Historical Flat-File Replay
```bash
python3 historical.py --case AABB:2021-09-13:pump --case MSFT:2021-09-13:control
python3 historical.py --cases-file cases.json --lookback 70
python3 historical.py --no-live                          # force offline replay
```

### Backtest / Calibration
```bash
python3 backtest.py --n 50    # precision/recall calibration (50 windows per class)
```

### Dashboard
```bash
python3 dashboard_v2.py    # render out/dashboard_v2.html
```

### Tests
```bash
python3 -m pytest tests/ -v              # all 35 tests
python3 -m pytest tests/test_v2.py -v    # core scoring (14 tests)
python3 -m pytest tests/test_edgar.py -v # EDGAR pipeline (6 tests)
python3 -m pytest tests/test_flatfiles.py -v  # flat files (5 tests)
python3 -m pytest tests/test_social.py -v     # multi-platform social (5 tests)
python3 -m pytest tests/test_security_class.py -v  # security-class thresholds (5 tests)
```

## Operational Modes

### Live Mode (default)
Requires `.env` credentials and network access. Makes real API calls, caches results for future replay, and preserves full provenance (SHA-256 hashes, source URLs).

### Replay Mode
Reads from cached custody artifacts under `out/`, `flatfiles/day_aggs/`, and `state/`. No credentials or network needed. Produces identical scores from the same cached data.

### Offline / Degraded
When a data source is unavailable (no cache, no credentials), it contributes zero to scores. The system never fabricates data — unavailable sources are explicitly marked and excluded from corroboration.

## Cron Setup

```bash
# EDGAR daily-diff: weekdays at 9am
0 9 * * 1-5  cd /path/to/secfedclaw_v2 && python3 edgar_pipeline.py

# Full pipeline: weekdays at 10am (after EDGAR)
0 10 * * 1-5  cd /path/to/secfedclaw_v2 && python3 pipeline.py
```

## Output Files

| Path | Description |
|---|---|
| `out/review_queue.json` | Ranked review queue (all tickers) |
| `out/<TICKER>_..._watch_v2.json` | Per-ticker review package with full provenance |
| `out/dashboard_v2.html` | Self-contained offline dashboard |
| `out/historical_results.json` | Flat-file backtest results |
| `out/edgar/issuer_features_<TICKER>.json` | Per-ticker EDGAR issuer-event features |
| `state/edgar_state.json` | EDGAR pipeline watermark (last date, seen accessions) |
| `flatfiles/day_aggs/<DATE>.csv.gz` | Cached historical day-aggregate flat files |
