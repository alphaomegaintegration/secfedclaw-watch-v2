#!/usr/bin/env python3
"""SECFEDCLAW v0.2 backtest / calibration harness.

Measures whether the v0.2 WATCH scorer would have *raised review priority* on
pump-and-dump-style windows while staying quiet on benign-news spikes and
routine activity. It does NOT label fraud; the target is review-priority
calibration (precision/recall of "flag for human review"), exactly as the
design doc requires.

Two corpora:

  1. REAL SEC CASE CORPUS  (`sec_cases()`) — public, officially described
     pump/ramp-and-dump matters. Metadata + source URLs only; tickers/windows
     are filled in for a LIVE run (Polygon daily range via DataConnector) and
     left blank otherwise so nothing is fabricated.

  2. SYNTHETIC LABELED CORPUS (`synthetic_corpus()`) — randomized, seeded
     case/control windows that are runnable offline so precision/recall is
     computable immediately and deterministically:
        * pump            : coordinated promo posts + price/volume ramp (+reversal)
        * benign_news      : real price/volume move, NO coordination/promo (legit)
        * control          : routine / flat behaviour
     Signal intensity is randomized so weak pumps can be missed and noisy
     benign windows can be flagged — yielding a realistic, non-trivial
     confusion matrix.

A window is "flagged" when review_priority >= MEDIUM. Positives = pump.
Negatives = benign_news + control.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import scoring_v2  # noqa: E402
from config import ALGORITHM_VERSION, FINDING_CEILING  # noqa: E402

PRIORITY_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL_REVIEW": 3}


# --------------------------------------------------------------------------- #
# Real public SEC case corpus (metadata only; not new findings; allegations
# unless final judgment). Fill tickers/windows for a live Polygon-backed run.
# --------------------------------------------------------------------------- #
def sec_cases() -> list[dict[str, Any]]:
    return [
        {"case_id": "sec-2021-214-gallagher-twitter",
         "url": "https://www.sec.gov/newsroom/press-releases/2021-214",
         "pattern": "Single Twitter promoter; secret accumulation, promote, undisclosed selling.",
         "tickers": [], "window": None},
        {"case_id": "sec-2022-221-social-influencers",
         "url": "https://www.sec.gov/newsroom/press-releases/2022-221",
         "pattern": "Twitter/Discord influencer coordinated promotion + undisclosed disposal.",
         "tickers": [], "window": None},
        {"case_id": "sec-2014-256-newsletter-microcap",
         "url": "https://www.sec.gov/newsroom/press-releases/2014-256",
         "pattern": "Newsletter penny-stock promotion; control blocks, inflated demand, dumping.",
         "tickers": [], "window": None},
        {"case_id": "sec-2022-62-offshore-nominee",
         "url": "https://www.sec.gov/newsroom/press-releases/2022-62",
         "pattern": "Offshore nominee control + funded promotion + dumping into demand.",
         "tickers": [], "window": None},
    ]


# --------------------------------------------------------------------------- #
# Synthetic data factory
# --------------------------------------------------------------------------- #
@dataclass
class _F:
    """Minimal Fetch-compatible object for the scorer."""
    name: str
    data: Any
    mode: str = "synthetic"
    status: int = 200
    artifact_path: str | None = None
    sha256: str | None = None
    source_url_redacted: str | None = None
    def ok(self) -> bool:
        return self.data is not None


def _daily_baseline(n: int, base_price: float, daily_vol: float, rng: random.Random,
                    spike: float = 0.0, vol_mult: float = 1.0, reversal: bool = False) -> dict:
    """n flat-ish days, optional spike (pct) + volume multiplier on last day."""
    res = []
    price = base_price
    for i in range(n):
        drift = rng.uniform(-0.012, 0.012)
        o = price
        c = price * (1 + drift)
        v = daily_vol * rng.uniform(0.7, 1.3)
        if i == n - 1 and spike:
            c = price * (1 + spike)
            v = daily_vol * vol_mult
        res.append({"o": round(o, 4), "c": round(c, 4),
                    "h": round(max(o, c) * 1.01, 4), "l": round(min(o, c) * 0.99, 4),
                    "v": int(v), "vw": round((o + c) / 2, 4), "n": int(v / 90),
                    "t": 1700000000000 + i * 86400000})
        price = c
    if reversal:
        res[-1]["c"] = round(res[-1]["o"] * (1 + spike * 0.3), 4)  # partial intraday give-back
    return {"results": res}


def _grouped_with(ticker: str, abs_ret: float, log_vol_extreme: bool, rng: random.Random) -> dict:
    pop = [{"T": f"N{i}", "o": 10.0, "c": 10.0 * (1 + rng.uniform(-0.02, 0.02)),
            "v": int(1_000_000 * rng.uniform(0.5, 1.5)), "vw": 10} for i in range(300)]
    v = 20_000_000 if log_vol_extreme else 1_200_000
    pop.insert(0, {"T": ticker, "o": 1.0, "c": round(1.0 * (1 + abs_ret), 4), "v": v, "vw": 1.1})
    return {"results": pop}


def _promo_posts(n: int, ticker: str, coordinated: bool, rng: random.Random) -> dict:
    base = f"${ticker} guaranteed moon rocket must buy now join telegram free signals 100x"
    posts = []
    t0 = 1700000000
    for i in range(n):
        if coordinated:
            text = base + (" " + rng.choice(["go go go", "last chance", "do not miss"]))
        else:
            text = rng.choice([
                f"${ticker} earnings looked fine, holding long term",
                f"thoughts on ${ticker} after the product news?",
                f"${ticker} chart looks like a normal pullback to me",
            ])
        posts.append({"id": f"{ticker}{i}", "text": text,
                      "created_at": _iso(t0 + i * (120 if coordinated else 9000)),
                      "author_id": (f"a{i % 2}" if coordinated else f"u{i}"),
                      "public_metrics": {"like_count": rng.randint(0, 8)}})
    return {"data": posts}


def _iso(epoch: int) -> str:
    import datetime as dt
    return dt.datetime.fromtimestamp(epoch, dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _fetches(label: str, ticker: str, rng: random.Random) -> dict[str, Any]:
    none = _F("none", None, mode="unavailable")
    if label == "pump":
        intensity = rng.uniform(0.5, 1.0)            # some weak pumps -> possible misses
        spike = rng.uniform(0.25, 0.9) * intensity + 0.15
        vol_mult = rng.uniform(8, 30) * intensity
        n_posts = max(3, int(rng.uniform(4, 12) * intensity))
        daily = _daily_baseline(40, 1.0, 1_000_000, rng, spike=spike, vol_mult=vol_mult, reversal=True)
        grouped = _grouped_with(ticker, spike, vol_mult > 5_000_000 / 1_200_000, rng)
        x = _promo_posts(n_posts, ticker, coordinated=True, rng=rng)
    elif label == "benign_news":
        spike = rng.uniform(0.06, 0.20)              # real move, modest
        daily = _daily_baseline(40, 25.0, 5_000_000, rng, spike=spike, vol_mult=rng.uniform(2, 4))
        grouped = _grouped_with(ticker, spike, False, rng)
        # occasional incidental chatter (noise that may cause a false positive)
        x = _promo_posts(rng.randint(0, 4), ticker, coordinated=(rng.random() < 0.15), rng=rng)
    else:  # control
        daily = _daily_baseline(40, 50.0, 8_000_000, rng, spike=0.0)
        grouped = _grouped_with(ticker, rng.uniform(0.0, 0.02), False, rng)
        x = _promo_posts(rng.randint(0, 3), ticker, coordinated=False, rng=rng)
    return {
        "daily_range": _F("daily", daily), "grouped": _F("grouped", grouped),
        "snapshot": none, "trades": none, "quotes": none,
        "x": _F("x", x), "reddit": none, "reddit_unavailable": True,
        "otc_threshold": none, "reg_sho": none, "halts": none, "submissions": none,
    }


def _class_balanced_sample(label: str, ticker: str, rng) -> dict[str, Any]:
    """Build fetches with price/volume (hence liquidity class) randomized
    INDEPENDENTLY of the label, so per-class precision/recall is meaningful."""
    none = _F("none", None, mode="unavailable")
    base_price = rng.choice([0.5, 1.5, 6.0, 25.0, 90.0, 180.0])
    daily_vol = rng.choice([6e5, 4e6, 2.5e7, 1.5e8])
    if label == "pump":
        spike = rng.uniform(0.30, 0.90); vol_mult = rng.uniform(8, 30)
        x = _promo_posts(max(4, int(rng.uniform(4, 12))), ticker, coordinated=True, rng=rng); rev = True
    elif label == "benign_news":
        spike = rng.uniform(0.06, 0.20); vol_mult = rng.uniform(2, 4)
        x = _promo_posts(rng.randint(0, 4), ticker, coordinated=(rng.random() < 0.15), rng=rng); rev = False
    else:
        spike = 0.0; vol_mult = 1.0
        x = _promo_posts(rng.randint(0, 3), ticker, coordinated=False, rng=rng); rev = False
    daily = _daily_baseline(40, base_price, daily_vol, rng, spike=spike, vol_mult=vol_mult, reversal=rev)
    grouped = _grouped_with(ticker, spike, vol_mult > 6.0, rng)
    return {"daily_range": _F("d", daily), "grouped": _F("g", grouped),
            "snapshot": none, "trades": none, "quotes": none, "x": _F("x", x),
            "reddit": none, "reddit_unavailable": True, "stocktwits": none,
            "otc_threshold": none, "reg_sho": none, "halts": none, "submissions": none,
            "edgar": none, "litigation": none}


def per_class_breakdown(n_per_class: int, seed: int, threshold: str) -> dict[str, Any]:
    """Precision/recall by liquidity class on a class-balanced synthetic corpus."""
    import random
    thr = PRIORITY_RANK[threshold]
    rng = random.Random(seed ^ 0x5EC)
    by: dict[str, dict[str, int]] = {}
    for label in ("pump", "benign_news", "control"):
        for i in range(n_per_class):
            ticker = f"{label[:2].upper()}{i:03d}"
            pkg = scoring_v2.build_package(ticker, _class_balanced_sample(label, ticker, rng))
            cls = (pkg.get("security_class") or {}).get("class", "unknown")
            d = by.setdefault(cls, {"tp": 0, "fp": 0, "tn": 0, "fn": 0})
            flagged = PRIORITY_RANK[pkg["review_priority"]] >= thr
            pos = label == "pump"
            if pos and flagged: d["tp"] += 1
            elif pos and not flagged: d["fn"] += 1
            elif not pos and flagged: d["fp"] += 1
            else: d["tn"] += 1
    out = {}
    for cls, c in by.items():
        p = c["tp"] / (c["tp"] + c["fp"]) if (c["tp"] + c["fp"]) else 0.0
        r = c["tp"] / (c["tp"] + c["fn"]) if (c["tp"] + c["fn"]) else 0.0
        f1 = 2 * p * r / (p + r) if (p + r) else 0.0
        out[cls] = {**c, "precision": round(p, 3), "recall": round(r, 3), "f1": round(f1, 3),
                    "n": sum(c.values())}
    return out


def synthetic_corpus(n_per_class: int, seed: int) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    corpus = []
    for label in ("pump", "benign_news", "control"):
        for i in range(n_per_class):
            corpus.append({"label": label, "ticker": f"{label[:2].upper()}{i:03d}", "rng_seed": rng.randint(0, 1 << 30)})
    return corpus


# --------------------------------------------------------------------------- #
# Evaluation
# --------------------------------------------------------------------------- #
def run(n_per_class: int, seed: int, threshold: str) -> dict[str, Any]:
    corpus = synthetic_corpus(n_per_class, seed)
    thr = PRIORITY_RANK[threshold]
    rows = []
    tp = fp = tn = fn = 0
    ledger = {"useful_watch": 0, "benign_explained": 0, "false_positive": 0,
              "insufficient_evidence": 0, "missed_event": 0}
    by_priority: dict[str, int] = {}
    for item in corpus:
        rng = random.Random(item["rng_seed"])
        fetches = _fetches(item["label"], item["ticker"], rng)
        pkg = scoring_v2.build_package(item["ticker"], fetches)
        flagged = PRIORITY_RANK[pkg["review_priority"]] >= thr
        positive = item["label"] == "pump"
        by_priority[pkg["review_priority"]] = by_priority.get(pkg["review_priority"], 0) + 1
        if positive and flagged:
            tp += 1; ledger["useful_watch"] += 1
        elif positive and not flagged:
            fn += 1; ledger["missed_event"] += 1
        elif not positive and flagged:
            fp += 1; ledger["false_positive"] += 1
        else:
            tn += 1
            ledger["benign_explained" if item["label"] == "benign_news" else "insufficient_evidence"] += 1
        rows.append({"ticker": item["ticker"], "label": item["label"],
                     "review_priority": pkg["review_priority"], "watch_score": pkg["watch_score"],
                     "anomaly_evidence_score": pkg["anomaly_evidence_score"],
                     "n_families_active": pkg["corroboration"]["n_families_active"],
                     "flagged": flagged})

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    accuracy = (tp + tn) / max(len(corpus), 1)
    return {
        "algorithm_version": ALGORITHM_VERSION,
        "finding_ceiling": FINDING_CEILING,
        "harness": "synthetic_labeled_v1",
        "flag_threshold": threshold,
        "n_samples": len(corpus),
        "n_per_class": n_per_class,
        "seed": seed,
        "confusion_matrix": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
        "metrics": {"precision": round(precision, 3), "recall": round(recall, 3),
                    "f1": round(f1, 3), "accuracy": round(accuracy, 3)},
        "priority_distribution": by_priority,
        "calibration_ledger": ledger,
        "per_class": per_class_breakdown(n_per_class, seed, threshold),
        "sec_case_corpus": sec_cases(),
        "rows": rows,
        "limitations": [
            "Synthetic corpus calibrates the scorer's review-priority behaviour; it is not evidence about any real issuer.",
            "Real SEC cases are public allegations unless final judgment; tickers/windows must be supplied for a live Polygon-backed run.",
            "Flagging means 'raise for human review', never 'fraud' or a trading signal.",
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="SECFEDCLAW v0.2 backtest / calibration harness")
    ap.add_argument("--n", type=int, default=40, help="samples per class")
    ap.add_argument("--seed", type=int, default=20260602)
    ap.add_argument("--threshold", choices=list(PRIORITY_RANK), default="MEDIUM")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent / "out" / "backtest_results.json"))
    args = ap.parse_args()
    result = run(args.n, args.seed, args.threshold)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, default=str) + "\n")

    m = result["metrics"]; cm = result["confusion_matrix"]
    print(f"\nSECFEDCLAW v0.2 backtest — {result['n_samples']} windows "
          f"({result['n_per_class']}/class), flag>= {result['flag_threshold']}")
    print("=" * 64)
    print(f"  precision {m['precision']:.3f}   recall {m['recall']:.3f}   "
          f"F1 {m['f1']:.3f}   accuracy {m['accuracy']:.3f}")
    print(f"  TP {cm['tp']}  FP {cm['fp']}  TN {cm['tn']}  FN {cm['fn']}")
    print(f"  priority distribution: {result['priority_distribution']}")
    print("  per-class (class-balanced):")
    for cls, c in result["per_class"].items():
        print(f"    {cls:<14} P {c['precision']:.2f}  R {c['recall']:.2f}  F1 {c['f1']:.2f}  (n={c['n']})")
    print(f"  results: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
