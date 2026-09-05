"""Farebi — a KYC deepfake / manipulated-face *risk signal* service.

This package is deliberately layered (see ``FAREBI.md`` §6). Every module
declares which layers it may import, and CI enforces it mechanically:

    L0  core, utils          may import stdlib + third-party only
    L1  capture, degradation, data
    L2  signals/*            plugins are leaves; may not import each other
    L3  models, fusion
    L4  inference, explain
    L5  api, monitoring
    OFFLINE  harness, evaluation   never imported by serving code

The product emits four verdicts — ``likely_real``, ``likely_fake``,
``uncertain``, ``unable_to_assess`` — and is a risk signal for a human
reviewer, never an autonomous rejection engine.
"""

from __future__ import annotations

__version__ = "0.1.0"
__all__ = ["__version__"]
