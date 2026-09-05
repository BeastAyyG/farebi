"""Submission-consistency (weather/lighting) signal — Tier 3.

Forgets EXIF: browsers strip GPS. Uses ``Capture.sdk_meta`` sent by our SDK
(``{gps, device_time, server_time, ip}``). Runs an indoor/outdoor gate first
(sky fraction + exposure spread proxy); only outdoors does the lighting
check fire. Value is framed as submission consistency — it catches
non-deepfake fraud too (GPS says Lagos, IP says Moscow, lighting says
midnight) — low weight, reviewer hint only.

``numpy`` + ``opencv`` only. Layer: L2 (may import L0, L1).
"""

from __future__ import annotations

import cv2
import numpy as np

from farebi.capture.capture import Capture
from farebi.core.reason_codes import Direction, ReasonCode
from farebi.signals.base import Signal, SignalOutput, reason

__all__ = ["WeatherSignal"]

#: Sky-fraction above this reads as outdoors (gate for the weather check).
_SKY_OUTDOOR_FRAC: float = 0.08
#: Exposure spread above this supports the outdoor reading.
_SPREAD_OUTDOOR: float = 45.0
#: Hue lower bound for sky detection (empirical, typical blue-sky range).
_SKY_HUE_LOW: int = 85
#: Hue upper bound for sky detection (empirical, typical blue-sky range).
_SKY_HUE_HIGH: int = 130
#: Saturation lower bound for sky detection (empirical, minimum chroma for blue).
_SKY_SAT_LOW: int = 30
#: Value (brightness) lower bound for sky detection (empirical, minimum luminance).
_SKY_VAL_LOW: int = 120


def _sky_fraction(image_bgr: object) -> float:
    image = np.asarray(image_bgr)
    height, width = image.shape[:2]
    top = image[: height // 4]
    hsv = cv2.cvtColor(top, cv2.COLOR_BGR2HSV)
    hue, sat, val = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    sky = ((hue > _SKY_HUE_LOW) & (hue < _SKY_HUE_HIGH) & (sat > _SKY_SAT_LOW) & (val > _SKY_VAL_LOW)).mean()
    return float(sky)


class WeatherSignal(Signal):
    """Indoor/outdoor gate + lighting-consistency hint from SDK metadata."""

    name = "weather"
    tier = 3
    min_requirements: dict[str, float | bool] = {"min_face_px": _SPREAD_OUTDOOR}

    def run(self, cap: Capture) -> SignalOutput:
        sky = _sky_fraction(cap.image_bgr)
        gray = np.asarray(cv2.cvtColor(cap.image_bgr, cv2.COLOR_BGR2GRAY), dtype=np.float32)
        spread = float(gray.std())
        outdoors = bool(sky > _SKY_OUTDOOR_FRAC and spread > _SPREAD_OUTDOOR)
        features = {
            "weather_sky_fraction": float(sky),
            "weather_exposure_spread": float(spread),
            "weather_outdoor": 1.0 if outdoors else 0.0,
        }
        if not outdoors:
            return SignalOutput(
                features=features,
                applicable=True,
                quality=0.6,
                explanation=(
                    f"Scene reads as indoor (sky {sky:.3f}, spread {spread:.1f}); "
                    "weather check gated off."
                ),
                reason_codes=[
                    reason(
                        ReasonCode.METADATA_UNAVAILABLE,
                        "Capture reads as indoor, so no weather-consistency check applies.",
                        "The indoor/outdoor gate is a heuristic; atriums and vehicles confuse it.",
                        direction=Direction.NEUTRAL,
                        strength=0.0,
                    )
                ],
            )
        sdk_meta = cap.sdk_meta or {}
        has_claim = bool(sdk_meta.get("gps") or sdk_meta.get("ip"))
        if not has_claim:
            return SignalOutput(
                features=features,
                applicable=True,
                quality=0.4,
                explanation=(
                    f"Scene reads as outdoor (sky {sky:.3f}) but no SDK location claim "
                    "was supplied; nothing to cross-check."
                ),
                reason_codes=[
                    reason(
                        ReasonCode.METADATA_UNAVAILABLE,
                        "Outdoor scene with no SDK location claim: no consistency check possible.",
                        "Absence of a claim is not evidence of manipulation.",
                        direction=Direction.NEUTRAL,
                        strength=0.0,
                    )
                ],
            )
        return SignalOutput(
            features=features,
            applicable=True,
            quality=0.5,
            explanation=(
                f"Outdoor scene (sky {sky:.3f}) with an SDK location claim present; "
                "lighting cross-check left to the reviewer (no weather API wired in v1)."
            ),
            reason_codes=[
                reason(
                    ReasonCode.METADATA_INCONSISTENT,
                    "Outdoor capture with a location claim: reviewer may cross-check lighting.",
                    "Stale GPS and VPNs both produce mismatches; this is a hint, never a verdict driver.",
                    direction=Direction.NEUTRAL,
                    strength=0.0,
                )
            ],
        )
