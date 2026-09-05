"""CLIP-ViT semantic forgery signal — Tier 1 (model lands in Phase 06).

Placeholder with the final plugin shape: the name, tier and applicability
gate a future ``models/`` checkpoint will serve. ``torch`` and the weights
are absent from the current install, so :meth:`run` degrades to
``applicable=False`` with an explicit reason instead of failing the import —
a missing model must read as absent evidence, never as a 500
(non-negotiable #3).

Adaptation notes for the Phase 06 drop (from
``vendor/UniversalFakeDetect``):

* Load the checkpoint from ``artifacts/models/`` (see
  ``FaceMeshConfig.model_path`` for the path convention), never from
  ``vendor/`` — vendor code is gitignored reference, not a runtime source.
* Keep inference under ``torch.no_grad()`` on CPU by default; the feature
  must stay a small ``dict[str, float]`` (e.g. a fake-logit and its margin),
  never an embedding dump.
* Keep this module ``torch``-optional at import time so base installs stay
  green; import ``torch`` inside :meth:`run`.

Layer: L2 (may import L0, L1).
"""

from __future__ import annotations

from pathlib import Path

from farebi.capture.capture import Capture
from farebi.signals.base import Signal, SignalOutput

__all__ = ["VitClipSignal"]

#: Where the Phase 06 training drop must place the checkpoint.
_WEIGHTS_PATH = Path("artifacts/models/clip-vit-fake.pt")


class VitClipSignal(Signal):
    """Semantic forgery score from a CLIP-ViT backbone (not yet shipped)."""

    name = "vit_clip"
    tier = 1
    min_requirements: dict[str, float | bool] = {"min_face_px": 96.0}

    def run(self, cap: Capture) -> SignalOutput:
        try:
            import torch
        except ImportError:
            return SignalOutput.unavailable(
                self.name,
                "torch is not installed; the CLIP-ViT model lands in Phase 06",
            )
        if not _WEIGHTS_PATH.exists():
            return SignalOutput.unavailable(
                self.name,
                f"torch {torch.__version__} is present but {_WEIGHTS_PATH.as_posix()} "
                "is missing (Phase 06 model drop)",
            )
        return SignalOutput.unavailable(
            self.name,
            "weights are present but inference wiring lands with the Phase 06 drop",
        )
