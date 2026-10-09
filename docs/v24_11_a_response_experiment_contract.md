# V24.11-A: archived-cohort-bound retrospective HR experiment contract

This slice defines an explicit, versioned experiment plan and its pure local
validator. It consumes the complete E/1 record or E/3 archived full response.
It does not assemble current sources, create model input arrays, fit a model,
calculate PFT features, update a personal baseline, or authorize predictions.
The existing migration head remains `e4f7a92c1836`.

## Concrete target and inputs

The task is `RETROSPECTIVE_HR_RESPONSE_WITHIN_ATHLETE`. The target commitment is
the mean of positive finite recorded HR samples in a complete, verified-export
grid observation window, measured in bpm. Windows retain the existing half-open
start-inclusive/end-exclusive semantics. This declares an aggregation; no target
values are computed in this slice. Recorded sensor HR is not promoted to a
verified physiological reference or a fatigue label.

`KAYAK_WATER` is an explicit modality declaration, not independently verified
sport metadata. Workload inputs describe observed GPS-derived motion, not
measured mechanical power. Supported workload fields are ground speed, its
previous-segment change/rate, and the absolute bearing change. The default
selection contains only `gps_ground_speed_mps`.

The environment selection accepts the existing 11 named dataset channels.
Defaults are air temperature, headwind component and crosswind magnitude.
They are fixed engineering choices, not automatically selected using TEST
statistics. Every selected environmental channel must have at least one
`AVAILABLE` observation across archived TRAIN members. VALIDATION/TEST values
cannot supply missing TRAIN support. There is no silent feature substitution.

For the user's September 27/28/30 cohort, the September 27 TRAIN hydrology was
reported `WITHHELD`. Selecting such an unsupported TRAIN channel is rejected.
The default profile does not select hydrology; its original masks and values
remain in the member datasets. Source statuses remain distinct: `AVAILABLE`,
`MISSING`, `WITHHELD`, `NOT_APPLICABLE`. Unavailable values are never zero-filled
or promoted. The future model-row requirement is that all selected values are
available and finite; excluded rows stay in the original observations/history.

## Time and physiological lag

Default history lookbacks are 30,000, 60,000 and 120,000 ms. They are engineering
configuration values, not measured or scientifically optimized physiological
lags. Callers may explicitly select 1–8 distinct positive integer lookbacks,
up to 600,000 ms each. The upper bound is a configuration/execution limit.
Changing a lookback changes the experiment commitment.

History is anchored at the target observation window's end, so the current
workload may condition a retrospective response. No workload after that window
may enter it. Histories stay within the same session, route, exercise and
sequence. The future materializer must verify full selected-lookback coverage;
incomplete cold starts are excluded from model rows without deleting raw data.
Unlabelled workload observations remain useful history. Initial physiological
state remains unknown and pre-history/post-recovery censoring remains explicit.

There is no fixed HR shift, future HR predictor, physiological delay estimate,
or inferred physiological reset. The verified 1,663/1,685/1,386-ms export-clock
mappings are technical timestamp evidence, not physiological delay. Source clock,
sensor processing and physiological kinetics are not equated. This task does not
claim pre-exercise forecasting or causal identification.

## Reference, membership and commitment

The manifest pins `record_schema_version`, `record_hash`, `cohort_index_hash`,
`request_manifest_hash` and `owner_id`. All archived whole-session members and
their requested splits must match exactly. The archive must contain supported
complete chronological TRAIN/VALIDATION/TEST assignments and no flagged exact
duplicate pair. A limited single-session archive cannot prepare this experiment.
This is a check of retained declared metadata; it is not new source verification,
statistical independence, or a simultaneous snapshot of all provider inputs.

The strict JSON manifest rejects unknown fields, promoted authority, duplicate
members/features/lookbacks/metrics, numerical boolean aliases and unknown
predictors. Canonical membership, selected-feature, metric and lookback ordering
participate in `experiment_manifest_hash`, a SHA-256 commitment excluding itself.
Defaults are explicit in the canonical payload. Hashes provide local integrity
and binding; a fabricated internally consistent archive is not authenticated
merely by its hash. Original inputs are never rewritten.

The schema is generated from `ResponseExperimentManifest` at
`docs/contracts/response_experiment_manifest_v0_1.schema.json`.
Neither record UUID nor current database storage is authenticated by this local
reference. The existing archive API provides ownership/current-source checks.

## Evaluation policy

Fitted preprocessing and data-driven feature selection are TRAIN-only.
VALIDATION is for model selection; TEST is for final frozen evaluation. Requested
metrics are MAE, RMSE and mean signed error, each in bpm, reported per session
alongside label/input coverage. The metrics are requests, not computed results.
Whole-session partitions remain exactly as archived. Saving this local plan
does not persist a separate dataset assignment or mutate the historical index.

One TRAIN session is an explicit limitation. Archive preparation-candidate counts
are not the count of usable model rows or independent samples. The validator
does not access raw observation/HR arrays, validate row-level coverage, fit a
scaler/imputer, estimate uncertainty or measure model performance.

## PFT handoff

The user's PFT v0.1 summary and standalone domain package are reviewed in
`docs/pft_v0_1_integration_notes.md`. This plan adopts separation of measurement
and interpretation, preservation of original data and modality/stimulus-specific
future baselines. Future references must be available strictly before the target
session, and comparisons must precede eligible baseline updates.

Those are future integration commitments, not a verified current baseline.
PFT, HR-derived predictors, fitness/fatigue targets and readiness scores are
excluded from this schema. A PFT feature derived from the target session's HR
cannot enter this experiment as a disguised independent predictor. Adding true
pre-session PFT data requires a new contract and actual temporal/provenance
checks; the current schema rejects supplied PFT/baseline references.

## Offline CLI and control

Run with the project Python and `PYTHONPATH=apps/api` from the project root:

```text
python tools/check_response_experiment.py prepare --archive archive_full_1.json --experiment-id response-plan --output experiment_contract.json
python tools/check_response_experiment.py check experiment_contract.json --archive archive_full_1.json
python tools/check_response_experiment.py control --archive archive_full_1.json --experiment-id response-plan --output-dir new-control-directory
```

`prepare` and `control` optionally accept repeated `--workload-feature`,
`--environment-feature`, `--lookback-ms`, and expected record/index hash pins.
The Python service also accepts an explicitly empty environment selection.
The archive input is bounded to 3 MiB, and the experiment to 64 KiB. Reads reject
duplicate JSON keys, nonfinite/deep/malformed JSON and invalid UTF-8; a Windows
UTF-8 BOM is accepted. Errors redact private input values and file paths.
Outputs are created exclusively, never overwritten.

Control creates four new local files: the plan, identical repeated plan,
detailed check and final summary. It verifies stable bytes/hash binding,
unchanged input bytes, wrong-pin and changed-split rejection, HR/PFT predictor
rejection, TRAIN-only fitting policy, no fixed lag/shift, sequence isolation,
modality scope and forbidden authority. No archive is deleted or repaired.
It reports `EXPERIMENT_CONTRACT_LOCAL_CONTROL_VERIFIED`; ordinary check reports
`LOCALLY_VALID_RESPONSE_EXPERIMENT_CONTRACT`.

The claim scope is `LOCAL_EXPERIMENT_POLICY_AND_ARCHIVED_PAYLOAD_BINDING_ONLY`.
Current/source/owner/storage/chronology/training/numeric authority flags remain
false. Historical chronology/split claims are separately labelled as embedded
claims. `model_input_arrays_checked=false`, `model_input_row_count=null`, and
all provider calls/database writes are zero. Row-level materialization and
executable enforcement of this plan belong to the next slice.

## Verification and next slice

Tests bind actual C assembler/E/1 constructor outputs from SQLite fixtures,
check negative scope/leakage/metadata cases, and run the CLI in a fresh process
with an invalid database URL to establish its offline path. Fixture runs do not
substitute for the user's Windows/local-archive control. Release counts are in
the package's `VALIDATION.json`.

Next: source-bound row-level sequence/input materialization, with coverage and
exclusion reasons under this exact plan; more earlier TRAIN sessions before
model fitting; then an explicitly scoped temporal baseline model. PFT domain
integration remains a separate migration and processing effort.

Method reference: [scikit-learn's official leakage and preprocessing guidance](https://scikit-learn.org/stable/common_pitfalls.html#data-leakage).
The guide supports learning preprocessing/feature-selection steps only from
training data. No scikit-learn dependency or implementation is introduced here.
