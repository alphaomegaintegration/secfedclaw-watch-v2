# Authorized Social Import + Review-Priority Model

**Commit:** `c1c331b` (2026-06-03) — *Authorized Discord/Telegram import + gradient-boosted review-priority model*
**Files:** `social_import.py`, `model.py`, `ledger.py`, `train_model.py`, `features/social.py`, `scoring_v2.py`, `tests/test_social_import.py`, `tests/test_model.py`

## Overview

Two final roadmap items, both within the WATCH / SOUL boundary:
1. **Authorized social import** — Discord/Telegram message ingestion from operator-provided lawful exports (no autonomous scraping)
2. **Gradient-boosted review-priority model** — pure-numpy advisory classifier with calibration ledger and operator feedback loop

---

## Authorized Social Import (`social_import.py`)

### Lawful-Authorization Boundary

This module **NEVER scrapes** private Discord/Telegram channels and performs **NO unauthorized access**. It only ingests data the operator has:
- Lawfully obtained (e.g. official Telegram Desktop export, Discord data export, DiscordChatExporter dump of an owned/authorized channel)
- Explicitly placed in the import directory (`out/social_import/`)
- Opted in via `SECFEDCLAW_AUTHORIZED_SOCIAL=1`

The feature is **OFF by default**. Both the opt-in flag AND files in the import directory are required.

### Supported Formats

| Format | Extension | Detection |
|---|---|---|
| **Telegram export** | `.json` | `messages[]` with `from_id` / `type` fields |
| **Discord export** | `.json` | `messages[]` with `author` / `timestamp` fields |
| **Generic JSONL** | `.jsonl` | One JSON object per line with `text`/`body`, `platform`, etc. |
| **CSV** | `.csv` | Header row with `text`/`body`, `platform`, etc. |

Telegram text segments (mixed formatting) are automatically concatenated. Discord reaction counts contribute to engagement.

### Integration

Imported messages normalize into the same post schema as X/Reddit/StockTwits (platforms `telegram`/`discord`), flowing through:
- Coordination graph (k-shingle clustering, burst sync)
- Social features (issuer-specific vs promo split, sentiment)
- Cross-platform detection (`n_platforms`, `cross_platform_issuer_specific`)

Wired via `features/social.normalize_posts(imported_posts=...)`.

### API

```python
# Check if authorized
social_import.authorized()  # → bool (reads SECFEDCLAW_AUTHORIZED_SOCIAL)

# Load operator-provided imports (returns [] if not authorized)
posts = social_import.load_authorized(ticker="ABC")  # filtered by ticker mention

# Status check
social_import.status()  # → {authorized, import_dir, files_present, note}
```

### Credentials

| Variable | Default | Purpose |
|---|---|---|
| `SECFEDCLAW_AUTHORIZED_SOCIAL` | *(unset = off)* | Set to `1`, `true`, or `yes` to enable import |

---

## Review-Priority Model (`model.py`)

### Design

A compact, dependency-light gradient boosting classifier over decision stumps with logistic loss. Pure numpy — no sklearn dependency.

Key constraints:
- **Advisory only** — never changes the interpretable rules-based priority
- **Never a guilt/fraud classifier** — outputs a calibrated triage probability
- **Never a trading signal** — strictly WATCH-level context
- **Abstains** until ≥40 labeled, two-class samples exist (≥8 per class)

### Feature Vector

14 features extracted from each scored package:

```
market_anomaly_score, coordination_score, market_structure_score,
issuer_event_score, halt_regulatory_score, issuer_context_score,
social_issuer_specific_burst, social_promotional_noise,
anomaly_evidence_score, evidence_quality_score,
n_families_active, n_platforms, bullish_ratio, class_ordinal
```

`class_ordinal` encodes security class: thin_microcap=0, small_cap=1, mid_cap=2, large_cap=3.

### Output

When a trained model exists, packages gain a `model_advisory` block:
```json
{
  "review_priority_probability": 0.8234,
  "top_features": [
    {"feature": "coordination_score", "value": 72.0, "importance": 0.312},
    {"feature": "market_anomaly_score", "value": 85.0, "importance": 0.198}
  ],
  "model_version": "gbm_v1",
  "note": "Advisory calibrated probability for triage only; not a guilt/fraud label or trading signal."
}
```

The rules-based review priority always remains primary.

---

## Calibration Ledger (`ledger.py`)

Records operator outcome labels on review packages — the human-in-the-loop feedback signal.

### Labels

| Label | y | Meaning |
|---|---|---|
| `useful_watch` | 1 | Genuinely review-worthy |
| `missed_event` | 1 | Should have been flagged higher |
| `false_positive` | 0 | Flagged but benign |
| `benign_explained` | 0 | Explained by legitimate catalyst |
| `insufficient_evidence` | 0 | Not enough to warrant review |

### Storage

Labels are stored as JSONL at `out/ledger/labels.jsonl`. Each row includes:
- Timestamp, ticker, source run ID
- Operator label and y value
- The package's original review priority
- Full 14-element feature vector (for direct model training)

### API

```python
ledger.add_label(package, "useful_watch", note="Confirmed coordination cluster")
ledger.load_labels()      # → list of label rows
ledger.to_xy(rows)        # → (X, y) for model training
ledger.summary()          # → {n_labels, by_label, n_positive, n_negative}
```

---

## Training (`train_model.py`)

### CLI

```bash
python3 train_model.py                 # ledger labels + synthetic bootstrap
python3 train_model.py --no-bootstrap  # ledger labels only
python3 train_model.py --boot-n 80     # more bootstrap samples per class
```

### Bootstrap Strategy

Until enough real operator labels exist, the trainer generates synthetic samples from the backtest corpus. Critically, **price/volume (and therefore liquidity class) are randomized independently of the label** — so the model must learn from genuine anomaly/coordination/social signal rather than a leaky class proxy.

The discriminator across labels is:
- **Pump:** coordinated promo + price/volume spike + reversal
- **Benign news:** real spike with no coordination
- **Control:** routine/flat activity

### Abstention

If fewer than 40 total samples or fewer than 8 per class, the model writes `abstain: true` and stays out of the way. The interpretable rules engine remains the sole priority driver.

### Validation

Reports 5-fold cross-validated AUC and top feature importances. On the bootstrap, the model recovers `coordination_score` as the top feature — consistent with pump-and-dump dynamics.

### Output

Model saved to `out/model/model.json`.

---

## Testing

### `tests/test_social_import.py` (4 tests)
- **Telegram export parsing** — verifies message extraction, text segment concatenation, platform tag
- **Discord export parsing** — verifies author extraction, reaction engagement, platform tag
- **JSONL parsing** — generic format with custom platform tags
- **Authorization gate** — confirms `load_authorized()` returns [] when not opted in

### `tests/test_model.py` (6 tests)
- **Feature vector extraction** — correct 14-element vector from a package
- **GBM fit and predict** — model trains and produces probabilities in [0, 1]
- **AUC computation** — known-order ranking gives expected AUC
- **Serialization roundtrip** — to_dict/from_dict preserves predictions
- **Abstention gate** — model abstains with insufficient labels
- **Bootstrap training** — synthetic corpus trains successfully, coordination_score ranks high

```bash
python3 -m pytest tests/test_social_import.py -v   # all 4 pass
python3 -m pytest tests/test_model.py -v            # all 6 pass
```
