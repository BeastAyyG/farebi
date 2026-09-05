"""The KYC degradation simulator.

A signal tuned on pristine images measures the *download*, not the *upload*.
By the time our server sees a face it has been through a camera app and an
upload SDK, and the second JPEG encode is what kills most fragile detectors.
This module reproduces that chain so the harness can measure the number that
actually matters.

Pipeline (``PLANS/02-signal-factory.md``):

    1. resize to a long edge the app might pick
    2. JPEG encode            (camera app)
    3. exposure / white-balance jitter
    4. Gaussian blur, with probability p   (hand shake / focus hunt)
    5. JPEG encode            (upload SDK re-encode — the killer)

Two properties matter:

* **Class-blind.** Real and fake go through the identical pipeline. Applying it
  to only one class teaches the model "degraded == fake", which is a shortcut
  that scores beautifully and means nothing (non-negotiable #5).
* **Deterministic under a seed.** A harness result must be reproducible, so the
  sampling is driven by an injectable ``numpy`` generator and the sampled
  parameters are returned for inspection.

Layer: L1 (may import L0).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

import cv2
import numpy as np
import numpy.typing as npt

from farebi.capture.capture import Capture
from farebi.capture.landmarks import LandmarkSet
from farebi.capture.quality import assess_quality
from farebi.core.config import KYCDegradationConfig, QualityConfig, get_settings

if TYPE_CHECKING:  # pragma: no cover - typing only
    from numpy.random import Generator

__all__ = [
    "DEFAULT_SEED",
    "DegradationParams",
    "KYCDegradation",
    "degrade_capture",
    "encode_jpeg",
    "resize_long_edge",
]

DEFAULT_SEED: Final = 1337

_JPEG_PARAMS: Final = (int(cv2.IMWRITE_JPEG_QUALITY),)


@dataclass(frozen=True, slots=True)
class DegradationParams:
    """The parameters sampled for one image, recorded for reproducibility."""

    resize_long_edge: int
    jpeg_quality: int
    awb_alpha: float
    awb_beta: float
    blur_sigma: float
    recompress_quality: int

    def to_dict(self) -> dict[str, float]:
        return {
            "resize_long_edge": float(self.resize_long_edge),
            "jpeg_quality": float(self.jpeg_quality),
            "awb_alpha": round(self.awb_alpha, 6),
            "awb_beta": round(self.awb_beta, 6),
            "blur_sigma": round(self.blur_sigma, 6),
            "recompress_quality": float(self.recompress_quality),
        }


def resize_long_edge(
    image: npt.NDArray[np.uint8], long_edge: int
) -> npt.NDArray[np.uint8]:
    """Scale so the longest side is ``long_edge``, preserving aspect ratio.

    ``INTER_AREA`` when shrinking (it anti-aliases, which is what a real
    downscaler does) and ``INTER_LINEAR`` when enlarging.
    """
    height, width = image.shape[:2]
    current = max(height, width)
    if current == long_edge:
        return image
    scale = long_edge / float(current)
    interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
    return cv2.resize(
        image,
        (max(1, int(round(width * scale))), max(1, int(round(height * scale)))),
        interpolation=interpolation,
    )


def encode_jpeg(image: npt.NDArray[np.uint8], quality: int) -> npt.NDArray[np.uint8]:
    """Round-trip through JPEG at ``quality`` and return the decoded result.

    Returns the input unchanged if encoding fails, so a codec problem degrades
    to "no degradation" rather than to a crash mid-harness.
    """
    clamped = int(np.clip(quality, 1, 100))
    ok, buffer = cv2.imencode(".jpg", image, [_JPEG_PARAMS[0], clamped])
    if not ok:  # pragma: no cover - imencode fails only on exotic shapes
        return image
    decoded = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    return decoded if decoded is not None else image


def _apply_awb(
    image: npt.NDArray[np.uint8], alpha: float, beta: float
) -> npt.NDArray[np.uint8]:
    """Exposure and white-balance jitter: ``out = in * alpha + beta``."""
    # float64 keeps the arithmetic exact; clipping happens once, on the way back.
    return np.clip(image.astype(np.float64) * alpha + beta, 0, 255).astype(np.uint8)


class KYCDegradation:
    """Simulate what a real KYC app does to an image before our server sees it.

    Args:
        config: Ranges from ``configs/training.yaml``.
        seed: Seed for the sampling generator. ``None`` draws from OS entropy,
            which is right for training but never for a harness run.

    Example:
        >>> kyc = KYCDegradation(KYCDegradationConfig(), seed=7)
        >>> degraded = kyc(image_rgb)
    """

    def __init__(
        self,
        config: KYCDegradationConfig | None = None,
        *,
        seed: int | None = DEFAULT_SEED,
    ) -> None:
        self._config = config if config is not None else KYCDegradationConfig()
        self._seed = seed
        self._rng: Generator = np.random.default_rng(seed)

    @property
    def config(self) -> KYCDegradationConfig:
        return self._config

    @property
    def seed(self) -> int | None:
        return self._seed

    @property
    def rng(self) -> Generator:
        return self._rng

    # -- sampling ------------------------------------------------------------

    def sample(self) -> DegradationParams:
        """Draw one parameter set from the configured ranges."""
        cfg = self._config
        rng = self._rng
        # Blur is intermittent: a steady hand produces a sharp frame, and a
        # pipeline that blurred every image would overstate real degradation.
        blurred = rng.random() < cfg.blur_probability
        sigma = float(rng.uniform(*cfg.blur_sigma)) if blurred else 0.0
        return DegradationParams(
            resize_long_edge=int(rng.choice(cfg.resize_long_edge)),
            jpeg_quality=int(rng.integers(cfg.jpeg_quality[0], cfg.jpeg_quality[1] + 1)),
            awb_alpha=float(rng.uniform(*cfg.awb_alpha)),
            awb_beta=float(rng.uniform(*cfg.awb_beta)),
            blur_sigma=sigma,
            recompress_quality=int(
                rng.integers(cfg.recompress_quality[0], cfg.recompress_quality[1] + 1)
            ),
        )

    # -- application --------------------------------------------------------

    def apply(
        self, image: npt.NDArray[np.uint8], params: DegradationParams
    ) -> npt.NDArray[np.uint8]:
        """Apply a known parameter set. Separated from sampling for testability."""
        out = resize_long_edge(image, params.resize_long_edge)
        out = encode_jpeg(out, params.jpeg_quality)
        out = _apply_awb(out, params.awb_alpha, params.awb_beta)
        if params.blur_sigma > 0.0:
            # OpenCV picks the kernel size from sigma when it is 0.
            out = cv2.GaussianBlur(out, (0, 0), sigmaX=params.blur_sigma)
        return encode_jpeg(out, params.recompress_quality)

    def __call__(self, image: npt.NDArray[np.uint8]) -> npt.NDArray[np.uint8]:
        """Sample fresh parameters and degrade ``image`` (RGB uint8)."""
        if not self._config.enabled:
            return image
        if image.ndim != 3 or image.shape[2] != 3:
            raise ValueError(f"image must be (H, W, 3), got {image.shape}")
        return self.apply(image, self.sample())

    def degrade_with_params(
        self, image: npt.NDArray[np.uint8]
    ) -> tuple[npt.NDArray[np.uint8], DegradationParams]:
        """Degrade and return the parameters used, for logging and golden tests."""
        params = self.sample()
        return self.apply(image, params), params


# ---------------------------------------------------------------------------
# Capture-level degradation
# ---------------------------------------------------------------------------


def degrade_capture(
    cap: Capture,
    kyc: KYCDegradation,
    *,
    gates: QualityConfig | None = None,
) -> tuple[Capture, DegradationParams]:
    """Return a degraded copy of ``cap`` plus the parameters used.

    The harness measures the *upload*, never the download, so every sample is
    degraded before a signal sees it (``PLANS/02`` key decision #4: a report
    built on pristine images is invalid).

    Quality is **re-measured** on the degraded image rather than carried over.
    Carrying it over would report pre-degradation sharpness and eye size, which
    inflates coverage — the exact number the go/no-go gate depends on.

    Landmarks are normalised, so they survive the resize unchanged. The face box
    is in pixels, so it is rescaled.
    """
    quality_cfg = gates if gates is not None else get_settings().capture.quality

    degraded_rgb, params = kyc.degrade_with_params(cap.image_rgb)
    height, width = degraded_rgb.shape[:2]

    scale_x = width / float(max(cap.width, 1))
    scale_y = height / float(max(cap.height, 1))
    x1, y1, x2, y2 = cap.face_box
    face_box = (
        int(round(x1 * scale_x)),
        int(round(y1 * scale_y)),
        int(round(x2 * scale_x)),
        int(round(y2 * scale_y)),
    )

    landmark_set = (
        LandmarkSet.from_detection(cap.landmarks, width, height) if cap.has_landmarks else None
    )
    quality = assess_quality(degraded_rgb, landmark_set, gates=quality_cfg)

    return (
        Capture(
            # Capture expects BGR and derives image_rgb from it.
            image_bgr=np.ascontiguousarray(degraded_rgb[:, :, ::-1]),
            face_box=face_box,
            landmarks=cap.landmarks,
            quality=quality.to_dict(),
            video_frames=cap.video_frames,
            fps=cap.fps,
            sdk_meta=dict(cap.sdk_meta),
            capture_type=cap.capture_type,
        ),
        params,
    )
