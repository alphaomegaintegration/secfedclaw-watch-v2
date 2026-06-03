#!/usr/bin/env python3
"""Per-security-class calibration for SECFEDCLAW v0.2.

Pump-and-dump risk and the right detection thresholds differ sharply by
security class. Microcap / thin / OTC-like names are the classic targets and
warrant MORE sensitivity; mega-cap liquid names generate routine volume that
should NOT be mistaken for anomaly (the v0.1 "AAPL floats at MEDIUM" problem).

We classify by a liquidity proxy (price + daily dollar-volume) — honest and
data-available, without needing shares-outstanding — and return class-specific
thresholds for:
  * z_confirm        : robust-z required for price+volume double-confirmation
  * floor            : anomaly-evidence below which a package is held at LOW
                       (routine-context floor) — higher for liquid names
  * social_weight    : how much social/promo matters (higher for microcaps)
  * label            : human-readable class

All WATCH-level context; thresholds are calibration knobs, not proof logic.
"""
from __future__ import annotations

from typing import Any

CLASS_PARAMS: dict[str, dict[str, Any]] = {
    # thin / microcap / OTC-like: most pump-prone -> most sensitive
    "thin_microcap": {"z_confirm": 2.5, "floor": 18.0, "social_weight": 1.25,
                      "label": "thin / microcap / OTC-like"},
    "small_cap":     {"z_confirm": 2.8, "floor": 22.0, "social_weight": 1.10,
                      "label": "small cap"},
    "mid_cap":       {"z_confirm": 3.0, "floor": 26.0, "social_weight": 1.00,
                      "label": "mid cap"},
    "large_cap":     {"z_confirm": 3.6, "floor": 33.0, "social_weight": 0.85,
                      "label": "large / mega cap"},
    "unknown":       {"z_confirm": 3.0, "floor": 25.0, "social_weight": 1.00,
                      "label": "unknown (insufficient market data)"},
}


def classify(price: float | None, dollar_volume: float | None) -> str:
    """Liquidity-class proxy from latest price and daily dollar-volume."""
    if dollar_volume is None and price is None:
        return "unknown"
    dv = dollar_volume or 0.0
    px = price if price is not None else 99.0
    # Penny / thin names: low price OR low turnover.
    if px < 1.0 or dv < 5_000_000:
        return "thin_microcap"
    if dv < 50_000_000:
        return "small_cap"
    if dv < 500_000_000:
        return "mid_cap"
    return "large_cap"


def params(cls: str) -> dict[str, Any]:
    return CLASS_PARAMS.get(cls, CLASS_PARAMS["unknown"])


def classify_from_market(ts: dict[str, Any], xs: dict[str, Any],
                         market_metrics: dict[str, Any] | None = None) -> dict[str, Any]:
    """Derive class + params from available market feature dicts."""
    price = None
    dollar_volume = None
    # cross-sectional carries dollar_volume + (ret implies price moves); prefer it
    if xs and xs.get("available"):
        dollar_volume = xs.get("dollar_volume")
    # time-series last bar (if the daily series was parsed) gives a price level
    if market_metrics and market_metrics.get("last_close"):
        price = market_metrics.get("last_close")
    cls = classify(price, dollar_volume)
    p = params(cls)
    return {"class": cls, "label": p["label"], "z_confirm": p["z_confirm"],
            "floor": p["floor"], "social_weight": p["social_weight"],
            "price": price, "dollar_volume": dollar_volume}
