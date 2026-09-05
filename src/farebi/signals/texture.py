"""Texture / noise-residual consistency signal — Tier 1.

A face pasted into another image (or synthesised wholesale and composited)
usually mismatches its background in micro-texture: sharpness, residual
energy, or both. This signal measures Laplacian sharpness and denoising
residuals in the face versus the surrounding background and reports the
(log) mismatch, which fusion can weigh. ``numpy`` + ``opencv`` only.

Layer: L2 (may import L0, L1).
"""

from __future__ import annotations

import math

import cv2
import numpy as np
import numpy.typing as npt

from farebi.capture.capture import Capture
from farebi.core.reason_codes import Direction, ReasonCode
from farebi.signals.base import Signal, SignalOutput, reason

__all__ = ["TextureSignal"]

#: |log-ratio| beyond this flags a face/background texture mismatch.
#: Natural photos reach ~1.0 (depth of field, uneven light), so the v1 line
#: sits above all measured real photos. Starting point for harness calibration.
_RATIO_FLAG: float = 1.5
#: Minimum usable face-crop edge in px. Below this the Laplacian has too
#: little support, so the crop is rejected.
_MIN_CROP_PX: int = 32
#: Minimum background pixels for the comparison baseline. Below this the
#: variance is a small-sample artefact, so the baseline is unavailable.
_MIN_BG_PX: int = 4096


def _clip_box(
    box: tuple[int, int, int, int], width: int, height: int
) -> tuple[int, int, int, int] | None:
    x1, y1, x2, y2 = (int(v) for v in box)
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(width, x2), min(height, y2)
    if x2 - x1 < _MIN_CROP_PX or y2 - y1 < _MIN_CROP_PX:
        return None
    return (x1, y1, x2, y2)


def _laplacian_var(gray: npt.NDArray[np.float32]) -> float:
    # float32 -> CV_64F is unsupported by OpenCV's filter dispatch; float32 ->
    # float32 is, and float64 precision is recovered via the variance below.
    lap = np.asarray(cv2.Laplacian(gray, cv2.CV_32F), dtype=np.float64)
    return float(lap.var())


def _residual_energy(gray: npt.NDArray[np.float32]) -> float:
    blurred = np.asarray(cv2.GaussianBlur(gray, (0, 0), 1.0), dtype=np.float32)
    return float(np.var(gray - blurred))


def _background_stats(
    gray: npt.NDArray[np.float32], face: tuple[int, int, int, int]
) -> tuple[float, float] | None:
    """Sharpness and residual energy outside a 1.5x expanded face box."""
    height, width = gray.shape
    x1, y1, x2, y2 = face
    fw, fh = x2 - x1, y2 - y1
    ex1, ey1 = max(0, x1 - fw // 4), max(0, y1 - fh // 4)
    ex2, ey2 = min(width, x2 + fw // 4), min(height, y2 + fh // 4)
    mask = np.ones((height, width), dtype=bool)
    mask[ey1:ey2, ex1:ex2] = False
    if int(mask.sum()) < _MIN_BG_PX:
        return None
    # Per-pixel Laplacian needs a neighbourhood; approximate the background
    # sharpness on the downmasked frame is biased, so compute on the full
    # frame once and index afterwards.
    lap = np.asarray(cv2.Laplacian(gray, cv2.CV_32F), dtype=np.float64)
    blurred = np.asarray(cv2.GaussianBlur(gray, (0, 0), 1.0), dtype=np.float32)
    resid = gray - blurred
    return float(lap[mask].var()), float(np.var(resid[mask]))


def _clipped_fraction(cap: Capture) -> float:
    raw = cap.quality.get("clipped_fraction", 0.0)
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return 0.0
    return min(1.0, max(0.0, float(raw)))


class TextureSignal(Signal):
    """Face-vs-background micro-texture consistency."""

    name = "texture"
    tier = 1
    min_requirements: dict[str, float | bool] = {"min_face_px": 96.0}

    def run(self, cap: Capture) -> SignalOutput:
        box = _clip_box(cap.face_box, cap.width, cap.height)
        if box is None:
            return SignalOutput.unavailable(self.name, "face box is degenerate after clipping")
        x1, y1, x2, y2 = box
        gray = np.asarray(cv2.cvtColor(cap.image_bgr, cv2.COLOR_BGR2GRAY), dtype=np.float32)
        face = np.ascontiguousarray(gray[y1:y2, x1:x2])

        face_sharp = _laplacian_var(face)
        face_resid = _residual_energy(face)
        bg = _background_stats(gray, box)
        if bg is None:
            return SignalOutput.unavailable(self.name, "not enough background to compare against")

        bg_sharp, bg_resid = bg
        sharp_lr = math.log((face_sharp + 1.0) / (bg_sharp + 1.0))
        resid_lr = math.log((face_resid + 1.0) / (bg_resid + 1.0))

        features = {
            "texture_face_sharpness": math.log1p(face_sharp),
            "texture_bg_sharpness": math.log1p(bg_sharp),
            "texture_sharpness_logratio": sharp_lr,
            "texture_residual_logratio": resid_lr,
        }

        short_edge = min(x2 - x1, y2 - y1)
        quality = max(0.1, min(1.0, short_edge / 192.0) * (1.0 - _clipped_fraction(cap)))

        mismatch = max(abs(sharp_lr), abs(resid_lr))
        if mismatch > _RATIO_FLAG:
            direction = Direction.TOWARD_FAKE
            strength = 0.3
            message = (
                f"The face texture differs from its background "
                f"(sharpness log-ratio {sharp_lr:+.2f}, residual log-ratio {resid_lr:+.2f}), "
                f"as seen with pasted or synthesised faces."
            )
        else:
            direction = Direction.TOWARD_UNCERTAIN
            strength = 0.0
            message = (
                f"Face and background textures are consistent "
                f"(sharpness log-ratio {sharp_lr:+.2f}, residual log-ratio {resid_lr:+.2f})."
            )

        return SignalOutput(
            features=features,
            applicable=True,
            quality=quality,
            explanation=(
                f"texture face sharpness {face_sharp:.1f} vs background {bg_sharp:.1f} "
                f"(log-ratio {sharp_lr:+.2f}); residual {face_resid:.2f} vs {bg_resid:.2f} "
                f"(log-ratio {resid_lr:+.2f})."
            ),
            reason_codes=[
                reason(
                    ReasonCode.TEXTURE_INCONSISTENCY,
                    message,
                    "Depth of field, beautification and uneven lighting also split "
                    "face/background texture, so a mismatch is only a weak cue for fusion.",
                    direction=direction,
                    strength=strength,
                )
            ],
        )
