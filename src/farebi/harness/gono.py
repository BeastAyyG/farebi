"""The go/no-go gate.

The harness decides which signals live — not the author, and not the elegance of
the idea (``FAREBI.md`` §7). The rule is fixed, mechanical, and identical for
every signal:

    KEEP   cross_source_auc >= 0.65 AND coverage >= 0.50
    BENCH  cross_source_auc >= 0.60               (conditional, quality-gated)
    KILL   otherwise                              (deleted from the tree)

The thresholds are module constants rather than YAML entries on purpose. They
express *product policy* — how much evidence we require before a signal is
allowed to influence a KYC decision. Putting them in configuration would let a
discouraging harness run be "fixed" by lowering the bar, which is precisely the
failure mode this gate exists to prevent. Ranges that describe the *world*
(degradation strengths, quality gates) are config; the bar is not.

Layer: OFFLINE (may import L0-L4; never imported by serving code).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from farebi.core.constants import HarnessStatus
from farebi.harness.evaluate_signal import SignalEvaluation

__all__ = [
    "BENCH_AUC",
    "KEEP_AUC",
    "KEEP_COVERAGE",
    "Verdict",
    "decide",
    "verdict_table_rows",
]


#: Policy thresholds. See the module docstring for why these are not config.
KEEP_AUC: float = 0.65
KEEP_COVERAGE: float = 0.50
BENCH_AUC: float = 0.60


@dataclass(frozen=True, slots=True)
class Verdict:
    """The gate's decision for one signal, with the reason it was reached."""

    signal: str
    status: HarnessStatus
    auc: float | None
    coverage: float
    best_feature: str | None
    reason: str
    evaluated_at: str

    @property
    def keep(self) -> bool:
        return self.status is HarnessStatus.KEEP

    def to_dict(self) -> dict[str, object]:
        return {
            "signal": self.signal,
            "status": self.status.value,
            "cross_source_auc": None if self.auc is None else round(self.auc, 6),
            "coverage": round(self.coverage, 6),
            "best_feature": self.best_feature,
            "reason": self.reason,
            "evaluated_at": self.evaluated_at,
        }


def decide(
    evaluation: SignalEvaluation,
    *,
    keep_auc: float = KEEP_AUC,
    keep_coverage: float = KEEP_COVERAGE,
    bench_auc: float = BENCH_AUC,
    evaluated_at: str | None = None,
) -> Verdict:
    """Apply the rule to one evaluation.

    The thresholds are parameters so the tests can prove the *boundaries* of the
    gate (0.649 vs 0.650) without duplicating the logic under test. Callers use
    the defaults.
    """
    auc = evaluation.cross_source_auc
    coverage = evaluation.coverage
    stamp = evaluated_at or datetime.now(UTC).isoformat(timespec="seconds")

    # An unmeasurable signal is never a KEEP: "no evidence" is not "good signal".
    if auc is None:
        status, reason = (
            HarnessStatus.KILL,
            "no fold produced a defined AUC, so the signal carries no measurable evidence",
        )
    elif auc >= keep_auc and coverage >= keep_coverage:
        status, reason = (
            HarnessStatus.KEEP,
            f"AUC {auc:.3f} >= {keep_auc:.2f} and coverage {coverage:.0%} >= {keep_coverage:.0%}",
        )
    elif auc >= bench_auc:
        status, reason = (
            HarnessStatus.BENCH,
            f"AUC {auc:.3f} >= {bench_auc:.2f} but coverage {coverage:.0%} < "
            f"{keep_coverage:.0%}; usable only when applicable, quality-gated",
        )
    else:
        status, reason = (
            HarnessStatus.KILL,
            f"AUC {auc:.3f} < {bench_auc:.2f} after degradation",
        )

    return Verdict(
        signal=evaluation.signal,
        status=status,
        auc=auc,
        coverage=coverage,
        best_feature=evaluation.best_feature,
        reason=reason,
        evaluated_at=stamp,
    )


def verdict_table_rows(verdicts: list[Verdict]) -> list[dict[str, str]]:
    """Render verdicts as display rows.

    Sorting by status then name puts the kills at the top where they are hardest
    to ignore — a signal we have to delete is the most actionable thing in the
    report.
    """
    severity = {HarnessStatus.KILL: 0, HarnessStatus.BENCH: 1, HarnessStatus.KEEP: 2}
    ordered = sorted(verdicts, key=lambda v: (severity.get(v.status, 3), v.signal))
    return [
        {
            "signal": v.signal,
            "status": v.status.value,
            "auc": "n/a" if v.auc is None else f"{v.auc:.3f}",
            "coverage": f"{v.coverage:.0%}",
            "best_feature": v.best_feature or "-",
            "reason": v.reason,
        }
        for v in ordered
    ]
