# FAREBI — Master Plan

**Status:** ACTIVE · **Version:** 1.0 · **Created:** 2026-09-05
**Authority:** This is the single coordinating plan for the project. Every sub-plan, every
implementation session, and every architectural decision resolves back to this document.

> **Rule of precedence.** When a sub-plan or a code change disagrees with `FAREBI.md`,
> `FAREBI.md` wins. If `FAREBI.md` is wrong, amend `FAREBI.md` first, then implement.

---

## 1. What this is

Farebi is a **KYC deepfake / manipulated-face risk signal service**. It takes a single
uploaded face image (and, later, a short capture sequence) and returns one of four verdicts:

| Verdict | Meaning |
| --- | --- |
| `likely_real` | Calibrated manipulation probability is below the low band. |
| `likely_fake` | Calibrated manipulation probability is above the high band. |
| `uncertain` | Inside the band, or out-of-distribution, or signals disagree. **Route to human review.** |
| `unable_to_assess` | Invalid, corrupt, no face, face too small, or unusable quality. |

**It is a risk signal, never an autonomous rejection engine.** NIST identity guidance is
explicit that automated media analysis must be combined with manual review and
capture/liveness controls. The product is designed so that "I don't know, here is exactly
why, a human will look" is a first-class output — not a failure state.

### The one-sentence thesis

> Do not build a deepfake classifier. Build a **signal factory** — a plugin harness that
> cheaply, honestly, and repeatedly decides which forensic signals survive the real KYC
> upload pipeline — and fuse the survivors into a calibrated, explainable probability with
> a statistically grounded `uncertain` band.

---

## 2. Source documents and how they reconcile

Two specification documents exist. They describe the same product from opposite ends, and
they disagree on directory layout. This section settles it.

| Document | What it actually specifies | Role |
| --- | --- | --- |
| `IDEA.md` | The **delivery shell**: repo layout, API contract, response schema, secure-upload controls, evaluation metrics, frontend requirements, docs, Docker, CI, Definition of Done. | Governs **what the product exposes** and **how it is shipped**. |
| `farebi plan.txt` | The **research engine**: 7 unconventional forensic signals with proof-of-concept code, the `Signal` plugin contract, the `KYCDegradation` simulator, the go/no-go harness, learned fusion with a conformal band, data sourcing, per-signal gotchas, and a 10-week plan. | Governs **how detection actually works** and **how we avoid fooling ourselves**. |

### The reconciliation decision

They are not competing layouts — they are **two runtimes over one codebase**. `IDEA.md`
describes the *serving* runtime. `farebi plan.txt` describes the *factory* runtime. The
merged architecture keeps both and adds the explicit boundary that neither document states:

```
   OFFLINE FACTORY  ──── produces ────▶  ARTIFACTS  ──── consumed by ────▶  ONLINE SERVING
   (scripts, harness)                   (versions,                          (api, inference)
                                         hashed)                                  │
   No request ever runs the                   │                                   │
   factory. No training job                   │                                   ▼
   ever imports the API.                      └──────── artifacts/ ────────▶ verdicts
```

**Concretely:**

- The package is named **`farebi`** (not `kyc_detector`). Every module in `IDEA.md`'s
  `src/kyc_detector/` maps 1:1 into `src/farebi/` — nothing is dropped. See §6.
- `farebi plan.txt`'s `signals/`, `harness/`, `fusion/` and the degradation simulator are
  promoted to **first-class packages** inside `src/farebi/`.
- `IDEA.md`'s `forensics/` package is **renamed to `signals/`** and becomes the plugin
  registry. Its five files (`face_locator`, `image_quality`, `metadata`, `frequency`,
  `compression`) become signal plugins plus one `capture/` preprocessing package.
- All thresholds, weights, calibration parameters, and model versions live in `artifacts/`
  and are referenced by the API at runtime. **Nothing is hardcoded.**

---

## 3. System architecture

### 3.1 Two runtimes

```
┌─────────────────────────────── OFFLINE FACTORY ───────────────────────────────┐
│                                                                               │
│  data/raw ─▶ degradation/ ─▶ data/processed ─▶ manifests ─▶ splits            │
│                    │                                                          │
│                    ▼                                                          │
│  signals/* (plugins) ─▶ harness/evaluate_signal ─▶ GO / NO-GO report          │
│                                    │                                          │
│                          surviving signals only                               │
│                                    ▼                                          │
│  fusion/ (LR + isotonic + conformal band) ─▶ thresholds + calibration         │
│                                    │                                          │
│  evaluation/ (metrics, robustness, slices, fairness) ─▶ reports               │
└──────────────────────────────────────────────────────────────────────────────┘
                                     │
                          artifacts/ (weights, temperature.json,
                          thresholds.json, fusion.pkl, model_registry.json)
                                     │
┌─────────────────────────────── ONLINE SERVING ───────────────────────────────┐
│  Upload ─▶ security ─▶ decode ─▶ capture (face + landmarks + quality)        │
│                                      │                                        │
│                                      ▼                                        │
│                          signals/* (parallel, preflight-gated)                │
│                                      │ features + applicability + quality     │
│                                      ▼                                        │
│                    fusion ─▶ p_fake ─▶ uncertainty ─▶ policy ─▶ verdict       │
│                                      │                                        │
│                          explain (heatmap + reason codes)                     │
│                                      ▼                                        │
│                          API response ─▶ delete image                         │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Online request lifecycle

```
Upload (multipart/form-data)
  ↓
[1]  Secure file validation        core/security.py + utils/image_io.py
       magic bytes, size cap, pixel cap, single-frame, self-generated temp name
  ↓
[2]  Decode + normalize            utils/image_io.py
  ↓
[3]  Face / landmark / quality     capture/  (MediaPipe Face Mesh, iris points)
       ── fails ──▶ unable_to_assess
  ↓
[4]  Signal preflight + run        signals/* (each declares min_requirements)
  ↓
[5]  Feature assembly              fusion/features.py
       quality-masked, missing-signal-imputed
  ↓
[6]  Calibrated probability        fusion/ (LR + isotonic → p_fake)
  ↓
[7]  Uncertainty / OOD             inference/uncertainty.py
       transform consistency, ensemble disagreement, OOD score, margin to band
  ↓
[8]  Attribution                   explain/attribution.py + heatmap.py
  ↓
[9]  Reason generation             explain/signal_summary.py (structured codes)
  ↓
[10] Verdict policy                inference/policy.py (band from artifacts/)
  ↓
[11] Response                      api/routes/detect.py
  ↓
[12] Delete image + temp files     (retention off by default)
```

---

## 4. Module organization

```text
D:\Farebi\
│
├── FAREBI.md                  ◀── THIS FILE. Primary plan. Read first, always.
├── PROGRESS.md                ◀── Living checklist. Updated every session.
├── PLANS/                     ◀── Sub-plans. Subordinate to FAREBI.md.
│
├── README.md  LICENSE  SECURITY.md  THREAT_MODEL.md
├── MODEL_CARD.md  DATA_CARD.md  RISK_REGISTER.md
├── .gitignore  .dockerignore  .env.example
├── pyproject.toml  uv.lock  Makefile  docker-compose.yml
│
├── IDEA.md                    (frozen source spec — delivery shell)
├── farebi plan.txt            (frozen source spec — research engine)
│
├── configs/                   app · labels · model · training · thresholds · signals
├── data/                      raw · interim · processed · manifests · splits
├── artifacts/                 models · calibration · reports · model_registry.json
├── scripts/                   prepare_data · generate_splits · audit_dataset
│                              train · calibrate · tune_thresholds · evaluate
│                              run_harness · export_model · smoke_test
├── docs/                      architecture · api · data_collection
│                              evaluation_protocol · deployment · limitations
│                              incident_response
├── monitoring/                drift.py · alerts.yaml · dashboard.json
├── docker/                    api.Dockerfile · web.Dockerfile · nginx.conf
├── .github/workflows/ci.yml
│
├── src/farebi/
│   ├── core/                  L0 — no internal deps
│   │   ├── config.py          pydantic-settings; env + configs/*.yaml
│   │   ├── constants.py
│   │   ├── logging.py         structlog; PII-safe by construction
│   │   ├── reason_codes.py    the canonical ReasonCode enum
│   │   ├── security.py        upload validation rules
│   │   └── seed.py
│   │
│   ├── utils/                 L0
│   │   ├── image_io.py        safe decode, magic-byte sniff, pixel caps
│   │   ├── hashing.py         sha256 for weights / configs / inputs
│   │   └── artifacts.py       versioned load/save of artifacts/
│   │
│   ├── capture/               L1 — from IDEA.md's forensics/face_locator + image_quality
│   │   ├── face_mesh.py       MediaPipe Face Mesh (468+10 iris points)
│   │   ├── landmarks.py       region ROI extraction (eyes, sclera, cheeks, forehead)
│   │   ├── quality.py         blur, exposure, face size, occlusion
│   │   └── capture.py         the Capture dataclass builder
│   │
│   ├── degradation/           L1 — KYCDegradation simulator
│   │   ├── kyc_pipeline.py    resize → JPEG → AWB jitter → blur → re-JPEG
│   │   └── replay.py          screen-replay simulation (moiré, gamut, glare)
│   │
│   ├── data/                  L1
│   │   ├── manifest.py        schema enforcement, attack_type taxonomy
│   │   ├── split.py           identity-disjoint AND source-grouped splits
│   │   ├── dataset.py
│   │   ├── transforms.py
│   │   └── validators.py      leakage + shortcut audits
│   │
│   ├── signals/               L2 — THE FACTORY. Plugins are leaves.
│   │   ├── base.py            Signal ABC, Capture, SignalOutput, ReasonCode
│   │   ├── registry.py        auto-discovery + tier/requirement metadata
│   │   ├── fft.py
│   │   ├── texture.py
│   │   ├── vit_clip.py        CLIP-ViT features + linear probe (UnivFD-style)
│   │   ├── prnu.py            sensor-noise presence
│   │   ├── replay_detect.py   moiré / gamut / specular — PRNU's required partner
│   │   ├── corneal.py         DELETED — harness-KILLED (KILL-01, AUC 0.544)
│   │   ├── chromatic_aberration.py   KEEP (AUC 0.884)
│   │   ├── rppg.py            POS/CHROM, video + still perfusion
│   │   ├── sss_active.py      active-illumination subsurface scattering
│   │   ├── scleral.py         vein topology / Murray's Law
│   │   ├── weather.py         submission-consistency signal
│   │   ├── metadata.py        EXIF — context only, never proof
│   │   └── geometry.py        DELETED — harness-KILLED (KILL-02, AUC 0.559)
│   │
│   ├── models/                L3
│   │   ├── backbone.py        CLIP-ViT frozen feature extractor
│   │   ├── classifier.py      linear probe / MLP head
│   │   ├── ensemble.py        MC-dropout + seed ensemble
│   │   ├── losses.py
│   │   └── registry.py
│   │
│   ├── fusion/                L3 — replaces hand-tuned weights
│   │   ├── features.py        assemble + quality-mask the feature vector
│   │   ├── fusion.py          ExplainableFusion: LR → isotonic calibration
│   │   ├── conformal.py       conformal UNCERTAIN band (target_error)
│   │   └── attribution.py     per-signal contribution → top drivers
│   │
│   ├── inference/             L4
│   │   ├── pipeline.py        the orchestrator (§3.2)
│   │   ├── predictor.py       loads weights once, returns LOGITS, CPU+GPU
│   │   ├── calibration.py     logits → calibrated p (temperature.json)
│   │   ├── uncertainty.py     disagreement, transform stability, OOD, margin
│   │   └── policy.py          4-way verdict from band + uncertainty
│   │
│   ├── explain/               L4
│   │   ├── attribution.py     Captum Integrated Gradients
│   │   ├── heatmap.py         original + map + overlay + region scores
│   │   └── signal_summary.py  measurements → structured reason codes
│   │
│   ├── api/                   L5
│   │   ├── main.py  dependencies.py  schemas.py
│   │   ├── worker.py          Celery/Redis for slow signals (rPPG, MC-dropout)
│   │   └── routes/            detect.py  health.py  model_info.py
│   │
│   ├── monitoring/            L5
│   │   └── drift.py           score + coverage drift per signal
│   │
│   ├── evaluation/            OFFLINE ONLY — never imported by api/
│   │   ├── metrics.py  calibration_metrics.py  robustness.py
│   │   ├── slices.py  fairness.py  report.py
│   │
│   └── harness/               OFFLINE ONLY — THE ARBITER
│       ├── evaluate_signal.py cross-source AUC, coverage, per-feature AUC
│       ├── splits.py          GroupKFold by source group
│       ├── gono.py            KEEP / BENCH / KILL rule
│       └── report.py          one report per signal per dataset version
│
├── tests/
│   ├── conftest.py   fixtures/
│   ├── unit/         image_validation · calibration · uncertainty · policy
│   │                 signal_summary · contract
│   ├── integration/  detect_api · inference_pipeline
│   ├── security/     upload_security
│   ├── robustness/   jpeg_recompression · resize_crop · blur_noise
│   └── harness/      golden go/no-go regression
│
└── frontend/                  React + Vite + TS
    └── src/  api/  types/  components/  styles/
        components: UploadPanel · ResultCard · ProbabilityBar · SignalList
                    HeatmapViewer · UncertaintyBanner · PrivacyNotice · DriverList
```

---

## 5. The Signal contract — the spine of the system

Every detection idea, conventional or exotic, is **a plugin behind one interface**. This is
the single most important design decision in the project: it is what lets us add a signal
in a day, measure it in an hour, and delete it without emotional cost.

```python
@dataclass
class Capture:
    """Everything the server knows about one submission."""

    image_bgr: np.ndarray  # full, decoded, EXIF-orientation-corrected
    face_box: tuple  # (x1, y1, x2, y2)
    landmarks: np.ndarray  # MediaPipe 478×3 — includes iris points
    quality: dict  # blur, exposure, face_px, eye_px, iou
    video_frames: list | None = None
    fps: float | None = None
    sdk_meta: dict = field(default_factory=dict)  # GPS/time/device from OUR SDK, not EXIF
    capture_type: str = "selfie"  # selfie | id_photo | unknown


@dataclass
class SignalOutput:
    features: dict[str, float]  # raw numbers → the learned fusion. NEVER a verdict.
    applicable: bool  # False if eyes too small / no video / no GPS
    quality: float  # 0–1: how trustworthy these features are ON THIS input
    explanation: str  # human-readable, cites the actual features
    reason_codes: list[ReasonCode]  # structured, with direction + limitation
    artifacts: dict = field(default_factory=dict)  # crops, spectra, waveforms for the UI


class Signal(ABC):
    name: str
    tier: int  # 1 = build first, 2 = needs video/active, 3 = conditional
    min_requirements: dict = {}  # e.g. {"min_eye_px": 40, "needs_video": True}
    requires: list[str] = []  # companion signals (e.g. prnu requires replay_detect)

    def preflight(self, cap: Capture) -> bool: ...  # cheap applicability check
    @abstractmethod
    def run(self, cap: Capture) -> SignalOutput: ...
```

### Rules the contract enforces

1. **Signals output features, not verdicts.** A signal never says "fake". It says
   "cheek/chin green ratio = 0.97, region micro-variance = 4.2". The fusion decides.
2. **A signal never imports another signal.** Signals are leaves. If two signals need the
   same ROI extraction, that code moves to `capture/`.
3. **Every signal declares `applicable` and `quality`.** Coverage is a first-class metric.
4. **Every signal ships an `explanation` and `reason_codes` with a `limitation` field.**
   "Similar patterns are also caused by background removal or JPEG compression."
5. **Every signal must survive the harness or be deleted** (§7).

---

## 6. Dependency graph and layering

```
        L6  frontend ─────────────── HTTP only ─────────────┐
                                                            │
        L5  api ─────────────┬────────── monitoring         │
                             │                              │
        L4  inference ─── explain ─── policy                │
                             │                              │
        L3  models ───────── fusion                         │
                             │                              │
        L2  signals/*  ←── plugins are LEAVES, mutually independent
                             │
        L1  capture ─ degradation ─ data
                             │
        L0  core ─ utils
                                                            │
     OFFLINE ONLY:  harness ─┐                              │
                    evaluation ─┴─ (L1..L4)  ◀── never imported by api
```

| Layer | May import | Must never import |
| --- | --- | --- |
| L0 `core` `utils` | stdlib, third-party | anything internal |
| L1 `capture` `degradation` `data` | L0 | L2+ |
| L2 `signals/*` | L0, L1 | **other signals**, L3+ |
| L3 `models` `fusion` | L0–L2 | L4+ |
| L4 `inference` `explain` `policy` | L0–L3 | L5 |
| L5 `api` `monitoring` | L0–L4 | `harness`, `evaluation` |
| L6 `frontend` | HTTP only | — |
| OFFLINE `harness` `evaluation` | L0–L4 | `api` |

**CI enforces this.** A lint rule fails the build on any `signals/x.py` importing
`signals/y.py`, and on any `api/` import of `harness` or `evaluation`.

---

## 7. The go/no-go gate

The harness decides which signals live. Split by **source group** (generator family /
camera set), never randomly — a random split leaks generator fingerprints and produces a
0.98 AUC that collapses to 0.55 on the first new model a fraudster adopts.

```python
evaluate_signal(signal, samples) -> {
    "signal", "coverage",          # how often it can even run
    "cross_source_auc",            # GroupKFold AUC — the honest number
    "auc_std",                     # high std = generator-specific = fragile
    "per_feature_auc",             # which feature actually carries the signal
}
```

| Outcome | Rule | Action |
| --- | --- | --- |
| **KEEP** | `cross_source_auc ≥ 0.65` **AND** `coverage ≥ 0.50` | Promoted into fusion features. |
| **BENCH** | `auc ≥ 0.60`, coverage low | Conditional signal. Fires only when applicable; quality-gated. |
| **KILL** | `auc < 0.60` after degradation | Deleted. The physics was right; the pipeline killed it. |

**The two-day rule.** Never spend more than two days on a signal before running it through
the harness. The harness decides, not you, and not the elegance of the idea.

---

## 8. The artifacts contract (offline → online interface)

The API reads **only** from `artifacts/`. It never trains, never tunes, never guesses.

| Artifact | Produced by | Contains | Version key |
| --- | --- | --- | --- |
| `artifacts/models/*.pt` | `scripts/train.py` | backbone + head weights, sha256 | `model_version` |
| `artifacts/calibration/temperature.json` | `scripts/calibrate.py` | temperature / isotonic params | `calibration_version` |
| `artifacts/thresholds.json` | `scripts/tune_thresholds.py` | conformal band `q_lo`, `q_hi`, OOD cutoffs | `threshold_version` |
| `artifacts/fusion.pkl` | `scripts/train.py` | fitted `ExplainableFusion` + feature names | `fusion_version` |
| `artifacts/signal_registry.json` | `scripts/run_harness.py` | KEEP/BENCH/KILL per signal with AUC | `registry_version` |
| `artifacts/model_registry.json` | — | package versions, seeds, config hash, device | — |

Every API response echoes `model_version`, `threshold_version`, and `calibration_version`.
A production result must be reproducible from those three keys alone.

---

## 9. Verdict policy

`inference/policy.py`. Thresholds are loaded from `artifacts/thresholds.json` — never
hardcoded.

```python
if invalid_image or no_face or face_too_small or quality_unusable:
    verdict = "unable_to_assess"
elif ood_score > ood_cutoff or disagreement > disagreement_cutoff:
    verdict = "uncertain"  # model is not entitled to an opinion
elif p_fake >= q_hi:
    verdict = "likely_fake"
elif p_fake <= q_lo:
    verdict = "likely_real"
else:
    verdict = "uncertain"  # inside the conformal band
```

`q_lo` / `q_hi` come from conformal calibration on a held-out calibration split:

> Find `q_lo` = the largest `t` such that `P(fake | p < t) ≤ target_error` (default 0.05),
> and `q_hi` = the smallest `t` such that `P(real | p > t) ≤ target_error`.

This is what lets us say to a compliance officer: *"when we say `likely_real`, we are wrong
at most 5% of the time on held-out data from generators we never trained on."* The
`uncertain` rate is a tunable business parameter — automation vs. human review — not an
accident.

**`fake_probability` and `confidence_level` are separate fields and always will be.**
Probability is the predicted class probability; confidence is how stable and reliable that
prediction appears. The UI must never render "98% guaranteed fake". It renders:

> Estimated manipulation probability: 0.82. Confidence: medium. This image should be
> manually reviewed.

---

## 10. Data strategy

Four rules. Break any of them and every number the project produces is a lie.

1. **Degrade everything, identically.** A fake that arrives as a pristine PNG and a real
   that arrives as a JPEG teaches the model "PNG = fake". Apply `KYCDegradation` to *both*
   classes: resize to 720–1280 long edge → JPEG q80–95 → AWB/exposure jitter → optional
   blur → second JPEG q70–90 (the killer). Calibrate the ranges against real uploads.
2. **Split by identity AND by source group.** No identity appears in two splits. Hold out
   **at least one entire generator** (e.g. all Flux images) that never touches training.
   The headline number is AUC on that generator.
3. **No dataset shortcuts.** Do not let all reals come from one source and all fakes from
   another. Strip EXIF from training data by default; keep metadata as a separate,
   tiny-weight signal — otherwise you are training a metadata detector by accident.
4. **Collect your own reals.** Public datasets do not look like your uploads. 200–500
   consenting people, many phones, indoor/outdoor, through the actual app, including
   glasses, makeup, beauty filters, and dark rooms — that is the false-positive population.

### Splits

| Split | Purpose |
| --- | --- |
| `train.csv` | Model training and fusion fitting |
| `validation.csv` | Model selection |
| `calibration.csv` | Probability calibration + conformal band — **never trained on** |
| `test_known.csv` | Known attack sources |
| `test_unseen_generator.csv` | Generators/tools absent from training. **The honest number.** |

### Sources

| Need | Sources |
| --- | --- |
| Real (baseline) | FFHQ, CelebA-HQ, VGGFace2 — still degraded |
| Real (critical) | Own captures, 200–500 consenting people, ≥20 phone models |
| GAN fakes | Self-generated StyleGAN2/3, varied truncation ψ |
| Diffusion fakes | SD 1.5 / SDXL / Flux, KYC-style prompts ("passport photo, plain background") |
| Face swaps | FaceForensics++, Celeb-DF v2, DFDC + fresh InSwapper/SimSwap/roop |
| Replay attacks | Photograph fakes off screens; virtual-camera injection |
| rPPG validation | UBFC-rPPG, PURE, COHFACE — validate HR before trusting the signal |
| PRNU validation | VISION, Dresden Image Database |

### Manifest schema

`binary_label` alone is not enough. Every row carries
`image_path, binary_label, attack_type, source_dataset, generator_family, identity_id,
capture_type, split`. Attack-type taxonomy:

```yaml
real:                  [authentic, authentic_benign_processed]
fake_or_manipulated:   [fully_synthetic, face_swap, face_morph, localized_edit,
                        identity_altering_retouch]
ambiguous:             [unknown_edit, heavy_beauty_filter]
```

---

## 11. Signal portfolio

Six conventional signals + seven unconventional + replay detection. **Expect only 4–6 to
survive the harness. That is a win** — diversity of survivors matters far more than count.

First harness run (quick256, n=407, degraded-mode, `n_splits=2`, 2026-09-05):
**5 KEEP, 2 KILL, 1 environmental.** Verdicts are recorded per-row below;
kill reasons live in `RISK_REGISTER.md`.

| # | Signal | Tier | Module | Known risk / mitigation · **harness verdict** |
| --- | --- | --- | --- | --- |
| 1 | Frequency domain (FFT) | 1 | `signals/fft.py` | Generator-specific; low ψ vs high ψ differ · **KEEP (AUC 0.730)** |
| 2 | Texture & spatial artifacts | 1 | `signals/texture.py` | Dies under heavy JPEG — measure, don't assume · **KEEP (AUC 0.875)** |
| 3 | CLIP-ViT linear probe | 1 | `signals/vit_clip.py` | Overfits training generators; prefer frozen CLIP features · **ENVIRONMENTAL KILL (no torch/weights) — file kept as Phase-06 re-entry slot** |
| 4 | PRNU sensor-noise presence | 1 | `signals/prnu.py` | **Does not prove the face is real** — a screen replay has genuine PRNU. Requires #5. · **KEEP (AUC 0.907)** — must be re-validated on laundered fakes before the Phase-04 gate closes |
| 5 | Screen-replay detection | 1 | `signals/replay_detect.py` | Moiré (FFT peak at pixel pitch), display gamut, specular rectangle, flat depth · **KEEP (AUC 0.862)** |
| 6 | Corneal reflection consistency | 1 | ~~`signals/corneal.py`~~ | Needs eye ≥ 40px — solve with capture UX ("move closer"), not code · **KILLED (AUC 0.544, KILL-01) — premise dead on real portraits, file deleted** |
| 7 | Chromatic aberration | 1 | `signals/chromatic_aberration.py` | Modern ISPs correct CA aggressively; may be weak. Run on full frame. · **KEEP (AUC 0.884)** — re-validate on high-res before the gate closes |
| 8 | rPPG video pulse (POS/CHROM) | 2 | `signals/rppg.py` | Needs ≥5s at ≥20fps; **SNR drops on darker skin — fairness-tested, weight-gated** |
| 9 | Active-illumination SSS | 2 | `signals/sss_active.py` | Dark→bright frame pair 100ms apart; also defeats replay (random color sequence) |
| 10 | rPPG still perfusion map | 3 | `signals/rppg.py` | Weakest of the set; low expectations, ready to kill |
| 11 | Scleral vein topology | 3 | `signals/scleral.py` | Needs eye crop ≥80px → low coverage. Quality-gated bonus. |
| 12 | Weather witness | 3 | `signals/weather.py` | EXIF GPS is stripped by browsers — take GPS/time from **our SDK**. Indoor/outdoor gate first. |
| 13 | EXIF / metadata forensics | 3 | `signals/metadata.py` | **Context, never proof.** Absence of EXIF proves nothing. |
| 14 | Facial geometry / iris consistency | 1 | ~~`signals/geometry.py`~~ | Landmark noise on low-res · **KILLED (AUC 0.559, KILL-02) — file deleted** |

**Active illumination is the unfair advantage.** We control the capture app. Flashing
screen-dark → screen-bright 100ms apart isolates our own light source, cancels ambient
light, and converts three weak passive signals (SSS, corneal, 3D shape) into strong active
ones. A random colour sequence on top defeats pre-recorded and injected video outright.

---

## 12. Phases, gates, and sub-plans

Each phase has exactly one exit gate. **Do not start the next phase until the gate passes.**

| # | Phase | Sub-plan | Exit gate |
| --- | --- | --- | --- |
| 0 | Foundation: repo, config, security, capture | `PLANS/01-foundation.md` | One image traverses an empty pipeline end-to-end |
| 1 | Signal factory: contract, registry, degradation, harness | `PLANS/02-signal-factory.md` | Harness runs and reports KEEP/BENCH/KILL on a stub signal |
| 2 | Data: loaders, manifests, splits, leakage audit, self-capture | `PLANS/03-data.md` | Identity-disjoint + source-grouped splits; 300+ real self-captures |
| 3 | Tier-1 signals | `PLANS/04-signals-tier1.md` | Baseline cross-source AUC reported (expect 0.75–0.85, **not** 0.99); ≥2 of PRNU/corneal/CA survive |
| 4 | Tier-2 signals: video rPPG + active illumination | `PLANS/05-signals-tier2.md` | HR error <5 BPM on UBFC; replay AUC ≥ 0.90 |
| 5 | Tier-3 conditional signals | `PLANS/06-signals-tier3.md` | Each has a harness report; kept or killed on evidence |
| 6 | Fusion, calibration, conformal band, policy, explainability | `PLANS/07-fusion-uncertainty.md` | `uncertain` rate ≤15% at 5% target error on the held-out generator |
| 7 | API + worker queue | `PLANS/08-api-frontend.md` | Valid uploads scored; hostile uploads rejected; no retention |
| 8 | Reviewer frontend | `PLANS/08-api-frontend.md` | A non-technical person can read a report and agree or disagree |
| 9 | Evaluation, fairness, robustness, governance docs | `PLANS/09-evaluation-governance.md` | No demographic bucket has FPR > 1.5× overall |
| 10 | Monitoring, drift, retraining playbook | `PLANS/10-monitoring.md` | Dashboard live; weekly harness re-run automated |

`PLANS/00-index.md` is the registry and status board for all of the above.

---

## 13. External dependencies

| Layer | Packages |
| --- | --- |
| Serving | `fastapi`, `uvicorn[standard]`, `pydantic`, `pydantic-settings`, `celery`, `redis`, `python-multipart` |
| Vision | `opencv-python-headless`, `numpy`, `scipy`, `pillow`, `mediapipe` (iris landmarks — chosen over dlib) |
| ML | `torch`, `torchvision`, `open-clip-torch` (frozen CLIP-ViT features), `scikit-learn`, `pandas` |
| Explainability | `captum` (Integrated Gradients), `shap` (fusion attributions) |
| Signal-specific | `pyVHR` (POS/CHROM rPPG — validate, then reimplement), `scikit-image` (vessel skeletonisation, Murrays' Law), `astral` (solar position) |
| Observability | `structlog`, `prometheus-client` |
| Quality | `pytest`, `pytest-cov`, `ruff`, `mypy`, `hypothesis` |
| Tooling | `uv` (locked via `uv.lock`), `make`, Docker |
| Frontend | `react`, `react-dom`, `vite`, `typescript`, `vitest` |

**All versions pinned in `uv.lock`.** PyTorch does not guarantee bit-exact reproducibility
across releases, platforms, or hardware — so every run records package versions, seeds,
model-weight hash, config hash, and device info into `artifacts/model_registry.json`.

---

## 14. Non-negotiables

These are constitutional. A change that violates one of these is rejected in review,
regardless of how good it looks.

1. **Every signal is a plugin.** No signal imports another signal. Shared code goes to `capture/`.
2. **Signals emit features, never verdicts.** Fusion owns the decision.
3. **No hardcoded thresholds.** All come from `artifacts/` and are versioned.
4. **Metadata is context, never proof.** Missing EXIF is not evidence of manipulation.
5. **Degradation applies to real and fake identically**, always, in training.
6. **Splits are identity-disjoint and source-grouped.** At least one generator fully held out.
7. **No upload retention by default.** Images deleted immediately after inference.
8. **Four verdicts.** `uncertain` is a product feature, not an apology.
9. **Every signal reports `applicable` and `quality`.** Coverage is measured, not assumed.
10. **Every response carries model, threshold, and calibration versions.**
11. **No signal ships without a harness report.**
12. **Every heatmap ships with a limitation notice.**
13. **Fairness is a legal requirement, not a nice-to-have.** FPR measured per Fitzpatrick
    bucket, age, glasses, and makeup. If a signal is uneven across skin tones, down-weight
    it via `quality` for low-SNR captures — never let it silently reject people.
14. **Never log raw images or EXIF values containing PII.**

---

## 15. Definition of Done

Tracked live in `PROGRESS.md`. Summary of the bar:

**Correctness** — valid JPEG/PNG upload and score; hostile, corrupt, oversized, and
unsupported uploads rejected; no-face and low-quality inputs return `unable_to_assess`;
the model handles genuine, generated, face-swap, morph, and edited images; training,
calibration, and test identities are disjoint; an unseen-generator test exists and is the
headline number.

**Honesty** — probability is calibrated; `uncertain` exists and is returned; every result
carries structured reason codes; heatmaps carry limitation notices; metadata is never
treated as proof; FPR and FNR are documented; robustness to compression, resizing,
screenshots, and blur is measured; fairness slices are published.

**Operations** — uploads not retained by default; model/threshold/calibration versions
recorded; unit, integration, security, and robustness tests pass; API and frontend run
under Docker; `MODEL_CARD.md`, `DATA_CARD.md`, `THREAT_MODEL.md`, and `RISK_REGISTER.md`
are complete; the product visibly recommends manual review for uncertain or high-risk
results.

---

## 16. Working conventions

- **Start every session** by reading `FAREBI.md` (this file) and `PROGRESS.md`.
- **End every session** by updating `PROGRESS.md` — tick what shipped, note what blocked.
- **A phase's sub-plan is the detailed spec.** This file is the coordination layer; sub-plans
  hold file-level detail. Neither may contradict the other.
- **When adding a signal:** write the plugin → run it through the harness → accept the
  verdict → only then wire it into fusion.
- **When in doubt, prefer the number over the narrative.** The harness exists because
  intuition about deepfake signals is reliably overconfident.

---

## 17. Reference repositories & papers (clone-first map)

FAREBI.md specifies *what* to build but not *where the existing code is*. The following is
the desk-research map from the project brainstorm. Use it to skip re-implementing loaders,
metrics, and baselines. **Check the last-commit date before building on anything** — the
DeepfakeBench original environment is Python 3.7 and must be swapped for an upversioned fork.

### Tier 1 — clone first (saves weeks)

| What | Repo / paper | Why |
| --- | --- | --- |
| Go/no-go harness already built | `SCLBD/DeepfakeBench` — 20 spatial detectors, 9 datasets, frame/video AUC. Newest detector: "Orthogonal Subspace Decomposition for Generalizable AI-Generated Image Detection" (ICML 2025 Spotlight) | Closest thing to our harness. **Use its loaders + metrics; add our physics signals as plugins.** Original env is Py3.7 → use fork `alexsabb/CVDeepfakeBench` (PyTorch 2.x, CUDA 12). |
| CPU-friendly neural baseline | `WisconsinAIVision/UniversalFakeDetect` (UnivFD, CVPR 2023) — CLIP embeddings + linear probe / kNN, cross-generator | Exactly the frozen-CLIP + logistic-probe approach in §11/#3. Follow-ups: FatFormer (CVPR 2024), C2P-CLIP (AAAI 2025), "CLIPping the Deception", "Forensics Adapter" (CVPR 2025). A zero-shot variant trained *only on real images* aligns with the physics-signal philosophy. |
| PRNU code, ready to use | `polimi-ispl/prnu-python` (canonical Binghamton port) | Use its `extract_noise()`. Variants: `sim-pez/prnu` (VDNet/VDID denoisers), `E0HYL/CameraFingerprint_pytorch` (DnCNN/FFDNet, multi-GPU), `Noiseprint` (learned PRNU alt). **Read `frassom/prnu-copy-attack` for the adversarial week — it is how an attacker defeats PRNU.** |

### Tier 2 — papers that validate the exotic signals

- **Corneal** — Hu, Li, Lyu, "Exposing GAN-generated Faces Using Inconsistent Corneal
  Specular Highlights" (ICASSP 2021, arXiv 2009.11924); project page
  `cse.buffalo.edu/ubmdfl/projects/GAN_detect_iris`. A 2024–25 two-branch follow-up adds
  pupil segmentation + binocular specular comparison. **Caveat: portrait setting only; the
  signal is weaker on diffusion-eyes — test on a held-out diffusion generator before trusting
  any published AUC.**
- **rPPG** — `BiDAlab/DeepFakesON-Phys` (≥98% AUC on Celeb-DF/DFDC); `rPPG-Toolbox`
  (NeurIPS 2023); `pyVHR`. Foundational papers: "DeepFakes Have No Heart" (ICIAP 2022, most
  explainable), FakeCatcher (TPAMI 2020), DeepRhythm (ACM MM 2020, poor on DFDC Preview).
  **Honest failure mode: handcrafted rPPG is fragile against external illumination whose
  frequency/power aliases into the 1–3 Hz heart-rate band (flickering 50/60 Hz LEDs).** Survey:
  arXiv 2301.05819.
- **Frequency / CA / SSS / scleral / weather** source papers (no maintained repo — build from these):
  - Chromatic aberration → Johnson & Farid, "Exposing Digital Forgeries Through Chromatic
    Aberration" (ACM MM&Sec 2006); Gloe et al. on lateral CA.
  - Subsurface scattering → Jensen et al. 2001 dipole BSSRDF; Donner & Jensen skin models
    (no detector paper uses SSS for deepfakes — **may be genuinely novel territory**).
  - Scleral veins → Zhou, Du et al. biometrics; SBVPI dataset for segmentation.
  - Weather/lighting consistency → Kee, O'Brien & Farid, "Exposing Photo Manipulation with
    Inconsistent Shadows"; Johnson & Farid 2007. **Farid's lab is the source for most
    physics-based forensics — search the publication page.**
  - Frequency artifacts → Durall et al. "Watch your Up-Convolution" (CVPR 2020); Frank et al.
    "Leveraging Frequency Analysis" (ICML 2020, has repo); NPR (CVPR 2024).

### Tier 3 — curated indexes (for everything else)

- `Daisy-Zhang/Awesome-Deepfakes-Detection` — most complete index; dedicated bio-signals and
  frequency-domain sections.
- `flyingby/Awesome-Deepfake-Generation-and-Detection` — companion to a 2026 ACM Computing
  Surveys paper; useful for expected AUC benchmarks.
- `qiqitao77/Awesome-Comprehensive-Deepfake-Detection` — best dataset table (Celeb-DF++ 2025,
  Moiré-against-screen-replay benchmark — directly relevant to #5 replay detection).
- `Purdue-M2/AI-Face-FairnessBench` — for the §9 fairness audit; ships UnivFD, F3Net, SRM,
  SPSL plus fairness-specific detectors DAW-FDD / DAG-FDD / PG-FDD with checkpoints.

---

## 18. Threat landscape (seed for THREAT_MODEL.md / RISK_REGISTER.md)

The plan references NIST guidance and capture controls but never states the *business* threat.
These figures justify the project and belong in the governance docs:

- **Deloitte Center for Financial Services**: generative-AI fraud losses in the US projected at
  **$40B by 2027**, up from **$12.3B in 2023**.
- An AI-generated face capable of passing many verification systems now costs **under $20**
  with **~30 minutes** of setup.
- Crime-as-a-service kits (e.g. **ProKYC**) package deepfake video + forged documents as a
  subscription — the capability is commoditized.
- Deepfake attacks are up **>2000% over three years** and now account for roughly **1 in 15**
  identity-fraud attempts.
- **FATF Horizon Scan on AI and Deepfakes (Dec 2025)** names deepfakes a direct threat to
  AML/CDD controls worldwide.

**Out-of-band defense (missing from §11):** a perfect image detector is useless if the fraudster
bypasses the camera. Mandate **device attestation (Play Integrity / App Attest)** and
**virtual-camera detection in the SDK** as capture-layer controls, not optional extras. Injection
attacks that feed synthetic video straight into the verification API must be caught at the device
layer, not the pixel layer.

---

## 19. Resource-constrained execution (small-AI / powerful-AI split)

The build was scoped under a tight token/compute budget. The rule that makes it feasible: the
**powerful AI writes what is hard to get right and cheap to read; the small AI writes what is
easy to specify and cheap to test.** A task gets a test before implementation → small AI; a task
is "why is this broken" or "what to do" → powerful AI.

**Powerful AI only (~20% of calls, 80% of value):**
Signal contract + `Capture` dataclass + harness (once); one-page spec per signal;
`KYCDegradation` parameter ranges; interpret harness reports ("AUC 0.61 / std 0.18 → keep/fix/kill?");
debug physics-level bugs (NaN correlations, landmark off-by-one); fusion + calibration + conformal
math; fairness interpretation; one-pass diff review of each merged signal.

**Small AI (everything mechanical, ~80% of calls, cheap):**
implement each signal plugin from the spec against the contract; write unit tests from the
edge-case list; dataset loaders, degradation-on-load, fake-generation scripts; docstrings, CLI,
plotting, markdown reports; FastAPI/Pydantic/Dockerfile; Streamlit reviewer UI; mechanical
refactors; first-pass fixes when a test names the failure (cap **2 attempts**, then escalate).

**Handoff artifact — one spec sheet per signal.** Stored in `specs/`. The powerful AI writes it
once (~600 tokens); the small AI reads it many times. Template: contract reference + applicability
conditions + `quality` formula + feature keys with expected real/fake ranges + numbered algorithm
+ edge-case → required behaviour + tests the implementation must pass + **kill criteria** (e.g.
`cross_source_auc < 0.60` OR `coverage < 0.40` → DEAD in `reports/`).

**Token protocol (do not violate):**
- Never paste whole files or long chat history to the powerful AI. Send exactly one of: the
  signal idea + link to contract; the JSON harness report (~200 tokens) + "keep/fix/kill?"; the
  failing test name + assertion + ≤30 lines; or the git diff of one file with the spec name.
- Always give the small AI `core/contract.py` + `specs/<name>.md` and ask for **complete files**,
  not patches. Keep the powerful-AI context short — fresh session per signal.
- Rough powerful-AI budget for the whole build: **~50–60k tokens**; everything else is small-AI or free.

**Guardrail that costs zero tokens:** an automated `tests/test_contract_compliance.py` runs
against every signal and catches ~80% of small-model mistakes — NaN leakage, exceptions on
garbage input, numpy scalars / None breaking JSON serialization, and nondeterminism (missing
seeds). It asserts `0.0 ≤ quality ≤ 1.0`, all features finite floats, `applicable=False` on
garbage, and `features` identical across two runs.
