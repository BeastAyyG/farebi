"""Run the signal go/no-go harness and write the registry artifact.

Two entry points:

* ``--self-test`` evaluates the in-repo stub signals (no dataset required). This
  is the CI proof that the gate discriminates: a noise signal is KILLed, a
  label-encoded signal is KEPT, a strong-but-rare signal is BENCHed.
* ``--samples PATH`` evaluates the *real* signals discovered in ``farebi.signals``
  against a pre-built ``list[Sample]`` pickle (produced by the Phase 03 data
  pipeline). The harness never builds Captures itself — that is the capture
  layer's job — so it consumes already-constructed samples.

Either way it writes the machine-owned outputs the rest of the system reads:

* ``configs/signals.yaml`` — verdicts; the fusion gate refuses anything not
  ``keep``/``bench`` (``FAREBI.md`` §7).
* ``artifacts/signal_registry.json`` — verdicts + git SHA + config hash.
* ``artifacts/reports/harness/*.md`` — one report per signal + a summary.

Layer: OFFLINE. Never imported by serving code.
"""

from __future__ import annotations

import argparse
import pickle
import sys
from pathlib import Path

# Make ``tests/fixtures`` importable so the self-test can reuse the stub signals
# and the synthetic sample generator without duplicating them. The import itself
# is deferred into the self-test branch (below) because ``fixtures`` is only on
# the path at runtime, not for static type checking.
_TESTS = Path(__file__).resolve().parents[1] / "tests"
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))

from farebi.core.config import SignalsConfig  # noqa: E402
from farebi.core.logging import configure_logging, get_logger  # noqa: E402
from farebi.harness.evaluate_signal import Sample, evaluate_signal  # noqa: E402
from farebi.harness.gono import verdict_table_rows  # noqa: E402
from farebi.harness.report import (  # noqa: E402
    HarnessReport,
    status_counts,
    write_reports,
    write_signal_registry,
)
from farebi.signals.base import Signal  # noqa: E402
from farebi.signals.registry import default_registry, reset_registry  # noqa: E402

_log = get_logger(__name__)


def _collect_signals() -> list[Signal]:
    """Discover and return the real signal instances in ``farebi.signals``."""
    registry = default_registry()
    registry.discover()
    return [registry.get(name) for name in registry.names()]


def _load_samples(path: Path) -> list[Sample]:
    with path.open("rb") as handle:
        samples = pickle.load(handle)
    if not isinstance(samples, list) or not samples:
        raise ValueError(f"{path} must contain a non-empty list[Sample], got {type(samples)}")
    return samples


def run(
    *,
    self_test: bool,
    samples_path: Path | None,
    dataset_version: str,
    config_path: Path | None,
    n_splits: int = 5,
) -> HarnessReport:
    """Evaluate every signal, run the gate, and write the registry outputs."""
    if self_test:
        if samples_path is not None:
            raise ValueError("--self-test and --samples are mutually exclusive")
        # Lazy import: ``fixtures`` is only on sys.path at runtime (added above),
        # not visible to static type checking.
        from fixtures.stub_signals import (  # type: ignore[import-not-found]
            EncodedSignal,
            NoiseSignal,
            PartialSignal,
            make_samples,
        )

        samples = make_samples(per_group=10, seed=1337)
        signals: list[Signal] = [NoiseSignal(), EncodedSignal(), PartialSignal()]
    else:
        if samples_path is None:
            _log.warning("no --samples given; falling back to --self-test")
            return run(
                self_test=True,
                samples_path=None,
                dataset_version=dataset_version,
                config_path=config_path,
            )
        samples = _load_samples(samples_path)
        signals = _collect_signals()

    reset_registry(SignalsConfig())

    evaluations = []
    verdicts = []
    for signal in signals:
        # 3 real + 3 fake source groups in self-test -> n_splits must be <= 3.
        # Real runs default to 5; small shims (e.g. 2+2 groups) pass --n-splits 2.
        splits = 3 if self_test else n_splits
        evaluation = evaluate_signal(
            signal, samples, dataset_version=dataset_version, n_splits=splits
        )
        evaluations.append(evaluation)
        from farebi.harness.gono import decide

        verdicts.append(decide(evaluation))
        _log.info(
            "signal_evaluated",
            signal=signal.name,
            status=verdicts[-1].status.value,
            auc=verdicts[-1].auc,
            coverage=round(verdicts[-1].coverage, 3),
        )

    report = HarnessReport(
        dataset_version=dataset_version,
        evaluations=evaluations,
        verdicts=verdicts,
        registry_version=f"harness-{dataset_version}",
        notes=[
            f"evaluated {len(signals)} signal(s) in self-test mode"
            if self_test
            else f"evaluated {len(signals)} signal(s) from farebi.signals"
        ],
    )

    written = write_reports(report)
    artifact, cfg = write_signal_registry(report, config_path=config_path)

    _print_summary(report)
    _log.info("harness_done", artifact=str(artifact), config=str(cfg), reports=len(written))
    return report


def _print_summary(report: HarnessReport) -> None:
    counts = status_counts(report.verdicts)
    print("\n=== Signal harness summary ===")
    print(f"dataset: {report.dataset_version}   registry: {report.registry_version}")
    print("verdicts: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) + "\n")
    for row in verdict_table_rows(report.verdicts):
        print(
            f"  {row['signal']:<16} {row['status'].upper():<10} "
            f"auc={row['auc']:<7} cov={row['coverage']:<5} {row['reason']}"
        )
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--self-test", action="store_true", help="evaluate the in-repo stub signals"
    )
    parser.add_argument(
        "--samples", type=Path, default=None, help="pickle of list[Sample] for real runs"
    )
    parser.add_argument("--dataset-version", default="self-test", help="recorded in every report")
    parser.add_argument(
        "--config", type=Path, default=None, help="override configs/signals.yaml path"
    )
    parser.add_argument(
        "--n-splits",
        type=int,
        default=5,
        help="GroupKFold splits for real runs (must be <= #groups per side)",
    )
    args = parser.parse_args(argv)

    configure_logging(level="INFO", json_logs=False)
    run(
        self_test=args.self_test or args.samples is None,
        samples_path=args.samples,
        dataset_version=args.dataset_version,
        config_path=args.config,
        n_splits=args.n_splits,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
