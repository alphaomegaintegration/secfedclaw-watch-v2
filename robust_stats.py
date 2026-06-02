#!/usr/bin/env python3
"""Robust statistics for SECFEDCLAW scoring v0.2.

Pure-stdlib implementations (no scipy/sklearn dependency) of the robust
baseline primitives recommended by the SECFEDCLAW scoring research:
median/MAD robust z-scores, EWMA, winsorization, and cross-sectional
(market-relative) z-scores.

These are *anomaly-context* primitives only. Nothing here is a trading
signal or proof of misconduct.
"""
from __future__ import annotations

import math
from typing import Iterable, Sequence

# 0.6745 = inverse of the standard-normal IQR scaling used to make the
# MAD a consistent estimator of the standard deviation for Gaussian data.
_MAD_SCALE = 0.6745


def median(values: Sequence[float]) -> float:
    xs = sorted(v for v in values if v is not None and not _isnan(v))
    n = len(xs)
    if n == 0:
        return float("nan")
    mid = n // 2
    if n % 2:
        return float(xs[mid])
    return (xs[mid - 1] + xs[mid]) / 2.0


def mad(values: Sequence[float], center: float | None = None) -> float:
    """Median absolute deviation."""
    xs = [v for v in values if v is not None and not _isnan(v)]
    if not xs:
        return float("nan")
    c = median(xs) if center is None else center
    return median([abs(v - c) for v in xs])


def robust_z(x: float, baseline: Sequence[float]) -> float:
    """Robust z-score of x against a baseline distribution.

    Uses median/MAD. Falls back to a small epsilon when MAD is zero so a
    constant-then-jump series still produces a finite, large score rather
    than infinity.
    """
    if x is None or _isnan(x):
        return float("nan")
    base = [v for v in baseline if v is not None and not _isnan(v)]
    if len(base) < 3:
        return float("nan")
    c = median(base)
    m = mad(base, c)
    if m == 0 or _isnan(m):
        # Degenerate spread: use a scaled IQR / range fallback.
        spread = (_quantile(base, 0.75) - _quantile(base, 0.25)) or (max(base) - min(base))
        if spread == 0:
            return 0.0 if x == c else math.copysign(6.0, x - c)
        return (x - c) / (spread * 0.7413)
    return _MAD_SCALE * (x - c) / m


def cross_sectional_z(x: float, population: Sequence[float]) -> float:
    """Robust z of x against a same-period cross-sectional population.

    This is the market-relative anomaly primitive: how extreme is this
    ticker's value versus every other ticker on the same day. Robust to
    the heavy tails of market-wide return/volume distributions.
    """
    return robust_z(x, population)


def ewma(values: Sequence[float], halflife: float) -> float:
    """Exponentially weighted moving average with a half-life in periods."""
    xs = [v for v in values if v is not None and not _isnan(v)]
    if not xs:
        return float("nan")
    alpha = 1.0 - math.exp(math.log(0.5) / max(halflife, 1e-9))
    acc = xs[0]
    for v in xs[1:]:
        acc = alpha * v + (1 - alpha) * acc
    return acc


def winsorize(values: Sequence[float], limits: tuple[float, float] = (0.01, 0.99)) -> list[float]:
    xs = [v for v in values if v is not None and not _isnan(v)]
    if not xs:
        return []
    lo = _quantile(xs, limits[0])
    hi = _quantile(xs, limits[1])
    return [min(max(v, lo), hi) for v in xs]


def gini(values: Sequence[float]) -> float:
    """Gini concentration coefficient in [0,1]; used for actor concentration."""
    xs = sorted(v for v in values if v is not None and v >= 0)
    n = len(xs)
    if n == 0 or sum(xs) == 0:
        return 0.0
    cum = 0.0
    for i, v in enumerate(xs, start=1):
        cum += i * v
    return (2 * cum) / (n * sum(xs)) - (n + 1) / n


def hhi(counts: Sequence[float]) -> float:
    """Herfindahl-Hirschman index (normalized 0..1) of a count distribution."""
    total = sum(c for c in counts if c and c > 0)
    if total <= 0:
        return 0.0
    shares = [(c / total) ** 2 for c in counts if c and c > 0]
    return sum(shares)


def squash(value: float, scale: float, cap: float = 100.0) -> float:
    """Map an unbounded non-negative magnitude onto a bounded 0..cap score.

    Uses a saturating curve so very large robust-z values do not dominate.
    """
    if value is None or _isnan(value):
        return 0.0
    v = abs(value)
    return cap * (1.0 - math.exp(-v / max(scale, 1e-9)))


def _quantile(values: Sequence[float], q: float) -> float:
    xs = sorted(v for v in values if v is not None and not _isnan(v))
    if not xs:
        return float("nan")
    if len(xs) == 1:
        return float(xs[0])
    pos = q * (len(xs) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return float(xs[lo])
    frac = pos - lo
    return xs[lo] * (1 - frac) + xs[hi] * frac


def _isnan(v) -> bool:
    try:
        return math.isnan(v)
    except (TypeError, ValueError):
        return False
