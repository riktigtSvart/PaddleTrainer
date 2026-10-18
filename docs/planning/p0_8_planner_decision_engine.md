# P0.8 — Minimal PlanningPolicy + PlannerDecision Engine

P0.8 is the first runtime layer that makes a structured planning decision.
It performs **no plan mutation**.

```text
Frozen AthletePlanningContextAggregate
    -> PlannerDecisionRequest
    -> PlannerInputEnvelope
    -> CandidateActionSet
    -> PlanningPolicySet
    -> PolicyExecutionRecord
    -> PlannerDecision
```

## Candidate generation boundary

P0.7 explicitly marks its training-space projection as provisional until the
remaining decision-space dimensions are integrated. P0.8 therefore does not
create workout-family selection candidates while `final_authorization=false`.
The exclusion and its reason are retained in `CandidateActionSet`.

This enforces the invariant that authorization problems are handled before
soft ranking rather than by generating an invalid action and hoping that a
later policy fixes it.

## Minimal policy set

`minimal_planner_policy_set_v0.1` contains:

- `GLOBAL_ENTRY_GATE_BOUNDARY@v0.1` — HARD
- `FINAL_AUTHORIZATION_BOUNDARY@v0.1` — HARD
- `CRITICAL_UNKNOWN_INFORMATION@v0.1` — SOFT

Policies and decisions remain separate. Every policy/action evaluation is
stored in `PolicyExecutionRecord`.

## No scalar utility and no arbitrary tie-break

P0.8 does not invent a numeric benefit/cost score. If multiple viable actions
remain and no explicit policy separates them, the result is
`HUMAN_DECISION_REQUIRED`.

The stable ordering used for hashing is not used as a planning preference.

## Expected current behavior

The P0.7 runtime projection still has unresolved goal, regime, sport-readiness,
authority, availability and environment dimensions. Therefore the current
end-to-end P0.8 behavior is expected to be:

```text
final_authorization=false
    -> workout-family actions excluded during generation
    -> DEFER required by hard authorization policy
    -> DEFERRED_PENDING_CONTEXT
```

This is a correct bounded decision, not a planner failure.

P0.9 will add decision-time structured rationale and reproducible replay around
this engine.
