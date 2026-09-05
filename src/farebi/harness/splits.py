"""Group-aware, class-balanced cross-validation splits.

``FAREBI.md`` §7 is blunt about why this exists: a random split leaks generator
fingerprints and produces a 0.98 AUC that collapses to 0.55 the moment a
fraudster adopts a new model. Every fold must therefore hold out whole **source
groups** — a generator family, or a camera set for real captures.

**Why this is not plain ``GroupKFold``.** In this problem source groups are
class-pure by nature: the ``stylegan3`` group contains only fakes, the ``cam_iphone``
group only reals. A textbook GroupKFold would therefore hand us test folds
containing exactly one class, and AUC is undefined on a single class — every fold
would be skipped and the harness would report nothing at all.

So each fold holds out **one real-leaning group and one fake-leaning group**
together. That is both computable and the harder, more honest question: it asks
whether a signal generalises to a camera set *and* a generator family it has
never seen, which is precisely the deployment case.

Layer: OFFLINE (may import L0-L4; never imported by serving code).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import numpy.typing as npt

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Sequence

__all__ = ["Fold", "SplitError", "group_kfold", "split_indices", "summarise_folds"]

_MIN_SPLITS = 2


class SplitError(ValueError):
    """Raised when a group-aware, class-balanced split cannot be constructed."""


@dataclass(frozen=True, slots=True)
class Fold:
    """One train/test partition, in terms of positional indices."""

    index: int
    train_idx: npt.NDArray[np.int64]
    test_idx: npt.NDArray[np.int64]

    @property
    def train_size(self) -> int:
        return int(self.train_idx.size)

    @property
    def test_size(self) -> int:
        return int(self.test_idx.size)


def _assign_balanced(
    group_ids: list[int],
    members: list[npt.NDArray[np.int64]],
    n_splits: int,
    *,
    seed: int | None,
) -> list[list[int]]:
    """Distribute groups across folds, largest first into the emptiest fold.

    Placing the big pieces early stops the greedy pass from stranding them in
    whatever fold is left at the end, which is what produces a ragged split.
    """
    sizes = [int(members[g].size) for g in group_ids]
    order = sorted(range(len(group_ids)), key=lambda i: (-sizes[i], i))

    if seed is not None:
        rng = np.random.default_rng(seed)
        # Shuffle only within equal sizes so the size ordering survives.
        shuffled: list[int] = []
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and sizes[order[j + 1]] == sizes[order[i]]:
                j += 1
            chunk = order[i : j + 1]
            shuffled.extend(rng.permutation(chunk).tolist() if len(chunk) > 1 else chunk)
            i = j + 1
        order = shuffled

    buckets: list[list[int]] = [[] for _ in range(n_splits)]
    totals = np.zeros(n_splits, dtype=np.int64)
    for i in order:
        target = int(np.argmin(totals))
        buckets[target].append(group_ids[i])
        totals[target] += sizes[i]
    return buckets


def split_indices(
    groups: Sequence[str],
    labels: npt.NDArray[np.int64],
    *,
    n_splits: int,
    seed: int | None = None,
) -> list[Fold]:
    """Assign whole source groups to folds, keeping both classes in every fold.

    Groups are split into real-leaning and fake-leaning by majority class, then
    each side is distributed independently across the folds. Every fold therefore
    holds out at least one group of each kind whenever the data allows it.

    Args:
        groups: Source group per sample. Samples sharing a group never straddle
            a train/test boundary.
        labels: ``0`` = real, ``1`` = fake.
        n_splits: Number of folds.
        seed: Seeds the within-equal-size tie shuffle. ``None`` is
            non-deterministic.

    Returns:
        One :class:`Fold` per split; every sample is in exactly one test set.

    Raises:
        SplitError: Fewer than ``n_splits`` groups on either side, mismatched
            lengths, or an empty sample set.
    """
    if n_splits < _MIN_SPLITS:
        raise SplitError(f"n_splits must be at least {_MIN_SPLITS}, got {n_splits}")

    labels_arr = np.asarray(labels, dtype=np.int64).ravel()
    groups_arr = np.asarray(groups, dtype=object).ravel()

    if groups_arr.size != labels_arr.size:
        raise SplitError(
            f"groups ({groups_arr.size}) and labels ({labels_arr.size}) must be the same length"
        )
    if labels_arr.size == 0:
        raise SplitError("cannot split an empty sample set")
    if not np.all(np.isin(labels_arr, (0, 1))):
        raise SplitError("labels must contain only 0 and 1")

    unique, inverse = np.unique(groups_arr, return_inverse=True)
    inverse = inverse.ravel()
    members: list[npt.NDArray[np.int64]] = [
        np.flatnonzero(inverse == i).astype(np.int64) for i in range(unique.size)
    ]

    real_side: list[int] = []
    fake_side: list[int] = []
    for gid in range(unique.size):
        idx = members[gid]
        side = fake_side if float(labels_arr[idx].mean()) >= 0.5 else real_side
        side.append(gid)

    short = [
        (name, len(side))
        for name, side in (("real-source", real_side), ("fake-source", fake_side))
        if len(side) < n_splits
    ]
    if short:
        detail = "; ".join(f"{name} groups: {count} < n_splits {n_splits}" for name, count in short)
        raise SplitError(
            f"cannot build {n_splits} class-balanced folds ({detail}). "
            "Each fold must hold out one real-source and one fake-source group, so "
            "collect more source groups or lower n_splits."
        )

    real_buckets = _assign_balanced(real_side, members, n_splits, seed=seed)
    fake_buckets = _assign_balanced(
        fake_side, members, n_splits, seed=None if seed is None else seed + 1
    )

    folds: list[Fold] = []
    for i in range(n_splits):
        held = real_buckets[i] + fake_buckets[i]
        test_idx = (
            np.sort(np.concatenate([members[g] for g in held])).astype(np.int64)
            if held
            else np.empty(0, dtype=np.int64)
        )
        mask = np.ones(labels_arr.size, dtype=bool)
        mask[test_idx] = False
        folds.append(
            Fold(index=i, train_idx=np.flatnonzero(mask).astype(np.int64), test_idx=test_idx)
        )
    return folds


def group_kfold(
    groups: Sequence[str],
    labels: npt.NDArray[np.int64],
    *,
    n_splits: int = 5,
    seed: int | None = None,
) -> list[tuple[npt.NDArray[np.int64], npt.NDArray[np.int64]]]:
    """Convenience wrapper returning ``(train_idx, test_idx)`` tuples."""
    return [
        (f.train_idx, f.test_idx)
        for f in split_indices(groups, labels, n_splits=n_splits, seed=seed)
    ]


@dataclass(frozen=True, slots=True)
class FoldSummary:
    """What a reviewer needs in order to trust a split."""

    n_folds: int
    test_groups_per_fold: list[int]
    folds_with_both_classes: int
    min_train: int
    min_test: int

    @property
    def every_fold_has_both_classes(self) -> bool:
        return self.folds_with_both_classes == self.n_folds


def summarise_folds(
    folds: list[Fold], groups: Sequence[str], labels: npt.NDArray[np.int64]
) -> FoldSummary:
    """Describe a split: fold sizes, held-out group counts, class coverage."""
    groups_arr = np.asarray(groups, dtype=object).ravel()
    labels_arr = np.asarray(labels, dtype=np.int64).ravel()

    both = 0
    per_fold_groups: list[int] = []
    for fold in folds:
        held = {groups_arr[i] for i in fold.test_idx.tolist()}
        per_fold_groups.append(len(held))
        test_labels = labels_arr[fold.test_idx]
        if test_labels.size and test_labels.min() == 0 and test_labels.max() == 1:
            both += 1

    return FoldSummary(
        n_folds=len(folds),
        test_groups_per_fold=per_fold_groups,
        folds_with_both_classes=both,
        min_train=min((f.train_size for f in folds), default=0),
        min_test=min((f.test_size for f in folds), default=0),
    )
