# P1.6A–B — Authoritative planned execution linkage

## Status

Implemented and regression-validated.

Alembic head:

`a91f6c3d7b20`

## Purpose

P1.6 establishes a scientifically conservative link between an actual
`WorkoutSession` and an authoritative logical training plan.

The binding proves plan identity only.

It does **not** claim that:

- the current plan revision was necessarily the historical plan content at execution time;
- planned and actual start times matched;
- a specific authoritative occurrence was executed;
- planned blocks have been aligned to executed phases;
- physiological response has been causally attributed to a planned occurrence.

Those stronger claims remain outside P1.6A–B.

## P1.6A — legacy execution-link provenance hardening

Exact Polar target reconciliation now persists:

`planned_workout_link_source = PROVIDER_EXACT`

when the provider training target ID exactly identifies the owned planned
workout.

Legacy mutable execution linkage remains evidence, not authoritative truth.

Accepted authoritative link evidence:

- `EXACT_PROVIDER_ID`
- `MANUAL_CONFIRMED`

Rejected as insufficient:

- `AUTO_MATCHED`
- stored planned-workout link without qualifying provenance
- temporal proximity alone

## P1.6B — immutable authoritative plan/execution binding

New immutable persistence:

`planning_plan_execution_links`

The binding includes:

- athlete identity
- authoritative logical plan identity
- revision observed when the link was created
- stable `WorkoutSession.id`
- source `PlannedWorkout.id`
- link basis
- provider target ID when exact provider evidence exists
- source workout content hash
- workout-session source hash
- observed authoritative revision content hash
- explicit `plan_content_at_execution_status = unverified`
- explicit `temporal_match_used = false`

One workout session may have only one authoritative logical-plan binding.

A repeated request for the same already-established binding is idempotent.
A later plan revision does not rewrite the historically observed revision
stored in the execution link.

Attempting to rebind the same workout session to conflicting authoritative
evidence fails closed.

## Transaction and concurrency boundary

Creation of a new authoritative execution link occurs inside one application
transaction.

The implementation:

1. checks for an existing immutable session binding;
2. locks the authoritative logical-plan pointer;
3. verifies the current authoritative revision and its hashes;
4. locks and captures the mutable planned-workout source;
5. locks and captures the mutable workout session;
6. resolves eligibility from provider/manual evidence;
7. persists the immutable execution link;
8. commits on success;
9. rolls back on any failure.

The planned-workout source hash uses the same locked source serialization
semantics used by authoritative plan adoption.

## API

Explicit endpoint:

`POST /workouts/{workout_id}/authoritative-plan/executions/{session_id}`

The client supplies resource identities only.

The client cannot supply:

- revision ID
- provider target evidence
- source hashes
- link basis
- occurrence IDs
- temporal-match claims

Those values are resolved server-side from locked authoritative/current
application state.

The response explicitly preserves the evidence boundary:

- `plan_identity_linked = true`
- `plan_content_at_execution_status = unverified`
- `occurrence_alignment_verified = false`
- `phase_alignment_verified = false`
- `temporal_match_used = false`

## Deliberately deferred

### P1.6C

Authoritative occurrence ↔ executed-block/phase reconciliation.

No direct `WorkoutSession -> pt-occ:*` authoritative FK is created in
P1.6A–B because current evidence does not establish occurrence-level execution
alignment with sufficient confidence.

### P1.6D

Verified response linkage to reconciled execution units.

## Validation

Focused P1.6 tests:

`27 passed`

Planning suite:

`275 passed`

Migration/head-sensitive regression:

`30 passed`

Full backend regression:

`2959 passed, 1 warning`

The remaining warning is the existing Starlette `httpx` TestClient deprecation
warning and is unrelated to P1.6.

`git diff --check` passes.

PostgreSQL was migrated successfully from:

`e2a7c4b9d310`

to:

`a91f6c3d7b20`
