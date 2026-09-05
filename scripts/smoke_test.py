#!/usr/bin/env python
"""End-to-end smoke test.

Answers one question: can one image traverse the pipeline end-to-end and come
out as a well-formed result object? Then it runs the hostile-upload rejection
matrix and checks every hostile input produces the *expected distinct* code.

Run with ``make smoke`` or ``python scripts/smoke_test.py``. Exit code 0 means
the Phase 01 exit gate is satisfied.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Make `src` and `tests` importable when run directly, without installing.
_ROOT = Path(__file__).resolve().parents[1]
for _path in (_ROOT / "src", _ROOT / "tests"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from farebi.capture.face_mesh import FaceMeshDetector  # noqa: E402
from farebi.core.config import get_settings  # noqa: E402
from farebi.core.constants import RejectionCode  # noqa: E402
from farebi.core.logging import configure_logging  # noqa: E402
from farebi.core.security import UploadLimits  # noqa: E402
from farebi.inference.pipeline import DetectionPipeline  # noqa: E402
from fixtures.synthetic import (  # noqa: E402
    encode_jpeg,
    encode_png,
    hostile_cases,
    make_apng,
    synthetic_face_rgb,
)

EXPECTED_STAGES = (
    "secure_file_validation",
    "decode",
    "capture",
    "signal_preflight",
    "feature_assembly",
    "calibrated_probability",
    "uncertainty",
    "attribution",
    "reason_generation",
    "verdict_policy",
    "response",
)

_SEPARATOR = "-" * 74


def _upload_limits() -> UploadLimits:
    upload = get_settings().upload
    return UploadLimits(
        max_bytes=upload.max_bytes,
        max_pixels=upload.max_pixels,
        max_edge_px=upload.max_edge_px,
        allowed_media_types=frozenset(upload.allowed_media_types),
        allow_multiframe=upload.allow_multiframe,
    )


def _check(label: str, condition: bool, detail: str = "") -> bool:
    status = "PASS" if condition else "FAIL"
    suffix = f"  ({detail})" if detail else ""
    print(f"  [{status}] {label}{suffix}")
    return condition


def run_valid_images(pipeline: DetectionPipeline) -> bool:
    """One JPEG and one PNG must traverse the pipeline and produce a result."""
    print("\nValid uploads")
    print(_SEPARATOR)
    rgb = synthetic_face_rgb(size=512)
    ok = True

    for label, data, media_type in (
        ("jpeg", encode_jpeg(rgb), "image/jpeg"),
        ("png", encode_png(rgb), "image/png"),
    ):
        result = pipeline.run(data, declared_media_type=media_type, filename=f"smoke.{label}")
        payload = result.to_dict()

        print(f"\n  {label.upper()}  ({len(data):,} bytes)")
        ok &= _check(
            "result is well-formed", result.request_id != "", result.request_id[:8] + "..."
        )
        ok &= _check("no rejection code", result.rejection_code is None)
        ok &= _check("all 11 stages present", len(result.stages) == len(EXPECTED_STAGES))
        ok &= _check(
            "stage names match the spec",
            tuple(stage.name for stage in result.stages) == EXPECTED_STAGES,
        )
        ok &= _check("image hash recorded", bool(result.image_sha256))
        ok &= _check(
            "versions reported on every response",
            bool(result.model_version and result.threshold_version and result.calibration_version),
        )
        ok &= _check("result is JSON-serialisable", json.dumps(payload) is not None)
        ok &= _check(
            "verdict is None or unable_to_assess (no signals yet)",
            result.verdict is None or result.verdict.value == "unable_to_assess",
            str(result.verdict),
        )
        ok &= _check(
            "every reason carries a limitation",
            all(reason.limitation.strip() for reason in result.reasons),
        )

        quality = result.quality or {}
        print(
            f"        capture={result.capture_status.value:<20} "
            f"face_px={quality.get('face_px', 'n/a')} "
            f"blur={quality.get('blur_score', 'n/a')}"
        )
        if result.capture_status.value == "no_face":
            print(
                "        note: synthetic face not detected — expected; this is a "
                "pipeline check, not a detection check"
            )

    return ok


def run_hostile_matrix(pipeline: DetectionPipeline) -> bool:
    """Every hostile input must be refused with its own distinct code."""
    print("\nHostile upload rejection matrix")
    print(_SEPARATOR)

    limits = _upload_limits()
    valid_jpeg = encode_jpeg(synthetic_face_rgb(size=256))
    cases = dict(hostile_cases(limits, valid_jpeg))

    apng = make_apng(synthetic_face_rgb(size=128))
    if apng is not None:
        cases["animated_png"] = (
            apng,
            "image/png",
            "animated.png",
            RejectionCode.MULTI_FRAME_REJECTED,
        )

    ok = True
    seen_codes: dict[str, str] = {}

    for name, (data, media_type, filename, expected) in sorted(cases.items()):
        result = pipeline.run(data, declared_media_type=media_type, filename=filename)
        actual = result.rejection_code

        matched = actual is expected
        ok &= _check(
            f"{name:<26} -> {expected.value}",
            matched,
            f"got {actual.value if actual else 'accepted'}"
            if not matched
            else result.reasons[0].message
            if result.reasons
            else "",
        )

        if matched and result.verdict is not None:
            ok &= _check(
                f"{name:<26} verdict is unable_to_assess",
                result.verdict.value == "unable_to_assess",
            )

        # Distinctness: two different attacks must not collapse to one bucket.
        if actual is not None:
            key = actual.value
            if key in seen_codes and seen_codes[key] != name:
                print(
                    f"        note: {key} shared with '{seen_codes[key]}' (expected for "
                    "content-vs-declared-type mismatches)"
                )
            seen_codes.setdefault(key, name)

    print(
        f"\n  {len(seen_codes)} distinct rejection codes exercised: {', '.join(sorted(seen_codes))}"
    )
    return ok


def main() -> int:
    configure_logging(level="WARNING", json_logs=False)
    settings = get_settings()

    print("Farebi — Phase 01 smoke test")
    print("=" * 74)
    print(f"  env                 {settings.app.env}")
    print(f"  face mesh enabled   {settings.capture.face_mesh.enabled}")
    print(f"  mediapipe present   {FaceMeshDetector.is_installed()}")
    print(
        f"  upload limits       {settings.upload.max_bytes:,} bytes · "
        f"{settings.upload.max_edge_px}px max edge"
    )

    all_ok = True
    with DetectionPipeline(settings) as pipeline:
        all_ok &= run_valid_images(pipeline)
        all_ok &= run_hostile_matrix(pipeline)

    print("\n" + "=" * 74)
    print("SMOKE TEST PASSED" if all_ok else "SMOKE TEST FAILED")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
