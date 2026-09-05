# 03 — Data

**Parent:** [`FAREBI.md`](../FAREBI.md) · **Phase:** 2 · **Depends on:** 01, 02
**Status:** ⬜ Not started

> Every number the project ever reports is bounded by the quality of this phase. A model
> trained on pristine FFHQ reals versus PNG fakes will score 99% and be worthless in
> production. This phase exists to make that outcome impossible.

## Objective

Produce identity-disjoint, source-grouped, degradation-consistent data splits, a schema-validated
manifest, an automated leakage/shortcut audit, and the beginning of the self-capture campaign.

## Scope

### `data/manifests/schema.json`

Enforced schema for the manifest. Required columns:

```
image_path, binary_label, attack_type, source_dataset, generator_family,
identity_id, capture_type, split
```

- `attack_type` must come from the taxonomy in `configs/labels.yaml`
  (`real`: authentic, authentic_benign_processed · `fake_or_manipulated`: fully_synthetic,
  face_swap, face_morph, localized_edit, identity_altering_retouch · `ambiguous`:
  unknown_edit, heavy_beauty_filter).
- `generator_family` is **mandatory** — it is what the harness groups on.
- `identity_id` is **mandatory** — it is what keeps splits disjoint.
- `data/manifests/sample_manifest.csv` ships as the worked example.

### `src/farebi/data/`

| File | Responsibility |
| --- | --- |
| `manifest.py` | Load, validate against schema, normalise paths, reject unknown `attack_type`/`generator_family`. Emits a validation report, not an exception storm. |
| `split.py` | Grouped splitting: **no `identity_id` in two splits**, and at least one whole `generator_family` reserved for `test_unseen_generator.csv`. Deterministic under seed. |
| `dataset.py` | `torch` Dataset yielding `(image, label, meta)` with `KYCDegradation` applied at load time. |
| `transforms.py` | Train-time augmentation (geometric + photometric only — no JPEG artefacts here; that is `KYCDegradation`'s job). |
| `validators.py` | **The shortcut audit.** See below. |

### `src/farebi/data/validators.py` — the shortcut audit

Automated checks that run on every dataset version and fail loudly:

1. **Identity leakage** — any `identity_id` present in more than one split.
2. **Source/class confounding** — the chi-square / mutual-information score between
   `source_dataset` and `binary_label`. If one source is all-real and another all-fake, the
   model will learn the source, not the manipulation.
3. **Format confounding** — file extension, file size, and bit-depth distributions per class.
   Catches "PNG = fake".
4. **Metadata confounding** — fraction of rows with EXIF per class. Catches accidental
   metadata detectors. (Training data is EXIF-stripped by default; this verifies it.)
5. **Duplicate detection** — perceptual hash collisions across splits.
6. **Resolution confounding** — per-class resolution distributions.

Each check emits `PASS` / `WARN` / `FAIL`. `FAIL` blocks training.

### `scripts/`

| Script | Responsibility |
| --- | --- |
| `prepare_data.py` | raw → interim → processed. Face detection, crop/align, **EXIF strip by default**, `KYCDegradation` for the processed set, manifest row emission. |
| `generate_splits.py` | Writes `data/splits/{train,validation,calibration,test_known,test_unseen_generator}.csv`. |
| `audit_dataset.py` | Runs `validators.py` and prints/writes the shortcut-audit report to `artifacts/reports/dataset_audit.md`. |

### Data sources to acquire

| Need | Source | Critical note |
| --- | --- | --- |
| Real (baseline) | FFHQ, CelebA-HQ, VGGFace2 | Already web-processed — still run through `KYCDegradation` |
| Real (**critical**) | **Own captures** | 200–500 consenting people, ≥20 phone models, indoor/outdoor, through the actual app. Include glasses, makeup, beauty filters, dark rooms — **this is the false-positive population** |
| GAN fakes | Self-generated StyleGAN2/3 | Vary truncation ψ — low-ψ faces are "too perfect" and easy; high-ψ are harder |
| Diffusion fakes | SD 1.5 / SDXL / Flux, Midjourney sample set | Prompts like "passport photo, plain background, neutral expression" — a fantasy background is trivially easy |
| Face swaps | FaceForensics++, Celeb-DF v2, DFDC + fresh InSwapper/SimSwap/roop | Old datasets are too easy; current open-source swappers are mandatory |
| Held-out generators | **DF40** (40 deepfake techniques, plugs into the DeepfakeBench workflow) | The cross-generator eval set — absent from train/val/calibration by construction |
| In-the-wild | **Deepfake-Eval-2024** (real-world 2024 content) | Academic-benchmark SOTAs lost ~45% image-AUC here; this is the ceiling check |
| Replay attacks | Photograph fakes off phone/laptop screens; virtual camera | What real fraudsters do. **Defeats PRNU** — see §04 |
| rPPG validation | UBFC-rPPG, PURE, COHFACE | Ground-truth HR: validate the pulse extractor on real people first |
| PRNU validation | VISION, Dresden Image Database | Many real devices for noise-presence calibration |

### `data/README.md`

Provenance, licence, and consent status for **every** source. No undocumented data enters
the repo. Consent status for the self-capture set is recorded here and nowhere else.

## Key decisions

1. **Hold out one entire generator.** All Flux images (or equivalent) never touch training.
   The headline number is AUC on that set.
2. **Calibration split is sacred.** It is never trained on, and never used for model
   selection. It exists solely for probability calibration and the conformal band.
3. **The self-capture campaign starts in this phase, not later.** It has a long calendar lead
   time and it blocks the fairness gate in phase 09. Start recruiting now.
4. **Validate rPPG on real humans before using it on fakes.** If the pulse extractor cannot
   recover ground-truth HR on UBFC, the signal is dead on arrival and we should find out
   cheaply.
5. **Train neural baselines on paired real↔fake frames from the same source video.**
   GenD (WACV 2026, `vendor/GenD`) shows unpaired training invites shortcut learning
   and destroys cross-dataset generalisation; paired training is the single biggest
   lever. Enforce pairing in `generate_splits.py` and assert it in a test.

## Exit gate

- [ ] `train/validation/calibration/test_known/test_unseen_generator` splits exist, with zero
      `identity_id` overlap (asserted in a test, not just checked once).
- [ ] At least one `generator_family` is fully absent from train/validation/calibration.
- [ ] `audit_dataset.py` reports **zero FAIL** on the current dataset version.
- [ ] Format, metadata, and source confounding checks all PASS or are explicitly documented
      as accepted WARN in `RISK_REGISTER.md`.
- [ ] `KYCDegradation` applied to 100% of processed images, both classes.
- [ ] ≥300 real self-captures in the manifest.
- [ ] ≥300 screen-replay attacks in the manifest.
- [ ] `data/README.md` lists provenance + licence + consent for every source.

## Risks

| Risk | Mitigation |
| --- | --- |
| Self-capture recruitment is slow and blocks everything | Start in this phase; treat ≥20 phones and diverse lighting as the acceptance bar |
| Licence terms on public datasets restrict commercial KYC use | Record licence per source in `data/README.md`; do not ship a model trained on non-commercial data |
| Reals and fakes differ in resolution in ways we cannot fully correct | `validators.py` measures it; `KYCDegradation` narrows it; document residual risk in `MODEL_CARD.md` |
