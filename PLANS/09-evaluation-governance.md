# 09 — Evaluation, Fairness, Robustness, Testing & Governance

**Parent:** [`FAREBI.md`](../FAREBI.md) · **Phase:** 9 · **Depends on:** 07, 08
**Status:** ⬜ Not started

## Objective

Prove the system works, prove it fails gracefully, document exactly how it fails, and put the
governance artifacts in place that let another organisation trust or reject it.

## Scope

### `src/farebi/evaluation/` (offline only — never imported by `api/`)

| File | Responsibility |
| --- | --- |
| `metrics.py` | AUROC, AUPRC, accuracy, precision, recall, FPR, FNR, confusion matrix, **TPR at fixed FPR** (the operating points a KYC team actually cares about). |
| `calibration_metrics.py` | Expected Calibration Error, Brier score, reliability diagram. |
| `robustness.py` | JPEG compression, screenshots, resize+crop, blur, brightness, noise, metadata removal, social-media-style recompression. Reports AUC **degradation** per transform, not just absolute AUC. |
| `slices.py` | Real vs known fake · real vs unseen generator · selfie vs ID portrait · face size buckets · image quality buckets · attack type · demographic group (only where consented labels exist). |
| `fairness.py` | **FPR per Fitzpatrick skin-type bucket, age band, glasses, makeup.** Plus an adversarial test window. |
| `report.py` | Writes `artifacts/reports/{evaluation.json, evaluation.md, confusion_matrix.png, calibration_curve.png, robustness.csv}`. |

### Fairness gate

> **No demographic bucket may have FPR > 1.5× the overall FPR.**

Where a bucket fails:
1. Publish it in `MODEL_CARD.md` — do not hide it.
2. Down-weight the responsible signal via its `quality` field for the affected captures.
3. If it cannot be corrected, restrict or disable the signal for that population and record it
   in `RISK_REGISTER.md`. **Never let a signal silently reject people.**

### Adversarial test

Run a red-team window: an attacker with knowledge of the system tries to beat it for one week
(targeted compression, re-encoding, filters, screen replay, injected video, prompt-crafted
diffusion). Every success is written into `THREAT_MODEL.md` and `RISK_REGISTER.md`, and the
successful sample is added to the evaluation set.

### Tests

| Directory | Coverage |
| --- | --- |
| `tests/unit/` | `image_validation`, `calibration`, `uncertainty`, `policy`, `signal_summary`, `contract` (every signal satisfies `Signal` and survives `preflight` on degenerate input) |
| `tests/integration/` | `detect_api`, `inference_pipeline` |
| `tests/security/` | `upload_security` — the full rejection matrix |
| `tests/robustness/` | `jpeg_recompression`, `resize_crop`, `blur_noise` — verdict stability, not exact equality |
| `tests/harness/` | Golden go/no-go regression: a signal that was KEEP must not silently drop below its recorded AUC |

### Governance documents

| File | Must contain |
| --- | --- |
| `THREAT_MODEL.md` | **In scope:** fully AI-generated faces, face swaps, face morphs, local facial manipulation, heavily manipulated selfies, recompressed/screenshot versions of attacks. **Out of scope:** a stolen but genuine photograph; whether the face belongs to the claimed person; liveness from a single still; physical masks; complete document authenticity. |
| `MODEL_CARD.md` | Architecture + version, training datasets, label definitions, evaluation metrics, known failure cases, thresholds, demographic and quality slice results, intended **and prohibited** uses. |
| `DATA_CARD.md` | Provenance, licence, consent, collection method, known biases, per-source counts. |
| `RISK_REGISTER.md` | Genuine photos flagged · new generators bypassing the model · compressed-image degradation · demographic differences · biometric leakage · users treating the heatmap as proof. **Plus every killed signal and why.** |
| `SECURITY.md` | Disclosure policy, upload threat surface, retention statement. |

### Deployment

- `docker/api.Dockerfile`, `docker/web.Dockerfile`, `docker/nginx.conf`, `docker-compose.yml`.
- `.github/workflows/ci.yml` — install, lint, type, import-linter, unit, integration, security,
  robustness, harness-regression.
- `docs/` — `architecture.md`, `api.md`, `data_collection.md`, `evaluation_protocol.md`,
  `deployment.md`, `limitations.md`, `incident_response.md`.

### Reproducibility

PyTorch does not guarantee bit-exact reproducibility across releases, platforms, or hardware.
Every run records into `artifacts/model_registry.json`: package versions, seeds, model-weight
sha256, config hash, git SHA, device info, and CUDA/driver versions.

## Key decisions

1. **Robustness is measured as degradation, not absolute score.** "AUROC 0.82 → 0.79 at
   q=70 JPEG" is actionable. "AUROC 0.79" alone is not.
2. **The headline number is the unseen-generator AUC.** Any other number quoted in marketing
   or docs must be labelled with its split.
3. **Fairness is a release gate, not a report.** A failing bucket blocks release.
4. **Killed signals are documented, not quietly forgotten.** They are the most valuable
   institutional knowledge in the project.

## Exit gate

- [ ] FPR and FNR documented at the production operating point, on both known and unseen
      generator splits.
- [ ] Robustness measured for compression, resizing, screenshots, and blur, reported as
      degradation.
- [ ] **No demographic bucket has FPR > 1.5× overall.**
- [ ] Adversarial red-team window completed; results written into `THREAT_MODEL.md`.
- [ ] Unit, integration, security, robustness, and harness-regression tests all pass in CI.
- [ ] API and frontend both run under `docker-compose up`.
- [ ] `MODEL_CARD.md`, `DATA_CARD.md`, `THREAT_MODEL.md`, `RISK_REGISTER.md` complete.
- [ ] `artifacts/model_registry.json` records versions, seeds, hashes, and device for the
      shipped model.
- [ ] The product visibly recommends manual review for every uncertain or high-risk result.

## Risks

| Risk | Mitigation |
| --- | --- |
| Demographic labels are unavailable or not consented | Report the slice as "not measured" rather than imputing; do not release a fairness claim that was never measured |
| Fairness gate blocks release late in the project | Measure FPR per bucket from phase 05 onward, not at the end |
| Adversarial test finds something catastrophic | That is the test succeeding. Budget time to fix before release, not after. |
| Robustness numbers look bad and tempt selective reporting | Publish the full `robustness.csv`; document the worst case in `MODEL_CARD.md` |
