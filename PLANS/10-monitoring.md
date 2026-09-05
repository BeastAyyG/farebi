# 10 — Monitoring, Drift & Retraining

**Parent:** [`FAREBI.md`](../FAREBI.md) · **Phase:** 10 · **Depends on:** 08, 09
**Status:** ⬜ Not started

## Objective

Detect, before customers do, that the model is decaying — and have a written playbook for what
to do about it.

Deepfake generators move fast. A detector that is excellent today is mediocre in six months.
Monitoring is not an ops nicety; it is how the system stays true.

## Scope

### `monitoring/drift.py`

Three distinct drift signals, because they fail differently and need different responses:

| Drift | What it measures | What it means |
| --- | --- | --- |
| **Score distribution drift** | PSI / KS test on the `fake_probability` distribution vs. the reference window | The population changed, or the model changed. Disambiguate before acting. |
| **Per-signal coverage drift** | Change in `applicable` rate for each signal | Capture UX changed, or upload pipeline changed (e.g. a new app version resizes differently) |
| **Per-signal AUC drift** | Weekly re-run of the harness on newly collected labelled fakes | **A generator has moved ahead of us.** The most important of the three. |

Also tracked: `uncertain` rate, `unable_to_assess` rate, verdict mix, request latency
(sync vs async), and per-signal error rate.

### `monitoring/alerts.yaml`

Alert rules with clear owners and thresholds:

- `uncertain` rate exceeds its configured ceiling for 24h → review thresholds.
- Any signal's coverage drops >20% relative → **check the capture pipeline first**, not the model.
- Any signal's weekly harness AUC falls below its recorded KEEP threshold → retraining review.
- Score-distribution PSI > 0.2 → investigate population shift.
- Any demographic-bucket FPR exceeds 1.5× overall in production → **pause automation for that
  bucket and escalate.** This one is a compliance event, not an ops ticket.

### `monitoring/dashboard.json`

Panels: verdict mix over time, `uncertain` rate, probability histogram vs. reference,
per-signal coverage, per-signal weekly AUC trend, latency, and bucket-level FPR.

### `docs/incident_response.md`

The retraining playbook:

1. **Detect** — which drift alert fired; is it population, coverage, or capability?
2. **Triage** — if coverage dropped, check the upload/capture pipeline before touching the model.
3. **Collect** — new fakes from the generator that beat us, added to the dataset with
   provenance and a dataset version bump.
4. **Re-run the harness** on all signals against the new data. Some previously-KILLed signals
   may revive; some KEEPs may die.
5. **Retrain the fusion** — usually fusion-only is enough; full retrain only when the neural
   baseline degrades.
6. **Re-calibrate and re-derive the band** on a fresh calibration split.
7. **Re-run fairness and robustness.** No regression allowed.
8. **Ship with new version keys** — model, threshold, calibration, fusion, registry.
9. **Post-mortem** into `RISK_REGISTER.md`.

### Longitudinal evaluation set

Maintain a frozen, growing **canary set** of labelled fakes from generators as they appear,
versioned by quarter. Every model version is scored against every canary set version, giving a
decay curve rather than a single point. This is the evidence base for "is the model getting
worse?"

## Key decisions

1. **The weekly harness re-run is automated, not manual.** A signal's KEEP status is a
   measurement with a date on it, not a permanent achievement.
2. **Coverage drift is checked before capability drift.** A sudden AUC change is far more often
   a pipeline change than a model failure.
3. **Fairness regressions in production are a compliance event** with an explicit escalation
   path, not a ticket.
4. **Every model version is scored against every canary version.** That matrix is the honest
   record of model decay.

## Exit gate

- [ ] `drift.py` runs on a schedule and writes score-distribution, coverage, and AUC metrics.
- [ ] `alerts.yaml` deployed with owners attached to every rule.
- [ ] Dashboard live with all seven panel groups.
- [ ] Weekly harness re-run automated; results appended to `artifacts/reports/harness/`.
- [ ] Canary set established with at least one generator generation frozen.
- [ ] `docs/incident_response.md` written and walked through once end-to-end.
- [ ] Retraining playbook exercised at least once on synthetic drift (a fire drill).

## Risks

| Risk | Mitigation |
| --- | --- |
| No labelled production data → AUC drift cannot be measured | Canary set + periodic manual review sampling; treat unlabelled drift as a leading indicator only |
| Alert fatigue → alerts get muted | Three alert classes with different severities; fairness escalates, everything else tickets |
| Drift is detected but nobody has time to retrain | The playbook is time-boxed per step; fusion-only retraining is the default because it is cheap |
