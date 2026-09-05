"""Real detection pipeline behind ``POST /v1/detect`` (Phase 08, first slice).

Runs the five KEEP signals from the Tier-1 harness over one uploaded image and
maps the internal :class:`SignalOutput` contract to the wire shape the reviewer
console consumes (``frontend/src/types/detection.ts`` ``DetectResponse``,
mirroring ``frebi.md`` A.13).

Honesty notes (do not "improve" these silently):

* The verdict rule is a v0 heuristic (fixed band, strength averaging), **not**
  the Phase-07 calibrated fusion. ``threshold_version`` echoes
  ``configs/thresholds.yaml`` (currently ``"uncalibrated-0.0.0"``) so every
  response advertises that fact.
* ``heatmap_base64`` is ``None``: per-signal attribution heatmaps are a Phase-07
  explain item, and the wire type allows null "when explanation is unavailable".
* ``capture_type`` defaults to ``selfie`` via :func:`build_capture`; uploads the
  pipeline cannot classify stay ``unknown`` only if the capture says so.

Layer: L8 api (may import L0-L2; must never import harness/evaluation).
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Final

import yaml

from farebi.capture.capture import Capture, CaptureResult, CaptureStatus, build_capture
from farebi.capture.face_mesh import FaceMeshDetector
from farebi.core.config import get_settings, reload_settings
from farebi.core.reason_codes import Direction, Reason
from farebi.core.security import UploadLimits
from farebi.signals.base import SignalOutput
from farebi.signals.registry import all_enabled
from farebi.utils.image_io import decode_image

MODEL_VERSION: Final = "kyc-detector-0.1.0"

#: v0 decision band on ``fake_probability``. Fixed placeholders until
#: ``scripts/tune_thresholds.py`` writes ``artifacts/thresholds.json`` from a
#: held-out calibration split (see ``configs/thresholds.yaml`` NON-NEGOTIABLE #3).
#: Named constants per the no-hardcoded-thresholds lint ethos.
_V0_Q_LO: Final = 0.4
_V0_Q_HI: Final = 0.6

#: A.9 reviewer-facing copy. The client renders 4xx ``detail`` verbatim, so these
#: must match ``frontend/src/lib/copy.ts`` ``UPLOAD_ERROR`` exactly.
_COPY_TOO_LARGE: Final = "File size exceeds limit of 10MB"
_COPY_BAD_FORMAT: Final = "Only JPEG and PNG are supported"
_COPY_CORRUPT: Final = "Could not read uploaded file - it may be corrupt"
_COPY_NO_FACE: Final = "No face detected in image - unable to assess"
_COPY_FACE_TOO_SMALL: Final = "Face is too small - move closer and try again"
_COPY_SERVER: Final = "An unexpected error occurred. Please try again."

_ALLOWED_SUFFIXES: Final = frozenset({".jpg", ".jpeg", ".png"})
_ALLOWED_MEDIA_TYPES: Final = frozenset({"image/jpeg", "image/png"})

_THRESHOLDS_PATH: Final = Path(__file__).resolve().parents[3] / "configs" / "thresholds.yaml"

_CLIP_MODEL = None
#: Research-drop checkpoint (605 MB full state dict, trained on quick256-v2,
#: cross-source AUC 0.9229 ± 0.0733). Borrowed-model lineage: a CLIP ViT-B/32
#: linear probe in the GenD style (``vendor/GenD``); the sanctioned Phase-06
#: weights drop belongs at ``artifacts/models/`` and will replace this path.
_CLIP_MODEL_WEIGHT_CANDIDATES: Final = (
    Path(__file__).resolve().parents[3] / "models" / "weights" / "clip_probe_v2.pt" / "clip_linear_probe_best.pt",
    Path(__file__).resolve().parents[3] / "models" / "weights" / "clip_linear_probe_best.pt",
    Path(__file__).resolve().parents[3] / "artifacts" / "models" / "clip-vit-fake.pt",
)

_FUSION_ARTIFACT_DIR: Final = Path(__file__).resolve().parents[3] / "artifacts" / "fusion"
_FUSION_SCALER_PATH = _FUSION_ARTIFACT_DIR / "scaler.pkl"
_FUSION_CLF_PATH = _FUSION_ARTIFACT_DIR / "classifier.pkl"
_FUSION_ISO_PATH = _FUSION_ARTIFACT_DIR / "isotonic.pkl"
_FUSION_BAND_PATH = _FUSION_ARTIFACT_DIR / "band.json"
_FUSION_FEATURE_NAMES_PATH = _FUSION_ARTIFACT_DIR / "feature_names.json"

_CLIP_MODEL = None
_FUSION_SCALER = None
_FUSION_CLF = None
_FUSION_ISO = None
_FUSION_BAND = None
_FUSION_FEATURE_NAMES = None


def _clip_weight_path() -> Path | None:
    for candidate in _CLIP_MODEL_WEIGHT_CANDIDATES:
        if candidate.is_file():
            return candidate
    return None


def _get_clip_model():  # type: ignore[no-untyped-def]
    """Lazily load the borrowed CLIP probe; ``None`` when unavailable.

    Torch is imported here, not at module import, so the serving slice stays
    importable (and testable) on machines without the ``ml`` extra. A missing
    checkpoint is absent evidence, never a 500 — the caller falls through to
    the next fallback tier.
    """
    global _CLIP_MODEL
    if _CLIP_MODEL is not None:
        return _CLIP_MODEL
    weight_path = _clip_weight_path()
    if weight_path is None:
        return None
    try:
        import torch

        from farebi.models import build_model

        model = build_model(
            "clip_linear_probe",
            num_classes=2,
            device="cuda" if torch.cuda.is_available() else "cpu",
        )
        model.load_state_dict(torch.load(weight_path, map_location=model.device))
        model.eval()
        _CLIP_MODEL = model
        return model
    except Exception:
        return None

def _load_fusion_artifacts():
    global _FUSION_SCALER, _FUSION_CLF, _FUSION_ISO, _FUSION_BAND, _FUSION_FEATURE_NAMES
    if _FUSION_SCALER is not None:
        return True
    if not _FUSION_SCALER_PATH.exists():
        return False
    try:
        import pickle
        with open(_FUSION_SCALER_PATH, "rb") as f:
            _FUSION_SCALER = pickle.load(f)
        with open(_FUSION_CLF_PATH, "rb") as f:
            _FUSION_CLF = pickle.load(f)
        with open(_FUSION_ISO_PATH, "rb") as f:
            _FUSION_ISO = pickle.load(f)
        with open(_FUSION_BAND_PATH, "rb") as f:
            _FUSION_BAND = json.load(f)
        with open(_FUSION_FEATURE_NAMES_PATH, "rb") as f:
            _FUSION_FEATURE_NAMES = json.load(f)
        return True
    except Exception:
        return False

def _fusion_predict(ran: list[tuple[str, SignalOutput]]) -> tuple[float, float, str, list[dict[str, Any]], float, float] | None:
    """Return (p_fake, uncertainty, confidence, drivers, q_lo, q_hi) or None."""
    if not _load_fusion_artifacts():
        return None
    scaler = _FUSION_SCALER
    clf = _FUSION_CLF
    iso = _FUSION_ISO
    band = _FUSION_BAND
    feat_names = _FUSION_FEATURE_NAMES
    if scaler is None or clf is None or iso is None or band is None or feat_names is None:
        return None

    # Build a dict of signal name -> features dict for applicable signals
    signal_features = {}
    for name, out in ran:
        if out.applicable and hasattr(out, 'features') and out.features is not None:
            signal_features[name] = out.features

    # Assemble feature vector in the order used during training
    feat_values = []
    for fname in feat_names:
        parts = fname.split("__", 1)
        if len(parts) != 2:
            return None
        sig_name, feat_key = parts
        if sig_name not in signal_features:
            return None
        val = signal_features[sig_name].get(feat_key)
        if val is None:
            return None
        feat_values.append(val)

    import numpy as np
    X = np.array(feat_values, dtype=np.float64).reshape(1, -1)
    X_scaled = scaler.transform(X)
    p_raw = clf.predict_proba(X_scaled)[0, 1]
    p_cal = float(iso.predict([p_raw])[0])
    q_lo = band["q_lo"]
    q_hi = band["q_hi"]

    # Continuous uncertainty: 1 on the band edges, decaying to 0 at the
    # extremes (confident real at 0, confident fake at 1).
    if q_lo < p_cal < q_hi:
        # Inside band: uncertainty = 1 (max uncertainty)
        uncertainty = 1.0
    elif p_cal <= q_lo:
        # Below lower bound: certain real at 0, boundary at q_lo.
        if q_lo > 0:
            uncertainty = p_cal / q_lo
        else:
            uncertainty = 1.0
        uncertainty = max(0.0, min(1.0, uncertainty))
    else:  # p_cal >= q_hi
        # Above upper bound: certain fake at 1, boundary at q_hi.
        if q_hi < 1.0:
            uncertainty = (1.0 - p_cal) / (1.0 - q_hi)
        else:
            uncertainty = 1.0
        uncertainty = max(0.0, min(1.0, uncertainty))

    high_cut, medium_cut = _confidence_cutoffs()
    if uncertainty <= high_cut:
        confidence = "high"
    elif uncertainty <= medium_cut:
        confidence = "medium"
    else:
        confidence = "low"

    # Compute drivers: top 2 features by absolute coefficient (after scaling)
    coef = clf.coef_[0]
    abs_coef = np.abs(coef)
    top_indices = np.argsort(abs_coef)[-2:][::-1]  # top 2
    drivers: list[dict[str, Any]] = []
    for idx in top_indices:
        fname = feat_names[int(idx)]
        # Map feature name to signal name and push direction
        sig, feat = fname.split("__", 1)
        # Direction: if coef positive, higher value pushes fake; else real
        push = "fake" if coef[int(idx)] > 0 else "real"
        drivers.append({
            "signal": sig,
            "feature": feat,
            "push": push,
            "weight": float(abs_coef[int(idx)]),
        })

    return p_cal, uncertainty, confidence, drivers, float(q_lo), float(q_hi)


class DetectFailure(Exception):
    """A 4xx detection failure: carries the HTTP status and the A.9 detail."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _confidence_cutoffs() -> tuple[float, float]:
    """(high, medium) uncertainty cutoffs from ``configs/thresholds.yaml``."""
    try:
        with open(_THRESHOLDS_PATH, encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
        levels = raw["confidence_levels"]
        return float(levels["high"]), float(levels["medium"])
    except Exception:  # missing file or schema drift: documented fallback
        return 0.15, 0.35


def _threshold_version() -> str:
    try:
        with open(_THRESHOLDS_PATH, encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
        return str(raw.get("version", "uncalibrated-0.0.0"))
    except Exception:
        return "uncalibrated-0.0.0"


def _pipeline_parts() -> tuple[UploadLimits, Any]:
    """Production upload limits + capture config (no research overrides)."""
    upload = get_settings().upload
    limits = UploadLimits(
        max_bytes=upload.max_bytes,
        max_pixels=upload.max_pixels,
        max_edge_px=upload.max_edge_px,
        allowed_media_types=frozenset(upload.allowed_media_types),
    )
    return limits, reload_settings().capture


def _sniff_media_type(filename: str, declared: str | None) -> str:
    suffix = Path(filename).suffix.lower()
    if declared in _ALLOWED_MEDIA_TYPES:
        return declared
    if suffix in _ALLOWED_SUFFIXES:
        return "image/png" if suffix == ".png" else "image/jpeg"
    raise DetectFailure(400, _COPY_BAD_FORMAT)


def _decode(raw: bytes, filename: str, declared: str | None, limits: UploadLimits) -> Any:
    if len(raw) > limits.max_bytes:
        raise DetectFailure(400, _COPY_TOO_LARGE)
    media_type = _sniff_media_type(filename, declared)
    try:
        return decode_image(
            raw,
            declared_media_type=media_type,
            filename=Path(filename).name or "capture",
            limits=limits,
        )
    except Exception:
        raise DetectFailure(400, _COPY_CORRUPT) from None


def _capture_or_raise(result: CaptureResult) -> Capture:
    if result.status is CaptureStatus.NO_FACE:
        raise DetectFailure(400, _COPY_NO_FACE)
    if result.status is CaptureStatus.DETECTOR_ERROR or result.capture is None:
        # Landmark/quality failures carry their own reviewer copy; a dead
        # detector is a server fault (route maps 500 to the fixed A.9 copy).
        if result.status is CaptureStatus.DETECTOR_ERROR:
            raise DetectFailure(500, _COPY_SERVER)
        raise DetectFailure(400, result.detail or _COPY_SERVER)
    if result.status is CaptureStatus.FACE_TOO_SMALL:
        raise DetectFailure(400, _COPY_FACE_TOO_SMALL)
    if result.status is not CaptureStatus.OK:
        # QUALITY_UNUSABLE, LANDMARKS_UNAVAILABLE: the pipeline's own detail
        # is the most truthful reviewer copy.
        raise DetectFailure(400, result.detail or _COPY_SERVER)
    return result.capture


def _primary_reason(output: SignalOutput) -> Reason | None:
    """Strongest reason wins; ties break toward_fake first (deterministic)."""
    direction_rank = {
        Direction.TOWARD_FAKE: 0,
        Direction.TOWARD_REAL: 1,
        Direction.TOWARD_UNCERTAIN: 2,
        Direction.NEUTRAL: 3,
    }
    ranked = sorted(
        output.reason_codes,
        key=lambda r: (-r.strength, direction_rank.get(r.direction, 4)),
    )
    return ranked[0] if ranked else None


def _wire_signal(name: str, output: SignalOutput) -> dict[str, Any]:
    primary = _primary_reason(output)
    if primary is None:
        return {
            "code": "SIGNAL_UNAVAILABLE",
            "direction": Direction.TOWARD_UNCERTAIN.value,
            "strength": 0.0,
            "message": output.explanation,
            "limitation": "A skipped signal is not evidence in either direction.",
            "applicable": False,
            "not_applicable_reason": output.explanation,
        }
    entry: dict[str, Any] = {
        "code": primary.code.value,
        "direction": primary.direction.value,
        "strength": round(float(primary.strength), 4),
        "message": primary.message,
        "limitation": primary.limitation,
    }
    if not output.applicable:
        entry["applicable"] = False
        entry["not_applicable_reason"] = output.explanation
    return entry


def _signal_leans(output: SignalOutput) -> tuple[float, float]:
    """(fake_strength, real_strength): max reason strength per direction."""
    fake = 0.0
    real = 0.0
    for reason in output.reason_codes:
        if reason.direction is Direction.TOWARD_FAKE:
            fake = max(fake, float(reason.strength))
        elif reason.direction is Direction.TOWARD_REAL:
            real = max(real, float(reason.strength))
    return fake, real


def _run_signals(capture: Capture) -> list[tuple[str, SignalOutput]]:
    """Run every fusion-eligible signal; a crashing signal is unavailable, not fatal."""
    ran: list[tuple[str, SignalOutput]] = []
    for sig in all_enabled():
        name: str = sig.name
        try:
            ran.append((name, sig(capture)))
        except Exception:
            ran.append((name, SignalOutput.unavailable(name, "signal raised during scoring")))
    return ran


def _verdict_and_scores(
    ran: list[tuple[str, SignalOutput]],
) -> tuple[str, float, float, str, list[dict[str, Any]]]:
    """v0 rule: mean fake/real strengths -> p_fake -> fixed band -> verdict."""
    applicable = [(name, out) for name, out in ran if out.applicable]
    if not applicable:
        return "unable_to_assess", 0.5, 1.0, "low", []
    fakes = []
    reals = []
    drivers: list[dict[str, Any]] = []
    for name, out in applicable:
        fake, real = _signal_leans(out)
        fakes.append(fake)
        reals.append(real)
        push = "fake" if fake > real else ("real" if real > fake else "uncertain")
        drivers.append(
            {
                "signal": name,
                "push": push,
                "weight": round(abs(fake - real), 4),
            }
        )
    mean_fake = sum(fakes) / len(fakes)
    mean_real = sum(reals) / len(reals)
    total = mean_fake + mean_real
    p_fake = mean_fake / total if total > 0 else 0.5

    if p_fake <= _V0_Q_LO:
        verdict = "likely_real"
    elif p_fake >= _V0_Q_HI:
        verdict = "likely_fake"
    else:
        verdict = "uncertain"

    inapplicable_frac = (len(ran) - len(applicable)) / max(len(ran), 1)
    uncertainty = 0.5 * inapplicable_frac + 0.5 * (1.0 - abs(2.0 * p_fake - 1.0))

    high_cut, medium_cut = _confidence_cutoffs()
    if uncertainty <= high_cut:
        confidence = "high"
    elif uncertainty <= medium_cut:
        confidence = "medium"
    else:
        confidence = "low"

    drivers.sort(key=lambda d: float(d["weight"]), reverse=True)
    return verdict, p_fake, uncertainty, confidence, drivers[:2]


def _wire_quality(capture: Capture) -> dict[str, Any]:
    quality: dict[str, Any] = dict(capture.quality)
    quality["face_found"] = True
    quality["face_count"] = 1
    quality["face_resolution_ok"] = bool(quality.get("usable", True))
    if "eye_width_px" in quality:
        quality["eye_px"] = quality["eye_width_px"]
    return quality


def _capture_type_wire(capture: Capture) -> str:
    if capture.capture_type == "id_photo":
        return "document"
    if capture.capture_type == "selfie":
        return "selfie"
    return "unknown"


def detect_image(raw: bytes, filename: str, media_type: str | None) -> dict[str, Any]:
    """Full pipeline: bytes -> Capture -> signals -> DetectResponse dict.

    Raises :class:`DetectFailure` for every 4xx path (bad upload, no usable
    face). Unexpected exceptions propagate to the route, which maps them to the
    fixed A.9 500 copy.
    """
    limits, config = _pipeline_parts()
    decoded = _decode(raw, filename, media_type, limits)
    with FaceMeshDetector() as detector:
        result = build_capture(decoded, config=config, detector=detector)
    capture = _capture_or_raise(result)

    ran = _run_signals(capture)
    # Tiered scoring, best evidence first: calibrated fusion, then the
    # borrowed CLIP probe, then the uncalibrated v0 heuristic. Every tier is
    # advertised via `calibration_version` so no response ever pretends to be
    # more calibrated than it is.
    fusion_result = _fusion_predict(ran)
    clip_model = None if fusion_result is not None else _get_clip_model()
    if fusion_result is not None:
        p_fake, uncertainty, confidence, drivers, q_lo, q_hi = fusion_result
        verdict = "likely_fake" if p_fake > 0.5 else "likely_real"
        calib_version = "fusion_v1"
        band = {"q_lo": q_lo, "q_hi": q_hi}
    elif clip_model is not None:
        import torch
        from PIL import Image

        pil_img = Image.fromarray(capture.image_rgb)
        tensor = clip_model.preprocess(pil_img).unsqueeze(0).to(clip_model.device)
        with torch.no_grad():
            logits = clip_model(tensor)
            probs = torch.softmax(logits, dim=1)[0]
        p_fake = float(probs[1].item())
        uncertainty = 1.0 - abs(2.0 * p_fake - 1.0)
        high_cut, medium_cut = _confidence_cutoffs()
        if uncertainty <= high_cut:
            confidence = "high"
        elif uncertainty <= medium_cut:
            confidence = "medium"
        else:
            confidence = "low"
        verdict = "likely_fake" if p_fake > 0.5 else "likely_real"
        drivers = []
        calib_version = "clip_probe_v2"
        band = {"q_lo": _V0_Q_LO, "q_hi": _V0_Q_HI}
    else:
        verdict, p_fake, uncertainty, confidence, drivers = _verdict_and_scores(ran)
        calib_version = "uncalibrated"
        band = {"q_lo": _V0_Q_LO, "q_hi": _V0_Q_HI}

    warnings: list[str] = []
    if verdict == "uncertain":
        warnings.append("The result is uncertain and should be manually reviewed.")
    if any(code is not None and code.code.value == "MULTIPLE_FACES" for code in result.reasons):
        warnings.append("Multiple faces detected; scored the most prominent one.")
    for name, out in ran:
        if not out.applicable:
            warnings.append(f"{name} could not be measured on this image.")

    return {
        "request_id": uuid.uuid4().hex,
        "verdict": verdict,
        "fake_probability": round(float(p_fake), 4),
        "confidence_level": confidence,
        "uncertainty_score": round(float(uncertainty), 4),
        "capture_type": _capture_type_wire(capture),
        "signals": [_wire_signal(name, out) for name, out in ran],
        "quality": _wire_quality(capture),
        "heatmap_base64": None,
        "warnings": warnings,
        "model_version": MODEL_VERSION,
        "threshold_version": _threshold_version(),
        "calibration_version": calib_version,
        "top_drivers": drivers,
        "band": {"q_lo": _V0_Q_LO, "q_hi": _V0_Q_HI},
    }


def list_signal_names() -> list[str]:
    """Names of fusion-eligible signals (import-safe: discovery never raises)."""
    names: list[str] = []
    for sig in all_enabled():
        try:
            names.append(sig.name)
        except Exception:
            continue
    return names
