# 01 — Foundation

**Parent:** [`FAREBI.md`](../FAREBI.md) · **Phase:** 0 · **Depends on:** nothing
**Status:** ✅ Gate passed (2026-09-05)

## Objective

Stand up a repository where **one image can traverse an empty pipeline end-to-end**. No
detection logic yet. The goal is to prove the skeleton, the config system, the upload
security boundary, and the face/landmark capture layer are all sound before any signal work
begins.

## Scope

### Repository skeleton

- `pyproject.toml` — project `farebi`, `src/` layout, pinned dev + prod extras,
  `ruff`/`mypy`/`pytest` config, **import-linter contract enforcing §6 layering**.
- `uv.lock` — generated and committed.
- `Makefile` — `install`, `lint`, `type`, `test`, `train`, `harness`, `serve`, `ui`, `docker`.
- `.env.example`, `.gitignore`, `.dockerignore`, `LICENSE`, `README.md`.
- `configs/` — `app.yaml`, `labels.yaml`, `model.yaml`, `training.yaml`, `thresholds.yaml`,
  `signals.yaml` (created empty-but-valid; populated by later phases).
- `artifacts/{models,calibration,reports}/.gitkeep`, `artifacts/model_registry.json`.
- `data/{raw,interim,processed}/.gitkeep`, `data/README.md`.

### `src/farebi/core/` (L0)

| File | Responsibility |
| --- | --- |
| `config.py` | `pydantic-settings` loader merging `.env` + `configs/*.yaml`. Single `Settings` object; no module reads `os.environ` directly. |
| `constants.py` | Verdict enum, `CaptureType`, magic-byte signatures, size/pixel caps. |
| `logging.py` | `structlog` with a **PII-safe processor** that redacts image bytes, EXIF values, and raw paths from every log record. Logs `request_id` on every line. |
| `reason_codes.py` | Canonical `ReasonCode` enum + `Direction` (`toward_fake` / `toward_real` / `toward_uncertain` / `neutral`) + `Signal` dataclass with a mandatory `limitation` field. |
| `security.py` | Upload validation rules (pure functions, no I/O). |
| `seed.py` | `set_seed()` for python, numpy, torch. |

### `src/farebi/utils/` (L0)

| File | Responsibility |
| --- | --- |
| `image_io.py` | Safe decode: magic-byte sniff, format allowlist (JPEG/PNG), pixel-dimension cap, single-frame enforcement (`PIL.n_frames`), EXIF orientation correction, corrupt-file rejection. |
| `hashing.py` | `sha256` for files, tensors, and config dicts. |
| `artifacts.py` | Versioned load/save against `artifacts/`; every save writes a sidecar with git SHA, package versions, and timestamp. |

### `src/farebi/capture/` (L1)

| File | Responsibility |
| --- | --- |
| `face_mesh.py` | MediaPipe Face Mesh wrapper — 478 landmarks including the 10 iris points (468–477). Chosen over dlib specifically for iris localisation, which `corneal.py` and `scleral.py` both need. |
| `landmarks.py` | Named ROI extractors: forehead, left/right cheek, nose bridge/tip, chin, sclera, per-eye cornea. Returns masks + crops. |
| `quality.py` | Blur (Laplacian variance), exposure, face bbox size in px, inter-ocular distance in px, eye width in px, occlusion estimate. Emits the `quality` dict consumed by `Capture`. |
| `capture.py` | Builds the `Capture` dataclass from a decoded image. **This is the only place a `Capture` is constructed.** |

### `src/farebi/inference/pipeline.py`

An **empty orchestrator**: steps in order, each a no-op returning a typed placeholder, with
the full type signatures from `FAREBI.md` §3.2. Proves the shape before the substance.

### `scripts/smoke_test.py`

Fixes one test image, runs it through the pipeline, asserts a well-formed result object.

## Key decisions

1. **MediaPipe, not dlib.** Iris landmarks are required by two Tier-1/3 signals and dlib
   cannot provide them. This decision is made now so it does not get relitigated later.
2. **Import-linter in CI from day one.** The layering rules in `FAREBI.md` §6 are enforced
   mechanically, not by good intentions. Cheap now, expensive to retrofit.
3. **`Capture` construction is centralised.** Signals receive a `Capture`; they never
   re-detect faces. Keeps signal plugins cheap and testable.
4. **No EXIF in logs, ever.** Enforced by the logging processor, not by reviewer diligence.

## Exit gate

- [x] `make install` succeeds from a clean environment.
- [x] `make lint` and `make type` pass with zero errors.
- [x] Import-linter enforces: no `signals.* → signals.*`, no `api → harness|evaluation`, no
      layer skipping.
- [x] One JPEG and one PNG traverse the empty pipeline and produce a well-formed result.
- [x] A corrupt file, an oversized file, an oversized-dimension file, a multi-frame GIF
      renamed `.jpg`, and a PDF renamed `.png` are all **rejected** with distinct codes.
- [x] No image bytes or EXIF values appear in logs (verified by a test asserting on captured
      log records).
- [x] `README.md` documents install and the smoke-test command.

### Evidence (2026-09-05)

- `pytest -m "not slow"` → **167 passed**.
- `ruff check .` → All checks passed · `ruff format --check .` → 59 files formatted.
- `mypy --strict src` → Success: no issues found in 30 source files.
- `importlinter` → 2 contracts kept, 0 broken.
- `python scripts/smoke_test.py` → **SMOKE TEST PASSED** (9 distinct rejection codes).
- MediaPipe 0.10.35 API break handled via a two-backend adapter (`solutions`|`tasks`);
  `face_landmarker.task` (3,758,596 bytes) downloaded to `artifacts/models/`.
- Note: installed with `pip install -e ".[dev,face]"` rather than `uv`; no `uv.lock`
  committed (lockfile tooling is a later-phase concern). `make install` uses pip.

## Risks

| Risk | Mitigation |
| --- | --- |
| MediaPipe adds a heavy dependency and can be awkward on some Python versions | Pin it; provide a `--no-face-mesh` degraded mode so the pipeline still runs in CI |
| Over-engineering the skeleton before any signal exists | Hard rule: no file in this phase contains detection logic. The pipeline is empty on purpose. |
