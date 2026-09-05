"""Screen-replay simulation probe (red-team, Phase 04).

Threat model (physical replay): the attacker displays a synthetic face on a
phone/laptop panel and photographs the screen with a real camera. The replayed
photo carries the photographing camera's PRNU — so ``prnu`` measuring noise
*presence* cannot catch it — but it should carry screen tells (moiré, gamut
shift, sheen, flattened micro-contrast) that ``replay_detect`` was built for.
This probe asks whether the L2 signal fires on L3-simulated replays of the
quick-shim fakes, and how the other KEEP signals move.

Methodology (deterministic, torch-free, reuses the shipped simulator):
  1. Every label=1 row of quick_manifest.csv is passed through
     ``ScreenReplaySimulator(seed=7)`` — one shared instance, so the sampled
     parameter sequence is deterministic in manifest order. At 256px inputs
     the display-composite step is a no-op (scale caps at 1.0); moiré
     (pitch 2-6px), gamut, sheen (p=0.5), and depth-flattening apply.
  2. Replayed PNGs (lossless, so no extra JPEG confound beyond what the
     harness itself applies) go under new ``<group>_replay`` source groups;
     real rows pass through unchanged.

Honest caveats (also recorded in RISK_REGISTER.md):
  * NO photographing-camera noise is added: the simulator synthesises screen
    tells but not sensor noise, so simulated replays are PRNU-absent while a
    REAL photographed screen would carry the attacker's camera PRNU. Any PRNU
    separation on this probe is a SIMULATION ARTIFACT and must not be
    credited — real-replay validation awaits photographed screens from the
    self-capture campaign (data/capture_campaign/).
  * Partial circularity: the simulator's moiré pitch range (2-6px) sits inside
    replay_detect's detection band (radius 0.05-0.45 ~ periods 2.2-20px), so
    strong replay_detect separation partly validates end-to-end plumbing
    rather than discovering moiré. The operational question — firing on
    replayed fakes vs clean reals — still stands.
  * BGR/RGB: cv2 loads BGR; the simulator assumes RGB (luma + per-channel
    gamut), so convert BGR->RGB before and back after.

Usage:
    .venv/Scripts/python.exe scripts/attack_replay_sim.py
"""

from __future__ import annotations

import csv
import pathlib
import sys

import cv2
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from farebi.degradation.replay import ScreenReplaySimulator  # noqa: E402

SRC_MANIFEST = ROOT / "data" / "manifests" / "quick_manifest.csv"
OUT_DIR = ROOT / "data" / "raw" / "quick_replay"
OUT_MANIFEST = ROOT / "data" / "manifests" / "quick_replay_manifest.csv"

_SIM_SEED = 7


def main() -> None:
    with open(SRC_MANIFEST, newline="") as fh:
        reader = csv.DictReader(fh)
        assert reader.fieldnames is not None
        fieldnames = list(reader.fieldnames)
        rows = list(reader)

    fake_rows = [r for r in rows if int(r["label"]) == 1]
    sim = ScreenReplaySimulator(seed=_SIM_SEED)

    out_rows: list[dict[str, str]] = []
    n_replayed = 0
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for row in fake_rows:
        img_bgr = cv2.imread(str(ROOT / row["path"]), cv2.IMREAD_COLOR)
        if img_bgr is None:
            raise RuntimeError(f"cannot read {ROOT / row['path']}")
        img_rgb = np.asarray(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB), dtype=np.uint8)
        replayed_rgb = sim(img_rgb)
        replayed_bgr = cv2.cvtColor(replayed_rgb, cv2.COLOR_RGB2BGR)
        group = f"{row['source_group']}_replay"
        dest_dir = OUT_DIR / group
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / (pathlib.Path(row["path"]).stem + ".png")
        if not cv2.imwrite(str(dest), replayed_bgr):
            raise RuntimeError(f"write failed for {dest}")
        new_row = dict(row)
        new_row["path"] = dest.relative_to(ROOT).as_posix()
        new_row["source_group"] = group
        out_rows.append(new_row)
        n_replayed += 1
    for row in rows:
        if int(row["label"]) != 1:
            out_rows.append(row)  # real rows pass through unchanged

    with open(OUT_MANIFEST, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(out_rows)
    print(f"replayed {n_replayed} fakes (seed={_SIM_SEED}) -> {OUT_MANIFEST}")


if __name__ == "__main__":
    main()
