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
trades, quotes), X recent search, SEC EDGAR (submissions, companyfacts,
companyconcept, FTD), FINRA (OTC threshold, Reg SHO daily, short interest),
Nasdaq (Reg SHO threshold, trade-halts RSS). Reddit public JSON is 403-blocked.

**Recommended additions (by leverage):**

1. **Polygon Flat Files (S3)** — credentials already in `.env`
   (`MASSIVE_FLATFILES_*`). Unlocks multi-year per-ticker baselines and the
   backtest corpus. *Highest leverage for calibration.*
2. **SEC bulk `submissions.zip` + `companyfacts.zip` daily diffs** — the
   recursive issuer-context pipeline you scoped in chat. Gives Form 4/144
   insider-sale and S-1/S-3/424B dilution context as first-class features.
3. **SEC full-text search (EFTS)** and **litigation/admin-proceeding feeds** —
   promoter/issuer enforcement history (design doc family E).
4. **Reddit via authenticated API** (OAuth, ToS-compliant) — restores
   cross-platform social corroboration (currently blocked).
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
ranked **Review Queue** (priority-filterable), **Packages** (component bars,
caps, coordination clusters, adversary caveats, benign review), and
**Backtest / Calibration** (KPI cards, confusion matrix, calibration ledger,
SEC case corpus). Run `python3 pipeline.py` to refresh all three from data.

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

## 10. Roadmap (next, in priority order)

1. **Reddit OAuth** restore (cross-platform corroboration).
4. Merge the v0.2 panel into the production dashboard + score-ready-ratio KPI.
5. Per-security-class calibrated thresholds (OTC / microcap / small / large).
6. Optional gradient-boosted review-priority model once the labeled corpus
   exists (interpretable, calibrated probability — never a guilt classifier).

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
  features/            market, social, coordination, official, temporal, edgar
  tests/               test_v2.py (14) + test_edgar.py (6) + test_flatfiles.py (5)
  out/                 generated packages, review_queue, backtest, dashboard, edgar/
  flatfiles/day_aggs/  cached + hashed historical day-aggregate flat files
```
