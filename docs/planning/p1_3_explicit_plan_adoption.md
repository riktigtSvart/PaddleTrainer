# P1.3R — Explicit Plan Adoption Service + Read API (rebased)

P1.3 establishes an explicit application workflow that can create revision 1
for the **current** state of one existing `PlannedWorkout`.

P1.3R does not change that domain behavior. It rebases the integration onto the
current Phase Reconciliation / Phase Clarification API tree.

## Workflow

1. `GET /api/v1/workouts/{workout_id}/plan-adoption-preview`
   - read-only current-app capture;
   - returns `source_content_sha256` as the concurrency token;
   - reports whether `CURRENT_STATE_BASELINE_ONLY` adoption is allowed.
2. Caller explicitly sends:
   - `expected_source_content_sha256`;
   - `acknowledge_current_state_baseline_only=true`.
3. `POST /api/v1/workouts/{workout_id}/plan-adoption`
   - captures current state again;
   - rejects stale preview hashes;
   - mints planning-owned revision and occurrence identities;
   - the P1.2 repository locks and re-hashes the mutable source in the same
     transaction;
   - commits only after baseline acceptance.
4. `GET /api/v1/workouts/{workout_id}/authoritative-plan`
   - owner-scoped read-only authoritative identity/revision view.

## Authority semantics

Baseline revision remains:

- `origin = ADOPTED_CURRENT_STATE`
- `history_claim = CURRENT_STATE_BASELINE_ONLY`
- `revision_number = 1`
- `previous_revision_id = null`

External capture IDs remain provenance only. The source `PlannedWorkout` is not
mutated and authority does not extend retroactively before explicit adoption.

## Conservative Polar boundary

`STORED_POLAR_TARGET` adoption remains fail-closed while provider snapshot
intent and mutable ORM edit intent are not fully reconciled. The blocker is
`POLAR_SOURCE_RECONCILIATION_REQUIRED`.

## Rebase integration invariant

P1.3R must not remove existing Phase Reconciliation functionality. The main API
router includes all three modules:

```text
phase_reconciliations
phase_clarification_storage
planning_adoption
```

The P1.3 wiring regression test now checks this explicitly.

## Migration coexistence

P1.3 itself adds no migration. In the current repository, an independent later
Phase Clarification migration extends P1.2:

```text
c91f7a3e2d40 -> da7e4c92b610
```

Therefore the repository Alembic script head is `da7e4c92b610`, while the P1.2
planning tables remain owned by `c91f7a3e2d40` and are not rewritten by P1.3R.
