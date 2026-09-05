"""Download shard-0 of 4 HF parquet repos and slice face images for the harness shim.

ONE-TIME researcher script (Phase 04 data shim, NOT the Phase 03 pipeline).
Writes decoded images to data/raw/quick/ (gitignored) and a small CSV manifest
to data/manifests/quick_manifest.csv (tracked: provenance metadata only).

Sources (all public research datasets, CC / research licences):
  real: bitmind/ffhq-256_training_faces, bitmind/celeb-a-hq_training_faces
  fake: bitmind/ffhq-256___stable-diffusion-xl-base-1.0_training_faces (SDXL,
        paired with FFHQ), bitmind/ffhq-256___FLUX.1-dev_training_faces (FLUX)

Usage:
    .venv/Scripts/python.exe scripts/fetch_quick_shim_data.py [--n-per-group 120]
"""

from __future__ import annotations

import argparse
import csv
import io
import pathlib

import pandas as pd  # type: ignore[import-untyped]
from huggingface_hub import HfApi, hf_hub_download
from PIL import Image

REPOS: tuple[tuple[str, str], ...] = (
    ("bitmind/ffhq-256_training_faces", "ffhq"),
    ("bitmind/celeb-a-hq_training_faces", "celeba-hq"),
    ("bitmind/ffhq-256___stable-diffusion-xl-base-1.0_training_faces", "sdxl"),
    ("bitmind/ffhq-256___FLUX.1-dev_training_faces", "flux"),
)

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "raw" / "quick"
MANIFEST = ROOT / "data" / "manifests" / "quick_manifest.csv"

IMAGE_EXTS = {".jpg", ".jpeg", ".png"}


def _image_col(df: pd.DataFrame) -> str:
    for cand in ("image", "img", "file", "filepath", "path", "image_path"):
        if cand in df.columns:
            return cand
    raise KeyError(f"no image column in {list(df.columns)}")


def _to_pil(cell: object) -> Image.Image:
    if isinstance(cell, Image.Image):
        return cell
    if isinstance(cell, dict):  # HF datasets image struct serialised
        raw = cell.get("bytes")
        if raw is not None:
            return Image.open(io.BytesIO(bytes(raw)))
        p = cell.get("path")
        if p is not None:
            return Image.open(str(p))
    if isinstance(cell, (bytes, bytearray, memoryview)):
        return Image.open(io.BytesIO(bytes(cell)))
    if isinstance(cell, str):
        p = pathlib.Path(cell)
        if p.suffix.lower() in IMAGE_EXTS and p.exists():
            return Image.open(p)
    raise TypeError(f"cannot decode image cell of type {type(cell)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-per-group", type=int, default=120)
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, object]] = []
    api = HfApi()
    for repo, group in REPOS:
        files = sorted(
            f
            for f in api.list_repo_files(repo, repo_type="dataset")
            if f.endswith(".parquet") and "train" in f
        )
        if not files:
            print(f"SKIP {repo}: no train parquet found")
            continue
        shard = hf_hub_download(repo, files[0], repo_type="dataset")
        df = pd.read_parquet(shard)
        col = _image_col(df)
        label = 0 if group in ("ffhq", "celeba-hq") else 1
        take = min(args.n_per_group, len(df))
        n = 0
        for i in range(take):
            try:
                img = _to_pil(df[col].iloc[i]).convert("RGB")
            except Exception as exc:  # shim: skip bad rows loudly
                print(f"SKIP {group}[{i}]: {exc}")
                continue
            dest = OUT_DIR / f"{group}_{n:04d}.jpg"
            img.save(dest, quality=95)
            rows.append(
                {
                    "path": str(dest.relative_to(ROOT)).replace("\\", "/"),
                    "label": label,
                    "source_group": group,
                    "origin_repo": repo,
                }
            )
            n += 1
        print(f"{group}: kept {n}/{take} (label={label})")

    with open(MANIFEST, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["path", "label", "source_group", "origin_repo"])
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} rows to {MANIFEST}")


if __name__ == "__main__":
    main()
