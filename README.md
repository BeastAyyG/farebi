# Farebi

**A KYC deepfake / manipulated-face risk-signal service.**

Farebi takes one uploaded face image and returns one of four verdicts:

| Verdict | Meaning |
| --- | --- |
| `likely_real` | Calibrated manipulation probability is below the low band. |
| `likely_fake` | Calibrated manipulation probability is above the high band. |
| `uncertain` | Inside the band, out-of-distribution, or signals disagree. **Route to human review.** |
| `unable_to_assess` | Invalid, corrupt, no face, face too small, or unusable quality. |

> **Farebi is a risk signal, never an autonomous rejection engine.**
> NIST identity guidance is explicit that automated media analysis must be
> combined with manual review and capture/liveness controls. "I don't know —
> here is exactly why, and a human will look" is a first-class output of this
> system, not a failure state.

## Status

Phases 00–02 are done (foundation, signal factory + harness). Tier-1 signals
are implemented and have passed through the go/no-go harness once
(`quick256`, n=407, degraded-mode, `n_splits=2`):

| Signal | AUC | Verdict |
| --- | --- | --- |
| `prnu.py` | 0.907 | **KEEP** |
| `chromatic_aberration.py` | 0.884 | **KEEP** |
| `texture.py` | 0.875 | **KEEP** |
| `replay_detect.py` | 0.862 | **KEEP** |
| `fft.py` | 0.730 | **KEEP** |
| `corneal.py` | 0.544 | **KILLED** — deleted, see `RISK_REGISTER.md` KILL-01 |
| `geometry.py` | 0.559 | **KILLED** — deleted, see `RISK_REGISTER.md` KILL-02 |
| `vit_clip.py` | n/a | Environmental kill (no torch) — kept as Phase-06 re-entry slot |

Phase 04's gate (≥2 of {PRNU, corneal, CA} survive) passes via PRNU + CA.
Still open before the gate fully closes: `models/` + train/evaluate scripts,
the no-hardcoded-thresholds lint rule, and CA/PRNU re-validation on
high-res + laundered data.

Full plan: [`FAREBI.md`](./FAREBI.md) · Checklist: [`PROGRESS.md`](./PROGRESS.md) ·
Sub-plans: [`PLANS/`](./PLANS)

## Install

Requires Python 3.11–3.13.

```bash
make install          # runtime + dev + MediaPipe
make install-minimal  # runtime + dev, no MediaPipe (degraded CI mode)
```

Or manually:

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev,face]"   # Windows
.venv/bin/python     -m pip install -e ".[dev,face]"   # macOS/Linux
```

MediaPipe is optional. With `FAREBI_CAPTURE__FACE_MESH__ENABLED=false` (or
without the package installed) the pipeline still runs — it simply reports
`LANDMARKS_UNAVAILABLE` and returns `unable_to_assess`.

## Run the smoke test

```bash
make smoke
# or
python scripts/smoke_test.py
```

This synthesises a test image, pushes it through the full pipeline, and asserts
that a well-formed result object comes out. It then runs the hostile-upload
rejection matrix and prints a PASS/FAIL table.

## Reviewer frontend

The reviewer console lives in [`frontend/`](./frontend) — React + TypeScript +
Vite, talking to the API over HTTP only. It implements
[`frebi.md`](./frebi.md) in full: verdict, calibrated probability, confidence,
per-signal explanations *with their limitations*, the attribution heatmap and
its mandatory caveat, quality warnings, artefact versions, and the persistent
privacy notice.

```bash
make ui-install     # npm install
make ui             # dev server on :5173
make ui-check       # typecheck + contrast audit + render smoke test
```

`frontend/.env.example` ships with `VITE_MOCK_API=true`, so the whole UI —
every verdict and every error state — is demoable before the API exists. See
[`frontend/README.md`](./frontend/README.md) for the requirement-to-file map
and [`frontend/DESIGN.md`](./frontend/DESIGN.md) for the palette rationale.

## Verify

```bash
make check    # lint + type + test + smoke
make lint     # ruff + import-linter (layer enforcement)
make type     # mypy --strict
make test     # pytest
```

## Configuration

Single `Settings` object, built from `configs/*.yaml` and overridden by
`FAREBI_*` environment variables (see [`.env.example`](./.env.example)).

```
FAREBI_APP__LOG_LEVEL=DEBUG
FAREBI_CAPTURE__FACE_MESH__ENABLED=false
FAREBI_UPLOAD__MAX_BYTES=8388608
```

Priority: init kwargs > environment > `.env` > `configs/*.yaml` > defaults.

## Architecture

Two runtimes over one codebase (see `FAREBI.md` §3):

```
OFFLINE FACTORY ──▶ ARTIFACTS ──▶ ONLINE SERVING
(scripts, harness)   (versioned,   (api, inference)
                      hashed)
```

Layers are enforced mechanically by `import-linter` and by
`tests/unit/test_layering.py`:

```
L5  api, monitoring
L4  inference, explain
L3  models, fusion
L2  signals/*          <- plugins are leaves; may not import each other
L1  capture, degradation, data
L0  core, utils
OFFLINE  harness, evaluation   <- never imported by serving code
```

## Privacy and safety

* Uploaded images are **not retained**. They are decoded in memory and dropped.
* No image bytes, EXIF values, or raw filesystem paths are ever logged. This is
  enforced by a structlog processor (`core/logging.py`), not by convention, and
  asserted by `tests/security/test_upload_security.py`.
* Uploaded filenames are never used as storage paths — we generate our own.
* Metadata (EXIF) is reported as **context only, never proof**. Absence of EXIF
  is not evidence of manipulation.

## Known limitations

* No fusion, calibration, or API yet. Signals emit features; nothing produces
  a verdict — the serving pipeline is still the foundation stub that returns
  `None` / `unable_to_assess`.
* Harness numbers above are directional (256px research data, 2 source groups
  per class). CA and PRNU must be re-validated on high-res + laundered data
  before Phase 04's gate fully closes.
* Face-mesh landmark index groups in `capture/landmarks.py` are approximate.
* Fairness slices are not yet measurable: that requires the Phase 03
  self-capture campaign.

## License

MIT — see [`LICENSE`](./LICENSE).
