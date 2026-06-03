# Deployment and Monitoring

## Deployment Overview

SECFEDCLAW v0.2 runs as a scheduled local process — no cloud infrastructure required. The daily pipeline executes after market close, scores the universe, and delivers a digest.

```
16:35 local (weekdays)
    │
    ▼
┌────────────────────────────────────────────────────┐
│  daily.py (lock-protected, logged)                 │
│  1. preflight.py  → GO_LIVE / DEGRADED / REPLAY   │
│  2. edgar_pipeline.py  → incremental SEC filings   │
│  3. scan.py  → live multi-ticker scan + discovery  │
│  4. backtest.py  → precision/recall calibration    │
│  5. dashboard_v2.py  → offline HTML dashboard      │
│  6. notify.py  → Telegram digest (or file fallback)│
└────────────────────────────────────────────────────┘
    │
    ▼
out/daily_run_summary.json + logs/daily_<UTC>.log
```

## Preflight (`preflight.py`)

Per-source live-readiness check before each run. Probes:

| Source | Method | Key |
|---|---|---|
| Polygon | API probe (market status) | `POLYGON_API_KEY` |
| Flat Files | Key presence | `MASSIVE_FLATFILES_*` |
| SEC EDGAR | HTTP probe | `SEC_USER_AGENT` |
| X / Twitter | Key presence | `X_BEARER_TOKEN` |
| Reddit | Key presence | `REDDIT_CLIENT_ID` + `SECRET` |
| StockTwits | Public (always live) | None |
| FINRA / Nasdaq | Replay-only | None |

Verdicts:
- **GO_LIVE** — key sources (Polygon + SEC) reachable, ≥4 sources live
- **DEGRADED** — some sources live, partial coverage
- **REPLAY_ONLY** — no live sources; cached artifacts only

```bash
python3 preflight.py    # print verdict + per-source status JSON
```

## Scheduled Daily Run (`daily.py`)

Lock-protected, idempotent, once-per-day pipeline. Runs all 6 steps sequentially with logging.

### Install (macOS launchd)
```bash
./deploy/schedule_install.sh install     # weekdays 16:35 local
./deploy/schedule_install.sh status      # check if loaded
./deploy/schedule_install.sh uninstall   # remove
```

### Install (Linux cron)
```bash
# Edit paths in deploy/secfedclaw.cron, then:
crontab deploy/secfedclaw.cron
```

### Manual run
```bash
python3 daily.py                             # live if reachable
python3 daily.py --no-live --tickers AAPL    # replay mode, single ticker
```

### Lock behavior
- Lockfile at `out/.daily.lock` prevents overlapping runs
- Stale locks (>6 hours) are automatically cleared
- Set `SECFEDCLAW_DAILY_NOLOCK=1` to bypass (for testing)

## Daily Digest (`notify.py`)

After each daily run, a concise digest of flagged (≥MEDIUM) tickers is delivered.

### Delivery channels
1. **Telegram** (primary) — requires `TELEGRAM_BOT_TOKEN` + `TELEGRAM_HOME_CHANNEL` in `.env`
2. **File fallback** — writes to `out/digest_<UTC>.txt` when Telegram is unreachable

### Dashboard deep-link
Set `SECFEDCLAW_DASHBOARD_URL` to include a clickable link in the digest:
```bash
export SECFEDCLAW_DASHBOARD_URL=http://127.0.0.1:8787/dashboard_v2.html
```
Falls back to the local `file://` path if unset.

### Standalone
```bash
python3 notify.py --print    # preview digest text
python3 notify.py            # deliver via Telegram or file
```

## Dashboard Server (`serve.py`)

Lightweight localhost-bound static server for the dashboard.

```bash
python3 serve.py                 # http://127.0.0.1:8787/
python3 serve.py --port 9000     # custom port
```

- `/` redirects to `/dashboard_v2.html`
- Binds to **127.0.0.1 only** by default (WATCH content privacy)
- `--host 0.0.0.0` is allowed but prints a security warning

## Monitoring

### Health check commands
```bash
# Preflight verdict
python3 preflight.py

# Launchd job status
./deploy/schedule_install.sh status

# Latest daily run summary
cat out/daily_run_summary.json | python3 -m json.tool

# Launchd error log (should be empty)
cat logs/launchd.err.log

# Latest daily log
ls -t logs/daily_*.log | head -1 | xargs cat

# Full test suite
python3 -m pytest tests/ -q
```

### Key indicators

| Indicator | Healthy | Investigate |
|---|---|---|
| `daily_run_summary.ok` | `true` | `false` — check `errors` array |
| `preflight_verdict` | `GO_LIVE` | `DEGRADED` (partial) or `REPLAY_ONLY` (no live) |
| `launchd.err.log` | Empty | Any content — check python path or permissions |
| `flagged_ge_medium` | 0–15 | >15 may indicate noisy thresholds or data issue |
| Test suite | All pass | Failures — check recent code changes |

### Daily run summary fields

| Field | Description |
|---|---|
| `started_utc` / `finished_utc` | Run timestamps |
| `ok` | `true` if all steps exited 0 and no errors |
| `preflight_verdict` | GO_LIVE / DEGRADED / REPLAY_ONLY / ERROR |
| `steps` | Exit codes: edgar, scan, backtest, dashboard |
| `data_mode` | live / replay |
| `priority_distribution` | Count per priority level |
| `flagged_ge_medium` | Total MEDIUM + HIGH + CRITICAL |
| `digest` | Delivery result (sent, fallback_file) |
| `errors` | Array of error messages (empty = healthy) |
| `log` | Path to the detailed log file |

### Log locations

| Path | Content |
|---|---|
| `logs/daily_<UTC>.log` | Full daily run log (per-step output) |
| `logs/launchd.out.log` | Launchd stdout (daily.py console output) |
| `logs/launchd.err.log` | Launchd stderr (should be empty) |
| `out/daily_run_summary.json` | Machine-readable run summary |
| `out/digest_<UTC>.txt` | Digest file fallback (when Telegram unavailable) |

### Troubleshooting

**Daily run shows `ok: false`:**
Check `errors` array and individual `steps` exit codes. Common causes: network timeout (scan step), stale EDGAR state, missing `.env` keys.

**Preflight returns `REPLAY_ONLY` unexpectedly:**
Check `.env` file exists and has valid `POLYGON_API_KEY` + `SEC_USER_AGENT`. Network connectivity required.

**Launchd error log has content:**
Reinstall with `./deploy/schedule_install.sh install` — the installer resolves the real python binary (not pyenv shim) and sets PATH explicitly.

**Lockfile prevents run:**
If a previous run crashed, the lock may be stale. It auto-clears after 6 hours, or manually: `rm out/.daily.lock`
