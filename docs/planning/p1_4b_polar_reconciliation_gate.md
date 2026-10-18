# P1.4B Polar reconciliation gate integration

P1.4B consumes the transient P1.4 reconciliation artifact in the plan-adoption eligibility path.

A reconciliation artifact is accepted only when its content hash verifies and all capture/source/external-plan binding fields match the exact capture under consideration. A `sync_projection_match` with supported future baseline adoption satisfies the source reconciliation gate.

The authoritative write remains disabled because reconciliation lineage is not yet persisted in the immutable plan revision schema. The blocking condition is `POLAR_RECONCILIATION_AUDIT_PERSISTENCE_REQUIRED`.

Actual execution start time is out of scope. Source reconciliation compares provider planned intent with current plan state; plan-vs-execution timing belongs to execution comparison.
