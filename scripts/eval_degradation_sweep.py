"""Robustness sweep: re-run the 5 KEEP signals under fixed upload JPEG quality.

The harness degrades with sampled JPEG ranges, so its AUCs describe average
uploads. This probe pins the upload-SDK re-encode (the documented killer) to
fixed qualities to map each signal's operating envelope: at what compression
does each signal die?

Design notes:
  - Same ``seed=1337`` + same sample order at every level, and a FRESH
    ``KYCDegradation`` per level, so resize/AWB/blur draws are IDENTICAL
    across levels (same count of rng draws per image regardless of values)
    and only the final JPEG quality varies. Controlled experiment.
  - ``jpeg_quality`` (camera app) is fixed at 85; only ``recompress_quality``
    (upload SDK) sweeps. The pristine level disables degradation entirely as
    the ceiling reference — NOT a go/no-go number (PLANS/02 key decision #4).
  - Probe-only: uses evaluate_signal() + decide() directly, never touches
    configs/signals.yaml or artifacts/signal_registry.json.

Usage:
    .venv/Scripts/python.exe scripts/eval_degradation_sweep.py \\
        --samples data/interim/quick_samples_v2.pkl --n-splits 3
"""

from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path
from typing import Any

_TESTS = Path(__file__).resolve().parents[1] / "tests"
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))

from farebi.core.config import KYCDegradationConfig  # noqa: E402
from farebi.core.logging import configure_logging  # noqa: E402
from farebi.degradation.kyc_pipeline import KYCDegradation  # noqa: E402
from farebi.harness.evaluate_signal import Sample, evaluate_signal  # noqa: E402
from farebi.harness.gono import decide  # noqa: E402
from farebi.signals.registry import default_registry  # noqa: E402

KEEP_SIGNALS: tuple[str, ...] = (
    "fft",
    "texture",
    "prnu",
    "replay_detect",
    "chromatic_aberration",
)

#: (level name, recompress quality or None for pristine)
LEVELS: tuple[tuple[str, int | None], ...] = (
    ("pristine", None),
    ("q95", 95),
    ("q75", 75),
    ("q50", 50),
    ("q30", 30),
)

SEED = 1337


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", type=Path, required=True)
    ap.add_argument("--n-splits", type=int, default=3)
    ap.add_argument("--report", type=Path, default=Path("reports/degradation_sweep_v2.json"))
    args = ap.parse_args()

    configure_logging(level="INFO", json_logs=False)
    with args.samples.open("rb") as fh:
        samples: list[Sample] = pickle.load(fh)

    registry = default_registry()
    registry.discover()

    report: dict[str, dict[str, Any]] = {}
    for level, quality in LEVELS:
        level_rows: dict[str, Any] = {}
        for name in KEEP_SIGNALS:
            if quality is None:
                evaluation = evaluate_signal(
                    registry.get(name),
                    samples,
                    dataset_version=f"sweep-{level}",
                    n_splits=args.n_splits,
                    seed=SEED,
                    apply_degradation=False,
                )
            else:
                cfg = KYCDegradationConfig(
                    jpeg_quality=(85, 85), recompress_quality=(quality, quality)
                )
                evaluation = evaluate_signal(
                    registry.get(name),
                    samples,
                    dataset_version=f"sweep-{level}",
                    n_splits=args.n_splits,
                    seed=SEED,
                    kyc=KYCDegradation(cfg, seed=SEED),
                )
            verdict = decide(evaluation)
            level_rows[name] = {
                "auc": evaluation.cross_source_auc,
                "auc_std": evaluation.auc_std,
                "coverage": evaluation.coverage,
                "best_feature": evaluation.best_feature,
                "status": verdict.status.value,
            }
        report[level] = level_rows

    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)

    print("\n=== Degradation sweep (upload JPEG q) ===")
    header = "signal".ljust(20) + "".join(lvl.rjust(12) for lvl, _ in LEVELS)
    print(header)
    for name in KEEP_SIGNALS:
        cells = "".join(
            (
                "n/a".rjust(12)
                if report[lvl][name]["auc"] is None
                else f"{report[lvl][name]['auc']:.3f}".rjust(12)
            )
            for lvl, _ in LEVELS
        )
        print(name.ljust(20) + cells)
    print(f"\nWrote {args.report}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
