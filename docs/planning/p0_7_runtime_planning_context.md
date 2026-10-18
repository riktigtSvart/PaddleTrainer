# P0.7 — AthletePlanningContextAggregate runtime projection v0.1

P0.7 connects the implemented planning foundation into the first frozen,
decision-time runtime context:

```text
CurrentTrainingState
        +
EntryGateDecision
        +
WorkoutFamilyRegistry
        ↓
RuntimePlanningProjection
        ↓
AthletePlanningContextAggregate
```

## What is resolved in P0.7

The context now stores typed projections of:

- current load-anchor status and recent observed exposure;
- global EntryGate mode/reasons;
- stimulus-specific gates;
- every built-in workout family's EntryGate eligibility;
- workout-family registry version/hash;
- automatically surfaced critical unknowns such as an UNKNOWN stimulus gate
  or partial/unknown load anchor.

The family-space projection remains explicitly scoped as:

```text
ENTRY_GATE_FAMILY_SPACE_V0.1
```

It is **not final workout authorization**.

P0.7 explicitly carries unresolved planning dimensions:

- goal priority;
- objective regime;
- sport readiness;
- planning authority;
- detailed availability;
- environment.

Therefore `final_authorization` is always false in this slice.

## Important cutoff correction

`information_cutoff_at` limits the newest real-world information that may
influence the decision. It must not be confused with the time at which a
derived state/gate snapshot was computed.

A derived snapshot may legitimately be produced *after* the evidence cutoff,
provided that:

1. its own `information_cutoff_at` is not later than the planning context
   cutoff; and
2. the derived snapshot exists by the planning context `as_of` decision time.

So the valid pattern is:

```text
18:00 evidence cutoff
18:01 CurrentTrainingState computed from <=18:00 evidence
18:02 EntryGate computed from that state
18:03 planning context / decision time
```

This is not future-data leakage.

By contrast, a source containing 18:04 evidence cannot enter an 18:00-cutoff
context, and a derived snapshot first becoming available after the 18:03
planning `as_of` time cannot be used in that context.

## Semantic context hash

Generated source object IDs are audit references, not planning semantics. The
context semantic hash therefore depends on the referenced source content hashes
and versions, not the generated `object_id` values. Exact IDs remain stored in
the contract for provenance/audit.

## P0.7 does not yet

- choose a workout;
- create candidate actions;
- resolve goal priorities;
- resolve sport-entry readiness;
- grant planning authority;
- evaluate detailed environment/availability;
- mutate a WorkoutPlan.

Those boundaries remain explicit for P0.8 and later integrations.
