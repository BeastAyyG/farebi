"""Phase-07 prototype: fuse the five KEEP signals with LR + isotonic + band.

Reads the wide feature matrix from ``extract_quick_features.py`` and, per
source-group-held-out fold (same ``split_indices`` the harness uses):

* fits StandardScaler + LogisticRegression on the train fold,
* fits IsotonicRegression on the train fold's predicted scores (in-sample fit
  — mildly optimistic calibration, noted in the report, honest for a probe),
* reports raw and calibrated AUC on the held-out fold plus the Brier score,
* builds a conformal-style band from train-fold calibrated scores (5th
  percentile of fake scores, 95th of real scores) and reports the test-fold
  uncertain rate and conditional error rates outside the band.

Writes JSON to ``reports/fusion_probe_quick256.json``. Prototype only: the
production L5 fusion will use nested calibration splits and full-res data.

Usage:
    .venv/Scripts/python.exe scripts/train_fusion_probe.py \
        --features data/interim/quick_features.csv
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.preprocessing import StandardScaler

from farebi.core.logging import configure_logging
from farebi.harness.splits import split_indices


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", type=Path, default=Path("data/interim/quick_features.csv"))
    ap.add_argument("--out", type=Path, default=Path("reports/fusion_probe_quick256.json"))
    ap.add_argument("--n-splits", type=int, default=2)
    ap.add_argument("--seed", type=int, default=1337)
    args = ap.parse_args()

    configure_logging(level="INFO", json_logs=False)
    frame = pd.read_csv(args.features)
    meta = ["sample_id", "label", "source_group"]
    feat_cols = [c for c in frame.columns if c not in meta]
    design = frame[feat_cols].to_numpy(dtype=np.float64)
    y = frame["label"].to_numpy(dtype=np.int64)
    groups = frame["source_group"].tolist()

    folds = split_indices(groups, y, n_splits=args.n_splits, seed=args.seed)
    fold_rows = []
    for fold in folds:
        tr, te = fold.train_idx, fold.test_idx
        if te.size == 0 or y[te].min() == y[te].max():
            continue
        scaler = StandardScaler().fit(design[tr])
        clf = LogisticRegression(max_iter=5000).fit(scaler.transform(design[tr]), y[tr])
        p_train = clf.predict_proba(scaler.transform(design[tr]))[:, 1]
        p_test = clf.predict_proba(scaler.transform(design[te]))[:, 1]
        iso = IsotonicRegression(out_of_bounds="clip").fit(p_train, y[tr])
        c_test = iso.predict(p_test)
        c_train = iso.predict(p_train)
        q_lo = float(np.percentile(c_train[y[tr] == 1], 5))
        q_hi = float(np.percentile(c_train[y[tr] == 0], 95))
        certain = (c_test < q_lo) | (c_test > q_hi)
        wrong = ((c_test > 0.5).astype(int) != y[te]) & certain
        fold_rows.append(
            {
                "held_out": sorted({groups[i] for i in te.tolist()}),
                "n_train": int(tr.size),
                "n_test": int(te.size),
                "auc_raw": float(roc_auc_score(y[te], p_test)),
                "auc_cal": float(roc_auc_score(y[te], c_test)),
                "brier_raw": float(brier_score_loss(y[te], p_test)),
                "brier_cal": float(brier_score_loss(y[te], c_test)),
                "q_lo": q_lo,
                "q_hi": q_hi,
                "uncertain_rate": float(1.0 - certain.mean()),
                "error_given_certain": float(wrong.sum() / max(int(certain.sum()), 1)),
            }
        )

    summary = {
        "dataset": str(args.features),
        "n_samples": len(frame),
        "n_features": len(feat_cols),
        "features": feat_cols,
        "mean_auc_raw": float(np.mean([f["auc_raw"] for f in fold_rows])),
        "mean_auc_cal": float(np.mean([f["auc_cal"] for f in fold_rows])),
        "mean_uncertain_rate": float(np.mean([f["uncertain_rate"] for f in fold_rows])),
        "mean_error_given_certain": float(np.mean([f["error_given_certain"] for f in fold_rows])),
        "notes": [
            "isotonic fit in-sample on train fold: calibration mildly optimistic.",
            "one held-out group per side per fold (GroupKFold by source): directional only.",
            "compare against the per-signal harness AUCs in the probe report.",
        ],
        "folds": fold_rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "folds"}, indent=2))
    for f in fold_rows:
        print(
            f"  held_out={f['held_out']} auc_raw={f['auc_raw']:.3f} "
            f"auc_cal={f['auc_cal']:.3f} uncertain={f['uncertain_rate']:.2f} "
            f"err|certain={f['error_given_certain']:.3f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
