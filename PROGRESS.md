# PROGRESS — Living Checklist

**Parent plan:** [`FAREBI.md`](./FAREBI.md) · **Sub-plans:** [`PLANS/00-index.md`](./PLANS/00-index.md)
**Last updated:** 2026-09-05

## How to use this file

- Tick `[x]` **only** when the item genuinely passes. `[~]` means partially done / WIP.
- Every tick corresponds to an exit-gate condition in the owning sub-plan. If you cannot point
  to the evidence, it is not done.
- **Update this file at the end of every working session** — tick what shipped, note what
  blocked, bump "Last updated".
- When you tick an item that changes architecture, amend `FAREBI.md` first.

### Legend

`[x]` Done · `[~]` In progress · `[ ]` Not started · `[!]` Blocked

---

## Phase 00 — Planning & architecture

- [x] Read and analyse `IDEA.md` (delivery shell: API contract, upload security, evaluation, frontend, DoD)
- [x] Read and analyse `farebi plan.txt` (7 unconventional signals, Signal contract, degradation, harness, fusion, 10-week plan)
- [x] Reconcile the two conflicting directory layouts into one architecture
- [x] Write `FAREBI.md` — master plan (architecture, modules, layering, contract, policy, gates, non-negotiables)
- [x] Write `PLANS/00-index.md` — sub-plan registry with critical path
- [x] Write `PLANS/01-foundation.md`
- [x] Write `PLANS/02-signal-factory.md`
- [x] Write `PLANS/03-data.md`
- [x] Write `PLANS/04-signals-tier1.md`
- [x] Write `PLANS/05-signals-tier2.md`
- [x] Write `PLANS/06-signals-tier3.md`
- [x] Write `PLANS/07-fusion-uncertainty.md`
- [x] Write `PLANS/08-api-frontend.md`
- [x] Write `PLANS/09-evaluation-governance.md`
- [x] Write `PLANS/10-monitoring.md`
- [x] Create `PROGRESS.md` (this file)

**Gate:** plan complete and internally consistent → **PASSED**

---

## Phase 01 — Foundation · [`PLANS/01`](./PLANS/01-foundation.md)

- [x] `pyproject.toml` + `uv.lock` + `Makefile` + `configs/`
- [x] `core/` — config, constants, logging (PII-safe), reason_codes, security, seed
- [x] `utils/` — image_io, hashing, artifacts
- [x] `capture/` — face_mesh (MediaPipe, iris points), landmarks, quality, capture
- [x] Empty `inference/pipeline.py` with full type signatures
- [x] `scripts/smoke_test.py` + `scripts/fetch_face_landmarker.py`
- [x] Import-linter enforces layering (no `signals→signals`, no `api→harness|evaluation`)
- [x] Hostile upload rejection: wrong magic bytes, oversized file, oversized dimensions, corrupt, multi-frame
- [x] No image bytes or EXIF values in logs (test-asserted)
- [x] `README.md` documents install + smoke test

**Gate:** one image traverses an empty pipeline end-to-end → `[x]` PASSED
(evidence: `pytest -m "not slow"` 167 passed; `ruff check`/`ruff format --check`/
`mypy --strict`/`importlinter` all clean; `scripts/smoke_test.py` →
`SMOKE TEST PASSED`, 9 distinct rejection codes)

---

## Phase 02 — Signal factory · [`PLANS/02`](./PLANS/02-signal-factory.md)

- [x] `signals/base.py` — `Capture`, `SignalOutput`, `Signal` ABC, `require()`, `reason()`
- [x] `signals/registry.py` — auto-discovery, tier/requirement metadata, harness-status gate
- [x] `degradation/kyc_pipeline.py` — resize → JPEG → AWB → blur → re-JPEG, seeded
- [x] `degradation/replay.py` — screen-replay simulation
- [x] `harness/splits.py` — GroupKFold by source group
- [x] `harness/evaluate_signal.py` — coverage, cross_source_auc, auc_std, per_feature_auc
- [x] `harness/gono.py` — KEEP / BENCH / KILL
- [x] `harness/report.py` + `scripts/run_harness.py`
- [x] Stub weak signal reported as KILL; stub strong signal reported as KEEP (tested)
- [x] `configs/signals.yaml` blocks a `kill`-status signal from fusion (tested)

**Gate:** harness runs and correctly arbitrates a stub signal → `[x]` PASSED
(evidence: `pytest tests/harness/test_gono.py` → noise=KILL, partial=BENCH,
encoded=KEEP; `pytest tests/unit/test_registry.py` → `kill`/`unmeasured` excluded
from `all_enabled()`; `python scripts/run_harness.py --self-test` prints the same
three verdicts. Full suite `pytest -m "not slow"` → 174 passed, 0 failed.)

---

## Phase 03 — Data · [`PLANS/03`](./PLANS/03-data.md)

- [ ] `data/manifests/schema.json` + `sample_manifest.csv`
- [ ] `data/` loaders: manifest, split, dataset, transforms, validators
- [ ] Shortcut audit: identity leakage, source/class confounding, format confounding,
      metadata confounding, duplicates, resolution confounding
- [ ] `scripts/prepare_data.py`, `generate_splits.py`, `audit_dataset.py`
- [ ] Splits written: train / validation / calibration / test_known / test_unseen_generator
- [ ] Zero `identity_id` overlap across splits (test-asserted)
- [ ] ≥1 `generator_family` fully held out from train/val/calibration
- [ ] `KYCDegradation` applied to 100% of processed images, both classes
- [ ] ≥300 real self-captures in manifest
- [ ] ≥300 screen-replay attacks in manifest
- [ ] `data/README.md` — provenance + licence + consent for every source
- [ ] rPPG extractor validated on UBFC-rPPG / PURE / COHFACE (HR error < 5 BPM)

**Gate:** identity-disjoint, source-grouped splits; audit reports zero FAIL → `[ ]`

---

## Phase 04 — Tier-1 signals · [`PLANS/04`](./PLANS/04-signals-tier1.md)

- [x] `signals/fft.py`
- [x] `signals/texture.py`
- [x] `signals/vit_clip.py` (stub — kills clean without torch; Phase-06 re-entry slot)
- [x] `signals/prnu.py` (noise **presence**, numpy+cv2 re-implementation of Bondi/Mihçak stages)
- [x] `signals/replay_detect.py` (PRNU's mandatory companion)
- [x] `signals/corneal.py` — harness-KILLED, deleted (see RISK_REGISTER.md KILL-01)
- [x] `signals/chromatic_aberration.py`
- [x] `signals/geometry.py` — harness-KILLED, deleted (see RISK_REGISTER.md KILL-02)
- [ ] `models/` — backbone, classifier, ensemble, losses, registry
- [ ] `scripts/train.py`, `scripts/evaluate.py`
- [x] Harness report for each signal with `per_feature_auc`
- [ ] Neural baseline AUC reported on `test_unseen_generator` (expect 0.75–0.85)
- [x] ≥2 of {PRNU, corneal, chromatic aberration} survive (PRNU + CA)
- [x] Killed signals **deleted** from the tree, reason in `RISK_REGISTER.md`
- [x] No hardcoded decision thresholds in any signal (lint-enforced —
  `tests/unit/test_signal_thresholds.py` AST-scans `signals/` for anonymous
  numeric comparators; band edges / size floors live behind named constants,
  zero/one guards allowed as structural)

**Gate:** baseline cross-source AUC reported; ≥2 of 3 survive → `[ ]`

---

## Phase 05 — Tier-2 signals · [`PLANS/05`](./PLANS/05-signals-tier2.md)

- [ ] `signals/rppg.py` video mode (POS/CHROM, not raw green)
- [ ] `signals/sss_active.py` — dark→bright frame pair, difference image
- [ ] Random colour-sequence challenge (defeats pre-recorded + injected video)
- [ ] SDK capture-bundle schema (still + frames + fps + sdk_meta)
- [ ] `degradation/replay.py` extended to injected video
- [ ] HR error < 5 BPM on UBFC-rPPG
- [ ] Deepfake-video AUC ≥ 0.75
- [ ] Replay separation AUC ≥ 0.90
- [ ] Per-Fitzpatrick-bucket FPR table; no bucket > 1.5× overall

**Gate:** HR < 5 BPM on UBFC; replay AUC ≥ 0.90 → `[ ]`

---

## Phase 06 — Tier-3 signals · [`PLANS/06`](./PLANS/06-signals-tier3.md)

- [ ] `signals/rppg.py` still-image perfusion map
- [ ] `signals/scleral.py` — Murray's Law vessel topology, ≥80px eye gate
- [ ] `signals/weather.py` — indoor/outdoor gate, submission-consistency framing
- [ ] `signals/metadata.py` — EXIF, context only
- [ ] Harness report for each
- [ ] Killed signals deleted with reason recorded
- [ ] `metadata.py` emits only `neutral` direction codes (test-enforced)
- [ ] `scleral.py` reports `applicable=False` below 80px (test-enforced)

**Gate:** every conditional signal has a harness verdict, kept or killed on evidence → `[ ]`

---

## Phase 07 — Fusion, uncertainty, policy, explainability · [`PLANS/07`](./PLANS/07-fusion-uncertainty.md)

- [ ] `fusion/features.py` — quality-masked feature assembly
- [ ] `fusion/fusion.py` — `ExplainableFusion` (LR + isotonic)
- [ ] `fusion/conformal.py` — `q_lo` / `q_hi` at 5% target error
- [ ] `fusion/attribution.py` — top-5 drivers
- [ ] `inference/pipeline.py` — real orchestrator
- [ ] `inference/predictor.py` — loads weights once, returns logits, CPU+GPU
- [ ] `inference/calibration.py` — logits → calibrated p
- [ ] `inference/uncertainty.py` — disagreement, transform stability, OOD, margin
- [ ] `inference/policy.py` — 4-way verdict from `artifacts/thresholds.json`
- [ ] `explain/attribution.py` (Captum IG), `heatmap.py`, `signal_summary.py`
- [ ] `scripts/calibrate.py`, `scripts/tune_thresholds.py`
- [ ] Reliability diagram + ECE + Brier written to `artifacts/reports/`
- [ ] `uncertain` rate ≤ 15% at 5% target error on held-out generator
- [ ] `unable_to_assess` for no-face / small-face / corrupt / unusable blur
- [ ] Every response carries model + threshold + calibration versions
- [ ] Heatmap always ships with a limitation notice (test-enforced)
- [ ] No reason code lacks a `limitation` field (test-enforced)
- [ ] `signal_summary.py` passes the banned-phrase check

**Gate:** `uncertain` rate ≤ 15% at 5% target error on held-out generator → `[ ]`

---

## Phase 08 — API · [`PLANS/08`](./PLANS/08-api-frontend.md)

- [ ] `api/main.py`, `dependencies.py`, `schemas.py`, `worker.py`
- [ ] `POST /v1/detect`, `GET /v1/model-info`, `GET /health`, `GET /ready`, `GET /v1/result/{id}`
- [ ] Secure upload: magic bytes, size cap, pixel cap, single-frame, self-generated temp names
- [ ] Temp files outside web root; deleted after inference (test-asserted)
- [ ] Async routing for slow signals (rPPG, MC-dropout)
- [ ] Valid JPEG/PNG uploads score successfully
- [ ] Rejection matrix complete: wrong magic bytes, oversized, corrupt, multi-frame,
      path-traversal filename, null-byte filename
- [ ] No image bytes or EXIF values in logs (test-asserted)

**Gate:** valid uploads scored; hostile uploads rejected; no retention → `[ ]`

## Phase 08b — Reviewer frontend · [`PLANS/08`](./PLANS/08-api-frontend.md)

- [ ] Vite + React + TS scaffold, `api/client.ts`, `types/detection.ts`
- [ ] `UploadPanel`, `ResultCard`, `ProbabilityBar`, `SignalList`, `DriverList`
- [ ] `HeatmapViewer` (with limitation notice), `UncertaintyBanner`, `PrivacyNotice`
- [ ] Four verdict colours: green / red / amber / gray
- [ ] No "guaranteed fake" language anywhere (test-enforced on copy)
- [ ] Model version + privacy notice always visible
- [ ] Non-technical walkthrough passed

**Gate:** a non-technical person can read a report and agree or disagree → `[ ]`

---

## Phase 09 — Evaluation, governance, deployment · [`PLANS/09`](./PLANS/09-evaluation-governance.md)

- [ ] `evaluation/metrics.py` — AUROC, AUPRC, accuracy, P/R, FPR, FNR, confusion, TPR@FPR
- [ ] `evaluation/calibration_metrics.py` — ECE, Brier, reliability diagram
- [ ] `evaluation/robustness.py` — JPEG, screenshot, resize/crop, blur, brightness, noise,
      metadata removal, social recompression (reported as **degradation**)
- [ ] `evaluation/slices.py` — real vs known, real vs unseen, selfie vs ID, face size,
      quality, attack type, demographics (consented only)
- [ ] `evaluation/fairness.py` — FPR per Fitzpatrick / age / glasses / makeup
- [ ] `evaluation/report.py` → `evaluation.json`, `evaluation.md`, `confusion_matrix.png`,
      `calibration_curve.png`, `robustness.csv`
- [ ] FPR and FNR documented at the production operating point
- [ ] **No demographic bucket has FPR > 1.5× overall**
- [ ] Adversarial red-team window completed; results in `THREAT_MODEL.md`
- [ ] `tests/unit`, `tests/integration`, `tests/security`, `tests/robustness`, `tests/harness`
- [ ] `docker/api.Dockerfile`, `docker/web.Dockerfile`, `docker/nginx.conf`, `docker-compose.yml`
- [ ] `.github/workflows/ci.yml`
- [ ] `docs/` — architecture, api, data_collection, evaluation_protocol, deployment,
      limitations, incident_response
- [ ] `THREAT_MODEL.md`, `MODEL_CARD.md`, `DATA_CARD.md`, `RISK_REGISTER.md`, `SECURITY.md`
- [ ] `artifacts/model_registry.json` — versions, seeds, hashes, device

**Gate:** no demographic bucket FPR > 1.5× overall; all tests pass; Docker runs → `[ ]`

---

## Phase 10 — Monitoring · [`PLANS/10`](./PLANS/10-monitoring.md)

- [ ] `monitoring/drift.py` — score drift, coverage drift, AUC drift
- [ ] `monitoring/alerts.yaml` with owners per rule
- [ ] `monitoring/dashboard.json` — verdict mix, uncertain rate, probability histogram,
      per-signal coverage, per-signal AUC trend, latency, bucket FPR
- [ ] Weekly automated harness re-run
- [ ] Canary set established and versioned
- [ ] `docs/incident_response.md` retraining playbook
- [ ] Fire drill: playbook exercised once on synthetic drift

**Gate:** dashboard live; weekly harness re-run automated → `[ ]`

---

## Definition of Done

Aggregate bar. All must be `[x]` before the project is called complete.

**Correctness**
- [ ] Valid JPEG/PNG uploads work
- [ ] Dangerous, corrupt, huge, or unsupported uploads are rejected
- [ ] No-face and low-quality images return `unable_to_assess`
- [ ] Model supports genuine, generated, face-swap, morph, and edited images
- [ ] Training, calibration, and test identities are separate
- [ ] An unseen-generator test exists and is the headline number

**Honesty**
- [ ] The returned probability is calibrated
- [ ] The system returns `uncertain` instead of forcing every result
- [ ] Every result includes structured reason codes
- [ ] A heatmap is displayed with a limitation notice
- [ ] Metadata is never treated as proof by itself
- [ ] False-positive and false-negative rates are documented
- [ ] Robustness to compression, resizing, screenshots, and blur is measured
- [ ] Fairness slices published; no bucket > 1.5× overall FPR

**Operations**
- [ ] Uploaded images are not retained by default
- [ ] Model version, threshold version, and calibration version are recorded
- [ ] Unit, integration, security, and robustness tests pass
- [ ] The API and frontend run through Docker
- [ ] `MODEL_CARD.md`, `DATA_CARD.md`, `THREAT_MODEL.md` are complete
- [ ] The product clearly recommends manual review for uncertain or high-risk results

---

## Session log

| Date | What happened | Blockers |
| --- | --- | --- |
| 2026-09-05 | Analysed `IDEA.md` + `farebi plan.txt`. Reconciled the two layouts into a two-runtime architecture. Authored `FAREBI.md`, `PLANS/00`–`PLANS/10`, and this checklist. No code written yet — workspace is greenfield. | None. Next up: `PLANS/01` foundation. |
| 2026-09-05 | **Phase 01 implemented and shipped green.** Repo skeleton (`pyproject.toml`, `Makefile`, `configs/`, tooling), L0 `core/`+`utils/`, L1 `capture/` (incl. a two-backend MediaPipe adapter for the 0.10.35 API break + downloaded `face_landmarker.task`), empty L4 `inference/pipeline.py`, `scripts/smoke_test.py` + `scripts/fetch_face_landmarker.py`, `data/README.md` + `.gitkeep`s, `tests/fixtures/README.md`. Quality gates all pass: 167 tests, `ruff`, `ruff format`, `mypy --strict`, `importlinter`, smoke test (9 distinct rejection codes). Fixed real defects: `security.py:121` tuple precedence, PiiScrubber ordering, pipeline `response` trace, cv2 `fillConvexPoly` typing. | None. Next up: `PLANS/02` signal factory. |
| 2026-09-05 | **Phase 02 signal factory — gate PASSED.** Wrote `scripts/run_harness.py` (self-test + `--samples` pickle modes) and two test suites: `tests/harness/test_gono.py` (golden go/no-go: noise→KILL, partial→BENCH, encoded→KEEP, plus boundary tests) and `tests/unit/test_registry.py` (a `kill`/`unmeasured` signal is excluded from `all_enabled()`). Fixed a real `config.py` bug: `YamlConfigSettingsSource.__init__` now accepts a single `Path` (was iterating a lone `Path` and raising). Stub `NoiseSignal` changed from random noise to a constant feature so its KILL is deterministic. Full suite: 174 passed, 0 failed; `ruff`/`mypy --strict` clean on changed files. Earlier also cloned 14 reference repos into `vendor/` (see memory). | None. Next up: Phase 03 data pipeline, then real Tier-1 signals (`signals/fft.py`, `texture.py`, `vit_clip.py`, …) adapted from `vendor/`. |
| 2026-09-05 | **Tier-1a signals shipped.** `signals/prnu.py` (numpy+cv2 re-implementation of prnu-python wavelet-denoising stages — Gaussian residual + boxFilter Wiener + numpy Wiener-DFT), `fft.py`, `texture.py`, `replay_detect.py` (PRNU companion), `vit_clip.py` (Phase-06 stub). Fixed `test_layering` leaf rule to exempt the `farebi.signals.base` contract import; `cv2.Laplacian` CV_64F→CV_32F; calibrated thresholds on 6 Dresden naturals (peak-height flags removed). 174/174 pytest, ruff/mypy clean. Committed `e8bcb48`, pushed to `BeastAyyG/farebi` (master). | None. |
| 2026-09-05 | **Vendor audit + roadmap update.** Cloned GenD (`yermandy/GenD`) and `polimi-ispl/synthetic-image-detection` (laundering caveat for PRNU); applied DeepFakesON-Phys open PR #2 vectorisation locally with tracked patch in `docs/vendor-patches/`; recorded prnu-python pins and rPPG-Toolbox lineage. Updated `vendor/clone_all.sh`, `vendor/README.md`, `PLANS/03` (DF40, Eval-2024, paired training), `PLANS/04` (CoOp/GenD/AIDE path), `PLANS/09` (red-team items). Committed `654370f`, pushed. | None. |
| 2026-09-05 | **Tier-1b + first harness verdicts (quick256 shim).** Wrote `signals/corneal.py`, `geometry.py`, `ca.py`; `tests/unit/test_signals_tier1b.py` 11 passed. Data shim (Option A): 480 rows from bitmind 256px parquets (ffhq/celeba-hq real, sdxl/flux fake), 407 usable captures; iris-mapping assert passed on 215 real captures. Fixed real bug: mediapipe 0.10.35 `VisionRunningMode` renamed. Harness (`--n-splits 2`, degraded): KEEP prnu 0.907 / texture 0.875 / CA 0.884 / replay 0.862 / fft 0.730; KILL corneal 0.544 / geometry 0.559 / vit_clip (no torch). Corneal premise check on 1024px real portraits (n=31, eye 116px): IoU median 0.000 with working highlight extraction — premise kill, not resolution. Corneal + geometry **deleted** per PLANS/04; reasons in new `RISK_REGISTER.md`. Phase-04 2-of-3 survival gate satisfied (PRNU + CA); neural baseline + `models/` still open so the Phase-04 gate stays open. | Self-capture campaign (calendar lead time, blocks Phase-09 fairness gate) should start as a parallel workstream. |
| 2026-09-05 | **Threshold lint (Phase-04 item).** Named every anonymous comparison literal in Tier-1 signals (`_MIN_CROP_PX`, `_MIN_BG_PX`, band edges `_HIGH_BAND_R`/`_MIDHIGH_BAND_R`/`_MOIRE_BAND_LO|HI`, `_MIN_BLOCK_PX` � each with calibration/methodology comments); added `tests/unit/test_signal_thresholds.py` AST lint (only 0/1 structural literals allowed as bare comparators, self-tested with planted-literal cases). 183 pytest pass; ruff/mypy clean on touched files (remaining RUF012 are the intentional Signal-ABC pattern; 18 pre-existing ruff-0.16.6 drift errors on HEAD untouched). Ticked the PROGRESS.md item. `models/` + train/evaluate + neural baseline still open (blocked on torch). | None. |
| 2026-09-05 | **PRNU-laundering red-team probe (Phase-04 item, partial).** Torch-free deterministic laundering recipe (128px downscale + JPEG-q75 + upscale + JPEG-q92) in `scripts/launder_quick_fakes.py`; 240 sdxl/flux fakes laundered, manifest `data/manifests/quick_laundered_manifest.csv`. Generalized `scripts/build_quick_samples.py` with `--manifest/--out`; new `scripts/eval_probe.py` evaluates without clobbering the machine-owned quick256 registry. Probe (`quick256-laundered`, n=354, n_splits=2): PRNU 0.939 / replay 0.944 / texture 0.918 / CA 0.973 / fft 0.821 — all five KEEP signals survive; AUCs rose vs clean (resampling collapses fake residual structure while real sensor noise persists). RISK_REGISTER.md PRNU-laundering entry updated with numbers + caveat (own recipe, not the exact polimi pipeline; copy-attack + high-res re-validation still open). | None. |
| 2026-09-05 | **PRNU copy-attack probe (Phase-04 red-team).** Donor fingerprint averaged from 120 ffhq residuals (same Gaussian sigma=1.0 + zero-mean estimator as prnu.py), transplant J*(1+alpha*F) onto 240 sdxl/flux fakes in scripts/attack_copy_prnu.py; alpha=0.08 calibrated to real median variance (gap 9%); attacked PNGs (lossless) under <group>_copyattack in data/manifests/quick_copyattack_manifest.csv. Fixed build_quick_samples.py hardcoded declared_media_type=image/jpeg which rejected all 240 PNGs (now sniffed from suffix). Probe (quick256-copyattack, n=445, n_splits=2): PRNU 0.907 -> **0.669** (face_energy feature collapses to 0.622); texture 0.875 -> 0.682, replay 0.862 -> 0.760, fft 0.730 -> 0.652; CA unaffected at 0.907. Cross-camera donor = lower bound on attacker power. RISK_REGISTER.md STANDING-PRNU updated: presence is spoofable, structural fix is device-enrolment matching (future work). | None. |
| 2026-09-05 | **Self-capture campaign kit (Phase 03 parallel workstream).** Wrote `data/capture_campaign/`: `PROTOCOL.md` (12-shot minimum per subject, diversity quotas incl. Fitzpatrick I-VI + 20 phone models, replay-attack procedure with `<family>-replay` grouping, QC checklist, withdrawal/purge rule), `CONSENT_TEMPLATE.md` (marked requires legal review, 18+, no public release covered), `shot_log_template.csv` (8 manifest columns + session extras). Updated `data/README.md` layout + `PLANS/03` status to in-progress. No captures yet — exit-gate counts (300 real / 300 replay) still open; recruiting is the human-side critical path. | Human recruiting + legal review of consent form. |
