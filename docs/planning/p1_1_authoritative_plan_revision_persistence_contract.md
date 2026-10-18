# P1.1 — Authoritative Plan Revision Persistence Contract

## Status

Contract frozen for review. **No production Alembic migration is included in P1.1.**

P1.0 established that `planned_workouts` / `workout_blocks` are mutable
operational state and that the current plan-contract read API is capture-scoped.
P1.1 therefore defines a separate authoritative lineage rather than promoting
existing capture IDs or mutable ORM block IDs.

## Ownership model

```text
existing PlannedWorkout.id
        |
        | stable binding only
        v
planning_logical_plans
        |
        +--> current_revision_id   (the only moving pointer)
        |
        v
planning_plan_revisions           (append-only immutable)
        |
        +--> planning_plan_revision_occurrences
                    |
                    v
            planning_plan_occurrence_identities
```

The operational `planned_workouts` row is not the authoritative revision and
`workout_blocks.id` is not an occurrence identity.

## Stable logical plan identity

For existing application plans P1.0 selected:

```text
logical_plan_id = "planned-workout:" + PlannedWorkout.id
```

`source_workout_id` is retained as a unique application binding. It is not a
revision identifier and must not be part of occurrence identity derivation.

## Immutable revision rules

A persisted authoritative revision contains:

- planner-owned immutable `revision_id`;
- logical plan + athlete identity;
- strictly increasing revision number;
- exact previous revision reference;
- authority-window start and effective time;
- canonical WorkoutPlanContract JSON + semantic hash;
- revision origin and history claim;
- stable occurrence membership;
- adoption provenance **or** planner decision lineage.

Existing revision rows are never updated in place. The logical-plan row's
`current_revision_id` / `current_revision_number` is the mutable concurrency
pointer.

## Adoption of pre-existing mutable plans

Adoption is deliberately non-retroactive.

A current stored workout can become revision 1 only as:

```text
origin        = ADOPTED_CURRENT_STATE
history_claim = CURRENT_STATE_BASELINE_ONLY
```

This means:

- the current state is frozen at adoption time;
- PaddleTrainer does not claim that this exact plan was historically effective
  before adoption;
- P1.0's capture-scoped plan ID is retained only as provenance;
- P1.0's capture-scoped occurrence IDs are retained only as provenance;
- new `pt-occ:*` identities are minted by planning;
- the existing `PlannedWorkout` and `WorkoutBlock` rows are not mutated by the
  adoption transaction.

The adoption command must carry `expected_source_content_sha256`. Production
persistence must compare that value to the source content inside the same
transaction and fail on drift rather than adopting a moving target.

## Occurrence identity

Stable occurrence identity is planning-owned.

A baseline adoption mints one `pt-occ:*` ID per current expanded occurrence.
The ephemeral capture occurrence ID may be recorded on that baseline binding
only.

For later revisions:

- unchanged occurrence -> same occurrence ID + `PRESERVED`;
- newly introduced occurrence -> fresh occurrence ID + `NEW`;
- removed occurrence -> absent from the new revision, while its identity record
  remains in history.

No occurrence ID is generated from ORM `WorkoutBlock.id`, capture `plan_id`,
provider target version or current expanded occurrence ID.

## Planner-created revisions

`PLANNER_CREATED` revisions require all of:

- context hash;
- planner decision hash;
- stored rationale hash;
- plan mutation instruction hash.

This preserves the P0.9/P0.10 audit chain at the production persistence
boundary.

## PostgreSQL schema contract

P1.1 freezes four table responsibilities:

1. `planning_logical_plans` — stable plan identity + current pointer.
2. `planning_plan_revisions` — immutable canonical revisions and provenance.
3. `planning_plan_occurrence_identities` — long-lived occurrence identities.
4. `planning_plan_revision_occurrences` — occurrence membership/order per
   revision.

The P1.0 snapshot showed Alembic head `b8e4d6a10f32`. This is recorded as an
audited baseline only. **P1.1 does not create a migration revision**, because
the schema contract is being frozen before production DDL is introduced.

## Required production transaction semantics

Adoption:

```text
lock / validate logical plan absence-or-unadopted state
validate source_workout_id binding
compare expected source content hash
insert logical plan if needed
insert immutable revision 1
insert occurrence identities + membership
atomically set current revision pointer
commit
```

Append:

```text
SELECT logical plan FOR UPDATE
compare expected_current_revision_id
validate previous revision + next number
insert immutable revision
insert newly minted occurrence identities
insert revision occurrence membership
atomically move current revision pointer
commit
```

A mismatch is an optimistic concurrency conflict, not an invitation to merge
silently.

## Deliberately not implemented in P1.1

- no Alembic migration;
- no SQLAlchemy production repository;
- no writes to `planned_workouts` / `workout_blocks`;
- no automatic migration of historical plans;
- no automatic reconciliation after Polar resync;
- no execution-session revision binding.

Those belong to later P1 slices after this contract is accepted.
