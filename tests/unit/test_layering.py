"""AST-based layering enforcement.

``import-linter`` enforces the layer *ordering* declaratively. This module adds
the two rules that are awkward to express there:

* **Signals are leaves.** No module under ``signals/`` may import another
  module under ``signals/``. If two signals need the same ROI extraction, that
  code moves to ``capture/`` — it does not become a shared import.
* **No layer skipping.** A module may import from its own layer and any layer
  below it, but not from a named layer it has no business touching, and serving
  code may never reach the offline packages.

The check runs against the source tree, so it works even while ``signals/`` is
still empty — which is exactly when you want the rule in place.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "src" / "farebi"

#: Layer index. Lower may be imported by higher; never the reverse.
LAYERS: dict[str, int] = {
    "core": 0,
    "utils": 0,
    "capture": 1,
    "degradation": 1,
    "data": 1,
    "signals": 2,
    "models": 3,
    "fusion": 3,
    "inference": 4,
    "explain": 4,
    "api": 5,
    "monitoring": 5,
}

#: Offline-only packages. Serving code may never import them.
OFFLINE_PACKAGES = frozenset({"harness", "evaluation"})
SERVING_PACKAGES = frozenset({"api", "monitoring"})

#: Modules under ``signals/`` that are infrastructure rather than plugins, and
#: so are exempt from the "plugins are leaves" rule. Kept here as well as in
#: ``farebi.signals.registry.INFRASTRUCTURE_MODULES`` so that a drift between
#: the two is caught by a test rather than by a silent exemption.
SIGNAL_INFRASTRUCTURE_MODULES = frozenset({"base", "registry"})

#: The one ``farebi.signals.*`` import a plugin is allowed: the contract it
#: conforms to (the plugin ABC, the output type, the helpers). Importing the
#: loader (``registry``) or any sibling plugin stays forbidden.
SIGNAL_CONTRACT_MODULES = frozenset({"farebi.signals.base"})


def _iter_python_modules() -> list[tuple[str, Path]]:
    """Every importable module in the package, as ``(layer_name, path)``.

    Files directly in ``src/farebi/`` (the package ``__init__``) belong to no
    layer and are skipped.
    """
    modules: list[tuple[str, Path]] = []
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        relative = path.relative_to(PACKAGE_ROOT)
        if len(relative.parts) < 2:
            continue
        modules.append((relative.parts[0], path))
    return modules


def _imported_subpackages(tree: ast.AST) -> set[str]:
    """First path segment of every ``farebi.*`` import in a module."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("farebi."):
                    found.add(alias.name.split(".")[1])
        elif isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("farebi."):
            found.add(node.module.split(".")[1])
    return found


def _imported_modules(tree: ast.AST) -> set[str]:
    """Full dotted path of every ``farebi.*`` import in a module."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "farebi" or alias.name.startswith("farebi."):
                    found.add(alias.name)
        elif (
            isinstance(node, ast.ImportFrom)
            and node.module
            and (node.module == "farebi" or node.module.startswith("farebi."))
        ):
            found.add(node.module)
    return found


def _module_name(path: Path) -> str:
    return str(path.relative_to(PACKAGE_ROOT).with_suffix("")).replace("\\", "/").replace("/", ".")


def test_every_package_is_in_a_declared_layer() -> None:
    """A new top-level package must be assigned a layer, not silently ignored."""
    for layer, path in _iter_python_modules():
        if layer == path.stem:  # the package's own __init__.py
            continue
        assert layer in LAYERS or layer in OFFLINE_PACKAGES, (
            f"{_module_name(path)} sits in package {layer!r}, which has no declared layer. "
            f"Add it to LAYERS in {Path(__file__).name} and to FAREBI.md §6."
        )


def test_no_layer_skipping() -> None:
    """A module may only import from its own layer or a strictly lower one."""
    violations: list[str] = []

    for layer, path in _iter_python_modules():
        if layer not in LAYERS:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for imported in _imported_subpackages(tree):
            if imported not in LAYERS:
                continue
            if LAYERS[imported] > LAYERS[layer]:
                violations.append(
                    f"{_module_name(path)} (L{LAYERS[layer]}) imports "
                    f"farebi.{imported} (L{LAYERS[imported]})"
                )

    assert not violations, "layer violations:\n  " + "\n  ".join(violations)


def test_serving_code_never_imports_offline_packages() -> None:
    """``harness`` and ``evaluation`` must never reach a request path."""
    violations: list[str] = []

    for layer, path in _iter_python_modules():
        if layer not in SERVING_PACKAGES:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for imported in _imported_subpackages(tree):
            if imported in OFFLINE_PACKAGES:
                violations.append(f"{_module_name(path)} imports farebi.{imported}")

    assert not violations, "offline code reached serving code:\n  " + "\n  ".join(violations)


def test_signals_are_leaves() -> None:
    """No signal plugin may import another signal plugin.

    Shared code goes to ``capture/``, not into a third signal. Two modules are
    exempt because they are *infrastructure*, not plugins — they define and load
    the contract rather than implement a detection idea:

    * ``signals.base`` — the contract every plugin conforms to.
    * ``signals.registry`` — the loader that discovers plugins. It imports the
      contract and dynamically imports plugins by name.

    A plugin necessarily imports the contract (``farebi.signals.base``) to
    subclass ``Signal``; that single import is allowed. Anything else under
    ``farebi.signals.*`` — a sibling plugin or the loader — fails the build.
    """
    signals_dir = PACKAGE_ROOT / "signals"
    if not signals_dir.exists():
        pytest.skip("signals/ not created yet")

    violations: list[str] = []
    for path in sorted(signals_dir.rglob("*.py")):
        if path.stem in SIGNAL_INFRASTRUCTURE_MODULES:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for module in _imported_modules(tree):
            if module in SIGNAL_CONTRACT_MODULES:
                continue
            if module == "farebi.signals" or module.startswith("farebi.signals."):
                violations.append(f"{_module_name(path)} imports {module}")

    assert not violations, "signal plugins must be leaves:\n  " + "\n  ".join(violations)


def test_signal_infrastructure_exemption_stays_narrow() -> None:
    """The exemption above must not grow by accident.

    If this fails, either a new infrastructure module was added deliberately
    (add it here and to the docstring above, with a reason) or a plugin was
    wrongly named after the infrastructure.
    """
    signals_dir = PACKAGE_ROOT / "signals"
    actual = {p.stem for p in signals_dir.glob("*.py")} & SIGNAL_INFRASTRUCTURE_MODULES
    assert actual == SIGNAL_INFRASTRUCTURE_MODULES, (
        f"signals/ infrastructure modules changed; actual: {sorted(actual)}. "
        f"Expected: {sorted(SIGNAL_INFRASTRUCTURE_MODULES)}."
    )


def test_l0_is_acyclic() -> None:
    """L0 contains two packages, and the dependency must run one way.

    ``utils`` may use ``core``; ``core`` may never reach into ``utils``. Without
    this rule the two L0 packages form an import cycle the moment someone adds a
    lazy import for convenience.
    """
    violations: list[str] = []

    for layer, path in _iter_python_modules():
        if LAYERS.get(layer) != 0:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for imported in _imported_subpackages(tree):
            if LAYERS.get(imported) != 0:
                continue  # covered by test_no_layer_skipping
            if imported == layer:
                continue  # intra-package imports are always allowed
            if layer == "core" and imported == "utils":
                violations.append(f"{_module_name(path)} (core) imports farebi.utils")

    assert not violations, "L0 must stay acyclic:\n  " + "\n  ".join(violations)


@pytest.mark.parametrize("layer_name", sorted(LAYERS))
def test_layer_directory_exists(layer_name: str) -> None:
    assert (PACKAGE_ROOT / layer_name).is_dir(), f"missing package: src/farebi/{layer_name}"
