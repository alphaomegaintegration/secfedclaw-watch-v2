#!/usr/bin/env python3
"""Train the SECFEDCLAW v0.2 gradient-boosted review-priority model.

Training data = operator labels from the calibration ledger (real, preferred) +
an optional bootstrap from the synthetic backtest corpus (clearly labeled as
synthetic) so the model is usable before many real labels accrue. Cross-validated
AUC is reported. If too few labeled, two-class samples exist, the model ABSTAINS
(writes abstain=True) and the interpretable rules engine remains primary.

  python3 train_model.py                 # ledger + synthetic bootstrap
  python3 train_model.py --no-bootstrap  # ledger labels only
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import model as M
import ledger as L
import scoring_v2
import backtest


def _bootstrap_samples(n_per_class: int, seed: int):
    """Score synthetic windows -> (feature_vector, y) pairs.

    Price/volume (and therefore liquidity class) are randomized INDEPENDENTLY of
    the label, so the model must learn from genuine anomaly / coordination /
    social signal rather than a leaky class proxy. The discriminator across
    labels is: pump = coordinated promo + price/volume spike (+reversal);
    benign_news = a real spike with NO coordination; control = routine/flat.
    """
    import random
    bt = backtest
    none = bt._F("none", None, mode="unavailable")
    X, y = [], []
    rng = random.Random(seed)
    for label in ("pump", "benign_news", "control"):
        for i in range(n_per_class):
            ticker = f"{label[:2].upper()}{i:03d}"
            base_price = rng.choice([0.5, 1.5, 6.0, 25.0, 90.0, 180.0])
            daily_vol = rng.choice([6e5, 4e6, 2.5e7, 1.5e8])
            if label == "pump":
                spike = rng.uniform(0.30, 0.90); vol_mult = rng.uniform(8, 30)
                x = bt._promo_posts(max(4, int(rng.uniform(4, 12))), ticker, coordinated=True, rng=rng)
                reversal = True
            elif label == "benign_news":
                spike = rng.uniform(0.06, 0.20); vol_mult = rng.uniform(2, 4)
                x = bt._promo_posts(rng.randint(0, 4), ticker, coordinated=(rng.random() < 0.15), rng=rng)
                reversal = False
            else:
                spike = 0.0; vol_mult = 1.0
                x = bt._promo_posts(rng.randint(0, 3), ticker, coordinated=False, rng=rng)
                reversal = False
            daily = bt._daily_baseline(40, base_price, daily_vol, rng, spike=spike,
                                       vol_mult=vol_mult, reversal=reversal)
            grouped = bt._grouped_with(ticker, spike, vol_mult > 6.0, rng)
            fetches = {
                "daily_range": bt._F("d", daily), "grouped": bt._F("g", grouped),
                "snapshot": none, "trades": none, "quotes": none,
                "x": bt._F("x", x), "reddit": none, "reddit_unavailable": True,
                "stocktwits": none, "otc_threshold": none, "reg_sho": none,
                "halts": none, "submissions": none, "edgar": none,
            }
            pkg = scoring_v2.build_package(ticker, fetches)
            X.append(M.feature_vector(pkg))
            y.append(1 if label == "pump" else 0)
    return X, y


def main() -> int:
    ap = argparse.ArgumentParser(description="Train SECFEDCLAW review-priority GBM")
    ap.add_argument("--no-bootstrap", action="store_true", help="use only real ledger labels")
    ap.add_argument("--boot-n", type=int, default=60, help="synthetic samples per class")
    ap.add_argument("--seed", type=int, default=20260603)
    ap.add_argument("--out", default=str(M.MODEL_PATH))
    args = ap.parse_args()

    rows = L.load_labels()
    Xr, yr = L.to_xy(rows)
    Xb, yb = ([], [])
    if not args.no_bootstrap:
        Xb, yb = _bootstrap_samples(args.boot_n, args.seed)
    X = Xr + Xb
    y = yr + yb

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    n_pos = sum(1 for v in y if v == 1)
    n_neg = sum(1 for v in y if v == 0)
    meta = {
        "model_version": "gbm_v1",
        "trained_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "feature_names": M.FEATURE_NAMES,
        "n_total": len(y), "n_real_labels": len(yr), "n_bootstrap": len(yb),
        "n_positive": n_pos, "n_negative": n_neg,
        "guardrail": "Advisory calibrated review-priority probability only; not a guilt/fraud label or trading signal.",
    }

    if len(y) < M.MIN_LABELS or n_pos < M.MIN_PER_CLASS or n_neg < M.MIN_PER_CLASS:
        meta.update({"abstain": True,
                     "reason": f"insufficient labeled two-class data "
                               f"(have {len(y)}; need >= {M.MIN_LABELS}, >= {M.MIN_PER_CLASS}/class)"})
        out.write_text(json.dumps(meta, indent=2) + "\n")
        print(json.dumps({"abstain": True, **{k: meta[k] for k in ("n_total", "n_real_labels", "reason")}}, indent=2))
        return 0

    cv_auc = M.kfold_auc(X, y, k=5)
    gbm = M.GradientBoosting().fit(X, y)
    full = {**meta, "abstain": False, "cv_auc": round(cv_auc, 4), **gbm.to_dict()}
    out.write_text(json.dumps(full, indent=2) + "\n")
    imp = sorted(zip(M.FEATURE_NAMES, gbm.importances), key=lambda t: -t[1])[:6]
    print(f"\nSECFEDCLAW review-priority GBM trained — n={len(y)} "
          f"(real={len(yr)}, bootstrap={len(yb)}), 5-fold AUC={cv_auc:.3f}")
    print("top features:", ", ".join(f"{k}={v:.2f}" for k, v in imp))
    print("model:", out)
    print("NOTE: advisory probability for triage only; rules engine stays primary; not guilt or a trading signal.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
