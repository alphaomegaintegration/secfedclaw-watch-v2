#!/usr/bin/env python3
"""Operator labeling CLI for the SECFEDCLAW calibration ledger.

Record outcome labels on review packages so the gradient-boosted model can learn
which WATCH packages were genuinely worth review. This is the human-in-the-loop
feedback that closes the loop when running live.

  python3 label.py out/AAPL_..._watch_v2.json useful_watch --note "promoter selling"
  python3 label.py out/XYZ_..._watch_v2.json false_positive
  python3 label.py --summary
  python3 label.py --list-labels
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger as L


def main() -> int:
    ap = argparse.ArgumentParser(description="Label review packages for the calibration ledger")
    ap.add_argument("package", nargs="?", help="path to a *_watch_v2.json review package")
    ap.add_argument("label", nargs="?", choices=sorted(L.VALID), help="outcome label")
    ap.add_argument("--note", default="", help="optional reviewer note")
    ap.add_argument("--summary", action="store_true", help="print ledger summary")
    ap.add_argument("--list-labels", action="store_true", help="list valid labels and meaning")
    args = ap.parse_args()

    if args.list_labels:
        print("Positive (y=1, review-worthy):  " + ", ".join(sorted(L.POSITIVE)))
        print("Negative (y=0, not worth review): " + ", ".join(sorted(L.NEGATIVE)))
        return 0
    if args.summary:
        print(json.dumps(L.summary(), indent=2))
        return 0
    if not (args.package and args.label):
        ap.error("provide PACKAGE and LABEL, or use --summary / --list-labels")

    pkg_path = Path(args.package)
    if not pkg_path.exists():
        print(f"package not found: {pkg_path}")
        return 2
    package = json.loads(pkg_path.read_text())
    row = L.add_label(package, args.label, note=args.note)
    print(json.dumps({"recorded": True, "ticker": row["ticker"], "label": row["label"],
                      "y": row["y"], "ledger": str(L.LEDGER_PATH)}, indent=2))
    s = L.summary()
    print(f"ledger now: {s['n_labels']} labels ({s['n_positive']} pos / {s['n_negative']} neg). "
          f"Retrain with: python3 train_model.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
