# Self-capture campaign — protocol

**Status:** recruiting not started — this kit unblocks it.
**Acceptance bars (from `PLANS/03-data.md` exit gate):** ≥300 real self-captures
and ≥300 screen-replay attacks in the manifest, ≥20 distinct phone models,
consent + provenance recorded in `data/README.md`.

## Why this exists

Public datasets (FFHQ, CelebA-HQ) are web-processed portraits. The false-positive
population that matters is real users holding phones in bad lighting with beauty
filters on. No public set reproduces that, and the fairness gate (Phase 09, no
bucket > 1.5× overall FPR) cannot be measured without it. This campaign has
calendar lead time — start recruiting before the pipeline code is finished.

## 1. Real captures

### 1.1 Per-subject shot list (minimum 12 shots)

| # | Lighting | Accessories / processing | Expression |
|---|----------|--------------------------|------------|
| 1–2 | Indoor daylight, face to window | none | neutral, slight smile |
| 3 | Indoor daylight | glasses (if worn; else skip) | neutral |
| 4 | Indoor artificial (warm lamp) | none | neutral |
| 5 | Outdoor shade | none | neutral |
| 6 | Outdoor direct sun | none | neutral |
| 7 | Low light / dark room, screen glow only | none | neutral |
| 8 | Indoor daylight | makeup as normally worn | neutral |
| 9 | Indoor daylight | strongest beauty filter the subject actually uses | neutral |
| 10 | Indoor daylight | none, arm's-length selfie angle | neutral |
| 11 | Indoor daylight | none, phone on table ~1 m (ID-check framing) | neutral |
| 12 | Backlit (window behind subject) | none | neutral |

Add shots freely (hats, masks below nose, wet hair, night mode) — log them in
`shot_log_template.csv`, never invent new `attack_type` values (taxonomy lives in
`configs/labels.yaml`: these are all `authentic`, except shot 9 which is
`authentic_benign_processed`).

### 1.2 Capture rules

- Shoot through the actual app when a build exists; otherwise the stock camera
  app at full resolution, rear camera preferred, **long edge ≥ 720 px**.
- One subject = one `identity_id` (format `scap-NNNN`). That ID must never appear
  in any other split — `split.py` enforces this, but get it right at the source.
- No identity documents, screens, or other people in frame.
- EXIF (especially GPS) is stripped at ingest by `prepare_data.py`; collectors
  must still avoid photographing addresses,creens with personal data, etc.
- Subjects must be 18+. No exceptions, no parental-consent path — out of scope.

### 1.3 Diversity quotas (recruit against these, not vibes)

- ≥20 distinct phone models across the set (log `device_model` per shot).
- Skin tone spread across the full Fitzpatrick I–VI range — rPPG SNR and several
  Tier-1 features vary with melanin; the Phase-09 gate is unmeasurable without it.
- Age spread 18–70+, facial hair, head coverings worn for religious reasons,
  glasses/contact lenses. Record what is visible in `accessories`, never infer
  ethnicity or religion.

## 2. Screen-replay attacks (≥300)

What real fraudsters do, and the attack class that **defeats PRNU presence**
(a phone photographing a screen is a real camera — see RISK_REGISTER.md).

### 2.1 Procedure

1. Display source fakes fullscreen: quick256 `sdxl`/`flux` sets plus fresh
   InSwapper/SimSwap/roop swaps (old FF++ swaps are too easy — see PLANS/03).
2. Photograph the screen with a *different* phone (never screenshot — a
   screenshot is a digital copy, not a replay; label it `unknown_edit` if it
   happens by accident, never `replay`).
3. Vary: display technology (OLED phone, LCD laptop, tablet), brightness
   (max / medium / low), ambient (dark room / office), capture distance
   (fill frame / 30 cm back), slight angle (±10°).
4. Moiré is signal, not noise — do **not** "fix" exposure to remove it.
   `replay_detect.py` eats moiré for breakfast; starving it during collection
   would be self-sabotage.

### 2.2 Labels

- `attack_type=replay`, `capture_type=replay`, `generator_family=<source fake's
  family>+replay` (e.g. `sdxl-replay`) so the harness can hold replay out as its
  own group. `identity_id` = the fake's identity if known, else `replay-NNNN`.
- Virtual-camera / injected-video attacks are a **separate** class (`injection`,
  cf. RISK_REGISTER.md INJECT) — do not mix them into the replay count.

## 3. QC checklist (every shot, before it enters `raw/`)

- [ ] Face detectable by the production detector (or MediaPipe fallback).
- [ ] Eye width ≥ 40 px at full res (else the capture gate would reject it anyway).
- [ ] No second face, no ID document, no legible screen text in frame.
- [ ] Shot-log row filled: all 8 manifest columns + session extras.
- [ ] Consent form signed and filed (see `CONSENT_TEMPLATE.md`); subject ID
      entered in the consent log the same day — same-day, no backlog.

## 4. Withdrawal / purge

Consent is revocable. On withdrawal: delete the subject's `raw/` files,
`interim/` derivatives, and manifest rows within 5 working days, confirm in
writing, record the purge (date, scope, confirmer) in `data/README.md`. Splits
and reports generated afterwards must be re-emitted — never edit a released
split CSV in place.

## 5. What happens after collection

`scripts/prepare_data.py` (Phase 03) ingests `raw/` + shot logs → EXIF strip →
face crop/align → `KYCDegradation` on 100% of rows → manifest rows in the
enforced schema (`data/manifests/schema.json`). Collectors only need this kit +
the shot-log template; everything downstream is pipeline code.
