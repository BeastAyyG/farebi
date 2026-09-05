"""Decode-path tests: valid inputs decode, invalid ones are refused precisely."""

from __future__ import annotations

import numpy as np
import pytest

from farebi.core.constants import RejectionCode
from farebi.core.security import UploadLimits, validate_upload
from farebi.utils.image_io import (
    DecodedImage,
    ImageDecodeError,
    UploadRejected,
    decode_image,
    validate_and_decode,
)
from fixtures.synthetic import (
    encode_grayscale_png,
    encode_jpeg,
    encode_png,
    hostile_cases,
    hostile_oversized,
    hostile_png_dimensions,
    hostile_truncated_jpeg,
    synthetic_face_rgb,
)


class TestValidDecoding:
    def test_png_decodes_to_rgb_uint8(self, png_bytes: bytes, upload_limits: UploadLimits) -> None:
        image = decode_image(png_bytes, declared_media_type="image/png", limits=upload_limits)

        assert isinstance(image, DecodedImage)
        assert image.array.ndim == 3
        assert image.array.shape[2] == 3
        assert image.array.dtype == np.uint8
        assert (image.width, image.height) == (512, 512)
        assert image.media_type == "image/png"
        assert len(image.sha256) == 64

    def test_jpeg_decodes_to_rgb_uint8(
        self, jpeg_bytes: bytes, upload_limits: UploadLimits
    ) -> None:
        image = decode_image(jpeg_bytes, declared_media_type="image/jpeg", limits=upload_limits)

        assert image.array.shape == (512, 512, 3)
        assert image.media_type == "image/jpeg"

    def test_grayscale_input_is_converted_to_three_channels(
        self, face_rgb, upload_limits: UploadLimits
    ) -> None:
        data = encode_grayscale_png(face_rgb)
        image = decode_image(data, declared_media_type="image/png", limits=upload_limits)

        assert image.array.shape == (512, 512, 3), "grayscale must be promoted to RGB"
        assert image.grayscale is True

    def test_to_bgr_is_contiguous_and_channel_swapped(
        self, png_bytes: bytes, upload_limits: UploadLimits
    ) -> None:
        image = decode_image(png_bytes, declared_media_type="image/png", limits=upload_limits)
        bgr = image.to_bgr()

        assert bgr.flags["C_CONTIGUOUS"]
        np.testing.assert_array_equal(bgr[:, :, 0], image.array[:, :, 2])
        np.testing.assert_array_equal(bgr[:, :, 2], image.array[:, :, 0])

    def test_exif_orientation_is_applied_and_reported(
        self, face_rgb, upload_limits: UploadLimits
    ) -> None:
        rotated = encode_jpeg(face_rgb, exif_orientation=6)  # 6 = rotate 90 CW
        image = decode_image(rotated, declared_media_type="image/jpeg", limits=upload_limits)

        assert image.orientation_applied is True

    def test_absent_orientation_is_not_reported_as_applied(
        self, jpeg_bytes: bytes, upload_limits: UploadLimits
    ) -> None:
        image = decode_image(jpeg_bytes, declared_media_type="image/jpeg", limits=upload_limits)
        assert image.orientation_applied is False


class TestRejection:
    def test_empty_upload(self, upload_limits: UploadLimits) -> None:
        with pytest.raises(UploadRejected) as excinfo:
            decode_image(b"", declared_media_type="image/jpeg", limits=upload_limits)
        assert excinfo.value.code is RejectionCode.EMPTY_UPLOAD

    def test_oversized_upload(self, upload_limits: UploadLimits) -> None:
        with pytest.raises(UploadRejected) as excinfo:
            decode_image(
                hostile_oversized(upload_limits),
                declared_media_type="image/jpeg",
                limits=upload_limits,
            )
        assert excinfo.value.code is RejectionCode.FILE_TOO_LARGE

    def test_truncated_header(self, upload_limits: UploadLimits) -> None:
        with pytest.raises(UploadRejected) as excinfo:
            decode_image(
                hostile_truncated_jpeg(),
                declared_media_type="image/jpeg",
                limits=upload_limits,
            )
        assert excinfo.value.code is RejectionCode.HEADER_TRUNCATED

    def test_oversized_dimensions_rejected_before_decode(self, upload_limits: UploadLimits) -> None:
        with pytest.raises(UploadRejected) as excinfo:
            decode_image(
                hostile_png_dimensions(20_000, 20_000),
                declared_media_type="image/png",
                limits=upload_limits,
            )
        assert excinfo.value.code is RejectionCode.DIMENSIONS_TOO_LARGE

    def test_declared_type_must_match_magic_bytes(
        self, png_bytes: bytes, upload_limits: UploadLimits
    ) -> None:
        with pytest.raises(UploadRejected) as excinfo:
            decode_image(png_bytes, declared_media_type="image/jpeg", limits=upload_limits)
        assert excinfo.value.code is RejectionCode.MAGIC_BYTES_MISMATCH

    def test_undeclared_type_is_rejected(
        self, png_bytes: bytes, upload_limits: UploadLimits
    ) -> None:
        with pytest.raises(UploadRejected) as excinfo:
            decode_image(png_bytes, declared_media_type=None, limits=upload_limits)
        assert excinfo.value.code is RejectionCode.MEDIA_TYPE_NOT_ALLOWED

    def test_corrupt_payload_raises_decode_error(
        self, jpeg_bytes: bytes, upload_limits: UploadLimits
    ) -> None:
        cut = int(len(jpeg_bytes) * 0.55)
        corrupt = jpeg_bytes[:cut] + b"\x00" * (len(jpeg_bytes) - cut)

        with pytest.raises((ImageDecodeError, UploadRejected)):
            decode_image(corrupt, declared_media_type="image/jpeg", limits=upload_limits)

    def test_pixel_bomb_above_configured_budget(self, upload_limits: UploadLimits) -> None:
        """A 3000x3000 PNG is under the edge cap but over a small pixel budget."""
        tight = UploadLimits(
            max_bytes=upload_limits.max_bytes,
            max_pixels=1_000_000,
            max_edge_px=4096,
            allowed_media_types=upload_limits.allowed_media_types,
        )
        data = encode_png(synthetic_face_rgb(size=100))  # header claims 100x100

        # 100x100 is fine; a forged header claiming 2000x2000 is not.
        with pytest.raises(UploadRejected) as excinfo:
            decode_image(
                hostile_png_dimensions(2000, 2000),
                declared_media_type="image/png",
                limits=tight,
            )
        assert excinfo.value.code is RejectionCode.PIXEL_BOMB
        assert decode_image(data, declared_media_type="image/png", limits=tight).width == 100

    def test_every_hostile_case_produces_its_expected_code(
        self, jpeg_bytes: bytes, upload_limits: UploadLimits
    ) -> None:
        """Matrix completeness: the smoke test and CI use the same expectations."""
        for name, (data, media_type, filename, expected) in hostile_cases(
            upload_limits, jpeg_bytes
        ).items():
            # DECODE_FAILED is a *decode-stage* rejection: the header passes every
            # security rule, so validate_upload reports OK and the failure only
            # surfaces when the pixels are actually decoded.
            if expected is RejectionCode.DECODE_FAILED:
                validation = validate_upload(
                    data,
                    declared_media_type=media_type,
                    filename=filename,
                    limits=upload_limits,
                )
                assert validation.ok, f"{name}: header should have passed validation"
                with pytest.raises(ImageDecodeError):
                    decode_image(
                        data,
                        declared_media_type=media_type,
                        filename=filename,
                        limits=upload_limits,
                    )
                continue

            image, validation = validate_and_decode(
                data,
                declared_media_type=media_type,
                filename=filename,
                limits=upload_limits,
            )
            assert image is None, f"{name}: expected rejection, got an image"
            assert validation is not None
            assert validation.code is expected, f"{name}: {validation.code} != {expected}"

    def test_non_raising_variant_returns_validation(self, upload_limits: UploadLimits) -> None:
        image, validation = validate_and_decode(
            b"", declared_media_type="image/jpeg", limits=upload_limits
        )
        assert image is None
        assert validation is not None
        assert not validation.ok

        with pytest.raises(UploadRejected):
            validation.raise_for_status()
