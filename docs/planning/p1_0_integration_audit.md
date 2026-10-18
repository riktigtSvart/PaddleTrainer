# P1.0 — Integration Audit

## Scope

This audit compares the P0 planning kernel with the application source supplied
in `PaddleTrainer_API_Integration_Snapshot.zip` and with the existing
Planning/Data Integration Contract v0.1.

P1.0 is deliberately read-only. It introduces no production migration, no
plan mutation and no new planner authority.

## Verified application architecture

The current API is a FastAPI application with:

- async SQLAlchemy 2.x;
- PostgreSQL/asyncpg configuration;
- Alembic migrations;
- a single application API router under the configured `/api/v1` prefix.

The inspected Alembic chain is linear and its current head in the supplied
snapshot is `b8e4d6a10f32` (`add_pft_measurements`).

Therefore the P0.12 SQLite repository is **not** the production persistence
architecture. It remains a planning-owned development/reference store until a
PostgreSQL/Alembic integration is explicitly designed.

## Existing workout ownership

Operational plans currently live in:

- `PlannedWorkout` / table `planned_workouts`;
- `WorkoutBlock` / table `workout_blocks`.

`WorkoutBlock` is a flat ORM representation with `parent_block_id`, `position`,
legacy `BlockType` including `REPEAT`, optional duration/distance/intensity and
`repeat_count`.

The existing contract adapter already performs the correct semantic boundary:
flat ORM rows become ordered structured `SEGMENT` / `SEQUENCE` blocks; `REPEAT`
is not promoted into the new semantic taxonomy.

## Existing plan contract API

The current read path is:

```text
PlannedWorkout + WorkoutBlock rows
    -> stored_workout_snapshot
    -> build_plan_read
    -> legacy_plan_adapter / polar target adapter
    -> WorkoutPlanContract 0.1 DRAFT1
```

The endpoints are read-only and owner-scoped. The implementation explicitly
reports zero database writes and zero provider calls, and it does not authorize
numeric model output, capability updates or state estimation.

This boundary should be reused rather than duplicated by the planning core.

## Critical identity finding

The current read API is a **server capture API**, not a persisted plan-revision
API.

Its own tests establish that two reads of unchanged stored content have:

```text
same source_content_sha256
new capture_id
new exported WorkoutPlanContract.plan_id
```

The external `plan_id` is therefore capture-scoped.

`expand_plan()` derives every `planned_occurrence_id` from:

```text
contract plan_id
+ contract plan_revision
+ occurrence path
```

Consequently unchanged stored content read twice also receives different
external occurrence IDs.

This is incompatible with the P0.10 requirement that unchanged occurrences can
retain identity across authoritative plan revisions. The current exported
contract must therefore **not** be directly promoted to the planning revision
gateway.

## Revision finding

The existing contract `plan_revision` also cannot currently be treated as the
PaddleTrainer authoritative plan revision:

- legacy ORM conversion emits revision `1`;
- Polar conversion uses the provider target version;
- neither represents a persisted application plan revision lineage;
- the read API explicitly labels historical plan content unverified.

The application needs a separate persisted logical plan/revision identity
before P0.10 can be connected to production writes.

## Polar block identity finding

Polar synchronization mutates an existing `PlannedWorkout` in place and then
removes and recreates its entire `WorkoutBlock` tree. New ORM block UUIDs are
therefore generated on a resync.

ORM `WorkoutBlock.id` cannot be used as the sole long-term occurrence identity
for provider-managed plans.

The provider contract adapter's path-based block identity is more stable than
those transient ORM row IDs, but it still needs an authoritative persisted
plan identity before occurrence IDs can be stable across revisions.

## Execution linkage finding

`WorkoutSession` stores:

- `planned_workout_id`;
- `planned_workout_link_source` with provider-exact / manual-confirmed /
  auto-matched provenance.

This is useful linkage evidence, but it points to the mutable workout row. The
schema does not persist which authoritative plan revision was effective at
execution time.

Therefore current plan/execution comparison code is correct to keep
`plan_content_at_execution_status` separate from link identity and to avoid
claiming verified historical plan content.

A later integration phase should persist the effective plan revision reference
at execution-link time.

## Identity mapping selected for the integration boundary

P1.0 introduces a stable **binding key**, not a plan revision:

```text
planning_logical_plan_id = "planned-workout:" + PlannedWorkout.id
```

The application UUID is already stable at the workout aggregate level and is
owned by the current application. The external capture-scoped contract
`plan_id` remains separately preserved.

This mapping does **not** authorize rewriting the external contract and does not
make the captured contract an authoritative revision.

## P0.12 persistence decision

The SQLite sidecar remains:

```text
DEV / REFERENCE ONLY
```

Do not add it to the main FastAPI router as production persistence and do not
copy its schema into PostgreSQL mechanically.

The production persistence design should be an Alembic migration on the main
PostgreSQL chain, after the plan-revision ownership contract is frozen.

## P1.0 implementation

The new `ExistingWorkoutPlanCapture` boundary:

- consumes the existing `build_plan_read` result;
- is pinned to `plan-contract-read-api-0.1-draft1` and DRAFT1;
- preserves the entire source result as canonical JSON;
- preserves current source hash, capture ID, external plan/revision IDs,
  contract block IDs and occurrence IDs;
- derives only the stable application binding key;
- fails closed if source authority/version semantics change;
- explicitly sets authoritative revision promotion to `False`.

No database or provider access occurs in this adapter.

## Recommended next implementation sequence

### P1.1 — Authoritative plan-revision persistence contract

Design the PostgreSQL/Alembic contract for a stable logical plan and immutable
revisions. It must not mutate existing historical revisions.

At minimum the design needs:

- stable logical plan identity bound to `PlannedWorkout.id`;
- monotonically or otherwise immutably identified revisions;
- canonical WorkoutPlanContract JSON + hash;
- source capture/provenance ref;
- previous revision ref;
- decision/rationale/context linkage for planner-created revisions;
- current-revision pointer with optimistic concurrency;
- explicit adoption semantics for pre-existing mutable workouts.

No migration should be written until this schema contract is reviewed.

### P1.2 — Authoritative contract materializer

Create a one-way adapter from an authoritative persisted revision to the
existing operational `PlannedWorkout` / `WorkoutBlock` representation.

The materializer must be loss-aware and must not infer semantic `STEADY` from
legacy `WORK` or silently convert unknown intensity zones into physical units.

### P1.3 — Execution revision binding

Persist the effective authoritative plan-revision reference when a session is
linked to a planned workout. This is required before historical adherence can
be upgraded from unverified/current-capture comparison to verified plan-at-
execution comparison.

### P1.4 — Planning evidence adapters

Only after the plan boundary is stable, connect execution/PFT/response records
into `EvidenceItem` adapters. Observed time and available-to-planner time must
remain separate.
