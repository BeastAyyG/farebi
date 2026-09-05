"""PRNU copy-attack probe (red-team, Phase 04).

Threat model (Lukas/Fridrich copy-attack): the attacker estimates a real
camera fingerprint F from public photos and transplants it onto a synthetic
face, J' = J * (1 + alpha * F), so the forgery carries realistic sensor
noise. Our ``prnu`` signal measures noise *presence* (face_energy), not PCE
matching against a reference — this probe asks whether transplanted noise
pushes fake face-energy into the real range and collapses the signal.

Methodology (deterministic, torch-free, numpy+cv2 only):
  1. Donor fingerprint: average Gaussian-residual (sigma=1.0) + row/column
     zero-mean over all 120 ffhq real rows — the same estimator
     ``signals/prnu.py`` uses, reimplemented here (~10 lines) so this OFFLINE
     script does not import signal internals.
  2. Strength calibration: sweep alpha over a small grid and keep the value
     whose attacked-fake median full-frame residual variance best matches the
     real median (adversarially fair — a real attacker tunes strength to
     blend in, and over-strength injection would be visibly noisy).
  3. Write attacked PNGs (lossless, so no JPEG confound) under new
     ``<group>_copyattack`` source groups; real rows pass through unchanged.

Honest caveats (also recorded in RISK_REGISTER.md):
  * Cross-camera donor: quick-shim reals come from many cameras, so the donor
    is generic sensor-like structure, not a true same-camera fingerprint. A
    same-camera attack is strictly stronger — this probe is a LOWER BOUND on
    attacker power. If even this fools the presence metric, same-camera does.
  * Digital transplant, not screen replay: ``replay_detect`` is not expected
    to fire and is not the mitigation. The structural fix is device-enrolment
    matching (store fingerprint at first verification), which is future work.

Usage:
    .venv/Scripts/python.exe scripts/attack_copy_prnu.py
"""

from __future__ import annotations

import csv
import pathlib

import cv2
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC_MANIFEST = ROOT / "data" / "manifests" / "quick_manifest.csv"
RAW_QUICK = ROOT / "data" / "raw" / "quick"
OUT_DIR = ROOT / "data" / "raw" / "quick_copyattack"
OUT_MANIFEST = ROOT / "data" / "manifests" / "quick_copyattack_manifest.csv"

_ALPHA_GRID: tuple[float, ...] = (0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.1)


def _residual(gray_u8: np.ndarray) -> np.ndarray:
    """Gaussian-residual + row/column zero-mean (mirrors signals/prnu.py)."""
    gray = np.asarray(gray_u8, dtype=np.float32)
    blurred = np.asarray(cv2.GaussianBlur(gray, (0, 0), 1.0), dtype=np.float32)
    res = gray - blurred
    res = res - res.mean(axis=1, keepdims=True)
    return np.ascontiguousarray(res - res.mean(axis=0, keepdims=True), dtype=np.float32)


def _gray(path: pathlib.Path) -> np.ndarray:
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError(f"cannot read {path}")
    return np.asarray(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), dtype=np.uint8)


def main() -> None:
    with open(SRC_MANIFEST, newline="") as fh:
        reader = csv.DictReader(fh)
        assert reader.fieldnames is not None
        fieldnames = list(reader.fieldnames)
        rows = list(reader)

    # 1. Donor fingerprint from the ffhq real rows (flat <group>_NNNN.jpg layout).
    donor_paths = sorted(RAW_QUICK.glob("ffhq_*.jpg"))
    if not donor_paths:
        raise RuntimeError(f"no donor images in {RAW_QUICK}")
    acc: np.ndarray | None = None
    for path in donor_paths:
        res = _residual(_gray(path))
        acc = res if acc is None else acc + res
    assert acc is not None
    donor = acc / len(donor_paths)
    donor = donor / (float(donor.std()) + 1e-6)
    print(f"donor fingerprint estimated from {len(donor_paths)} ffhq images")

    real_vars = [float(np.var(_residual(_gray(p)))) for p in donor_paths]
    real_median = float(np.median(real_vars))
    print(f"real median full-frame residual variance: {real_median:.3f}")

    fake_rows = [r for r in rows if int(r["label"]) == 1]
    fake_imgs = [(r, cv2.imread(str(ROOT / r["path"]), cv2.IMREAD_COLOR)) for r in fake_rows]
    for row, img in fake_imgs:
        if img is None:
            raise RuntimeError(f"cannot read {ROOT / row['path']}")

    # 2. Calibrate alpha against the real median variance.
    best_alpha = _ALPHA_GRID[0]
    best_gap = float("inf")
    for alpha in _ALPHA_GRID:
        attacked_vars = []
        for _, img in fake_imgs:
            assert img is not None
            f32 = np.asarray(img, dtype=np.float32)
            attacked = np.clip(f32 * (1.0 + alpha * donor[..., None]), 0, 255)
            gray = np.asarray(
                cv2.cvtColor(attacked.astype(np.uint8), cv2.COLOR_BGR2GRAY),
                dtype=np.uint8,
            )
            attacked_vars.append(float(np.var(_residual(gray))))
        gap = abs(float(np.median(attacked_vars)) - real_median)
        print(f"alpha={alpha:<5} attacked median variance gap: {gap:.3f}")
        if gap < best_gap:
            best_gap = gap
            best_alpha = alpha
    print(f"selected alpha={best_alpha} (gap {best_gap:.3f})")

    # 3. Write attacked PNGs + manifest.
    out_rows: list[dict[str, str]] = []
    n_attacked = 0
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for row, img in fake_imgs:
        assert img is not None
        f32 = np.asarray(img, dtype=np.float32)
        attacked = np.clip(f32 * (1.0 + best_alpha * donor[..., None]), 0, 255).astype(np.uint8)
        group = f"{row['source_group']}_copyattack"
        dest_dir = OUT_DIR / group
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / (pathlib.Path(row["path"]).stem + ".png")
        if not cv2.imwrite(str(dest), attacked):
            raise RuntimeError(f"write failed for {dest}")
        new_row = dict(row)
        new_row["path"] = dest.relative_to(ROOT).as_posix()
        new_row["source_group"] = group
        out_rows.append(new_row)
        n_attacked += 1
    for row in rows:
        if int(row["label"]) != 1:
            out_rows.append(row)  # real rows pass through unchanged

    with open(OUT_MANIFEST, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(out_rows)
    print(f"attacked {n_attacked} fakes (alpha={best_alpha}) -> {OUT_MANIFEST}")


if __name__ == "__main__":
    main()
