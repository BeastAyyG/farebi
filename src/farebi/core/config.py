"""Configuration loading: ``configs/*.yaml`` overridden by environment.

Design rules:

* There is exactly one ``Settings`` object. No module reads ``os.environ``
  directly, and no module opens a YAML file directly.
* Priority (highest first): init kwargs > environment > ``.env`` > YAML >
  field defaults.
* Every section is a nested pydantic model, so a typo in ``configs/app.yaml``
  fails at import time with a precise message rather than at first request.

Layer: L0 (may not import anything internal).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal, TypeVar

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from farebi.core.constants import HarnessStatus

__all__ = [
    "ArtifactsConfig",
    "CaptureConfig",
    "ConfigError",
    "FaceMeshConfig",
    "QualityConfig",
    "RetentionConfig",
    "Settings",
    "SignalEntryConfig",
    "SignalsConfig",
    "TrainingConfig",
    "UploadConfig",
    "get_settings",
    "reload_settings",
]

_CONFIG_DIR = Path(__file__).resolve().parents[3] / "configs"
_ENV_PREFIX = "FAREBI_"

#: Loaded in order; later files win. Split by concern, not by layer: the signal
#: registry is rewritten by the harness on every run, so it is kept out of
#: ``app.yaml`` (which humans edit) to avoid churn and merge conflicts.
_CONFIG_FILES: tuple[str, ...] = ("app.yaml", "signals.yaml", "training.yaml")


class ConfigError(RuntimeError):
    """Raised when the configuration is missing, malformed, or contradictory."""


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------


class RetentionConfig(BaseModel):
    """Upload retention. Defaults to *not retaining anything* (non-negotiable #7)."""

    model_config = ConfigDict(frozen=True)

    keep_uploads: bool = False
    temp_dir: str | None = None


class AppConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = "farebi"
    env: str = "development"
    log_level: str = "INFO"
    log_format: str = "json"
    request_id_header: str = "X-Request-ID"
    retention: RetentionConfig = Field(default_factory=RetentionConfig)


class UploadConfig(BaseModel):
    """Limits enforced *before* an image is decoded."""

    model_config = ConfigDict(frozen=True)

    max_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    max_pixels: int = Field(default=40_000_000, gt=0)
    max_edge_px: int = Field(default=4096, gt=0)
    allowed_media_types: tuple[str, ...] = ("image/jpeg", "image/png")
    allow_multiframe: bool = False


class FaceMeshConfig(BaseModel):
    """MediaPipe face landmarker. ``enabled: false`` gives a degraded-but-running pipeline.

    ``backend`` selects the MediaPipe API. ``auto`` prefers the legacy
    ``solutions`` graph and falls back to ``tasks``; recent MediaPipe releases
    removed ``solutions`` entirely, so ``tasks`` (which needs ``model_path``)
    is what most installs will end up using.
    """

    model_config = ConfigDict(frozen=True)

    enabled: bool = True
    backend: Literal["auto", "solutions", "tasks"] = "auto"
    model_path: str = "artifacts/models/face_landmarker.task"
    max_num_faces: int = Field(default=3, gt=0)
    min_detection_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    refine_landmarks: bool = True  # required for the 10 iris points (468-477)


class QualityConfig(BaseModel):
    """Capture-quality gates. Non-negotiable #3: never hardcoded in a signal."""

    model_config = ConfigDict(frozen=True)

    min_face_px: int = Field(default=96, gt=0)
    min_interocular_px: int = Field(default=40, gt=0)
    min_eye_width_px: int = Field(default=40, gt=0)
    min_blur_score: float = Field(default=45.0, ge=0.0)
    min_exposure: float = Field(default=0.15, ge=0.0, le=1.0)
    max_exposure: float = Field(default=0.85, ge=0.0, le=1.0)
    max_clipped_fraction: float = Field(default=0.20, ge=0.0, le=1.0)


class CaptureConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    face_mesh: FaceMeshConfig = Field(default_factory=FaceMeshConfig)
    quality: QualityConfig = Field(default_factory=QualityConfig)


class SignalEntryConfig(BaseModel):
    """One signal's registry row, as written by ``scripts/run_harness.py``.

    The harness owns ``status``; humans must not hand-promote a signal by
    editing this file, which is why ``status`` defaults to ``unmeasured``
    (not fusion-eligible) rather than to something optimistic.
    """

    model_config = ConfigDict(frozen=True)

    status: HarnessStatus = HarnessStatus.UNMEASURED
    tier: int = Field(default=1, ge=1, le=3)
    module: str | None = None
    requires: tuple[str, ...] = ()
    weight: float | None = None  # null => weight comes from the fitted fusion
    cross_source_auc: float | None = Field(default=None, ge=0.0, le=1.0)
    coverage: float | None = Field(default=None, ge=0.0, le=1.0)
    evaluated_on: str | None = None


class SignalsConfig(BaseModel):
    """The signal registry (``configs/signals.yaml``)."""

    model_config = ConfigDict(frozen=True)

    registry_version: str = "empty-0.0.0"
    #: Applied to any discovered signal with no explicit row. ``unmeasured`` is
    #: fail-closed: an unmeasured signal contributes nothing to fusion.
    default_status: HarnessStatus = HarnessStatus.UNMEASURED
    entries: dict[str, SignalEntryConfig] = Field(default_factory=dict)


class KYCDegradationConfig(BaseModel):
    """Ranges for :class:`farebi.degradation.kyc_pipeline.KYCDegradation`.

    Every value is a *range*, not a tuning constant: the simulator samples from
    them per image. They are educated guesses until real production uploads
    exist, which is exactly why they live in YAML and get recalibrated in
    Phase 03 (``PLANS/02`` risk table).
    """

    model_config = ConfigDict(frozen=True)

    enabled: bool = True
    #: Long-edge sizes a KYC app actually ships. Sampled uniformly.
    resize_long_edge: tuple[int, ...] = (720, 960, 1080, 1280)
    jpeg_quality: tuple[int, int] = (80, 95)
    #: Multiplicative gain jitter and additive offset jitter (0-255 scale).
    awb_alpha: tuple[float, float] = (0.9, 1.1)
    awb_beta: tuple[float, float] = (-10.0, 10.0)
    blur_sigma: tuple[float, float] = (0.3, 1.0)
    blur_probability: float = Field(default=0.3, ge=0.0, le=1.0)
    #: The upload-SDK re-encode. This is the one that kills fragile signals.
    recompress_quality: tuple[int, int] = (70, 90)

    @model_validator(mode="after")
    def _check_ranges(self) -> KYCDegradationConfig:
        for name in ("jpeg_quality", "recompress_quality"):
            low, high = getattr(self, name)
            if not 1 <= low <= high <= 100:
                raise ValueError(f"{name} must satisfy 1 <= low <= high <= 100, got {(low, high)}")
        if not self.resize_long_edge:
            raise ValueError("resize_long_edge must not be empty")
        if any(edge <= 0 for edge in self.resize_long_edge):
            raise ValueError(f"resize_long_edge values must be positive, got {self.resize_long_edge}")
        for name in ("awb_alpha", "awb_beta", "blur_sigma"):
            low, high = getattr(self, name)
            if low > high:
                raise ValueError(f"{name} must satisfy low <= high, got {(low, high)}")
        return self


class GeometricAugmentationConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    horizontal_flip: bool = True
    rotation_deg: float = Field(default=0.0, ge=0.0, le=45.0)


class AugmentationConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    kyc_degradation: KYCDegradationConfig = Field(default_factory=KYCDegradationConfig)
    geometric: GeometricAugmentationConfig = Field(default_factory=GeometricAugmentationConfig)


class ReplayConfig(BaseModel):
    """Ranges for the screen-replay simulator (:mod:`farebi.degradation.replay`).

    This builds the *replay attack* evaluation set, so it is dataset
    construction rather than training augmentation — hence its own section.
    """

    model_config = ConfigDict(frozen=True)

    enabled: bool = True
    #: The display the attacker plays the image back on.
    display_resolution: tuple[int, int] = (1920, 1080)
    #: Moiré: interference period in pixels, and its amplitude on 0-255 luma.
    moire_pitch_px: tuple[float, float] = (2.0, 6.0)
    moire_amplitude: tuple[float, float] = (2.0, 8.0)
    #: Per-channel display gain (RGB). Slightly non-unit is what a real panel does.
    gamut_gain: tuple[float, float, float] = (1.04, 0.99, 1.02)
    sheen_probability: float = Field(default=0.5, ge=0.0, le=1.0)
    sheen_strength: tuple[float, float] = (10.0, 60.0)
    #: Screen photos lose micro-contrast; this is the blur mixed back in.
    depth_flatten_sigma: tuple[float, float] = (0.4, 1.2)

    @model_validator(mode="after")
    def _check_ranges(self) -> ReplayConfig:
        width, height = self.display_resolution
        if width <= 0 or height <= 0:
            raise ValueError(f"display_resolution must be positive, got {self.display_resolution}")
        for name in ("moire_pitch_px", "moire_amplitude", "sheen_strength", "depth_flatten_sigma"):
            low, high = getattr(self, name)
            if low <= 0 or low > high:
                raise ValueError(f"{name} must satisfy 0 < low <= high, got {(low, high)}")
        return self


class OptimizerConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = "adamw"
    lr: float = Field(default=3e-4, gt=0.0)
    weight_decay: float = Field(default=0.01, ge=0.0)


class SchedulerConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = "cosine"
    warmup_epochs: int = Field(default=1, ge=0)


class TrainingConfig(BaseModel):
    """``configs/training.yaml`` — everything the offline factory needs."""

    model_config = ConfigDict(frozen=True)

    seed: int = 1337
    deterministic: bool = True
    device: Literal["auto", "cpu", "cuda", "mps"] = "auto"
    batch_size: int = Field(default=32, gt=0)
    epochs: int = Field(default=20, gt=0)
    num_workers: int = Field(default=4, ge=0)
    class_weighting: str = "balanced"
    replay: ReplayConfig = Field(default_factory=ReplayConfig)
    optimizer: OptimizerConfig = Field(default_factory=OptimizerConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    augmentation: AugmentationConfig = Field(default_factory=AugmentationConfig)


class ArtifactsConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    dir: str = "artifacts"


# ---------------------------------------------------------------------------
# YAML settings source (lowest priority above field defaults)
# ---------------------------------------------------------------------------


class YamlConfigSettingsSource(PydanticBaseSettingsSource):
    """Feeds ``configs/*.yaml`` into pydantic-settings.

    Implemented as a settings *source* rather than a plain dict merge so that
    the documented precedence (env beats YAML) is preserved by the library
    instead of by hand-rolled logic.

    Several files are merged shallowly, in order, later winning — so
    ``signals.yaml`` can be machine-rewritten without touching ``app.yaml``.
    """

    def __init__(
        self, settings_cls: type[BaseSettings], paths: Path | tuple[Path, ...] | list[Path]
    ) -> None:
        super().__init__(settings_cls)
        # Accept either a single path or a sequence of paths, so callers (and the
        # tests) may pass one file as easily as several.
        if isinstance(paths, Path):
            paths = (paths,)
        elif not isinstance(paths, (tuple, list)):
            raise ConfigError(
                f"YamlConfigSettingsSource expects a path or sequence of paths, got "
                f"{type(paths).__name__}"
            )
        self._paths = tuple(paths)
        self._data: dict[str, Any] = {}
        for path in self._paths:
            self._data.update(self._read(path))

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:  # malformed YAML is a hard failure
            raise ConfigError(f"{path} is not valid YAML: {exc}") from exc
        if raw is None:
            return {}
        if not isinstance(raw, dict):
            raise ConfigError(
                f"{path} must contain a mapping at the top level, got {type(raw).__name__}"
            )
        return raw

    def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:
        return self._data.get(field_name), field_name, False

    def __call__(self) -> dict[str, Any]:
        known = self.settings_cls.model_fields
        # Unknown keys are ignored here; `extra="forbid"` on Settings surfaces
        # them as an error once they reach validation.
        return {key: value for key, value in self._data.items() if key in known}

    def __repr__(self) -> str:
        return f"{type(self).__name__}(paths={[str(p) for p in self._paths]})"


# ---------------------------------------------------------------------------
# Root settings
# ---------------------------------------------------------------------------


class Settings(BaseSettings):
    """The single configuration object for the whole process."""

    model_config = SettingsConfigDict(
        env_prefix=_ENV_PREFIX,
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",  # a stray key in app.yaml must not pass silently
        frozen=True,
        validate_default=True,
    )

    app: AppConfig = Field(default_factory=AppConfig)
    upload: UploadConfig = Field(default_factory=UploadConfig)
    capture: CaptureConfig = Field(default_factory=CaptureConfig)
    signals: SignalsConfig = Field(default_factory=SignalsConfig)
    training: TrainingConfig = Field(default_factory=TrainingConfig)
    artifacts: ArtifactsConfig = Field(default_factory=ArtifactsConfig)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Highest priority first. YAML sits just above field defaults.
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlConfigSettingsSource(
                settings_cls, tuple(_CONFIG_DIR / name for name in _CONFIG_FILES)
            ),
            file_secret_settings,
        )


T = TypeVar("T", bound=BaseSettings)


def _build() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        raise ConfigError(f"invalid Farebi configuration:\n{exc}") from exc


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return the process-wide settings, constructing them on first use.

    Tests call :func:`reload_settings` after mutating the environment.
    """
    global _settings
    if _settings is None:
        _settings = _build()
    return _settings


def reload_settings(**overrides: Any) -> Settings:
    """Rebuild settings, applying ``overrides`` at the highest priority."""
    global _settings
    _settings = Settings(**overrides)
    return _settings


def config_dir() -> Path:
    """Directory holding the YAML config files (exported for scripts/tests)."""
    override = os.getenv(f"{_ENV_PREFIX}CONFIG_DIR")
    return Path(override) if override else _CONFIG_DIR
