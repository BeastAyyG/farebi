"""No anonymous decision numbers in signals (Phase-04 gate item).

Non-negotiable #3 extended to L2: every numeric literal that takes part in a
comparison inside ``src/farebi/signals/`` must either be a structural
zero/one guard (``== 0``, ``> 0``, ``<= 1.0`` and kin — emptiness checks and
unit-interval clamps can never lean toward fake or real) or live behind a
named module-level constant (``_BLOCK_FLAG`` and friends, each carrying a
calibration comment).

This keeps the ``> 0.4``-style magic number out of the signal code: a reader
auditing a threshold finds the constant, its comment, and the Dresden
measurement behind it instead of a bare literal. Centralising the values
themselves into ``configs/signals.yaml`` is a later step (the harness owns
that file); this test locks the naming discipline that makes it possible.
"""

from __future__ import annotations

import ast
import pathlib

SIGNALS_DIR = pathlib.Path(__file__).resolve().parents[2] / "src" / "farebi" / "signals"

#: Literals allowed as direct comparators: zero guards (empty / degenerate /
#: divide-by-zero checks) and unit-interval clamps. Neither can separate real
#: from fake, so neither is a decision threshold. ``0 == 0.0`` (and ``1 ==
#: 1.0``) under Python equality, so the float members cover the int forms.
_STRUCTURAL_LITERALS: frozenset[float] = frozenset({0.0, 1.0})


def _anonymous_comparators(tree: ast.AST) -> list[str]:
    """Describe every comparison against a non-structural numeric literal."""
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        for operand in (node.left, *node.comparators):
            if (
                isinstance(operand, ast.Constant)
                and isinstance(operand.value, (int, float))
                and not isinstance(operand.value, bool)
                and operand.value not in _STRUCTURAL_LITERALS
            ):
                found.append(f"L{node.lineno}: compare against {operand.value!r}")
    return found


def test_no_anonymous_numeric_comparators_in_signals() -> None:
    """Every signal comparison literal is structural or a named constant."""
    violations: list[str] = []
    for path in sorted(SIGNALS_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for item in _anonymous_comparators(tree):
            violations.append(f"{path.name} {item}")
    assert not violations, (
        "Anonymous numeric comparators in signals/ — move the literal to a "
        "named module constant with a calibration comment:\n" + "\n".join(violations)
    )


def test_lint_catches_a_planted_literal() -> None:
    """The scanner itself is tested: a bare ``x > 0.4`` must be flagged."""
    tree = ast.parse("def f(x):\n    return x > 0.4\n")
    assert _anonymous_comparators(tree) == ["L2: compare against 0.4"]


def test_lint_allows_zero_guards_and_clamps() -> None:
    """Zero/one guards and unit-interval clamps are structural, not decisions."""
    tree = ast.parse(
        "def f(a, b, q):\n"
        "    empty = a.size == 0\n"
        "    positive = b > 0\n"
        "    clamped = 0.0 <= q <= 1.0\n"
        "    return empty, positive, clamped\n"
    )
    assert _anonymous_comparators(tree) == []
