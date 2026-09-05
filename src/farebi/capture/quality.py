"""Capture-quality assessment.

Quality is a **gate, not a signal**. It decides whether any downstream signal is
entitled to an opinion at all; it never contributes evidence toward fake or
real. Keeping that boundary clean is what lets us say "unusable input" without
implying "manipulated input".

Gates come from ``configs/app.yaml`` (``capture.quality``) — non-negotiable #3:
no decision threshold is hardcoded in a module.

Layer: L1 (may import L0 only).
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
import numpy.typing as npt

from farebi.capture.landmarks import FaceRegion, LandmarkSet, interocular_distance_px
from farebi.core.config import QualityConfig

__all__ = [
    "QualityAssessment",
    "assess_quality",
    "exposure_stats",
    "laplacian_blur_score",
    "occlusion_estimate",
]

_UNDETERMINED = -1.0


@dataclass(frozen=True, slots=True)
class QualityAssessment:
    """Per-image quality measurements plus the gates they failed.

    ``failures`` holds the gate names that were missed. Empty means the capture
    is usable. Measurements that could not be computed (typically because iris
    landmarks are unavailable) are ``None`` rather than ``0``, so a caller can
    never mistake "unknown" for "terrible".
    """

    blur_score: float
    exposure: float
    clipped_fraction: float
    face_width_px: int
    face_height_px: int
    interocular_px: float | None
    eye_width_px: float | None
    occlusion_estimate: float
    failures: tuple[str, ...]

    @property
    def usable(self) -> bool:
        """True when every gate passed."""
        return not self.failures

    @property
    def face_px(self) -> int:
        """Shortest edge of the face bounding box. The primary scale gate."""
        return min(self.face_width_px, self.face_height_px)

    def to_dict(self) -> dict[str, object]:
        """The ``quality`` block of the API response."""
        return {
            "blur_score": round(float(self.blur_score), 4),
            "exposure": round(float(self.exposure), 4),
            "clipped_fraction": round(float(self.clipped_fraction), 4),
            "face_width_px": self.face_width_px,
            "face_height_px": self.face_height_px,
            "face_px": self.face_px,
            "interocular_px": None
            if self.interocular_px is None
            else round(self.interocular_px, 2),
            "eye_width_px": None if self.eye_width_px is None else round(self.eye_width_px, 2),
            "occlusion_estimate": round(float(self.occlusion_estimate), 4),
            "usable": self.usable,
            "failed_gates": list(self.failures),
        }


def laplacian_blur_score(image_rgb: npt.NDArray[np.uint8]) -> float:
    """Variance of the Laplacian, on luma. Higher is sharper.

    This is the standard cheap focus measure. It is *relative*: the useful
    threshold depends on resolution, which is why the gate in ``app.yaml`` is a
    starting value to be re-tuned against real upload data in Phase 03.
    """
    if image_rgb.size == 0:
        return 0.0
    gray = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def exposure_stats(image_rgb: npt.NDArray[np.uint8]) -> tuple[float, float]:
    """Return ``(mean_luma, clipped_fraction)`` in ``[0, 1]``.

    ``clipped_fraction`` is the proportion of pixels at 0 or 255, i.e. detail
    that no longer exists. A well-exposed image can still be clipped, so both
    numbers are reported.
    """
    if image_rgb.size == 0:
        return 0.0, 1.0
    gray = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2GRAY)
    mean_luma = float(gray.mean()) / 255.0
    clipped = float(np.count_nonzero((gray <= 0) | (gray >= 255))) / float(gray.size)
    return mean_luma, clipped


def occlusion_estimate(landmarks: LandmarkSet) -> float:
    """Heuristic occlusion/ framing score in ``[0, 1]``.

    How much of the face oval appears to be cut off by the frame. MediaPipe's
    Solutions API does not expose per-landmark visibility, so this measures the
    geometric consequence instead: how close the face oval sits to, and crosses,
    the image border.

    This is a **heuristic**. It cannot distinguish a cropped face from a face
    genuinely occluded by a hand, glasses or hair. It is reported as a number,
    never as a reason code asserting occlusion.
    """
    pts = landmarks.points(FaceRegion.FACE_OVAL)
    if pts.size == 0:
        return 0.0

    width, height = float(landmarks.image_width), float(landmarks.image_height)
    outside = np.count_nonzero(
        (pts[:, 0] < 0) | (pts[:, 0] >= width) | (pts[:, 1] < 0) | (pts[:, 1] >= height)
    )
    outside_fraction = float(outside) / float(pts.shape[0])

    # Border-touch fraction: how much of the oval hugs the frame edge.
    margin_x, margin_y = width * 0.02, height * 0.02
    touching = np.count_nonzero(
        (pts[:, 0] < margin_x)
        | (pts[:, 0] >= width - margin_x)
        | (pts[:, 1] < margin_y)
        | (pts[:, 1] >= height - margin_y)
    )
    touching_fraction = float(touching) / float(pts.shape[0])

    return float(min(1.0, max(0.0, outside_fraction + 0.5 * touching_fraction)))


def _eye_width_px(landmarks: LandmarkSet) -> float | None:
    """Widest eye opening in pixels, across both eyes."""
    if not landmarks.has_iris:
        return None
    widths: list[float] = []
    for region in (FaceRegion.EYE_LEFT, FaceRegion.EYE_RIGHT):
        try:
            w, _ = landmarks.region_size_px(region)
        except ValueError:
            continue
        if w > 0:
            widths.append(float(w))
    return max(widths) if widths else None


def assess_quality(
    image_rgb: npt.NDArray[np.uint8],
    landmarks: LandmarkSet | None,
    *,
    gates: QualityConfig,
) -> QualityAssessment:
    """Measure quality and apply the configured gates.

    Args:
        image_rgb: Decoded, orientation-corrected image.
        landmarks: Face mesh, or ``None`` when the detector was unavailable or
            found no face. Scale gates are then recorded as ``None`` and the
            corresponding gates are reported as failed.
        gates: Thresholds from configuration.
    """
    blur = laplacian_blur_score(image_rgb)
    exposure, clipped = exposure_stats(image_rgb)

    face_w = face_h = 0
    interocular: float | None = None
    eye_width: float | None = None
    occlusion = 0.0

    if landmarks is not None:
        face_w, face_h = landmarks.region_size_px(FaceRegion.FACE_OVAL)
        try:
            interocular = interocular_distance_px(landmarks)
        except ValueError:
            interocular = None  # iris refinement off: unknown, not zero
        eye_width = _eye_width_px(landmarks)
        occlusion = occlusion_estimate(landmarks)

    failures: list[str] = []

    if blur < gates.min_blur_score:
        failures.append("blur")
    if not gates.min_exposure <= exposure <= gates.max_exposure:
        failures.append("exposure")
    if clipped > gates.max_clipped_fraction:
        failures.append("clipped")

    face_px = min(face_w, face_h) if face_w and face_h else 0
    if face_px < gates.min_face_px:
        failures.append("face_size")

    if interocular is not None and interocular < gates.min_interocular_px:
        failures.append("interocular")
    if eye_width is not None and eye_width < gates.min_eye_width_px:
        failures.append("eye_width")

    return QualityAssessment(
        blur_score=blur,
        exposure=exposure,
        clipped_fraction=clipped,
        face_width_px=face_w,
        face_height_px=face_h,
        interocular_px=interocular,
        eye_width_px=eye_width,
        occlusion_estimate=occlusion,
        failures=tuple(failures),
    )
