# 02 — The Signal Factory

**Parent:** [`FAREBI.md`](../FAREBI.md) · **Phase:** 1 · **Depends on:** 01
**Status:** ⬜ Not started

> This is the most important phase in the project. Get it right and every future signal is a
> one-day job that gets an honest verdict. Get it wrong and the project becomes a pile of
> untestable detectors, each defended by the person who wrote it.

## Objective

Build the machinery that makes signals cheap to write, cheap to measure, and cheap to
delete: the `Signal` contract, the plugin registry, the `KYCDegradation` simulator, and the
go/no-go harness that decides whether a signal lives.

## Scope

### `src/farebi/signals/base.py`

The contract, verbatim from `FAREBI.md` §5:

```python
@dataclass
class Capture: ...          # image_bgr, face_box, landmarks, quality,
                            # video_frames, fps, sdk_meta, capture_type
@dataclass
class SignalOutput: ...     # features, applicable, quality, explanation,
                            # reason_codes, artifacts
class Signal(ABC):
    name: str
    tier: int
    min_requirements: dict
    requires: list[str]
    def preflight(self, cap) -> bool
    @abstractmethod
    def run(self, cap) -> SignalOutput
```

Plus two helpers every plugin uses:
- `require(cap, **kwargs)` — evaluates `min_requirements` against `Capture.quality` and
  returns a `SignalOutput` with `applicable=False` when unmet. **Never raises.**
- `reason(code, direction, strength, message, limitation)` — builder that refuses to
  construct a reason code whose `limitation` is empty.

### `src/farebi/signals/registry.py`

- Auto-discovery: import every module in `signals/`, collect `Signal` subclasses.
- `get(name)`, `tier(n)`, `all_enabled()`, `preflight_all(cap) -> dict[str, bool]`.
- `enabled` is read from `configs/signals.yaml`, which records for each signal:
  `tier`, `enabled`, `min_requirements`, `requires`, and `harness_status`
  (`keep` / `bench` / `kill` / `unmeasured`).
- **A signal with `harness_status != keep|bench` is not wired into fusion.** Enforced in code.

### `src/farebi/degradation/kyc_pipeline.py`

```python
class KYCDegradation:
    """Simulate what a real KYC app does to an image before our server sees it."""

    # 1. resize to long edge ∈ {720, 960, 1080, 1280} (INTER_AREA | INTER_LINEAR)
    # 2. JPEG q ∈ [80, 95]        (camera app)
    # 3. exposure/white-balance jitter: α ∈ [0.9, 1.1], β ∈ [-10, 10]
    # 4. Gaussian blur σ ∈ [0.3, 1.0] with p = 0.3   (hand shake / focus hunt)
    # 5. JPEG q ∈ [70, 90]        (upload SDK re-encode — the killer)
```

- Applied to **real and fake identically**, randomly sampled per image.
- Ranges are config-driven (`configs/training.yaml`) so they can be recalibrated once real
  production uploads are available.
- Deterministic under a seed for reproducibility.

### `src/farebi/degradation/replay.py`

Screen-replay simulation: downscale to a display resolution, add moiré at a pixel pitch,
apply a display colour gamut, add a specular sheen rectangle, flatten depth. Used to build
the replay-attack evaluation set. Exists because **PRNU is meaningless without it** (§04).

### `src/farebi/harness/`

| File | Responsibility |
| --- | --- |
| `splits.py` | `GroupKFold` over `source_group` (generator family / camera set). Never a random split. |
| `evaluate_signal.py` | Runs a signal over `(Capture, label, source_group)` samples; returns `coverage`, `cross_source_auc`, `auc_std`, `per_feature_auc`. |
| `gono.py` | Applies the rule: **KEEP** `auc ≥ 0.65 AND coverage ≥ 0.50` · **BENCH** `auc ≥ 0.60` · **KILL** otherwise. Writes `artifacts/signal_registry.json`. |
| `report.py` | One markdown + JSON report per signal per dataset version, written to `artifacts/reports/harness/`. Includes the per-feature AUC table so we can see *which* feature carries the signal. |

### `scripts/run_harness.py`

`run_harness.py --signal fft` or `--all`. Prints the table, writes the registry, exits
non-zero if any signal marked `enabled` is `kill`.

## Key decisions

1. **The harness is the arbiter, not the author.** The two-day rule is enforced socially and
   by the registry: a signal cannot enter fusion without a report.
2. **Coverage is measured, never assumed.** A signal with 0.90 AUC that runs on 8% of
   uploads is a bonus, not a pillar.
3. **`per_feature_auc` is mandatory output.** It is how we discover that one carefully
   engineered feature is doing all the work and nine others are noise.
4. **Degradation is not optional in training.** If a signal is trained or tuned on
   non-degraded images, its harness report is invalid.

## Exit gate

- [ ] A deliberately trivial stub signal (random features) passes through the harness and is
      reported as **KILL** — proving the gate bites.
- [ ] A deliberately strong stub signal (a feature correlated with the label on degraded
      data) is reported as **KEEP** — proving the gate is not just rejecting everything.
- [ ] `configs/signals.yaml` blocks a `kill`-status signal from entering fusion (tested).
- [ ] `KYCDegradation` is deterministic under a fixed seed (golden hash test).
- [ ] Harness splits by source group — verified by a test that asserts every fold's test
      groups are disjoint from its train groups.
- [ ] `artifacts/signal_registry.json` is written with version + git SHA.

## Risks

| Risk | Mitigation |
| --- | --- |
| The harness is slow to run on the full dataset | Sample-based mode for iteration; full run only for the registry write |
| `auc_std` is ignored in practice | Surface it in the report next to the mean; high std = fragile, flag in `RISK_REGISTER.md` |
| Degradation ranges are guesses until real uploads exist | Config-driven from day one; recalibrate in phase 03 |
