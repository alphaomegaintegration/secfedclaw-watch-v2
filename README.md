# SECFEDCLAW v0.2 — agentic WATCH-level pump-and-dump review scorer

Finding ceiling: **WATCH** · Mode: review-priority only · Python 3.10+, stdlib-only

A connection-aware, multi-ticker securities-surveillance prototype that fuses
social, market, official (SEC/FINRA/Nasdaq) and microstructure signals into
**non-accusatory review-priority packages** for authorized human review. Runs
**live** off a `.env` of API keys when network is available, and **replays** from
local custody artifacts otherwise — preserving provenance either way.

> ⚠️ **Operating boundary (see `SECURITY.md`):** WATCH-only. No trading signals,
> no market actions, no accusations, no external contact, no asset freezes, no
> legal process. HIGH/CRITICAL means "urgent human review," nothing more.

It implements the highest-leverage items from the SECFEDCLAW
continuous-improvement backlog (robust baselines, real coordination graph,
microstructure scoring, temporal corroboration, multi-ticker scan, backtest,
dashboard).

---

## 1. Review findings (what prompted this)

The system is mature and well-designed. The recurring gaps your own continuous
agents flagged — and that this prototype addresses:

| # | Gap (v0.1) | Evidence | Fixed in v0.2 |
|---|---|---|---|
| 1 | Market anomaly used **absolute** return/volume, no baselines | AAPL = MEDIUM in 9/9 runs with no real anomaly | Rolling 20/60d **robust z (median/MAD)** + **cross-sectional** z; price+volume **double-confirmation** |
| 2 | `coordination_score` hard-coded **0.0** | algorithms review §5.7, (i) OPEN | Real graph: near-dup clustering, shared domains, burst sync, author HHI |
| 3 | Microstructure collected but **unused** | algorithms review §8.3 | Trade-burst, large-trade share, spread (bps), VWAP shift |
| 4 | Social X-only, dupes inflate, promo **adds** to burst | algorithms review §5.3–5.5 | Dedup by (platform,id); promo **deflates**; issuer-specific vs noise split |
| 5 | No **temporal/cross-source corroboration** requirement | algorithms review §8.4 | Corroboration multiplier; HIGH/CRITICAL needs ≥2 families |
| 6 | Evidence quality **additive** → reviewability inflates concern | algorithms review §5.1 (f) | Anomaly-evidence anchor **separated** from evidence quality; routine-context floor cap |
| 7 | **Single ticker** (AAPL), hard-coded `/home/ubuntu` paths | README, code | Multi-ticker scan + discovery; path-portable root |
| 8 | Only **8/141** timelines scored | business review §4 Gap A | Scan scores the whole universe in one run |

**Also found (operational, outside this prototype):**
- 🔴 **Rotate keys:** `hermes/.hermes_history` contains pasted plaintext API keys
  (an Anthropic key + one other). Rotate them and scrub the file.
- 🟡 README credential status is stale — SEC EDGAR now works (`SEC_USER_AGENT` is set).

## 2. Data sources — live status

**19 data sources** (13 live, 6 need credentials or opt-in). All SEC EDGAR APIs
are completely keyless per [sec.gov EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces).

**Market & official (all live):**

| Source | Auth | Notes |
|---|---|---|
| Polygon aggregates/grouped/snapshot/prev | `POLYGON_API_KEY` | OHLCV, cross-section |
| Polygon Flat Files (S3 history) | `MASSIVE_FLATFILES_*` | Multi-year day-aggs for backtest |
| SEC EDGAR submissions | None (User-Agent only) | Dynamic CIK for any ticker |
| SEC EDGAR daily-index | None (User-Agent only) | Daily-diff pipeline (issuer_event) |
| SEC litigation/admin feeds | None (User-Agent only) | Enforcement history |
| FINRA OTC threshold | None (public JSON) | `api.finra.org` |
| Nasdaq trade halts | None (public RSS) | `nasdaqtrader.com` |
| Nasdaq Reg SHO threshold | None (public) | `nasdaqtrader.com` |

**Social (8 platforms):**

| Platform | Auth | Status | SEC case reference |
|---|---|---|---|
| X (Twitter) | `X_BEARER_TOKEN` | ✅ live | Atlas Trading, Citron Research |
| StockTwits | None (public) | ✅ live | OST, general pump chatter |
| Reddit | None / `REDDIT_CLIENT_ID` | ✅ live (IP-dependent) | Atlas Trading (r/wallstreetbets) |
| Social web search | `FIRECRAWL_API_KEY` | ✅ live | Cross-platform promotion via Google |
| Discord | `DISCORD_BOT_TOKEN` + `DISCORD_GUILD_IDS` | ⚠ needs bot | Atlas Trading ($114M Discord chatroom) |
| Instagram | `FIRECRAWL_API_KEY` | ⚠ needs login session | OST/CLEU deepfake AI video ads |
| Facebook | `FIRECRAWL_API_KEY` | ⚠ needs login session | CLEU/OST ad targeting → WhatsApp |
| Telegram / WhatsApp | Authorized import + opt-in | 🔒 off by default | CLEU/OST WhatsApp groups (§12) |

**Setup for new social connectors:**

```bash
# Discord: create a bot at discord.com/developers/applications, enable Message Content Intent
DISCORD_BOT_TOKEN=your_bot_token
DISCORD_GUILD_IDS=guild_id_1,guild_id_2    # comma-separated server IDs to monitor

# Instagram/Facebook: Firecrawl handles rendering (key already in .env)
FIRECRAWL_API_KEY=your_key                 # also powers social_web_search

# Telegram/WhatsApp: operator places lawful exports in out/social_import/
SECFEDCLAW_AUTHORIZED_SOCIAL=1             # opt-in gate

# Cross-platform coordinated-push intel (deterministic, no LLM). Off by default.
# Adds a CAPPED boost to coordination_score only when a near-duplicate push spans
# >=2 platforms by >=3 distinct accounts AND aligns with a confirmed market move.
# Quarantined: never lights an independent family, so social-only can't reach HIGH.
SECFEDCLAW_SOCIAL_INTEL=1                  # opt-in gate
```

**Remaining additions (by leverage):**

1. **Options flow / OPRA** (Polygon entitlement) — unusual options pre-pump.
2. **Corporate-actions / split & ticker-change feed** — kills the largest class
   of false anomalies (the `needs_adjustment_review` flag is stubbed for this).

## 3. Algorithm upgrades (implemented here)

- **`robust_stats.py`** — median/MAD, robust & cross-sectional z, EWMA,
  winsorize, Gini/HHI, saturating `squash`.
- **`features/market.py`** — time-series + cross-sectional anomaly, price+volume
  double-confirmation, microstructure, liquidity/thinness + corporate-action flags.
- **`features/coordination.py`** — k-shingle Jaccard near-duplicate clustering,
  shared-domain graph, burst synchronization, author HHI.
- **`features/social.py`** — normalize/dedup, issuer-specific vs promo-noise split.
- **`features/official.py`** — generalized (any ticker) FTD/threshold/halt/issuer.
- **`features/temporal.py`** — cross-source corroboration multiplier.
- **`scoring_v2.py`** — corroboration-gated composite anchored on concern-bearing
  anomaly evidence, separated from reviewability, with all WATCH caps + actuating
  benign-explanation band reduction.

## 4. Agentic architecture

Five role-bounded agents (`agents.py`), mirroring SOUL.md detect→analyze→review→explain→package:

```
ScoutAgent     → gathers source data (live via .env, else replay), reports health
AnalystAgent   → runs the v0.2 scoring engine
AdversaryAgent → red-teams: benign tests, coordination-cluster sanity,
                 corroboration enforcement; may ONLY lower priority / add caveats
ExplainerAgent → grounded plain-language review summary (LLM or template)
PackagerAgent  → writes the custody-preserving (sha256) review package
Orchestrator   → runs the loop per ticker; scan.py runs it across the universe
```

## 5. How to run

```bash
cd secfedclaw-watch-v2
python3 tests/test_v2.py                      # 14 tests, all pass
python3 pipeline.py                            # scan -> backtest -> dashboard (one command)

# or individually:
python3 scan.py --tickers AAPL TSLA AMC GME   # score a universe
python3 scan.py --discover 15                 # + top 15 cross-sectional movers
python3 scan.py --no-live                      # force replay from custody artifacts
python3 backtest.py --n 50                     # precision/recall calibration harness
python3 dashboard_v2.py                        # render out/dashboard_v2.html (offline)

# go live (on a machine with network + the .env credentials):
python3 preflight.py                           # per-source live readiness (GO/DEGRADED)
python3 scan.py --live --tickers AAPL AMC GME  # preflight, then scan live
python3 label.py out/AMC_..._watch_v2.json useful_watch   # feed the calibration ledger
```

On your laptop (open network) it runs **live** off the `.env` keys; in a
locked-down sandbox it runs **replay** off the cached custody artifacts. Output:
ranked `out/review_queue.json` + per-ticker `out/<TICKER>_..._watch_v2.json`.

### Validation observed (replay over cached artifacts)
- Large caps (AAPL/TSLA/GME/AMD) → **LOW** (fixes v0.1's MEDIUM floor — no real anomaly).
- Discovery surfaced genuine microcap movers (FFIE, ASST, TOVX, CURR…); **CURR**
  had a −24% move (cross-sectional return-z **15.7**) but stayed **LOW** because
  volume wasn't confirmed, it's thin, and no other family corroborated — correct
  WATCH discipline (price-only moves are not pump candidates).

## 6. Backtest / calibration (implemented — `backtest.py`)

Measures whether v0.2 would **raise review priority** on pump windows while
staying quiet on benign-news and routine windows. Target is review-priority
calibration, never a fraud label. Corpora:

- **Real SEC case corpus** — public cases (2021-214, 2022-221, 2014-256,
  2022-62) as metadata + URLs; supply tickers/windows for a live Polygon run.
- **Synthetic labeled corpus** — seeded, randomized pump / benign-news / control
  windows, runnable offline, with varied signal intensity so weak pumps can be
  missed and noisy benign windows can be flagged (non-trivial metrics).

Observed (150 windows, 50/class, flag ≥ MEDIUM, seed 20260602):

| precision | recall | F1 | accuracy | TP | FP | TN | FN |
|---:|---:|---:|---:|---:|---:|---:|---:|
| **0.714** | **1.000** | **0.833** | **0.867** | 50 | 20 | 80 | 0 |

Zero missed pumps; the false positives are benign-news windows carrying
coordinated chatter — the correct class to surface for human review. A key
calibration finding fed straight back into the engine: benign *discussion
volume* must NOT count as a corroborating family — only coordination/promotion
should — which lifted precision from 0.65 to 0.71 with no recall loss.

## 7. Dashboard (implemented — `dashboard_v2.py`)

Self-contained offline HTML (inline CSS/JS, **no auto-loaded external resources
or callbacks**) → `out/dashboard_v2.html`, built on a small consistent design
system (color/space/type tokens, accessible contrast). Eleven tabs (Overview,
Packages, Network, How it works, Agents, Learning, Status, LLM cost,
Methodology, SEC case studies, Backtest):

- **Overview** — operator KPI cards (universe, **score-ready %**, flagged
  ≥MEDIUM, CRITICAL/HIGH, mean anomaly-evidence, mode) + the ranked, filterable
  review queue. Every metric has an **ⓘ tooltip**, and each ticker carries
  **reference links** (SEC EDGAR, EDGAR full-text, market, StockTwits) that open
  externally on click.
- **Packages** — evidence cards with component bars, families, caps,
  coordination clusters, the model advisory, and a non-accusatory rationale.
- **Network** — interactive coordination network graph: nodes are tickers, edges
  are weighted by coordination score; colored by priority band, draggable layout.
- **How it works** — interactive workflow diagram of the full pipeline
  (Scout→Analyst→Adversary→Explainer→Packager), clickable to expand each stage.
- **Agents** — the five-agent **orchestration** (Scout→Analyst→Adversary→
  Explainer→Packager): the data feeds each pulls, the data-engineering +
  algorithms it applies, and its output, plus the live/replay data-feed table.
- **Learning** — the autonomous feedback cycle (Scan→Review→Learn→Advise),
  model KPIs (labels, AUC, training data), feature-importance bars, operator
  label breakdown, and design constraints (abstention, anti-leakage, rules-primary).
- **Status** — operational view *from an agent perspective*: each agent's live
  state, the integrations it depends on, and per-connection live/replay/ok
  health, plus system KPIs (preflight verdict, model, LLM spend, last run).
- **LLM cost** — usage & cost ledger (total cost, by model, by component); empty
  until an LLM-backed component records spend via `usage.record(...)`.
- **Methodology** — review-priority bands + a full **data dictionary** of every
  metric, and an explicit "what it does NOT do".
- **SEC case studies** — public SEC matters mapped to *which thresholds fire and
  why* (for reviewers and for building labeled training windows), plus a worked
  threshold-hit example.
- **Backtest** — precision/recall, confusion matrix, calibration ledger.

Run `python3 pipeline.py` (or `dashboard_v2.py`) to refresh.

## 8. EDGAR daily-diff pipeline (implemented — `edgar_pipeline.py`)

Incremental SEC ingestion ("just the diffs"). It keeps a **state watermark**
(`state/edgar_state.json`) of the last processed date + seen accession numbers,
so each run only processes new filings — cron-friendly and recursive/adaptive.

Flow: resolve ticker→CIK from `company_tickers.json` → for each new business day
fetch the SEC **daily-index** master file → parse pump-relevant filings
(insider 3/4/5/144, dilution S-1/S-3/424B/EFFECT/S-8, material 8-K, late NT,
delisting 25/15-12B) → diff against seen accessions → recompute per-ticker
issuer features → write `out/edgar/issuer_features_<TICKER>.json`.

The scorer consumes these as a **concern-bearing `issuer_event`** signal (not
mere reviewability): insiders/issuers selling or diluting into promoted demand
is a classic pump tell, so `issuer_event` is a corroborating family and feeds
`anomaly_evidence`. `features/edgar.py` holds the pure, tested logic.

```bash
python3 edgar_pipeline.py --tickers AAPL TSLA AMC GME   # daily incremental run
python3 edgar_pipeline.py --max-days 5                  # advance up to 5 business days
# cron (daily): 0 9 * * 1-5  cd .../secfedclaw_v2 && python3 edgar_pipeline.py
```

Live on a networked machine (uses `SEC_USER_AGENT`); offline it parses any
cached daily-index and otherwise no-ops while preserving state.

## 9. Polygon Flat Files historical replay (implemented — `flatfiles.py`, `historical.py`)

S3-compatible access to historical daily-aggregate flat files via stdlib AWS
SigV4 (no boto3) using the `MASSIVE_FLATFILES_*` credentials, so the backtest
can run on **real multi-year per-ticker history** for SEC-case windows instead
of synthetic data. Raw downloads are cached + hashed under `flatfiles/day_aggs/`.

`flatfiles.py` lists/gets day-aggregate files and assembles real `daily_range`
(per-ticker bars) + `grouped` (event-day cross-section) inputs for the scorer.
`historical.py` replays labeled case/control windows through the v0.2 market
engine and reports pump-vs-control separation.

```bash
python3 historical.py --case PUMPX:2021-09-13:pump --case MSFT:2021-09-13:control
python3 historical.py --cases-file cases.json --lookback 70
```

Flat files are market-only, so this validates the **MARKET-anomaly component**
(rolling 20/60d + cross-sectional, price+volume double-confirmation) on real
windows; full corroboration still uses the live scan. Validated on real-shaped
data: a +75% / 28×-volume pump day scored market-anomaly ~99 (double-confirmed)
vs a benign control ~44 — ~55-pt separation. Live needs `MASSIVE_FLATFILES_*` +
network; offline replays cached day-aggs.

## 10. Multi-platform social signals (implemented — `connectors.py`, `features/social.py`)

Social coverage is now **three platforms**, all normalized into one post schema
so the coordination graph + social split + dedup work cross-platform:

- **X** recent search (cashtag) — existing.
- **Reddit OAuth** — authenticated app-only (`client_credentials`) search across
  finance subreddits (pennystocks, wallstreetbets, Shortsqueeze, …). Replaces the
  403-blocked public-JSON path; needs `REDDIT_CLIENT_ID`/`REDDIT_CLIENT_SECRET`/
  `REDDIT_USER_AGENT`.
- **StockTwits** — symbol stream with native **Bullish/Bearish sentiment** tags
  (public, rate-limited). Finance-native and cashtag-first.

New signals: per-platform counts, **cross-platform issuer-specific** corroboration,
and **sentiment skew** — *unanimous bullish sentiment + promotional language* is a
recognized hype/coordination tell and nudges the coordination score (capped,
explained). Posts from all platforms feed the same near-duplicate / shared-domain /
burst-sync coordination graph, so coordinated promo spanning platforms surfaces
naturally. Validated: a 3-platform coordinated pump (8-post duplicate cluster,
unanimous bullish) scored coordination 72 and reached MEDIUM.

## 11. Per-security-class calibration (implemented — `features/security_class.py`)

Detection thresholds are now **calibrated per liquidity class** instead of being
one-size-fits-all — the fix for both the "large-cap floats at MEDIUM" noise and
under-sensitivity on the microcaps that pumps actually target. Each ticker is
classified by a price + daily-dollar-volume proxy into
`thin_microcap / small_cap / mid_cap / large_cap`, and the class sets:

| class | z_confirm | routine-context floor | social weight |
|---|---:|---:|---:|
| thin / microcap / OTC-like | 2.5 | 18 | 1.25× |
| small cap | 2.8 | 22 | 1.10× |
| mid cap | 3.0 | 26 | 1.00× |
| large / mega cap | 3.6 | 33 | 0.85× |

So a large cap needs stronger, higher-z double-confirmation and far more
anomaly-evidence to escape LOW, while a thin microcap is more sensitive and
weights social/promo higher. The class + thresholds are emitted in every package
(`security_class`) and shown in the dashboard. Validated: AAPL → `large_cap`
(floor 33), AMC → `small_cap` (floor 22); backtest precision/recall unchanged.

## 12. Authorized Discord/Telegram import (implemented — `social_import.py`)

Discord/Telegram are high-value promotion channels but private; SOUL.md requires
explicit lawful authorization. This adapter therefore performs **no autonomous
scraping** — it ingests only data the operator has lawfully obtained and placed
in `out/social_import/` (official Telegram export JSON, Discord/DiscordChatExporter
JSON, or curated JSONL/CSV), and is **OFF unless opted in** via
`SECFEDCLAW_AUTHORIZED_SOCIAL=1`. Imported messages normalize into the shared
post schema, so they flow through the coordination graph and social features
automatically (platforms `telegram`/`discord`).

## 13. Review-priority model + calibration ledger (implemented — `model.py`, `ledger.py`, `train_model.py`, `label_cases.py`)

A dependency-light (numpy-only, **no sklearn**) **gradient-boosted** classifier
over decision stumps (14 features, logistic loss) that outputs a *calibrated
review-priority probability* and per-feature contributions — an advisory triage
aid that **never** changes the interpretable rules-based priority and is **never**
a guilt/fraud label.

### Training data

**64 real labels** from 8 SEC/DOJ enforcement cases + 6 matched controls, plus
180 bootstrap samples (price/volume randomized independently of label to prevent
class leakage):

| Case | Type | Ticker | Windows | Source |
|---|---|---|---|---|
| CLEU ramp-and-dump | Pump | CLEU | 3 | DOJ N.D. Ill. 1:25-cr-00161 |
| Atlas Trading influencers | Pump | GTTN, SURF, UPC | 3 | SEC 2022-221 |
| SafeMoon crypto | Pump | SFM | 1 | SEC 2023 |
| Wintercap/OneLife | Pump | ONEI | 1 | SEC enforcement 2024 |
| Ostin Technology | Pump | OST | 3 | DOJ E.D. Va. 1:25-cr-00259 |
| Citron Research / Andrew Left | Short-and-distort | ROKU, NVDA, CRON, XL | 4 | DOJ 2:24-cr-456 (convicted Jun 2026) |
| Matched controls | — | MSFT, AAPL, TSLA, GOOG | 6 | — |

`label_cases.py` runs each case through the full 5-agent pipeline (all live
sources) and labels in the ledger. `historical.py --cases-file cases.json`
replays market-only windows via flat files.

### Performance

| Metric | Value |
|---|---|
| 5-fold CV AUC | **0.982** |
| Real-label accuracy | **0.81** (zero false positives) |
| Real labels | **64** (40 manipulation, 24 control) |
| False positives | **0** — no control ever misclassified |

### Learned feature importances

| Feature | Importance | What it captures |
|---|---|---|
| `coordination_score` | **43%** | Near-duplicate clusters, burst sync, shared domains |
| `class_ordinal` | 23% | Liquidity class (microcaps are pump targets) |
| `social_promotional_noise` | 17% | Promotional language volume |
| `market_anomaly_score` | 17% | Price+volume abnormality |

The model correctly identifies coordination as the dominant discriminator.
Notably, `market_anomaly_score` gained 17% importance (was 0%) after adding
the Citron/Left cases — because large-cap tickers (ROKU, NVDA) show measurable
market moves from influential tweets. The Citron case also teaches the model
that manipulation works in **both directions** (short-and-distort, not just
pump-and-dump).

### Components

- `ledger.py` records operator outcome labels (`useful_watch`/`missed_event` →
  positive; `false_positive`/`benign_explained`/`insufficient_evidence` →
  negative) with each package’s 14-element feature vector.
- `train_model.py` trains from real labels + optional bootstrap, reports 5-fold
  AUC, and **abstains** until ≥40 two-class samples exist.
- `label_cases.py` runs known SEC cases through the full multi-source pipeline
  and labels each package with known ground truth.
- When a trained model is present, every package gets a `model_advisory`
  (probability + top features); the rules engine remains primary.

```bash
python3 label_cases.py                   # label SEC cases through full pipeline
python3 train_model.py                   # retrain (real labels + bootstrap)
python3 train_model.py --no-bootstrap    # real labels only
python3 historical.py --cases-file cases.json   # market-only replay
```

## 14. Going live (replay → live)

The engine is **connection-aware**: the same code runs live on a networked
machine with the `.env` credentials and replays cached custody artifacts
otherwise. To switch on live:

1. `python3 preflight.py` — probes every source with the real creds and prints a
   per-source verdict: `GO_LIVE` (core market source reachable), `DEGRADED`
   (only non-core live), or `REPLAY_ONLY`. No secrets printed; read-only probes.
2. `python3 scan.py --live …` (or `python3 pipeline.py`) — runs preflight, then
   scans with `prefer_live=True`. Sources that aren't reachable degrade to
   cached replay individually, and the per-ticker `source_health` shows which.
3. **Live custody:** every successful live response is persisted (raw + SHA256)
   under `live_cache/<UTC>/`, so a live package is as reproducible/auditable as a
   replayed one (SOUL evidence discipline). `flatfiles/day_aggs/` caches history.
4. **Feedback loop:** label reviewed packages with `python3 label.py … <label>`
   and `python3 train_model.py` to recalibrate as real labels accrue.

Credentials used live: `POLYGON_API_KEY`, `X_BEARER_TOKEN`/`TWITTER_BEARER_TOKEN`,
`SEC_USER_AGENT`, `MASSIVE_FLATFILES_*`, and (optional) `REDDIT_CLIENT_ID`/
`REDDIT_CLIENT_SECRET`, `FMP_API_KEY` (Financial Modeling Prep — quotes, profiles,
historical prices; free tier at https://financialmodelingprep.com/developer/docs),
and `FIRECRAWL_API_KEY` (social web search + Instagram/Facebook/Discord fallback).
StockTwits/FINRA/Nasdaq need none.

### Schedule a daily live run (`daily.py`, `deploy/`)

`daily.py` is a lock-protected, logged once-per-day pass: preflight → EDGAR
daily-diff → live scan (+discovery) → backtest → dashboard. It writes
`out/daily_run_summary.json` and `logs/daily_<UTC>.log`, and a lockfile prevents
overlapping runs.

```bash
python3 daily.py                       # run once now (live if reachable)
# macOS (launchd, weekdays 16:35 local, after close):
./deploy/schedule_install.sh install   # status / uninstall also supported
# Linux: edit paths in deploy/secfedclaw.cron, then: crontab deploy/secfedclaw.cron
```

This is independent of the legacy 30-minute hermes collector cron — it does not
modify or replace it.

### Daily digest (`notify.py`)

After each daily run, a concise WATCH digest of the flagged (≥MEDIUM) tickers is
delivered via Telegram (`TELEGRAM_BOT_TOKEN` + `TELEGRAM_HOME_CHANNEL`); if
Telegram is unreachable/unconfigured it falls back to `out/digest_<UTC>.txt`.
Run standalone with `python3 notify.py` (or `--print` to preview). Digest is
review-priority context for the authorized user only — no trading signals. The
digest deep-links to the dashboard (see below).

### View / publish the dashboard (`serve.py`)

The dashboard is a single self-contained HTML file. To view it at a stable URL
(and have the digest link to it), run a lightweight local server:

```bash
python3 serve.py                 # http://127.0.0.1:8787/  (localhost only)
export SECFEDCLAW_DASHBOARD_URL=http://127.0.0.1:8787/dashboard_v2.html   # digest deep-link
```

**Privacy:** `serve.py` binds to **127.0.0.1 by default** — the dashboard carries
enforcement-adjacent WATCH content and must not be exposed on a network or the
public internet without a deliberate, authorized decision. `--host 0.0.0.0` is
possible but prints a warning. Publishing to a public host (e.g. GitHub Pages)
is **not recommended** and is left entirely to the operator. If no URL is set,
the digest links to the local `file://` path instead.

## 15. Enforcement history, per-class calibration, agent status & LLM cost

- **Enforcement-history family** (`features/enforcement.py`) — parses the SEC
  litigation-releases feed and flags when the ticker/issuer appears in recent
  actions. **Backward-looking context** (family E): it raises review attention
  and is a corroborating family, but never implies current misconduct; matched
  releases are emitted for verification.
- **Per-class backtest** (`backtest.py per_class_breakdown`) — precision/recall
  by liquidity class on a class-balanced corpus. Observed: small-cap P≈1.0,
  thin/microcap P≈0.3 at recall 1.0 — microcaps are tuned for high recall (don't
  miss pumps) at the cost of precision (more benign windows surface). Shown on
  the Backtest tab.
- **Agent status** (`agent_status.py` + Status tab) — per-agent live state, the
  integrations each depends on, and per-connection live/replay/ok health.
- **LLM usage & cost** (`usage.py` + LLM-cost tab) — a dependency-free ledger any
  LLM-using component records to (`usage.record(model, in_tok, out_tok, component)`),
  with a configurable pricing table and cost aggregation by model/component/day.
- **LLM explanation agent** (`explainer.py`, the 5th agent) — writes a 3–5
  sentence plain-language review summary grounded ONLY in the package evidence.
  Off by default (deterministic template); set `SECFEDCLAW_LLM_EXPLAIN=1` to use
  an LLM (OpenRouter or Anthropic from `.env`). A guardrail rejects any output
  with fraud/accusation/trading language (falls back to the template), every
  summary ends with the WATCH disclaimer, and each LLM call is cost-tracked via
  `usage.py` (so the LLM-cost tab populates). Shown as "Review summary" on each
  package card.
- **Live data through the agents** — live is the default (`scan.py --live`);
  `tests/test_live_flow.py` injects a mock live transport and proves data flows
  Scout→Analyst→Adversary→Packager with custody persistence. Real live runs use
  the operator's network + `.env`.

## 16. Roadmap (next, in priority order)

1. Accrue real operator labels in the ledger and retrain (replace synthetic bootstrap).
2. **Reddit OAuth** — set `REDDIT_CLIENT_ID`/`REDDIT_CLIENT_SECRET` to enable (last missing social platform).
3. Promotion sources (newsletters/stock-promo disclosures) via `FIRECRAWL_API_KEY`.
4. Corporate-actions / split & ticker-change feed (largest class of false anomalies).

## 7. Files

```
secfedclaw_v2/
  README.md            this plan + prototype overview
  SKILL.md             secfedclaw-watch-scoring-v2 agent skill
  config.py            path-portable root + .env loader (no value printing)
  connectors.py        live-or-replay DataConnector with full provenance
  robust_stats.py      robust statistical primitives
  scoring_v2.py        v0.2 composite engine
  agents.py            scout / analyst / adversary / packager + orchestrator
  scan.py              multi-ticker scan CLI (+ discovery)
  backtest.py          calibration harness (precision/recall)
  dashboard_v2.py      offline self-contained dashboard
  pipeline.py          one-command scan -> backtest -> dashboard
  edgar_pipeline.py    EDGAR daily-diff ingestion (state watermark, incremental)
  flatfiles.py         Polygon/Massive Flat Files client (stdlib SigV4, day-aggs)
  historical.py        real-data case/control replay through the v0.2 engine
  social_import.py     authorized Discord/Telegram/JSONL import (opt-in, lawful)
  ledger.py            operator calibration-label ledger
  model.py             numpy gradient-boosted review-priority model (advisory)
  train_model.py       train/cross-validate the model (ledger + synthetic bootstrap)
  preflight.py         per-source live-readiness check (GO/DEGRADED/REPLAY)
  label.py             operator labeling CLI for the calibration ledger
  daily.py             scheduled daily run (lock, preflight→edgar→scan→backtest→dashboard→digest)
  notify.py            daily WATCH digest (Telegram, file fallback, dashboard deep-link)
  serve.py             localhost static server to view/publish the dashboard
  usage.py             LLM usage & cost ledger (recorder + pricing + summary)
  agent_status.py      per-agent + integration status assembler
  explainer.py         LLM-backed review-summary agent (template fallback + guardrails)
  deploy/              launchd plist + cron + schedule_install.sh
  features/            market, social (X/Reddit/StockTwits), coordination, official, temporal, edgar, security_class, enforcement
  tests/               15 suites, ~75 tests (incl. enforcement, usage, live_flow, explainer)
  out/                 generated packages, review_queue, backtest, dashboard, edgar/
  flatfiles/day_aggs/  cached + hashed historical day-aggregate flat files
```
