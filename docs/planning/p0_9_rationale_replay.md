# P0.9 — Structured Decision-Time Rationale + Deterministic Replay

P0.9 closes the auditability gap around the P0.8 decision engine.

```text
Frozen Context
    -> Input Envelope
    -> Candidate Set
    -> Policy Execution
    -> Planner Decision
    -> Structured Decision Rationale
    -> Planner Run Record
```

## Decision rationale

`DecisionRationale` stores reason codes and references, not reconstructed prose.
It includes:

- selected action ID when one exists;
- primary reason codes;
- binding constraint codes;
- policy references;
- alternatives excluded during candidate generation;
- alternatives eliminated or left viable by policy execution;
- high/blocking critical unknowns;
- unresolved planning dimensions;
- review/rebuild triggers.

`accepted_tradeoffs` remains empty in P0.9 because no validated trade-off/value
resolver exists yet. The implementation must not invent one retroactively.

Natural-language explanation may later render this record, but may not add a
reason that is absent from it.

## Replay record

`PlannerRunRecord` links exact semantic hashes for:

- planning context;
- input envelope;
- candidate set;
- policy set;
- policy execution;
- planner decision;
- decision rationale.

It also records engine, policy-set, candidate-generation and rationale-builder
versions plus the original decision time.

The current P0.8/P0.9 engine is deterministic, so runs are marked
`DETERMINISTIC_EXACT`. Exact replay is only promised for such runs. Future
stochastic/model-driven planners must use `AUDIT_ONLY` unless all state needed
for exact replay (including model/config/random state where applicable) is
captured.

## Temporal integrity

Replay evaluates the original frozen decision-time inputs. Later observations
may evaluate the decision in the future learning layer, but may not rewrite the
stored rationale or original run record.

P0.9 still performs no plan mutation.
