# 07 — Fusion, Uncertainty, Policy & Explainability

**Parent:** [`FAREBI.md`](../FAREBI.md) · **Phase:** 6 · **Depends on:** 04, 05, 06
**Status:** ⬜ Not started

> This is the part a regulator and a bank's model-risk team will read. Every hand-tuned weight
> in the reference code (`0.45`, `1.03`, `0.78`) was a placeholder; this phase replaces all of
> them with something learned, calibrated, and defensible.

## Objective

Turn per-signal features into **one calibrated probability with a statistically grounded
`uncertain` band**, and make every result traceable back to the measurements that produced it.

## Scope

### `src/farebi/fusion/`

| File | Responsibility |
| --- | --- |
| `features.py` | Assemble the feature vector from all applicable signals. Quality-masked, missing-signal-imputed, fixed column order recorded in `artifacts/fusion.pkl`. |
| `fusion.py` | `ExplainableFusion`: `LogisticRegression(C=0.5)` wrapped in `CalibratedClassifierCV(method="isotonic", cv=5)`. Interpretable, and its coefficients *are* the explanation. |
| `conformal.py` | Conformal `uncertain` band: find `q_lo` / `q_hi` on the **calibration split** such that `P(fake | p < q_lo) ≤ target_error` and `P(real | p > q_hi) ≤ target_error` (default 0.05). |
| `attribution.py` | Per-feature contribution `coef × value` → top-5 drivers with direction, for the reviewer UI. |

Why logistic regression rather than a gradient-boosted model: the bank's model-risk team has
to be able to read it. SHAP is available as a secondary view if the linear model is
insufficient, but the linear model is the default and must be justified before abandoning.

### `src/farebi/inference/`

| File | Responsibility |
| --- | --- |
| `pipeline.py` | The real orchestrator. Wires `FAREBI.md` §3.2 steps 1–12 in order. |
| `predictor.py` | Loads weights once, runs image + face-crop predictions, returns **logits** (not labels), supports CPU and GPU, stamps `model_version` on every result. |
| `calibration.py` | Logits → calibrated probability from `artifacts/calibration/temperature.json`. Never trained on the same data as the model. |
| `uncertainty.py` | Ensemble disagreement (MC-dropout variance), transform consistency (resize/JPEG round-trip), OOD score, margin to the band, image-quality uncertainty. Aggregates to one `uncertainty_score` and one `confidence_level`. |
| `policy.py` | The 4-way verdict from `FAREBI.md` §9. Thresholds loaded from `artifacts/thresholds.json` — **never hardcoded**. |

### `src/farebi/explain/`

| File | Responsibility |
| --- | --- |
| `attribution.py` | Captum Integrated Gradients over the neural baseline. |
| `heatmap.py` | Original image, coloured attribution map, overlay, and normalised region scores. |
| `signal_summary.py` | Measurements → structured reason codes with `code`, `direction`, `strength`, `message`, `limitation`. |

**Forbidden output** — `signal_summary.py` must never generate unsupported statements such as
"The eyes prove this is fake", "Missing EXIF means AI-generated", or "The skin is too
perfect". Allowed, and encouraged:

```json
{
  "code": "MODEL_FACE_BOUNDARY_SIGNAL",
  "direction": "toward_fake",
  "strength": 0.72,
  "message": "The visual classifier assigned substantial importance to the face and hair boundary.",
  "limitation": "Similar patterns can also be caused by background removal or image compression."
}
```

### `scripts/`

- `calibrate.py` — fit temperature/isotonic on the calibration split, write
  `artifacts/calibration/temperature.json` plus a reliability diagram.
- `tune_thresholds.py` — fit the conformal band, write `artifacts/thresholds.json`.

## Key decisions

1. **Quality-aware masking.** When a signal is inapplicable or low-quality, its features are
   masked and the fusion falls back on what it does have. It does not impute a neutral value
   and pretend to know.
2. **`uncertain` rate is a business parameter.** Target error (5%) is the policy lever; the
   resulting `uncertain` rate is the cost. Both are published, not hidden.
3. **`fake_probability` and `confidence_level` stay separate.** Probability is the predicted
   class probability; confidence is how stable that prediction is. Never collapse them.
4. **The band must be computed on the calibration split only**, never on test or train.

## Exit gate

- [ ] `ExplainableFusion` trains on the surviving signal features; top-5 drivers are produced
      for every result and match the measurements.
- [ ] Reliability diagram + ECE + Brier score written to `artifacts/reports/`.
- [ ] Conformal band achieves **`uncertain` rate ≤ 15% at 5% target error** on the held-out
      generator split.
- [ ] `unable_to_assess` returned for: no face, face below minimum px, corrupt image, unusable
      blur — each with a distinct reason code.
- [ ] `uncertain` returned for: inside-band, high OOD, high disagreement — each distinguishable
      in the response.
- [ ] Every response carries `model_version`, `threshold_version`, `calibration_version`.
- [ ] Heatmap rendered and base64-encoded with a **limitation notice attached** (test-enforced).
- [ ] No reason code lacks a `limitation` field (test-enforced).
- [ ] `signal_summary.py` output passes a banned-phrase check.

## Risks

| Risk | Mitigation |
| --- | --- |
| Isotonic calibration overfits a small calibration split | Require a minimum calibration-set size; fall back to Platt scaling below it and log the switch |
| The `uncertain` rate is commercially unacceptable (too high) | It is a tunable parameter — expose `target_error` in config and publish the automation/review trade-off curve |
| Reviewers over-trust the heatmap | Mandatory limitation notice in the API response and in the UI, adjacent to the image |
| Linear fusion underfits vs. gradient boosting | Justify any move away from LR in `MODEL_CARD.md`; measure the gain before paying the interpretability cost |
