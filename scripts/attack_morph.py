"""Face-morph attack probe (red-team, Phase 04).

Threat model (ID-photo morphing): the attacker blends two REAL identities
into one image that matches both — the classic KYC enrolment-fraud attack.
Unlike fully-synthetic fakes, a morph carries GENUINE sensor noise and
genuine camera optics from two real photos. Our KEEP portfolio was validated
only on synthetic fakes, so by construction PRNU (noise presence), texture
and CA may be blind here: the honest question is what — if anything — still
fires. Expectation going in: fft (blend ghosts/double edges) is the most
likely survivor; PRNU face_energy should stay in the real range.

Methodology (deterministic, torch-free, numpy+cv2+mediapipe only):
  1. Build captures for the quick-shim real rows with the shared
     FaceMeshDetector (same 24px/15-blur shim overrides as the builder).
  2. Pair ffhq rows sequentially (0,1), (2,3), ... and celeba-hq rows the
     same way. For each pair: similarity-align both faces to a 256px canon
     (eye-centre midpoint, inter-eye distance, in-plane angle), warp, then
     alpha-0.5 blend inside a feathered FACE_OVAL mask from image A so the
     background stays A's (background ghosts would let fft/texture fire for
     the wrong reason — this probe tests FACE morphs, not panorama seams).
  3. Write lossless PNGs under ``<group>_morph`` source groups (ffhq_morph,
     celeba_morph — two fake groups, preserving the n_splits=2 structure);
     real rows pass through unchanged. The probe manifest is real-vs-morph
     (clean synthetic fakes excluded to isolate the morph question).

Honest caveats (also recorded in RISK_REGISTER.md):
  * Landmark-based alignment is weaker than a professional morph pipeline
    (triangle-warp + Poisson blending + retouch). A real attacker smooths the
    seams our fft signal most likely catches — this probe is an UPPER BOUND
    on detectability, the mirror image of the copy-attack lower bound.
  * 256px inputs: morph seams are relatively coarser than at KYC resolution.

Usage:
    .venv/Scripts/python.exe scripts/attack_morph.py
"""

from __future__ import annotations

import csv
import math
import pathlib

import cv2
import numpy as np

from farebi.capture.capture import build_capture
from farebi.capture.face_mesh import FaceMeshDetector
from farebi.capture.landmarks import EYE_LEFT, EYE_RIGHT
from farebi.core.config import QualityConfig, get_settings, reload_settings
from farebi.core.security import UploadLimits
from farebi.utils.image_io import decode_image

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC_MANIFEST = ROOT / "data" / "manifests" / "quick_manifest.csv"
OUT_DIR = ROOT / "data" / "raw" / "quick_morph"
OUT_MANIFEST = ROOT / "data" / "manifests" / "quick_morph_manifest.csv"

_CANVAS = 256
# Canonical eye targets: NATURAL scale (dst_iod = 56px, matching the ~55px
# source iod of the 256px data). Caution learned twice: eye_width_px ~= 28 in
# the quality logs is the SINGLE-eye width, not the iod — a 30px target halved
# every head and tripped FACE_TOO_SMALL; the original 77px target zoomed ~1.4x
# and starved the background estimators. Scale ~= 1.0 preserves natural framing
# and backgrounds.
_DST_L = (_CANVAS / 2.0 - 28.0, 0.40 * _CANVAS)
_DST_R = (_CANVAS / 2.0 + 28.0, 0.40 * _CANVAS)
_FEATHER = 21


def _eye_centres(lm: np.ndarray, w: int, h: int) -> tuple[np.ndarray, np.ndarray]:
    """Mean eye-contour centres in pixel space (lm is normalised Nx3)."""
    px = lm[:, :2] * np.array([w, h], dtype=np.float32)
    left = px[np.asarray(EYE_LEFT, dtype=np.int64)].mean(axis=0)
    right = px[np.asarray(EYE_RIGHT, dtype=np.int64)].mean(axis=0)
    return np.asarray(left, dtype=np.float32), np.asarray(right, dtype=np.float32)


def _align_matrix(left: np.ndarray, right: np.ndarray) -> np.ndarray | None:
    """Similarity matrix mapping eye centres onto the canonical canvas."""
    src_mid = (left + right) / 2.0
    src_iod = float(np.linalg.norm(right - left))
    if src_iod < 1e-6:
        return None
    dst_mid = np.array(
        [(_DST_L[0] + _DST_R[0]) / 2.0, (_DST_L[1] + _DST_R[1]) / 2.0],
        dtype=np.float32,
    )
    dst_iod = _DST_R[0] - _DST_L[0]
    scale = dst_iod / src_iod
    src_ang = math.degrees(math.atan2(right[1] - left[1], right[0] - left[0]))
    mat = cv2.getRotationMatrix2D(tuple(float(v) for v in src_mid), src_ang, scale)
    mat[:, 2] += dst_mid - src_mid
    return np.asarray(mat, dtype=np.float64)


def _warp_points(pts: np.ndarray, mat: np.ndarray) -> np.ndarray:
    ones = np.ones((pts.shape[0], 1), dtype=np.float64)
    homog = np.concatenate([pts.astype(np.float64), ones], axis=1)
    return np.asarray(homog @ mat.T, dtype=np.float32)


def _morph_pair(
    img_a: np.ndarray, lm_a: np.ndarray, img_b: np.ndarray, lm_b: np.ndarray
) -> np.ndarray | None:
    """Blend two faces; None if either face is unalignable."""
    ha, wa = img_a.shape[:2]
    hb, wb = img_b.shape[:2]
    la, ra = _eye_centres(lm_a, wa, ha)
    lb, rb = _eye_centres(lm_b, wb, hb)
    ma = _align_matrix(la, ra)
    mb = _align_matrix(lb, rb)
    if ma is None or mb is None:
        return None
    # BORDER_REPLICATE: the default constant-black fill paints pure-0 wedges
    # along canvas edges whenever the similarity transform shifts the frame;
    # those wedges trip the clipped-pixel quality gate (and no real photo has
    # them). Replicate keeps edge statistics natural.
    wa_img = cv2.warpAffine(
        img_a, ma, (_CANVAS, _CANVAS), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE
    )
    wb_img = cv2.warpAffine(
        img_b, mb, (_CANVAS, _CANVAS), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE
    )
    # Feathered face mask from A's warped oval contour (background stays A's).
    oval = lm_a[:, :2] * np.array([wa, ha], dtype=np.float32)
    oval_w = _warp_points(np.asarray(oval, dtype=np.float32), ma)
    mask = np.zeros((_CANVAS, _CANVAS), dtype=np.float32)
    hull = cv2.convexHull(oval_w.astype(np.float32)).astype(np.int32)
    cv2.fillConvexPoly(mask, hull, 1.0)
    k = _FEATHER | 1
    mask = np.asarray(cv2.GaussianBlur(mask, (k, k), 0), dtype=np.float32)
    m = mask[..., None].astype(np.float32)
    blended = wa_img.astype(np.float32) * m + wb_img.astype(np.float32) * (1.0 - m)
    return np.asarray(np.clip(blended, 0, 255), dtype=np.uint8)


def main() -> None:
    with open(SRC_MANIFEST, newline="") as fh:
        reader = csv.DictReader(fh)
        assert reader.fieldnames is not None
        fieldnames = list(reader.fieldnames)
        rows = list(reader)

    upload = get_settings().upload
    limits = UploadLimits(
        max_bytes=upload.max_bytes,
        max_pixels=upload.max_pixels,
        max_edge_px=upload.max_edge_px,
        allowed_media_types=frozenset(upload.allowed_media_types),
    )
    base = reload_settings().capture
    config = base.model_copy(
        update={
            "quality": QualityConfig(
                min_face_px=base.quality.min_face_px,
                min_interocular_px=base.quality.min_interocular_px,
                min_eye_width_px=24,
                min_blur_score=15.0,
                min_exposure=base.quality.min_exposure,
                max_exposure=base.quality.max_exposure,
                max_clipped_fraction=base.quality.max_clipped_fraction,
            )
        }
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    morph_rows: list[dict[str, str]] = []
    kept_reals = 0
    with FaceMeshDetector() as detector:
        for group in ("ffhq", "celeba-hq"):
            group_rows = [r for r in rows if r["source_group"] == group and r["label"] == "0"]
            caps: list[tuple[dict[str, str], np.ndarray, np.ndarray]] = []
            for row in group_rows:
                raw = (ROOT / row["path"]).read_bytes()
                decoded = decode_image(
                    raw,
                    declared_media_type="image/jpeg",
                    filename=pathlib.Path(row["path"]).name,
                    limits=limits,
                )
                result = build_capture(decoded, config=config, detector=detector)
                if not result.ok or result.capture is None:
                    continue
                cap = result.capture
                caps.append((row, cap.image_bgr, np.asarray(cap.landmarks)))
            kept_reals += len(caps)
            made = 0
            for i in range(0, len(caps) - 1, 2):
                (row_a, img_a, lm_a), (_, img_b, lm_b) = caps[i], caps[i + 1]
                morphed = _morph_pair(img_a, lm_a, img_b, lm_b)
                if morphed is None:
                    continue
                name = f"{group}-morph_{made:04d}.png"
                cv2.imwrite(str(OUT_DIR / name), morphed)
                new_row = dict(row_a)
                new_row["path"] = (OUT_DIR / name).relative_to(ROOT).as_posix()
                new_row["label"] = "1"
                new_row["source_group"] = f"{group}_morph"
                morph_rows.append(new_row)
                made += 1
            print(f"{group}: {len(caps)} real captures -> {made} morphs")

    real_rows = [r for r in rows if r["label"] == "0"]
    with open(OUT_MANIFEST, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(real_rows + morph_rows)
    print(f"kept {kept_reals} real captures; wrote {len(morph_rows)} morphs -> {OUT_MANIFEST}")


if __name__ == "__main__":
    main()
