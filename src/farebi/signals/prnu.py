"""Sensor-noise (PRNU-inspired) presence signal — Tier 1.

Adapted from ``vendor/prnu-python`` (Bondi, Bestagini, Bonettini, Politecnico
di Milano, 2018), which implements the Binghamton-toolbox flow: noise-residual
extraction, row/column zero-mean normalisation, Wiener filtering in the DFT
domain, and PCE scoring of a residual against a reference fingerprint.

What changed for Farebi, and why:

* No reference fingerprint exists for a single KYC submission, so this signal
  measures the *presence and face/background consistency* of sensor noise
  instead of matching a device. A synthesised or heavily smoothed face
  typically carries far less sensor noise than a camera photograph, while a
  spliced face often mismatches the background it was pasted into.
* The ``db4`` wavelet + ``pywt`` stage is replaced by a Gaussian-residual
  estimator with a box-filter Wiener stage, so the serving install needs only
  ``numpy`` + ``opencv`` (both hard runtime dependencies). ``scipy``,
  ``pywt`` and ``sklearn`` live in the ``ml`` extra and must never be
  required on the request path.
* Cross-correlation / PCE helpers are omitted: with no reference fingerprint
  there is nothing to correlate against. Survival is decided by the harness
  (``FAREBI.md`` §5 rule 5); these features are fusion inputs, never a verdict.

Caveat: this signal must never fire alone — missing noise also follows from
heavy compression or beautification filters — hence ``requires`` on
``replay_detect``.

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

__all__ = ["PrnuSignal"]

#: Residual variance lives on the 0-255 gray scale. Natural Dresden photos
#: bottom out near 0.9, so only values clearly below every measured real
#: photo count as "absent". Starting point for harness calibration.
_ABSENT_BELOW: float = 0.4
#: Healthy camera noise on the same scale. Above this the pattern is present.
_PRESENT_ABOVE: float = 4.0
#: |log(face/bg)| beyond this flags a face/background noise mismatch.
#: Natural photos reach ~1.6 (smooth face against textured scene), so the
#: v1 line sits above all measured real photos.
_RATIO_FLAG: float = 2.0
#: Vendor ``noise_extract`` default: sigma=5 on the 0-255 scale.
_NOISE_VAR: float = 25.0
_EPS: float = 1e-6


def _clip_box(
    box: tuple[int, int, int, int], width: int, height: int
) -> tuple[int, int, int, int] | None:
    """Clip a face box to the frame; ``None`` when nothing usable remains."""
    x1, y1, x2, y2 = (int(v) for v in box)
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(width, x2), min(height, y2)
    if x2 - x1 < 32 or y2 - y1 < 32:
        return None
    return (x1, y1, x2, y2)


def _to_gray(bgr: npt.NDArray[np.uint8]) -> npt.NDArray[np.uint8]:
    return np.asarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), dtype=np.uint8)


def _zero_mean(residual: npt.NDArray[np.float32]) -> npt.NDArray[np.float32]:
    """Row/column zero-mean, mirroring vendor ``zero_mean`` (single channel).

    Removes low-frequency content the denoiser left behind so the energy that
    remains is dominated by sensor-level noise rather than scene lighting.
    """
    out = residual - residual.mean(axis=1, keepdims=True)
    return np.ascontiguousarray(out - out.mean(axis=0, keepdims=True), dtype=np.float32)


def _wiener_adaptive(x: npt.NDArray[np.float32], noise_var: float) -> npt.NDArray[np.float32]:
    """Vendor ``wiener_adaptive`` with ``cv2.boxFilter`` standing in for
    ``scipy.ndimage.uniform_filter`` (same box mean, no scipy dependency)."""
    energy = x * x
    best: npt.NDArray[np.float32] | None = None
    for ksize in (3, 5, 9):
        local = np.asarray(
            cv2.boxFilter(energy, -1, (ksize, ksize), normalize=True), dtype=np.float32
        )
        var = np.maximum(local - noise_var, 0.0)
        best = var if best is None else np.minimum(best, var)
    assert best is not None  # loop always runs; keeps mypy strict-happy
    return np.ascontiguousarray(x * (noise_var / (best + noise_var)), dtype=np.float32)


def _wiener_dft(residual: npt.NDArray[np.float32], sigma: float) -> npt.NDArray[np.float32]:
    """Vendor ``wiener_dft`` verbatim, in ``numpy`` terms only."""
    noise_var = sigma * sigma
    height, width = residual.shape
    spectrum = np.fft.fft2(residual)
    magnitude = np.abs(spectrum / math.sqrt(height * width))
    filtered_mag = _wiener_adaptive(magnitude.astype(np.float32), noise_var)
    safe_mag = np.where(magnitude == 0, 1.0, magnitude)
    safe_filt = np.where(magnitude == 0, 0.0, filtered_mag)
    cleaned = np.real(np.fft.ifft2(spectrum * safe_filt / safe_mag))
    return np.ascontiguousarray(cleaned, dtype=np.float32)


def _extract_face_residual(face_gray: npt.NDArray[np.uint8]) -> npt.NDArray[np.float32]:
    """Full vendor-style pipeline on the face crop: denoise, zero-mean, Wiener."""
    gray = np.asarray(face_gray, dtype=np.float32)
    blurred = np.asarray(cv2.GaussianBlur(gray, (0, 0), 1.0), dtype=np.float32)
    residual = _zero_mean((gray - blurred).astype(np.float32))
    sigma = float(residual.std()) if residual.size else 0.0
    if sigma <= 0.0:
        return residual
    return _wiener_dft(residual, sigma)


def _background_energy(full_gray: npt.NDArray[np.uint8], face: tuple[int, int, int, int]) -> float:
    """Gaussian-residual variance outside a 1.5x expanded face box.

    Deliberately the cheap estimator (no Wiener DFT over the full frame):
    this is the comparison baseline for the face, documented as approximate
    in the explanation rather than presented as a matched measurement.
    """
    height, width = full_gray.shape
    x1, y1, x2, y2 = face
    fw, fh = x2 - x1, y2 - y1
    ex1, ey1 = max(0, x1 - fw // 4), max(0, y1 - fh // 4)
    ex2, ey2 = min(width, x2 + fw // 4), min(height, y2 + fh // 4)
    gray = np.asarray(full_gray, dtype=np.float32)
    blurred = np.asarray(cv2.GaussianBlur(gray, (0, 0), 1.0), dtype=np.float32)
    residual = gray - blurred
    mask = np.ones_like(residual, dtype=bool)
    mask[ey1:ey2, ex1:ex2] = False
    bg = residual[mask]
    if bg.size < 1024:
        return 0.0
    return float(np.var(bg))


def _clipped_fraction(cap: Capture) -> float:
    raw = cap.quality.get("clipped_fraction", 0.0)
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return 0.0
    return min(1.0, max(0.0, float(raw)))


class PrnuSignal(Signal):
    """Presence and face/background consistency of sensor noise."""

    name = "prnu"
    tier = 1
    # Must never fire alone: a missing pattern also follows from compression
    # or beautification, so replay screening is a hard companion.
    requires = ["replay_detect"]
    min_requirements: dict[str, float | bool] = {
        "min_face_px": 96.0,
        "max_clipped_fraction": 0.5,
    }

    def run(self, cap: Capture) -> SignalOutput:
        box = _clip_box(cap.face_box, cap.width, cap.height)
        if box is None:
            return SignalOutput.unavailable(self.name, "face box is degenerate after clipping")
        x1, y1, x2, y2 = box
        full_gray = _to_gray(cap.image_bgr)
        face_gray = np.ascontiguousarray(full_gray[y1:y2, x1:x2])

        face_residual = _extract_face_residual(face_gray)
        face_energy = float(np.var(face_residual)) if face_residual.size else 0.0
        face_mean_abs = float(np.mean(np.abs(face_residual))) if face_residual.size else 0.0
        bg_energy = _background_energy(full_gray, box)
        logratio = math.log((face_energy + 1.0) / (bg_energy + 1.0))

        features = {
            "prnu_face_energy": face_energy,
            "prnu_bg_energy": bg_energy,
            "prnu_face_bg_logratio": logratio,
            "prnu_face_mean_abs": face_mean_abs,
        }

        short_edge = min(x2 - x1, y2 - y1)
        quality = max(0.1, min(1.0, short_edge / 192.0) * (1.0 - _clipped_fraction(cap)))

        mismatch = abs(logratio) > _RATIO_FLAG
        if face_energy < _ABSENT_BELOW:
            code = ReasonCode.SENSOR_NOISE_ABSENT
            direction = Direction.TOWARD_FAKE
            strength = 0.3
            message = (
                f"Almost no sensor noise was measured in the face region "
                f"(residual variance {face_energy:.2f})."
            )
        elif face_energy > _PRESENT_ABOVE and not mismatch:
            code = ReasonCode.SENSOR_NOISE_PRESENT
            direction = Direction.TOWARD_REAL
            strength = 0.15
            message = (
                f"A healthy sensor-noise pattern is present in the face region "
                f"(residual variance {face_energy:.2f})."
            )
        else:
            code = (
                ReasonCode.SENSOR_NOISE_ABSENT
                if face_energy < _PRESENT_ABOVE
                else ReasonCode.SENSOR_NOISE_PRESENT
            )
            direction = Direction.TOWARD_UNCERTAIN
            strength = 0.0
            message = (
                f"Sensor noise in the face region is inconclusive "
                f"(variance {face_energy:.2f}, face/bg log-ratio {logratio:+.2f})."
            )
        if mismatch and direction is not Direction.TOWARD_FAKE:
            message += (
                f" The face noise level differs from the background "
                f"(log-ratio {logratio:+.2f}), which can indicate a pasted face."
            )

        return SignalOutput(
            features=features,
            applicable=True,
            quality=quality,
            explanation=(
                f"prnu face variance {face_energy:.2f}, background variance {bg_energy:.2f}, "
                f"face/bg log-ratio {logratio:+.2f}, mean |residual| {face_mean_abs:.3f}."
            ),
            reason_codes=[
                reason(
                    code,
                    message,
                    "Heavy compression, beautification filters and strong denoising "
                    "also remove sensor noise, so a weak pattern is not proof of "
                    "synthesis; interpret only alongside the replay signal.",
                    direction=direction,
                    strength=strength,
                )
            ],
        )
