"""PII-safety of the logging layer, by construction rather than by convention.

Non-negotiable #14: never log raw images or EXIF values containing PII. This is
enforced by a processor that runs before any renderer, so it cannot be bypassed
by a careless call site.
"""

from __future__ import annotations

import logging

import pytest

from farebi.core.logging import PiiScrubber, bind, clear, configure_logging, get_logger

_RAW_IMAGE = b"\x89PNG\r\n\x1a\n" + b"\xde\xad\xbe\xef" * 64
_SECRET_PATH = r"C:\Users\applicant\Documents\passport_scan.jpg"


@pytest.fixture
def scrubbed() -> PiiScrubber:
    return PiiScrubber()


def _scrub(scrubber: PiiScrubber, **event: object) -> dict:
    return scrubber(None, "info", dict(event))


class TestPiiScrubber:
    def test_image_bytes_are_never_serialised(self, scrubbed: PiiScrubber) -> None:
        for key in ("image", "image_bgr", "image_rgb", "image_bytes", "raw", "thumbnail"):
            out = _scrub(scrubbed, **{key: _RAW_IMAGE})
            assert out[key] == "<redacted>", key

    def test_exif_and_metadata_are_redacted(self, scrubbed: PiiScrubber) -> None:
        for key in ("exif", "exif_data", "gps", "device_id", "sdk_meta"):
            out = _scrub(scrubbed, **{key: {"GPSLatitude": 51.5, "Serial": "ABC123"}})
            assert out[key] == "<redacted>", key

    def test_paths_are_redacted(self, scrubbed: PiiScrubber) -> None:
        for key in ("path", "image_path", "filename", "file_path"):
            out = _scrub(scrubbed, **{key: _SECRET_PATH})
            assert out[key] == "<redacted>", key

    def test_byte_values_become_a_length_only(self, scrubbed: PiiScrubber) -> None:
        out = _scrub(scrubbed, payload=_RAW_IMAGE)
        assert out["payload"] == f"<bytes len={len(_RAW_IMAGE)}>"
        assert _RAW_IMAGE not in str(out).encode()

    def test_long_strings_are_truncated(self, scrubbed: PiiScrubber) -> None:
        out = _scrub(scrubbed, note="x" * 5000)
        assert len(out["note"]) < 300
        assert out["note"].endswith("...<truncated>")

    def test_short_safe_values_survive(self, scrubbed: PiiScrubber) -> None:
        out = _scrub(scrubbed, request_id="abc-123", stage="decode", count=3)
        assert out["request_id"] == "abc-123"
        assert out["stage"] == "decode"
        assert out["count"] == 3

    def test_nested_structures_are_walked(self, scrubbed: PiiScrubber) -> None:
        out = _scrub(
            scrubbed, result={"image": _RAW_IMAGE, "info": {"exif": {"GPS": 1}, "ok": True}}
        )
        assert out["result"]["image"] == "<redacted>"
        assert out["result"]["info"]["exif"] == "<redacted>", "nested sensitive keys are redacted"
        assert out["result"]["info"]["ok"] is True, "sibling values survive"

    def test_lists_are_walked(self, scrubbed: PiiScrubber) -> None:
        out = _scrub(scrubbed, payloads=[_RAW_IMAGE, _RAW_IMAGE])
        assert all(item == f"<bytes len={len(_RAW_IMAGE)}>" for item in out["payloads"])

    def test_sensitive_list_key_redacts_the_whole_list(self, scrubbed: PiiScrubber) -> None:
        out = _scrub(scrubbed, frames=[_RAW_IMAGE, _RAW_IMAGE])
        assert out["frames"] == "<redacted>"

    def test_deep_nesting_does_not_hang(self, scrubbed: PiiScrubber) -> None:
        deep: dict = {"leaf": "value"}
        for _ in range(20):
            deep = {"child": deep}
        out = _scrub(scrubbed, tree=deep)
        assert "leaf" in str(out) or "max-depth" in str(out)

    def test_array_like_objects_report_only_their_type(self, scrubbed: PiiScrubber) -> None:
        class _ArrayLike:
            shape = (512, 512, 3)
            size = 786432

        out = _scrub(scrubbed, arr=_ArrayLike())
        assert out["arr"] == "<_ArrayLike>"


class TestEndToEndLogSafety:
    """Logs rendered through the real stack must not contain sensitive values."""

    def test_nothing_sensitive_reaches_the_rendered_output(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        configure_logging(level="INFO", json_logs=False)
        with caplog.at_level(logging.INFO):
            logger = get_logger("farebi.test.privacy")
            logger.info(
                "processing_upload",
                image_bytes=_RAW_IMAGE,
                exif={"Make": "Apple", "GPSPosition": "51.5N 0.1W"},
                image_path=_SECRET_PATH,
                request_id="req-1",
            )

        text = caplog.text
        assert "req-1" in text, "safe context should survive scrubbing"
        assert "Apple" not in text
        assert "GPSPosition" not in text
        assert "passport_scan" not in text
        assert "deadbeef" not in text

    def test_request_id_is_stamped_on_every_line(self, caplog: pytest.LogCaptureFixture) -> None:
        configure_logging(level="INFO", json_logs=True)
        clear()
        bind(request_id="req-42")

        with caplog.at_level(logging.INFO):
            get_logger("farebi.test.stamp").info("hello")

        assert "req-42" in caplog.text
        clear()

    def test_clear_removes_bound_context(self, caplog: pytest.LogCaptureFixture) -> None:
        configure_logging(level="INFO", json_logs=True)
        bind(request_id="req-99")
        clear()

        with caplog.at_level(logging.INFO):
            get_logger("farebi.test.clear").info("hello")

        assert "req-99" not in caplog.text
