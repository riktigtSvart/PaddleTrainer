# P0.2 / P0.3 Notes

## P0.2 — Snapshot persistence semantics

The implementation now defines an explicit repository port and executable
in-memory reference semantics:

- same stable ID + same immutable contract -> idempotent `ALREADY_PRESENT`;
- same stable ID + different content -> conflict;
- stored canonical contract must verify its content hash on decode.

Content hashes are **semantic hashes**: generated snapshot/context IDs and
`created_at` do not affect them. Athlete identity, `as_of`, information cutoff,
versions, source provenance and actual payload remain hash-significant.

Snapshot payloads are recursively frozen before hashing, closing the mutable
container hole left by the initial P0.1 skeleton.

No production database migration is included yet.

## P0.3 — Evidence/source boundary

`EvidenceItem` explicitly separates:

- `observed_at`: when the real-world event/measurement occurred;
- `available_at`: when the planner could actually know it;
- `created_at`: when this evidence contract was materialized.

This prevents delayed feedback/imports from leaking backward into earlier
planning decisions.

Adapters are deliberately constrained: they translate what a source record
actually establishes into planning evidence. They do not infer capability,
fatigue/readiness or next-workout decisions.

The next implementation slice is P0.4:
`CurrentTrainingState + LoadAnchorState`, consuming `EvidenceBundle`.
