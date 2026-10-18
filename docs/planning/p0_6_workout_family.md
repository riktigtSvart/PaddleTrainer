# P0.6 — WorkoutFamilyPrescription runtime foundation

P0.6 creates a versioned workout-family registry and the first four canonical
families:

- `KAYAK_EASY_TECHNICAL@v0.1`
- `KAYAK_LONG_AEROBIC@v0.1`
- `STRENGTH_REFERENCE_AND_DEVELOPMENT@v0.1`
- `RUN_EASY_AEROBIC_FALLBACK@v0.1`

A workout family is a reusable prescription envelope between abstract planning
stimulus and a later concrete `WorkoutPlanContract`.

## Important boundary

`FamilyEntryGateAssessment` evaluates **only** the EntryGate contribution.

```text
EntryGate eligibility
    != final workout authorization
```

Final availability must later intersect with sport-entry readiness,
environment/equipment, calendar availability and planning authority.

Therefore an `ELIGIBLE` family in P0.6 is not yet permission for the planner to
schedule that workout.

## Dose semantics

Dose constraints retain `HARD / SOFT / FREE` strictness and typed dimensions.
The current built-ins use duration, RPE, movement count, sets, RIR and
qualitative dose constraints.

Heart rate in the easy endurance families is an observation, not a forced
prescription target.

## Reanchor-compatible families

`KAYAK_LONG_AEROBIC@v0.1` carries the 60–75 minute reanchor envelope but marks
it explicitly as **not a mandatory duration quota**.

`STRENGTH_REFERENCE_AND_DEVELOPMENT@v0.1` is training plus reference building,
not maximal testing: 2–4 main movements, about 2–3 sets, RIR 2–4 concept,
moderate-low repetitions, no failure/grinding, and one progression dimension
at a time.

## Non-families

- PFT + easy kayak is a session-composition pattern, not a workout family.
- Hiking is incidental/external physical-load observation, not a workout
  family.
- `CONTROLLED_AEROBIC_DEVELOPMENT` remains deferred until personal reanchor
  evidence supports parameterization.
