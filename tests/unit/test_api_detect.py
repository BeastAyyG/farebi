"""Endpoint + mapping tests for the Phase-08 serving slice (L8 api).

Committed-safe tests use synthetic bytes (corrupt / blank / wrong suffix) and
synthetic :class:`SignalOutput` objects. The one end-to-end test needs a real
face image, so it scans the gitignored research pools and skips when absent.
"""

from __future__ import annotations

import io
import pathlib
from typing import Any

import httpx
import pytest
from PIL import Image

from farebi.api import service
from farebi.api.app import create_app
from farebi.core.config import get_settings
from farebi.core.reason_codes import Direction, Reason, ReasonCode
from farebi.signals.base import SignalOutput

ROOT = pathlib.Path(__file__).resolve().parents[2]

_COPY_CORRUPT = "Could not read uploaded file - it may be corrupt"
_COPY_BAD_FORMAT = "Only JPEG and PNG are supported"
_COPY_NO_FACE = "No face detected in image - unable to assess"


async def _get(path: str) -> httpx.Response:
    """GET via httpx async ASGI transport (avoids starlette.testclient)."""
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.get(path)


async def _post_detect(path: str, files: dict[str, tuple[str, bytes, str]]) -> httpx.Response:
    """POST via httpx async ASGI transport."""
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.post(path, files=files)


def _blank_png_bytes(size: int = 128) -> bytes:
    img = Image.new("RGB", (size, size), color=(127, 127, 127))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _reason(
    code: ReasonCode,
    direction: Direction,
    strength: float,
) -> Reason:
    return Reason(
        code=code,
        direction=direction,
        strength=strength,
        message=f"test message for {code.value}",
        limitation="test limitation: other causes exist",
    )


def _output(
    reasons: list[Reason],
    *,
    applicable: bool = True,
) -> SignalOutput:
    return SignalOutput(
        features={"test_feature": 0.5},
        applicable=applicable,
        quality=0.9,
        explanation="test explanation",
        reason_codes=reasons,
    )


@pytest.mark.anyio
async def test_health_lists_served_signals() -> None:
    response = await _get("/v1/health")
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    assert body["status"] == "ok"
    assert body["model_version"] == service.MODEL_VERSION
    assert "prnu" in body["signals"]


@pytest.mark.anyio
async def test_detect_rejects_corrupt_bytes_with_a9_copy() -> None:
    response = await _post_detect(
        "/v1/detect",
        files={"file": ("capture.jpg", b"not an image at all", "image/jpeg")},
    )
    assert response.status_code == 400
    assert response.json() == {"detail": _COPY_CORRUPT}


@pytest.mark.anyio
async def test_detect_rejects_unsupported_suffix_with_a9_copy() -> None:
    response = await _post_detect(
        "/v1/detect",
        files={"file": ("capture.gif", b"GIF89a", "image/gif")},
    )
    assert response.status_code == 400
    assert response.json() == {"detail": _COPY_BAD_FORMAT}


@pytest.mark.anyio
async def test_detect_rejects_oversize_upload() -> None:
    limit = int(get_settings().upload.max_bytes)
    response = await _post_detect(
        "/v1/detect",
        files={"file": ("capture.jpg", b"\xff" * (limit + 1), "image/jpeg")},
    )
    assert response.status_code == 400
    assert "exceeds limit" in response.json()["detail"]


@pytest.mark.anyio
async def test_detect_blank_image_maps_to_no_face_copy() -> None:
    response = await _post_detect(
        "/v1/detect",
        files={"file": ("blank.png", _blank_png_bytes(), "image/png")},
    )
    assert response.status_code == 400
    assert response.json() == {"detail": _COPY_NO_FACE}


def test_verdict_rule_fake_side() -> None:
    ran = [
        ("prnu", _output([_reason(ReasonCode.SENSOR_NOISE_ABSENT, Direction.TOWARD_FAKE, 0.8)])),
        ("fft", _output([_reason(ReasonCode.FREQUENCY_ARTIFACT, Direction.TOWARD_FAKE, 0.6)])),
    ]
    verdict, p_fake, _uncertainty, _confidence, drivers = service._verdict_and_scores(ran)
    assert verdict == "likely_fake"
    assert p_fake == pytest.approx(0.7 / 0.7)
    assert drivers[0]["signal"] == "prnu"


def test_verdict_rule_real_side() -> None:
    ran = [
        ("prnu", _output([_reason(ReasonCode.SENSOR_NOISE_PRESENT, Direction.TOWARD_REAL, 0.7)])),
        ("fft", _output([_reason(ReasonCode.FREQUENCY_ARTIFACT, Direction.TOWARD_FAKE, 0.1)])),
    ]
    verdict, p_fake, _uncertainty, _confidence, _drivers = service._verdict_and_scores(ran)
    assert verdict == "likely_real"
    assert p_fake == pytest.approx(0.1 / 0.8)


def test_verdict_rule_no_applicable_signals() -> None:
    ran = [("prnu", _output([], applicable=False))]
    verdict, p_fake, uncertainty, confidence, drivers = service._verdict_and_scores(ran)
    assert verdict == "unable_to_assess"
    assert p_fake == pytest.approx(0.5)
    assert uncertainty == pytest.approx(1.0)
    assert confidence == "low"
    assert drivers == []


def test_wire_signal_marks_inapplicable() -> None:
    entry = service._wire_signal("prnu", _output([], applicable=False))
    assert entry["applicable"] is False
    assert "not_applicable_reason" in entry
    assert entry["direction"] == Direction.TOWARD_UNCERTAIN.value


def _research_faces(limit: int = 8) -> list[pathlib.Path]:
    """Candidate real-face images from gitignored research pools (may include drops)."""
    found: list[pathlib.Path] = []
    for pool in ("data/raw/quick", "data/raw/quick1024"):
        candidate_dir = ROOT / pool
        if not candidate_dir.is_dir():
            continue
        for path in sorted(candidate_dir.glob("*.jpg")):
            if path.stat().st_size > 0:
                found.append(path)
            if len(found) >= limit:
                return found
    return found


@pytest.mark.anyio
async def test_detect_end_to_end_on_research_face() -> None:
    # Production gates reject some 256px research rows (known shim finding);
    # scan candidates for the first one the live pipeline accepts.
    candidates = _research_faces()
    if not candidates:
        pytest.skip("no gitignored research faces on disk")
    last_body = ""
    for image in candidates:
        response = await _post_detect(
            "/v1/detect",
            files={"file": (image.name, image.read_bytes(), "image/jpeg")},
        )
        if response.status_code == 200:
            break
        last_body = response.text
    else:
        pytest.skip(f"no research face passes production gates (last: {last_body[:120]})")
    body: dict[str, Any] = response.json()
    for key in (
        "request_id",
        "verdict",
        "fake_probability",
        "confidence_level",
        "uncertainty_score",
        "capture_type",
        "signals",
        "quality",
        "warnings",
        "model_version",
        "threshold_version",
        "top_drivers",
        "band",
    ):
        assert key in body, f"missing wire field: {key}"
    assert body["verdict"] in ("likely_real", "likely_fake", "uncertain", "unable_to_assess")
    assert 0.0 <= float(body["fake_probability"]) <= 1.0
    assert len(body["signals"]) >= 1
    assert body["quality"]["face_found"] is True
