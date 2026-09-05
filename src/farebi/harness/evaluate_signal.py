"""Measure one signal against labelled, source-grouped samples.

This is the arbiter (``FAREBI.md`` §7). It answers four questions and refuses to
answer a fifth:

* **coverage** — how often the signal can run at all. A 0.90-AUC signal that
  fires on 8% of uploads is a bonus feature, not a pillar.
* **cross_source_auc** — mean AUC across source-group-held-out folds. The honest
  number, because a random split measures generator fingerprints.
* **auc_std** — spread of that AUC across folds. High spread means the signal
  works on *some* generators and is therefore fragile.
* **per_feature_auc** — which feature actually carries the signal. Mandatory
  output: it is how we discover that one engineered feature does all the work
  and nine others are noise.

It does **not** answer "is this image fake". Signals emit features; the fusion
decides.

Two deliberate choices:

* Samples are degraded with :class:`KYCDegradation` before measurement. A report
  built on pristine images measures the download, not the upload, and is invalid
  (``PLANS/02`` key decision #4).
* AUC is computed only over samples where the signal was applicable. Coverage is
  reported separately and gated separately, so an unusable-signal's low coverage
  is never hidden behind a flattering AUC.

Layer: OFFLINE (may import L0-L4; never imported by serving code).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final, Sequence

import numpy as np
import numpy.typing as npt

from farebi.degradation.kyc_pipeline import KYCDegradation, degrade_capture
from farebi.harness.metrics import discriminative_auc, roc_auc
from farebi.harness.splits import split_indices

if TYPE_CHECKING:  # pragma: no cover - typing only
    from farebi.core.config import KYCDegradationConfig
    from farebi.signals.base import Capture, Signal

__all__ = [
    "DEFAULT_N_SPLITS",
    "Sample",
    "SignalEvaluation",
    "collect_feature_matrix",
    "evaluate_signal",
]

#: Fewer folds than this makes ``auc_std`` meaningless as a fragility signal.
DEFAULT_N_SPLITS: Final = 5


@dataclass(frozen=True, slots=True)
class Sample:
    """One labelled, source-grouped evaluation item."""

    capture: Capture
    label: int  # 0 = real, 1 = fake
    source_group: str
    sample_id: str = ""


@dataclass(frozen=True, slots=True)
class SignalEvaluation:
    """The measurement the go/no-go gate consumes.

    ``per_feature_auc`` holds the *discriminative* AUC (folded into ``[0.5, 1]``).
    Pair it with ``per_feature_direction`` to recover the raw AUC: ``+1`` means a
    higher feature value tracks "more likely fake", ``-1`` means it tracks
    "more likely real", and the raw value is ``auc`` or ``1 - auc`` respectively.
    """

    signal: str
    dataset_version: str
    n_samples: int
    n_applicable: int
    coverage: float
    n_splits: int
    n_folds_used: int
    skipped_folds: int
    cross_source_auc: float | None
    auc_std: float
    per_feature_auc: dict[str, float] = field(default_factory=dict)
    per_feature_direction: dict[str, int] = field(default_factory=dict)
    best_feature: str | None = None
    degraded: bool = True
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "signal": self.signal,
            "dataset_version": self.dataset_version,
            "n_samples": self.n_samples,
            "n_applicable": self.n_applicable,
            "coverage": round(self.coverage, 6),
            "n_splits": self.n_splits,
            "n_folds_used": self.n_folds_used,
            "skipped_folds": self.skipped_folds,
            "cross_source_auc": (
                None if self.cross_source_auc is None else round(self.cross_source_auc, 6)
            ),
            "auc_std": round(self.auc_std, 6),
            "per_feature_auc": {k: round(v, 6) for k, v in sorted(self.per_feature_auc.items())},
            "per_feature_direction": dict(sorted(self.per_feature_direction.items())),
            "best_feature": self.best_feature,
            "degraded": self.degraded,
            "notes": list(self.notes),
        }


def _degrade_samples(
    samples: Sequence[Sample], kyc: KYCDegradation
) -> tuple[list[Sample], list[str]]:
    """Return degraded copies of every sample, plus any notes worth reporting."""
    out: list[Sample] = []
    notes: list[str] = []
    failures = 0
    for sample in samples:
        try:
            degraded, _ = degrade_capture(sample.capture, kyc)
        except Exception:  # noqa: BLE001 - a bad sample must not kill a run
            failures += 1
            out.append(sample)  # fall back to the pristine capture
            continue
        out.append(
            Sample(
                capture=degraded,
                label=sample.label,
                source_group=sample.source_group,
                sample_id=sample.sample_id,
            )
        )
    if failures:
        notes.append(
            f"{failures} sample(s) could not be degraded and were evaluated as captured; "
            "their numbers are optimistic and the run should be repeated."
        )
    return out, notes


def collect_feature_matrix(
    signal: Signal, samples: Sequence[Sample]
) -> tuple[list[int], dict[str, list[float]]]:
    """Run ``signal`` over ``samples`` and gather its features.

    Returns:
        ``(applicable_indices, features)`` where ``features`` maps each feature
        name to one value per applicable sample, in the same order.
    """
    applicable: list[int] = []
    features: dict[str, list[float]] = {}

    for i, sample in enumerate(samples):
        output = signal(sample.capture)
        if not output.applicable or not output.features:
            continue
        applicable.append(i)
        for name, value in output.features.items():
            features.setdefault(name, []).append(float(value))

    return applicable, features


def evaluate_signal(
    signal: Signal,
    samples: Sequence[Sample],
    *,
    n_splits: int = DEFAULT_N_SPLITS,
    seed: int | None = 1337,
    apply_degradation: bool = True,
    kyc: KYCDegradation | None = None,
    kyc_config: KYCDegradationConfig | None = None,
    dataset_version: str = "unknown",
) -> SignalEvaluation:
    """Measure ``signal`` and return the numbers the gate needs.

    Args:
        signal: The plugin instance to measure.
        samples: Labelled, source-grouped captures.
        n_splits: Number of source-group-held-out folds.
        seed: Seeds both the degradation sampling and the fold assignment, so a
            harness run is reproducible.
        apply_degradation: Almost always ``True``. Disable only to demonstrate
            how much a signal was overfitting to pristine input.
        kyc: Degradation instance; built from ``kyc_config`` (or settings) when
            omitted.
        kyc_config: Ranges for a default :class:`KYCDegradation`.
        dataset_version: Recorded in the report so a number is never orphaned
            from the data that produced it.
    """
    notes: list[str] = []
    if not samples:
        raise ValueError("cannot evaluate a signal against zero samples")

    working: Sequence[Sample] = samples
    if apply_degradation:
        degradator = kyc if kyc is not None else KYCDegradation(kyc_config, seed=seed)
        working, degradation_notes = _degrade_samples(samples, degradator)
        notes.extend(degradation_notes)
    else:
        notes.append(
            "degradation was DISABLED: these numbers describe pristine input and "
            "must not be used for a go/no-go decision (PLANS/02 key decision #4)."
        )

    applicable_idx, features = collect_feature_matrix(signal, working)
    n_samples = len(working)
    n_applicable = len(applicable_idx)
    coverage = n_applicable / n_samples if n_samples else 0.0

    empty = SignalEvaluation(
        signal=signal.name,
        dataset_version=dataset_version,
        n_samples=n_samples,
        n_applicable=n_applicable,
        coverage=coverage,
        n_splits=n_splits,
        n_folds_used=0,
        skipped_folds=0,
        cross_source_auc=None,
        auc_std=0.0,
        degraded=apply_degradation,
        notes=notes,
    )

    if not features or not applicable_idx:
        notes.append("the signal produced no usable features on any sample.")
        return empty

    labels_all = np.asarray([s.label for s in working], dtype=np.int64)
    groups_all = [s.source_group for s in working]
    labels = labels_all[np.asarray(applicable_idx, dtype=np.int64)]
    groups = [groups_all[i] for i in applicable_idx]

    try:
        folds = split_indices(groups, labels, n_splits=n_splits, seed=seed)
    except ValueError as exc:
        notes.append(f"split failed: {exc}")
        return empty

    per_feature_folds: dict[str, list[float]] = {}
    per_feature_raw: dict[str, list[float]] = {}
    per_feature_direction: dict[str, int] = {}
    n_folds_used = 0
    skipped = 0

    for fold in folds:
        test_idx = fold.test_idx
        if test_idx.size == 0:
            skipped += 1
            continue
        y_test = labels[test_idx]
        if y_test.min() == y_test.max():
            # A fold holding out only one class cannot produce an AUC. Skipping
            # is honest; averaging a NaN in would not be.
            skipped += 1
            continue

        fold_used = False
        for name, values in features.items():
            scores = np.asarray(values, dtype=np.float64)[test_idx]
            try:
                raw = roc_auc(y_test, scores)
            except ValueError:
                continue
            folded, direction = discriminative_auc(raw)
            per_feature_folds.setdefault(name, []).append(folded)
            per_feature_raw.setdefault(name, []).append(raw)
            per_feature_direction.setdefault(name, direction)
            fold_used = True
        n_folds_used += 1 if fold_used else 0
        if not fold_used:
            skipped += 1

    if not per_feature_folds:
        notes.append("no fold produced a defined AUC (every fold held out a single class).")
        return empty

    per_feature_auc = {name: float(np.mean(v)) for name, v in per_feature_folds.items()}
    # Direction from the median raw AUC across folds, so one odd fold cannot flip it.
    for name, raws in per_feature_raw.items():
        per_feature_direction[name] = 1 if float(np.median(raws)) >= 0.5 else -1


    best_feature = max(per_feature_auc, key=lambda k: per_feature_auc[k])
    best_folds = np.asarray(per_feature_folds[best_feature], dtype=np.float64)

    notes.append(
        "the best feature is selected on the same folds it is reported on, so its "
        "AUC is mildly optimistic; compare it against the other rows in per_feature_auc."
    )

    return SignalEvaluation(
        signal=signal.name,
        dataset_version=dataset_version,
        n_samples=n_samples,
        n_applicable=n_applicable,
        coverage=coverage,
        n_splits=n_splits,
        n_folds_used=n_folds_used,
        skipped_folds=skipped,
        cross_source_auc=float(best_folds.mean()),
        auc_std=float(best_folds.std()),
        per_feature_auc=per_feature_auc,
        per_feature_direction=per_feature_direction,
        best_feature=best_feature,
        degraded=apply_degradation,
        notes=notes,
    )
