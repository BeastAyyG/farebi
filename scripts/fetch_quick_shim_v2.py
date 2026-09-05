"""Extend the quick256 shim with two new source groups (v2 manifest).

ONE-TIME researcher script (Phase 04 data shim, NOT the Phase 03 pipeline).
Downloads shard-0 of 2 new HF parquet repos, saves decoded JPGs into the
existing data/raw/quick/ dir (gitignored), and writes
data/manifests/quick_manifest_v2.csv (tracked: v1 rows + new rows).

New groups (motivation: the nested-calibration probe showed the 5% UNCERTAIN
bar is unreachable at n=318 with 2 groups/side — calibration slices of
~50 samples swing wildly; v2 gives 3 groups/side so n_splits=3 runs with
one held-out group per side per fold and bigger calibration slices):
  real: bitmind/ffhq shard 100 resized 1024->256 (FFHQ identities are unique
        per image; shard 100 is disjoint from the v1 training_faces slice,
        so no identity overlap; resize matches the quick256 preprocessing)
  fake: bitmind/celeb-a-hq___FLUX.1-dev_training_faces (FLUX on the CelebA
        domain — same generator family as the v1 flux group but a different
        source domain, i.e. an honest domain-shift group)

Rejected candidates (documented so nobody re-tries them):
  bitmind/lfw — 250px candids, faces below the 24px-eye shim gate (6/120 kept)
  bitmind/white_paper_holdout_4___RealVisXL_V4.0 — holdout set holds no
        frontal faces (MediaPipe NO_FACE 32/40, Haar 0/12)
  bitmind/face-swap — 178x218 swaps, below the eye gate (same reason the
        kenjon repo was rejected during the vendor audit)

Usage:
    .venv/Scripts/python.exe scripts/fetch_quick_shim_v2.py [--n-per-group 120]
"""

from __future__ import annotations

import argparse
import csv
import io
import pathlib

import pandas as pd
from huggingface_hub import HfApi, hf_hub_download
from PIL import Image

# (repo, group, label, shard_substring, max_side_px)
REPOS: tuple[tuple[str, str, int, str, int], ...] = (
    ("bitmind/ffhq", "ffhq1024", 0, "train-00100-of-00190", 256),
    ("bitmind/celeb-a-hq___FLUX.1-dev_training_faces", "flux-celeba", 1, "train-00000", 256),
)

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "raw" / "quick"
V1_MANIFEST = ROOT / "data" / "manifests" / "quick_manifest.csv"
V2_MANIFEST = ROOT / "data" / "manifests" / "quick_manifest_v2.csv"

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

    with open(V1_MANIFEST, newline="") as fh:
        rows: list[dict[str, object]] = []
        for r in csv.DictReader(fh):
            rows.append(
                {
                    "path": r["path"],
                    "label": r["label"],
                    "source_group": r["source_group"],
                    "origin_repo": r["origin_repo"],
                }
            )
    print(f"carried {len(rows)} v1 rows")

    api = HfApi()
    for repo, group, label, shard_sub, max_side in REPOS:
        files = sorted(
            f
            for f in api.list_repo_files(repo, repo_type="dataset")
            if f.endswith(".parquet") and shard_sub in f
        )
        if not files:
            print(f"SKIP {repo}: no parquet matching {shard_sub!r} found")
            continue
        shard = hf_hub_download(repo, files[0], repo_type="dataset")
        df = pd.read_parquet(shard)
        col = _image_col(df)
        take = min(args.n_per_group, len(df))
        n = 0
        for i in range(take):
            try:
                img = _to_pil(df[col].iloc[i]).convert("RGB")
            except Exception as exc:  # shim: skip bad rows loudly
                print(f"SKIP {group}[{i}]: {exc}")
                continue
            if max(img.size) > max_side:
                img = img.resize((max_side, max_side), Image.Resampling.LANCZOS)
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

    with open(V2_MANIFEST, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["path", "label", "source_group", "origin_repo"])
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} rows to {V2_MANIFEST}")


if __name__ == "__main__":
    main()
