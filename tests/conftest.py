"""Shared pytest fixtures and the import shim for ``tests/fixtures``.

``tests`` is on ``sys.path`` (see ``pyproject.toml`` → ``pythonpath``) so that
``from fixtures.synthetic import ...`` resolves identically for every test
module and for ``scripts/smoke_test.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from farebi.core.config import Settings, reload_settings
from farebi.core.logging import clear, configure_logging
from farebi.core.security import UploadLimits

_TESTS_DIR = Path(__file__).resolve().parent
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))


@pytest.fixture(autouse=True)
def _clean_logging() -> None:
    """Give every test a freshly configured, quiet logging stack."""
    configure_logging(level="WARNING", json_logs=False)
    clear()
    yield
    clear()


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Point artifacts at a temp dir so tests never touch ``artifacts/``.

    Settings are frozen, so this rebuilds them rather than mutating.
    """
    monkeypatch.delenv("FAREBI_ARTIFACTS__DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    return reload_settings(artifacts={"dir": str(tmp_path / "artifacts")})


@pytest.fixture
def upload_limits() -> UploadLimits:
    """Limits matching ``configs/app.yaml``, independent of the live settings."""
    return UploadLimits(
        max_bytes=10 * 1024 * 1024,
        max_pixels=40_000_000,
        max_edge_px=4096,
        allowed_media_types=frozenset({"image/jpeg", "image/png"}),
        allow_multiframe=False,
    )


@pytest.fixture
def face_rgb():
    """A deterministic synthetic face as an RGB uint8 array."""
    from fixtures.synthetic import synthetic_face_rgb

    return synthetic_face_rgb(size=512)


@pytest.fixture
def png_bytes(face_rgb):
    from fixtures.synthetic import encode_png

    return encode_png(face_rgb)


@pytest.fixture
def jpeg_bytes(face_rgb):
    from fixtures.synthetic import encode_jpeg

    return encode_jpeg(face_rgb, quality=92)
