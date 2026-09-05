# Frontend Requirements — frebi.md

**Purpose:** This file documents every UI element, component, and interaction needed for the Farebi frontend. Read alongside `FAREBI.md` (the master plan) and `IDEA.md` (the delivery shell). This is your single source of truth for what the frontend must display, how it must behave, and what edge cases to handle.

---

## 1. Core Verdict Display

### 1.1 Verdict States with Colors
| Verdict | Color | Label |
|---|---|---|
| `likely_real` | Green (`#22c55e`) | "Likely Real" |
| `likely_fake` | Red (`#ef4444`) | "Likely Fake" |
| `uncertain` | Amber (`#eab308`) | "Uncertain" |
| `unable_to_assess` | Gray (`#6b7280`) | "Unable to Assess" |

### 1.2 Probability Text (MANDATORY FORMAT)
Never render raw percentages or "guaranteed" statements. Always use:

> "Estimated manipulation probability: **0.82**. **Confidence:** medium. The image should be manually reviewed."

| Field | Description |
|---|---|
| `fake_probability` | Calibrated probability in [0, 1] — displayed as `0.82` |
| `confidence_level` | `low` / `medium` / `high` — derived from uncertainty score and band position |

### 1.3 Confidence Badge
Show near the probability text:
- `low`: "Low confidence — result should be manually reviewed"
- `medium`: "Medium confidence — proceed with caution"
- `high`: "High confidence — result may be trusted"

---

## 2. Image Upload & Preview

### 2.1 Supported Formats
- JPEG (`image/jpeg`)
- PNG (`image/png`)

### 2.2 Upload Constraints (enforced by API, but UI should preview)
- Max file size: 10MB (configurable)
- Max pixel dimension: 2048×2048 (configurable)
- Single frame only (no multi-page TIFF/GIF unless supported)
- Valid magic bytes (JPEG/PNG) — do not trust MIME type

### 2.3 Preview Behavior
- Display compressed preview (max 400×400) immediately after upload
- Show "Validating..." spinner during security checks
- On rejection, show specific error reason (size, format, corrupt, no face detected)

---

## 3. Signal Explanations

### 3.1 Signal Code List (from `signals/` registry)
Each signal returns a `SignalOutput` with these displayable fields:

| Field | Example |
|---|---|
| `code` | `"FFT_FREQUENCY"` |
| `direction` | `"toward_fake"` / `"toward_real"` / `"neutral"` |
| `strength` | `0.64` (float in [0, 1]) |
| `message` | `"The visual classifier found patterns associated with manipulated images."` |
| `limitation` | `"Similar patterns can also be caused by background removal or image compression."` |

### 3.2 Signal Display Component
For each applicable signal (`applicable: true`):
- Show `code` as clickable tag (opens signal docs)
- Show `direction` arrow (↑ toward fake, ↓ toward real, → neutral)
- Show `strength` as progress bar (0 to 1)
- Show `message` as tooltip or secondary text
- Show `limitation` in smaller dimmed text

### 3.3 Inapplicable Signals
Show greyed-out: `"Signal not applicable — eyes too small / no video / no GPS"` with reason from `quality` field.

---

## 4. Attribution Heatmap

### 4.1 Heatmap Views (toggleable)
| View | Description |
|---|---|
| `original` | The uploaded image |
| `attribution` | Colored map showing per-pixel contribution (red = toward fake, blue = toward real) |
| `overlay` | Original + semi-transparent attribution map |
| `region_scores` | Breakdown by facial region (forehead, eyes, nose, mouth, chin) with scores |

### 4.2 Limitation Notice (MANDATORY)
Always display beneath heatmap:

> "This heatmap shows pixel areas the model focused on. It is **not definitive proof** of manipulation. Similar patterns can be caused by lighting, background, or compression. Always combine with manual review."

### 4.3 Heatmap Download
- Button to download as PNG base64
- Include the limitation notice in the download metadata

---

## 5. Quality Warnings

### 5.1 Quality Indicators (from `quality` dict in SignalOutput / Capture)
| Indicator | Threshold | Display |
|---|---|---|
| `blur_score` | > 0.3 | "⚠ Image is blurry — may affect accuracy" |
| `face_resolution_ok` | face_px < 40 | "⚠ Face is small (< 40px) — consider moving closer" |
| `eye_px` | < 40 | "⚠ Eyes too small for some signals" |
| `exposure` | extreme | "⚠ Poor exposure — result may be unreliable" |
| `iou` (eye overlap) | < 0.5 | "⚠ Face partially obscured" |

### 5.2 Quality Summary Bar
Show a horizontal bar at top of results:
- Green: All quality checks pass
- Amber: Some warnings present
- Red: Critical quality failure (→ `unable_to_assess`)

---

## 6. Model & Version Information

### 6.1 Version Display
Show three version numbers from `artifacts/`:
```
Model:      kyc-detector-0.1.0
Threshold:  conformal-q0.05-v1
Calibration: temperature-v2
```

### 6.2 Model Info Tooltip
On hover, show:
- Architecture (CLIP-ViT / backbone + head)
- Training data summary
- Last updated
- SHA256 of weights

---

## 7. Privacy & Limitation Notice

### 7.1 Persistent Banner (bottom of page)
> **Important:** This detector analyzes image manipulation only. It does **not** verify liveness, identity ownership, or document authenticity. Results should be combined with manual review and capture/liveness controls per NIST guidelines. Uploaded images are deleted after inference by default.

### 7.2 Per-Result Warning
Append to every result:
> "This detector does not verify liveness or identity ownership. Result should be manually reviewed."

---

## 8. Verdict Policy Visualization

### 8.1 Band Indicator (for `uncertain` results)
Show a progress-like indicator:
```
[ q_lo ──────────── p_fake ──────────── q_hi ]
0.0        0.5        1.0
```
- Green zone: `p_fake ≤ q_li` → `likely_real`
- Red zone: `p_fake ≥ q_hi` → `likely_fake`
- Amber zone: inside band → `uncertain`

### 8.2 Uncertainty Score
Display numeric uncertainty score (0 to 1) from inference pipeline, with interpretation:
- `< 0.3`: Low uncertainty
- `0.3–0.6`: Medium
- `> 0.6`: High — strongly recommend manual review

---

## 9. Edge Cases & Error States

### 9.1 Upload Errors
| Error | UI Message |
|---|---|
| File too large | "File size exceeds limit of 10MB" |
| Invalid format | "Only JPEG and PNG are supported" |
| Corrupt file | "Could not read uploaded file — it may be corrupt" |
| Multi-frame | "Multi-frame files are not supported" |
| No face detected | "No face detected in image — unable to assess" |
| Face too small | "Face is too small — move closer and try again" |

### 9.2 API Errors
| Status | UI Handling |
|---|---|
| 400 | Show specific error detail from response |
| 500 | "An unexpected error occurred. Please try again." |
| Timeout | "Request timed out. Check your connection and try again." |

### 9.3 Empty/No Result State
When no image uploaded or result loading:
- Show illustration or placeholder
- Text: "Upload an image to begin detection"
- Hint: "JPEG or PNG, under 10MB"

---

## 10. Accessibility Requirements

- All color information conveyed also via text/patterns (not color alone)
- Verdict labels are screen-reader friendly
- Heatmap has `aria-label` describing what it shows
- Focus management: after upload, focus moves to result area
- Contrast ratio ≥ 4.5:1 for all text

---

## 11. "Absurd / Creative" Ideas (High-Impact Only)

| Idea | Description | Rationale |
|---|---|---|
| `"Signal Radar Chart"` | Radial chart showing each signal's strength simultaneously | Multi-signal balance at a glance; educates non-experts |
| `"What-if Slider"` | Slider to adjust probability threshold and see how verdict changes | Demonstrates sensitivity and uncertainty; builds trust |
| `"Reason Code Explorer"` | Clickable reason codes that expand into forensic explanations | Bridges technical signals to human understanding |
| `"Social Media Recompression Simulator"` | Preview image after Instagram/Facebook recompression and see how result changes | Shows robustness limits honestly; manages expectations |

---

## 12. Component Summary

| Component | Props | Key Behavior |
|---|---|---|
| `UploadPanel` | `onSelect`, `onPreview` | Browse + drag-and-drop, preview, validate |
| `ResultCard` | `verdict`, `probability`, `confidence`, `signals` | Display core verdict + probability + signal list |
| `ProbabilityBar` | `value`, `confidence`, `verdict` | Colored bar with probability text |
| `SignalList` | `signals[]` | Loop over applicable signals, show code/direction/strength |
| `HeatmapViewer` | `image`, `map`, `mode` | Toggle original/attribution/overlay/region_scores |
| `UncertaintyBanner` | `uncertainty_score`, `in_band` | Amber banner with recommendation |
| `PrivacyNotice` | `n/a` | Persistent bottom banner |
| `VersionInfo` | `model`, `threshold`, `calibration` | Three version numbers |
| `QualityWarnings` | `quality dict` | Horizontal bar with individual warnings |

---

## 13. API Response Shape (What Frontend Receives)

```json
{
  "request_id": "8ae1bf1c-3a28-4f58-a850-53a65db12c17",
  "verdict": "uncertain",
  "fake_probability": 0.64,
  "confidence_level": "low",
  "uncertainty_score": 0.31,
  "capture_type": "selfie",
  "signals": [...],
  "quality": {
    "face_found": true,
    "face_count": 1,
    "blur_score": 0.18,
    "face_resolution_ok": true
  },
  "heatmap_base64": "...",
  "warnings": ["The result is uncertain and should be manually reviewed."],
  "model_version": "kyc-detector-0.1.0"
}
```

---

## 14. Integration Checklist

- [ ] UploadPanel connected to `/v1/detect` endpoint
- [ ] Verdict displayed with correct color and label
- [ ] Probability text follows mandatory format
- [ ] Confidence level badge shown
- [ ] Quality warnings displayed per `quality` dict
- [ ] Signal explanations rendered for applicable signals
- [ ] Heatmap viewer with limitation notice
- [ ] Model version shown
- [ ] Persistent privacy notice at bottom
- [ ] All error states handled
- [ ] Accessibility requirements met
- [ ] Download heatmap button works
- [ ] Version info displayed

---