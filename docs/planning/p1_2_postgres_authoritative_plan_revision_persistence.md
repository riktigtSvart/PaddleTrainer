# P1.2 — PostgreSQL/Alembic Authoritative Plan Revision Persistence

## Status

Production persistence implementation is present, but P1.2 performs **no automatic adoption** of existing workouts and adds no write endpoint. The migration creates empty planning-owned authoritative history tables. Existing `planned_workouts` and `workout_blocks` remain operational mutable state.

## Pre-migration contract correction

P1.1 correctly froze the identity semantics, but its table sketch contained two storage mismatches that had to be corrected before the first production migration:

1. planner-owned IDs are domain strings in the namespaces `pt-plan-rev:*` and `pt-occ:*`; they therefore cannot be PostgreSQL UUID columns without inventing a second hidden identifier mapping;
2. the first table sketch omitted immutable revision copies of `athlete_id` and the external contract plan ID/revision held by `AdoptionSourceRef`.

No P1.1 production migration existed, so P1.2 corrects those table details before any database state is created. The accepted domain semantics are unchanged.

## Migration

Alembic revision:

```text
c91f7a3e2d40
    down_revision = b8e4d6a10f32
```

It creates only:

```text
planning_logical_plans
planning_plan_revisions
planning_plan_occurrence_identities
planning_plan_revision_occurrences
```

The migration does not add, alter, rewrite, or backfill `planned_workouts` or `workout_blocks`.

Planning-owned revision and occurrence identifiers are stored as `TEXT`. Application user/workout bindings remain PostgreSQL UUID values.

## Database-level immutability

`planning_logical_plans.current_revision_id/current_revision_number` is the intended moving pointer.

The historical tables are protected by a PostgreSQL trigger that rejects `UPDATE` and `DELETE` on:

- `planning_plan_revisions`;
- `planning_plan_occurrence_identities`;
- `planning_plan_revision_occurrences`.

The normal repository only inserts history rows and moves the logical-plan pointer.

## Async SQLAlchemy repository

`SqlAlchemyAuthoritativePlanRevisionRepository` implements the P1.1 port.

It:

- flushes but never commits; transaction ownership remains with the application boundary;
- locks the logical-plan pointer on append;
- compares `expected_current_revision_id` before append;
- validates the full domain revision transition before insert;
- preserves `PRESERVED` occurrence identity and inserts only `NEW` identities;
- round-trips the stored canonical contract and checks the stored revision semantic hash;
- converts integrity races into `AuthoritativePlanConflictError` rather than silently merging.

## Adoption source drift protection

Revision 1 adoption requires a `LockedPlanSourceHashProvider`.

The production provider locks the current `PlannedWorkout`, then its `WorkoutBlock` rows, rebuilds the existing `stored_workout_snapshot`, and computes the same source-content digest used by the current plan-contract read API.

Only when that locked digest equals `CurrentStateAdoptionBinding.expected_source_content_sha256` may revision 1 be inserted. A changed mutable source fails closed.

The provider does **not** promote capture-scoped plan or occurrence IDs. Those remain provenance only.

## Deliberately not active yet

P1.2 does not:

- auto-adopt any existing plan;
- expose a plan-revision write API;
- materialize authoritative revisions back into `PlannedWorkout` / `WorkoutBlock`;
- bind executions to an effective authoritative revision;
- reconcile Polar resyncs automatically.

Those are separate integration steps so the first database migration cannot silently change planning authority or operational workout content.
