"""Phase-07 follow-up: band transportability (in-domain vs cross-domain).

Follow-up to ``train_fusion_nested.py``. The v2 nested run showed the
percentile band widening to 43% uncertain under multi-group folds because each
class's calibration slice is a bimodal union of two source domains. This script
tests the production-relevant hypothesis: the UNCERTAIN band is a
*deployment-domain* object, while cross-source folds measure *discrimination*.

Design (same rows, outer folds and seed as the nested v2 report, so the
transported column reproduces it up to the calA/calB split):

* outer train fold -> stratified 2/3 fit + 1/3 calibration (seeded),
* calibration slice -> stratified halves calA (band fit) and calB (in-domain eval),
* StandardScaler + LogisticRegression on fit, isotonic map on calA,
* per-class percentile band edges from calA (same 5/95 construction as nested),
* report the SAME band twice: on calB (in-domain, honest: unseen rows, same
  domains) and on the outer test fold (transported: unseen domains).

If in-domain uncertain/err|certain sit near the 15%/5% DoD targets while the
transported numbers stay wide, the conclusion is structural: ship
per-deployment calibration sets and specify the UNCERTAIN targets in-domain;
cross-source evaluation keeps measuring AUC only. No modelling change can fix
a band transported across domains, because group-conditional (Mondrian)
thresholds cannot cover an unseen held-out group.

Usage:
    .venv/Scripts/python.exe scripts/eval_band_transport.py \
        --features data/interim/quick_features_v2.csv --n-splits 3
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedShuffleSplit
from sklearn.preprocessing import StandardScaler

from farebi.core.logging import configure_logging
from farebi.harness.splits import split_indices

_CAL_FRACTION = 1.0 / 3.0
_INDOMAIN_FRACTION = 0.5


def _band_metrics(
    c_eval: np.ndarray, y_eval: np.ndarray, q_lo: float, q_hi: float
) -> dict[str, float]:
    certain = (c_eval < q_lo) | (c_eval > q_hi)
    wrong = ((c_eval > 0.5).astype(int) != y_eval) & certain
    return {
        "n_eval": int(c_eval.size),
        "uncertain_rate": float(1.0 - certain.mean()),
        "error_given_certain": float(wrong.sum() / max(int(certain.sum()), 1)),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", type=Path, default=Path("data/interim/quick_features_v2.csv"))
    ap.add_argument("--out", type=Path, default=Path("reports/fusion_band_transport_v2.json"))
    ap.add_argument("--n-splits", type=int, default=3)
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
    outer = StratifiedShuffleSplit(n_splits=1, test_size=_CAL_FRACTION, random_state=args.seed)
    inner = StratifiedShuffleSplit(n_splits=1, test_size=_INDOMAIN_FRACTION, random_state=args.seed)
    fold_rows: list[dict[str, Any]] = []
    for fold in folds:
        tr, te = fold.train_idx, fold.test_idx
        if te.size == 0 or y[te].min() == y[te].max():
            continue
        fit_rel, cal_rel = next(outer.split(design[tr], y[tr]))
        fit, cal = tr[fit_rel], tr[cal_rel]
        if y[cal].min() == y[cal].max():
            continue
        a_rel, b_rel = next(inner.split(design[cal], y[cal]))
        cal_a, cal_b = cal[a_rel], cal[b_rel]
        if y[cal_a].min() == y[cal_a].max() or y[cal_b].min() == y[cal_b].max():
            continue
        scaler = StandardScaler().fit(design[fit])
        clf = LogisticRegression(max_iter=5000).fit(scaler.transform(design[fit]), y[fit])
        p_a = clf.predict_proba(scaler.transform(design[cal_a]))[:, 1]
        iso = IsotonicRegression(out_of_bounds="clip").fit(p_a, y[cal_a])
        c_a = iso.predict(p_a)
        q_lo = float(np.percentile(c_a[y[cal_a] == 1], 5))
        q_hi = float(np.percentile(c_a[y[cal_a] == 0], 95))
        c_b = iso.predict(clf.predict_proba(scaler.transform(design[cal_b]))[:, 1])
        c_te = iso.predict(clf.predict_proba(scaler.transform(design[te]))[:, 1])
        in_domain = _band_metrics(c_b, y[cal_b], q_lo, q_hi)
        transported = _band_metrics(c_te, y[te], q_lo, q_hi)
        fold_rows.append(
            {
                "held_out": sorted({groups[i] for i in te.tolist()}),
                "n_fit": int(fit.size),
                "n_cal_a": int(cal_a.size),
                "n_cal_b": int(cal_b.size),
                "n_test": int(te.size),
                "auc_raw": float(roc_auc_score(y[te], p_te))
                if (p_te := clf.predict_proba(scaler.transform(design[te]))[:, 1]).size
                else float("nan"),
                "q_lo": q_lo,
                "q_hi": q_hi,
                "in_domain": in_domain,
                "transported": transported,
            }
        )

    summary = {
        "dataset": str(args.features),
        "n_samples": len(frame),
        "n_features": len(feat_cols),
        "mean_in_domain_uncertain": float(
            np.mean([f["in_domain"]["uncertain_rate"] for f in fold_rows])
        ),
        "mean_in_domain_error_given_certain": float(
            np.mean([f["in_domain"]["error_given_certain"] for f in fold_rows])
        ),
        "mean_transported_uncertain": float(
            np.mean([f["transported"]["uncertain_rate"] for f in fold_rows])
        ),
        "mean_transported_error_given_certain": float(
            np.mean([f["transported"]["error_given_certain"] for f in fold_rows])
        ),
        "notes": [
            "same rows, outer folds and seed as the nested report: the transported "
            "column is the nested construction re-evaluated; only the calA/calB "
            "split is new, so in-domain vs transported deltas isolate domain shift.",
            "band edges are per-class percentiles (5th fake / 95th real) of the "
            "calA calibrated scores; binary APS-style sets reduce to the same "
            "edges, so no alternative thresholding of one score can do better.",
            "Mondrian (group-conditional) thresholds cannot cover an unseen "
            "held-out group, so the transported width is structural, not a bug.",
        ],
        "folds": fold_rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "folds"}, indent=2))
    for f in fold_rows:
        print(
            f"  held_out={f['held_out']} auc_raw={f['auc_raw']:.3f} "
            f"in_domain(unc={f['in_domain']['uncertain_rate']:.2f},"
            f"err={f['in_domain']['error_given_certain']:.3f}) "
            f"transported(unc={f['transported']['uncertain_rate']:.2f},"
            f"err={f['transported']['error_given_certain']:.3f})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
