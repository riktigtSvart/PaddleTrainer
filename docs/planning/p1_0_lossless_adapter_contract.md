# P1.0 — Current App Plan Read → Planning Capture Contract

## Purpose

The adapter answers one narrow question:

> What exactly did the current application expose about this stored workout at
> this read time, without pretending that the read is an immutable plan
> revision?

## Accepted source

Pinned source contract:

```text
api_rules_version = plan-contract-read-api-0.1-draft1
contract_release  = DRAFT1
schema_version    = 0.1
status            = PLAN_CONTRACT_READ_WITH_LIMITATIONS
```

Accepted source kinds:

```text
STORED_ORM_WORKOUT
STORED_POLAR_TARGET
```

A source version/authority change fails closed.

## Mandatory non-authority assertions

The adapter requires:

```text
database_writes                  = 0
provider_calls                   = 0
numeric_output_authorized        = false
capability_update_performed      = false
historical_plan_content_verified = false
actual_phase_alignment_verified  = false
```

It also requires the source limitation:

```text
STATELESS_READ_CAPTURE_NOT_A_PERSISTED_PLAN_REVISION
```

and the adapter historical status:

```text
UNVERIFIED
```

## Identity separation

The following identities are intentionally different:

```text
source_workout_id
    application PlannedWorkout UUID

planning_logical_plan_id
    planned-workout:<source_workout_id>
    stable binding key only

external_contract_plan_id
    capture-scoped ID from the current read API

external_contract_plan_revision
    current contract/provider value, not a PaddleTrainer revision lineage

external_occurrence_ids
    capture-scoped expanded occurrence IDs from the current contract
```

No field is silently promoted into another identity role.

## Lossless preservation

The complete source read is retained as canonical JSON and hashed independently.
All extracted fields are therefore auditable against the exact adapter input.

## Promotion rule

P1.0 always emits:

```text
authoritative_revision_promotion_allowed = false
```

with blockers:

```text
STATELESS_READ_CAPTURE_NOT_A_PERSISTED_PLAN_REVISION
HISTORICAL_PLAN_CONTENT_UNVERIFIED
CAPTURE_SCOPED_EXTERNAL_PLAN_ID
CAPTURE_SCOPED_EXTERNAL_OCCURRENCE_IDS
```

Only the later authoritative adoption/revision contract may clear these
blockers.
