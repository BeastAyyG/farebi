"""Screen-replay (moiré / periodic-pattern) signal — Tier 1.

Photographing a screen superimposes the display grid on the image: periodic
moiré beating and excess mid-band spectral energy. This signal hunts exactly
that structure in the face spectrum with ``numpy`` + ``opencv`` only.

It is also the mandatory companion of ``prnu`` (which ``requires`` it): a
missing sensor pattern means something different on a screen photo than on a
direct capture, so PRNU must never be interpreted without this screening.

Layer: L2 (may import L0, L1).
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from farebi.capture.capture import Capture
from farebi.core.reason_codes import Direction, ReasonCode
from farebi.signals.base import Signal, SignalOutput, reason

__all__ = ["ReplayDetectSignal"]

_EPS: float = 1e-6


def _clip_box(
    box: tuple[int, int, int, int], width: int, height: int
) -> tuple[int, int, int, int] | None:
    x1, y1, x2, y2 = (int(v) for v in box)
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(width, x2), min(height, y2)
    if x2 - x1 < 32 or y2 - y1 < 32:
        return None
    return (x1, y1, x2, y2)


def _moire_scores(face_gray: npt.NDArray[np.uint8]) -> tuple[float, float]:
    """Return ``(peak_ratio, midband_ratio)`` for the face crop."""
    gray = np.asarray(face_gray, dtype=np.float64)
    gray -= gray.mean()
    mag = np.abs(np.fft.fftshift(np.fft.fft2(gray)))
    height, width = mag.shape
    yy, xx = np.mgrid[0:height, 0:width]
    radius = np.sqrt(
        ((xx - width / 2) / (width / 2)) ** 2 + ((yy - height / 2) / (height / 2)) ** 2
    )
    radius = radius / float(np.sqrt(2.0))
    # Moiré beating lives in the low/mid bands (display pitch is a few px);
    # keep the DC neighbourhood out so the peak cannot be the image mean.
    band = mag[(radius > 0.05) & (radius < 0.45)]
    if band.size == 0:
        return 1.0, 0.0
    peak_ratio = float(band.max() / (np.median(band) + _EPS))
    midband_ratio = float(band.sum() / (float(mag.sum()) + _EPS))
    return peak_ratio, midband_ratio


def _clipped_fraction(cap: Capture) -> float:
    raw = cap.quality.get("clipped_fraction", 0.0)
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return 0.0
    return min(1.0, max(0.0, float(raw)))


class ReplayDetectSignal(Signal):
    """Periodic screen-grid / moiré structure in the face region."""

    name = "replay_detect"
    tier = 1
    min_requirements: dict[str, float | bool] = {"min_face_px": 96.0}

    def run(self, cap: Capture) -> SignalOutput:
        box = _clip_box(cap.face_box, cap.width, cap.height)
        if box is None:
            return SignalOutput.unavailable(self.name, "face box is degenerate after clipping")
        x1, y1, x2, y2 = box
        # BGR->gray without cv2 (numpy only): the standard luma weights.
        bgr = cap.image_bgr[y1:y2, x1:x2].astype(np.float64)
        face_gray = np.ascontiguousarray(
            0.114 * bgr[:, :, 0] + 0.587 * bgr[:, :, 1] + 0.299 * bgr[:, :, 2]
        ).astype(np.uint8)

        peak_ratio, midband_ratio = _moire_scores(face_gray)
        features = {
            "replay_moire_peak": peak_ratio,
            "replay_midband_ratio": midband_ratio,
        }

        short_edge = min(x2 - x1, y2 - y1)
        quality = max(0.1, min(1.0, short_edge / 192.0) * (1.0 - _clipped_fraction(cap)))

        # Both scores are fusion features only in v1: natural photos reach
        # hundreds of x (Dresden sample: 28-425x), so no peak height can lean
        # toward replay without replay-side calibration data. The replay
        # simulator (ReplayConfig) exists to generate that data for the
        # harness, which then sets the boundary.
        direction = Direction.TOWARD_UNCERTAIN
        strength = 0.0
        message = (
            f"Screen-pattern scores measured "
            f"(moiré peak {peak_ratio:.1f}x, mid-band share {midband_ratio:.3f}); "
            f"uncalibrated in v1, reported for fusion."
        )

        return SignalOutput(
            features=features,
            applicable=True,
            quality=quality,
            explanation=(
                f"replay moiré peak {peak_ratio:.1f}x, mid-band share {midband_ratio:.3f}."
            ),
            reason_codes=[
                reason(
                    ReasonCode.SCREEN_REPLAY_INDICATOR,
                    message,
                    "Finely textured fabrics and fences also produce periodic "
                    "peaks, so this is a screening cue for fusion, not proof of replay.",
                    direction=direction,
                    strength=strength,
                )
            ],
        )
