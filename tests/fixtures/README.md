# `tests/fixtures/` — shared synthetic test inputs

All test data is **synthetic and generated in code** — no real faces, no
downloads, no privacy surface. This is deliberate: the suite must run offline
and deterministically in any CI image, including the `--no-face-mesh` one.

## What lives here

* `synthetic.py` — the generators. Draws a crude front-facing face
  (`synthetic_face_rgb`), encodes it as PNG/JPEG (with optional EXIF
  orientation), and builds the **hostile-upload matrix** (`hostile_cases`) plus
  individual adversarial inputs (oversized, truncated header, disguised magic
  bytes, path-traversal filename, multi-frame APNG, corrupt payload).

## Contract: tests and the smoke script share inputs

`scripts/smoke_test.py` and the test suite import the *same* `hostile_cases`
and `synthetic_face_rgb`. A rejection matrix that differs between CI and the
smoke script proves nothing, so keep all hostile inputs defined once, here.

## Adding a hostile case

1. Add it to `hostile_cases()` with its `(data, declared_type, filename,
   expected_code)` tuple.
2. Pick a `RejectionCode` that is **distinct** from every other case — the
   security tests assert at least six separable failure modes and that nothing
   folds into a generic bucket.
3. `DECODE_FAILED` is special: it is raised at *decode* time, not by
   `validate_upload` (the header is valid, only the pixels are corrupt). Tests
   that branch on `validate_upload` skip it; tests that decode handle it via
   `pytest.raises(ImageDecodeError)`.

## Determinism

`synthetic_face_rgb` seeds `np.random.default_rng(7)`. Changing the seed or the
drawing code changes every downstream hash and face-detection outcome — that is
fine for shape tests, but keep it stable within a phase so failure diffs are
meaningful.
