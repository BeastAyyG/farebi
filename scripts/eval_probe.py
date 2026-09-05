"""Evaluate signals on a Sample pickle WITHOUT touching machine-owned outputs.

scripts/run_harness.py rewrites configs/signals.yaml +
artifacts/signal_registry.json on every real run. The registry currently
holds the quick256 verdicts (the fusion gate's input); a red-team probe
must not clobber it. This script runs evaluate_signal() + decide() over
the discovered farebi.signals and prints the verdict table only.

Usage:
    .venv/Scripts/python.exe scripts/eval_probe.py --samples data/interim/X.pkl \\
        --dataset-version NAME --n-splits 2
"""

from __future__ import annotations

import argparse
import pickle
import sys
from pathlib import Path

_TESTS = Path(__file__).resolve().parents[1] / "tests"
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))

from farebi.core.logging import configure_logging  # noqa: E402
from farebi.harness.evaluate_signal import Sample, evaluate_signal  # noqa: E402
from farebi.harness.gono import decide, verdict_table_rows  # noqa: E402
from farebi.signals.registry import default_registry  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", type=Path, required=True)
    ap.add_argument("--dataset-version", default="probe")
    ap.add_argument("--n-splits", type=int, default=2)
    args = ap.parse_args()

    configure_logging(level="INFO", json_logs=False)
    with args.samples.open("rb") as fh:
        samples: list[Sample] = pickle.load(fh)

    registry = default_registry()
    registry.discover()
    verdicts = []
    for name in registry.names():
        evaluation = evaluate_signal(
            registry.get(name),
            samples,
            dataset_version=args.dataset_version,
            n_splits=args.n_splits,
        )
        verdicts.append(decide(evaluation))

    print(f"\n=== Probe summary: {args.dataset_version} (n={len(samples)}) ===")
    for row in verdict_table_rows(verdicts):
        print(
            f"  {row['signal']:<20} {row['status'].upper():<10} "
            f"auc={row['auc']:<7} cov={row['coverage']:<5} {row['reason']}"
        )
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
