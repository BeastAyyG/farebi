# 05 — Tier-2 Signals (Video rPPG + Active Illumination)

**Parent:** [`FAREBI.md`](../FAREBI.md) · **Phase:** 4 · **Depends on:** 02, 03, 04
**Status:** ⬜ Not started

> This phase is where the project stops being "detect a fake image" and becomes "verify a live
> human in front of a real sensor" — a fundamentally easier problem. It requires the capture
> SDK to be extended to send short video and to actively control the screen illumination.

## Objective

Add the two signals that no still-image attacker can satisfy passively: a real cardiac pulse
extracted from video, and skin that responds correctly to light **we control**.

## Scope

### `signals/rppg.py` (video mode)

- **Use POS or CHROM algorithms, not raw green-channel averaging.** Both are ~20 lines and
  far more robust to motion and lighting. Start from `pyVHR`, validate, then reimplement.
- Bandpass 0.7–3.5 Hz (≈42–210 BPM), `filtfilt` to avoid phase distortion, Welch PSD.
- Liveness checks: (1) clear dominant peak, SNR > 3.0; (2) BPM physiologically plausible,
  45–180; (3) **cross-region agreement** — forehead and cheek must show the same heart rate
  (within 8 BPM). Blood flows everywhere simultaneously; a fake shows random per-region rates.
- Requirements declared in `min_requirements`: `needs_video: True`, `min_frames: 100`,
  `min_fps: 20`, `min_face_px`, `min_light`.

### `signals/sss_active.py` — active illumination

The single highest-value change available to us, because **we control the capture app**:

1. Capture two frames 100 ms apart: screen dark → screen bright white (or front flash).
2. The **difference image isolates our own light source** and cancels ambient lighting.
3. From that difference: subsurface scattering at shadow boundaries (light entering skin and
   exiting elsewhere → characteristic warm bleeding at the lit/shadow transition), specular vs
   diffuse skin response, and a crude 3D shape cue — a flat screen replay lights uniformly, a
   real face does not.
4. **Random colour sequence upgrade:** flash a random colour sequence and check the face
   reflects the matching colours in the right order. This defeats pre-recorded and injected
   video outright — a replay cannot predict a sequence that does not exist yet.

This one change converts three weak passive signals (SSS, corneal reflection, 3D geometry)
into strong active ones.

### `degradation/replay.py` (extension)

Extend the replay simulator to cover injected video (virtual camera) and recorded replay, so
the harness has something to measure against.

### SDK contract additions

`src/farebi/api/schemas.py` gains an optional `capture_bundle` upload: still frame + frame
sequence + `fps` + `sdk_meta` (device attestation, GPS, device time, server time).

## Fairness — a legal requirement, not a nice-to-have

> **rPPG SNR drops on darker skin.** This is documented, measurable, and if unhandled it
> silently rejects people.

- Measure FPR per Fitzpatrick skin-type bucket (and by age, glasses, makeup).
- If a bucket is worse, **lower the signal's weight for low-SNR captures via the `quality`
  field** — do not let it reject people.
- Report the per-bucket table in `MODEL_CARD.md`. No bucket may exceed 1.5× overall FPR.

## Key decisions

1. **Validate the pulse extractor on real humans first.** On UBFC-rPPG, PURE, and COHFACE —
   which have ground-truth HR — before ever pointing it at a fake. If HR error is ≥5 BPM on
   real people, the signal is dead and we should learn that cheaply.
2. **Active illumination is opt-in but strongly preferred.** Where the SDK cannot do it, the
   signal reports `applicable=False` and the fusion proceeds on degraded evidence with lower
   `quality`.
3. **rPPG is asynchronous.** It is far too slow for a synchronous request — it routes through
   the Celery worker (phase 08).

## Exit gate

- [ ] HR error < 5 BPM on UBFC-rPPG (validated before any fake is scored).
- [ ] Deepfake-video AUC ≥ 0.75 on a held-out generator.
- [ ] Replay attacks separated with **AUC ≥ 0.90** by the active-illumination signal.
- [ ] Random colour-sequence challenge defeats 100% of tested pre-recorded and injected
      replays.
- [ ] Per-Fitzpatrick-bucket FPR table produced; no bucket > 1.5× overall.
- [ ] Harness report exists for both signals, including coverage on real capture conditions.

## Risks

| Risk | Mitigation |
| --- | --- |
| Users move, and rPPG needs a still face | SDK UX: "Hold still for a moment", ≥5 s, plus motion gating in `quality` |
| Dark rooms and poor lighting kill the signal | Enforce a minimum luminance in capture UX; report `applicable=False` below it |
| Active illumination degrades UX (bright flash in the face) | 100 ms, ramp rather than hard flash; A/B the drop-off rate before committing |
| Injected video bypasses the camera entirely | Device attestation (Play Integrity / App Attest) + virtual-camera detection in the SDK — **outside the image pipeline entirely** |
