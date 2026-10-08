# V24.10-D: source-verified cohort API

The API now exposes the existing V24.10-C assembler, including its actual
owner/database/current-Polar checks and whole-session temporal audit. It does
not create a cohort table, persist split assignments, or require a migration.
The B and C command-line contracts and canonical index bytes are unchanged.

## Request

`POST /api/v1/integrations/polar/response-cohorts/assemble`

Content type: `application/json`. The body is the existing strict
`ResponseCohortManifest` from V24.10-A/B, not an index or a local verification
result. Existing prepared `cohort_request.json` files can be sent unchanged.
The request contains expected pins; the server establishes proof itself.

The only query option is `include_index=true` or `include_index=false` (default).
Other query parameters, repeated options, and alternative boolean spellings
are rejected. Chronology is always evaluated; there is no request option to
disable source checks or promote authorization.

The API bounds the raw JSON body to 128 KiB, including streams without a
Content-Length header. Duplicate object keys, invalid UTF-8/JSON, and non-finite
numeric constants are rejected before dependency resolution. Schema errors
return at most 20 diagnostics containing field paths and error types, never
input values, unknown field names, or exception messages. The execution limit
is 20 members; the service retains its 120-second assembly, 64-MiB snapshot,
16-MiB selected current-source, and 1-MiB index limits.

## Owner selection

The server looks up an **existing** user by its configured `demo_user_email`.
No user is created by this endpoint. `athlete_id` in the manifest is checked
against that user; it does not select the owner. Every replay snapshot still
requires the assembler's owner/session/evidence joins before any Polar call.
Missing and foreign snapshots use the same public error.

This is the project's current local demo identity mode, not authentication of
a remote caller or a production multi-user authorization scheme. The endpoint
does not add or imply such authentication. The owner's existing Polar
connection needs `training_sessions:read`, checked again after token refresh.
Credential refresh may update authentication records; scientific records,
environmental provider state, and dataset split assignments are not written.

## Successful response

HTTP 200 means that **all selected members passed source verification**. It
does not mean complete chronology, a complete evaluation split, statistical
independence, valid sensor quality, or permission to train a model.

The response envelope has:

| Field | Meaning |
| --- | --- |
| `schema_version` | API envelope version `0.1` |
| `representation` | `SUMMARY` by default; `FULL_INDEX` when requested |
| `cohort_index_hash_scope` | The hash commits the complete index, not this summary/envelope |
| `summary` | Counts, source/chronology/split flags, limitations, policy and limits |
| `cohort_index` | `null` by default; the unchanged full C index when requested |

The default summary omits member source commitments and detailed temporal
evidence. It retains temporal status, ordering, missing partitions, conflict
and possible-duplicate counts, and blocking reasons. A summary is not a full
index and cannot pass `verify_cohort_index_integrity`.

With `include_index=true`, the nested `cohort_index` is byte-for-byte
equivalent after canonical serialization to C's result for the same request
and unchanged sources. Its hash is not recomputed over the API envelope.
The same actual source verification is performed for each request, including
summary requests. The API does not accept an uploaded proof flag or fall back
to a cached index when current sources fail.

A single verified session therefore returns HTTP 200 with
`SINGLE_SESSION_TIME_BOUNDS_ONLY` and relative chronology/split flags false.
Missing or conflicting temporal metadata, possible duplicates, and incomplete
or reversed split requests remain explicit limitations in a source-verified
response. The service alone decides these flags. `training_authorized`,
`numeric_output_authorized`, causal and pre-exercise authorization remain false.
No fixed HR shift, physiological lag estimate, feature fitting or imputation is
introduced. The 1,663-ms export-clock origin is not a physiological lag.

## Failure response

Failures expose fixed `blocking_reasons`, a whitelisted `upstream_reason` when
available, and an optional canonical member position. They never expose a
successful prefix, full index, source hash, raw provider reply, credential or
database exception. `verified_member_count=0`, `members=[]`, and index/hash,
totals and temporal audit are null. Authorization flags are false.

| HTTP | Examples |
| --- | --- |
| 400 | Malformed JSON, duplicate keys or non-finite constants |
| 403 | Owner pin mismatch or missing Polar scope |
| 404 | Missing configured owner/connection, missing or foreign snapshot, missing selected current session |
| 409 | Pin/source/proof divergence, inconsistent saved evidence, ambiguous current session |
| 413 | Request, selected current source, snapshot or index size limit |
| 415 | Missing/unsupported JSON content type |
| 422 | Invalid manifest/query or more than 20 execution members |
| 502 | Polar request failure or malformed current-source response |
| 503 | Local dependency failure or invalid internal publication result |
| 504 | Assembly execution time limit |

`COHORT_MEMBER_EVIDENCE_VERIFICATION_FAILED` can carry distinct fixed upstream
codes such as `REPLAY_CURRENT_POLAR_SOURCE_CHANGED`,
`REPLAY_HR_PROOF_STATE_CHANGED`, `REPLAY_SNAPSHOT_INTEGRITY_FAILED`, or
`REPLAY_STORED_SNAPSHOT_BINDING_FAILED`. These identify why source proof was
withheld without treating caller-supplied diagnostics as authority. Every
response has `Cache-Control: no-store`.

## Validation

Tests invoke the actual C assembly/replay/database verification on three
distinct fixture sessions with canonical identity order different from
wall-clock order. They compare the API's full index to C, repeat responses,
and verify that snapshots, HR proofs and scientific records are unchanged.
Only current Polar access and token retrieval are replaced in those fixtures.
Additional controls exercise single-session limitations, incomplete/reversed
splits, unsupported time bounds, actual owner/pin/source/proof failures,
corrupt saved data, schema rejection, JSON streaming bounds, redaction, router
registration and the fixed HTTP error translations.

Local tests use SQLite fixtures. The separate large probe uses the provided
real 3,038-slot HR source and matching TCX with explicitly synthetic workload,
route and environmental scaffolding. Neither establishes a live multi-session
Polar cohort, production database behavior, or model readiness. The Windows
live control compares the new API with the user's existing C control index.
