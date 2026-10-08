# V24.7 — route input causes and chronological HR response context

V24.7 extends the existing read-only route inspection and training-data audit
(`audit_version=0.5.0`). It explains environmental/model input gates and keeps
the observed workload timeline needed by a future dynamic HR model. There is
no estimator, training, numerical prediction, fatigue score, new dependency,
database table, migration or new endpoint.

## API and provenance

Use the existing
`GET /api/v1/integrations/polar/sessions/routes/inspect?route_date=YYYY-MM-DD`.
Each `route_sessions[].training_data_readiness_audit.routes[]` now contains:

- `input_diagnostics`: existing input states, blocking-cause counts, component
  evidence and source selection, and a separate bounded HR-exclusion packet.
- `temporal_context`: observed workload runs, boundary counts and temporal policy.

The full internal audit also attaches `temporal_context` to every segment.
The public audit summary continues to omit the full segment array. Counts
always cover the full route; `items` packets return at most 25 records and
declare `total_count`, `returned_count` and `truncated`. Cause examples return
at most three order indices per cause. The exclusion packet is separate from
the first page of segment details, so late HR gaps remain visible.

`input_diagnostics.source_hash` commits the full route input, reproduced model
gate results, all windows (including those outside the detail page), full trusted
environment, source selection and weather provenance. It also commits
`owner_bound_audit_source_hash`, which refers to the parent audit's current
athlete/session/source binding. The child `decision_hash` commits its complete
report. Changing owner, source, temporal layout, evidence or provider selection
changes these hashes. A noncanonical source cannot produce a verified hash.

Environment detail is matched by the exact `(route_index, exercise_index)`
and unique `order_index`. For usable input contexts, its full copied context
must equal the supplied current trusted environment segment. Missing,
duplicate or mismatched detail adds explicit binding blockers and withholds
preparation candidates. An internal caller that omits the optional full
environment retains the prior input gates and reports
`environment_detail_binding_verified=false`; missing component detail does
not become verified evidence.

The raw HR validator, native API normalization, TCX verifier, persisted export
proofs and sensor-declaration contracts are unchanged. No read-only check
writes them or promotes sensor identity/acquisition quality.

## Environmental and model-input causes

`upstream_input_state` reports the actual input status, `model_ready`, athlete
binding status, environment route status and declared/aligned segment counts.
`route_blocking_reasons` preserves the reproduced model gate reasons.
`segment_blocking_reason_counts` expands the per-segment model reasons and adds
HR-grid, temporal-support and environment-detail binding reasons.

`component_status_counts` separately counts `water_identity`, `weather`,
`wind` and `hydrology`. Bounded details retain the upstream trust basis,
limitations, resolved water identity, weather sample timestamp/position and
matching distance/time delta where provided, and trusted hydrology context.
Missing values are not replaced by inferred identity, local current velocity
or representativeness claims.

`component_source_selection` distinguishes `NOT_SELECTED`, `SELECTED`,
`DERIVED_FROM_SELECTED_WEATHER`, `SYNTHETIC_TEST`, and
`SELECTION_NOT_PROVIDED`. Selection is not evidence of a successful match;
component status describes the resulting evidence. The original default
inspection selects no external environment provider. V24.7 does not silently
select a provider or issue additional external requests.

The existing environmental aggregate can accept a partial context with
limitations when some components are usable. V24.7 makes the other components
visible and preserves that policy; it does not invent an all-components-required
rule. In particular, `NOT_APPLICABLE` hydrology is distinct from missing data.

Weather availability is described as `NOT_PROVIDED`,
`SYNTHETIC_TEST_CONTEXT`, `RETROSPECTIVE_HISTORICAL_CONTEXT` or
`PRE_EXERCISE_AVAILABILITY_NOT_ESTABLISHED`, based on the supplied provenance.
A historical/reanalysis value describes retrospective conditions. A forecast
label or claimed issue time alone cannot establish what was available to the
athlete before exercise. A forecast availability verifier is not implemented:
all `pre_exercise_feature_authorized` flags remain false. Future work needs
source-bound forecast run/issue/availability evidence and a prediction cutoff.

## Physiological dynamics and observation support

An export clock offset locates the recorded HR samples on the exercise clock.
It is not a physiological workload-to-HR delay. V24.7 preserves timestamps and
sample indices; `physiological_lag_ms=null`, `fixed_hr_shift_applied=false`.
No universal delay or history horizon is assigned. Onset and recovery need not
share response parameters. Estimating those parameters requires an individual,
validated model with usable workload and measurement data.

The temporal builder preserves source order. Valid integer half-open windows
must satisfy `0 <= start < end <= exercise_duration`; order indices must be
unique, nonnegative integers and strictly increasing. Overlap or reversal blocks
the entire temporal sequence and preparation candidates. Invalid windows are
excluded; valid observation windows on either side are not connected across them.

New observed runs start at time gaps, skipped source order indices or explicit
upstream source discontinuities. These are data-support boundaries, not
identified work/rest phases or verified physiological resets. Initial state is
unknown; pre-observation history and post-observation recovery remain censored.
The current record cannot establish recovery after recording stops. Pause clock
semantics are still a limitation of the saved export evidence.

Each supported segment has `sequence_index`, `sequence_position`,
`history_start_order_index`, `previous_order_index` and `next_order_index`.
These are pointers into the original input rows, avoiding quadratic copies of
all prior history. Adjacent workload remains in the run even where the HR grid
has no label. Missing HR is never interpolated and never becomes a candidate
label. The three known unrecorded terminal HR slots and the over-duration
terminal window remain separately explained by the existing diagnostics.

The observed run including the current segment is available for retrospective
conditioning. For causal prediction, `completed_history_end_order_index` and
`completed_history_end_exercise_elapsed_ms` bound the preceding completed
segments. A whole-segment GPS speed is only observable after the end waypoint:
`current_workload_available_not_before_exercise_elapsed_ms` is its window end,
which is a lower bound, not verified publication/ingestion time. The current
segment is `RETROSPECTIVE_CONDITIONING_ONLY` and is not authorized as a
predictor of earlier HR samples in that same window. Causal predictor selection
is not yet implemented. GPS ground speed is an external motion observation,
not measured metabolic workload or boat speed through water.

No target HR or future observed workload is used by an estimator. Any future
history/target window generation must preserve their common
`ATHLETE_PROVIDER_SESSION` split group. Overlapping histories cannot be split
randomly between training and validation. Dataset splits remain unassigned.

## Fatigue hypothesis and scientific scope

HR onset acceleration and post-exercise HR recovery are studied as markers of
training response. Nelson et al. (2020) found protocol-dependent associations
between onset acceleration and running performance across training phases;
this does not establish a universal threshold or a mechanism of circulatory
fatigue. Aubry et al. (2015) observed faster post-exercise HR recovery in
functionally overreached triathletes despite reduced performance, showing why
the direction of a change cannot be interpreted in isolation. Their conditions
do not validate a wrist-PPG kayaking fatigue score.

V24.7 records this relationship as a research hypothesis requiring external
validation. Suitable later work needs repeated comparable within-athlete
protocols, separately measured performance/fatigue or recovery outcomes,
training phase, baseline HR, environment and measurement-quality covariates.
Correlated kinetics are not a causal diagnosis; delayed HR following a workload
change must not be automatically labelled a sensor artifact.

Primary sources:

- Nelson et al. (2020), *Optimisation of assessment of maximal rate of heart
  rate increase for tracking training-induced changes in endurance exercise
  performance*, Scientific Reports 10, 2528.
  https://doi.org/10.1038/s41598-020-59369-6
- Aubry et al. (2015), *The Development of Functional Overreaching Is Associated
  with a Faster Heart Rate Recovery in Endurance Athletes*, PLOS ONE 10(10).
  https://doi.org/10.1371/journal.pone.0139754
- Bunc et al. (1988), *Kinetics of heart rate responses to exercise*.
  https://pubmed.ncbi.nlm.nih.gov/3404576/

## Verification

The V24.7 tests cover source identity, overlaps/reversal, incomplete labels,
window boundaries, time/order/source gaps, delayed-response history support,
bounded cause reports, environment-detail binding, forecast claim rejection,
owner/source hash changes and read-only API integration. The original suite
also exercises persistence and real ORM/API contracts.

The attached real Polar sample/TCX smoke test verifies the original HR and TCX
decision hashes, 3038 HR slots, export-clock mapping and unchanged evidence
rows. A separate terminal-window replay uses the previously reported window
positions with a synthetic upstream input scaffold; it is not a live
environment-provider test. The user's backend live check is the remaining
deployment-specific verification of the whole route and actual provider causes.
