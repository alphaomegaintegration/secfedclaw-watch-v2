# SECFEDCLAW v0.2 — Project Wiki

Finding ceiling: **WATCH** · Mode: review-priority only · Python 3.10+, stdlib-only

An agentic, connection-aware securities-surveillance prototype that fuses social, market, official (SEC/FINRA/Nasdaq), and microstructure signals into non-accusatory review-priority packages for authorized human review.

> ⚠️ **Operating boundary:** WATCH-only. No trading signals, no market actions, no accusations, no external contact, no asset freezes, no legal process.

## Pages

- **[Social Import + Model](Social-Import-and-Model.md)** — Authorized Discord/Telegram import, gradient-boosted review-priority model, and calibration ledger
- **[Security-Class Thresholds](Security-Class-Thresholds.md)** — Per-liquidity-class calibrated detection thresholds and operator dashboard KPIs
- **[Multi-Platform Social Signals](Multi-Platform-Social-Signals.md)** — Reddit OAuth, StockTwits sentiment, cross-platform normalization, and coordination detection
- **[Polygon Flat Files Integration](Polygon-Flat-Files-Integration.md)** — S3-compatible historical day-aggregate access, SigV4 signing, caching, and real-data historical backtest replay
- **[EDGAR Daily-Diff Pipeline](EDGAR-Daily-Diff-Pipeline.md)** — Incremental SEC filing ingestion with state watermarking and issuer-event scoring
- **[Architecture Overview](Architecture-Overview.md)** — Agentic pipeline, data flow, and scoring engine design
- **[Deployment and Monitoring](Deployment-and-Monitoring.md)** — Scheduled daily runs, preflight, digest, dashboard server, monitoring, and troubleshooting
- **[Running the System](Running-the-System.md)** — CLI reference, environment setup, and operational modes

## Quick Start

```bash
python3 -m pytest tests/ -q                   # 52 tests across 9 files
python3 pipeline.py                            # scan -> backtest -> dashboard
python3 daily.py                               # scheduled daily run (preflight->scan->dashboard->digest)
python3 preflight.py                           # per-source live-readiness check
python3 serve.py                               # dashboard at http://127.0.0.1:8787/
```
