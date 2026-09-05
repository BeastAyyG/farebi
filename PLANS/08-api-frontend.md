# 08 — API & Reviewer Frontend

**Parent:** [`FAREBI.md`](../FAREBI.md) · **Phases:** 7, 8 · **Depends on:** 07
**Status:** ⬜ Not started

## Objective

Expose the detector over HTTP with a hard security boundary, and build a reviewer UI that
lets a non-technical person understand and challenge a result.

## 8A — API

### Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/v1/detect` | Score one upload. Multipart/form-data, `UploadFile`. |
| `GET` | `/v1/model-info` | Model, threshold, calibration, fusion, registry versions + enabled signals. |
| `GET` | `/health` | Liveness. |
| `GET` | `/ready` | Readiness — artifacts loaded, model warm. |
| `GET` | `/v1/result/{request_id}` | Async result for signals routed to the worker (rPPG). |

### Files

```
src/farebi/api/
├── main.py            FastAPI app, exception handlers, request-id middleware
├── dependencies.py    Settings, Predictor, Fusion, SignalRegistry — all singletons
├── schemas.py         Pydantic request/response models (the published contract)
├── worker.py          Celery + Redis for slow signals
└── routes/            detect.py  health.py  model_info.py
```

### Response contract

```json
{
  "request_id": "uuid",
  "verdict": "uncertain",
  "fake_probability": 0.64,
  "confidence_level": "low",
  "uncertainty_score": 0.31,
  "capture_type": "selfie",
  "signals": [
    {"code": "VISUAL_MODEL_FAKE_SIGNAL", "direction": "toward_fake",
     "strength": 0.64, "message": "...", "limitation": "..."},
    {"code": "MODEL_DISAGREEMENT", "direction": "toward_uncertain",
     "strength": 0.58, "message": "..."},
    {"code": "METADATA_UNAVAILABLE", "direction": "neutral", "strength": 0.0,
     "message": "No trustworthy capture metadata was available. This is not evidence of manipulation."}
  ],
  "top_drivers": [{"signal": "...", "push": "fake", "weight": 0.31}],
  "quality": {"face_found": true, "face_count": 1, "blur_score": 0.18,
              "face_resolution_ok": true},
  "heatmap_base64": "...",
  "warnings": ["The result is uncertain and should be manually reviewed.",
               "This detector does not verify liveness or identity ownership."],
  "model_version": "farebi-0.1.0",
  "threshold_version": "...",
  "calibration_version": "..."
}
```

### Secure upload handling — `core/security.py` + `utils/image_io.py`

Mandatory controls (OWASP defence-in-depth):

- Allowlist JPEG and PNG only.
- **Verify actual file signatures** — never trust the client `Content-Type` or filename.
- Enforce maximum file size and maximum decoded pixel dimensions.
- Reject corrupt, truncated, and multi-frame files.
- **Generate our own temporary filenames.** The uploaded filename is never used as a path.
- Store temp files **outside the public web root**.
- **Delete images immediately after inference by default.** Retention is off unless
  explicitly configured, and then only with a documented lawful basis.
- **Never log raw images or EXIF values containing PII.**

### Async routing

rPPG and MC-dropout are too slow for a synchronous request → Celery/Redis. `/v1/detect`
returns `202` with a `request_id` when a slow signal is applicable; the client polls
`/v1/result/{id}`.

## 8B — Frontend

`frontend/` — React + Vite + TypeScript. No backend imports; HTTP only.

```
src/
├── main.tsx  App.tsx
├── api/client.ts          typed fetch wrapper
├── types/detection.ts     mirrors api/schemas.py
└── components/
    ├── UploadPanel.tsx        drag-drop, client-side type/size pre-check, preview
    ├── ResultCard.tsx         verdict + probability + confidence
    ├── ProbabilityBar.tsx     banded bar showing q_lo / q_hi
    ├── SignalList.tsx         per-signal explanations WITH limitations
    ├── DriverList.tsx         top-5 fusion drivers
    ├── HeatmapViewer.tsx      overlay + mandatory limitation notice
    ├── UncertaintyBanner.tsx  why this is uncertain + review recommendation
    └── PrivacyNotice.tsx      retention + limitations, always visible
```

### Colour and language rules

| Verdict | Colour |
| --- | --- |
| Likely Real | Green |
| Likely Fake | Red |
| Uncertain | Amber |
| Unable to Assess | Gray |

**Never** render "98% guaranteed fake". Render:

> Estimated manipulation probability: 0.82. Confidence: medium. The image should be manually
> reviewed.

The UI must always display: image preview, verdict, calibrated probability, confidence/
uncertainty indicator, signal explanations, heatmap with limitation, quality warnings, model
version, and the limitation + privacy notice.

## Exit gate

**API**
- [ ] Valid JPEG and PNG uploads score successfully.
- [ ] Rejected: wrong magic bytes with correct extension, oversized file, oversized dimensions,
      corrupt file, multi-frame GIF renamed `.jpg`, PDF renamed `.png`, path-traversal filename,
      and a filename containing null bytes / control characters.
- [ ] No temp file survives the request (asserted by test).
- [ ] No image bytes or EXIF values in logs (asserted by test).
- [ ] `/v1/model-info` reports all five version keys.
- [ ] Async path works end-to-end for a video capture bundle.

**Frontend**
- [ ] A non-technical person can read a report, say why the system reached its verdict, and
      agree or disagree with it — verified by a walkthrough with someone outside the team.
- [ ] Heatmap limitation notice is always visible when a heatmap is shown.
- [ ] Privacy notice states that uploads are not retained.
- [ ] All four verdict states render with the correct colour and copy.

## Risks

| Risk | Mitigation |
| --- | --- |
| Temp files leak on exception paths | `try/finally` with a context manager; test asserts the temp dir is empty after every request, including error cases |
| Heatmap is read as proof | Limitation notice is structurally adjacent, not a tooltip |
| Async complexity leaks into the common sync path | Sync path stays the default; async only when a slow signal is actually applicable |
| Reverse proxy / CORS misconfiguration exposes the API | `docker/nginx.conf` reviewed; CORS allowlist from config, never `*` in production |
