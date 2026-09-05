"""The orchestrator.

**This phase ships an empty pipeline on purpose.** Every step exists, in order,
with its final type signature and its real error handling — but each one returns
a typed placeholder instead of a measurement. The point of Phase 01 is to prove
the shape: that an image can traverse all twelve stages of ``FAREBI.md`` §3.2
and come out as a well-formed result object, before any signal work begins.

What is *not* a placeholder:

* Upload security (steps 1-2) — fully implemented, because it is a boundary,
  not a detection concern.
* Capture and quality gating (step 3) — fully implemented.
* ``unable_to_assess`` — fully implemented, and already the correct answer for
  inputs that cannot be captured.

What is a placeholder (phases 04-07): signals, fusion, calibration,
uncertainty, attribution, and therefore ``likely_real`` / ``likely_fake`` /
``uncertain``. Until those land, ``verdict`` is ``None`` for anything that
*was* captured successfully.

Layer: L4 (may import L0-L3).
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from farebi.capture.capture import CaptureResult, CaptureStatus, build_capture
from farebi.capture.face_mesh import FaceMeshDetector
from farebi.core.config import Settings, get_settings
from farebi.core.constants import CaptureType, RejectionCode, Verdict
from farebi.core.logging import bind, clear, get_logger
from farebi.core.reason_codes import Direction, Reason, ReasonCode
from farebi.core.security import UploadLimits

if TYPE_CHECKING:  # pragma: no cover - typing only
    import numpy as np
    import numpy.typing as npt

    from farebi.utils.image_io import DecodedImage

__all__ = [
    "DetectionPipeline",
    "PipelineResult",
    "StageTrace",
    "UncertaintyPlaceholder",
]

_log = get_logger(__name__)

#: Response versions. Non-negotiable #10: every response carries them.
MODEL_VERSION = "0.0.0-foundation"
THRESHOLD_VERSION = "uncalibrated-0.0.0"
CALIBRATION_VERSION = "uncalibrated-0.0.0"

#: Shown whenever the system has not yet earned the right to an opinion.
_NOT_EVALUATED_WARNING = (
    "No detection model has been evaluated for this image yet. "
    "This result is a pipeline check, not a manipulation assessment."
)
_REVIEW_WARNING = (
    "This system is a risk signal. Uncertain and high-risk results require manual review."
)
_LIVENESS_WARNING = (
    "This detector does not verify liveness or confirm that the face belongs to the claimed person."
)


@dataclass(frozen=True, slots=True)
class StageTrace:
    """One pipeline step: name, whether it ran, and how long it took."""

    name: str
    executed: bool
    duration_ms: float
    note: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "stage": self.name,
            "executed": self.executed,
            "duration_ms": round(self.duration_ms, 3),
            "note": self.note,
        }


@dataclass(frozen=True, slots=True)
class UncertaintyPlaceholder:
    """Shape of the uncertainty block. Populated in Phase 07."""

    score: float | None = None
    ood_score: float | None = None
    disagreement: float | None = None
    margin_to_band: float | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "score": self.score,
            "ood_score": self.ood_score,
            "disagreement": self.disagreement,
            "margin_to_band": self.margin_to_band,
        }


@dataclass(frozen=True, slots=True)
class PipelineResult:
    """The response object. This shape is the contract with the API layer."""

    request_id: str
    verdict: Verdict | None
    fake_probability: float | None
    confidence_level: str | None
    uncertainty: UncertaintyPlaceholder
    capture_status: CaptureStatus
    capture_type: str
    quality: dict[str, object] | None
    signals: tuple[str, ...]
    reasons: tuple[Reason, ...]
    stages: tuple[StageTrace, ...]
    warnings: tuple[str, ...]
    image_sha256: str | None
    rejection_code: RejectionCode | None
    model_version: str = MODEL_VERSION
    threshold_version: str = THRESHOLD_VERSION
    calibration_version: str = CALIBRATION_VERSION

    def to_dict(self) -> dict[str, object]:
        """Serialise to the API response shape."""
        return {
            "request_id": self.request_id,
            "verdict": self.verdict.value if self.verdict else None,
            "fake_probability": self.fake_probability,
            "confidence_level": self.confidence_level,
            "uncertainty": self.uncertainty.to_dict(),
            "capture_status": self.capture_status.value,
            "capture_type": self.capture_type,
            "quality": self.quality,
            "signals": list(self.signals),
            "signals_evaluated": 0,
            "reasons": [reason.to_dict() for reason in self.reasons],
            "stages": [stage.to_dict() for stage in self.stages],
            "warnings": list(self.warnings),
            "image_sha256": self.image_sha256,
            "rejection_code": self.rejection_code.value if self.rejection_code else None,
            "model_version": self.model_version,
            "threshold_version": self.threshold_version,
            "calibration_version": self.calibration_version,
        }


class DetectionPipeline:
    """Runs one submission through all twelve stages.

    Construct once per process. The face-mesh detector is reused across
    requests, because building it is expensive.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._limits = UploadLimits(
            max_bytes=self._settings.upload.max_bytes,
            max_pixels=self._settings.upload.max_pixels,
            max_edge_px=self._settings.upload.max_edge_px,
            allowed_media_types=frozenset(self._settings.upload.allowed_media_types),
            allow_multiframe=self._settings.upload.allow_multiframe,
        )
        fmc = self._settings.capture.face_mesh
        self._detector = FaceMeshDetector(
            enabled=fmc.enabled,
            backend=fmc.backend,
            model_path=fmc.model_path,
            max_num_faces=fmc.max_num_faces,
            min_detection_confidence=fmc.min_detection_confidence,
            refine_landmarks=fmc.refine_landmarks,
        )

    def close(self) -> None:
        """Release the face-mesh detector."""
        self._detector.close()

    def __enter__(self) -> DetectionPipeline:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # ------------------------------------------------------------------ run
    def run(
        self,
        data: bytes,
        *,
        declared_media_type: str | None,
        filename: str | None = None,
        capture_type: str = CaptureType.SELFIE.value,
        sdk_meta: dict[str, object] | None = None,
        video_frames: list[npt.NDArray[np.uint8]] | None = None,
        fps: float | None = None,
        request_id: str | None = None,
    ) -> PipelineResult:
        """Process one submission. Never raises for a bad submission.

        Args:
            data: Raw upload bytes.
            declared_media_type: Client-supplied ``Content-Type``. Untrusted.
            filename: Client-supplied filename. Validated, never used as a path.
            capture_type: ``selfie`` | ``id_photo`` | ``unknown``.
            sdk_meta: Metadata from our SDK (never EXIF).
            video_frames: Optional frames for Tier-2 signals (Phase 05).
            fps: Frame rate of ``video_frames``.
            request_id: Caller-supplied id; one is generated when omitted.

        Returns:
            A :class:`PipelineResult` — well-formed even when the input is
            rejected. Rejection is expressed as ``verdict=unable_to_assess``
            plus a ``rejection_code``, never as an exception.
        """
        request_id = request_id or str(uuid.uuid4())
        clear()
        bind(request_id=request_id)

        traces: list[StageTrace] = []
        reasons: list[Reason] = []
        warnings: list[str] = [_NOT_EVALUATED_WARNING, _REVIEW_WARNING, _LIVENESS_WARNING]

        def trace(name: str, executed: bool, started: float, note: str = "") -> None:
            traces.append(
                StageTrace(name, executed, (time.perf_counter() - started) * 1000.0, note)
            )

        # [1] Secure file validation --------------------------------------
        started = time.perf_counter()
        from farebi.core.security import validate_upload

        validation = validate_upload(
            data,
            declared_media_type=declared_media_type,
            filename=filename,
            limits=self._limits,
        )
        trace("secure_file_validation", validation.ok, started, validation.detail)

        if not validation.ok:
            _log.info("upload_rejected", rejection_code=validation.code.value)
            reasons.append(_rejection_reason(validation.code, validation.detail))
            return PipelineResult(
                request_id=request_id,
                verdict=Verdict.UNABLE_TO_ASSESS,
                fake_probability=None,
                confidence_level=None,
                uncertainty=UncertaintyPlaceholder(),
                capture_status=CaptureStatus.NO_FACE,
                capture_type=capture_type,
                quality=None,
                signals=(),
                reasons=tuple(reasons),
                stages=tuple(traces),
                warnings=tuple(warnings),
                image_sha256=None,
                rejection_code=validation.code,
            )

        # [2] Decode and normalise ----------------------------------------
        from farebi.utils.image_io import decode_image

        started = time.perf_counter()
        decoded: DecodedImage
        try:
            decoded = decode_image(
                data,
                declared_media_type=declared_media_type,
                filename=filename,
                limits=self._limits,
            )
        except Exception as exc:  # decode errors are broad by nature
            code = getattr(exc, "code", RejectionCode.DECODE_FAILED)
            detail = getattr(exc, "detail", str(exc))
            trace("decode", False, started, detail)
            reasons.append(_rejection_reason(code, detail))
            return PipelineResult(
                request_id=request_id,
                verdict=Verdict.UNABLE_TO_ASSESS,
                fake_probability=None,
                confidence_level=None,
                uncertainty=UncertaintyPlaceholder(),
                capture_status=CaptureStatus.NO_FACE,
                capture_type=capture_type,
                quality=None,
                signals=(),
                reasons=tuple(reasons),
                stages=tuple(traces),
                warnings=tuple(warnings),
                image_sha256=None,
                rejection_code=code,
            )
        trace("decode", True, started, f"{decoded.width}x{decoded.height} {decoded.media_type}")

        # [3] Capture: face, landmarks, quality ---------------------------
        started = time.perf_counter()
        capture_result: CaptureResult = build_capture(
            decoded,
            config=self._settings.capture,
            detector=self._detector,
            capture_type=capture_type,
            sdk_meta=sdk_meta,
            video_frames=video_frames,
            fps=fps,
        )
        reasons.extend(capture_result.reasons)
        trace(
            "capture",
            capture_result.ok,
            started,
            f"{capture_result.status.value}: {capture_result.detail}",
        )

        # [4]-[9] Placeholder stages --------------------------------------
        for name in (
            "signal_preflight",
            "feature_assembly",
            "calibrated_probability",
            "uncertainty",
            "attribution",
            "reason_generation",
        ):
            started = time.perf_counter()
            trace(name, False, started, "not implemented until phase 04-07")

        # [10] Verdict policy ---------------------------------------------
        started = time.perf_counter()
        verdict: Verdict | None
        if capture_result.capture is None:
            # No face, no landmarks, no detector: we cannot even form an opinion.
            verdict = Verdict.UNABLE_TO_ASSESS
        elif capture_result.status in (
            CaptureStatus.FACE_TOO_SMALL,
            CaptureStatus.QUALITY_UNUSABLE,
        ):
            verdict = Verdict.UNABLE_TO_ASSESS
        else:
            # Capture succeeded, but no signals exist yet. Returning None here
            # is deliberate: inventing a verdict would be worse than admitting
            # there is nothing to base one on.
            verdict = None
        trace("verdict_policy", True, started, f"verdict={verdict.value if verdict else None}")

        # [11] Response + [12] cleanup ------------------------------------
        # The trace is recorded *before* the result is built: `stages` is a
        # snapshot of the list, so anything appended afterwards is lost.
        trace("response", True, time.perf_counter(), "result assembled; upload released")

        result = PipelineResult(
            request_id=request_id,
            verdict=verdict,
            fake_probability=None,
            confidence_level=None,
            uncertainty=UncertaintyPlaceholder(),
            capture_status=capture_result.status,
            capture_type=capture_type,
            quality=capture_result.quality.to_dict() if capture_result.quality else None,
            signals=(),
            reasons=tuple(reasons),
            stages=tuple(traces),
            warnings=tuple(warnings),
            image_sha256=decoded.sha256,
            rejection_code=None,
        )
        # Non-negotiable #7: no retention. `decoded` goes out of scope here;
        # nothing is written to disk at any point in this pipeline.
        del data

        _log.info(
            "pipeline_complete",
            verdict=verdict.value if verdict else None,
            capture_status=capture_result.status.value,
        )
        return result


def _rejection_reason(code: RejectionCode, detail: str) -> Reason:
    """Turn a rejection code into a structured, limitation-bearing reason.

    Rejections report ``IMAGE_REJECTED`` rather than a per-code reason: the
    security taxonomy exists for monitoring, but folding it into the user-facing
    explanation would leak exactly the detail an attacker wants while probing
    the endpoint.
    """
    return Reason(
        code=ReasonCode.IMAGE_REJECTED,
        direction=Direction.TOWARD_UNCERTAIN,
        strength=0.0,
        message=f"The upload could not be processed: {detail}",
        limitation=(
            "A rejected upload means the file could not be assessed at all. "
            "It says nothing about whether the image is genuine."
        ),
    )
