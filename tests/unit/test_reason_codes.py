"""Reason-code contract tests.

These enforce the honesty rules that are easy to erode under deadline pressure:
a reason without a stated limitation reads as proof, and metadata must never
point in any direction at all.
"""

from __future__ import annotations

import pytest

from farebi.core.reason_codes import METADATA_CODES, Direction, Reason, ReasonCode


def _make(**overrides: object) -> Reason:
    defaults: dict[str, object] = {
        "code": ReasonCode.VISUAL_MODEL_FAKE_SIGNAL,
        "direction": Direction.TOWARD_FAKE,
        "strength": 0.5,
        "message": "The visual classifier found patterns associated with manipulated images.",
        "limitation": "Heavy JPEG compression can produce similar patterns.",
    }
    defaults.update(overrides)
    return Reason(**defaults)  # type: ignore[arg-type]


class TestReasonContract:
    def test_valid_reason_is_constructed(self) -> None:
        reason = _make()
        assert reason.code is ReasonCode.VISUAL_MODEL_FAKE_SIGNAL
        assert reason.direction is Direction.TOWARD_FAKE

    def test_limitation_is_mandatory(self) -> None:
        """An unsupported claim is worse than no claim (non-negotiable)."""
        for empty in ("", "   ", "\n"):
            with pytest.raises(ValueError, match="limitation is mandatory"):
                _make(limitation=empty)

    def test_message_is_mandatory(self) -> None:
        with pytest.raises(ValueError, match="message must be a non-empty"):
            _make(message="  ")

    @pytest.mark.parametrize("strength", [-0.01, 1.01, 2.0])
    def test_strength_is_bounded(self, strength: float) -> None:
        with pytest.raises(ValueError, match=r"strength must be within"):
            _make(strength=strength)

    @pytest.mark.parametrize("strength", [0.0, 0.5, 1.0])
    def test_boundary_strengths_are_accepted(self, strength: float) -> None:
        assert _make(strength=strength).strength == strength

    def test_code_must_come_from_the_enum(self) -> None:
        with pytest.raises(TypeError, match="code must be a ReasonCode"):
            _make(code="VISUAL_MODEL_FAKE_SIGNAL")

    def test_direction_must_come_from_the_enum(self) -> None:
        with pytest.raises(TypeError, match="direction must be a Direction"):
            _make(direction="toward_fake")

    def test_metadata_codes_must_be_neutral(self) -> None:
        """Non-negotiable #4: metadata is context, never proof."""
        for code in METADATA_CODES:
            for direction in (
                Direction.TOWARD_FAKE,
                Direction.TOWARD_REAL,
                Direction.TOWARD_UNCERTAIN,
            ):
                with pytest.raises(ValueError, match="must be"):
                    _make(code=code, direction=direction)

            neutral = _make(code=code, direction=Direction.NEUTRAL)
            assert neutral.direction is Direction.NEUTRAL

    def test_non_metadata_codes_may_point_somewhere(self) -> None:
        for direction in Direction:
            if direction is Direction.NEUTRAL:
                continue
            assert _make(direction=direction).direction is direction

    def test_to_dict_shape_matches_the_api_contract(self) -> None:
        payload = _make(strength=0.64123).to_dict()
        assert set(payload) == {"code", "direction", "strength", "message", "limitation"}
        assert payload["code"] == "VISUAL_MODEL_FAKE_SIGNAL"
        assert payload["direction"] == "toward_fake"
        assert payload["strength"] == 0.6412

    def test_reasons_are_immutable(self) -> None:
        from dataclasses import FrozenInstanceError

        reason = _make()
        with pytest.raises(FrozenInstanceError):
            reason.strength = 0.9  # type: ignore[misc]


class TestBannedPhrases:
    """The copy rules from IDEA.md §4, enforced mechanically.

    A reason that asserts proof, or that treats missing EXIF as evidence, is a
    defect even if the underlying measurement is sound.
    """

    BANNED = (
        "proves",
        "proof that",
        "definitely",
        "guaranteed",
        "100% fake",
        "the eyes prove",
        "missing exif means",
        "must be ai",
    )

    def test_shipped_reason_messages_avoid_absolute_claims(self) -> None:
        """Every reason the shipped pipeline emits stays inside the vocabulary."""
        from farebi.capture.capture import _extend_quality_reasons
        from farebi.core.config import get_settings
        from fixtures.synthetic import synthetic_face_rgb

        rgb = synthetic_face_rgb(size=256)
        # Force every gate to fail by using impossibly strict gates.
        gates = get_settings().capture.quality.model_copy(
            update={
                "min_blur_score": 1e9,
                "min_face_px": 1_000_000,
                "min_exposure": 0.5,
                "max_exposure": 0.51,
                "max_clipped_fraction": -1.0,
            }
        )
        from farebi.capture.quality import assess_quality

        assessment = assess_quality(rgb, None, gates=gates)
        reasons: list[Reason] = []
        _extend_quality_reasons(reasons, assessment, gates)

        assert reasons, "expected the strict gates to produce reasons"
        for reason in reasons:
            lowered = reason.message.lower()
            for banned in self.BANNED:
                assert banned not in lowered, f"{reason.code}: banned phrase {banned!r}"
            assert reason.limitation.strip()
