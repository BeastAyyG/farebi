# 04 — Tier-1 Signals

**Parent:** [`FAREBI.md`](../FAREBI.md) · **Phase:** 3 · **Depends on:** 02, 03
**Status:** ⬜ Not started

## Objective

Build the signals that must exist for the product to function, and put the neural baseline in
place so the factory itself has been validated against real data. **Expect a cross-source AUC
of 0.75–0.85. If you see 0.99, suspect leakage before celebrating.**

## Scope

| Module | Signal | Notes |
| --- | --- | --- |
| `signals/fft.py` | Frequency domain | Radial power-spectrum statistics, GAN upsampling grid artefacts. Vary generator ψ — low-ψ is easy, high-ψ is not. |
| `signals/texture.py` | Texture & spatial artefacts | Local binary patterns, noise residual inconsistency, edge statistics. Likely degrades under JPEG — measure it. |
| `signals/vit_clip.py` | **Neural baseline** | Frozen CLIP-ViT features + linear probe (UnivFD approach). **Do not fine-tune a ViT from scratch first** — the linear probe generalises across generators far better and trains in minutes. Upgrade path: CLIPping-the-Deception CoOp Prompt Tuning (keeps the text encoder, +5% mAP same envelope); alternative: GenD LN-tuning (`vendor/GenD`, HF `yermandy/gend`). Cross-check against AIDE hybrid (`meet4150/AIDE_image_detector`, FFT+semantic, ICLR 2025). Weights install in Phase 06 — no torch in `.venv` yet. |
| `signals/prnu.py` | Sensor-noise presence | Wavelet (Mihçak) denoising then noise-residual statistics. `fastNlMeansDenoising` is prototyping-only. **Presence, not matching.** |
| `signals/replay_detect.py` | Screen-replay detection | Moiré (FFT peak at display pixel pitch), display colour gamut, specular rectangle, flat depth. **Mandatory companion to PRNU.** |
| `signals/corneal.py` | Corneal reflection consistency | MediaPipe iris landmarks localise the cornea. Check: reflections exist; both eyes reflect the same scene; count and position are plausible. |
| `signals/chromatic_aberration.py` | Chromatic aberration | Run on the **full frame**, not the face crop — CA lives at image edges. Sub-pixel R/B channel displacement vs radial distance. |
| `signals/geometry.py` | Facial geometry & iris consistency | Landmark symmetry, iris/pupil ratio consistency between eyes, interocular plausibility. |

### `src/farebi/models/`

- `backbone.py` — frozen CLIP-ViT feature extractor (loads once, `predictor.py` owns the handle).
- `classifier.py` — linear probe head (and an optional shallow MLP for comparison).
- `ensemble.py` — MC-dropout passes + seed ensemble; used by `inference/uncertainty.py`.
- `losses.py`, `registry.py`.

### `scripts/train.py`, `scripts/evaluate.py`

Train the probe on the train split, select on validation, report on **both** `test_known` and
`test_unseen_generator`. Log to MLflow/W&B including the dataset version hash.

## The PRNU caveat — read this before writing `prnu.py`

> **PRNU proves that a physical camera photographed something. It does not prove the face is
> real.** A fraudster displays a Flux face on a tablet and photographs it with a phone:
> genuine PRNU, entirely fake face.

Therefore:

1. PRNU must never fire alone. It is paired with `replay_detect.py` in `requires`.
2. Its honest KYC strength is **device enrolment**: store the noise fingerprint from a
   customer's first verification and check the same sensor on re-verification. That is a
   signal a fraudster cannot forge without the customer's physical phone.
3. `replay_detect` is a Tier-1 signal, not an afterthought.

## The corneal caveat

Needs eye width ≥ 40px. **Solve this with capture UX, not code** — "move closer" is cheaper
than any algorithm. Enforce a minimum inter-ocular distance (≥120px) in the capture SDK and
let `applicable=False` handle the rest.

## Key decisions

1. **Linear probe before fine-tuning.** Faster, more general, and it is the honest baseline
   that every later model must beat.
2. **No hand-tuned weights.** Every threshold in the reference code (`0.45`, `1.03`, `0.78`)
   is a placeholder. Signals emit raw features; the fusion learns the weights (phase 07).
3. **Return logits, not labels.** `predictor.py` returns logits so calibration (phase 07) has
   something to work with.

## Exit gate

- [ ] All eight Tier-1 modules implement `Signal` and pass `preflight` correctly on
      easy/hard/no-face inputs.
- [ ] `run_harness.py --all` produces a report for each, with `per_feature_auc` tables.
- [ ] Neural baseline cross-source AUC reported on `test_unseen_generator` — and if it is
      above 0.95, the leakage audit in `PLANS/03` has been re-run and explained.
- [x] **≥2 of {PRNU, corneal, chromatic aberration} survive** (KEEP or BENCH).
      quick256 2026-09-05: PRNU 0.907 KEEP + CA 0.884 KEEP; corneal 0.544 KILL.
- [ ] `replay_detect` has a harness report against the replay-attack set.
- [x] Each killed signal is deleted from the tree (not merely disabled) with the reason
      recorded in `RISK_REGISTER.md`.
      2026-09-05: corneal (KILL-01) + geometry (KILL-02) deleted; vit_clip kept as
      Phase-06 stub (environmental kill, see RISK_REGISTER.md).
- [ ] No signal contains a hardcoded decision threshold — enforced by a lint check that greps
      for float literals in comparison positions.

## Risks

| Risk | Mitigation |
| --- | --- |
| CLIP probe overfits to training generators | Cross-source `GroupKFold` is the reported metric; a high `auc_std` flags fragility |
| Chromatic aberration is too weak on modern flagships (ISP correction) | Keep it if AUC ≥ 0.60 — it is nearly free and uncorrelated, which is exactly what fusion wants. Kill it otherwise. |
| Texture/FFT signals die under the second JPEG | Measure on degraded data only. Expect attrition; that is the point of the factory. |
| PRNU misused as evidence of authenticity | `requires: [replay_detect]` in the contract; the reason code text states the limitation explicitly |
