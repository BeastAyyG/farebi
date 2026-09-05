"""The ``Capture`` object — and the only place one is constructed.

``FAREBI.md`` §5 places ``Capture`` in ``signals/base.py``; the plugin ABC lives
there too. To satisfy both documents without a name collision, ``Capture`` is
**defined** here (L1) and **re-exported** from ``signals/base.py`` (L2 may
import L1). One definition, two import paths, no duplication.

Centralising construction buys three things:

* Signals receive a ``Capture`` and never re-run face detection. Detection is
  the expensive step; running it once keeps every signal cheap and testable.
* Quality gates are applied exactly once, in one place.
* ``unable_to_assess`` is decided by evidence, not by each signal improvising.

Layer: L1 (may import L0 only).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

import numpy as np
import numpy.typing as npt

from farebi.capture.face_mesh import FaceDetection, FaceMeshDetector, FaceMeshStatus
from farebi.capture.landmarks import LandmarkSet
from farebi.capture.quality import QualityAssessment, assess_quality
from farebi.core.config import CaptureConfig, QualityConfig
from farebi.core.constants import CaptureType
from farebi.core.logging import get_logger
from farebi.core.reason_codes import Direction, Reason, ReasonCode

if TYPE_CHECKING:  # pragma: no cover - typing only
    from farebi.utils.image_io import DecodedImage

__all__ = [
    "Capture",
    "CaptureError",
    "CaptureResult",
    "CaptureStatus",
    "build_capture",
]

_log = get_logger(__name__)


class CaptureStatus(str, Enum):
    """Why a capture succeeded or failed."""

    OK = "ok"
    NO_FACE = "no_face"
    FACE_TOO_SMALL = "face_too_small"
    QUALITY_UNUSABLE = "quality_unusable"
    LANDMARKS_UNAVAILABLE = "landmarks_unavailable"
    DETECTOR_ERROR = "detector_error"


class CaptureError(RuntimeError):
    """Raised only by :func:`require_capture` when a capture is unusable."""

    def __init__(
        self, status: CaptureStatus, detail: str, reasons: list[Reason] | None = None
    ) -> None:
        super().__init__(f"{status.value}: {detail}")
        self.status = status
        self.detail = detail
        self.reasons: list[Reason] = reasons or []


@dataclass(frozen=True, slots=True)
class Capture:
    """Everything the server knows about one submission.

    Attributes:
        image_bgr: Full decoded frame in BGR, EXIF-orientation corrected.
            Kept as BGR because most OpenCV-based signals want it; use
            :attr:`image_rgb` for anything CLIP/torch-side.
        face_box: ``(x1, y1, x2, y2)`` pixel bounding box of the chosen face.
        landmarks: ``(N, 3)`` normalised landmarks, including the 10 iris
            points when refinement is on. Empty when unavailable.
        quality: The measurable quality numbers, as a plain dict so it
            serialises straight into the API response.
        video_frames: Optional frame sequence for Tier-2 signals.
        fps: Sampling rate of ``video_frames``, when known.
        sdk_meta: GPS/time/device from **our** SDK. Never EXIF: browsers strip
            EXIF, and EXIF is context, not proof (non-negotiable #4).
        capture_type: ``selfie`` | ``id_photo`` | ``unknown``.
    """

    image_bgr: npt.NDArray[np.uint8]
    face_box: tuple[int, int, int, int]
    landmarks: npt.NDArray[np.float32]
    quality: dict[str, object]
    video_frames: list[npt.NDArray[np.uint8]] | None = None
    fps: float | None = None
    sdk_meta: dict[str, object] = field(default_factory=dict)
    capture_type: str = CaptureType.SELFIE.value

    # -- convenience --------------------------------------------------------
    image_rgb: npt.NDArray[np.uint8] = field(init=False)

    def __post_init__(self) -> None:
        if self.image_bgr.ndim != 3 or self.image_bgr.shape[2] != 3:
            raise ValueError(f"image_bgr must be (H, W, 3), got {self.image_bgr.shape}")
        if self.capture_type not in {member.value for member in CaptureType}:
            raise ValueError(f"capture_type must be one of {[m.value for m in CaptureType]}")
        # frozen + slots: write through object.__setattr__ for the derived field.
        object.__setattr__(self, "image_rgb", np.ascontiguousarray(self.image_bgr[:, :, ::-1]))

    @property
    def width(self) -> int:
        return int(self.image_bgr.shape[1])

    @property
    def height(self) -> int:
        return int(self.image_bgr.shape[0])

    @property
    def has_landmarks(self) -> bool:
        return self.landmarks.ndim == 2 and self.landmarks.shape[0] > 0

    @property
    def has_iris(self) -> bool:
        return self.has_landmarks and self.landmarks.shape[0] >= 478


@dataclass(frozen=True, slots=True)
class CaptureResult:
    """Outcome of :func:`build_capture`. Inspection without exceptions."""

    capture: Capture | None
    status: CaptureStatus
    detail: str
    quality: QualityAssessment | None
    reasons: tuple[Reason, ...]

    @property
    def ok(self) -> bool:
        return self.status is CaptureStatus.OK and self.capture is not None


def _select_primary_face(detections: tuple[FaceDetection, ...]) -> FaceDetection:
    """Pick the largest face by bounding-box area.

    With several faces we cannot know which one the applicant submitted, so we
    score the most prominent and record ``MULTIPLE_FACES`` as a reason. A KYC
    flow should treat that as a recapture prompt, not as an automatic pass.
    """
    return max(
        detections,
        key=lambda d: max(0, d.bbox()[2] - d.bbox()[0]) * max(0, d.bbox()[3] - d.bbox()[1]),
    )


def build_capture(
    decoded: DecodedImage,
    *,
    config: CaptureConfig,
    detector: FaceMeshDetector | None = None,
    capture_type: str = CaptureType.SELFIE.value,
    sdk_meta: dict[str, object] | None = None,
    video_frames: list[npt.NDArray[np.uint8]] | None = None,
    fps: float | None = None,
) -> CaptureResult:
    """Build a :class:`Capture` from a decoded image.

    Args:
        decoded: Output of :func:`farebi.utils.image_io.decode_image`.
        config: ``capture`` section of the settings.
        detector: Optional detector; one is constructed when omitted. Pass a
            shared instance in a serving process — construction is expensive.
        capture_type: Selfie or ID portrait.
        sdk_meta: Metadata from our own SDK (never EXIF).
        video_frames: Optional sequence for Tier-2 video signals.
        fps: Frame rate of ``video_frames``.

    Returns:
        A :class:`CaptureResult`. Never raises for expected conditions.
    """
    if capture_type not in {member.value for member in CaptureType}:
        raise ValueError(
            f"capture_type must be one of {[m.value for m in CaptureType]}, got {capture_type!r}"
        )

    reasons: list[Reason] = []
    owns_detector = detector is None
    detector = detector or FaceMeshDetector(
        enabled=config.face_mesh.enabled,
        backend=config.face_mesh.backend,
        model_path=config.face_mesh.model_path,
        max_num_faces=config.face_mesh.max_num_faces,
        min_detection_confidence=config.face_mesh.min_detection_confidence,
        refine_landmarks=config.face_mesh.refine_landmarks,
    )

    try:
        mesh_result = detector.detect(decoded.array)
    finally:
        if owns_detector:
            detector.close()

    if mesh_result.status is FaceMeshStatus.DISABLED:
        reasons.append(
            Reason(
                code=ReasonCode.LANDMARKS_UNAVAILABLE,
                direction=Direction.TOWARD_UNCERTAIN,
                strength=0.0,
                message="Face landmarking is disabled, so no face-region signals could be computed.",
                limitation="This is a configuration state, not evidence about the image.",
            )
        )
        return CaptureResult(
            None, CaptureStatus.LANDMARKS_UNAVAILABLE, mesh_result.detail, None, tuple(reasons)
        )

    if mesh_result.status is FaceMeshStatus.UNAVAILABLE:
        reasons.append(
            Reason(
                code=ReasonCode.LANDMARKS_UNAVAILABLE,
                direction=Direction.TOWARD_UNCERTAIN,
                strength=0.0,
                message="The face landmarking model is not installed, so face-region signals could not be computed.",
                limitation="This is a deployment state, not evidence about the image.",
            )
        )
        return CaptureResult(
            None, CaptureStatus.LANDMARKS_UNAVAILABLE, mesh_result.detail, None, tuple(reasons)
        )

    if mesh_result.status is FaceMeshStatus.ERROR:
        _log.warning("capture_detector_error", detail=mesh_result.detail)
        return CaptureResult(
            None, CaptureStatus.DETECTOR_ERROR, mesh_result.detail, None, tuple(reasons)
        )

    if mesh_result.status is FaceMeshStatus.NO_FACE or not mesh_result.detections:
        reasons.append(
            Reason(
                code=ReasonCode.NO_FACE_DETECTED,
                direction=Direction.TOWARD_UNCERTAIN,
                strength=0.0,
                message="No face could be located in this image.",
                limitation=(
                    "Faces can be missed because of extreme angles, heavy occlusion, "
                    "very low resolution, or unusual lighting. This is not evidence of manipulation."
                ),
            )
        )
        return CaptureResult(None, CaptureStatus.NO_FACE, mesh_result.detail, None, tuple(reasons))

    if len(mesh_result.detections) > 1:
        reasons.append(
            Reason(
                code=ReasonCode.MULTIPLE_FACES,
                direction=Direction.TOWARD_UNCERTAIN,
                strength=0.5,
                message=f"{len(mesh_result.detections)} faces were found; the largest was analysed.",
                limitation=(
                    "Only one face is analysed per submission. A KYC flow should ask for a "
                    "single-subject recapture rather than rely on which face was selected."
                ),
            )
        )

    detection = _select_primary_face(mesh_result.detections)
    landmark_set = LandmarkSet.from_detection(detection.landmarks, decoded.width, decoded.height)
    face_box = detection.bbox(padding_ratio=0.10)

    quality = assess_quality(decoded.array, landmark_set, gates=config.quality)
    _extend_quality_reasons(reasons, quality, config.quality)

    capture = Capture(
        image_bgr=decoded.to_bgr(),
        face_box=face_box,
        landmarks=detection.landmarks,
        quality=quality.to_dict(),
        video_frames=video_frames,
        fps=fps,
        sdk_meta=dict(sdk_meta or {}),
        capture_type=capture_type,
    )

    if quality.face_px < config.quality.min_face_px:
        return CaptureResult(
            capture,
            CaptureStatus.FACE_TOO_SMALL,
            f"face is {quality.face_px}px on its short edge; "
            f"minimum is {config.quality.min_face_px}px",
            quality,
            tuple(reasons),
        )

    if not quality.usable:
        return CaptureResult(
            capture,
            CaptureStatus.QUALITY_UNUSABLE,
            f"failed quality gates: {', '.join(quality.failures)}",
            quality,
            tuple(reasons),
        )

    return CaptureResult(capture, CaptureStatus.OK, "capture ok", quality, tuple(reasons))


def _extend_quality_reasons(
    reasons: list[Reason],
    quality: QualityAssessment,
    gates: QualityConfig,
) -> None:
    """Turn failed gates into structured reasons.

    Every one of these is a statement about *measurability*, never about
    authenticity — a blurry image is unassessable, not fake.
    """
    if "blur" in quality.failures:
        reasons.append(
            Reason(
                code=ReasonCode.IMAGE_TOO_BLURRY,
                direction=Direction.TOWARD_UNCERTAIN,
                strength=min(
                    1.0, max(0.0, 1.0 - quality.blur_score / max(gates.min_blur_score, 1e-6))
                ),
                message=(
                    f"The image is too blurry to analyse reliably "
                    f"(focus score {quality.blur_score:.1f}, minimum {gates.min_blur_score:.1f})."
                ),
                limitation=(
                    "Blur is caused by camera shake, motion, or a dirty lens at least as often "
                    "as by manipulation. It limits what can be measured; it is not evidence of fakery."
                ),
            )
        )

    if "exposure" in quality.failures:
        reasons.append(
            Reason(
                code=ReasonCode.EXPOSURE_OUT_OF_RANGE,
                direction=Direction.TOWARD_UNCERTAIN,
                strength=0.5,
                message=(
                    f"Brightness is outside the workable range "
                    f"({quality.exposure:.2f}; expected {gates.min_exposure:.2f}-{gates.max_exposure:.2f})."
                ),
                limitation=(
                    "Under- and over-exposure are normal in dim rooms and backlit scenes. "
                    "They reduce measurable detail rather than indicating manipulation."
                ),
            )
        )

    if "clipped" in quality.failures:
        reasons.append(
            Reason(
                code=ReasonCode.EXPOSURE_OUT_OF_RANGE,
                direction=Direction.TOWARD_UNCERTAIN,
                strength=min(1.0, quality.clipped_fraction),
                message=(
                    f"{quality.clipped_fraction:.0%} of pixels are fully black or fully white, "
                    "so detail in those areas no longer exists."
                ),
                limitation="Blown highlights and crushed shadows are common in ordinary phone photography.",
            )
        )

    if "face_size" in quality.failures:
        reasons.append(
            Reason(
                code=ReasonCode.FACE_TOO_SMALL,
                direction=Direction.TOWARD_UNCERTAIN,
                strength=1.0,
                message=(
                    f"The face occupies only {quality.face_px}px on its short edge; "
                    f"at least {gates.min_face_px}px is needed."
                ),
                limitation="A distant or tightly framed face is a capture problem, not a sign of manipulation.",
            )
        )

    if "eye_width" in quality.failures or "interocular" in quality.failures:
        reasons.append(
            Reason(
                code=ReasonCode.FACE_TOO_SMALL,
                direction=Direction.TOWARD_UNCERTAIN,
                strength=0.5,
                message="The eyes are too small in frame for eye-region signals to be measured.",
                limitation=(
                    "Eye-based signals are simply skipped when they cannot be measured. "
                    "Their absence is not evidence in either direction."
                ),
            )
        )


def require_capture(result: CaptureResult) -> Capture:
    """Return the capture or raise :class:`CaptureError`.

    Use at the top of anything that cannot proceed without a usable capture.
    """
    if result.capture is None:
        raise CaptureError(result.status, result.detail, list(result.reasons))
    return result.capture
