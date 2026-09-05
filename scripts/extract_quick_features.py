"""Extract a wide per-sample feature matrix for the fusion probe.

Runs the five KEEP signals over degraded quick-shim captures (same
``KYCDegradation`` seed the harness uses) and writes one row per sample with
``<signal>__<feature>`` columns plus label / source_group / sample_id.

Only samples where ALL five signals are applicable are kept; the rest are
counted and reported. This is a Phase-07 prototype input, not L5 code:
no model is trained here.

Usage:
    .venv/Scripts/python.exe scripts/extract_quick_features.py \
        --samples data/interim/quick_samples.pkl \
        --out data/interim/quick_features.csv
"""

from __future__ import annotations

import argparse
import pickle
from pathlib import Path

import pandas as pd

from farebi.core.logging import configure_logging
from farebi.degradation.kyc_pipeline import KYCDegradation, degrade_capture
from farebi.harness.evaluate_signal import Sample
from farebi.signals.registry import default_registry

SIGNALS = ("fft", "texture", "prnu", "replay_detect", "chromatic_aberration")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", type=Path, default=Path("data/interim/quick_samples.pkl"))
    ap.add_argument("--out", type=Path, default=Path("data/interim/quick_features.csv"))
    ap.add_argument("--seed", type=int, default=1337)
    args = ap.parse_args()

    configure_logging(level="INFO", json_logs=False)
    with args.samples.open("rb") as fh:
        samples: list[Sample] = pickle.load(fh)

    registry = default_registry()
    registry.discover()
    signals = {name: registry.get(name) for name in SIGNALS}

    kyc = KYCDegradation(None, seed=args.seed)
    rows: list[dict[str, object]] = []
    per_signal_n = dict.fromkeys(SIGNALS, 0)
    for sample in samples:
        try:
            degraded, _ = degrade_capture(sample.capture, kyc)
        except Exception:  # harness fallback: evaluate as captured
            degraded = sample.capture
        outputs = {}
        ok = True
        for name, signal in signals.items():
            out = signal(degraded)
            if not out.applicable or not out.features:
                ok = False
                break
            outputs[name] = out
        if not ok:
            continue
        row: dict[str, object] = {
            "sample_id": sample.sample_id,
            "label": sample.label,
            "source_group": sample.source_group,
        }
        for name, out in outputs.items():
            per_signal_n[name] += 1
            for feat, value in out.features.items():
                col = f"{name}__{feat}"
                if col in row:
                    raise ValueError(f"feature column collision: {col}")
                row[col] = float(value)
        rows.append(row)

    frame = pd.DataFrame(rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(args.out, index=False)
    print(f"kept {len(frame)}/{len(samples)} samples -> {args.out}")
    print(f"per-signal applicable: {per_signal_n}")
    print(f"feature columns: {frame.shape[1] - 3}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
