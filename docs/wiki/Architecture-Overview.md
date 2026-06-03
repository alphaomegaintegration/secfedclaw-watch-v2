# Architecture Overview

## Agentic Pipeline

Four role-bounded agents (`agents.py`), mirroring the detect→analyze→review→package workflow:

```
ScoutAgent     → gathers source data (live via .env, else replay), reports health
AnalystAgent   → runs the v0.2 scoring engine
AdversaryAgent → red-teams: benign tests, coordination-cluster sanity,
                 corroboration enforcement; may ONLY lower priority / add caveats
PackagerAgent  → writes the custody-preserving (sha256) review package
Orchestrator   → runs the loop per ticker; scan.py runs it across the universe
```

## Data Sources

### Currently Wired
- **Polygon** — aggregates, grouped daily, snapshot, trades, quotes
- **Polygon Flat Files** — S3-compatible historical day-aggregates via SigV4 (see [Polygon Flat Files Integration](Polygon-Flat-Files-Integration.md))
- **X (Twitter)** — recent search
- **SEC EDGAR** — submissions, companyfacts, companyconcept, FTD, daily-index diff (see [EDGAR Daily-Diff Pipeline](EDGAR-Daily-Diff-Pipeline.md))
- **FINRA** — OTC threshold, Reg SHO daily, short interest
- **Nasdaq** — Reg SHO threshold, trade-halts RSS
- **Reddit** — public JSON (currently 403-blocked)

### Connection Modes
Every data source operates in one of three modes:
1. **Live** — real API calls using `.env` credentials
2. **Replay** — reads from cached custody artifacts
3. **Unavailable** — graceful degradation, zero contribution to scores

## Scoring Engine (scoring_v2.py)

The v0.2 composite engine computes review priority through:

1. **Component scores** — market_anomaly, social, coordination, official, microstructure, issuer_event
2. **Anomaly evidence** — concern-bearing anchor separated from reviewability
3. **Temporal corroboration** — cross-source multiplier; HIGH/CRITICAL needs ≥2 families
4. **Review priority** — LOW / MEDIUM / HIGH / CRITICAL_REVIEW (WATCH ceiling)

Key design principles:
- Double-confirmation required (price AND volume) for market anomaly
- Promo content **deflates** social scores (not inflates)
- Routine-context floor caps benign tickers to LOW
- Benign-explanation band reduction for known-explainable moves

## Feature Modules

```
features/
  market.py        time-series + cross-sectional anomaly, microstructure
  social.py        normalize/dedup, issuer-specific vs promo-noise split
  coordination.py  k-shingle Jaccard clustering, shared domains, burst sync
  official.py      FTD/threshold/halt/issuer (any ticker)
  temporal.py      cross-source corroboration multiplier
  edgar.py         issuer-event features from SEC filing diffs
```

## Output Artifacts

```
out/
  review_queue.json                ranked review queue
  <TICKER>_..._watch_v2.json       per-ticker review packages
  dashboard_v2.html                offline self-contained dashboard
  historical_results.json          flat-file backtest results
  edgar/
    issuer_features_<TICKER>.json  per-ticker EDGAR issuer features
```

## Test Suite

25 tests across 3 files:
- `tests/test_v2.py` — 14 tests (robust stats, market, coordination, social, composite)
- `tests/test_edgar.py` — 6 tests (parsing, features, scoring integration)
- `tests/test_flatfiles.py` — 5 tests (parsing, signing, market fetches, scoring)
