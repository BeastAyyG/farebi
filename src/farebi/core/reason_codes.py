"""Canonical reason codes and the structured explanation object.

Every result the service returns carries a list of these. Three rules:

1. ``limitation`` is **mandatory**. A reason that reads as proof without stating
   what else could cause the same measurement is a bug, and the constructor
   rejects it.
2. ``direction`` is one of four values. Metadata-derived reasons are always
   ``neutral`` (non-negotiable #4: metadata is context, never proof).
3. ``strength`` is a magnitude in ``[0, 1]``, not a probability of fakery.

Naming note: ``PLANS/01-foundation.md`` calls this dataclass ``Signal``. It is
named ``Reason`` here because ``Signal`` is reserved for the plugin ABC in
``signals/base.py`` (FAREBI.md §5). Same object, non-colliding name.

Layer: L0 (may not import anything internal).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

__all__ = ["Direction", "Reason", "ReasonCode"]


class Direction(str, Enum):
    """Which way a piece of evidence points."""

    TOWARD_FAKE = "toward_fake"
    TOWARD_REAL = "toward_real"
    TOWARD_UNCERTAIN = "toward_uncertain"
    NEUTRAL = "neutral"


class ReasonCode(str, Enum):
    """The closed vocabulary of explanations.

    Adding a code is a deliberate act: the reviewer UI, the monitoring
    dashboards and the banned-phrase tests all key off these values.
    """

    # --- capture / quality -------------------------------------------------
    IMAGE_DECODED = "IMAGE_DECODED"
    IMAGE_REJECTED = "IMAGE_REJECTED"
    NO_FACE_DETECTED = "NO_FACE_DETECTED"
    MULTIPLE_FACES = "MULTIPLE_FACES"
    FACE_TOO_SMALL = "FACE_TOO_SMALL"
    IMAGE_TOO_BLURRY = "IMAGE_TOO_BLURRY"
    EXPOSURE_OUT_OF_RANGE = "EXPOSURE_OUT_OF_RANGE"
    LANDMARKS_UNAVAILABLE = "LANDMARKS_UNAVAILABLE"

    # --- model -------------------------------------------------------------
    VISUAL_MODEL_FAKE_SIGNAL = "VISUAL_MODEL_FAKE_SIGNAL"
    VISUAL_MODEL_REAL_SIGNAL = "VISUAL_MODEL_REAL_SIGNAL"
    MODEL_FACE_BOUNDARY_SIGNAL = "MODEL_FACE_BOUNDARY_SIGNAL"
    MODEL_DISAGREEMENT = "MODEL_DISAGREEMENT"

    # --- per-signal families (populated in phases 04-06) --------------------
    FREQUENCY_ARTIFACT = "FREQUENCY_ARTIFACT"
    TEXTURE_INCONSISTENCY = "TEXTURE_INCONSISTENCY"
    SENSOR_NOISE_ABSENT = "SENSOR_NOISE_ABSENT"
    SENSOR_NOISE_PRESENT = "SENSOR_NOISE_PRESENT"
    SCREEN_REPLAY_INDICATOR = "SCREEN_REPLAY_INDICATOR"
    CORNEAL_REFLECTION_INCONSISTENT = "CORNEAL_REFLECTION_INCONSISTENT"
    CHROMATIC_ABERRATION_ANOMALY = "CHROMATIC_ABERRATION_ANOMALY"
    PULSE_SIGNAL_ABSENT = "PULSE_SIGNAL_ABSENT"
    PERFUSION_MAP_ANOMALY = "PERFUSION_MAP_ANOMALY"
    SCLERAL_TOPOLOGY_ANOMALY = "SCLERAL_TOPOLOGY_ANOMALY"
    GEOMETRY_INCONSISTENCY = "GEOMETRY_INCONSISTENCY"

    # --- uncertainty / policy ---------------------------------------------
    OUT_OF_DISTRIBUTION = "OUT_OF_DISTRIBUTION"
    TRANSFORM_INSTABILITY = "TRANSFORM_INSTABILITY"
    INSIDE_UNCERTAIN_BAND = "INSIDE_UNCERTAIN_BAND"
    LOW_COVERAGE = "LOW_COVERAGE"
    SIGNAL_UNAVAILABLE = "SIGNAL_UNAVAILABLE"

    # --- metadata: always neutral -----------------------------------------
    METADATA_UNAVAILABLE = "METADATA_UNAVAILABLE"
    METADATA_INCONSISTENT = "METADATA_INCONSISTENT"


#: Codes that may only ever be emitted with ``Direction.NEUTRAL``.
#: Enforced by ``Reason.__post_init__`` and by tests/unit/test_reason_codes.py.
METADATA_CODES: frozenset[ReasonCode] = frozenset(
    {ReasonCode.METADATA_UNAVAILABLE, ReasonCode.METADATA_INCONSISTENT}
)


@dataclass(frozen=True, slots=True)
class Reason:
    """A single structured explanation attached to a result.

    Attributes:
        code: Which observation this is, from the closed :class:`ReasonCode` set.
        direction: Which way the observation points.
        strength: Magnitude in ``[0, 1]``. ``0.0`` for purely contextual notes.
        message: Human-readable statement, written for a non-technical reviewer.
        limitation: What else could produce this measurement. **Required.**
    """

    code: ReasonCode
    direction: Direction
    strength: float
    message: str
    limitation: str

    def __post_init__(self) -> None:
        if not isinstance(self.code, ReasonCode):
            raise TypeError(f"code must be a ReasonCode, got {type(self.code).__name__}")
        if not isinstance(self.direction, Direction):
            raise TypeError(f"direction must be a Direction, got {type(self.direction).__name__}")
        if not 0.0 <= self.strength <= 1.0:
            raise ValueError(f"strength must be within [0, 1], got {self.strength!r}")
        if not self.message.strip():
            raise ValueError("message must be a non-empty string")
        if not self.limitation.strip():
            # Non-negotiable: an unsupported claim is worse than no claim.
            raise ValueError(
                f"limitation is mandatory (code={self.code.value}); "
                "a reason without a stated limitation reads as proof"
            )
        if self.code in METADATA_CODES and self.direction is not Direction.NEUTRAL:
            raise ValueError(
                f"{self.code.value} is a metadata observation and must be "
                f"Direction.NEUTRAL (non-negotiable #4), got {self.direction.value}"
            )

    def to_dict(self) -> dict[str, object]:
        """Serialise to the API response shape (see ``IDEA.md`` §4)."""
        return {
            "code": self.code.value,
            "direction": self.direction.value,
            "strength": round(float(self.strength), 4),
            "message": self.message,
            "limitation": self.limitation,
        }
