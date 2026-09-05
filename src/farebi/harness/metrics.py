"""Rank-based AUC, implemented locally on purpose.

``scikit-learn`` is a declared dependency of the ``ml`` extra and Phase 04 will
want it for real modelling. The *harness* deliberately does not: it sits on the
critical path of every signal decision, and pulling a compiled dependency into
that path would make ``make test`` (which runs without the ``ml`` extra) unable
to check the gate that decides which signals live.

The implementation is the tie-corrected Mann-Whitney U statistic, which is what
``sklearn.metrics.roc_auc_score`` computes. ``tests/unit/test_harness_metrics.py``
pins it against a brute-force count of concordant pairs, so a regression shows
up as a test failure rather than as a subtly wrong go/no-go decision.

Layer: OFFLINE (may import L0-L4; never imported by serving code).
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

__all__ = ["discriminative_auc", "roc_auc"]


def roc_auc(y_true: npt.ArrayLike, scores: npt.ArrayLike) -> float:
    """Area under the ROC curve, tie-corrected.

    Args:
        y_true: Binary labels, ``1`` = the positive class (fake).
        scores: Decision scores; **higher means more likely positive**.

    Returns:
        AUC in ``[0, 1]``. ``0.5`` means no discrimination. A value *below*
        0.5 means the score runs the other way, which is just as informative —
        see :func:`discriminative_auc`.

    Raises:
        ValueError: Shapes disagree, the input is empty, or only one class is
            present (AUC is undefined). The harness turns this into a skipped
            fold rather than a crash.
    """
    y = np.asarray(y_true, dtype=np.int64).ravel()
    s = np.asarray(scores, dtype=np.float64).ravel()

    if y.shape != s.shape:
        raise ValueError(f"y_true and scores must align, got {y.shape} and {s.shape}")
    if y.size == 0:
        raise ValueError("cannot compute AUC on an empty input")
    if not np.all(np.isin(y, (0, 1))):
        raise ValueError("y_true must contain only 0 and 1")
    if not np.all(np.isfinite(s)):
        raise ValueError("scores must be finite")

    n_pos = int(np.count_nonzero(y == 1))
    n_neg = int(y.size - n_pos)
    if n_pos == 0 or n_neg == 0:
        raise ValueError(
            f"AUC is undefined with a single class present (pos={n_pos}, neg={n_neg})"
        )

    # Average ranks within tied groups: ties contribute half a concordant pair.
    order = np.argsort(s, kind="mergesort")
    ordered = s[order]
    ranks = np.empty(s.size, dtype=np.float64)

    start = 0
    while start < s.size:
        stop = start
        while stop + 1 < s.size and ordered[stop + 1] == ordered[start]:
            stop += 1
        ranks[order[start : stop + 1]] = (start + stop) / 2.0 + 1.0
        start = stop + 1

    rank_sum_pos = float(ranks[y == 1].sum())
    # Mann-Whitney U, normalised to [0, 1].
    return (rank_sum_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)


def discriminative_auc(auc: float) -> tuple[float, int]:
    """Fold an AUC into ``[0.5, 1]`` and report which way the feature points.

    A feature with AUC 0.30 separates the classes perfectly; it simply runs
    backwards. The fusion fits a signed weight, so direction is information to
    record, not a reason to reject. Killing a signal for pointing the other way
    would be the harness punishing correct physics.

    Returns:
        ``(folded_auc, direction)`` where ``direction`` is ``+1`` when a higher
        score means more likely fake, ``-1`` when it means more likely real.
    """
    if auc >= 0.5:
        return auc, 1
    return 1.0 - auc, -1
