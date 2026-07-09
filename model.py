#!/usr/bin/env python3
"""Gradient-boosted review-priority model for SECFEDCLAW v0.2.

A compact, dependency-light (numpy-only, no sklearn) gradient boosting
classifier over decision stumps with logistic loss. It outputs a CALIBRATED
review-priority PROBABILITY and per-feature contributions — it is explicitly an
advisory triage aid, NEVER a guilt/fraud classifier and never a trading signal.

Target label convention (see ledger.py): y=1 means "this window was genuinely
worth human review" (operator labels `useful_watch` / `missed_event`); y=0 means
not (`false_positive` / `benign_explained` / `insufficient_evidence`).

The model abstains (stays out of the way of the interpretable rules engine)
until enough labeled, two-class data exists.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from config import output_root

MODEL_PATH = output_root() / "model" / "model.json"
MIN_LABELS = 40          # minimum labeled samples before the model is usable
MIN_PER_CLASS = 8

# Fixed feature order extracted from a scored package.
FEATURE_NAMES = [
    "market_anomaly_score", "coordination_score", "market_structure_score",
    "issuer_event_score", "halt_regulatory_score", "issuer_context_score",
    "social_issuer_specific_burst", "social_promotional_noise",
    "anomaly_evidence_score", "evidence_quality_score",
    "n_families_active", "n_platforms", "bullish_ratio", "class_ordinal",
]
_CLASS_ORD = {"thin_microcap": 0, "small_cap": 1, "mid_cap": 2, "large_cap": 3, "unknown": 2}


def feature_vector(package: dict[str, Any]) -> list[float]:
    cs = package.get("component_scores", {})
    sm = package.get("social_metrics", {})
    sent = (sm.get("sentiment") or {})
    cls = (package.get("security_class") or {}).get("class", "unknown")
    return [
        float(cs.get("market_anomaly_score", 0)), float(cs.get("coordination_score", 0)),
        float(cs.get("market_structure_score", 0)), float(cs.get("issuer_event_score", 0)),
        float(cs.get("halt_regulatory_score", 0)), float(cs.get("issuer_context_score", 0)),
        float(cs.get("social_issuer_specific_burst", 0)), float(cs.get("social_promotional_noise", 0)),
        float(package.get("anomaly_evidence_score", 0)), float(package.get("evidence_quality_score", 0)),
        float((package.get("corroboration") or {}).get("n_families_active", 0)),
        float(sm.get("n_platforms", 0)), float(sent.get("bullish_ratio") or 0.0),
        float(_CLASS_ORD.get(cls, 2)),
    ]


def _sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


class GradientBoosting:
    """Logistic gradient boosting over decision stumps (depth-1 trees)."""

    def __init__(self, n_estimators: int = 60, learning_rate: float = 0.2,
                 n_thresholds: int = 12, min_leaf: int = 3):
        self.n_estimators = n_estimators
        self.lr = learning_rate
        self.n_thresholds = n_thresholds
        self.min_leaf = min_leaf
        self.f0 = 0.0
        self.stumps: list[dict] = []
        self.importances = None
        self.platt: tuple[float, float] | None = None  # (a,b) Platt scaling, if calibrated

    def _best_stump(self, X, residual):
        n, d = X.shape
        best = None
        best_gain = 0.0
        total_sse = float(np.sum((residual - residual.mean()) ** 2))
        for j in range(d):
            col = X[:, j]
            qs = np.unique(np.quantile(col, np.linspace(0.1, 0.9, self.n_thresholds)))
            for thr in qs:
                left = col <= thr
                if left.sum() < self.min_leaf or (~left).sum() < self.min_leaf:
                    continue
                lv = residual[left].mean()
                rv = residual[~left].mean()
                sse = float(np.sum((residual[left] - lv) ** 2) + np.sum((residual[~left] - rv) ** 2))
                gain = total_sse - sse
                if gain > best_gain:
                    best_gain = gain
                    best = {"feature": j, "threshold": float(thr),
                            "left": float(lv), "right": float(rv)}
        return best, best_gain

    def fit(self, X, y):
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=float)
        p = float(np.clip(y.mean(), 1e-3, 1 - 1e-3))
        self.f0 = math.log(p / (1 - p))
        F = np.full(len(y), self.f0)
        self.importances = np.zeros(X.shape[1])
        for _ in range(self.n_estimators):
            residual = y - _sigmoid(F)
            stump, gain = self._best_stump(X, residual)
            if not stump or gain <= 1e-9:
                break
            self.stumps.append(stump)
            self.importances[stump["feature"]] += gain
            col = X[:, stump["feature"]]
            upd = np.where(col <= stump["threshold"], stump["left"], stump["right"])
            F = F + self.lr * upd
        s = self.importances.sum()
        if s > 0:
            self.importances = self.importances / s
        return self

    def decision_function(self, X):
        X = np.asarray(X, dtype=float)
        F = np.full(X.shape[0], self.f0)
        for st in self.stumps:
            col = X[:, st["feature"]]
            F = F + self.lr * np.where(col <= st["threshold"], st["left"], st["right"])
        return F

    def predict_proba(self, X):
        z = self.decision_function(X)
        if self.platt is not None:          # Platt-scaled if calibrated
            a, b = self.platt
            return _sigmoid(a * z + b)
        return _sigmoid(z)

    def set_platt_from_scores(self, z, y, iters: int = 300, lr: float = 0.1):
        """Fit Platt scaling (a,b): sigmoid(a*decision + b) -> calibrated prob,
        via 1-D logistic regression. Pass OUT-OF-FOLD decision scores so the
        calibrator isn't fit on the same rows the model memorized."""
        z = np.asarray(z, dtype=float); y = np.asarray(y, dtype=float)
        if len(z) < 4 or len(np.unique(y)) < 2:
            return self                     # too little signal — leave uncalibrated
        a, b = 1.0, 0.0
        for _ in range(iters):
            p = _sigmoid(a * z + b)
            a -= lr * float(np.mean((p - y) * z))
            b -= lr * float(np.mean(p - y))
        self.platt = (float(a), float(b))
        return self

    def to_dict(self) -> dict:
        return {"f0": self.f0, "lr": self.lr, "stumps": self.stumps,
                "feature_names": FEATURE_NAMES, "platt": list(self.platt) if self.platt else None,
                "importances": (self.importances.tolist() if self.importances is not None else None)}

    @classmethod
    def from_dict(cls, d: dict) -> "GradientBoosting":
        m = cls(learning_rate=d.get("lr", 0.2))
        m.f0 = d["f0"]
        m.stumps = d["stumps"]
        pl = d.get("platt")
        m.platt = tuple(pl) if pl else None
        imp = d.get("importances")
        m.importances = np.array(imp) if imp else None
        return m


def auc(y_true, scores) -> float:
    y = np.asarray(y_true)
    s = np.asarray(scores)
    pos = s[y == 1]
    neg = s[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return 0.5
    order = np.argsort(s)
    ranks = np.empty_like(order, dtype=float)
    ranks[order] = np.arange(1, len(s) + 1)
    r_pos = ranks[y == 1].sum()
    return float((r_pos - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def kfold_auc(X, y, k: int = 5, **kw) -> float:
    X = np.asarray(X, dtype=float); y = np.asarray(y, dtype=float)
    n = len(y)
    idx = np.arange(n)
    rng = np.random.default_rng(7)
    rng.shuffle(idx)
    folds = np.array_split(idx, min(k, n))
    aucs = []
    for f in folds:
        test = np.zeros(n, dtype=bool); test[f] = True
        if len(np.unique(y[~test])) < 2 or len(np.unique(y[test])) < 2:
            continue
        m = GradientBoosting(**kw).fit(X[~test], y[~test])
        aucs.append(auc(y[test], m.predict_proba(X[test])))
    return float(np.mean(aucs)) if aucs else 0.5


def kfold_oof_decision(X, y, k: int = 5, **kw):
    """Out-of-fold decision_function scores aligned to X — each row scored by a
    model that did NOT train on it. Feeds honest Platt calibration."""
    X = np.asarray(X, dtype=float); y = np.asarray(y, dtype=float)
    n = len(y)
    idx = np.arange(n)
    rng = np.random.default_rng(7)
    rng.shuffle(idx)
    oof = np.zeros(n, dtype=float)
    got = np.zeros(n, dtype=bool)
    for f in np.array_split(idx, min(k, n)):
        test = np.zeros(n, dtype=bool); test[f] = True
        if len(np.unique(y[~test])) < 2:
            continue
        m = GradientBoosting(**kw).fit(X[~test], y[~test])
        oof[test] = m.decision_function(X[test]); got[test] = True
    return oof, got


def load_scorer():
    """Return (model_dict) if a trained model exists, else None."""
    if MODEL_PATH.exists():
        try:
            d = json.loads(MODEL_PATH.read_text())
            if not d.get("abstain"):
                return d
        except Exception:
            return None
    return None


def score_package(package: dict[str, Any], model_dict: dict) -> dict[str, Any]:
    """Advisory probability + top contributing features for a scored package."""
    m = GradientBoosting.from_dict(model_dict)
    fv = np.array([feature_vector(package)], dtype=float)
    proba = float(m.predict_proba(fv)[0])
    contribs = []
    if m.importances is not None:
        names = model_dict.get("feature_names", FEATURE_NAMES)
        vals = feature_vector(package)
        top = np.argsort(m.importances)[::-1][:4]
        contribs = [{"feature": names[i], "value": round(vals[i], 2),
                     "importance": round(float(m.importances[i]), 3)} for i in top]
    calibrated = model_dict.get("platt") is not None
    n_real = model_dict.get("n_real_labels", 0)
    kind = "Platt-calibrated" if calibrated else "uncalibrated"
    return {"review_priority_probability": round(proba, 4),
            "top_features": contribs,
            "model_version": model_dict.get("model_version", "gbm_v1"),
            "calibrated": calibrated,
            "n_real_labels": n_real,        # so a bootstrap-heavy model is legible
            "note": (f"Advisory {kind} probability for triage only (trained on {n_real} real "
                     f"labels + bootstrap); not a guilt/fraud label or trading signal.")}
