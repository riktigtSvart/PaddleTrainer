# P0.12 — Planning persistence + read-only dev API

P0.12 adds durable persistence for the planning bounded context without
claiming ownership of the application's existing database schema.

## Persistence boundary

A planning-owned SQLite sidecar is used for this implementation slice:

- `planning_schema_meta`
- `planning_snapshots`
- `planning_audit_artifacts`

The sidecar deliberately does **not** change SQLite `PRAGMA user_version` and
does not modify any existing PaddleTrainer migration chain. This keeps the
bounded-context contract testable while the main application database
technology/schema remains outside this implementation package.

The same immutable semantics as the in-memory reference apply:

```text
same stable ID + same canonical contract -> ALREADY_PRESENT
same stable ID + different contract      -> conflict
```

## Persisted audit chain

`persist_auditable_planner_run()` stores:

- AthletePlanningContextAggregate as a planning snapshot
- PlannerInputEnvelope
- CandidateActionSet
- PlanningPolicySet
- PlannerDecision
- DecisionRationale
- PlannerRunRecord

Plan mutation instructions and `PlanRevisionLink` have a separate persistence
function so plan application remains an explicit step.

## Developer API

P0.12 provides a small FastAPI router/app under `/dev/planning` for inspection:

- health/schema status
- snapshot lookup
- athlete snapshot listing
- audit artifact lookup
- athlete artifact listing
- planner-run lookup

The API is intentionally **read-only**. It cannot create planner decisions or
mutate plans. Writes occur only through validated application services.

## Production boundary

This is not yet a claim that the SQLite sidecar is the final production
persistence architecture. The next integration decision should compare these
repository contracts with the actual PaddleTrainer main DB/migration layer and
choose a lossless adapter rather than silently introducing a second source of
truth.
