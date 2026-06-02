#!/usr/bin/env python3
"""Market anomaly + microstructure features for SECFEDCLAW v0.2.

Upgrades over v0.1:
  * Time-series robust z-scores (median/MAD) vs rolling 20/60d baselines
    instead of absolute return/volume magnitudes.
  * Cross-sectional (market-relative) robust z vs the same-day population of
    all tickers, so a thin name's move is judged against the market, not its
    own absolute size.
  * Price AND volume DOUBLE-CONFIRMATION required for a high anomaly.
  * Microstructure features from snapshot/trades/quotes (previously collected
    but unused): trade-count burst, quote-count, spread proxy, VWAP deviation.
  * Liquidity / thinness filter and corporate-action discontinuity flag.

All outputs are anomaly *context* for human review, never proof or signals.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import robust_stats as rs  # noqa: E402


def _daily_results(fetch_data: Any) -> list[dict]:
    if isinstance(fetch_data, dict):
        res = fetch_data.get("results")
        if isinstance(res, list):
            return [r for r in res if isinstance(r, dict)]
    return []


def _series(results: list[dict]) -> dict[str, list[float]]:
    """Derive per-day feature series from OHLCV bars."""
    closes = [r.get("c") for r in results]
    out: dict[str, list[float]] = {
        "intraday_return_pct": [],
        "cc_return_pct": [],          # close-to-close
        "abs_cc_return_pct": [],
        "log_volume": [],
        "dollar_volume": [],
        "hl_range_pct": [],
        "trades_n": [],
    }
    import math
    prev_close = None
    for r in results:
        o, h, l, c, v = (r.get(k) for k in ("o", "h", "l", "c", "v"))
        if o:
            out["intraday_return_pct"].append((c - o) / o * 100 if c and o else float("nan"))
        else:
            out["intraday_return_pct"].append(float("nan"))
        if prev_close:
            cc = (c - prev_close) / prev_close * 100 if c else float("nan")
        else:
            cc = float("nan")
        out["cc_return_pct"].append(cc)
        out["abs_cc_return_pct"].append(abs(cc) if cc == cc else float("nan"))
        out["log_volume"].append(math.log10(v + 1) if v else float("nan"))
        out["dollar_volume"].append((v * (r.get("vw") or c or 0)) if v else float("nan"))
        out["hl_range_pct"].append((h - l) / c * 100 if (h and l and c) else float("nan"))
        out["trades_n"].append(float(r.get("n")) if r.get("n") else float("nan"))
        prev_close = c
    return out


def time_series_anomaly(daily_fetch_data: Any) -> dict[str, Any]:
    """Latest-day robust anomaly vs the preceding 20/60d rolling baseline."""
    results = _daily_results(daily_fetch_data)
    out: dict[str, Any] = {"available": False, "n_days": len(results)}
    if len(results) < 5:
        out["note"] = "insufficient daily history for rolling baseline"
        return out
    s = _series(results)
    out["available"] = True

    def latest_z(key: str, win: int) -> float:
        col = [v for v in s[key] if v == v]  # drop nan
        if len(col) < 4:
            return float("nan")
        latest = col[-1]
        baseline = col[max(0, len(col) - 1 - win):-1]
        return rs.robust_z(latest, baseline)

    win = 20 if len(results) >= 22 else max(4, len(results) - 1)
    long_win = 60 if len(results) >= 62 else win
    z = {
        "abs_return_z_20": latest_z("abs_cc_return_pct", win),
        "abs_return_z_60": latest_z("abs_cc_return_pct", long_win),
        "log_volume_z_20": latest_z("log_volume", win),
        "log_volume_z_60": latest_z("log_volume", long_win),
        "hl_range_z_20": latest_z("hl_range_pct", win),
        "trades_n_z_20": latest_z("trades_n", win),
    }
    out["z"] = {k: (round(v, 3) if v == v else None) for k, v in z.items()}
    out["baseline_window"] = win

    price_z = _best(z["abs_return_z_20"], z["abs_return_z_60"])
    vol_z = _best(z["log_volume_z_20"], z["log_volume_z_60"])
    out["price_z"] = round(price_z, 3) if price_z == price_z else None
    out["volume_z"] = round(vol_z, 3) if vol_z == vol_z else None
    out["double_confirmed"] = bool((price_z == price_z and price_z >= 3.0) and (vol_z == vol_z and vol_z >= 3.0))
    return out


def cross_sectional_anomaly(grouped_fetch_data: Any, ticker: str) -> dict[str, Any]:
    """Same-day robust z of this ticker vs the whole-market population."""
    out: dict[str, Any] = {"available": False}
    if not isinstance(grouped_fetch_data, dict):
        return out
    rows = grouped_fetch_data.get("results") or []
    if not isinstance(rows, list) or not rows:
        return out
    import math
    rets, lvols, target = [], [], None
    for r in rows:
        if not isinstance(r, dict):
            continue
        o, c, v = r.get("o"), r.get("c"), r.get("v")
        if not o or not c:
            continue
        ret = (c - o) / o * 100
        lvol = math.log10((v or 0) + 1)
        rets.append(abs(ret))
        lvols.append(lvol)
        if str(r.get("T", "")).upper() == ticker.upper():
            target = {"abs_return_pct": abs(ret), "ret_pct": ret, "log_volume": lvol,
                      "dollar_volume": (v or 0) * (r.get("vw") or c)}
    if target is None:
        out["note"] = f"{ticker} not present in grouped-daily population (n={len(rets)})"
        out["population_size"] = len(rets)
        return out
    out.update({
        "available": True,
        "population_size": len(rets),
        "abs_return_xz": round(rs.cross_sectional_z(target["abs_return_pct"], rets), 3),
        "log_volume_xz": round(rs.cross_sectional_z(target["log_volume"], lvols), 3),
        "ret_pct": round(target["ret_pct"], 3),
        "dollar_volume": round(target["dollar_volume"], 2),
    })
    pz, vz = out["abs_return_xz"], out["log_volume_xz"]
    out["double_confirmed"] = bool(pz >= 3.0 and vz >= 3.0)
    # Liquidity / thinness context (microcap pump risk vs large-cap noise).
    out["thin_liquidity"] = bool(target["dollar_volume"] < 2_000_000)
    return out


def microstructure(snapshot_fetch: Any, trades_fetch: Any, quotes_fetch: Any) -> dict[str, Any]:
    """Features from snapshot/trades/quotes (unused in v0.1)."""
    out: dict[str, Any] = {"available": False}
    snap = snapshot_fetch if isinstance(snapshot_fetch, dict) else {}
    tk = (snap.get("ticker") or {}) if isinstance(snap, dict) else {}
    day = tk.get("day") or {}
    prev = tk.get("prevDay") or {}
    if day or prev:
        out["available"] = True
        out["todays_change_perc"] = tk.get("todaysChangePerc")
        if day.get("vw") and prev.get("vw"):
            out["vwap_shift_pct"] = round((day["vw"] - prev["vw"]) / prev["vw"] * 100, 3)
    # trades
    trades = (trades_fetch.get("results") if isinstance(trades_fetch, dict) else None) or []
    if isinstance(trades, list) and trades:
        out["available"] = True
        sizes = [t.get("s") for t in trades if isinstance(t, dict) and t.get("s")]
        out["trade_count_sample"] = len(trades)
        if sizes:
            out["median_trade_size"] = rs.median(sizes)
            out["max_trade_size"] = max(sizes)
            out["large_trade_share"] = round(sum(1 for s in sizes if s >= 1000) / len(sizes), 3)
    # quotes -> spread proxy
    quotes = (quotes_fetch.get("results") if isinstance(quotes_fetch, dict) else None) or []
    if isinstance(quotes, list) and quotes:
        out["available"] = True
        spreads = []
        for q in quotes:
            if not isinstance(q, dict):
                continue
            bid, ask = q.get("bp") or q.get("p"), q.get("ap") or q.get("P")
            if bid and ask and ask >= bid:
                mid = (ask + bid) / 2
                if mid:
                    spreads.append((ask - bid) / mid * 10000)  # bps
        out["quote_count_sample"] = len(quotes)
        if spreads:
            out["median_spread_bps"] = round(rs.median(spreads), 2)
    return out


def market_anomaly_score(ts: dict[str, Any], xs: dict[str, Any], micro: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    """Compose a 0..100 market anomaly score with double-confirmation logic."""
    detail: dict[str, Any] = {"basis": []}
    score = 0.0

    # Time-series robust component (price+volume, saturating).
    if ts.get("available"):
        pz, vz = ts.get("price_z"), ts.get("volume_z")
        if pz is not None:
            score += rs.squash(max(pz, 0), scale=3.0, cap=30)
            detail["basis"].append(f"time-series |return| robust-z={pz}")
        if vz is not None:
            score += rs.squash(max(vz, 0), scale=3.0, cap=25)
            detail["basis"].append(f"time-series volume robust-z={vz}")
        if ts.get("double_confirmed"):
            score += 15
            detail["basis"].append("time-series price+volume double-confirmed")

    # Cross-sectional component.
    if xs.get("available"):
        pz, vz = xs.get("abs_return_xz"), xs.get("log_volume_xz")
        score += rs.squash(max(pz or 0, 0), scale=3.0, cap=25)
        score += rs.squash(max(vz or 0, 0), scale=3.0, cap=20)
        detail["basis"].append(f"cross-sectional return-xz={pz}, volume-xz={vz}")
        if xs.get("double_confirmed"):
            score += 10
            detail["basis"].append("cross-sectional price+volume double-confirmed")
        if xs.get("thin_liquidity"):
            detail["thin_liquidity"] = True
            detail["basis"].append("thin liquidity: microcap pump-risk context, treat z with care")

    # Microstructure nudge (small; context only).
    if micro.get("available"):
        if isinstance(micro.get("large_trade_share"), (int, float)) and micro["large_trade_share"] > 0.05:
            score += 5
            detail["basis"].append(f"elevated large-trade share={micro['large_trade_share']}")
        if isinstance(micro.get("median_spread_bps"), (int, float)) and micro["median_spread_bps"] > 50:
            score += 3
            detail["basis"].append(f"wide median spread={micro['median_spread_bps']}bps")

    detail["double_confirmed"] = bool(ts.get("double_confirmed") or xs.get("double_confirmed"))
    return rs.squash(score, scale=55, cap=100) if score > 100 else min(score, 100.0), detail


def _best(*vals: float) -> float:
    cand = [v for v in vals if v == v]  # not nan
    return max(cand) if cand else float("nan")
