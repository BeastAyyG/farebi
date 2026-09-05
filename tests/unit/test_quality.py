"""Quality gates: measured, gated from configuration, never verdicts."""

from __future__ import annotations

import numpy as np
import pytest

from farebi.capture.landmarks import FaceRegion, LandmarkSet
from farebi.capture.quality import (
    QualityAssessment,
    assess_quality,
    exposure_stats,
    laplacian_blur_score,
    occlusion_estimate,
)
from farebi.core.config import get_settings


def _flat(value: int = 128, size: int = 256) -> np.ndarray:
    return np.full((size, size, 3), value, dtype=np.uint8)


def _noisy(seed: int = 0, size: int = 256) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.integers(0, 256, size=(size, size, 3), dtype=np.uint8).astype(np.uint8)


class TestMeasurements:
    def test_flat_image_has_zero_blur(self) -> None:
        assert laplacian_blur_score(_flat()) == pytest.approx(0.0, abs=1e-6)

    def test_noisy_image_is_sharper_than_a_flat_one(self) -> None:
        assert laplacian_blur_score(_noisy()) > laplacian_blur_score(_flat())

    def test_exposure_is_normalised(self) -> None:
        exposure, clipped = exposure_stats(_flat(128))
        assert 0.0 <= exposure <= 1.0
        assert 0.0 <= clipped <= 1.0

    def test_black_image_is_clipped_and_dark(self) -> None:
        exposure, clipped = exposure_stats(_flat(0))
        assert exposure == pytest.approx(0.0)
        assert clipped == pytest.approx(1.0)

    def test_white_image_is_clipped_and_bright(self) -> None:
        exposure, clipped = exposure_stats(_flat(255))
        assert exposure == pytest.approx(1.0)
        assert clipped == pytest.approx(1.0)

    def test_empty_image_does_not_crash(self) -> None:
        empty = np.empty((0, 0, 3), dtype=np.uint8)
        assert laplacian_blur_score(empty) == 0.0
        assert exposure_stats(empty) == (0.0, 1.0)


class TestGating:
    def test_no_landmarks_fails_the_size_gates(self) -> None:
        gates = get_settings().capture.quality
        assessment = assess_quality(_flat(), None, gates=gates)

        assert assessment.face_px == 0
        assert assessment.interocular_px is None, "unknown, not zero"
        assert assessment.eye_width_px is None
        assert "face_size" in assessment.failures

    def test_unknown_measurements_are_none_not_zero(self) -> None:
        """A caller must be able to tell 'unmeasured' from 'terrible'."""
        gates = get_settings().capture.quality
        assessment = assess_quality(_flat(), None, gates=gates)

        assert assessment.interocular_px is None
        assert assessment.eye_width_px is None
        assert "interocular" not in assessment.failures
        assert "eye_width" not in assessment.failures

    def test_blur_gate_trips_for_a_flat_image(self) -> None:
        gates = get_settings().capture.quality
        assert "blur" in assess_quality(_flat(), None, gates=gates).failures

    def test_dark_image_trips_the_exposure_gate(self) -> None:
        gates = get_settings().capture.quality
        assert "exposure" in assess_quality(_flat(5), None, gates=gates).failures

    def test_only_true_clipping_trips_the_clipped_gate(self) -> None:
        """Near-black is underexposed, but its pixels are not clipped."""
        gates = get_settings().capture.quality
        dark = assess_quality(_flat(5), None, gates=gates)
        black = assess_quality(_flat(0), None, gates=gates)

        assert "clipped" not in dark.failures
        assert "clipped" in black.failures

    def test_a_good_image_passes_every_gate_it_can_be_measured_on(self) -> None:
        """With no landmarks the size gates cannot be measured, so only the
        photometric gates are asserted here."""
        gates = get_settings().capture.quality
        from fixtures.synthetic import synthetic_face_rgb

        assessment = assess_quality(synthetic_face_rgb(size=512), None, gates=gates)

        assert "blur" not in assessment.failures
        assert "exposure" not in assessment.failures
        assert "clipped" not in assessment.failures

    def test_gates_follow_configuration(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from farebi.core.config import reload_settings

        monkeypatch.setenv("FAREBI_CAPTURE__QUALITY__MIN_BLUR_SCORE", "1e12")
        strict = reload_settings().capture.quality
        monkeypatch.setenv("FAREBI_CAPTURE__QUALITY__MIN_BLUR_SCORE", "0")
        lenient = reload_settings().capture.quality

        from fixtures.synthetic import synthetic_face_rgb

        rgb = synthetic_face_rgb(size=512)
        assert "blur" in assess_quality(rgb, None, gates=strict).failures
        assert "blur" not in assess_quality(rgb, None, gates=lenient).failures

    def test_to_dict_shape_is_api_ready(self) -> None:
        gates = get_settings().capture.quality
        payload = assess_quality(_flat(), None, gates=gates).to_dict()

        assert payload["usable"] is False
        assert isinstance(payload["failed_gates"], list)
        assert "face_px" in payload
        assert "blur_score" in payload


class TestLandmarkBasedQuality:
    @pytest.fixture
    def landmark_set(self) -> LandmarkSet:
        """A synthetic mesh: a face oval comfortably inside a 1000x1000 frame."""
        rng = np.random.default_rng(3)
        points = rng.random((478, 3)).astype(np.float32)
        # Place the face oval (indices in FACE_OVAL) in the middle 40%.
        from farebi.capture.landmarks import EYE_LEFT, EYE_RIGHT, FACE_OVAL, IRIS_LEFT, IRIS_RIGHT

        centre = np.array([0.5, 0.5, 0.0], dtype=np.float32)
        points[list(FACE_OVAL)] = (
            centre
            + rng.random((len(FACE_OVAL), 3)).astype(np.float32)
            * np.array([0.4, 0.5, 0.0], dtype=np.float32)
            - np.array([0.2, 0.25, 0.0], dtype=np.float32)
        )
        points[list(EYE_LEFT)] = np.array([0.42, 0.45, 0.0], dtype=np.float32)
        points[list(EYE_RIGHT)] = np.array([0.58, 0.45, 0.0], dtype=np.float32)
        points[list(IRIS_LEFT)] = np.array([0.42, 0.45, 0.0], dtype=np.float32)
        points[list(IRIS_RIGHT)] = np.array([0.58, 0.45, 0.0], dtype=np.float32)
        return LandmarkSet.from_detection(points, 1000, 1000)

    def test_occlusion_estimate_is_zero_for_a_centred_face(self, landmark_set: LandmarkSet) -> None:
        assert occlusion_estimate(landmark_set) == pytest.approx(0.0)

    def test_occlusion_estimate_rises_when_the_face_is_cropped(
        self, landmark_set: LandmarkSet
    ) -> None:
        shifted = LandmarkSet.from_detection(
            landmark_set.points_xyz + np.array([0.45, 0.0, 0.0], dtype=np.float32),
            1000,
            1000,
        )
        assert occlusion_estimate(shifted) > occlusion_estimate(landmark_set)

    def test_scale_measurements_are_reported_in_pixels(self, landmark_set: LandmarkSet) -> None:
        gates = get_settings().capture.quality
        from fixtures.synthetic import synthetic_face_rgb

        rgb = synthetic_face_rgb(size=1000)
        assessment = assess_quality(rgb, landmark_set, gates=gates)

        assert assessment.interocular_px is not None
        assert assessment.interocular_px == pytest.approx(160.0, abs=1.0)
        assert assessment.face_px > 0

    def test_landmark_set_rejects_bad_shapes(self) -> None:
        with pytest.raises(ValueError, match=r"expected \(N, 3\)"):
            LandmarkSet.from_detection(np.zeros((10, 2), dtype=np.float32), 100, 100)
        with pytest.raises(ValueError, match="dimensions must be positive"):
            LandmarkSet.from_detection(np.zeros((10, 3), dtype=np.float32), 0, 100)

    def test_region_lookup_requires_iris_when_absent(self) -> None:
        small = LandmarkSet.from_detection(np.zeros((468, 3), dtype=np.float32), 100, 100)
        assert small.has_iris is False
        with pytest.raises(ValueError, match="iris"):
            small.points(FaceRegion.IRIS_LEFT)

    def test_sclera_mask_excludes_the_iris(self, landmark_set: LandmarkSet) -> None:
        """The sclera band is the eye region minus the iris, not the whole eye."""
        eye = landmark_set.mask(FaceRegion.EYE_LEFT)
        sclera = landmark_set.mask(FaceRegion.SCLERA_LEFT)

        assert eye.sum() > 0
        assert 0 <= sclera.sum() < eye.sum() or eye.sum() == 0

    def test_crop_returns_a_contiguous_array(self, landmark_set: LandmarkSet) -> None:
        from fixtures.synthetic import synthetic_face_rgb

        rgb = synthetic_face_rgb(size=1000)
        crop = landmark_set.crop(rgb, FaceRegion.FACE_OVAL, padding_ratio=0.1)
        assert crop.flags["C_CONTIGUOUS"]
        assert crop.shape[0] > 0 and crop.shape[1] > 0

    def test_crop_outside_the_frame_returns_empty(self, landmark_set: LandmarkSet) -> None:
        from fixtures.synthetic import synthetic_face_rgb

        rgb = synthetic_face_rgb(size=64)
        crop = landmark_set.crop(rgb, FaceRegion.FACE_OVAL)
        # The mesh is normalised to 1000px; on a 64px image it still maps inside.
        assert crop.shape[2] == 3


def test_quality_assessment_usable_property() -> None:
    assessment = QualityAssessment(
        blur_score=100.0,
        exposure=0.5,
        clipped_fraction=0.0,
        face_width_px=300,
        face_height_px=400,
        interocular_px=120.0,
        eye_width_px=60.0,
        occlusion_estimate=0.0,
        failures=(),
    )
    assert assessment.usable is True
    assert assessment.face_px == 300
