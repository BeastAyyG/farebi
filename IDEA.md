# Recommended Project Structure

Build this as a **three-outcome detector**:

- `likely_real`
- `likely_fake`
- `uncertain`
- Also support `unable_to_assess` for invalid, blurry, tiny, or no-face images.

For KYC, the detector should be a **risk signal**, not the only reason to reject someone. NIST identity guidance recommends combining automated media analysis with manual review and capture/liveness controls. 

```text
kyc-deepfake-detector/
│
├── README.md
├── LICENSE
├── SECURITY.md
├── THREAT_MODEL.md
├── MODEL_CARD.md
├── DATA_CARD.md
├── RISK_REGISTER.md
│
├── .gitignore
├── .dockerignore
├── .env.example
├── pyproject.toml
├── uv.lock
├── Makefile
├── docker-compose.yml
│
├── configs/
│   ├── app.yaml
│   ├── labels.yaml
│   ├── model.yaml
│   ├── training.yaml
│   ├── thresholds.yaml
│   └── signals.yaml
│
├── data/
│   ├── README.md
│   ├── raw/
│   │   └── .gitkeep
│   ├── interim/
│   │   └── .gitkeep
│   ├── processed/
│   │   └── .gitkeep
│   ├── manifests/
│   │   ├── schema.json
│   │   └── sample_manifest.csv
│   └── splits/
│       ├── train.csv
│       ├── validation.csv
│       ├── calibration.csv
│       ├── test_known.csv
│       └── test_unseen_generator.csv
│
├── artifacts/
│   ├── models/
│   │   └── .gitkeep
│   ├── calibration/
│   │   └── .gitkeep
│   ├── reports/
│   │   └── .gitkeep
│   └── model_registry.json
│
├── src/
│   └── kyc_detector/
│       ├── __init__.py
│       │
│       ├── api/
│       │   ├── __init__.py
│       │   ├── main.py
│       │   ├── dependencies.py
│       │   ├── schemas.py
│       │   └── routes/
│       │       ├── __init__.py
│       │       ├── detect.py
│       │       ├── health.py
│       │       └── model_info.py
│       │
│       ├── core/
│       │   ├── __init__.py
│       │   ├── config.py
│       │   ├── constants.py
│       │   ├── logging.py
│       │   ├── reason_codes.py
│       │   └── security.py
│       │
│       ├── data/
│       │   ├── __init__.py
│       │   ├── dataset.py
│       │   ├── manifest.py
│       │   ├── split.py
│       │   ├── transforms.py
│       │   └── validators.py
│       │
│       ├── models/
│       │   ├── __init__.py
│       │   ├── backbone.py
│       │   ├── classifier.py
│       │   ├── ensemble.py
│       │   ├── losses.py
│       │   └── registry.py
│       │
│       ├── forensics/
│       │   ├── __init__.py
│       │   ├── face_locator.py
│       │   ├── image_quality.py
│       │   ├── metadata.py
│       │   ├── frequency.py
│       │   └── compression.py
│       │
│       ├── inference/
│       │   ├── __init__.py
│       │   ├── pipeline.py
│       │   ├── predictor.py
│       │   ├── calibration.py
│       │   ├── uncertainty.py
│       │   └── policy.py
│       │
│       ├── explain/
│       │   ├── __init__.py
│       │   ├── attribution.py
│       │   ├── heatmap.py
│       │   └── signal_summary.py
│       │
│       ├── evaluation/
│       │   ├── __init__.py
│       │   ├── metrics.py
│       │   ├── calibration_metrics.py
│       │   ├── robustness.py
│       │   ├── slices.py
│       │   └── report.py
│       │
│       └── utils/
│           ├── __init__.py
│           ├── image_io.py
│           ├── hashing.py
│           └── seed.py
│
├── scripts/
│   ├── prepare_data.py
│   ├── generate_splits.py
│   ├── audit_dataset.py
│   ├── train.py
│   ├── calibrate.py
│   ├── tune_thresholds.py
│   ├── evaluate.py
│   ├── export_model.py
│   └── smoke_test.py
│
├── frontend/
│   ├── package.json
│   ├── package-lock.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── api/
│       │   └── client.ts
│       ├── types/
│       │   └── detection.ts
│       ├── components/
│       │   ├── UploadPanel.tsx
│       │   ├── ResultCard.tsx
│       │   ├── ProbabilityBar.tsx
│       │   ├── SignalList.tsx
│       │   ├── HeatmapViewer.tsx
│       │   ├── UncertaintyBanner.tsx
│       │   └── PrivacyNotice.tsx
│       └── styles/
│           └── app.css
│
├── tests/
│   ├── conftest.py
│   ├── fixtures/
│   │   └── README.md
│   ├── unit/
│   │   ├── test_image_validation.py
│   │   ├── test_calibration.py
│   │   ├── test_uncertainty.py
│   │   ├── test_policy.py
│   │   └── test_signal_summary.py
│   ├── integration/
│   │   ├── test_detect_api.py
│   │   └── test_inference_pipeline.py
│   ├── security/
│   │   └── test_upload_security.py
│   └── robustness/
│       ├── test_jpeg_recompression.py
│       ├── test_resize_crop.py
│       └── test_blur_noise.py
│
├── docs/
│   ├── architecture.md
│   ├── api.md
│   ├── data_collection.md
│   ├── evaluation_protocol.md
│   ├── deployment.md
│   ├── limitations.md
│   └── incident_response.md
│
├── monitoring/
│   ├── drift.py
│   ├── alerts.yaml
│   └── dashboard.json
│
├── docker/
│   ├── api.Dockerfile
│   ├── web.Dockerfile
│   └── nginx.conf
│
└── .github/
    └── workflows/
        └── ci.yml
```

---

## Most Important Files

### 1. Project and risk documentation

#### `README.md`

Include:

- Project objective
- Supported image formats
- Installation instructions
- Training instructions
- API and UI startup commands
- Example output
- Known limitations
- Privacy notice

#### `THREAT_MODEL.md`

Define what the project detects.

**In scope:**

- Fully AI-generated faces
- Face swaps
- Face morphs
- Local facial manipulation
- Heavily manipulated selfies
- Recompressed and screenshot versions of attacks

**Out of scope:**

- A stolen but genuine photograph
- Whether the face belongs to the claimed person
- Liveness from one still image
- Physical masks
- Complete identity-document authenticity

#### `MODEL_CARD.md`

Record:

- Model architecture and version
- Training datasets
- Label definitions
- Evaluation metrics
- Known failure cases
- Thresholds
- Demographic and quality slice results
- Intended and prohibited uses

#### `RISK_REGISTER.md`

Track risks such as:

- Genuine photos being flagged
- New generators bypassing the model
- Poor performance on compressed images
- Demographic performance differences
- Leakage of biometric information
- Users treating the heatmap as definitive proof

---

## 2. Dataset files

Your manifest should contain more than a binary label.

Example `sample_manifest.csv`:

```csv
image_path,binary_label,attack_type,source_dataset,generator_family,identity_id,capture_type,split
processed/real/001.jpg,0,real,source_a,none,person_001,selfie,train
processed/fake/002.jpg,1,fully_synthetic,source_b,generator_x,synthetic_001,selfie,train
processed/fake/003.jpg,1,face_morph,source_c,morph_tool_y,morph_001,id_photo,test_unseen
```

Recommended attack types:

```yaml
real:
  - authentic
  - authentic_benign_processed

fake_or_manipulated:
  - fully_synthetic
  - face_swap
  - face_morph
  - localized_edit
  - identity_altering_retouch

ambiguous:
  - unknown_edit
  - heavy_beauty_filter
```

Keep these splits separate:

- `train.csv`: model training
- `validation.csv`: model selection
- `calibration.csv`: calibrating probabilities
- `test_known.csv`: known attack sources
- `test_unseen_generator.csv`: generators/tools not seen during training

This last test is essential: NIST has reported that morph detector performance can drop sharply when evaluated against unfamiliar morph-generation software. 

Do not place the same identity in multiple splits. Also avoid making all genuine photos come from one dataset and all fake photos from another, because the model may learn dataset-specific shortcuts rather than manipulation evidence.

---

## 3. Core detection pipeline

The main orchestration belongs in:

```text
src/kyc_detector/inference/pipeline.py
```

The pipeline should run these steps:

```text
Upload
  ↓
Secure file validation
  ↓
Image decoding and normalization
  ↓
Face detection and quality checks
  ↓
Full-image and face-crop predictions
  ↓
Test-time consistency checks
  ↓
Probability calibration
  ↓
Uncertainty/OOD analysis
  ↓
Attribution heatmap
  ↓
Structured reason generation
  ↓
Verdict policy
  ↓
API response
```

### `predictor.py`

Responsibilities:

- Load model weights once
- Run image and face-crop predictions
- Return logits, not just labels
- Support CPU and GPU
- Include model version with every result

### `calibration.py`

Convert raw logits into a calibrated probability. Keep the calibration data separate from training data. Calibration curves and reliability diagrams should verify whether a reported probability can reasonably be interpreted as confidence. 

Store the fitted calibration parameters in:

```text
artifacts/calibration/temperature.json
```

### `uncertainty.py`

Calculate:

- Ensemble disagreement
- Prediction variation after safe resize/recompression transforms
- Out-of-distribution score
- Distance from decision thresholds
- Image quality uncertainty

### `policy.py`

Use abstention logic:

```python
if invalid_image or no_face or face_too_small:
    verdict = "unable_to_assess"
elif out_of_distribution or model_disagreement_is_high:
    verdict = "uncertain"
elif calibrated_fake_probability >= fake_threshold:
    verdict = "likely_fake"
elif calibrated_fake_probability <= real_threshold:
    verdict = "likely_real"
else:
    verdict = "uncertain"
```

Thresholds must come from `tune_thresholds.py`, not arbitrary values hardcoded into Python.

---

## 4. Explainability files

### `explain/attribution.py`

Generate an attribution map using a method such as Integrated Gradients or a layer-based attribution method. Captum provides PyTorch-compatible attribution methods and visualization utilities. 

### `explain/heatmap.py`

Create:

- Original image
- Colored attribution map
- Overlay image
- Normalized region scores

### `explain/signal_summary.py`

Convert actual measurements into structured explanations.

Example:

```json
{
  "code": "MODEL_FACE_BOUNDARY_SIGNAL",
  "direction": "toward_fake",
  "strength": 0.72,
  "message": "The visual classifier assigned substantial importance to the face and hair boundary.",
  "limitation": "Similar patterns can also be caused by background removal or image compression."
}
```

Do not generate unsupported statements such as:

- “The eyes prove this is fake.”
- “Missing EXIF means AI-generated.”
- “The skin is too perfect.”

Metadata absence and compression artifacts should normally be reported as **context**, not proof.

---

## 5. API files

FastAPI can receive uploaded images using `UploadFile` and `multipart/form-data`. 

Recommended endpoints:

```text
POST /v1/detect
GET  /v1/model-info
GET  /health
GET  /ready
```

Example API response:

```json
{
  "request_id": "8ae1bf1c-3a28-4f58-a850-53a65db12c17",
  "verdict": "uncertain",
  "fake_probability": 0.64,
  "confidence_level": "low",
  "uncertainty_score": 0.31,
  "capture_type": "selfie",
  "signals": [
    {
      "code": "VISUAL_MODEL_FAKE_SIGNAL",
      "direction": "toward_fake",
      "strength": 0.64,
      "message": "The visual classifier found patterns associated with manipulated images."
    },
    {
      "code": "MODEL_DISAGREEMENT",
      "direction": "toward_uncertain",
      "strength": 0.58,
      "message": "Predictions changed after resizing and JPEG recompression."
    },
    {
      "code": "METADATA_UNAVAILABLE",
      "direction": "neutral",
      "strength": 0.0,
      "message": "No trustworthy capture metadata was available. This is not evidence of manipulation."
    }
  ],
  "quality": {
    "face_found": true,
    "face_count": 1,
    "blur_score": 0.18,
    "face_resolution_ok": true
  },
  "heatmap_base64": "...",
  "warnings": [
    "The result is uncertain and should be manually reviewed.",
    "This detector does not verify liveness or identity ownership."
  ],
  "model_version": "kyc-detector-0.1.0"
}
```

Keep `fake_probability` and `confidence_level` separate:

- **Fake probability:** predicted class probability
- **Confidence level:** how reliable/stable that prediction appears

---

## 6. Secure upload handling

Implement upload protection in `core/security.py` and `utils/image_io.py`.

Required controls:

- Allow only JPEG and PNG initially
- Verify actual file signatures
- Do not trust the uploaded MIME type
- Limit file size
- Limit decoded pixel dimensions
- Reject corrupt or multi-frame files unless supported
- Generate your own temporary filenames
- Never use the uploaded filename as a storage path
- Store temporary files outside the public web directory
- Delete images immediately after inference by default
- Never log raw images or EXIF values containing PII

These controls follow OWASP’s defense-in-depth recommendations for upload endpoints. 

---

## 7. Evaluation files and metrics

`evaluation/metrics.py` should calculate:

- AUROC
- AUPRC
- Accuracy
- Precision and recall
- False-positive rate
- False-negative rate
- Confusion matrix
- True-positive rate at fixed false-positive rates

`evaluation/calibration_metrics.py` should calculate:

- Expected Calibration Error
- Brier score
- Reliability diagram

`evaluation/robustness.py` should test:

- JPEG compression
- Screenshots
- Resize and crop
- Blur
- Brightness changes
- Noise
- Metadata removal
- Social-media-style recompression

`evaluation/slices.py` should report results by:

- Real versus known fake
- Real versus unseen generator
- Selfie versus ID portrait
- Face size
- Image quality
- Attack type
- Demographic group, when you have appropriately consented labels

`report.py` should generate:

```text
artifacts/reports/evaluation.json
artifacts/reports/evaluation.md
artifacts/reports/confusion_matrix.png
artifacts/reports/calibration_curve.png
artifacts/reports/robustness.csv
```

---

## 8. Frontend requirements

The UI should display:

1. Image upload and preview
2. `Likely Real`, `Likely Fake`, `Uncertain`, or `Unable to Assess`
3. Calibrated probability
4. Confidence/uncertainty indicator
5. Signal explanations
6. Attribution heatmap
7. Image-quality warnings
8. Model version
9. Clear limitation and privacy notice

Use warning colors carefully:

- Green: likely real
- Red: likely fake
- Amber: uncertain
- Gray: unable to assess

Do not display “98% guaranteed fake.” Prefer:

> “Estimated manipulation probability: 0.82. Confidence: medium. The image should be manually reviewed.”

---

## Recommended Build Order

### Phase 1: Foundation

Create:

```text
README.md
THREAT_MODEL.md
pyproject.toml
.env.example
configs/
src/kyc_detector/core/
```

### Phase 2: Data pipeline

Create:

```text
data/manifests/
src/kyc_detector/data/
scripts/prepare_data.py
scripts/generate_splits.py
scripts/audit_dataset.py
```

### Phase 3: Baseline model

Create:

```text
src/kyc_detector/models/
scripts/train.py
scripts/evaluate.py
```

First prove the model can distinguish the classes before building the UI.

### Phase 4: Confidence and uncertainty

Create:

```text
inference/calibration.py
inference/uncertainty.py
inference/policy.py
scripts/calibrate.py
scripts/tune_thresholds.py
```

### Phase 5: Explanations

Create:

```text
explain/attribution.py
explain/heatmap.py
explain/signal_summary.py
```

### Phase 6: API

Create:

```text
api/main.py
api/schemas.py
api/routes/detect.py
api/routes/health.py
```

### Phase 7: Frontend

Create the React application and connect it to `/v1/detect`.

### Phase 8: Testing and deployment

Add:

```text
tests/
docker/
docker-compose.yml
.github/workflows/ci.yml
MODEL_CARD.md
SECURITY.md
```

Pin and lock the Python dependencies used for training and deployment. PyTorch notes that exact reproducibility is not guaranteed across releases, platforms, and hardware, so record the package versions, seeds, model-weight hash, configuration hash, and device information. 

---

## Definition of Done

The project is complete when:

- [ ] Valid JPEG/PNG uploads work.
- [ ] Dangerous, corrupt, huge, or unsupported uploads are rejected.
- [ ] No-face and low-quality images return `unable_to_assess`.
- [ ] The model supports genuine, generated, face-swap, morph, and edited images.
- [ ] Training, calibration, and test identities are separate.
- [ ] An unseen-generator test exists.
- [ ] The returned probability is calibrated.
- [ ] The system returns `uncertain` instead of forcing every result.
- [ ] Every result includes structured reason codes.
- [ ] A heatmap is displayed with a limitation notice.
- [ ] Metadata is never treated as proof by itself.
- [ ] False-positive and false-negative rates are documented.
- [ ] Robustness against compression, resizing, screenshots, and blur is measured.
- [ ] Uploaded images are not retained by default.
- [ ] Model version, threshold version, and calibration version are recorded.
- [ ] Unit, integration, security, and robustness tests pass.
- [ ] The API and frontend run through Docker.
- [ ] `MODEL_CARD.md`, `DATA_CARD.md`, and `THREAT_MODEL.md` are complete.
- [ ] The product clearly recommends manual review for uncertain or high-risk results.
