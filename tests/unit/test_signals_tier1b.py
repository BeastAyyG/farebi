"""Tier-1b survivor: chromatic aberration.

Corneal and geometry were harness-killed on quick256 (AUC 0.544 / 0.559,
plus a premise failure for corneal on 1024px real portraits) and deleted
from the tree per PLANS/04 — this file keeps the CA tests plus the
discovery fail-closed check and the noise-robustness check.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
import pytest

from farebi.capture.capture import Capture
from farebi.signals.base import Signal
from farebi.signals.ca import ChromaticAberrationSignal
from farebi.signals.registry import SignalRegistry

SIZE = 512


def _quality() -> dict[str, object]:
    return {
        "blur_score": 100.0,
        "exposure": 0.5,
        "clipped_fraction": 0.0,
        "face_width_px": 300,
        "face_height_px": 340,
        "face_px": 300,
        "interocular_px": 153.0,
        "eye_width_px": 60.0,
        "occlusion_estimate": 0.0,
        "usable": True,
        "failed_gates": [],
    }


def _capture(image: npt.NDArray[np.uint8], landmarks: npt.NDArray[np.float32]) -> Capture:
    return Capture(
        image_bgr=np.ascontiguousarray(image),
        face_box=(100, 80, 412, 460),
        landmarks=landmarks,
        quality=_quality(),
    )


def _assert_honest_output(sig: Signal, cap: Capture) -> None:
    out = sig(cap)
    assert 0.0 <= out.quality <= 1.0
    assert out.explanation.strip()
    for value in out.features.values():
        assert np.isfinite(value)
    for rc in out.reason_codes:
        assert rc.limitation.strip()


class TestDiscovery:
    def test_new_signals_discovered_and_fail_closed(self) -> None:
        registry = SignalRegistry()
        names = registry.discover()
        assert {"chromatic_aberration"} <= set(names)
        assert registry.is_fusion_eligible("chromatic_aberration") is False


class TestChromaticAberration:
    def test_checkerboard_frame_runs(self) -> None:
        # A smooth ramp has no Canny edges, so CA would (correctly) decline.
        # Use a checkerboard with a slight per-channel shift: guaranteed edges
        # plus genuine lateral colour fringing for the slope to measure.
        tile = np.indices((16, 16)).sum(axis=0) % 2
        board = (np.kron(tile, np.ones((16, 16))) * 255).astype(np.uint8)
        img = np.ascontiguousarray(
            np.stack(
                [
                    board,
                    np.roll(board, 2, axis=1),  # 2px lateral shift on green
                    np.roll(board, -2, axis=1),  # opposite shift on red
                ],
                axis=2,
            )
        )
        out = ChromaticAberrationSignal()(_capture(img, np.zeros((0, 3), dtype=np.float32)))
        assert out.applicable is True
        assert out.features["ca_edge_patches"] >= 100.0
        _assert_honest_output(
            ChromaticAberrationSignal(),
            _capture(img, np.zeros((0, 3), dtype=np.float32)),
        )

    def test_tiny_frame_is_unavailable(self) -> None:
        img = np.zeros((64, 64, 3), dtype=np.uint8)
        out = ChromaticAberrationSignal()(
            Capture(
                image_bgr=img,
                face_box=(0, 0, 64, 64),
                landmarks=np.zeros((0, 3), dtype=np.float32),
                quality=_quality(),
            )
        )
        assert out.applicable is False


class TestNoiseRobustness:
    @pytest.mark.parametrize("seed", [1, 2, 3])
    def test_no_signal_raises_on_noise(self, seed: int) -> None:
        rng = np.random.default_rng(seed)
        img = rng.integers(0, 255, (256, 256, 3)).astype(np.uint8)
        cap = Capture(
            image_bgr=np.ascontiguousarray(img),
            face_box=(32, 32, 224, 224),
            landmarks=np.zeros((0, 3), dtype=np.float32),
            quality=_quality(),
        )
        out = ChromaticAberrationSignal()(cap)  # must degrade to unavailable
        assert 0.0 <= out.quality <= 1.0
        for value in out.features.values():
            assert np.isfinite(value)
