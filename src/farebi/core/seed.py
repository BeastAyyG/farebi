"""Reproducibility helpers.

PyTorch does not guarantee bit-exact reproducibility across releases,
platforms or hardware, so seeding is necessary but not sufficient. Every
training run additionally records package versions, the config hash and the
device into ``artifacts/model_registry.json`` (see ``utils/artifacts.py``).

Layer: L0 (may not import anything internal).
"""

from __future__ import annotations

import os
import random

__all__ = ["get_seed", "set_seed"]

_SEED_ENV = "PYTHONHASHSEED"


def set_seed(seed: int, *, deterministic: bool = True) -> None:
    """Seed every RNG the project can reach.

    torch and numpy are optional imports: the foundation phase must run in an
    environment where neither is installed.

    Args:
        seed: Integer seed.
        deterministic: Also force single-threaded, deterministic cuDNN kernels.
            Costs performance; use it for runs whose numbers will be published.
    """
    if not isinstance(seed, int):
        raise TypeError(f"seed must be an int, got {type(seed).__name__}")

    os.environ[_SEED_ENV] = str(seed)
    random.seed(seed)

    try:
        import numpy as np

        np.random.seed(seed % (2**32))
    except ImportError:  # pragma: no cover - exercised only without numpy
        pass

    try:
        import torch

        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
            if deterministic:
                torch.backends.cudnn.deterministic = True
                torch.backends.cudnn.benchmark = False
    except ImportError:  # pragma: no cover - exercised only without torch
        pass


def get_seed() -> int | None:
    """Read the active seed, or ``None`` if none has been set this process."""
    raw = os.environ.get(_SEED_ENV)
    return int(raw) if raw is not None and raw.isdigit() else None
