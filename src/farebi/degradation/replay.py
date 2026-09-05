"""Screen-replay attack simulation.

This module exists for one specific reason: **PRNU is meaningless without it.**
A sensor-noise signal that reports "no camera noise" is only interesting if we
know what *screen* noise looks like — otherwise the signal is just measuring
"was this JPEG'd twice", which is not the question.

It synthesises the replay positives in the evaluation set by reproducing what
happens when an attacker plays an image on a display and photographs it:

    1. composite onto a display at its native resolution (usually a downscale)
    2. moiré — interference between the camera sensor grid and the pixel grid
    3. display gamut — the panel's non-unit per-channel response
    4. specular sheen — a bright reflection patch on the glass
    5. flattened depth — screen photos lose micro-contrast

The result is then normally passed through :class:`KYCDegradation`, because a
replayed photo is *also* a KYC upload.

Layer: L1 (may import L0).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

import cv2
import numpy as np
import numpy.typing as npt

from farebi.core.config import ReplayConfig

if TYPE_CHECKING:  # pragma: no cover - typing only
    from numpy.random import Generator

__all__ = [
    "DEFAULT_SEED",
    "ReplayParams",
    "ScreenReplaySimulator",
    "add_moire",
    "apply_gamut",
    "add_sheen",
    "flatten_depth",
]

DEFAULT_SEED: Final = 1337

_SHEEN_MARGIN: Final = 0.15  # keep the patch inside the frame


@dataclass(frozen=True, slots=True)
class ReplayParams:
    """The parameters sampled for one replay synthesis."""

    moire_pitch_px: float
    moire_amplitude: float
    sheen_strength: float
    depth_sigma: float

    def to_dict(self) -> dict[str, float]:
        return {
            "moire_pitch_px": round(self.moire_pitch_px, 6),
            "moire_amplitude": round(self.moire_amplitude, 6),
            "sheen_strength": round(self.sheen_strength, 6),
            "depth_sigma": round(self.depth_sigma, 6),
        }


def _composite_on_display(
    image: npt.NDArray[np.uint8], display: tuple[int, int]
) -> npt.NDArray[np.uint8]:
    """Scale the image to fit a display of ``(width, height)``, preserving aspect.

    Unlike :func:`farebi.degradation.kyc_pipeline.resize_long_edge` this fits
    *within* the display (a photo of a screen shows the whole panel), so the
    short edge drives the scale.
    """
    disp_w, disp_h = display
    height, width = image.shape[:2]
    scale = min(disp_w / float(width), disp_h / float(height), 1.0)
    if scale >= 1.0:
        return image
    return cv2.resize(
        image,
        (max(1, int(round(width * scale))), max(1, int(round(height * scale)))),
        interpolation=cv2.INTER_AREA,
    )


def add_moire(
    image: npt.NDArray[np.uint8], pitch_px: float, amplitude: float
) -> npt.NDArray[np.uint8]:
    """Add sensor/pixel-grid interference: crossed sinusoids on luma.

    Moiré is the visible tell of a photographed screen, and it is *periodic* —
    which is exactly why an FFT-based signal should find it and why a texture
    signal should not mistake it for skin.
    """
    height, width = image.shape[:2]
    yy = np.arange(height, dtype=np.float64)[:, None]
    xx = np.arange(width, dtype=np.float64)[None, :]
    phase = 2.0 * np.pi / max(pitch_px, 1e-6)
    pattern = 0.5 * (np.sin(xx * phase) + np.sin(yy * phase))
    # Add on luma only: a colour fringe would misrepresent how sensors alias.
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY).astype(np.float64)
    luma = np.clip(gray + amplitude * pattern, 0.0, 255.0)
    delta = (luma - gray)[:, :, None]
    return np.clip(image.astype(np.float64) + delta, 0, 255).astype(np.uint8)


def apply_gamut(
    image: npt.NDArray[np.uint8], gain: tuple[float, float, float]
) -> npt.NDArray[np.uint8]:
    """Apply a display's per-channel response (RGB gains)."""
    gains = np.asarray(gain, dtype=np.float64).reshape(1, 1, 3)
    return np.clip(image.astype(np.float64) * gains, 0, 255).astype(np.uint8)


def add_sheen(image: npt.NDArray[np.uint8], strength: float) -> npt.NDArray[np.uint8]:
    """Add a specular reflection patch: a soft-edged bright rectangle.

    Position is derived from the image dimensions rather than sampled, so the
    output stays deterministic under a seed for a given input size.
    """
    height, width = image.shape[:2]
    top = int(height * _SHEEN_MARGIN)
    left = int(width * _SHEEN_MARGIN)
    bottom = max(top + 1, int(height * 0.45))
    right = max(left + 1, int(width * 0.55))

    patch_h, patch_w = bottom - top, right - left
    # A linear ramp brightest at the top-left corner, feathered to zero so the
    # edge is not itself a hard frequency artifact.
    ramp_y = np.linspace(1.0, 0.0, patch_h, dtype=np.float64)[:, None]
    ramp_x = np.linspace(1.0, 0.0, patch_w, dtype=np.float64)[None, :]
    gradient = (ramp_y * ramp_x * strength)[:, :, None]

    out = image.astype(np.float64)
    out[top:bottom, left:right] += gradient
    return np.clip(out, 0, 255).astype(np.uint8)


def flatten_depth(image: npt.NDArray[np.uint8], sigma: float) -> npt.NDArray[np.uint8]:
    """Lose micro-contrast, the way a camera focused on a panel does.

    Mixing the image with a blurred copy lowers local contrast without the
    obvious whole-frame softness of a plain blur.
    """
    blurred = cv2.GaussianBlur(image, (0, 0), sigmaX=sigma)
    return cv2.addWeighted(image, 0.7, blurred, 0.3, 0.0)


class ScreenReplaySimulator:
    """Synthesise a photographed-screen version of an image.

    Args:
        config: Ranges from ``configs/training.yaml`` → ``training.replay``.
        seed: Seed for the sampling generator.

    Example:
        >>> replay = ScreenReplaySimulator(seed=7)
        >>> attacked = replay(genuine_rgb)
    """

    def __init__(
        self,
        config: ReplayConfig | None = None,
        *,
        seed: int | None = DEFAULT_SEED,
    ) -> None:
        self._config = config if config is not None else ReplayConfig()
        self._seed = seed
        self._rng: Generator = np.random.default_rng(seed)

    @property
    def config(self) -> ReplayConfig:
        return self._config

    @property
    def seed(self) -> int | None:
        return self._seed

    def sample(self) -> ReplayParams:
        """Draw one parameter set from the configured ranges."""
        cfg = self._config
        rng = self._rng
        sheen = float(rng.uniform(*cfg.sheen_strength)) if rng.random() < cfg.sheen_probability else 0.0
        return ReplayParams(
            moire_pitch_px=float(rng.uniform(*cfg.moire_pitch_px)),
            moire_amplitude=float(rng.uniform(*cfg.moire_amplitude)),
            sheen_strength=sheen,
            depth_sigma=float(rng.uniform(*cfg.depth_flatten_sigma)),
        )

    def apply(self, image: npt.NDArray[np.uint8], params: ReplayParams) -> npt.NDArray[np.uint8]:
        """Apply a known parameter set."""
        cfg = self._config
        out = _composite_on_display(image, cfg.display_resolution)
        out = add_moire(out, params.moire_pitch_px, params.moire_amplitude)
        out = apply_gamut(out, cfg.gamut_gain)
        if params.sheen_strength > 0.0:
            out = add_sheen(out, params.sheen_strength)
        return flatten_depth(out, params.depth_sigma)

    def __call__(self, image: npt.NDArray[np.uint8]) -> npt.NDArray[np.uint8]:
        """Sample fresh parameters and synthesise a replay of ``image``."""
        if not self._config.enabled:
            return image
        if image.ndim != 3 or image.shape[2] != 3:
            raise ValueError(f"image must be (H, W, 3), got {image.shape}")
        return self.apply(image, self.sample())

    def replay_with_params(
        self, image: npt.NDArray[np.uint8]
    ) -> tuple[npt.NDArray[np.uint8], ReplayParams]:
        """Synthesise and return the parameters used."""
        params = self.sample()
        return self.apply(image, params), params
