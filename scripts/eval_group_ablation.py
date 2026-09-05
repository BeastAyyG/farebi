"""Phase-07 diagnostic: which groups are hardest, which signals are redundant.

On the v2 feature matrix (3 real + 3 fake source groups, n_splits=3 outer
folds, seed 1337 — same rows/folds as the fusion probe):

* leave-one-signal-out: drop each signal's columns, refit the probe LR, and
  report the mean held-out AUC delta. A ~0 delta means the signal's evidence
  is redundant given the other four.
* per-held-out-group score medians: for each test-fold group, the median raw
  fusion score. Real groups should sit near 0, fake groups near 1; a group
  parked near 0.5 is the domain the fusion handles worst.

Both are directional (small-n, 256px) and feed Phase-07 signal weighting, not
the UNCERTAIN band — the transport probe showed the band is intrinsic overlap,
not domain shift.

Writes JSON to ``reports/fusion_ablation_v2.json``.

Usage:
    .venv/Scripts/python.exe scripts/eval_group_ablation.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler

from farebi.core.logging import configure_logging
from farebi.harness.splits import split_indices

SIGNALS = ["fft", "texture", "prnu", "replay_detect", "chromatic_aberration"]


def fit_auc(
    design: np.ndarray,
    y: np.ndarray,
    tr: np.ndarray,
    te: np.ndarray,
    cols: list[int],
) -> tuple[float, np.ndarray]:
    """Fit probe LR on ``cols`` and return (test AUC, test scores)."""
    sub = np.asarray(cols, dtype=np.intp)
    scaler = StandardScaler().fit(design[np.ix_(tr, sub)])
    clf = LogisticRegression(max_iter=5000).fit(scaler.transform(design[np.ix_(tr, sub)]), y[tr])
    p_test: np.ndarray = clf.predict_proba(scaler.transform(design[np.ix_(te, sub)]))[:, 1]
    return float(roc_auc_score(y[te], p_test)), p_test


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", type=Path, default=Path("data/interim/quick_features_v2.csv"))
    ap.add_argument("--out", type=Path, default=Path("reports/fusion_ablation_v2.json"))
    ap.add_argument("--n-splits", type=int, default=3)
    ap.add_argument("--seed", type=int, default=1337)
    args = ap.parse_args()

    configure_logging(level="INFO", json_logs=False)
    frame = pd.read_csv(args.features)
    meta = ["sample_id", "label", "source_group"]
    feat_cols = [c for c in frame.columns if c not in meta]
    by_signal = {s: [c for c in feat_cols if c.startswith(s + "__")] for s in SIGNALS}
    assert all(by_signal.values()), f"signal with no columns: {by_signal}"
    design = frame[feat_cols].to_numpy(dtype=np.float64)
    y = frame["label"].to_numpy(dtype=np.int64)
    groups: list[str] = frame["source_group"].tolist()

    folds = split_indices(groups, y, n_splits=args.n_splits, seed=args.seed)
    all_cols = list(range(len(feat_cols)))
    baseline_aucs: list[float] = []
    drop_deltas: dict[str, list[float]] = {s: [] for s in SIGNALS}
    group_medians: dict[str, list[float]] = {}
    for fold in folds:
        tr, te = fold.train_idx, fold.test_idx
        if te.size == 0 or y[te].min() == y[te].max():
            continue
        base_auc, p_test = fit_auc(design, y, tr, te, all_cols)
        baseline_aucs.append(base_auc)
        for sig in SIGNALS:
            keep = [i for i in all_cols if feat_cols[i] not in by_signal[sig]]
            drop_auc, _ = fit_auc(design, y, tr, te, keep)
            drop_deltas[sig].append(base_auc - drop_auc)
        te_list = te.tolist()
        for g in sorted({groups[i] for i in te_list}):
            med = float(np.median(p_test[[k for k, i in enumerate(te_list) if groups[i] == g]]))
            group_medians.setdefault(g, []).append(med)

    ablation: dict[str, Any] = {
        sig: {
            "n_features": len(by_signal[sig]),
            "mean_auc_delta_when_dropped": float(np.mean(drop_deltas[sig])),
        }
        for sig in SIGNALS
    }
    group_rows = {
        g: {"median_test_score": float(np.mean(v)), "label": int(y[groups.index(g)])}
        for g, v in group_medians.items()
    }
    summary = {
        "dataset": str(args.features),
        "n_samples": len(frame),
        "mean_baseline_auc": float(np.mean(baseline_aucs)),
        "leave_one_signal_out": ablation,
        "held_out_group_median_scores": group_rows,
        "notes": [
            "positive delta = AUC lost without the signal = unique evidence.",
            "group medians near 0.5 mark the domains fusion handles worst.",
            "sdxl has only 33 rows: its fold estimates are the noisiest.",
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"mean baseline AUC: {summary['mean_baseline_auc']:.3f}")
    for sig in sorted(ablation, key=lambda s: ablation[s]["mean_auc_delta_when_dropped"]):
        print(f"  drop {sig:22s} delta={ablation[sig]['mean_auc_delta_when_dropped']:+.3f}")
    for g, row in sorted(group_rows.items()):
        print(f"  group {g:12s} label={row['label']} median_score={row['median_test_score']:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
