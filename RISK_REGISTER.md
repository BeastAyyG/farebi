# Risk register — killed signals and standing caveats

Every harness kill lands here with the measured reason. A killed signal is
deleted from the tree (PLANS/04 gate); the registry artifact
(`artifacts/signal_registry.json`) keeps the numbers, this file keeps the
judgement so a future session does not re-litigate dead ideas without new
evidence.

## KILL-01 — `signals/corneal.py` (deleted 2026-09-05)

- **Harness (quick256, n_splits=2, degraded):** cross-source AUC **0.544**,
  coverage 100% → KILL (AUC < 0.60). Best feature was
  `corneal_count_ratio`, not the paper's IoU.
- **Premise check (1024px real portraits, CelebA-HQ, n=31 applicable,
  median eye width 116px):** highlight extraction works (median 1
  highlight/eye, only 31% of eyes empty) but cross-eye IoU median is
  **0.000**, mean 0.057; only 6% of real portraits clear the paper's real
  band (IoU > 0.30). Real portraits do not show overlapping highlights
  under iris-landmark normalisation — multi-source studio lighting and
  gaze asymmetry break the single-source assumption. The kill is premise,
  not resolution.
- **Re-entry condition:** new evidence only — e.g. a self-capture set with
  a single known light source where real IoU demonstrably clusters high.
  Do not re-add on 256px data.

## KILL-02 — `signals/geometry.py` (deleted 2026-09-05)

- **Harness (quick256, n_splits=2, degraded):** cross-source AUC **0.559**,
  coverage 100% → KILL (AUC < 0.60). Best feature `iod_px` — i.e. the
  signal was mostly measuring face size, which legitimately varies across
  sources.
- **Re-entry condition:** a geometry feature with a causal story (e.g.
  calibrated against depth) and a harness number. Ratio-soup does not
  re-enter.

## STANDING — `signals/vit_clip.py` (kept as stub, status kill)

- Kill reason is environmental, not merit: no torch in the research venv,
  no weights vendored (Phase-06). The file is the designated re-entry
  slot — do not delete. Re-entry: frozen CLIP-ViT + linear probe, then
  CoOp prompt-tuning / GenD / AIDE per PLANS/04.

## STANDING — PRNU vs laundered fakes

- PRNU keeps — **0.907** on quick256 — but the real groups are camera
  photos and the fake groups are raw diffusion outputs. Sensor-noise
  separation is expected there. The polimi-ispl synthetic-laundering
  finding (recompression/resize erases the noise signature) means this
  number must be re-measured on laundered fakes before it counts as
  production evidence. PRNU must never fire alone (`requires:
  [replay_detect]` is contractual).
- 2026-09-05 red-team probe (`quick256-laundered`, n=354, real vs
  128px-downscale + JPEG-q75 + upscale + JPEG-q92 fakes): PRNU **0.939**,
  replay_detect 0.944, texture 0.918, CA 0.973, fft 0.821 — all five
  KEEP signals survive this laundering recipe, and AUCs rose vs clean,
  consistent with resampling collapsing residual structure in fakes while
  real sensor noise persists. Caveat: this is our own torch-free recipe,
  not the exact polimi pipeline — re-validate against their laundered
  set (and the prnu-copy-attack repo) before the Phase-04 gate closes.
   High-res re-validation still open (no high-res fakes on hand).
- 2026-09-05 copy-attack probe (`quick256-copyattack`, n=445, real vs
  fakes carrying a transplanted donor fingerprint, alpha=0.08 calibrated so
  attacked-fake median residual variance matches the real median within 9%):
  PRNU **0.669** (was 0.907 clean) — the presence workhorse
  `prnu_face_energy` collapses to 0.622 while `prnu_face_mean_abs` (0.669)
  and the face/bg log-ratio (0.658) carry the residual. Collateral damage:
  texture 0.875 -> 0.682, replay 0.862 -> 0.760, fft 0.730 -> 0.652;
  CA unaffected (0.907 — different physical basis). Donor is a
  cross-camera average over 120 ffhq images, i.e. a LOWER BOUND on attacker
  power vs a true same-camera fingerprint. Conclusion: noise *presence* is
  spoofable by transplant — the structural fix is device-enrolment
  *matching* (store the fingerprint at first verification), which is future
 work beyond Phase 04. Digital transplant is not screen replay, so
 `replay_detect` is not the mitigation here.

## STANDING — `signals/replay_detect.py` leans on a non-screen cue

- 2026-09-05 replay-simulation probe (`quick256-replay`, n=441 real vs
  replayed-fake, `ScreenReplaySimulator(seed=7)` over the 240 sdxl/flux
  fakes, new `scripts/attack_replay_sim.py`): all five KEEP signals hold —
  replay_detect **0.862** (identical to clean), prnu 0.878, texture 0.828,
  fft 0.796, CA 0.931. Kept 441/480 (replay preserves sharpness better
  than laundering).
- Clean-fake vs replayed-fake follow-up (n=192+226, isolates the replay
  transform): `replay_moire_peak` moves (**0.828** — the screen cue
  registers) but `replay_midband_ratio` does not (**0.568**) — yet midband
  is the feature every real-vs-fake verdict leans on. Design tension: the
  feature that detects replay cannot lean (Dresden reals hit 28-425x
  peaks), and the feature that leans does not respond to replay. A
  replayed REAL photo (real PRNU + screen moire) would score
  midband-normal + peak-high = likely MISS under current weighting.
- Consequence: replay_detect's KEEP verdict is currently carried by a
  fake-content cue, not a screen cue. Do not claim replay coverage until
  photographed-screen positives — especially replayed REALs — from the
  self-capture campaign are in the harness.
- Caveats: simulator pitch (2-6px) sits inside the detection band
  (0.05-0.45), so separation is partly plumbing validation; simulated
  replays carry no photographing-camera PRNU, so PRNU numbers on this
  probe are simulation artifacts — neither credited nor charged.

## DIRECTIONAL — face-MORPH response is an upper bound, not coverage

- 2026-09-05 morph probe (`quick256-morph`, n=318 real vs landmark-morph,
  new `scripts/attack_morph.py`): sequential ffhq/celeba-hq pairs,
  eye-midpoint/iod/angle similarity alignment to a natural-scale 256px
  canvas (dst_iod 56px, scale ~1.0), alpha-0.5 blend inside a feathered
  FACE_OVAL mask, lossless PNGs. Manifest
  `data/manifests/quick_morph_manifest.csv`; 103/107 morphs kept.
- Probe AUCs (n_splits=2): prnu **0.779**, texture **0.766**,
  replay_detect **0.679**, CA **0.675**, fft **0.641** (BENCH band),
  vit_clip n/a (no torch). All five synthetic-fake KEEPs respond to
  morphs, but weaker across the board than to diffusion fakes.
- Mechanism (per-feature medians, real vs morph): prnu_face_energy
  10.2 -> 6.0, prnu_bg_energy 100.3 -> 20.9 (BOTH parents are warped, so
  the whole frame including A's background is resampling-softened);
  texture logratios move toward 0 (face/bg homogenised by smoothing).
  The separation is carried substantially by whole-frame resampling
  softness from this crude pipeline, NOT by morph-specific cues
  (no seam/ghost/demographic-shift features exist yet).
- Recipe bugs fixed along the way (all in the attack script, not shipped
  code): v1 dst_iod 77px zoomed faces and starved bg estimators
  (prnu_bg_energy -> 0.0, texture inapplicable — a bogus PRNU 1.000);
  v2 dst_iod 30px confused single-eye width with iod and halved every
  head (FACE_TOO_SMALL); default warpAffine black fill tripped the
  clipped-pixel gate (fixed with BORDER_REPLICATE).
- Consequence: treat these numbers as an UPPER BOUND on morph
  detectability. A professional pipeline (high-res warp + Poisson blend
  + grain matching, then downsample) would close most of the resampling
  gap. Structural defence is enrolment-time duplicate-identity /
  dedicated morph-detection models — future work needing morph training
  data + torch. Do not claim morph coverage.
