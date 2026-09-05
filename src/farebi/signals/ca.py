"""Chromatic-aberration radial-profile signal — Tier 1.

A real lens disperses colour: lateral fringing at high-contrast edges grows
with distance from the optical centre. AI-generated images either show no
chromatic aberration at all (too perfect) or a spatially uniform residue
rather than a radius-dependent profile.

This signal measures per-edge R-G / B-G channel-centroid shifts in annular
bands and fits the radial slope. It runs on the **full frame**, before any
face crop, because the effect lives strongest at image edges.

Caveat, stated plainly: modern flagship ISPs correct lateral CA in software,
so a flat profile also describes a genuine phone photo. The slope bands below
are starting points for harness calibration, not tuned boundaries, and the
harness (``FAREBI.md`` §5 rule 5) decides survival.

Layer: L2 (may import L0, L1).
"""

from __future__ import annotations

import cv2
import numpy as np
import numpy.typing as npt

from farebi.capture.capture import Capture
from farebi.core.reason_codes import Direction, ReasonCode
from farebi.signals.base import Signal, SignalOutput, reason

__all__ = ["ChromaticAberrationSignal"]

#: Frames smaller than this carry no measurable edge population.
_MIN_EDGE_PX: int = 256
#: Canny hysteresis thresholds on the green channel.
_CANNY_LO: int = 50
_CANNY_HI: int = 150
#: Half-size of the centroid patch around each sampled edge pixel.
_PATCH_HALF: int = 3
#: At most this many edge pixels are sampled (deterministic stride).
_MAX_PATCHES: int = 5000
#: Fewer usable patches than this and there is nothing to fit.
_MIN_PATCHES: int = 100
#: Annular bands across the frame radius; need this many populated bands.
_N_BANDS: int = 8
_MIN_BANDS: int = 3
#: A band counts when it holds at least this many patch measurements.
_MIN_PER_BAND: int = 10
#: Mean slope at/above this reads as a real-lens radial profile.
_SLOPE_REAL_ABOVE: float = 0.08
#: Mean slope at/below this reads as flat (AI-like or ISP-corrected).
_SLOPE_FAKE_BELOW: float = 0.02
#: Very strong but flat CA gets a small extra lean (uniform residue).
_FLAT_CA_ABOVE: float = 0.8
_FLAT_CA_BONUS: float = 0.15
_REAL_STRENGTH: float = 0.15
_FAKE_STRENGTH: float = 0.2


def _sample_edges(edges: npt.NDArray[np.uint8]) -> tuple[npt.NDArray[np.intp], ...]:
    """Edge-pixel coordinates, deterministically stride-subsampled."""
    ys, xs = np.nonzero(edges)
    if len(xs) > _MAX_PATCHES:
        step = max(1, len(xs) // _MAX_PATCHES)
        xs, ys = xs[::step], ys[::step]
    return xs, ys


def _channel_shifts(
    img_f: npt.NDArray[np.float32],
    green: npt.NDArray[np.float32],
    xs: npt.NDArray[np.intp],
    ys: npt.NDArray[np.intp],
    width: int,
    height: int,
) -> tuple[list[float], list[float], list[float]]:
    """Per-edge R-G / B-G centroid shifts and radii from the frame centre."""
    half = _PATCH_HALF
    cx, cy = width / 2.0, height / 2.0
    b_ch = img_f[:, :, 0]
    r_ch = img_f[:, :, 2]
    yy, xx = np.mgrid[-half : half + 1, -half : half + 1]
    rg_shifts: list[float] = []
    bg_shifts: list[float] = []
    radii: list[float] = []
    for x, y in zip(xs.tolist(), ys.tolist(), strict=True):
        if x < half or x >= width - half or y < half or y >= height - half:
            continue
        patch_g = green[y - half : y + half + 1, x - half : x + half + 1]
        patch_r = r_ch[y - half : y + half + 1, x - half : x + half + 1]
        patch_b = b_ch[y - half : y + half + 1, x - half : x + half + 1]
        tot_g = float(patch_g.sum())
        tot_r = float(patch_r.sum())
        tot_b = float(patch_b.sum())
        if tot_g < 1.0 or tot_r < 1.0 or tot_b < 1.0:
            continue
        cgx = float((patch_g * xx).sum()) / tot_g
        cgy = float((patch_g * yy).sum()) / tot_g
        crx = float((patch_r * xx).sum()) / tot_r
        cry = float((patch_r * yy).sum()) / tot_r
        cbx = float((patch_b * xx).sum()) / tot_b
        cby = float((patch_b * yy).sum()) / tot_b
        rg_shifts.append(float(np.hypot(crx - cgx, cry - cgy)))
        bg_shifts.append(float(np.hypot(cbx - cgx, cby - cgy)))
        radii.append(float(np.hypot(x - cx, y - cy)))
    return rg_shifts, bg_shifts, radii


def _band_means(
    radii: npt.NDArray[np.float64],
    shifts: npt.NDArray[np.float64],
    max_r: float,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Mean shift per populated annular band and the band centres."""
    edges = np.linspace(0.0, max_r, _N_BANDS + 1)
    centres: list[float] = []
    means: list[float] = []
    for i in range(_N_BANDS):
        inside = (radii >= edges[i]) & (radii < edges[i + 1])
        if int(inside.sum()) >= _MIN_PER_BAND:
            centres.append((edges[i] + edges[i + 1]) / 2.0)
            means.append(float(shifts[inside].mean()))
    return np.asarray(centres), np.asarray(means)


class ChromaticAberrationSignal(Signal):
    """Radial profile of lateral chromatic aberration over the full frame."""

    name = "chromatic_aberration"
    tier = 1
    # Full-frame measurement: the internal size gate below is the only guard,
    # mirroring the internal face-box check in the FFT signal.
    min_requirements: dict[str, float | bool] = {}

    def run(self, cap: Capture) -> SignalOutput:
        img = np.asarray(cap.image_bgr)
        height, width = img.shape[:2]
        if min(height, width) < _MIN_EDGE_PX:
            return SignalOutput.unavailable(
                self.name, f"frame too small for CA analysis ({width}x{height})"
            )

        img_f = np.asarray(img, dtype=np.float32)
        green = np.ascontiguousarray(img_f[:, :, 1])
        edges = cv2.Canny(green.astype(np.uint8), _CANNY_LO, _CANNY_HI)
        if int((edges > 0).sum()) < _MIN_PATCHES:
            return SignalOutput.unavailable(self.name, "insufficient edge content for CA analysis")

        xs, ys = _sample_edges(np.asarray(edges > 0, dtype=np.uint8) * np.uint8(255))
        rg, bg, radii = _channel_shifts(img_f, green, xs, ys, width, height)
        if len(radii) < _MIN_PATCHES:
            return SignalOutput.unavailable(
                self.name, "too few usable edge patches for CA estimation"
            )

        max_r = float(np.hypot(width / 2.0, height / 2.0))
        radii_a = np.asarray(radii, dtype=np.float64)
        rg_a = np.asarray(rg, dtype=np.float64)
        bg_a = np.asarray(bg, dtype=np.float64)
        band_r_rg, band_rg = _band_means(radii_a, rg_a, max_r)
        _, band_bg = _band_means(radii_a, bg_a, max_r)
        if len(band_r_rg) < _MIN_BANDS or len(band_bg) < _MIN_BANDS:
            return SignalOutput.unavailable(
                self.name, "insufficient spatial coverage for a radial CA fit"
            )

        rg_slope = float(np.polyfit(band_r_rg / max_r, band_rg, 1)[0])
        bg_slope = float(np.polyfit(band_r_rg / max_r, band_bg, 1)[0])
        mean_ca = float((band_rg.mean() + band_bg.mean()) / 2.0)
        slope_avg = (rg_slope + bg_slope) / 2.0

        features = {
            "ca_rg_slope": rg_slope,
            "ca_bg_slope": bg_slope,
            "ca_slope_avg": slope_avg,
            "ca_mean": mean_ca,
            "ca_edge_patches": float(len(radii)),
        }
        quality = min(1.0, len(band_r_rg) / _N_BANDS)

        if slope_avg >= _SLOPE_REAL_ABOVE:
            direction = Direction.TOWARD_REAL
            strength = _REAL_STRENGTH
            message = (
                f"Chromatic aberration grows toward the frame edges "
                f"(RG slope {rg_slope:.3f}, BG slope {bg_slope:.3f}), the "
                f"profile of a real lens."
            )
        elif slope_avg <= _SLOPE_FAKE_BELOW:
            direction = Direction.TOWARD_FAKE
            strength = _FAKE_STRENGTH
            if mean_ca > _FLAT_CA_ABOVE:
                strength = min(1.0, strength + _FLAT_CA_BONUS)
            message = (
                f"Chromatic aberration is flat across the frame "
                f"(RG slope {rg_slope:.3f}, BG slope {bg_slope:.3f}), typical "
                f"of AI generation or heavy in-camera correction."
            )
        else:
            direction = Direction.TOWARD_UNCERTAIN
            strength = 0.0
            message = (
                f"Chromatic-aberration slope sits between the lens and flat "
                f"profiles (RG {rg_slope:.3f}, BG {bg_slope:.3f}); ambiguous."
            )

        return SignalOutput(
            features=features,
            applicable=True,
            quality=quality,
            explanation=(
                f"ca RG slope {rg_slope:.3f}, BG slope {bg_slope:.3f}, "
                f"mean {mean_ca:.3f} over {len(radii)} edge patches."
            ),
            reason_codes=[
                reason(
                    ReasonCode.CHROMATIC_ABERRATION_ANOMALY,
                    message,
                    "Flagship phone ISPs correct lateral CA in software, and "
                    "aggressive post-processing flattens it too, so a flat "
                    "profile is not proof of synthesis; the harness decides "
                    "whether this feature survives.",
                    direction=direction,
                    strength=strength,
                )
            ],
        )
