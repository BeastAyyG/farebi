"""Build harness Samples from the quick-shim manifest (Phase 04 data shim).

Reads data/manifests/quick_manifest.csv, decodes each image, runs
build_capture with a SHARED FaceMeshDetector, and pickles list[Sample] to
data/interim/quick_samples.pkl (gitignored — contains pixel data).

Also runs the landmark-index mapping validation on every OK real capture:
iris landmark 468 must lie inside the EYE_LEFT contour bounding box
(per the corneal-signal index-mapping check). Any violation aborts.

Usage:
    .venv/Scripts/python.exe scripts/build_quick_samples.py [--limit N]
"""

from __future__ import annotations

import argparse
import csv
import pathlib
import pickle

import numpy as np

from farebi.capture.capture import Capture, build_capture
from farebi.capture.face_mesh import FaceMeshDetector
from farebi.capture.landmarks import EYE_LEFT
from farebi.core.config import QualityConfig, get_settings, reload_settings
from farebi.core.security import UploadLimits
from farebi.harness.evaluate_signal import Sample
from farebi.utils.image_io import decode_image

ROOT = pathlib.Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "manifests" / "quick_manifest.csv"
OUT = ROOT / "data" / "interim" / "quick_samples.pkl"


def _check_iris_mapping(sample_id: str, capture: Capture) -> None:
    """Iris centre 468 must sit inside the left-eye contour bbox (pixels).

    ``Capture.landmarks`` is the raw (N,3) normalised array; frame size comes
    from the capture image. Mirrors the corneal-signal index-mapping check.
    """
    pts = np.asarray(capture.landmarks)
    h, w = np.asarray(capture.image_bgr).shape[:2]
    iris_x = float(pts[468, 0]) * w
    iris_y = float(pts[468, 1]) * h
    eye = pts[list(EYE_LEFT)][:, :2] * (w, h)
    x0, y0 = eye.min(axis=0)
    x1, y1 = eye.max(axis=0)
    assert x0 < iris_x < x1 and y0 < iris_y < y1, (
        f"{sample_id}: iris 468 ({iris_x:.0f},{iris_y:.0f}) outside EYE_LEFT "
        f"bbox x[{x0:.0f},{x1:.0f}] y[{y0:.0f},{y1:.0f}] — index mapping wrong"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="max rows per group (0 = all)")
    ap.add_argument(
        "--min-eye-px",
        type=float,
        default=24.0,
        help="shim override for quality.min_eye_width_px (256px research rows; "
        "production KYC uploads are 720p+ where the app.yaml 40px gate holds)",
    )
    ap.add_argument(
        "--min-blur",
        type=float,
        default=15.0,
        help="shim override for quality.min_blur_score (keeps soft synthetic "
        "rows in the pool; the gate must not do the classifier's job)",
    )
    args = ap.parse_args()

    upload = get_settings().upload
    limits = UploadLimits(
        max_bytes=upload.max_bytes,
        max_pixels=upload.max_pixels,
        max_edge_px=upload.max_edge_px,
        allowed_media_types=frozenset(upload.allowed_media_types),
    )
    base = reload_settings().capture
    config = base.model_copy(
        update={
            "quality": QualityConfig(
                min_face_px=base.quality.min_face_px,
                min_interocular_px=base.quality.min_interocular_px,
                min_eye_width_px=args.min_eye_px,
                min_blur_score=args.min_blur,
                min_exposure=base.quality.min_exposure,
                max_exposure=base.quality.max_exposure,
                max_clipped_fraction=base.quality.max_clipped_fraction,
            )
        }
    )
    print(
        f"shim quality overrides: min_eye_width_px={args.min_eye_px} "
        f"(app.yaml {base.quality.min_eye_width_px}), "
        f"min_blur_score={args.min_blur} (app.yaml {base.quality.min_blur_score})"
    )

    with open(MANIFEST, newline="") as fh:
        rows = list(csv.DictReader(fh))
    if args.limit:
        by_group: dict[str, int] = {}
        kept_rows = []
        for r in rows:
            if by_group.get(r["source_group"], 0) < args.limit:
                kept_rows.append(r)
                by_group[r["source_group"]] = by_group.get(r["source_group"], 0) + 1
        rows = kept_rows

    samples: list[Sample] = []
    drops: dict[str, int] = {}
    checked = 0
    with FaceMeshDetector() as detector:
        for i, row in enumerate(rows):
            raw = (ROOT / row["path"]).read_bytes()
            try:
                decoded = decode_image(
                    raw,
                    declared_media_type="image/jpeg",
                    filename=pathlib.Path(row["path"]).name,
                    limits=limits,
                )
            except Exception as exc:  # shim: count decode drops
                drops[f"decode:{type(exc).__name__}"] = (
                    drops.get(f"decode:{type(exc).__name__}", 0) + 1
                )
                continue
            result = build_capture(decoded, config=config, detector=detector)
            if not result.ok or result.capture is None:
                key = f"capture:{result.status.name}"
                drops[key] = drops.get(key, 0) + 1
                continue
            label = int(row["label"])
            if label == 0 and result.capture.has_iris:
                _check_iris_mapping(row["path"], result.capture)
                checked += 1
            samples.append(
                Sample(
                    capture=result.capture,
                    label=label,
                    source_group=row["source_group"],
                    sample_id=f"{row['source_group']}_{i:04d}",
                )
            )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "wb") as fh:
        pickle.dump(samples, fh)
    print(f"kept {len(samples)}/{len(rows)} -> {OUT}")
    print(f"iris-mapping checks passed on {checked} real captures")
    for key in sorted(drops):
        print(f"  drop {key}: {drops[key]}")


if __name__ == "__main__":
    main()
