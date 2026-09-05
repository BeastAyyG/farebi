"""The Signal contract — ``FAREBI.md`` §5.

Every detection idea, conventional or exotic, is a plugin behind this one
interface. That is what makes a signal a one-day addition, a one-hour
measurement, and a painless deletion.

Three things live here:

* :class:`SignalOutput` — what a signal returns. **Features, never verdicts.**
* :class:`Signal` — the plugin ABC, plus :meth:`Signal.__call__` which applies
  the applicability gate so that no author can forget it.
* :func:`require` / :func:`reason` — the two helpers every plugin uses.

``Capture`` is **defined** in :mod:`farebi.capture.capture` (L1) and re-exported
here because ``FAREBI.md`` §5 specifies it as part of this contract. One
definition, two import paths.

Naming note: ``PLANS/02-signal-factory.md`` calls the applicability helper's
argument ``min_requirements``; requirement keys are prefixed ``min_`` / ``max_``
/ ``needs_`` so that a single resolver table can evaluate them generically.

Layer: L2 (may import L0, L1).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, Final

from farebi.capture.capture import Capture
from farebi.core.reason_codes import Direction, Reason, ReasonCode

__all__ = [
    "MAX_TIER",
    "MIN_TIER",
    "Capture",
    "Signal",
    "SignalError",
    "SignalOutput",
    "REQUIREMENT_KEYS",
    "reason",
    "require",
]

MIN_TIER: Final = 1
MAX_TIER: Final = 3


class SignalError(RuntimeError):
    """Raised for a malformed plugin declaration.

    This is a *programming* error — a bad ``min_requirements`` key or a missing
    ``name`` — not a statement about an image. Nothing in the request path
    should ever catch it; it is a build-time failure wearing a runtime type.
    """


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SignalOutput:
    """What a signal returns. Never a verdict — see ``FAREBI.md`` §5 rule 1.

    Attributes:
        features: Raw measurements, ``{name: value}``. These feed the learned
            fusion. An empty dict means "nothing measurable", which is a valid
            and honest answer.
        applicable: ``False`` when the signal could not run on this input
            (eyes too small, no video, no landmarks). **Not** evidence.
        quality: ``0``–``1``, how trustworthy these features are *on this
            input*. Drives the quality mask in fusion.
        explanation: Human-readable, cites the actual feature values.
        reason_codes: Structured reasons. Every one carries a ``limitation``.
        artifacts: Crops, spectra, waveforms for the reviewer UI. Never sent
            to the fusion model.
    """

    features: dict[str, float]
    applicable: bool
    quality: float
    explanation: str
    reason_codes: list[Reason]
    artifacts: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 <= self.quality <= 1.0:
            raise ValueError(f"quality must be within [0, 1], got {self.quality!r}")
        if not self.explanation.strip():
            raise ValueError("explanation must be a non-empty string")
        for key, value in self.features.items():
            # NaN and inf would poison a learned fusion silently; reject at the
            # boundary rather than debugging a model that predicts NaN.
            if not isinstance(key, str):  # pragma: no cover - dict[str, float]
                raise TypeError(f"feature keys must be str, got {type(key).__name__}")
            if value != value or value in (float("inf"), float("-inf")):
                raise ValueError(f"feature {key!r} is not finite: {value!r}")

    @classmethod
    def unavailable(cls, name: str, detail: str) -> SignalOutput:
        """The canonical 'could not be measured' output.

        Note the direction: ``TOWARD_UNCERTAIN``. An unmeasurable signal is
        absent evidence, not evidence of anything (non-negotiable #3).
        """
        return cls(
            features={},
            applicable=False,
            quality=0.0,
            explanation=f"{name} could not be measured on this submission: {detail}.",
            reason_codes=[
                Reason(
                    code=ReasonCode.SIGNAL_UNAVAILABLE,
                    direction=Direction.TOWARD_UNCERTAIN,
                    strength=0.0,
                    message=f"{name} was skipped: {detail}.",
                    limitation=(
                        f"A signal that cannot be measured is simply absent. Its silence "
                        f"is not evidence that the image is either genuine or manipulated."
                    ),
                )
            ],
        )

    def to_dict(self) -> dict[str, object]:
        """Serialise for the harness report and the API response."""
        return {
            "features": dict(self.features),
            "applicable": self.applicable,
            "quality": round(float(self.quality), 4),
            "explanation": self.explanation,
            "reason_codes": [r.to_dict() for r in self.reason_codes],
            "artifacts": sorted(self.artifacts),
        }


# ---------------------------------------------------------------------------
# Requirement evaluation
# ---------------------------------------------------------------------------

_Resolver = Callable[[Capture], float | None]


def _quality_number(key: str) -> _Resolver:
    """Resolve a requirement to a numeric field of ``Capture.quality``.

    Returns ``None`` when the field is absent or non-numeric, which fails the
    requirement: we cannot verify what we cannot read.
    """

    def resolver(cap: Capture) -> float | None:
        raw = cap.quality.get(key)
        # bool is an int subclass; a boolean quality flag is not a measurement.
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            return None
        return float(raw)

    return resolver


def _has_video(cap: Capture) -> float | None:
    frames = cap.video_frames
    return 1.0 if frames is not None and len(frames) > 0 else 0.0


def _has_iris(cap: Capture) -> float | None:
    return 1.0 if cap.has_iris else 0.0


def _has_landmarks(cap: Capture) -> float | None:
    return 1.0 if cap.has_landmarks else 0.0


def _fps(cap: Capture) -> float | None:
    return float(cap.fps) if cap.fps is not None else None


#: The closed vocabulary of requirement keys. Adding one is a deliberate act:
#: every key must be resolvable from ``Capture`` and must fail closed.
_RESOLVERS: Final[dict[str, _Resolver]] = {
    "min_face_px": _quality_number("face_px"),
    "min_eye_px": _quality_number("eye_width_px"),
    "min_interocular_px": _quality_number("interocular_px"),
    "min_blur_score": _quality_number("blur_score"),
    "min_exposure": _quality_number("exposure"),
    "max_exposure": _quality_number("exposure"),
    "max_clipped_fraction": _quality_number("clipped_fraction"),
    "max_occlusion": _quality_number("occlusion_estimate"),
    "needs_video": _has_video,
    "needs_iris": _has_iris,
    "needs_landmarks": _has_landmarks,
    "min_fps": _fps,
}

REQUIREMENT_KEYS: Final[frozenset[str]] = frozenset(_RESOLVERS)


def _is_met(key: str, actual: float, threshold: float) -> bool:
    """Compare an actual value against a threshold, by key prefix."""
    if key.startswith("min_"):
        return actual >= threshold
    if key.startswith("max_"):
        return actual <= threshold
    if key.startswith("needs_"):
        return actual >= 1.0
    # Unreachable: _RESOLVERS keys all carry a known prefix. Guarded anyway so
    # that a future key added without a prefix fails loudly instead of silently
    # passing every capture.
    raise SignalError(f"requirement {key!r} has no recognised min_/max_/needs_ prefix")


def require(cap: Capture, name: str = "signal", **requirements: float | bool) -> SignalOutput | None:
    """Evaluate applicability requirements against a capture.

    Returns ``None`` when every requirement is met, otherwise a
    :class:`SignalOutput` with ``applicable=False``.

    **Never raises for a capture condition.** A missing or unreadable quality
    value fails the requirement rather than propagating, because an unmeasurable
    signal must degrade to "absent", not to a 500.

    Raises:
        SignalError: A requirement key is not in :data:`REQUIREMENT_KEYS`.
            That is a programming error in a plugin declaration, not an image
            condition, and it is better to fail the build than to silently skip
            a gate the author believed was active.
    """
    unmet: list[str] = []

    for key, threshold in requirements.items():
        resolver = _RESOLVERS.get(key)
        if resolver is None:
            raise SignalError(
                f"{name!r} declares unknown requirement {key!r}; "
                f"known keys: {sorted(REQUIREMENT_KEYS)}"
            )
        wanted = float(threshold)
        actual = resolver(cap)
        if actual is None or not _is_met(key, actual, wanted):
            shown = "unavailable" if actual is None else f"{actual:.2f}"
            unmet.append(f"{key} (needed {wanted:.2f}, measured {shown})")

    if not unmet:
        return None
    return SignalOutput.unavailable(name, "; ".join(unmet))


# ---------------------------------------------------------------------------
# Reason builder
# ---------------------------------------------------------------------------


def reason(
    code: ReasonCode,
    message: str,
    limitation: str,
    *,
    direction: Direction = Direction.TOWARD_UNCERTAIN,
    strength: float = 0.0,
) -> Reason:
    """Build a :class:`Reason`, refusing one whose ``limitation`` is empty.

    Non-negotiable #2: a measurement that reads as proof without naming what
    else could cause it is worse than no measurement at all. The refusal lives
    in ``Reason.__post_init__``; this wrapper exists so plugin authors have one
    obvious constructor and a keyword-friendly signature.
    """
    return Reason(
        code=code,
        direction=direction,
        strength=strength,
        message=message,
        limitation=limitation,
    )


# ---------------------------------------------------------------------------
# The plugin ABC
# ---------------------------------------------------------------------------


class Signal(ABC):
    """One detection idea, measured honestly.

    Subclasses declare metadata as class attributes and implement :meth:`run`.
    They never implement the applicability gate themselves — :meth:`__call__`
    applies :meth:`preflight` first, so a plugin cannot accidentally run on an
    input it declared itself unable to handle.

    Rules enforced here (FAREBI.md §5):
        1. ``run`` returns features, never a verdict.
        2. A signal never imports another signal. (Test-enforced.)
        3. ``applicable`` and ``quality`` are always populated.
        4. Every reason code carries a limitation.
        5. Survival is decided by the harness, not by the author.
    """

    name: str = ""
    tier: int = MIN_TIER
    min_requirements: dict[str, float | bool] = {}
    requires: list[str] = []

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        # ABCMeta sets __abstractmethods__ only *after* __init_subclass__ runs,
        # so abstractness is detected from the class namespace instead: a class
        # that still carries an abstract (or absent) `run` is an intermediate
        # base and is validated when a concrete leaf finally implements it.
        run_attr = cls.__dict__.get("run")
        if run_attr is None or getattr(run_attr, "__isabstractmethod__", False):
            return
        if not cls.name:
            raise SignalError(f"{cls.__name__} must declare a non-empty `name`")
        if not MIN_TIER <= cls.tier <= MAX_TIER:
            raise SignalError(
                f"{cls.__name__} declares tier {cls.tier}; expected {MIN_TIER}-{MAX_TIER}"
            )
        unknown = sorted(set(cls.min_requirements) - REQUIREMENT_KEYS)
        if unknown:
            raise SignalError(
                f"{cls.__name__} declares unknown requirements {unknown}; "
                f"known keys: {sorted(REQUIREMENT_KEYS)}"
            )

    # -- applicability ------------------------------------------------------

    def preflight(self, cap: Capture) -> bool:
        """Cheap applicability check. Override only to add a *stricter* gate."""
        return require(cap, self.name, **self.min_requirements) is None

    # -- the one abstract method -------------------------------------------

    @abstractmethod
    def run(self, cap: Capture) -> SignalOutput:
        """Measure the capture and return features.

        Implementations must not raise for ordinary input: an unexpected
        condition is an ``applicable=False`` result, so one broken signal can
        never take down a submission.
        """

    # -- public entry point -------------------------------------------------

    def __call__(self, cap: Capture) -> SignalOutput:
        """Run the signal behind its applicability gate."""
        try:
            if not self.preflight(cap):
                return SignalOutput.unavailable(
                    self.name, "; ".join(sorted(self.min_requirements)) or "preflight declined"
                )
        except SignalError:
            raise  # a malformed declaration must not be swallowed
        except Exception as exc:  # noqa: BLE001 - one plugin must not 500 a request
            return SignalOutput.unavailable(self.name, f"preflight raised {type(exc).__name__}")
        try:
            return self.run(cap)
        except Exception as exc:  # noqa: BLE001 - see above
            return SignalOutput.unavailable(self.name, f"run raised {type(exc).__name__}")

    def __repr__(self) -> str:
        return f"{type(self).__name__}(name={self.name!r}, tier={self.tier})"
