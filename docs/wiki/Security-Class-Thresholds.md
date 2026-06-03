# Per-Security-Class Calibrated Thresholds

**Commit:** `522afe0` (2026-06-03) — *Per-security-class calibrated thresholds + operator dashboard KPIs*
**Files:** `features/security_class.py`, `features/market.py`, `scoring_v2.py`, `dashboard_v2.py`, `agents.py`, `tests/test_security_class.py`

## Overview

Detection thresholds are now calibrated per liquidity class instead of one-size-fits-all. This fixes two problems from v0.1:
- **Large-cap noise:** AAPL's routine volume was falsely flagged at MEDIUM
- **Microcap under-sensitivity:** the actual pump targets (thin/OTC names) weren't getting enough detection sensitivity

## Liquidity Classification

`features/security_class.py` classifies each ticker by a **price + daily dollar-volume proxy** (no shares-outstanding needed) into four classes:

| Class | Price | Dollar Volume | Description |
|---|---|---|---|
| `thin_microcap` | < $1.00 OR any | < $5M | Penny / thin / OTC-like — classic pump targets |
| `small_cap` | any | $5M – $50M | Small cap |
| `mid_cap` | any | $50M – $500M | Mid cap |
| `large_cap` | any | > $500M | Large / mega cap |
| `unknown` | unavailable | unavailable | Insufficient market data |

Classification inputs come from the cross-sectional data (dollar volume) and time-series last bar (price level).

## Class-Specific Thresholds

Each class has three calibrated parameters:

| Class | `z_confirm` | `floor` | `social_weight` |
|---|---|---|---|
| `thin_microcap` | 2.5 | 18.0 | 1.25× |
| `small_cap` | 2.8 | 22.0 | 1.10× |
| `mid_cap` | 3.0 | 26.0 | 1.00× |
| `large_cap` | 3.6 | 33.0 | 0.85× |
| `unknown` | 3.0 | 25.0 | 1.00× |

### Parameter Definitions

- **`z_confirm`** — Robust z-score threshold for price+volume double-confirmation. Lower values = more sensitive. Microcaps use 2.5 (catches smaller deviations); large caps use 3.6 (ignores routine volume spikes).
- **`floor`** — Routine-context floor: anomaly-evidence must exceed this value to escape LOW review priority. Higher for liquid names (33 for large cap) because their normal activity generates more baseline noise.
- **`social_weight`** — Multiplier on social/promo signal contribution. Higher for microcaps (1.25×) because social promotion is a primary pump vector in thin markets; lower for large caps (0.85×) where social volume is routine.

### Design Principle
The ordering is intentional: microcaps get **more sensitivity** (lower z, lower floor, higher social weight) because they are the classic pump-and-dump targets. Large caps get **less sensitivity** because their routine activity generates statistical noise that shouldn't trigger review.

## Scoring Integration

### `features/market.py`
- Uses class-specific `z_confirm` threshold for double-confirmation instead of a fixed value
- Exposes `last_close` and `last_dollar_volume` for classification

### `scoring_v2.py`
- Applies class-aware `floor` as the routine-context floor (replaces fixed value)
- Applies `social_weight` multiplier to social score contributions
- Includes a `security_class` block in every output package:
  ```json
  {
    "class": "large_cap",
    "label": "large / mega cap",
    "z_confirm": 3.6,
    "routine_context_floor": 33.0,
    "social_weight": 0.85,
    "price": 195.2,
    "dollar_volume": 8500000000
  }
  ```

### `agents.py`
- `PackagerAgent` summary now carries `security_class` for queue/dashboard display

## Dashboard Upgrades

`dashboard_v2.py` now includes:

### Operator KPI Cards
- **Universe** — total tickers scanned
- **Scored** — tickers with valid packages
- **Score-ready %** — scored / universe
- **Flagged ≥MED** — count of MEDIUM + HIGH + CRITICAL
- **CRITICAL / HIGH** — individual counts
- **Mean anomaly** — average anomaly-evidence across scored tickers
- **Mode** — overall data mode (live/replay)

### Source Health Panel
Aggregates per-source health across all scanned tickers:
- **ok** — sources that returned data / total attempts
- **live** — count of live fetches
- **replay** — count of replay fetches

### Liquidity Class Column
The review queue table now shows the security class abbreviation (thin/μcap, small, mid, large) for each ticker.

### Rendering
Still fully offline — inline CSS/JS, no external callbacks, same constraint as production.

## Validated Behavior

- **AAPL** → `large_cap` (floor 33, z_confirm 3.6) → stays **LOW** on routine volume
- **AMC** → `small_cap` (floor 22, z_confirm 2.8) → appropriate sensitivity
- **Backtest** — precision/recall unchanged at 0.71/1.00 (the thresholds shift WHERE detection fires, not whether it fires on genuine pumps)

## Testing

5 tests in `tests/test_security_class.py`:

- **`TestClassify.test_classes`** — Verifies classification boundaries: penny ($0.50) → thin_microcap, thin turnover ($2M) → thin_microcap, $20/$20M → small_cap, $50/$200M → mid_cap, $200/$5B → large_cap, None/None → unknown.
- **`TestClassify.test_params_ordering`** — Asserts the threshold ordering invariant: liquid names have higher z_confirm and floor; microcaps have higher social_weight.
- **`TestClassAwareScoring.test_large_cap_classified_and_high_floor`** — End-to-end: $300 name with ~1.5B daily dollar-volume → classified as large_cap, floor=33, review priority=LOW.
- **`TestClassAwareScoring.test_microcap_lower_z_confirm`** — End-to-end: $0.50 penny stock with price jump → classified as thin_microcap, z_confirm=2.5.

```bash
python3 -m pytest tests/test_security_class.py -v   # all 5 pass
```
