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

## Caveats (from the research map)
1. Most eye/rPPG papers were validated on GANs / 2020-era swaps. Diffusion
   generators (Flux, SDXL) have better eyes — expect weaker corneal/rPPG signal
   there. Always re-measure on a **held-out** diffusion generator via the harness.
2. Repo hygiene: DeepfakeBench upstream is Python 3.7 — prefer `CVDeepfakeBench`.
   `pyVHR` has heavy deps; `rPPG-Toolbox` is better maintained.
