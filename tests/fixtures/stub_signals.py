"""Stub signals for harness tests — the gate's calibration weights.

These exist to prove the go/no-go gate discriminates, in both directions:

* :class:`NoiseSignal` emits pure noise. The gate must **KILL** it. If it did
  not, the gate would be decorative.
* :class:`EncodedSignal` reads a label-encoded brightness level. The gate must
  **KEEP** it. If it did not, the gate would be rejecting everything.
* :class:`PartialSignal` is strong but only applicable on a minority of samples.
  The gate must **BENCH** it, exercising the coverage half of the rule.

They live in ``tests/`` and are never auto-discovered by the registry (which
scans ``farebi.signals``), so they cannot ship.

The label is encoded as whole-image brightness rather than as a positioned
patch, because :class:`KYCDegradation` resizes: a fixed pixel offset would move.
A brightness gap of ~120 levels survives AWB jitter (+-10%) and double JPEG.
"""

from __future__ import annotations

from typing import Final

import numpy as np
import numpy.typing as npt

from farebi.harness.evaluate_signal import Sample
from farebi.signals.base import Signal, SignalOutput, reason
from farebi.capture.capture import Capture
from farebi.core.reason_codes import Direction, ReasonCode

__all__ = [
    "REAL_GROUPS",
    "FAKE_GROUPS",
    "EncodedSignal",
    "NoiseSignal",
    "PartialSignal",
    "make_samples",
]

REAL_LEVEL: Final = 70
FAKE_LEVEL: Final = 190
IMAGE_SIZE: Final = 256

#: Source groups. Three real + three fake, each side class-pure. The splitter
#: (farebi.harness.splits) needs at least ``n_splits`` groups per side, so the
#: self-test uses ``n_splits=3`` (not the harness default of 5).
REAL_GROUPS: Final[tuple[str, ...]] = ("cam_iphone", "cam_pixel", "cam_dslr")
FAKE_GROUPS: Final[tuple[str, ...]] = ("gen_stylegan", "gen_diffusion", "gen_faceswap")


def _render(label: int, rng: np.random.Generator) -> npt.NDArray[np.uint8]:
    """Render a synthetic capture whose mean brightness encodes ``label``."""
    base = REAL_LEVEL if label == 0 else FAKE_LEVEL
    # A gradient gives JPEG and blur something to act on; flat fields would make
    # the degradation a no-op and flatter the signal.
    ramp = np.linspace(-12.0, 12.0, IMAGE_SIZE, dtype=np.float64)
    field = base + ramp[:, None] + ramp[None, :] * 0.5
    speckle = rng.normal(0.0, 2.5, (IMAGE_SIZE, IMAGE_SIZE))
    rgb = np.clip(field[:, :, None] + speckle[:, :, None], 0, 255).astype(np.uint8)
    return np.ascontiguousarray(np.repeat(rgb, 3, axis=2))


def _capture(
    label: int, rng: np.random.Generator, *, eligible: bool = True
) -> Capture:
    rgb = _render(label, rng)
    face = IMAGE_SIZE // 2
    return Capture(
        image_bgr=np.ascontiguousarray(rgb[:, :, ::-1]),
        face_box=(face - 64, face - 64, face + 64, face + 64),
        landmarks=np.zeros((0, 3), dtype=np.float32),
        quality={
            "blur_score": 100.0,
            "exposure": 0.5,
            "clipped_fraction": 0.0,
            "face_width_px": 128,
            "face_height_px": 128,
            "face_px": 128,
            "interocular_px": None,
            "eye_width_px": None,
            "occlusion_estimate": 0.0,
            "usable": True,
            "failed_gates": [],
        },
        sdk_meta={"eligible": eligible},
    )


def make_samples(
    *,
    per_group: int = 10,
    seed: int = 1337,
    partial_fraction: float = 0.3,
) -> list[Sample]:
    """Build a balanced, source-grouped evaluation set.

    Real groups contribute label 0, fake groups label 1, so every group is
    class-pure — the realistic case, and the one the splitter is built for.
    """
    rng = np.random.default_rng(seed)
    samples: list[Sample] = []
    for group in REAL_GROUPS:
        for i in range(per_group):
            eligible = bool(rng.random() < partial_fraction)
            samples.append(
                Sample(
                    capture=_capture(0, rng, eligible=eligible),
                    label=0,
                    source_group=group,
                    sample_id=f"{group}-{i}",
                )
            )
    for group in FAKE_GROUPS:
        for i in range(per_group):
            eligible = bool(rng.random() < partial_fraction)
            samples.append(
                Sample(
                    capture=_capture(1, rng, eligible=eligible),
                    label=1,
                    source_group=group,
                    sample_id=f"{group}-{i}",
                )
            )
    return samples


class NoiseSignal(Signal):
    """An information-free feature. Must be reported as KILL.

    It emits the same constant for every capture, so the score carries no class
    signal: AUC is exactly 0.5 and the gate must KILL it. (Per-sample random
    noise is *not* used here: with only three source groups per side the
    fold-averaged AUC of genuine noise is too noisy to assert on reliably.)
    """

    name = "stub_noise"
    tier = 1

    def run(self, cap: Capture) -> SignalOutput:
        return SignalOutput(
            features={"constant": 0.5},
            applicable=True,
            quality=1.0,
            explanation="constant feature = 0.500 (no information)",
            reason_codes=[
                reason(
                    ReasonCode.OUT_OF_DISTRIBUTION,
                    "This stub emits a constant feature that carries no information.",
                    "It exists to prove the harness rejects uninformative features.",
                    direction=Direction.TOWARD_UNCERTAIN,
                    strength=0.0,
                )
            ],
        )


class EncodedSignal(Signal):
    """Reads the brightness level that encodes the label. Must be KEEP."""

    name = "stub_encoded"
    tier = 1

    def run(self, cap: Capture) -> SignalOutput:
        luma = float(cap.image_rgb.mean())
        return SignalOutput(
            features={"mean_luma": luma},
            applicable=True,
            quality=1.0,
            explanation=f"mean luma = {luma:.1f}",
            reason_codes=[
                reason(
                    ReasonCode.TEXTURE_INCONSISTENCY,
                    f"Overall brightness measured at {luma:.1f}.",
                    "Brightness depends on scene lighting and exposure as much as on "
                    "the subject, so this stub is a test double and not a real signal.",
                    direction=Direction.TOWARD_UNCERTAIN,
                    strength=0.0,
                )
            ],
        )


class PartialSignal(Signal):
    """Strong but rarely applicable. Must be BENCH, not KEEP."""

    name = "stub_partial"
    tier = 2

    def run(self, cap: Capture) -> SignalOutput:
        if not bool(cap.sdk_meta.get("eligible", False)):
            return SignalOutput.unavailable(self.name, "sample not eligible for this stub")
        luma = float(cap.image_rgb.mean())
        return SignalOutput(
            features={"eligible_luma": luma},
            applicable=True,
            quality=1.0,
            explanation=f"mean luma on an eligible sample = {luma:.1f}",
            reason_codes=[
                reason(
                    ReasonCode.TEXTURE_INCONSISTENCY,
                    f"Overall brightness measured at {luma:.1f}.",
                    "Stub signal: brightness is not evidence of manipulation by itself.",
                    direction=Direction.TOWARD_UNCERTAIN,
                    strength=0.0,
                )
            ],
        )
