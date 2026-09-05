"""Signal discovery, status, and the fusion gate.

This is the only place that knows which signals exist. It answers three
questions and enforces one rule:

* *What is installed?* — :meth:`SignalRegistry.discover` imports every plugin
  module in ``farebi.signals`` and collects the concrete :class:`Signal`
  subclasses defined there.
* *What is the harness's verdict?* — :meth:`SignalRegistry.status_of` reads
  ``configs/signals.yaml``, which ``scripts/run_harness.py`` rewrites on every
  run.
* *What may reach fusion?* — :meth:`SignalRegistry.all_enabled`. A signal whose
  status is not ``keep`` or ``bench`` is **excluded**. This is the code-side
  half of ``FAREBI.md`` §7 and it is the reason a signal cannot sneak into
  production just by being written.

Naming note: ``PLANS/02`` calls the config field ``harness_status``; the
``configs/signals.yaml`` shipped in Phase 01 calls it ``status``. The file wins,
so the field is ``status`` and the enum is :class:`HarnessStatus`. One value,
one owner.

Layering note: this module is *infrastructure*, not a plugin. It imports the
contract (``signals.base``) and dynamically imports the plugins; it is exempted
from the "signals are leaves" rule in ``tests/unit/test_layering.py``, which
continues to forbid any plugin from importing another plugin.

Layer: L2 (may import L0, L1).
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from typing import TYPE_CHECKING, Final

from farebi.core.config import SignalsConfig, get_settings
from farebi.core.constants import FUSION_ELIGIBLE_STATUSES, HarnessStatus
from farebi.core.logging import get_logger
from farebi.signals.base import Signal, SignalOutput

if TYPE_CHECKING:  # pragma: no cover - typing only
    from farebi.signals.base import Capture

__all__ = [
    "INFRASTRUCTURE_MODULES",
    "RegistryError",
    "SIGNALS_PACKAGE",
    "SignalRegistry",
    "all_enabled",
    "default_registry",
    "get",
    "preflight_all",
    "reset_registry",
    "tier",
]

SIGNALS_PACKAGE: Final = "farebi.signals"

#: Contract and loader. These are not plugins and are never auto-discovered.
INFRASTRUCTURE_MODULES: Final[frozenset[str]] = frozenset({"base", "registry"})

_log = get_logger(__name__)


class RegistryError(RuntimeError):
    """Raised for a duplicate signal name, an unknown lookup, or a bad plugin."""


class SignalRegistry:
    """The collection of installed signals, filtered by harness status.

    Args:
        config: The ``signals`` config section. Read from the process settings
            when omitted; pass one explicitly in tests.
    """

    def __init__(self, config: SignalsConfig | None = None) -> None:
        self._config: SignalsConfig = config if config is not None else get_settings().signals
        self._signals: dict[str, Signal] = {}
        self._discovered: bool = False

    # -- configuration ------------------------------------------------------

    @property
    def config(self) -> SignalsConfig:
        return self._config

    def status_of(self, name: str) -> HarnessStatus:
        """The harness verdict for ``name``, falling back to ``default_status``.

        Unknown signals get the default, which is ``unmeasured`` and therefore
        not fusion-eligible. Shipping a new signal cannot change a live verdict
        until the harness has measured it.
        """
        entry = self._config.entries.get(name)
        return entry.status if entry is not None else self._config.default_status

    def is_fusion_eligible(self, name: str) -> bool:
        return self.status_of(name) in FUSION_ELIGIBLE_STATUSES

    # -- population ---------------------------------------------------------

    def register(self, signal: type[Signal] | Signal) -> Signal:
        """Register a plugin class or instance and return the instance.

        Raises:
            RegistryError: The plugin is abstract, unnamed, or already registered
                under its name by a different class.
        """
        instance = signal() if isinstance(signal, type) else signal

        if inspect.isabstract(type(instance)):
            raise RegistryError(f"{type(instance).__name__} is abstract and cannot be registered")
        name = instance.name
        if not name:
            raise RegistryError(f"{type(instance).__name__} has an empty name")

        existing = self._signals.get(name)
        if existing is not None and type(existing) is not type(instance):
            raise RegistryError(
                f"signal name {name!r} is claimed by both "
                f"{type(existing).__name__} and {type(instance).__name__}"
            )
        if existing is not None:
            return existing  # idempotent re-registration of the same class

        _log.debug("signal_registered", name=name, tier=instance.tier)
        self._signals[name] = instance
        return instance

    def discover(self, package: str = SIGNALS_PACKAGE) -> list[str]:
        """Import every plugin module in ``package`` and register its signals.

        Dynamic import is the point: a plugin is dropped in as a file and picks
        itself up. Discovery is idempotent and never raises for a broken plugin
        module — one bad signal must not stop the registry from building, and
        the import error is logged so it is visible.

        Returns:
            The names registered by this call.
        """
        registered: list[str] = []
        try:
            pkg = importlib.import_module(package)
        except ImportError as exc:  # pragma: no cover - package always exists
            raise RegistryError(f"cannot import signals package {package!r}: {exc}") from exc

        package_path = getattr(pkg, "__path__", None)
        if package_path is None:  # pragma: no cover - defensive
            raise RegistryError(f"{package!r} is not a package")

        for info in sorted(pkgutil.iter_modules(package_path), key=lambda m: m.name):
            if info.ispkg or info.name in INFRASTRUCTURE_MODULES:
                continue
            module_name = f"{package}.{info.name}"
            try:
                module = importlib.import_module(module_name)
            except Exception as exc:  # noqa: BLE001 - see docstring
                _log.warning("signal_module_import_failed", module=module_name, error=str(exc))
                continue

            for _, obj in inspect.getmembers(module, inspect.isclass):
                if not issubclass(obj, Signal) or inspect.isabstract(obj):
                    continue
                # Only classes *defined* here: a module may import a Signal for
                # its own use, and re-registering it would be a surprise.
                if obj.__module__ != module_name:
                    continue
                self.register(obj)
                registered.append(obj.name)

        self._discovered = True
        return sorted(registered)

    # -- queries ------------------------------------------------------------

    @property
    def discovered(self) -> bool:
        return self._discovered

    def names(self) -> list[str]:
        return sorted(self._signals)

    def get(self, name: str) -> Signal:
        """Return a registered signal by name.

        Raises:
            RegistryError: No signal with that name is registered.
        """
        try:
            return self._signals[name]
        except KeyError:
            raise RegistryError(
                f"no signal named {name!r} is registered; known: {self.names()}"
            ) from None

    def tier(self, number: int) -> list[Signal]:
        """Every signal at ``number``, ordered by name."""
        return [self._signals[n] for n in self.names() if self._signals[n].tier == number]

    def all_enabled(self) -> list[Signal]:
        """Signals the harness has cleared for fusion: status ``keep`` or ``bench``.

        A ``kill`` or ``unmeasured`` signal is absent from this list, and
        :meth:`run_all` refuses to run it by default. That is the enforcement
        half of "every signal must survive the harness or be deleted"
        (``FAREBI.md`` §5 rule 5).
        """
        return [self._signals[n] for n in self.names() if self.is_fusion_eligible(n)]

    def fusion_eligible(self) -> list[Signal]:
        """Alias for :meth:`all_enabled`, named for the caller in Phase 07."""
        return self.all_enabled()

    def killed(self) -> list[Signal]:
        """Signals the harness has rejected. Reports, never runs."""
        return [self._signals[n] for n in self.names() if self.status_of(n) is HarnessStatus.KILL]

    def missing_requirements(self) -> dict[str, tuple[str, ...]]:
        """Signals whose declared companion signals are not registered.

        A companion (``requires``) is a signal this one is meaningless without —
        PRNU without replay detection, for example. Reporting the gap beats
        silently running a signal that cannot be interpreted.
        """
        missing: dict[str, tuple[str, ...]] = {}
        for name in self.names():
            absent = tuple(r for r in self._signals[name].requires if r not in self._signals)
            if absent:
                missing[name] = absent
        return missing

    # -- execution ----------------------------------------------------------

    def preflight_all(self, cap: Capture) -> dict[str, bool]:
        """Applicability of every enabled signal on this capture.

        Keys are signal names; a signal that is not enabled is omitted entirely
        rather than reported as ``False``, so "not wired in" and "cannot run
        here" stay distinguishable.
        """
        return {s.name: s.preflight(cap) for s in self.all_enabled()}

    def run_all(self, cap: Capture, *, only_enabled: bool = True) -> dict[str, SignalOutput]:
        """Run every signal and return ``{name: SignalOutput}``.

        Signals are leaves and order-independent, so this is safe to parallelise
        later. A raising signal is an ``applicable=False`` output, never an
        exception (guaranteed by ``Signal.__call__``).
        """
        pool = self.all_enabled() if only_enabled else [self._signals[n] for n in self.names()]
        return {s.name: s(cap) for s in pool}


# ---------------------------------------------------------------------------
# Process-wide default registry
# ---------------------------------------------------------------------------

_default: SignalRegistry | None = None


def default_registry() -> SignalRegistry:
    """The shared registry, discovered on first use."""
    global _default
    if _default is None:
        registry = SignalRegistry()
        registry.discover()
        _default = registry
    return _default


def reset_registry(config: SignalsConfig | None = None) -> SignalRegistry:
    """Discard the shared registry and return a fresh, empty one.

    Tests call this to inject stub signals and synthetic status config without
    touching ``configs/signals.yaml``.
    """
    global _default
    _default = SignalRegistry(config)
    return _default


# -- convenience façade over the default registry (PLANS/02 API) ------------


def get(name: str) -> Signal:
    return default_registry().get(name)


def tier(number: int) -> list[Signal]:
    return default_registry().tier(number)


def all_enabled() -> list[Signal]:
    return default_registry().all_enabled()


def preflight_all(cap: Capture) -> dict[str, bool]:
    return default_registry().preflight_all(cap)
