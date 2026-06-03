---
name: secfedclaw-watch-scoring-v2
description: Use to run or extend the SECFEDCLAW v0.2 agentic multi-ticker WATCH scanner — robust rolling/cross-sectional market anomaly, real coordination graph, microstructure features, temporal corroboration gating — over the .env data connections (live or replay). WATCH-only.
version: 2.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [secfedclaw, scoring, watch, anomaly-detection, coordination, multi-ticker, agentic]
    related_skills: [secfedclaw-algorithms-agent, secfedclaw-watch-scoring]
---

# SECFEDCLAW WATCH Scoring v0.2 (agentic, multi-ticker)

## Overview

v0.2 is a connection-aware, multi-ticker upgrade of the v0.1 single-ticker
scorer. It runs a four-agent pipeline (scout → analyst → adversary → packager)
across a ticker universe and emits a ranked review queue of non-accusatory
WATCH packages. It uses the real `.env` connections when network egress is
available (live) and falls back to local custody artifacts (replay) with full
provenance preserved either way.

It does NOT produce trading signals, accusations, or findings above WATCH.

## Algorithmic upgrades vs v0.1

1. **Robust market anomaly** — median/MAD rolling 20/60-day z-scores AND
   same-day cross-sectional z vs the whole-market population; **price + volume
   double-confirmation** required for a high market anomaly. (v0.1 used
   absolute return/volume magnitudes → large caps floated at MEDIUM.)
2. **Real coordination score** — near-duplicate text clustering (k-shingle
   Jaccard), shared-domain co-occurrence, burst synchronization, author
   concentration (HHI). (v0.1 hard-coded `coordination_score = 0.0`.)
3. **Microstructure features** — trade-count burst, large-trade share, quote
   spread (bps), VWAP shift, from snapshot/trades/quotes. (Collected but
   unused in v0.1.)
4. **Social split** — issuer-specific burst vs promotional noise vs
   coordination candidate; promo noise DEFLATES rather than inflates; posts
   deduplicated by (platform, id) before scoring.
5. **Temporal corroboration gating** — HIGH/CRITICAL requires ≥ 2 independent
   active families; the multiplier anchors on concern-bearing anomaly
   evidence, separated from reviewability (evidence quality).
6. **Multi-ticker scan + discovery** — scores a universe and can discover the
   top cross-sectional movers from the grouped-daily snapshot.
7. **EDGAR daily-diff pipeline** (`edgar_pipeline.py`) — incremental SEC
   daily-index ingestion with a state watermark; extracts a concern-bearing
   `issuer_event` signal (insider/dilution/delisting) that corroborates a move.
8. **Polygon Flat Files historical replay** (`flatfiles.py`, `historical.py`) —
   stdlib-SigV4 S3 access to day-aggregate history (`MASSIVE_FLATFILES_*`) so
   the backtest runs on real SEC-case windows; validates the market-anomaly
   component (rolling + cross-sectional, double-confirmation) on real data.
9. **Multi-platform social** (X + Reddit OAuth + StockTwits) — normalized into
   one schema; adds sentiment (Bullish/Bearish), cross-platform corroboration,
   and a unanimous-bullish+promo coordination nudge. Reddit needs
   `REDDIT_CLIENT_ID`/`REDDIT_CLIENT_SECRET`; StockTwits is public.
10. **Per-security-class calibration** (`features/security_class.py`) — liquidity
    class (thin/μcap → small → mid → large) sets z_confirm, routine-context
    floor, and social weight, emitted as `security_class` and shown on the
    dashboard (KPI cards, score-ready %, source-health, class column).
11. **Authorized Discord/Telegram import** (`social_import.py`) — lawful
    operator-provided exports only (opt-in `SECFEDCLAW_AUTHORIZED_SOCIAL=1`); no
    autonomous private-channel scraping.
12. **Review-priority model + ledger** (`model.py`, `ledger.py`, `train_model.py`)
    — numpy-only gradient boosting; calibrated advisory probability + feature
    contributions; abstains until ≥40 two-class operator labels; rules engine
    stays primary; never a guilt label.

14. **Scheduled daily run** (`daily.py`, `deploy/`) — lock-protected, logged
    once-per-day pass (preflight→EDGAR→scan→backtest→dashboard) writing
    `out/daily_run_summary.json`; install via launchd (`deploy/schedule_install.sh`)
    or cron (`deploy/secfedclaw.cron`). Independent of the legacy hermes cron.

## Commands

From the repo root:

```bash
python3 tests/test_v2.py                          # unit tests (stdlib unittest)
python3 scan.py --tickers AAPL TSLA AMC GME       # explicit universe
python3 scan.py --discover 15                     # default universe + top 15 movers
python3 scan.py --no-live                          # force replay from custody artifacts
python3 -c "from agents import Orchestrator; print(Orchestrator().run('AAPL'))"
python3 edgar_pipeline.py --tickers AAPL TSLA AMC GME    # EDGAR daily-diff ingest
python3 historical.py --case TKR:2021-09-13:pump         # real Flat Files replay
python3 tests/test_edgar.py                              # EDGAR unit tests
python3 tests/test_flatfiles.py                          # Flat Files unit tests
```

Outputs: per-ticker packages and a ranked `review_queue.json` under
`secfedclaw_v2/out/`.

## Live vs replay

- **Live** (operator laptop): `DataConnector.live_available()` probes Polygon
  market status with `POLYGON_API_KEY`; if reachable it fetches Polygon daily
  range / grouped / snapshot, X recent search, and SEC submissions live.
- **Replay** (locked-down sandbox): falls back to the newest matching artifact
  under `collections/` and `artifacts/`. Every record carries
  source, mode, artifact path, sha256, and a redacted URL.

## Required package fields

ticker, generated_utc, algorithm_version (`watch_score_v0.2.0`),
finding_ceiling (WATCH), data_mode, watch_score, raw_score_before_caps,
review_priority, anomaly_evidence_score, evidence_quality_score, corroboration,
component_scores, score_caps_applied, benign_explanation_review, market_detail,
social_metrics, coordination_detail, evidence, evidence_gaps,
adversarial_review, review_questions, limitations, prohibited_actions.

## Guardrails

- LOW / MEDIUM / HIGH / CRITICAL_REVIEW are review-priority labels only.
- Single-family, social-only, no-market-context, low-evidence-quality,
  social-corroboration-unavailable, and routine-context-floor caps all apply.
- The adversary agent may only LOWER priority or add caveats, never raise it.
- Coordination/social features are high-false-positive: clusters are always
  emitted for human verification.
- Output explicitly prohibits trading signals, market actions, autonomous
  freezing, legal process, and external contacts.

## Verification checklist

- [ ] `python3 tests/test_v2.py` passes.
- [ ] Each package has algorithm_version, WATCH ceiling, prohibited_actions.
- [ ] Each package cites artifacts/hashes (replay) or redacted URLs (live).
- [ ] No recommendation to trade or contact external parties.
- [ ] HIGH/CRITICAL only when ≥ 2 independent families corroborate.
