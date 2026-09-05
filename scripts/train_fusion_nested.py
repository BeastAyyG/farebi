"""Phase-07 follow-up: nested calibration splits for the fusion probe.

Same data and outer folds as ``train_fusion_probe.py`` (same ``split_indices``
with the same seed, so fold membership is identical), but the isotonic map and
the conformal-style band are fit on a HELD-OUT calibration slice of the outer
train fold instead of in-sample:

* outer train fold -> random stratified 2/3 fit + 1/3 calibration (seeded),
* StandardScaler + LogisticRegression on fit,
* IsotonicRegression on calibration predicted scores,
* q_lo / q_hi band edges from calibration scores,
* all metrics reported on the untouched outer test fold.

One honesty caveat, stated in the report: the inner fit/cal split is random,
not by source group (the outer train fold only holds one real and one fake
group, so a group-wise inner split would leave an empty fit or cal side).
Group leakage into the calibration slice only touches the 1-D monotonic map,
never the LR weights — acceptable for a probe, and the production L5 fusion
will use fully nested group splits once more source groups exist.

Comparability note: AUC numbers here are directly comparable to
``reports/fusion_probe_quick256.json`` — same rows, same outer folds. Only the
calibration discipline changes, so any move in uncertain rate or
error|certain isolates the optimism of the in-sample isotonic fit.

Usage:
    .venv/Scripts/python.exe scripts/train_fusion_nested.py \
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
from sklearn.model_selection import StratifiedShuffleSplit
from sklearn.preprocessing import StandardScaler

from farebi.core.logging import configure_logging
from farebi.harness.splits import split_indices

_CAL_FRACTION = 1.0 / 3.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", type=Path, default=Path("data/interim/quick_features.csv"))
    ap.add_argument("--out", type=Path, default=Path("reports/fusion_nested_quick256.json"))
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
    inner = StratifiedShuffleSplit(n_splits=1, test_size=_CAL_FRACTION, random_state=args.seed)
    fold_rows = []
    for fold in folds:
        tr, te = fold.train_idx, fold.test_idx
        if te.size == 0 or y[te].min() == y[te].max():
            continue
        fit_rel, cal_rel = next(inner.split(design[tr], y[tr]))
        fit, cal = tr[fit_rel], tr[cal_rel]
        scaler = StandardScaler().fit(design[fit])
        clf = LogisticRegression(max_iter=5000).fit(scaler.transform(design[fit]), y[fit])
        p_cal = clf.predict_proba(scaler.transform(design[cal]))[:, 1]
        p_test = clf.predict_proba(scaler.transform(design[te]))[:, 1]
        iso = IsotonicRegression(out_of_bounds="clip").fit(p_cal, y[cal])
        c_test = iso.predict(p_test)
        c_cal = iso.predict(p_cal)
        q_lo = float(np.percentile(c_cal[y[cal] == 1], 5))
        q_hi = float(np.percentile(c_cal[y[cal] == 0], 95))
        certain = (c_test < q_lo) | (c_test > q_hi)
        wrong = ((c_test > 0.5).astype(int) != y[te]) & certain
        fold_rows.append(
            {
                "held_out": sorted({groups[i] for i in te.tolist()}),
                "n_fit": int(fit.size),
                "n_cal": int(cal.size),
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
            "isotonic + band fit on held-out 1/3 calibration slice of train fold.",
            "inner fit/cal split is random stratified, not by group (train fold "
            "holds one real + one fake group); leakage touches only the 1-D map.",
            "same rows, outer folds and seed as the fusion-probe report for this dataset: "
            "AUC deltas isolate calibration discipline.",
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
