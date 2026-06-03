# EDGAR Daily-Diff Pipeline

**Commit:** `02ddf20` (2026-06-03) — *EDGAR daily-diff pipeline + issuer_event scoring signal*
**Files:** `edgar_pipeline.py`, `features/edgar.py`, `tests/test_edgar.py`

## Overview

Incremental SEC EDGAR ingestion ("just the diffs"). A state watermark tracks the last processed date and seen accession numbers so each daily run only processes new filings — cron-friendly and recursive/adaptive.

The scorer consumes the output as a **concern-bearing `issuer_event` signal**: insiders/issuers selling or diluting into promoted demand is a classic pump tell, so `issuer_event` is a corroborating family that feeds `anomaly_evidence`.

## Pipeline Flow

```
ticker list
    │
    ▼
company_tickers.json ──▶ resolve ticker → CIK
    │
    ▼
SEC daily-index master file (per business day)
    │
    ▼
Parse pump-relevant filings:
  • Insider: Forms 3, 4, 5, 144
  • Dilution: S-1, S-3, 424B, EFFECT, S-8
  • Material: 8-K
  • Late: NT 10-K, NT 10-Q
  • Delisting: Forms 25, 15-12B
    │
    ▼
Diff against seen accessions (state/edgar_state.json)
    │
    ▼
Recompute per-ticker issuer features
    │
    ▼
out/edgar/issuer_features_<TICKER>.json
```

## State Watermark

The pipeline maintains state at `state/edgar_state.json`:

```json
{
  "last_processed_date": "2026-06-02",
  "seen_accessions": ["0001234567-26-000123", ...]
}
```

Each run advances from the last processed date, fetching only new business days. Already-seen accession numbers are skipped, ensuring idempotent re-runs.

## Filing Categories

Filings are classified into pump-relevant categories:

| Category | Form Types | Relevance |
|---|---|---|
| **Insider** | 3, 4, 5, 144 | Insider sales/transfers into promoted demand |
| **Dilution** | S-1, S-3, 424B, EFFECT, S-8 | Share dilution concurrent with promotion |
| **Material** | 8-K | Material events that may explain or mask pumps |
| **Late** | NT 10-K, NT 10-Q | Late filings signal issuer distress |
| **Delisting** | 25, 15-12B | Imminent delisting / deregistration |

## CLI

```bash
# Daily incremental run for specific tickers
python3 edgar_pipeline.py --tickers AAPL TSLA AMC GME

# Advance up to 5 business days
python3 edgar_pipeline.py --max-days 5

# Cron schedule (daily, weekdays at 9am)
# 0 9 * * 1-5  cd .../secfedclaw_v2 && python3 edgar_pipeline.py
```

## Issuer Features Output

Per-ticker features written to `out/edgar/issuer_features_<TICKER>.json`:

```json
{
  "ticker": "AAPL",
  "cik": "0000320193",
  "insider_filing_count": 3,
  "dilution_filing_count": 0,
  "material_filing_count": 1,
  "late_filing_count": 0,
  "delisting_filing_count": 0,
  "issuer_event_score": 0.35,
  "filings": [...]
}
```

The `issuer_event_score` (0–1) is computed by `features/edgar.py` and consumed by `scoring_v2.py` as a component of `anomaly_evidence`.

## Scoring Integration

The `issuer_event` signal flows into the scoring engine:

1. **`features/edgar.py`** computes pure issuer-event features and a normalized score from filing counts and categories.
2. **`scoring_v2.py`** incorporates `issuer_event` as a component of the rebalanced `anomaly_evidence` score. It is a **corroborating family** — meaning it can contribute to the ≥2 family threshold required for HIGH/CRITICAL review priority.
3. **`features/temporal.py`** recognizes `issuer_event` as a corroboration family for cross-source temporal analysis.
4. **`connectors.py`** provides `sec_daily_index`, `sec_company_tickers`, and `edgar_issuer_features` connectors.

## Connection Modes

- **Live:** Uses `SEC_USER_AGENT` environment variable to make requests to SEC EDGAR. Required format: `"Company Name email@example.com"` per SEC fair access policy.
- **Offline:** Parses any cached daily-index files. If no cache exists, the pipeline no-ops while preserving state — safe for cron in disconnected environments.

## Testing

6 tests in `tests/test_edgar.py`:

- **`TestParse.test_classify`** — Verifies filing type classification into categories.
- **`TestParse.test_parse_master_idx`** — Tests daily-index master file parsing.
- **`TestFeatures.test_empty_features_zero`** — Empty filings produce a zero score.
- **`TestFeatures.test_issuer_features_and_score`** — Insider + dilution filings produce expected feature counts and a non-zero score.
- **`TestScoringIntegration.test_absent_edgar_is_zero_and_safe`** — Missing EDGAR data produces zero `issuer_event` and does not inflate review priority.
- **`TestScoringIntegration.test_issuer_event_flows_into_score`** — Confirms `issuer_event` correctly feeds into the composite `anomaly_evidence` score.

```bash
python3 -m pytest tests/test_edgar.py -v   # all 6 pass
```
