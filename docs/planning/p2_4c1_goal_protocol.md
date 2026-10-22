# P2.4C1 — Explicit cycle goals and prospective measurement intent

Baseline: `6a938b81fa74c9b9630cfc6c7ed080d30b3b6434`.

This slice connects the existing TrainingPeriod hierarchy to an immutable,
versioned capability-goal profile and a prospective measurement protocol.
It is a shadow application service. It does not choose workouts, modify the
existing cycle UI/API, resolve planner authorization, evaluate adaptation or
establish the comparative utility of personalized planning.

## Strategic meaning

The athlete's career is the primary strategic horizon; the season's selected
competitions sit within it. Macrocycles allocate capability goals to their
mesocycles. Each assigned capability has exactly one explicit role in each
mesocycle:

- primary development;
- secondary development;
- maintenance;
- permitted temporary decline.

The macrocycle proposal contains this explicit decomposition. The mesocycle
protocol derives its roles from the committed macrocycle plan. It cannot
substitute caller-selected roles. No scientific periodization algorithm or
automatic schedule generation is introduced.

Capabilities absent from the macrocycle plan are recorded as unassigned.
Unassigned never means permission to decline. Legacy ObjectiveType weights
remain source data; a weight is not a target improvement, training-time quota
or one of the four roles. No new role is inferred from those weights.

## Vocabulary

`domain/goals/catalog.py` contains thirteen supported capability areas: the
ten referenced by existing workout families, plus sprint speed/start,
muscular endurance, and the high-intensity/anaerobic profile area.

Its 25 metric definitions separate:

- absolute, body-mass-relative and estimated VO2max;
- direct 1RM, submaximal reference load and estimated 1RM;
- power and rate of force development;
- standing and flying starts;
- lactate threshold, ventilatory threshold and critical power;
- sprint performance and an explicit anaerobic-capacity estimate;
- physiological measurements, task performance, estimates, indirect
  indicators and subjective context.

These are method families, not 25 implemented or validated standardized tests.
Every endpoint freezes an exact MeasurementProcedure: key/version, origin,
source reference, modality, exercise/task, procedure, equipment/processing,
and comparability conditions. An external reference does not automatically
establish standardization or validity. Subjective state is context only.
Peripheral oxidative capacity and musculoskeletal robustness remain latent
constructs when observed through indirect task indicators.

The catalogue version/hash and full procedures are included in each artifact.
Within a protocol and its revision history, changing a procedure requires a
new procedure version. Exact procedures and metric units remain separate;
different modalities, methods, starts or estimators are not interchangeable.

## Source capture and hierarchy

`SqlAlchemyTrainingGoalSource` reads existing TrainingPeriod,
TrainingPeriodObjective and User.timezone records in one SELECT statement.
`populate_existing=True` prevents a retained ORM identity map from silently
substituting stale source values. The service and audit repository must use
the exact same known-fresh session.

The snapshot contains only inputs used by this slice: period identity,
athlete, parent/type, title, dates, legacy objective types/weights and athlete
timezone. It is not a hash of every column of the mutable source tables.

The complete ancestor chain to the macrocycle and all direct child periods
are checked. Supported ranks are Olympic cycle, season, macrocycle and
mesocycle; higher ancestors may be omitted only when the macrocycle really
has no such parent. Children must be mesocycles, fit the parent window and
not overlap. A missing/cyclic/cross-athlete ancestor or a census hitting the
5000 joined-row limit blocks registration. Source dates are local dates in
the frozen athlete timezone.

Every named macrocycle capability requires a role directive for every child
mesocycle. Periods and goals are never created or edited by this service.

## Measurement and acceptance intent

Every assigned capability requires at least one primary endpoint. Supporting
and context measurements cannot substitute for a missing primary endpoint.
Multiple primary endpoints are conjunctive: all are required. No composite
score or arbitrary addition of percentages and kilograms is defined.

Baseline and follow-up windows must be ordered, non-overlapping, within the
mesocycle in the source timezone, and strictly after protocol materialization.
The service additionally verifies that database persistence preceded every
baseline window. This version supports prospective baseline scheduling only.
Historical data remain available to existing learning/evidence workflows;
they are not retroactively declared a preregistered baseline by this slice.

Change requirements use canonical finite decimal strings, with no default
scientific thresholds. Favourable change is positive in the catalogue's
improvement direction: follow-up minus baseline for higher-is-better,
baseline minus follow-up for lower-is-better. Percentage change additionally
requires a ratio-scale metric and a positive baseline.

- Development requires a positive favourable-change minimum.
- Maintenance requires a finite interval containing zero change.
- Permitted decline requires a negative floor while allowing no decline.
  Decline is an accepted cost, not an outcome to maximize.

An optional measurement-error estimate is in the same change basis as its
requirement and must name its source. It is not automatically a confidence
interval or validated personal error model. Unknown/inconclusive uncertainty
requires withholding assessment.

The frozen future assessment rules require exactly one eligible complete
protocol result per endpoint/window. Missing or multiple eligible results
withhold assessment; the caller cannot select the best result. Within-test
trial aggregation must already be specified in the exact procedure. Other
activity data are retained in their source workflows, not treated as zero or
independent trials. C1 records these rules; outcome census, eligibility
checking and assessment execution belong to a later slice.

## Immutable registration and recovery

Public application functions:

- `register_macrocycle_capability_plan`;
- `register_mesocycle_goal_protocol`;
- `load_cycle_goal_artifact`;
- `load_mesocycle_goal_context_source`.

The stable slot is artifact kind + athlete + existing period + integer
revision. Revision one has no predecessor; each later revision explicitly
supersedes the immediately preceding slot. At most 64 revisions per slot
series are supported in this schema, with bounded dependency replay.

New registrations capture current source inputs. Registering a new mesocycle
protocol requires the source snapshot still to match the frozen macrocycle
plan; a changed source requires an explicit new macrocycle revision.

Retry and historical load replay the original frozen sources, including
observed absences/unassigned capabilities. They do not recapture current
periods, select the latest macrocycle plan, or rewrite older intent. Reusing
one revision with a different proposal conflicts. An uncertain commit can be
recovered by the identical retry without repeating source capture.

The SQLAlchemy audit repository assigns persisted_at. Read-back verifies
canonical JSON, exact field types, metadata, stable identity, schema/rules,
catalogue hash, semantic hash, chronology and domain replay. Parent references
also pin the complete canonical contract SHA-256 and database time, protecting
identity/materialization fields excluded from semantic hashing. All source
and predecessor references are recursively restored; missing parents do not
fall back to current mutable data.

The service owns commit/rollback and verifies transaction closure before
returning success. No database migration is required: the two new artifact
kinds use the existing immutable audit store.

## Boundary with P2.4A/B

A successful committed mesocycle receipt can attest only that its measurement
schedule was registered before baseline windows. It cannot attest prior
registration before an actual planner decision, comparative planning utility,
physiological adaptation or causality.

The optional context-source loader returns a cutoff-checked SourceSnapshotRef
for explicit use in a new planning context. It does not attach itself, resolve
GOAL_PRIORITY/OBJECTIVE_REGIME, or change the P2.4A/B artifacts. Existing v0.1
observations remain descriptive. Comparative utility requires a separately
preregistered comparator/design and later verified outcome linkage.

## Validation

Synthetic domain and file-SQLite tests cover explicit role decomposition,
complete source reads, real source/audit adapters, frozen retries/history,
version chains, measurement windows and database-time boundaries, type and
numeric guards, uncertainty/ambiguity rules, context references, transaction
ownership, commit failure/recovery and canonical/tamper replay. They do not
prove live PostgreSQL integration or scientific validity of a test protocol.
