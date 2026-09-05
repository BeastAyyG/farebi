"""The fusion gate: a kill/unmeasured signal must never reach fusion.

This is the code-side half of ``FAREBI.md`` §7 / §5 rule 5. ``SignalRegistry``
is the only thing that decides what the fusion model is allowed to see, and it
reads that decision from ``configs/signals.yaml`` (written by the harness). A
signal whose status is not ``keep`` or ``bench`` is excluded — including one that
was just written and has never been measured at all.
"""

from __future__ import annotations

from farebi.core.config import SignalEntryConfig, SignalsConfig
from farebi.core.constants import FUSION_ELIGIBLE_STATUSES, HarnessStatus
from farebi.signals.base import Signal, SignalOutput
from farebi.signals.registry import reset_registry


class _DummyKeep(Signal):
    name = "dummy_keep"
    tier = 1

    def run(self, cap) -> SignalOutput:  # pragma: no cover - exercised only via registry
        return SignalOutput(
            features={"x": 0.0}, applicable=False, quality=0.0,
            explanation="dummy", reason_codes=[],
        )


class _DummyKill(Signal):
    name = "dummy_kill"
    tier = 1

    def run(self, cap) -> SignalOutput:  # pragma: no cover
        return SignalOutput(
            features={"x": 0.0}, applicable=False, quality=0.0,
            explanation="dummy", reason_codes=[],
        )


def test_fusion_eligible_statuses_are_keep_and_bench() -> None:
    assert {HarnessStatus.KEEP, HarnessStatus.BENCH} == FUSION_ELIGIBLE_STATUSES


def test_kill_and_unmeasured_are_excluded_from_fusion() -> None:
    config = SignalsConfig(
        default_status=HarnessStatus.UNMEASURED,
        entries={
            "dummy_keep": SignalEntryConfig(status=HarnessStatus.KEEP),
            "dummy_kill": SignalEntryConfig(status=HarnessStatus.KILL),
            "dummy_absent": SignalEntryConfig(status=HarnessStatus.UNMEASURED),
        },
    )
    registry = reset_registry(config)
    registry.register(_DummyKeep())
    registry.register(_DummyKill())

    # An unmeasured signal that is installed but has no explicit row falls back to
    # the default status, which is also not fusion-eligible.
    class _DummyUnmeasured(Signal):
        name = "dummy_unmeasured"
        tier = 1

        def run(self, cap) -> SignalOutput:  # pragma: no cover
            return SignalOutput(
                features={}, applicable=False, quality=0.0,
                explanation="x", reason_codes=[],
            )

    registry.register(_DummyUnmeasured())

    enabled = {s.name for s in registry.all_enabled()}
    assert "dummy_keep" in enabled
    assert "dummy_kill" not in enabled
    assert "dummy_unmeasured" not in enabled

    assert registry.is_fusion_eligible("dummy_keep") is True
    assert registry.is_fusion_eligible("dummy_kill") is False
    assert registry.is_fusion_eligible("dummy_unmeasured") is False
    # A signal the harness never measured must not be fusion-eligible by default.
    assert registry.is_fusion_eligible("does_not_exist") is False
    assert [s.name for s in registry.killed()] == ["dummy_kill"]
