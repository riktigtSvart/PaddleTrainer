# P2.4C2 — Goal-specific measurement change assessment

Baseline: `41f18e1710f2e6a13550698edeacb9ffbb3776d6`.

This shadow application service evaluates the exact C1 mesocycle protocol.
It reads existing measurements, freezes their source census and reports the
observed change against the preregistered acceptance requirements. It does
not change the C1 schema, choose workouts, mutate plans, update personal
load-response functions or establish comparative planning utility.

## Public application boundary

`application/assess_mesocycle_goals.py` exports:

- `assess_mesocycle_goal_protocol`;
- `load_mesocycle_goal_assessment`.

The write operation takes an athlete, an exact C1 `GoalVersionReference`, an
`activity_cutoff_at`, and the session-bound source/audit adapters. Callers
cannot pass selected outcomes, replacement capability roles, thresholds,
units, procedures or error estimates. The committed C1 artifact supplies
those values. The source and audit repositories must share the exact same
known-fresh session, whose commit/rollback the service owns.

The new `MESOCYCLE_GOAL_ASSESSMENT` kind uses the existing immutable audit
store. No database migration, HTTP route or frontend change is introduced.

## Measurement capture and time meaning

`SqlAlchemyGoalMeasurementSource` uses one SQL `UNION ALL` statement for:

- `Assessment` joined to its scalar `Measurement` rows;
- `PhysiologicalMeasurement` rows.

The query reads fresh columns directly, avoiding retained ORM identity-map
values. It captures every metric for this athlete in the interval from the
earliest baseline-window start through the lesser of the activity cutoff
and the latest follow-up-window end. It also bounds source `created_at`
fields by the capture-start time. Parent assessment ownership is checked by
the join/filter. Source and parent metadata, values, units, event/recording
times, provider/device context and quality text are retained in canonical
JSON with a SHA-256 digest. No synonym mapping, automatic unit conversion,
quality interpretation or numeric-text parsing is performed.

The activity cutoff bounds measurement event times. Source rows are mutable
and are read **now**, during the recorded capture interval. Their
application-supplied `created_at` values do not establish database
availability at a historical activity cutoff. Accordingly,
`source_availability_at_activity_cutoff_verified` is always false. An
assessment created today must never be fed to an earlier planner as
information known at that earlier cutoff.

Raw workout streams, PFT recordings and model-derived capacities do not
become scalar test outcomes automatically. They remain in their existing
source/learning workflows. A future explicit processing adapter can produce
a scalar result with its exact procedure and provenance. An ordinary or
incomplete row in the present census is retained with an exclusion or
unresolved reason, rather than silently converted into a standardized test.

The v0.1 limits are fewer than 5000 source rows, at most 64 endpoints and at
most 65536 UTF-8 bytes per source snapshot. Hitting a census limit blocks
persistence; it never produces a partial assessment.

## Explicit execution metadata

Each potentially usable result needs a `GoalMeasurementExecution` under
`measurement.extra_data["goal_measurement_execution"]`. The existing
assessment-create API can already retain this metadata. The physiological
measurement source uses the same key in its own `extra_data`.

The fixed execution schema is `goal-measurement-execution-v0.1`. Its fields
are:

- the full exact C1 `MeasurementProcedure`;
- the catalogue `MeasurementEvidenceKind`;
- aware UTC `started_at` and `ended_at`;
- `completion`: `complete`, `incomplete` or `unknown`;
- `result_level`: `complete_protocol_result`, `within_protocol_trial` or
  `unknown`;
- one `MeasurementConditionObservation` for every C1 condition, in the
  registered order, with `condition`, `status` (`met`, `not_met`, `unknown`),
  `observation` and `evidence_reference`;
- a positive canonical decimal `body_mass_kg`, when retained, required for
  measured or estimated body-mass-relative VO2max;
- a nonempty `execution_evidence_reference`.

Serialize typed execution objects with the existing canonical serializer:

```python
import json

from app.planning.domain.common.serialization import canonical_json
from app.planning.domain.goals.assessment import MEASUREMENT_EXECUTION_KEY

extra_data = {MEASUREMENT_EXECUTION_KEY: json.loads(canonical_json(execution))}
```

Unknown keys or incorrect primitive types are rejected as unresolved
execution details. The measured scalar comes from the existing numeric
source column, never from an execution-metadata override. Both a numeric
and a nonempty text value make that source unresolved.

The source event time must fall within its execution interval, and the
whole execution must fit the registered window. A complete result cannot
have been recorded before execution ended. When physiological source
period bounds are supplied, both must equal the declared execution bounds.

Execution details and condition evidence remain recorded assertions.
`execution_details_independently_verified` is always false. Neither a
metadata assertion nor an external protocol reference proves scientific
standardization, validity or sensor correctness.

## Selection, missingness and ambiguity

Every source has a candidate disposition for each endpoint:

- `eligible`;
- `ineligible`, with the explicit mismatch/incompletion reason;
- `unresolved`, when relevant execution, conditions or numeric data cannot
  be established.

Different units, metrics, full procedures, modalities, tasks, processing,
evidence kinds or violated conditions cannot be substituted. Within-test
trials are retained but cannot stand in for a complete protocol result.
Trial aggregation belongs to the exact C1 procedure and upstream processing.

Each closed window needs exactly one eligible complete result. Multiple
eligible results withhold assessment even when their values are identical.
A relevant unresolved candidate also blocks choosing another complete
result. No best/latest/closest-value selection or implicit deduplication is
allowed. A missing result is never zero. Open windows are withheld.

Supporting and context endpoints cannot replace primary endpoints.
Ordinal context results retain their observed values without arithmetic
change or an acceptance verdict. Supporting numeric results can describe
change, but have no independent acceptance requirement.

## Arithmetic and conditional acceptance

Favourable absolute change is follow-up minus baseline for higher-is-better
metrics, and baseline minus follow-up for lower-is-better metrics. A
favourable percentage is `100 * favourable_absolute_change / baseline` and
requires a ratio-scale metric and a positive baseline. Interval and ordinal
scales do not get percentage changes. Percent change in an estimated metric
remains an estimated endpoint; it does not become a physiological measure.

Comparisons use exact rational arithmetic over the decimal representation
of the persisted numeric values. Each change stores its exact numerator and
denominator plus a deterministic, 28-significant-digit display value.
Display rounding never decides acceptance. This is computational precision;
it does not recover measurement precision lost in an existing Float column.

The C1 requirement supplies its lower/optional upper boundary and optional
declared change-error amount `e` in the same change basis. C2 reports the
arithmetic sensitivity range `[change - e, change + e]`:

- wholly within the inclusive acceptance interval:
  `met_under_declared_error`;
- wholly outside the interval on either side:
  `not_met_under_declared_error`;
- overlapping an acceptance boundary: `withheld`;
- error amount/source absent: `withheld`.

For percentage change, `e` is an amount on that percentage-change scale,
not an additional percentage of the observed change. Zero error requires
an explicit C1 declaration/source; absence is never replaced with zero.
`point_requirement_met` records the arithmetic point comparison only and
does not override an uncertainty/missingness verdict.

This range is **conditional sensitivity analysis**, not a confidence
interval, a statistical significance test or a verified bound on true
error. C1 does not specify a statistical error model.
`measurement_error_model_validated` therefore remains false. The service
does not call a conditional criterion verdict proven adaptation.

All four goal roles keep their exact C1 requirements. Development needs
the positive target. Maintenance uses its finite interval. Permitted
decline uses its negative floor, while improvement may still satisfy it;
decline is an accepted cost, not a result to maximize.

All primary endpoints for a capability are required. Any withheld primary
withholds its capability verdict; otherwise all must meet their registered
criteria. The report also records whether all assigned primary criteria
are met under the declared assumptions. This is a conjunction, never a
weighted utility score or a sum of kilograms and percentages. Unassigned
capabilities remain explicitly unassigned.

## Immutable persistence and recovery

The stable slot is athlete + exact C1 protocol identity + activity cutoff.
Identical retry returns the first committed census, values, exclusions and
gaps. It never recaptures current measurements or silently repairs an old
missing result. A new cutoff produces a separate assessment and may see
late or edited source rows. Those reports are not independent trials.

The parent reference pins the C1 semantic hash, complete canonical JSON
SHA-256 and database persistence time. The C1 loader replays the full
macrocycle/protocol revision chain and checks registration before baseline.
Assessment read-back restores strict types and canonical JSON, validates
metadata/hashes/database times and recomputes every candidate, change and
verdict from the frozen census and exact parent. It does not consult today's
mutable measurements when restoring history.

Save/read-back and commit must all succeed and close the transaction before
a durable receipt is returned. Commit failure rolls back. If a disconnect
occurs after a successful commit, the exact retry recovers that artifact.

All existing authorization, planning-utility, causal attribution and
physiological-adaptation ceilings remain unchanged. C2 cannot claim the
personalized planner caused the observed change or outperformed a science-only
comparator. No automatic personal-model update is performed.

## Validation scope

Synthetic domain tests cover all four roles, exact fraction boundaries,
ambient Decimal-context independence, scale/direction distinctions,
uncertainty, windows, missingness, ambiguity, full procedure/condition
matching, supporting/ordinal context and census provenance guards.

Isolated file-SQLite tests use the real C1 registration, scalar measurement
and audit adapters. They cover one-statement capture, identity-map freshness,
scope limits, durable replay, frozen gaps, later captures, transaction
ownership, failed/skipped/uncertain commits and rehashed tamper detection.
They do not establish live PostgreSQL integration, scientific protocol
validity or exercise efficacy. The combined gate also retains the existing
C1, A/B, planning-context and earlier audit/planner regression tests.
