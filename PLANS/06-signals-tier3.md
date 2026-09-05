# 06 — Tier-3 Conditional Signals

**Parent:** [`FAREBI.md`](../FAREBI.md) · **Phase:** 5 · **Depends on:** 02, 03
**Status:** ⬜ Not started

> These are the beautiful ideas. Build them fast, run them through the harness, and delete them
> without regret if the numbers say so. Low coverage is acceptable and expected here; zero
> separation is not.

## Objective

Implement the conditional signals with deliberately low expectations, so that the ones which
do work become free upside and the ones which do not cost us two days instead of two months.

## Scope

### `signals/rppg.py` (still-image mode) — blood perfusion map

In a single image there is no temporal pulse, but the **spatial** distribution of blood
perfusion follows vascular anatomy. Green channel is most haemoglobin-sensitive
(oxyhaemoglobin peaks ≈540 nm).

- Region expectations: cheeks 0.9, nose tip 0.85, forehead centre 0.7, nose bridge 0.5,
  chin 0.4 (relative perfusion intensity).
- Checks: cheek-vs-chin ratio, nose-tip-vs-bridge ratio, and per-region micro-variance
  (real skin has capillary structure: std ≈8–25; AI skin is often <5 (too smooth) or >35
  (noise)).
- **Run it through the harness with low expectations. If it gets AUC 0.58, kill it and move on.**

### `signals/scleral.py` — scleral vein topology

Scleral vasculature follows **Murray's Law**: at a bifurcation, the cube of the parent
diameter equals the sum of the cubes of the daughter diameters (`r_parent³ = Σ r_daughter³`).

- Segment vessels on the sclera mask (green-channel vesselness / Frangi filter), skeletonise,
  extract branch points.
- Checks: vasculature present at all; branching angles plausible; Murray's Law residuals;
  topological validity (no crossing vessels, no unnatural dead-ends).
- **Enable only when the eye crop is ≥80px wide.** Expect low coverage — that is fine, use
  `quality` to signal reliability.

### `signals/weather.py` — submission consistency

**Forget EXIF.** Browsers and apps strip GPS. Have the SDK send
`{gps, device_time, server_time, ip}` in `sdk_meta`.

- Run an **indoor/outdoor classifier first**; only fire the weather check outdoors.
- Estimate lighting from the image (colour temperature, shadow direction/ratio, solar
  altitude) and cross-reference against a weather API for the claimed location and time.
- Reframe the value: it catches **non-deepfake fraud** too — GPS says Lagos, IP says Moscow,
  lighting says midnight. Low weight, high value as a reviewer hint.
- Frame the reason code as **submission consistency**, never as "this image is fake".

### `signals/metadata.py` — EXIF forensics

**Context, never proof.** Reports: metadata present/absent, software tags, inconsistent
timestamps, re-encode traces. Every reason code emitted by this signal must carry
`direction: neutral` and an explicit limitation: *"No trustworthy capture metadata was
available. This is not evidence of manipulation."*

### `signals/geometry.py`

Landmark symmetry, iris/pupil ratio consistency, interocular plausibility, head-pose vs.
eye-gaze consistency. Cheap; may be weak; measure it.

## Key decisions

1. **Two days maximum per signal before the harness runs.** This is the phase where the
   discipline matters most, because these are the ideas people get attached to.
2. **`direction: neutral` for all metadata reasons.** Enforced by a test on
   `signals/metadata.py` — no reason code from that module may push toward fake.
3. **Coverage below 0.5 is acceptable here** if the signal is BENCH-tier and fires only when
   applicable. It is a bonus, not a pillar.

## Exit gate

- [ ] All five modules implement `Signal` with correct `preflight`/`min_requirements` gating.
- [ ] Each has a harness report with `cross_source_auc`, `auc_std`, `coverage`,
      `per_feature_auc`.
- [ ] Killed signals are **deleted from the tree**, with the AUC and reason recorded in
      `RISK_REGISTER.md` and `artifacts/signal_registry.json`.
- [ ] `signals/metadata.py` emits only `neutral` reason codes (test-enforced).
- [ ] `signals/weather.py` gates on an indoor/outdoor classifier before firing.
- [ ] `signals/scleral.py` reports `applicable=False` below 80px eye width (test-enforced).

## Risks

| Risk | Mitigation |
| --- | --- |
| Attachment to elegant ideas overrides the numbers | The registry blocks `kill`-status signals from fusion mechanically |
| Still-image rPPG has near-zero separation | Expected. Budget two days, kill, move on. |
| Weather signal creates false fraud accusations from stale GPS | Low weight, reviewer hint only, never an automatic verdict driver |
| Scleral vessel segmentation is noisy on low-res eyes | Hard 80px gate; `quality` scales contribution down |
