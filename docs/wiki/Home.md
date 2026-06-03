# SECFEDCLAW v0.2 — Project Wiki

Finding ceiling: **WATCH** · Mode: review-priority only · Python 3.10+, stdlib-only

An agentic, connection-aware securities-surveillance prototype that fuses social, market, official (SEC/FINRA/Nasdaq), and microstructure signals into non-accusatory review-priority packages for authorized human review.

> ⚠️ **Operating boundary:** WATCH-only. No trading signals, no market actions, no accusations, no external contact, no asset freezes, no legal process.

## Pages

- **[Polygon Flat Files Integration](Polygon-Flat-Files-Integration.md)** — S3-compatible historical day-aggregate access, SigV4 signing, caching, and real-data historical backtest replay
- **[EDGAR Daily-Diff Pipeline](EDGAR-Daily-Diff-Pipeline.md)** — Incremental SEC filing ingestion with state watermarking and issuer-event scoring
- **[Architecture Overview](Architecture-Overview.md)** — Agentic pipeline, data flow, and scoring engine design
- **[Running the System](Running-the-System.md)** — CLI reference, environment setup, and operational modes

## Quick Start

```bash
python3 tests/test_v2.py                      # 14 + 6 + 5 = 25 tests
python3 pipeline.py                            # scan -> backtest -> dashboard
python3 historical.py --case TICKER:DATE:label # real-data historical replay
python3 edgar_pipeline.py --tickers AAPL       # incremental SEC filing ingestion
```
