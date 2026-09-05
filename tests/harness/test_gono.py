"""Golden go/no-go regression: the gate must arbitrate both ways.

These tests pin the behaviour the harness exists for. They use the in-repo stub
signals (``tests/fixtures/stub_signals.py``), which are deliberately constructed
so that each lands in a different verdict bucket:

* :class:`NoiseSignal`   -> KILL  (uninformative feature)
* :class:`EncodedSignal` -> KEEP  (perfectly separated label)
* :class:`PartialSignal` -> BENCH (strong but rarely applicable)
"""

from __future__ import annotations

from farebi.core.constants import HarnessStatus
from farebi.harness.evaluate_signal import evaluate_signal
from farebi.harness.gono import decide
from fixtures.stub_signals import (
    EncodedSignal,
    NoiseSignal,
    PartialSignal,
    make_samples,
)


def _evaluate(signal) -> tuple:
    # 3 real + 3 fake source groups -> the splitter needs n_splits <= 3 per side.
    samples = make_samples(per_group=10, seed=1337)
    evaluation = evaluate_signal(signal, samples, dataset_version="self-test", n_splits=3)
    return evaluation, decide(evaluation)


def test_noise_signal_is_killed() -> None:
    _, verdict = _evaluate(NoiseSignal())
    assert verdict.status is HarnessStatus.KILL
    assert verdict.auc is None or verdict.auc < 0.60


def test_encoded_signal_is_kept() -> None:
    evaluation, verdict = _evaluate(EncodedSignal())
    assert verdict.status is HarnessStatus.KEEP
    assert evaluation.cross_source_auc is not None
    assert evaluation.cross_source_auc >= 0.65
    assert evaluation.coverage >= 0.50


def test_partial_signal_is_benched() -> None:
    evaluation, verdict = _evaluate(PartialSignal())
    assert verdict.status is HarnessStatus.BENCH
    # The coverage half of the rule must fire: strong but rare -> not KEEP.
    assert evaluation.coverage < 0.50
    assert evaluation.cross_source_auc is not None
    assert evaluation.cross_source_auc >= 0.60


def test_gate_boundary_values() -> None:
    """The policy thresholds are parameters so we can prove the boundaries."""
    from farebi.harness.gono import BENCH_AUC, KEEP_AUC, KEEP_COVERAGE

    samples = make_samples(per_group=10, seed=1337)
    encoded = evaluate_signal(EncodedSignal(), samples, dataset_version="self-test", n_splits=3)

    # One basis point under the KEEP AUC bar flips KEEP -> BENCH.
    ev = encoded
    # Simulate a measurement that just misses the AUC bar but clears BENCH.
    from dataclasses import replace

    marginal = replace(ev, cross_source_auc=KEEP_AUC - 0.001, coverage=KEEP_COVERAGE)
    assert decide(marginal).status is HarnessStatus.BENCH

    # Clear both bars -> KEEP.
    clear = replace(ev, cross_source_auc=KEEP_AUC + 0.001, coverage=KEEP_COVERAGE)
    assert decide(clear).status is HarnessStatus.KEEP

    # Coverage below the bar, AUC high -> BENCH (not KEEP).
    low_cov = replace(ev, cross_source_auc=0.95, coverage=KEEP_COVERAGE - 0.001)
    assert decide(low_cov).status is HarnessStatus.BENCH

    # Below BENCH AUC -> KILL.
    weak = replace(ev, cross_source_auc=BENCH_AUC - 0.001, coverage=KEEP_COVERAGE)
    assert decide(weak).status is HarnessStatus.KILL
