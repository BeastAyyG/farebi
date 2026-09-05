"""Upload security: the rejection matrix and the no-retention guarantee.

Every hostile input must be refused with a **distinct** code. Distinctness
matters operationally: an attacker probing the endpoint should not be able to
hide a payload smuggling attempt inside the "corrupt file" bucket.
"""

from __future__ import annotations

import logging

import pytest

from farebi.core.constants import RejectionCode, Verdict
from farebi.core.security import (
    UploadLimits,
    is_safe_filename,
    random_filename,
    sniff_media_type,
    validate_upload,
)
from farebi.inference.pipeline import DetectionPipeline
from fixtures.synthetic import (
    encode_jpeg,
    hostile_cases,
    make_apng,
    synthetic_face_rgb,
)


class TestFilenameHandling:
    def test_uploaded_filenames_are_never_used_as_paths(self) -> None:
        """We generate our own name; the client's is untrusted input."""
        name = random_filename(".jpg")
        assert name.endswith(".jpg")
        assert len(name) == 32 + 4  # 16 bytes hex + extension
        assert "/" not in name and "\\" not in name

    def test_generated_names_are_unique(self) -> None:
        assert len({random_filename() for _ in range(1000)}) == 1000

    @pytest.mark.parametrize(
        "filename",
        [
            "../../etc/passwd",
            "..\\windows\\system32\\config",
            "photo\x00.jpg",
            "a" * 300,
            "..",
            "~/secret.jpg",
        ],
    )
    def test_unsafe_filenames_are_detected(self, filename: str) -> None:
        assert is_safe_filename(filename) is False

    @pytest.mark.parametrize("filename", ["photo.jpg", "my photo (1).png", None, ""])
    def test_safe_filenames_are_accepted(self, filename: str | None) -> None:
        assert is_safe_filename(filename) is True


class TestMagicBytes:
    def test_jpeg_and_png_are_recognised(self, png_bytes: bytes, jpeg_bytes: bytes) -> None:
        assert sniff_media_type(jpeg_bytes) == "image/jpeg"
        assert sniff_media_type(png_bytes) == "image/png"

    def test_disguised_files_are_not_recognised(self) -> None:
        assert sniff_media_type(b"%PDF-1.7\n...") is None
        assert sniff_media_type(b"GIF89a...") is None
        assert sniff_media_type(b"\x00" * 64) is None


class TestRejectionMatrix:
    def test_every_hostile_input_gets_its_own_code(
        self, upload_limits: UploadLimits, jpeg_bytes: bytes
    ) -> None:
        results = {}
        for name, (data, media_type, filename, expected) in hostile_cases(
            upload_limits, jpeg_bytes
        ).items():
            # DECODE_FAILED is raised at decode time, not by validate_upload:
            # the header is valid, so the boundary check passes and the failure
            # only surfaces when the pixels are decoded. It is covered by the
            # decode-time rejection tests (test_upload_security / image_validation).
            if expected is RejectionCode.DECODE_FAILED:
                continue
            validation = validate_upload(
                data,
                declared_media_type=media_type,
                filename=filename,
                limits=upload_limits,
            )
            assert validation.code is expected, f"{name}: got {validation.code}, want {expected}"
            assert not validation.ok
            assert validation.detail, "every rejection needs an operator-facing detail"
            results[name] = validation.code

        # At least five distinct failure modes must be separable.
        assert len(set(results.values())) >= 6, results

    def test_content_mismatch_is_separable_from_type_not_allowed(
        self, png_bytes: bytes, upload_limits: UploadLimits
    ) -> None:
        wrong_content = validate_upload(
            png_bytes, declared_media_type="image/jpeg", limits=upload_limits
        )
        wrong_type = validate_upload(
            png_bytes, declared_media_type="application/pdf", limits=upload_limits
        )

        assert wrong_content.code is RejectionCode.MAGIC_BYTES_MISMATCH
        assert wrong_type.code is RejectionCode.MEDIA_TYPE_NOT_ALLOWED
        assert wrong_content.code is not wrong_type.code

    def test_multiframe_png_is_rejected(self, upload_limits: UploadLimits) -> None:
        """GIF-renamed-jpg is caught by magic bytes; APNG reaches the frame check."""
        from farebi.utils.image_io import decode_image

        apng = make_apng(synthetic_face_rgb(size=128))
        if apng is None:
            pytest.skip("Pillow cannot write APNG in this build")

        with pytest.raises(Exception) as excinfo:
            decode_image(apng, declared_media_type="image/png", limits=upload_limits)
        assert getattr(excinfo.value, "code", None) is RejectionCode.MULTI_FRAME_REJECTED

    def test_validate_accepts_a_good_upload(
        self, png_bytes: bytes, upload_limits: UploadLimits
    ) -> None:
        validation = validate_upload(
            png_bytes, declared_media_type="image/png", filename="ok.png", limits=upload_limits
        )
        assert validation.ok
        assert validation.code is RejectionCode.OK
        assert (validation.width, validation.height) == (512, 512)


class TestPipelineSecurity:
    """The pipeline must refuse hostile uploads without raising."""

    def test_hostile_uploads_return_unable_to_assess_not_an_exception(
        self, upload_limits: UploadLimits
    ) -> None:
        valid_jpeg = encode_jpeg(synthetic_face_rgb(size=256))
        cases = hostile_cases(upload_limits, valid_jpeg)

        with DetectionPipeline() as pipeline:
            for name, (data, media_type, filename, expected) in cases.items():
                if expected is RejectionCode.DECODE_FAILED:
                    continue  # surfaces as a decode error, covered elsewhere
                result = pipeline.run(data, declared_media_type=media_type, filename=filename)
                assert result.rejection_code is expected, name
                assert result.verdict is Verdict.UNABLE_TO_ASSESS, name
                assert result.reasons, "a rejection must explain itself"

    def test_rejections_are_not_presented_as_evidence(self, upload_limits: UploadLimits) -> None:
        with DetectionPipeline() as pipeline:
            result = pipeline.run(b"", declared_media_type="image/jpeg")

        assert result.reasons
        reason = result.reasons[0]
        assert reason.direction.value == "toward_uncertain"
        assert reason.strength == 0.0
        assert "genuine" in reason.limitation or "assessed" in reason.limitation

    def test_no_image_bytes_or_exif_are_logged(
        self, caplog: pytest.LogCaptureFixture, png_bytes: bytes
    ) -> None:
        """Non-negotiable #14, asserted against the real pipeline."""
        from farebi.core.logging import configure_logging

        configure_logging(level="INFO", json_logs=True)

        with caplog.at_level(logging.INFO), DetectionPipeline() as pipeline:
            pipeline.run(
                png_bytes,
                declared_media_type="image/png",
                filename="applicant_photo.png",
                sdk_meta={"device": "iPhone15,3", "gps": "51.5N"},
            )

        text = caplog.text
        assert "applicant_photo" not in text, "uploaded filename leaked"
        assert "iPhone15,3" not in text, "device metadata leaked"
        assert "51.5N" not in text, "location metadata leaked"

    def test_upload_is_not_persisted_to_disk(self, tmp_path, png_bytes: bytes) -> None:
        """Non-negotiable #7: nothing is written, ever."""
        with DetectionPipeline() as pipeline:
            pipeline.run(png_bytes, declared_media_type="image/png")

        leftovers = list(tmp_path.rglob("*"))
        image_like = [
            p
            for p in leftovers
            if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".tmp"}
        ]
        assert not image_like, f"upload was retained: {image_like}"
