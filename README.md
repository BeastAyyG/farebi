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

Phase 01 (foundation) is implemented: repository skeleton, config layer,
PII-safe logging, upload security boundary, face/landmark capture, and an
**empty** orchestration pipeline that one image can traverse end-to-end.
No detection logic exists yet, on purpose.

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

* No detection logic yet. Every verdict from the foundation pipeline is
  `None`; `unable_to_assess` is emitted only for inputs that cannot be captured.
* Face-mesh landmark index groups in `capture/landmarks.py` are approximate and
  will be refined during Phase 04 signal work.
* Fairness slices are not yet measurable: that requires the Phase 03
  self-capture campaign.

## License

MIT — see [`LICENSE`](./LICENSE).
