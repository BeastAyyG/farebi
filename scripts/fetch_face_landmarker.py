"""Download the MediaPipe FaceLandmarker ``.task`` model asset.

The ``tasks`` face-mesh backend (the only one MediaPipe >= 0.10 exposes) needs a
model file that is *not* shipped with the package. This script fetches it once
into ``artifacts/models/face_landmarker.task`` so the serving pipeline can load
it in ``tasks`` mode.

Design notes:
* Stdlib only — no third-party dependency, so it runs in any environment where
  the package is installed, including the minimal ``--no-face-mesh`` CI image
  that still wants to warm the asset.
* Idempotent and safe: it refuses to overwrite an existing, plausibly-valid
  file unless ``--force`` is given, and it verifies the download is non-trivial
  before moving it into place (no half-written asset on a network blip).
* Honours ``FAREBI_ARTIFACTS__DIR`` so it lands in the same directory the
  running service will later read from.

Usage:
    python scripts/fetch_face_landmarker.py
    python scripts/fetch_face_landmarker.py --force
    python scripts/fetch_face_landmarker.py --url <url> --output <path>
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import urllib.request
from pathlib import Path

# The canonical float16 FaceLandmarker bundle. float16 keeps the asset small
# (~3.8 MB) while retaining landmark fidelity for a KYC capture path.
DEFAULT_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "face_landmarker/face_landmarker/float16/1/face_landmarker.task"
)
# Anything smaller than this cannot be a real model file.
MIN_PLAUSIBLE_BYTES = 1_000_000


def _artifacts_dir() -> Path:
    """Resolve the artifacts directory the same way the settings do (best effort)."""
    override = os.getenv("FAREBI_ARTIFACTS__DIR")
    if override:
        return Path(override)
    # Default lives at <repo>/artifacts; the script is run from the repo root.
    here = Path(__file__).resolve().parent
    return here.parent / "artifacts"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="model asset URL to download")
    parser.add_argument(
        "--output",
        default=None,
        help="destination path (default: <artifacts>/models/face_landmarker.task)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite an existing model file even if it looks valid",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    output = (
        Path(args.output) if args.output else _artifacts_dir() / "models" / "face_landmarker.task"
    )
    output.parent.mkdir(parents=True, exist_ok=True)

    if output.exists() and not args.force:
        size = output.stat().st_size
        if size >= MIN_PLAUSIBLE_BYTES:
            print(f"[skip] {output} already present ({size:,} bytes); use --force to re-download")
            return 0
        print(f"[warn] {output} exists but is only {size:,} bytes (suspect); re-downloading")

    print(f"[fetch] {args.url}")
    print(f"[dest]  {output}")
    try:
        # stream to a temp file so a failed/partial download never leaves a
        # corrupt asset in the final location.
        with tempfile.NamedTemporaryFile(
            dir=str(output.parent), delete=False, suffix=".part"
        ) as tmp:
            tmp_path = Path(tmp.name)
            with urllib.request.urlopen(args.url, timeout=60) as resp:
                total = int(resp.headers.get("Content-Length", "0") or "0")
                written = 0
                chunk_size = 1 << 16
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    tmp.write(chunk)
                    written += len(chunk)
                    if total:
                        pct = written * 100 // total
                        print(
                            f"\r[progress] {pct:3d}% ({written:,}/{total:,} bytes)",
                            end="",
                            flush=True,
                        )
            print()
    except Exception as exc:  # network/IO failures are the expected failure mode
        print(f"[error] download failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    if written < MIN_PLAUSIBLE_BYTES:
        tmp_path.unlink(missing_ok=True)
        print(
            f"[error] downloaded file is only {written:,} bytes; refusing to install",
            file=sys.stderr,
        )
        return 1

    tmp_path.replace(output)
    print(f"[ok] wrote {output} ({output.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
