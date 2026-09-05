# vendor/ — Confined reference repositories

**Purpose.** This folder holds *cloned* research code referenced by the signal
design in `farebi plan.txt` / `FAREBI.md` §11 and the research map. It exists so
that signal implementations in `src/farebi/signals/` can be *adapted from* proven
code rather than re-derived.

**Hard rule — confinement.** Everything in this folder stays here.
- Nothing under `vendor/` is imported by `src/`. `src/` implements the `Signal`
  contract; `vendor/` is read-only reference material. Importing from `vendor/`
  would break the layering in `FAREBI.md` §6 and is forbidden.
- These repos are **not** part of the package. They are gitignored from the main
  repo and never shipped.
- Each clone is shallow (`--depth 1`, blobless) to minimise footprint.

**Re-clone / update.** `bash clone_all.sh` (idempotent — skips existing repos).

## Cloned repositories (mapped to signals)

| Folder | Source | Mapped signal(s) |
| --- | --- | --- |
| `DeepfakeBench` | SCLBD/DeepfakeBench | Offline harness adapter, data loaders, metrics |
| `CVDeepfakeBench` | alexsabb/CVDeepfakeBench | PyTorch 2.x upversion of the above |
| `UniversalFakeDetect` | WisconsinAIVision/UniversalFakeDetect | `vit_clip.py` (CLIP + linear probe baseline) |
| `prnu-python` | polimi-ispl/prnu-python | `prnu.py` (canonical PRNU extractor) |
| `prnu-simpez` | sim-pez/prnu | PRNU with deep denoisers |
| `CameraFingerprint_pytorch` | E0HYL/CameraFingerprint_pytorch | PRNU via DnCNN/FFDNet |
| `prnu-copy-attack` | frassom/prnu-copy-attack | Adversarial test (attack on PRNU) — Week 9 |
| `DeepFakesON-Phys` | BiDAlab/DeepFakesON-Phys | `rppg.py` (physiological deepfake detection) |
| `rPPG-Toolbox` | alinle/rPPG | `rppg.py` (POS/CHROM benchmark) |
| `pyVHR` | phuselab/pyVHR | `rppg.py` (remote-PPG framework) |
| `Awesome-Deepfakes-Detection` | Daisy-Zhang | Literature index (bio-signals, frequency) |
| `Awesome-Deepfake-Gen-Detect` | flyingby | Literature index (2026 survey, AUC expectations) |
| `Awesome-Comprehensive-Deepfake-Detection` | qiqitao77 | Dataset table, moiré/replay papers |
| `AI-Face-FairnessBench` | Purdue-M2 | `evaluation/fairness.py` (Week 9) |
| `GenD` | yermandy/GenD | Alt neural baseline (WACV 2026): LN-tuning (0.03% params) of CLIP/PE/DINOv3 + linear head; weights on HF `yermandy/GenD_*` |
| `synthetic-image-detection` | polimi-ispl/synthetic-image-detection | SD-laundering detectors (WIFS 2024) — read before trusting PRNU on diffusion outputs |

## Caveats (from the research map)
1. Most eye/rPPG papers were validated on GANs / 2020-era swaps. Diffusion
   generators (Flux, SDXL) have better eyes — expect weaker corneal/rPPG signal
   there. Always re-measure on a **held-out** diffusion generator via the harness.
2. Repo hygiene: DeepfakeBench upstream is Python 3.7 — prefer `CVDeepfakeBench`.
   `pyVHR` has heavy deps; `rPPG-Toolbox` is better maintained.
3. **DeepFakesON-Phys: unmerged upstream PR #2 applied locally**
   (`src/vid_to_deepframes_rawframes.py`). The original pre-allocates `np.empty`
   channel cubes and writes frames starting at index 1, so index 0 stays
   uninitialised garbage that then pollutes every mean/std — numerically unstable
   frame tensors. The PR replaces this with list-append + `np.array` +
   vectorised `np.diff`/normalisation. Upstream has not merged it, so on
   re-clone re-apply: `git apply docs/vendor-patches/DeepFakesON-Phys-pr2-vectorisation.diff`
   inside `vendor/DeepFakesON-Phys/`.
4. **SD laundering breaks PRNU presence logic.** `synthetic-image-detection`
   (Mandelli et al., WIFS 2024) shows passing a real photo through an SD
   autoencoder (strength 0) preserves content while masking the camera-model
   artefacts PRNU relies on. A laundered real can therefore read as "no sensor
   noise" (false toward-fake) and a laundered fake keeps its scene. Never use
   PRNU-presence as a real-vs-synthetic gate on diffusion-era content; keep it
   scoped to device-enrolment + replay pairing per the §04 caveat.
5. **prnu-python is pinned and stale.** Upstream pins `numpy==1.23.5`, CI floor is
   Python 3.4–3.9, last commit 2023-02-02, no tags fetched. Our `signals/prnu.py`
   deliberately re-implements the extraction math in numpy+cv2 (Gaussian
   residual + Wiener stages, no pywt/scipy) so the pinned deps never enter our
   tree. Use the vendored copy only as the math reference.
6. **rPPG-Toolbox remote is `alinle/rPPG`** (older lineage), not the NeurIPS 2023
   `uhqfang/rPPG-Toolbox` with RhythmFormer/FactorizePhys. If deep rPPG models
   are needed, clone uhqfang separately; `pyVHR` covers classical POS/CHROM.
7. **Neural-baseline weights are deferred to Phase 06** (no torch in `.venv`
   yet): UnivFD linear-probe weights (ship with `UniversalFakeDetect`),
   GenD HF collection `yermandy/gend` (`GenD_CLIP_L_14`, `GenD_DINOv3_L`, …),
   AIDE hybrid `meet4150/AIDE_image_detector`. GenD's headline finding already
   shapes the data plan: **train on paired real↔fake frames from the same source
   video** — unpaired training invites shortcut learning.
