# PLANS — Sub-plan Registry

**Parent:** [`FAREBI.md`](../FAREBI.md) · **Checklist:** [`PROGRESS.md`](../PROGRESS.md)

Sub-plans hold file-level detail. `FAREBI.md` holds architecture and coordination.
If these ever disagree, `FAREBI.md` wins — then amend `FAREBI.md` and re-align.

| # | Sub-plan | Phase | Depends on | Status |
| --- | --- | --- | --- | --- |
| 01 | [Foundation](./01-foundation.md) | 0 — repo, config, security, capture | — | 🟩 Gate passed |
| 02 | [Signal factory](./02-signal-factory.md) | 1 — contract, registry, degradation, harness | 01 | ⬜ Not started |
| 03 | [Data](./03-data.md) | 2 — loaders, manifests, splits, leakage audit | 01, 02 | ⬜ Not started |
| 04 | [Tier-1 signals](./04-signals-tier1.md) | 3 — FFT, texture, CLIP-ViT, PRNU, replay, corneal, CA | 02, 03 | ⬜ Not started |
| 05 | [Tier-2 signals](./05-signals-tier2.md) | 4 — video rPPG, active illumination SSS | 02, 03, 04 | ⬜ Not started |
| 06 | [Tier-3 signals](./06-signals-tier3.md) | 5 — still rPPG, scleral veins, weather, metadata, geometry | 02, 03 | ⬜ Not started |
| 07 | [Fusion & uncertainty](./07-fusion-uncertainty.md) | 6 — fusion, calibration, conformal band, policy, explain | 04, 05, 06 | ⬜ Not started |
| 08 | [API & frontend](./08-api-frontend.md) | 7, 8 — serving, worker queue, reviewer UI | 07 | ⬜ Not started |
| 09 | [Evaluation & governance](./09-evaluation-governance.md) | 9 — metrics, fairness, robustness, docs, Docker, CI | 07, 08 | ⬜ Not started |
| 10 | [Monitoring](./10-monitoring.md) | 10 — drift, alerts, retraining playbook | 08, 09 | ⬜ Not started |

## Rules for this directory

- One sub-plan per phase. Do not create ad-hoc plan files; amend the relevant numbered plan.
- Every sub-plan ends with an **exit gate** that is objectively verifiable. A phase is not
  complete until its gate passes and `PROGRESS.md` is ticked.
- Status values: ⬜ Not started · 🟨 In progress · 🟩 Gate passed · 🟥 Blocked
- Never start phase *n+1* while phase *n* is 🟨 or 🟥, unless the blocker is explicitly an
  external dependency (e.g. waiting on the self-capture campaign).

## Critical path

```
01 Foundation ──▶ 02 Signal factory ──▶ 04 Tier-1 signals ──▶ 07 Fusion ──▶ 08 API/UI ──▶ 09 Governance ──▶ 10 Monitoring
                        │                       ▲                  ▲
                        ├──▶ 03 Data ───────────┘                  │
                        └──▶ 06 Tier-3 ─────────────────────────────┘
                                       05 Tier-2 ───────────────────┘
```

Phase 03 (data) partially overlaps 04 — start the self-capture campaign in parallel with
Tier-1 signal work, because it has a long calendar lead time and blocks the fairness gate.
