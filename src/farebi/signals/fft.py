"""Frequency-domain artifact signal — Tier 1.

Generative upsampling leaves tell-tale structure in the Fourier spectrum
(replicated spectra, anomalous high-frequency peaks), while JPEG
recompression leaves 8x8 block discontinuities. Both are measurable with
``numpy`` + ``opencv`` only, which keeps this signal on the serving path.

Features are spectral measurements, never a verdict: recompression and
resizing also reshape spectra, so the harness (``FAREBI.md`` §5 rule 5)
decides whether any of this survives.

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

__all__ = ["FftSignal"]

#: Flag when the 8x8 grid discontinuity exceeds this. Single-compressed camera
#: photos measure ~1.0-1.15 (Dresden sample: max 1.12); well above that means
#: mixed compression history, as left by a re-saved splice. Starting point for
#: harness calibration, not a tuned boundary.
_BLOCK_FLAG: float = 1.8
_EPS: float = 1e-6
#: Minimum usable face-crop edge in px. Below this the spectrum has too few
#: bins for band shares to mean anything, so the crop is rejected.
_MIN_CROP_PX: int = 32
#: High-band edge as a fraction of Nyquist (corner == 1.0). Band edges are
#: methodology constants, not decision thresholds: they define the feature,
#: while the lean/no-lean line lives in ``_BLOCK_FLAG`` above.
_HIGH_BAND_R: float = 0.4
#: Mid/high-band edge, same status as ``_HIGH_BAND_R``.
_MIDHIGH_BAND_R: float = 0.15
#: Minimum edge for the 8x8 block estimate: needs at least two block rows/cols.
_MIN_BLOCK_PX: int = 16


def _clip_box(
    box: tuple[int, int, int, int], width: int, height: int
) -> tuple[int, int, int, int] | None:
    x1, y1, x2, y2 = (int(v) for v in box)
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(width, x2), min(height, y2)
    if x2 - x1 < _MIN_CROP_PX or y2 - y1 < _MIN_CROP_PX:
        return None
    return (x1, y1, x2, y2)


def _spectrum(face_gray: npt.NDArray[np.uint8]) -> npt.NDArray[np.float64]:
    gray = np.asarray(face_gray, dtype=np.float64)
    gray -= gray.mean()
    return np.abs(np.fft.fftshift(np.fft.fft2(gray)))


def _radial_bands(
    mag: npt.NDArray[np.float64],
) -> tuple[npt.NDArray[np.bool_], npt.NDArray[np.bool_]]:
    """Masks for the high band (r > 0.4 Nyquist) and the mid/high band."""
    height, width = mag.shape
    yy, xx = np.mgrid[0:height, 0:width]
    radius = np.sqrt(
        ((xx - width / 2) / (width / 2)) ** 2 + ((yy - height / 2) / (height / 2)) ** 2
    )
    radius = radius / math.sqrt(2.0)  # corner == 1.0
    return (radius > _HIGH_BAND_R), (radius > _MIDHIGH_BAND_R)


def _blockiness(face: npt.NDArray[np.float64]) -> float:
    """8x8 JPEG-block edge discontinuity vs interior discontinuity.

    ``1.0`` means block edges look like any other pixel boundary; well above
    ``1.0`` means the 8x8 grid is visible (recompression history or a pasted
    region with different compression).
    """
    height, width = face.shape
    if height < _MIN_BLOCK_PX or width < _MIN_BLOCK_PX:
        return 1.0
    vert = np.abs(np.diff(face, axis=1))
    edge_cols = np.array([(j + 1) % 8 == 0 for j in range(vert.shape[1])])
    horiz = np.abs(np.diff(face, axis=0))
    edge_rows = np.array([(i + 1) % 8 == 0 for i in range(horiz.shape[0])])
    v_edge = float(vert[:, edge_cols].mean()) if edge_cols.any() else 0.0
    v_in = float(vert[:, ~edge_cols].mean()) if (~edge_cols).any() else 0.0
    h_edge = float(horiz[edge_rows, :].mean()) if edge_rows.any() else 0.0
    h_in = float(horiz[~edge_rows, :].mean()) if (~edge_rows).any() else 0.0
    return ((v_edge + h_edge) / 2.0 + _EPS) / ((v_in + h_in) / 2.0 + _EPS)


def _clipped_fraction(cap: Capture) -> float:
    raw = cap.quality.get("clipped_fraction", 0.0)
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return 0.0
    return min(1.0, max(0.0, float(raw)))


class FftSignal(Signal):
    """High-frequency spectral peaks and JPEG-block structure of the face."""

    name = "fft"
    tier = 1
    min_requirements: dict[str, float | bool] = {"min_face_px": 96.0}

    def run(self, cap: Capture) -> SignalOutput:
        box = _clip_box(cap.face_box, cap.width, cap.height)
        if box is None:
            return SignalOutput.unavailable(self.name, "face box is degenerate after clipping")
        x1, y1, x2, y2 = box
        gray_u8 = np.asarray(cv2.cvtColor(cap.image_bgr, cv2.COLOR_BGR2GRAY), dtype=np.uint8)
        face_u8 = np.ascontiguousarray(gray_u8[y1:y2, x1:x2])
        face = np.asarray(face_u8, dtype=np.float64)

        mag = _spectrum(face_u8)
        high_mask, midhigh_mask = _radial_bands(mag)
        total = float(mag.sum()) + _EPS
        high_ratio = float(mag[high_mask].sum()) / total
        band = mag[midhigh_mask]
        peak = float(band.max() / (np.median(band) + _EPS)) if band.size else 1.0
        block = _blockiness(face)

        features = {
            "fft_high_freq_ratio": high_ratio,
            "fft_spectral_peak": peak,
            "fft_blockiness": block,
        }

        short_edge = min(x2 - x1, y2 - y1)
        quality = max(0.1, min(1.0, short_edge / 192.0) * (1.0 - _clipped_fraction(cap)))

        # The spectral peak is a fusion feature only: natural photos reach
        # hundreds of x (Dresden sample: 80-330x), so no peak height can lean
        # toward fake without fake-side calibration data. Only the block grid,
        # which is ~1.0-1.15 on single-compressed photos, gets a weak voice.
        if block > _BLOCK_FLAG:
            direction = Direction.TOWARD_FAKE
            strength = 0.25
            message = (
                f"The 8x8 compression grid is strongly visible in the face "
                f"(blockiness {block:.2f}), suggesting mixed compression history."
            )
        else:
            direction = Direction.TOWARD_UNCERTAIN
            strength = 0.0
            message = (
                f"The face spectrum is unremarkable "
                f"(peak {peak:.1f}x, high-band share {high_ratio:.3f}, "
                f"blockiness {block:.2f})."
            )

        return SignalOutput(
            features=features,
            applicable=True,
            quality=quality,
            explanation=(
                f"fft high-band share {high_ratio:.3f}, spectral peak {peak:.1f}x, "
                f"blockiness {block:.2f}."
            ),
            reason_codes=[
                reason(
                    ReasonCode.FREQUENCY_ARTIFACT,
                    message,
                    "Ordinary recompression, resizing and screen capture also reshape "
                    "spectra, so peaks alone never identify a fake; the harness "
                    "decides whether this feature survives.",
                    direction=direction,
                    strength=strength,
                )
            ],
        )
