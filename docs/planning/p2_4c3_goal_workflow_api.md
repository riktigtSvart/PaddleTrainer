# P2.4C3 — Cycle-goal API and atomic measurement ingestion

Baseline: `7e0c0492c9b2bd1a1850802e5d0f106589decb99`.

This slice exposes the C1/C2 application services through the existing
FastAPI router and supplies a typed path for recording scalar observations
with their procedure/condition context. It adds no frontend or migration.
The existing planner, plan mutation and personal learning models are unchanged.

## HTTP surface

All paths below are relative to `/api/v1/planning/goals` by default. The
application's configured API prefix remains authoritative. The existing
`/docs` page describes the strict request/response schemas.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/catalog` | Versioned 13-capability, 25-metric vocabulary and four roles |
| POST | `/macrocycle-plans` | Register an explicit macrocycle decomposition |
| GET | `/macrocycle-plans` | List owned immutable macrocycle versions |
| GET | `/macrocycle-plans/{artifact_id}` | Restore one exact macrocycle version |
| POST | `/mesocycle-protocols` | Register a prospective C1 measurement protocol |
| GET | `/mesocycle-protocols` | List owned immutable mesocycle versions |
| GET | `/mesocycle-protocols/{artifact_id}` | Restore one exact protocol version |
| POST | `/measurements` | Atomically record a scalar source and its audit registration |
| GET | `/measurements` | List owned measurement registrations |
| GET | `/measurements/{artifact_id}` | Restore an exact measurement registration |
| POST | `/assessments` | Run or recover the C2 assessment for an exact cutoff |
| GET | `/assessments` | List owned immutable assessments |
| GET | `/assessments/{artifact_id}` | Restore an exact C2 assessment |

POST returns 201 for a new committed artifact and 200 for an identical retry.
A valid assessment may have a `withheld` verdict; it is still a stored result.
GET returns 200, with `Cache-Control: no-store`. Lists accept `limit` (1–50,
default 25) and `offset` (0–100000), order by database persistence time then
artifact ID, and return `items`, `has_more`, `limit` and `offset`. Each returned
item is restored through its domain loader before being returned. There is
no implicit latest-version substitution. Detail reads optionally accept an
aware ISO `available_by` time. Future availability/cutoff claims are rejected.
Unknown/duplicate query fields are rejected rather than silently ignored.

The catalog is public static vocabulary and performs no database read.
All other operations use the existing application demo-owner identity model:
`identity_scope = APPLICATION_DEMO_USER`. The server resolves the already
existing configured owner. Missing owner returns 404 without creating a user.
No athlete/user ID, authority flag or verification claim is accepted from a
request body. This is the existing identity model, not new authentication.
`goal_owner` is an explicit dependency for a future authenticated identity.

Ownership applies to source periods, direct parent references, list queries
and artifact detail reads. Unknown and other-owner IDs produce the same 404.
The C1 loaders additionally verify all deeper immutable parent ownership.
Read preflight transactions close before calling C1/C2 services that require
a known-fresh session. Borrowed/unknown transactions are not taken over.

## Goal-profile requests

The macrocycle POST body is the strict C1 `MacrocyclePlanProposal` shape:

- canonical `macrocycle_period_id` UUID;
- integer `revision` 1–64 and optional `supersedes` reference;
- explicit `goals`, `mesocycle_directives` and `rationale`.

The mesocycle POST body is the C1 `MesocycleProtocolProposal` shape:

- canonical `mesocycle_period_id` UUID;
- integer `revision`, optional `supersedes`, exact `macrocycle_plan` reference;
- `endpoints` and `rationale`.

A reference has `artifact_id` and lowercase SHA-256 `content_hash`. The
endpoints preserve the exact C1 procedure, windows, role and optional primary
change requirement. Body arrays are bounded (13 capabilities, 4096 directives,
64 endpoints and 32 procedure conditions). Nonempty bounded strings,
canonical decimal strings and offset-aware ISO datetimes are required.
Unknown fields are forbidden throughout the nested schemas. Revisions reject
strings, booleans and floating point values. Numeric requirements must use
canonical decimal strings rather than JSON numbers.

All C1 hierarchy, complete decomposition, chronology, scientific-boundary and
version-chain checks remain in the existing service. New registration captures
current source periods. Exact retry restores original immutable sources even
when current period ownership/title/dates have changed. An existing owned
slot is therefore identified before checking mutable periods for a new write.
A later revision still requires current owned source periods.

## Measurement request

`GoalMeasurementInput` takes:

```json
{
  "client_request_id": "00000000-0000-0000-0000-000000009001",
  "protocol_reference": {
    "artifact_id": "pt-goal:<exact 64-character digest>",
    "content_hash": "<exact protocol content hash>"
  },
  "endpoint_key": "<registered endpoint key>",
  "value": "50",
  "observation": {
    "started_at": "2030-01-02T09:00:00Z",
    "ended_at": "2030-01-02T09:10:00Z",
    "completion": "complete",
    "result_level": "complete_protocol_result",
    "conditions": [
      {
        "condition": "<exact registered condition, in registered order>",
        "status": "met",
        "observation": "<what was observed>",
        "evidence_reference": "<retained evidence reference>"
      }
    ],
    "body_mass_kg": "70",
    "execution_evidence_reference": "<execution evidence reference>"
  }
}
```

Angle-bracket values above are placeholders, not a runnable protocol. The
actual protocol determines every required condition and its scheduled windows.
The server copies metric key, unit, evidence kind, full procedure, task,
modality and processing from the exact committed endpoint. The request cannot
replace them. It supplies the observed scalar and execution assertions only.

The client-generated request UUID is an application idempotency token, not a
provider identifier. Its stable slot is scoped to the server-selected owner.
The service derives separate application UUIDs for the new Assessment and
Measurement rows. Reusing one token with changed intent produces 409.
Equivalent UTC-offset representations normalize to the same intent.

`value` is a canonical finite decimal string within the C2 numeric range.
The existing numeric source column remains Float. Inputs must round-trip
through that column's decimal representation; values that would silently
lose decimal digits are rejected. This does not claim exact physical/sensor
precision. The exact original input is also retained in the immutable audit.

Execution must fit wholly within either registered measurement window and
end before server recording time. The service never invents execution or
condition evidence. `completion` supports complete/incomplete/unknown;
`result_level` supports complete_protocol_result/within_protocol_trial/unknown;
condition status supports met/not_met/unknown. Conditions need the exact
registered names/order and nonempty observations/evidence references.
Unknown or violated conditions are retained without being promoted to met.
Optional body mass, when supplied, must be positive. If relative VO2 body
mass is missing, C2 keeps its existing unresolved/withheld behavior.

## Atomic source persistence

The new `GOAL_MEASUREMENT_REGISTRATION` audit kind uses the existing store.
The registration pins the exact C1 semantic hash, complete canonical JSON
SHA-256 and database persistence time. Its frozen proposal, copied execution,
source row identities, server recording time and authority boundary replay
strictly from that parent.

`SqlAlchemyGoalMeasurementWriter` appends an existing-model Assessment parent
and numeric Measurement child in the same transaction as the immutable
registration. It checks for source identity collisions rather than overwriting
rows. A source envelope is checked against the C2 65536-byte limit before any
write. The ordinary source metadata contains the C2 execution object and a
registration ID/hash link. The source is labeled GOAL_PROTOCOL, with no inferred
sport, physiological validity or provider verification.

Before commit, the service restores its audit read-back and independently
reads/verifies the actual scalar and parent rows, including their values,
units, owner, metadata and times. Missing/skipped/changed source writes cannot
return a successful receipt. The writer never commits on its own. Source,
audit and session must be the exact same fresh transaction owner.

Failed/skipped commit returns no durable success and rolls back its changes.
If a disconnect follows a successful commit, an identical HTTP retry restores
the original registration. Later changes or deletion of mutable scalar rows
do not change that registration and are not repaired by retry. Detail/list
measurement endpoints return frozen **registrations**, not a live source view;
`source_rows_immutable` remains false. C2 still captures the current existing
measurement tables, with its original source-availability limits.

## Assessment request and response

The assessment POST body is:

```json
{
  "protocol_reference": {
    "artifact_id": "pt-goal:<exact 64-character digest>",
    "content_hash": "<exact protocol content hash>"
  },
  "activity_cutoff_at": "2030-01-27T11:00:00Z"
}
```

No selected outcomes, error override, acceptance threshold or capability-role
replacement is accepted. C2 performs its complete source census, candidate
classification, exact rational changes and conditional sensitivity analysis.
The same cutoff reuses its frozen census, including gaps; a later cutoff may
see late or edited rows. Multiple reports are not independent trials.

Artifact responses include `identity_scope`, full `artifact`, database
`durable_available_at`, `reused`, `committed` and boundary flags. The full
artifact remains canonical C1/C2/C3 contract data. The envelope is an HTTP
representation and is not a replacement parent-hash source.

`measurement_schedule_preregistered` concerns the C1 schedule before baseline,
not prospective issuance of a result or an independent experiment. Execution
assertions, standardization, error-model validity, physiological adaptation,
causality and comparative utility are not upgraded by API registration.
`planning_authorized`, `planning_utility_supported` and
`physiological_adaptation_established` remain false.

## Failure and resource behavior

- 404: owner/owned period/owned artifact is unavailable.
- 409: immutable identity conflict, invalid domain contract, stored integrity
  failure, unsupported source size or an unowned transaction boundary.
- 413: actual streamed POST body exceeds 1 MiB, regardless of Content-Length.
- 422: invalid/extra request fields, types, query fields or future API cutoffs.
- 503: persistence/transaction closure could not establish success.

Responses expose stable error codes rather than raw SQL or stored contracts.
HTTP inputs do not relax any C1/C2 frozen schema. No destructive source update,
provider call, automatic model update or planning authorization is introduced.

## Verification

The targeted 24-file gate contains 484 passing tests, including 84 new cases.
New domain/HTTP tests exercise all thirteen operations, actual application
router registration/OpenAPI schemas, owner isolation, strict input typing,
body/query bounds, pagination, C1 frozen retries, full measurement-to-C2 flow,
source collisions, conditional unknowns, exact replay, source/audit read-back,
failed/skipped/uncertain commits and tamper rejection.

HTTP gate tests use real production adapters on isolated file SQLite through
an async bridge. An additional local ASGI smoke check uses a real SQLAlchemy
AsyncSession with aiosqlite; that optional driver is not added to the Windows
project/gate dependencies. Neither check establishes live PostgreSQL
integration or scientific validity. Existing ORM datetime.utcnow defaults and
some local framework versions emit deprecation warnings.
