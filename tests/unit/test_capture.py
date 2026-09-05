"""Capture construction, gating, and degraded modes."""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
import pytest

from farebi.capture.capture import (
    Capture,
    CaptureError,
    CaptureStatus,
    build_capture,
    require_capture,
)
from farebi.capture.face_mesh import FaceDetection, FaceMeshResult, FaceMeshStatus
from farebi.capture.landmarks import (
    EYE_LEFT,
    EYE_RIGHT,
    FACE_OVAL,
    IRIS_LEFT,
    IRIS_RIGHT,
    LandmarkSet,
)
from farebi.core.config import reload_settings
from farebi.core.reason_codes import ReasonCode


class StubDetector:
    """Stands in for :class:`FaceMeshDetector` without MediaPipe.

    Only ``detect()`` is part of the contract ``build_capture`` relies on.
    """

    def __init__(self, result: FaceMeshResult) -> None:
        self._result = result
        self.closed = False

    def detect(self, image_rgb: npt.NDArray[np.uint8]) -> FaceMeshResult:
        if not isinstance(image_rgb, np.ndarray):
            raise TypeError("expected an ndarray")
        return self._result

    def close(self) -> None:
        self.closed = True


def _synthetic_mesh(width: int = 1000, height: int = 1000) -> LandmarkSet:
    """A 478-point mesh with the face occupying the middle ~40% of the frame."""
    rng = np.random.default_rng(11)
    points = rng.random((478, 3)).astype(np.float32) * np.array([1.0, 1.0, 0.0], dtype=np.float32)

    span = np.array([0.40, 0.50, 0.0], dtype=np.float32)
    offset = np.array([0.30, 0.25, 0.0], dtype=np.float32)
    points[list(FACE_OVAL)] = offset + rng.random((len(FACE_OVAL), 3)).astype(np.float32) * span

    points[list(EYE_LEFT)] = np.array([0.40, 0.45, 0.0], dtype=np.float32)
    points[list(EYE_RIGHT)] = np.array([0.60, 0.45, 0.0], dtype=np.float32)
    points[list(IRIS_LEFT)] = np.array([0.40, 0.45, 0.0], dtype=np.float32)
    points[list(IRIS_RIGHT)] = np.array([0.60, 0.45, 0.0], dtype=np.float32)
    return LandmarkSet.from_detection(points, width, height)


def _detection(mesh: LandmarkSet) -> FaceDetection:
    return FaceDetection(
        landmarks=mesh.points_xyz,
        score=1.0,
        image_width=mesh.image_width,
        image_height=mesh.image_height,
    )


@pytest.fixture
def decoded():
    from farebi.core.config import get_settings
    from farebi.utils.image_io import decode_image
    from fixtures.synthetic import encode_png, synthetic_face_rgb

    upload = get_settings().upload
    from farebi.core.security import UploadLimits

    limits = UploadLimits(
        max_bytes=upload.max_bytes,
        max_pixels=upload.max_pixels,
        max_edge_px=upload.max_edge_px,
        allowed_media_types=frozenset(upload.allowed_media_types),
    )
    return decode_image(
        encode_png(synthetic_face_rgb(size=512)), declared_media_type="image/png", limits=limits
    )


class TestDegradedModes:
    def test_disabled_detector_reports_landmarks_unavailable(self, decoded) -> None:
        config = reload_settings().capture
        detector = StubDetector(
            FaceMeshResult((), FaceMeshStatus.DISABLED, "disabled by configuration")
        )
        result = build_capture(decoded, config=config, detector=detector)  # type: ignore[arg-type]

        assert result.status is CaptureStatus.LANDMARKS_UNAVAILABLE
        assert result.capture is None
        assert result.reasons
        assert result.reasons[0].code is ReasonCode.LANDMARKS_UNAVAILABLE
        assert result.reasons[0].direction.value == "toward_uncertain"

    def test_unavailable_detector_reports_landmarks_unavailable(self, decoded) -> None:
        config = reload_settings().capture
        detector = StubDetector(FaceMeshResult((), FaceMeshStatus.UNAVAILABLE, "not installed"))
        result = build_capture(decoded, config=config, detector=detector)  # type: ignore[arg-type]

        assert result.status is CaptureStatus.LANDMARKS_UNAVAILABLE
        assert result.reasons[0].code is ReasonCode.LANDMARKS_UNAVAILABLE

    def test_detector_error_is_surfaced_without_a_crash(self, decoded) -> None:
        config = reload_settings().capture
        detector = StubDetector(FaceMeshResult((), FaceMeshStatus.ERROR, "native failure"))
        result = build_capture(decoded, config=config, detector=detector)  # type: ignore[arg-type]

        assert result.status is CaptureStatus.DETECTOR_ERROR
        assert result.capture is None

    def test_no_face_is_reported_as_no_face(self, decoded) -> None:
        config = reload_settings().capture
        detector = StubDetector(FaceMeshResult((), FaceMeshStatus.NO_FACE, "nothing found"))
        result = build_capture(decoded, config=config, detector=detector)  # type: ignore[arg-type]

        assert result.status is CaptureStatus.NO_FACE
        assert result.reasons[0].code is ReasonCode.NO_FACE_DETECTED
        assert (
            "genuine" in result.reasons[0].limitation
            or "manipulation" in result.reasons[0].limitation
        )


class TestSuccessfulCapture:
    def test_capture_is_built_from_a_detection(self, decoded) -> None:
        config = reload_settings().capture
        mesh = _synthetic_mesh(decoded.width, decoded.height)
        detector = StubDetector(FaceMeshResult((_detection(mesh),), FaceMeshStatus.OK, "ok"))

        result = build_capture(decoded, config=config, detector=detector)  # type: ignore[arg-type]

        assert result.capture is not None, result.detail
        capture = result.capture
        assert capture.image_bgr.shape == (decoded.height, decoded.width, 3)
        assert capture.has_iris is True
        assert len(capture.face_box) == 4
        assert capture.quality["face_px"] > 0

    def test_image_rgb_is_the_channel_inverse_of_image_bgr(self, decoded) -> None:
        config = reload_settings().capture
        mesh = _synthetic_mesh(decoded.width, decoded.height)
        detector = StubDetector(FaceMeshResult((_detection(mesh),), FaceMeshStatus.OK, "ok"))

        result = build_capture(decoded, config=config, detector=detector)  # type: ignore[arg-type]
        assert result.capture is not None

        np.testing.assert_array_equal(
            result.capture.image_rgb[:, :, 0], result.capture.image_bgr[:, :, 2]
        )

    def test_multiple_faces_select_the_largest_and_say_so(self, decoded) -> None:
        config = reload_settings().capture
        big = _synthetic_mesh(decoded.width, decoded.height)
        small_mesh = LandmarkSet.from_detection(
            big.points_xyz * np.array([0.25, 0.25, 1.0], dtype=np.float32)
            + np.array([0.05, 0.05, 0.0], dtype=np.float32),
            decoded.width,
            decoded.height,
        )
        detector = StubDetector(
            FaceMeshResult(
                (_detection(small_mesh), _detection(big)), FaceMeshStatus.OK, "two faces"
            )
        )

        result = build_capture(decoded, config=config, detector=detector)  # type: ignore[arg-type]

        codes = {reason.code for reason in result.reasons}
        assert ReasonCode.MULTIPLE_FACES in codes
        assert result.capture is not None
        # The largest face is the one that was analysed.
        assert result.capture.quality["face_px"] >= config.quality.min_face_px

    def test_tiny_face_is_flagged_too_small(self, decoded) -> None:
        config = reload_settings().capture
        mesh = LandmarkSet.from_detection(
            _synthetic_mesh(decoded.width, decoded.height).points_xyz
            * np.array([0.02, 0.02, 1.0], dtype=np.float32),
            decoded.width,
            decoded.height,
        )
        detector = StubDetector(FaceMeshResult((_detection(mesh),), FaceMeshStatus.OK, "ok"))

        result = build_capture(decoded, config=config, detector=detector)  # type: ignore[arg-type]

        assert result.status is CaptureStatus.FACE_TOO_SMALL
        assert any(r.code is ReasonCode.FACE_TOO_SMALL for r in result.reasons)

    def test_own_detector_is_not_closed_by_the_caller(self, decoded) -> None:
        """A caller-owned detector must outlive a single capture."""
        config = reload_settings().capture
        mesh = _synthetic_mesh(decoded.width, decoded.height)
        detector = StubDetector(FaceMeshResult((_detection(mesh),), FaceMeshStatus.OK, "ok"))

        build_capture(decoded, config=config, detector=detector)  # type: ignore[arg-type]
        assert detector.closed is False


class TestCaptureObject:
    def _capture(self) -> Capture:
        return Capture(
            image_bgr=np.zeros((100, 200, 3), dtype=np.uint8),
            face_box=(10, 10, 90, 90),
            landmarks=np.zeros((478, 3), dtype=np.float32),
            quality={"face_px": 80},
        )

    def test_dimensions_and_defaults(self) -> None:
        capture = self._capture()
        assert (capture.width, capture.height) == (200, 100)
        assert capture.capture_type == "selfie"
        assert capture.sdk_meta == {}
        assert capture.video_frames is None
        assert capture.fps is None

    def test_invalid_image_shape_is_rejected(self) -> None:
        with pytest.raises(ValueError, match=r"must be \(H, W, 3\)"):
            Capture(
                image_bgr=np.zeros((100, 200), dtype=np.uint8),
                face_box=(0, 0, 1, 1),
                landmarks=np.zeros((478, 3), dtype=np.float32),
                quality={},
            )

    def test_invalid_capture_type_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="capture_type must be one of"):
            Capture(
                image_bgr=np.zeros((10, 10, 3), dtype=np.uint8),
                face_box=(0, 0, 1, 1),
                landmarks=np.zeros((478, 3), dtype=np.float32),
                quality={},
                capture_type="passport_photo",
            )

    def test_has_iris_reflects_the_point_count(self) -> None:
        assert self._capture().has_iris is True
        short = Capture(
            image_bgr=np.zeros((10, 10, 3), dtype=np.uint8),
            face_box=(0, 0, 1, 1),
            landmarks=np.zeros((468, 3), dtype=np.float32),
            quality={},
        )
        assert short.has_iris is False
        assert short.has_landmarks is True

    def test_empty_landmarks_report_as_absent(self) -> None:
        capture = Capture(
            image_bgr=np.zeros((10, 10, 3), dtype=np.uint8),
            face_box=(0, 0, 1, 1),
            landmarks=np.zeros((0, 3), dtype=np.float32),
            quality={},
        )
        assert capture.has_landmarks is False


class TestRequireCapture:
    def test_returns_the_capture_when_present(self, decoded) -> None:
        config = reload_settings().capture
        mesh = _synthetic_mesh(decoded.width, decoded.height)
        detector = StubDetector(FaceMeshResult((_detection(mesh),), FaceMeshStatus.OK, "ok"))
        result = build_capture(decoded, config=config, detector=detector)  # type: ignore[arg-type]

        assert require_capture(result) is result.capture

    def test_raises_with_the_status_and_reasons_when_absent(self, decoded) -> None:
        config = reload_settings().capture
        detector = StubDetector(FaceMeshResult((), FaceMeshStatus.NO_FACE, "none"))
        result = build_capture(decoded, config=config, detector=detector)  # type: ignore[arg-type]

        with pytest.raises(CaptureError) as excinfo:
            require_capture(result)

        assert excinfo.value.status is CaptureStatus.NO_FACE
        assert excinfo.value.reasons
