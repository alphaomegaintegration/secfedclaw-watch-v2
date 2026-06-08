# TODOS — SECFEDCLAW v0.2

Priority scale: **P0** = blocking correctness / security · **P1** = high-value next step · **P2** = meaningful improvement · **P3** = nice-to-have / future

---

## Data Sources

### P0 — Security / Correctness

- **Rotate compromised API keys.** `hermes/.hermes_history` contains plaintext credentials (an Anthropic key + one other) that were pasted into the shell. Rotate both immediately and scrub the file. (README §1, flagged red)

### P1

- **Instagram / Facebook produce only Firecrawl markdown** — the parsing blocks are wired (commit a64eb4f) and skip gracefully since neither connector returns structured post objects today. When a structured API path is added, the `"posts"` key pattern will activate automatically. No further action until then.

- **Reddit OAuth credentials.** `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` still needed to make the Reddit connector live outside the operator's home network. The IP-based public path is 403-blocked on most CI/cloud hosts. (README §16 item 2)

### P3 — Hardening

---

## Dashboard

### P2

- **options_flow bar color**: options_flow_score currently reuses the green `.bar-fill` gradient in the component score table. A distinct amber/blue gradient would better convey "this is an options signal, not a direct threat indicator".

---

## Testing

### P1

- **Scheduled CI workflow for `@pytest.mark.live` and `@pytest.mark.slow` tests** — markers added (commits b4afce8, afd2c59), but no separate scheduled GitHub Actions workflow yet. Create `.github/workflows/test-live.yml` that runs weekly with secrets, includes `test_golive.py`, `test_live_flow.py`, and the slow test.

### P2

- **`test_flatfiles.py` signing test** validates the AWS SigV4 `Authorization` header is present, but doesn't verify it's correct against a known fixture. Extend with a fixed-credential deterministic signing check.

- **Per-class backtest fixture**: the per-class breakdown table (README §15) isn't covered by a fast offline test — the backtest runs only in the slow pipeline. Add a deterministic unit test that instantiates the backtest runner on a tiny labeled fixture and checks the per-class precision/recall structure.

---

## Infrastructure

### P1

- **`deploy/` launchd/cron scripts** reference hardcoded paths from the original environment. Document the one-time path substitution step more prominently, or templatize them with a `setup_deploy.sh` that substitutes `$(pwd)` at install time.

### P2

- **`.env` not in `.gitignore`** — verified covered: `.env`, `.env.*`, `state/`, `flatfiles/`, `live_cache/` all present. No action needed.

### P3

- **`serve.py` has no auth layer.** README §14 notes it binds to `127.0.0.1` by default. Consider adding a shared-secret query-param or session token when `--host 0.0.0.0` is used, to prevent accidental exposure of WATCH packages on multi-user or cloud hosts.

- **`notify.py` Telegram fallback writes plaintext digest to `out/`** where it is readable by any process with access to the `out/` directory. Consider encrypting or restricting permissions on the fallback file.

---

## Completed

Recent work that is done and shipped:

- **USWDS/design-system refactor**: consistent color/space/type tokens, accessible contrast, clear section intros throughout the dashboard.
- **Sidebar navigation**: persistent sidebar nav added to the dashboard for quick tab access.
- **"How it works" interactive workflow tab (tab 11)**: added Scout→Analyst→Adversary→Explainer→Packager visual workflow. (commit 793cfa3)
- **Coordination network graph (tab 10)**: D3-based network visualization with colored edges and drag interaction; index-based edge lookup fixed. (commits 49a5ff2, 8a68c9b)
- **FMP (Financial Modeling Prep) connector**: `fmp_quote`, `fmp_profile`, `fmp_historical` — complements Polygon for quotes, profiles, and historical prices. (commit d7dde34)
- **Discord connector with Disboard+Firecrawl fallback**: all 7 planned social sources now have live connector implementations. (commit 4a8de35)
- **Discord messages wired into scoring pipeline**: `normalize_posts()` now accepts `discord_fetch_data`; bot-API messages feed social scores, coordination graph, and family-diversity gate. (commit 776ea1d)
- **Sidebar collapsed-state icons**: each tab shows a letter label (Q/P/N/?/A/L/S/$/M/⚖/B) in the 48px collapsed strip. (commit 13fc2d5)
- **serve.py token auth**: `--token` flag + auto-generated token when binding beyond localhost. (commit 0ed0669)
- **pytest markers**: `slow` + `live` registered in pytest.ini; test_daily subprocess skipped in standard CI. (commits b4afce8, afd2c59)
- **Flatfiles SigV4 deterministic test** + **backtest unit test** + **network graph regression tests** (13 cases). (commits 925fec5, 6eaef7b, 93daf80)
- **Corporate-actions / splits**: `polygon_splits()` connector + `needs_adjustment_review` cap in scoring. (commit 35f91fa)
- **Options flow**: `polygon_options_snapshot()` + `_options_flow_score()` at 8% weight in anomaly evidence. (commit 35f91fa)
- **OTC promo disclosures**: `otc_promotion_disclosure()` + +20 on issuer_event_score when disclosure found. (commit 35f91fa)
- **Instagram and Facebook wired into scoring pipeline**: parsing blocks added; skip gracefully since both return Firecrawl markdown today. (commit a64eb4f)
- **Discord normalize_posts unit tests**: bot-API format and Firecrawl blob both covered. (commit 68e2666)
- **Infrastructure fixes**: `out/` and `state/` mkdir guards in `daily.py` and `edgar_pipeline.py`. (commits a145229, d10a491)
- **requirements-dev.txt** added with `pytest>=7`. (commit 506fb1a)
- **FMP_API_KEY** documented in README and preflight.py. (commit 678eb0c)
- **Exception logging**: silent `pass` replaced with `warnings.warn` in connectors.py. (commit 9b12610)
- **dashboard_v2.py --help** improved with full description and flag docs. (commit e20038c)
- **README tab count** updated to 11. (commit 6da881d)
- **GBrain local-PGLite brain**: set up and synced for semantic code search across this repo. (CLAUDE.md)
- **Multi-platform social (X, Reddit OAuth, StockTwits)**: all normalized into one post schema with cross-platform dedup and coordination graph.
- **Per-security-class calibration**: `thin_microcap / small_cap / mid_cap / large_cap` thresholds — large caps no longer float at MEDIUM with no real anomaly.
- **Gradient-boosted review-priority model** (`model.py`): 5-fold CV AUC 0.982, 64 real labels from 8 SEC/DOJ enforcement cases, zero false positives on controls.
- **EDGAR daily-diff pipeline** (`edgar_pipeline.py`): incremental state-watermark ingestion, issuer_event as a corroborating family.
- **Polygon Flat Files / SigV4 historical replay** (`flatfiles.py`, `historical.py`): real multi-year day-aggs for backtest.
- **Backtest harness** (`backtest.py`): precision 0.714 / recall 1.000 / F1 0.833 on 150 synthetic windows.
- **Full 5-agent pipeline**: Scout → Analyst → Adversary → Explainer → Packager with WATCH caps and custody-preserving SHA256 artifacts.
- **`daily.py` + `notify.py` + `serve.py`**: scheduled daily run, Telegram digest, localhost dashboard server.
