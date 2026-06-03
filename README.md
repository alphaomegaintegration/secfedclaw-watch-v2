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

## 2. Data sources — current vs recommended

**Currently wired (and good):** Polygon (aggregates, grouped daily, snapshot,
trades, quotes) + **Flat Files** history, X recent search, **Reddit OAuth**,
**StockTwits** (sentiment), SEC EDGAR (submissions, companyfacts, FTD) +
**daily-diff pipeline**, FINRA (OTC threshold, Reg SHO daily, short interest),
Nasdaq (Reg SHO threshold, trade-halts RSS).

**Recommended additions (by leverage):**

1. **Polygon Flat Files (S3)** — credentials already in `.env`
   (`MASSIVE_FLATFILES_*`). Unlocks multi-year per-ticker baselines and the
   backtest corpus. *Highest leverage for calibration.*
2. **SEC bulk `submissions.zip` + `companyfacts.zip` daily diffs** — the
   recursive issuer-context pipeline you scoped in chat. Gives Form 4/144
   insider-sale and S-1/S-3/424B dilution context as first-class features.
3. **SEC full-text search (EFTS)** and **litigation/admin-proceeding feeds** —
   promoter/issuer enforcement history (design doc family E).
4. **Discord / Telegram** — implemented as an **authorized import** (operator
   provides lawful exports; no autonomous scraping). See §12.
5. **Promotion sources** (newsletters/stock-promo disclosures, public/ToS-OK)
   — design doc Use-Case 3; `FIRECRAWL_API_KEY` is present for bounded fetches.
6. **Options flow / OPRA** (Polygon entitlement) — unusual options pre-pump.
7. **Corporate-actions / split & ticker-change feed** — kills the largest class
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

Four role-bounded agents (`agents.py`), mirroring SOUL.md detect→analyze→review→package:

```
ScoutAgent     → gathers source data (live via .env, else replay), reports health
AnalystAgent   → runs the v0.2 scoring engine
AdversaryAgent → red-teams: benign tests, coordination-cluster sanity,
                 corroboration enforcement; may ONLY lower priority / add caveats
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

Self-contained offline HTML (inline CSS/JS, **no external callbacks**, same
constraint as the production dashboard) → `out/dashboard_v2.html`. Three tabs:
ranked **Review Queue** (priority-filterable, with a **liquidity-class** column),
**Packages** (component bars, caps, coordination clusters, adversary caveats,
benign review), and **Backtest / Calibration** (confusion matrix, ledger, SEC
case corpus). The Review Queue now leads with operator **KPI cards** — universe
size, **score-ready %**, flagged ≥MEDIUM, CRITICAL/HIGH counts, mean
anomaly-evidence, data mode — plus a **source-health panel** aggregating
live/replay/ok across scanned tickers. Run `python3 pipeline.py` to refresh.

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

## 13. Review-priority model + calibration ledger (implemented — `model.py`, `ledger.py`, `train_model.py`)

A dependency-light (numpy-only, **no sklearn**) **gradient-boosted** classifier
over decision stumps that outputs a *calibrated review-priority probability* and
per-feature contributions — an advisory triage aid that **never** changes the
interpretable rules-based priority and is **never** a guilt/fraud label.

- `ledger.py` records operator outcome labels (`useful_watch`/`missed_event` →
  positive; `false_positive`/`benign_explained`/`insufficient_evidence` →
  negative) with each package's feature vector at `out/ledger/labels.jsonl`.
- `train_model.py` trains from real ledger labels + an optional synthetic
  bootstrap (price/volume randomized independently of the label to avoid class
  leakage), reports 5-fold AUC, and **abstains** (model stays out of the way)
  until ≥40 two-class labeled samples exist.
- When a trained model is present, every package gets a `model_advisory`
  (probability + top features); the rules engine remains primary.

On the synthetic bootstrap the model recovers `coordination_score` as the top
feature — the correct pump discriminator — rather than any leaky proxy.

```bash
python3 train_model.py            # ledger + synthetic bootstrap
python3 train_model.py --no-bootstrap   # real ledger labels only
```

## 14. Roadmap (next, in priority order)

1. Accrue real operator labels in the ledger and retrain (replace synthetic bootstrap).
2. Per-class precision/recall reporting in the backtest (microcap vs large).
3. Promoter/issuer enforcement-history feed (SEC litigation releases).

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
  features/            market, social (X/Reddit/StockTwits), coordination, official, temporal, edgar, security_class
  tests/               test_v2 (14) + edgar (6) + flatfiles (5) + social (5) + security_class (5) + social_import (4) + model (6)
  out/                 generated packages, review_queue, backtest, dashboard, edgar/
  flatfiles/day_aggs/  cached + hashed historical day-aggregate flat files
```
