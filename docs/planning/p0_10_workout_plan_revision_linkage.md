# P0.10 — WorkoutPlanContract boundary + immutable revision linkage

P0.10 connects an authorized `PlannerDecision` to the WorkoutPlanContract world
without giving the planner permission to edit operational workout rows directly.

```text
PlannerDecision
    + DecisionRationale
    + WorkoutPlanContractArtifact
        -> PlanMutationInstruction
        -> WorkoutPlanRevisionGateway
        -> immutable new revision
        -> PlanRevisionLink
```

## Ownership boundary

The planning core does **not** redefine the WorkoutPlanContract schema.
`WorkoutPlanContractArtifact` is an integration wrapper around canonical
contract JSON plus stable occurrence IDs and an integration hash.

The external workout-contract implementation remains the owner of its own
schema and may also carry its own content hash.

## Mutation authorization

A mutation is accepted only when:

- decision and rationale hashes verify;
- rationale references that exact decision/context;
- planner decision status authorizes mutation;
- a selected action exists;
- the selected action explicitly has `plan_mutation_authorized=true`;
- P0.10 action type is `SELECT_WORKOUT_FAMILY`.

Deferred, blocked, review-required and human-decision-required results cannot
silently mutate plans.

## Immutable revision semantics

The reference gateway implements optimistic concurrency:

```text
expected_current_revision_id == actual current revision
    -> mutation may create a new revision

otherwise
    -> PlanRevisionConflictError
```

Old revisions remain retrievable after replacement. No in-place edit occurs.
The same mutation instruction is idempotent.

`REMOVE` persistence is intentionally not activated in P0.10 because the
canonical tombstone/removal representation is owned by the future operational
WorkoutPlan adapter.

## Provenance linkage

`PlanRevisionLink` permanently connects the created revision to:

- mutation instruction hash;
- planner decision hash;
- decision rationale hash;
- decision-time context hash;
- previous revision ID;
- gateway version.

This is the required audit chain before any production DB/ORM adapter is
allowed to mutate a current-plan pointer.
