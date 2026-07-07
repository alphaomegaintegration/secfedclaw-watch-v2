#!/usr/bin/env python3
"""Calibration label ledger for SECFEDCLAW v0.2.

Records operator outcome labels on review packages so the system can learn which
WATCH packages were genuinely worth review. This is the human-in-the-loop signal
the design doc calls for; it never auto-escalates anything externally.

Labels (operator-assigned after reviewing a package):
  useful_watch        -> y=1  (genuinely review-worthy)
  missed_event        -> y=1  (should have been flagged higher)
  false_positive      -> y=0  (flagged but benign)
  benign_explained    -> y=0  (explained by legitimate catalyst)
  insufficient_evidence-> y=0 (not enough to warrant review)

Stored as JSONL at out/ledger/labels.jsonl with the package's feature vector so
the model can train directly from it.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from model import feature_vector  # noqa: E402
import threading

LEDGER_PATH = Path(__file__).resolve().parent / "out" / "ledger" / "labels.jsonl"
POSITIVE = {"useful_watch", "missed_event"}
NEGATIVE = {"false_positive", "benign_explained", "insufficient_evidence"}
VALID = POSITIVE | NEGATIVE


_APPEND_LOCK = threading.Lock()  # serialize JSONL appends (threaded serve.py)

def label_to_y(label: str) -> int | None:
    if label in POSITIVE:
        return 1
    if label in NEGATIVE:
        return 0
    return None


def add_label(package: dict[str, Any], label: str, note: str = "",
              path: Path | None = None) -> dict[str, Any]:
    if label not in VALID:
        raise ValueError(f"label must be one of {sorted(VALID)}")
    p = path or LEDGER_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "ticker": package.get("ticker"),
        "source_run": package.get("source_run_id") or package.get("generated_utc"),
        "label": label, "y": label_to_y(label), "note": note,
        "review_priority": package.get("review_priority"),
        "features": feature_vector(package),
    }
    with _APPEND_LOCK:
        with p.open("a") as f:
            f.write(json.dumps(row, default=str) + "\n")
    return row


def load_labels(path: Path | None = None) -> list[dict[str, Any]]:
    p = path or LEDGER_PATH
    if not p.exists():
        return []
    rows = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def to_xy(rows: list[dict[str, Any]]):
    X = [r["features"] for r in rows if r.get("features") and r.get("y") in (0, 1)]
    y = [r["y"] for r in rows if r.get("features") and r.get("y") in (0, 1)]
    return X, y


def summary(path: Path | None = None) -> dict[str, Any]:
    rows = load_labels(path)
    counts: dict[str, int] = {}
    for r in rows:
        counts[r.get("label", "?")] = counts.get(r.get("label", "?"), 0) + 1
    return {"n_labels": len(rows), "by_label": counts,
            "n_positive": sum(1 for r in rows if r.get("y") == 1),
            "n_negative": sum(1 for r in rows if r.get("y") == 0)}
