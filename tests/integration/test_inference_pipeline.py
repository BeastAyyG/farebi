"""End-to-end pipeline integration.

The Phase 01 gate: one JPEG and one PNG traverse all eleven stages and produce a
well-formed result object. Whether MediaPipe finds a face in the synthetic image
is deliberately *not* asserted — that is a detection question, and there is no
detection logic yet.
"""

from __future__ import annotations

import json

import pytest

from farebi.capture.capture import CaptureStatus
from farebi.core.config import reload_settings
from farebi.core.constants import Verdict
from farebi.inference.pipeline import (
    CALIBRATION_VERSION,
    MODEL_VERSION,
    THRESHOLD_VERSION,
    DetectionPipeline,
)
from fixtures.synthetic import encode_jpeg, encode_png, synthetic_face_rgb

EXPECTED_STAGES = (
    "secure_file_validation",
    "decode",
    "capture",
    "signal_preflight",
    "feature_assembly",
    "calibrated_probability",
    "uncertainty",
    "attribution",
    "reason_generation",
    "verdict_policy",
    "response",
)


@pytest.fixture
def pipeline() -> DetectionPipeline:
    with DetectionPipeline() as instance:
        yield instance


@pytest.mark.parametrize(
    ("encoder", "media_type"),
    [(encode_jpeg, "image/jpeg"), (encode_png, "image/png")],
    ids=["jpeg", "png"],
)
def test_valid_upload_traverses_every_stage(pipeline, encoder, media_type) -> None:
    data = encoder(synthetic_face_rgb(size=512))
    result = pipeline.run(
        data, declared_media_type=media_type, filename=f"upload.{media_type[-3:]}"
    )

    assert result.rejection_code is None, result.reasons
    assert tuple(stage.name for stage in result.stages) == EXPECTED_STAGES
    assert all(stage.duration_ms >= 0 for stage in result.stages)
    assert len(result.image_sha256) == 64


def test_result_is_json_serialisable_and_complete(pipeline) -> None:
    result = pipeline.run(
        encode_png(synthetic_face_rgb(size=256)),
        declared_media_type="image/png",
    )
    payload = result.to_dict()

    # Round-trips through JSON: nothing exotic is allowed in the contract.
    restored = json.loads(json.dumps(payload))
    for key in (
        "request_id",
        "verdict",
        "fake_probability",
        "confidence_level",
        "uncertainty",
        "capture_status",
        "quality",
        "signals",
        "reasons",
        "stages",
        "warnings",
        "image_sha256",
        "model_version",
        "threshold_version",
        "calibration_version",
    ):
        assert key in restored, key


def test_versions_are_echoed_on_every_response(pipeline) -> None:
    """Non-negotiable #10: a result must be reproducible from these keys."""
    result = pipeline.run(encode_png(synthetic_face_rgb(size=256)), declared_media_type="image/png")
    assert result.model_version == MODEL_VERSION
    assert result.threshold_version == THRESHOLD_VERSION
    assert result.calibration_version == CALIBRATION_VERSION


def test_no_verdict_is_invented_before_signals_exist(pipeline) -> None:
    """`verdict is None` is the honest answer until Phase 07 lands."""
    result = pipeline.run(encode_png(synthetic_face_rgb(size=256)), declared_media_type="image/png")

    assert result.verdict in (None, Verdict.UNABLE_TO_ASSESS)
    assert result.fake_probability is None
    assert result.confidence_level is None
    assert result.signals == ()


def test_placeholder_stages_are_marked_not_executed(pipeline) -> None:
    result = pipeline.run(encode_png(synthetic_face_rgb(size=256)), declared_media_type="image/png")
    by_name = {stage.name: stage for stage in result.stages}

    # These stages must always run for a valid submission:
    # decode always succeeds, and the verdict policy always fires.
    assert by_name["decode"].executed is True
    assert by_name["verdict_policy"].executed is True
    # The capture stage is always *recorded*; whether it succeeds depends on
    # MediaPipe being present and finding a face. In degraded mode it reports
    # LANDMARKS_UNAVAILABLE — that is still a successful traversal, so we only
    # assert the stage ran (is present) here, not that it produced a capture.
    assert "capture" in by_name

    for name in (
        "signal_preflight",
        "feature_assembly",
        "calibrated_probability",
        "uncertainty",
        "attribution",
        "reason_generation",
    ):
        assert by_name[name].executed is False, f"{name} must remain a placeholder"
        assert by_name[name].note


def test_request_id_is_propagated_and_defaulted(pipeline) -> None:
    data = encode_png(synthetic_face_rgb(size=256))

    explicit = pipeline.run(data, declared_media_type="image/png", request_id="abc-123")
    generated = pipeline.run(data, declared_media_type="image/png")

    assert explicit.request_id == "abc-123"
    assert generated.request_id != "abc-123"
    assert len(generated.request_id) == 36


def test_warnings_always_include_the_limitation_notice(pipeline) -> None:
    result = pipeline.run(encode_png(synthetic_face_rgb(size=256)), declared_media_type="image/png")
    joined = " ".join(result.warnings)
    assert "manual review" in joined
    assert "liveness" in joined


class TestDegradedMode:
    def test_pipeline_runs_with_face_mesh_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """CI without MediaPipe must still produce a well-formed result."""
        monkeypatch.setenv("FAREBI_CAPTURE__FACE_MESH__ENABLED", "false")
        settings = reload_settings()

        with DetectionPipeline(settings) as pipeline:
            result = pipeline.run(
                encode_png(synthetic_face_rgb(size=256)),
                declared_media_type="image/png",
            )

        assert result.capture_status is CaptureStatus.LANDMARKS_UNAVAILABLE
        assert result.verdict is Verdict.UNABLE_TO_ASSESS
        assert tuple(stage.name for stage in result.stages) == EXPECTED_STAGES
        assert any(reason.code.value == "LANDMARKS_UNAVAILABLE" for reason in result.reasons)

    def test_pipeline_runs_when_mediapipe_is_absent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from farebi.capture import face_mesh as face_mesh_module

        monkeypatch.setattr(
            face_mesh_module.FaceMeshDetector, "is_installed", staticmethod(lambda: False)
        )
        with DetectionPipeline() as pipeline:
            result = pipeline.run(
                encode_png(synthetic_face_rgb(size=256)),
                declared_media_type="image/png",
            )

        assert result.capture_status is CaptureStatus.LANDMARKS_UNAVAILABLE
        assert result.verdict is Verdict.UNABLE_TO_ASSESS


class TestCaptureOutcomeIsReported:
    def test_quality_block_is_present_when_capture_succeeded(self, pipeline) -> None:
        result = pipeline.run(
            encode_png(synthetic_face_rgb(size=512)), declared_media_type="image/png"
        )
        if result.capture_status is CaptureStatus.OK:
            assert result.quality is not None
            assert result.quality["usable"] is True
        else:
            # Synthetic faces are frequently not detected; that is fine here.
            assert result.capture_status is not CaptureStatus.OK


def test_pipeline_context_manager_closes_the_detector() -> None:
    with DetectionPipeline() as pipeline:
        assert pipeline._detector._enabled in (True, False)

    # close() releases the native backend handle; the detector stays enabled.
    assert pipeline._detector._backend is None or pipeline._detector._enabled is False
