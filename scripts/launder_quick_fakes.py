"""Launder quick-shim fakes (PRNU-LAUNDER red-team probe, Phase 04).

Deterministic, torch-free laundering pipeline mimicking a social-media
re-share — the threat model from Mandelli et al. WIFS 2024
(``vendor/synthetic-image-detection``): a synthetic image passed through
resize + recompression steps that strip high-frequency generator traces.

Pipeline (all steps deterministic; cv2 JPEG encode/decode is fixed):
  1. downscale long edge to 128px (INTER_AREA — kills high-freq traces)
  2. JPEG encode qf=75, decode (first compression generation)
  3. upscale long edge back to 256px (INTER_LINEAR)
  4. JPEG encode qf=92 -> write file (second generation, share-like)

Reads label==1 rows from data/manifests/quick_manifest.csv, writes
laundered JPGs to data/raw/quick_laundered/<group>_laundered/ plus
data/manifests/quick_laundered_manifest.csv, which reuses the REAL rows
unchanged and points fake rows at the laundered files under new
source_group names (``<group>_laundered``). Feed that manifest to
build_quick_samples.py --manifest/--out, then evaluate real-vs-laundered.

This is evaluation methodology (OFFLINE), not product code.

Usage:
    .venv/Scripts/python.exe scripts/launder_quick_fakes.py
"""

from __future__ import annotations

import csv
import pathlib

import cv2
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC_MANIFEST = ROOT / "data" / "manifests" / "quick_manifest.csv"
OUT_DIR = ROOT / "data" / "raw" / "quick_laundered"
OUT_MANIFEST = ROOT / "data" / "manifests" / "quick_laundered_manifest.csv"

_LAUNDER_LONG_EDGE = 128
_RESTORE_LONG_EDGE = 256
_FIRST_JPEG_QF = 75
_FINAL_JPEG_QF = 92


def _scale_long_edge(img: np.ndarray, target: int, interp: int) -> np.ndarray:
    h, w = img.shape[:2]
    scale = target / max(h, w)
    return cv2.resize(img, (round(w * scale), round(h * scale)), interpolation=interp)


def launder(bgr: np.ndarray) -> np.ndarray:
    """Apply the deterministic laundering pipeline to a BGR image."""
    small = _scale_long_edge(bgr, _LAUNDER_LONG_EDGE, cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, _FIRST_JPEG_QF])
    if not ok:
        raise RuntimeError("first-generation JPEG encode failed")
    mid = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if mid is None:
        raise RuntimeError("first-generation JPEG decode failed")
    restored = _scale_long_edge(mid, _RESTORE_LONG_EDGE, cv2.INTER_LINEAR)
    return restored


def main() -> None:
    with open(SRC_MANIFEST, newline="") as fh:
        reader = csv.DictReader(fh)
        assert reader.fieldnames is not None
        fieldnames = list(reader.fieldnames)
        rows = list(reader)

    out_rows: list[dict[str, str]] = []
    n_laundered = 0
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for row in rows:
        if int(row["label"]) != 1:
            out_rows.append(row)  # real rows pass through unchanged
            continue
        src = ROOT / row["path"]
        img = cv2.imread(str(src), cv2.IMREAD_COLOR)
        if img is None:
            raise RuntimeError(f"cannot read {src}")
        group = f"{row['source_group']}_laundered"
        dest_dir = OUT_DIR / group
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name
        ok, buf = cv2.imencode(".jpg", launder(img), [cv2.IMWRITE_JPEG_QUALITY, _FINAL_JPEG_QF])
        if not ok:
            raise RuntimeError(f"final JPEG encode failed for {src}")
        dest.write_bytes(bytes(buf))
        new_row = {key: (row.get(key, "") or "") for key in fieldnames if key != "path"}
        new_row.update(
            {
                "path": dest.relative_to(ROOT).as_posix(),
                "label": "1",
                "source_group": group,
            }
        )
        out_rows.append(new_row)
        n_laundered += 1

    with open(OUT_MANIFEST, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(out_rows)
    print(f"laundered {n_laundered} fakes -> {OUT_DIR}")
    print(f"manifest ({len(out_rows)} rows) -> {OUT_MANIFEST}")


if __name__ == "__main__":
    main()
