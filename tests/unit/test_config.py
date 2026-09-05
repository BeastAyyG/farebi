"""Configuration layer: YAML + env precedence, validation, and failure modes."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from farebi.core.config import ConfigError, Settings, get_settings, reload_settings


class TestSettings:
    def test_yaml_values_are_loaded(self) -> None:
        settings = reload_settings()
        assert settings.upload.max_bytes == 10 * 1024 * 1024
        assert settings.upload.max_edge_px == 4096
        assert {"image/jpeg", "image/png"} <= set(settings.upload.allowed_media_types)

    def test_environment_overrides_yaml(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FAREBI_UPLOAD__MAX_BYTES", "2048")
        monkeypatch.setenv("FAREBI_APP__LOG_LEVEL", "DEBUG")

        settings = reload_settings()

        assert settings.upload.max_bytes == 2048
        assert settings.app.log_level == "DEBUG"

    def test_init_kwargs_beat_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FAREBI_UPLOAD__MAX_BYTES", "2048")
        settings = reload_settings(upload={"max_bytes": 4096})
        assert settings.upload.max_bytes == 4096

    def test_nested_environment_delimiter(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FAREBI_CAPTURE__QUALITY__MIN_FACE_PX", "128")
        assert reload_settings().capture.quality.min_face_px == 128

    def test_unknown_key_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            reload_settings(nonexistent_section={"a": 1})

    def test_settings_are_frozen(self) -> None:
        settings = reload_settings()
        with pytest.raises(ValidationError):
            settings.upload.max_bytes = 1  # type: ignore[misc]

    def test_out_of_range_value_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            reload_settings(upload={"max_bytes": -1})

    def test_retention_defaults_to_off(self) -> None:
        """Non-negotiable #7: uploads are not retained unless explicitly asked."""
        assert reload_settings().app.retention.keep_uploads is False

    def test_face_mesh_gates_are_configurable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FAREBI_CAPTURE__FACE_MESH__ENABLED", "false")
        assert reload_settings().capture.face_mesh.enabled is False

    def test_get_settings_is_cached(self) -> None:
        first = get_settings()
        assert get_settings() is first


class TestThresholdsAreNotHardcoded:
    """Non-negotiable #3: no decision threshold may live in a Python module."""

    def test_quality_gates_come_from_configuration(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FAREBI_CAPTURE__QUALITY__MIN_BLUR_SCORE", "999")
        settings = reload_settings()

        from farebi.capture.quality import assess_quality

        rgb = _flat_image()
        assessment = assess_quality(rgb, None, gates=settings.capture.quality)

        assert "blur" in assessment.failures, "gate must follow configuration, not a literal"

    def test_quality_gate_change_flips_the_outcome(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from farebi.capture.quality import assess_quality

        rgb = _flat_image()

        monkeypatch.setenv("FAREBI_CAPTURE__QUALITY__MIN_EXPOSURE", "0.9")
        strict = assess_quality(rgb, None, gates=reload_settings().capture.quality)
        monkeypatch.setenv("FAREBI_CAPTURE__QUALITY__MIN_EXPOSURE", "0.0")
        monkeypatch.setenv("FAREBI_CAPTURE__QUALITY__MAX_EXPOSURE", "1.0")
        lenient = assess_quality(rgb, None, gates=reload_settings().capture.quality)

        assert "exposure" in strict.failures
        assert "exposure" not in lenient.failures


def _flat_image():
    import numpy as np

    return np.full((64, 64, 3), 128, dtype=np.uint8)


def test_malformed_yaml_raises_config_error(tmp_path) -> None:
    """A broken config must fail loudly at load time, not at first request."""
    from farebi.core.config import YamlConfigSettingsSource

    broken = tmp_path / "app.yaml"
    broken.write_text("app: [unclosed\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="not valid YAML"):
        YamlConfigSettingsSource(Settings, broken)


def test_non_mapping_yaml_raises_config_error(tmp_path) -> None:
    from farebi.core.config import YamlConfigSettingsSource

    not_a_mapping = tmp_path / "app.yaml"
    not_a_mapping.write_text("- one\n- two\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="mapping at the top level"):
        YamlConfigSettingsSource(Settings, not_a_mapping)


def test_missing_yaml_file_is_not_an_error(tmp_path) -> None:
    """Absent config means defaults, not a crash — the package must be usable."""
    from farebi.core.config import YamlConfigSettingsSource

    source = YamlConfigSettingsSource(Settings, tmp_path / "does-not-exist.yaml")
    assert source() == {}
