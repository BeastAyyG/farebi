"""Harness reports and the signal registry artifact.

Two outputs, both machine-written:

* ``artifacts/reports/harness/<signal>.md`` — one per signal per dataset
  version, including the per-feature AUC table that shows *which* feature is
  carrying the signal (``PLANS/02`` key decision #3).
* ``artifacts/signal_registry.json`` — the verdicts, with version and git SHA so
  a number can always be traced to the code that produced it.

It also rewrites ``configs/signals.yaml``, which is how a KILL actually takes
effect: the registry refuses to fuse a signal whose status is not ``keep`` or
``bench``. That file is machine-owned; the header says so.

Layer: OFFLINE (may import L0-L4; never imported by serving code).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from farebi.core.constants import HarnessStatus
from farebi.harness.evaluate_signal import SignalEvaluation
from farebi.harness.gono import Verdict, verdict_table_rows
from farebi.utils.artifacts import git_sha, save_json
from farebi.utils.hashing import sha256_config

__all__ = [
    "HarnessReport",
    "render_signals_yaml",
    "render_signal_markdown",
    "render_summary_markdown",
    "write_reports",
    "write_signal_registry",
]

REPORT_SUBDIR: str = "reports/harness"


@dataclass(frozen=True, slots=True)
class HarnessReport:
    """Everything one harness run produced."""

    dataset_version: str
    evaluations: list[SignalEvaluation] = field(default_factory=list)
    verdicts: list[Verdict] = field(default_factory=list)
    registry_version: str = "unknown"
    created_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds")
    )
    notes: list[str] = field(default_factory=list)

    def verdict_for(self, name: str) -> Verdict | None:
        return next((v for v in self.verdicts if v.signal == name), None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "registry_version": self.registry_version,
            "dataset_version": self.dataset_version,
            "created_at": self.created_at,
            "git_sha": git_sha(),
            "notes": list(self.notes),
            "verdicts": [v.to_dict() for v in self.verdicts],
            "evaluations": [e.to_dict() for e in self.evaluations],
        }


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------


def _table(headers: list[str], rows: list[list[str]]) -> str:
    """Render a GitHub-flavoured markdown table."""
    if not rows:
        return "_no rows_"
    head = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join("---" for _ in headers) + " |"
    body = "\n".join("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join([head, divider, body])


def render_signal_markdown(evaluation: SignalEvaluation, verdict: Verdict) -> str:
    """One signal's report, including the per-feature AUC table."""
    auc = "n/a" if evaluation.cross_source_auc is None else f"{evaluation.cross_source_auc:.3f}"
    lines: list[str] = [
        f"# {evaluation.signal} — {verdict.status.value.upper()}",
        "",
        f"- **Dataset version:** `{evaluation.dataset_version}`",
        f"- **Evaluated:** {verdict.evaluated_at}",
        f"- **Decision:** {verdict.status.value} — {verdict.reason}",
        f"- **Cross-source AUC:** {auc} (std {evaluation.auc_std:.3f} across "
        f"{evaluation.n_folds_used} fold(s))",
        f"- **Coverage:** {evaluation.coverage:.1%} "
        f"({evaluation.n_applicable}/{evaluation.n_samples} samples)",
        f"- **Degraded before measurement:** {evaluation.degraded}",
        f"- **Best feature:** `{evaluation.best_feature}`",
        "",
    ]

    if evaluation.skipped_folds:
        lines.append(
            f"> {evaluation.skipped_folds} fold(s) were skipped because the held-out "
            "group contained only one class. Those folds contributed no AUC."
        )
        lines.append("")

    if evaluation.per_feature_auc:
        rows = [
            [
                name,
                f"{value:.3f}",
                "+1 (higher = more likely fake)"
                if evaluation.per_feature_direction.get(name, 1) == 1
                else "-1 (higher = more likely real)",
            ]
            for name, value in sorted(
                evaluation.per_feature_auc.items(), key=lambda kv: kv[1], reverse=True
            )
        ]
        lines.extend(
            [
                "## Per-feature AUC",
                "",
                "Discriminative AUC, folded into `[0.5, 1]`. A row at 0.500 is noise; "
                "if only one row is doing the work, the other features are decoration.",
                "",
                _table(["feature", "AUC", "direction"], rows),
                "",
            ]
        )

    if evaluation.notes:
        lines.append("## Notes")
        lines.append("")
        lines.extend(f"- {note}" for note in evaluation.notes)
        lines.append("")

    return "\n".join(lines)


def render_summary_markdown(report: HarnessReport) -> str:
    """The index page: every verdict, kills first."""
    rows = [
        [r["signal"], r["status"].upper(), r["auc"], r["coverage"], r["reason"]]
        for r in verdict_table_rows(report.verdicts)
    ]
    lines = [
        "# Signal harness summary",
        "",
        f"- **Registry version:** `{report.registry_version}`",
        f"- **Dataset version:** `{report.dataset_version}`",
        f"- **Run at:** {report.created_at}",
        f"- **Git SHA:** `{git_sha()}`",
        "",
        "Kills are listed first: a signal to delete is the most actionable result "
        "in the run.",
        "",
        _table(["signal", "status", "AUC", "coverage", "reason"], rows),
        "",
    ]
    if report.notes:
        lines.append("## Run notes")
        lines.append("")
        lines.extend(f"- {note}" for note in report.notes)
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Registry outputs
# ---------------------------------------------------------------------------

_CONFIG_HEADER = """# Signal registry configuration.
#
# GENERATED by scripts/run_harness.py — do not edit by hand.
# The harness owns `status`; run it again to change a verdict.
#
#   status: keep       -> always fused
#   status: bench      -> fused only when applicable and quality-gated
#   status: kill       -> excluded from fusion entirely
#   status: unmeasured -> never fused (the starting state for every signal)

"""


def render_signals_yaml(
    verdicts: list[Verdict], *, registry_version: str, default_status: str = "unmeasured"
) -> str:
    """Render ``configs/signals.yaml`` from the verdicts.

    Only signals the harness has actually measured are written; the
    ``default_status`` covers everything else and stays fail-closed.
    """
    entries: dict[str, Any] = {}
    for verdict in sorted(verdicts, key=lambda v: v.signal):
        entry: dict[str, Any] = {
            "status": verdict.status.value,
            "cross_source_auc": None if verdict.auc is None else round(verdict.auc, 4),
            "coverage": round(verdict.coverage, 4),
            "best_feature": verdict.best_feature,
            "evaluated_on": verdict.evaluated_at[:10],
        }
        entries[verdict.signal] = entry

    document: dict[str, Any] = {
        "signals": {
            "registry_version": registry_version,
            "default_status": default_status,
            "entries": entries,
        }
    }
    return _CONFIG_HEADER + yaml.safe_dump(document, sort_keys=False, default_flow_style=False)


def write_signal_registry(
    report: HarnessReport,
    *,
    base_dir: str | Path = "artifacts",
    config_path: str | Path | None = "configs/signals.yaml",
) -> tuple[Path, Path | None]:
    """Write the registry artifact and, optionally, the live config.

    Returns:
        ``(artifact_path, config_path_or_None)``.

    The payload carries the dataset version and a config hash so that a verdict
    can never be separated from the data and settings that produced it.
    """
    payload = report.to_dict()
    payload["config_hash"] = sha256_config(
        {v.signal: v.to_dict() for v in report.verdicts}
    )
    artifact = save_json(
        "signal_registry.json",
        payload,
        base_dir=base_dir,
        dataset_version=report.dataset_version,
        registry_version=report.registry_version,
    )

    written_config: Path | None = None
    if config_path is not None:
        target = Path(config_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            render_signals_yaml(
                report.verdicts, registry_version=report.registry_version
            ),
            encoding="utf-8",
        )
        written_config = target
    return artifact, written_config


def write_reports(
    report: HarnessReport, *, base_dir: str | Path = "artifacts"
) -> list[Path]:
    """Write the summary and one markdown report per signal."""
    root = Path(base_dir) / REPORT_SUBDIR
    root.mkdir(parents=True, exist_ok=True)

    written: list[Path] = [root / "_summary.md"]
    written[0].write_text(render_summary_markdown(report), encoding="utf-8")

    by_name = {e.signal: e for e in report.evaluations}
    for verdict in report.verdicts:
        evaluation = by_name.get(verdict.signal)
        if evaluation is None:  # pragma: no cover - verdicts come from evaluations
            continue
        path = root / f"{verdict.signal}.md"
        path.write_text(render_signal_markdown(evaluation, verdict), encoding="utf-8")
        written.append(path)

    return written


def status_counts(verdicts: list[Verdict]) -> dict[str, int]:
    """How many signals landed in each status. Used by the CLI exit code."""
    counts = {status.value: 0 for status in HarnessStatus}
    for verdict in verdicts:
        counts[verdict.status.value] += 1
    return counts
