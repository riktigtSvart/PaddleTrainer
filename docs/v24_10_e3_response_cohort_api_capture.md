# V24.10-E/3: configured-owner cohort archive API and live control

Foundation: committed E/2 `e5e1e74d15b977a5676b47054fc040d68066acc7`.
The additive E/2 migration head remains `e4f7a92c1836`; there is no new
migration or dependency. Restart the API after installing this batch.

## Endpoints

All paths are below `/api/v1/integrations/polar/response-cohorts`.

| Method and path | Input | Successful response | Source claim |
| --- | --- | --- | --- |
| POST `/capture` | Existing strict `ResponseCohortManifest`; no query | E/2 receipt: `CREATED` or `ALREADY_PRESENT`, HTTP 200 | Actual capture-time C assembler and acknowledged complete archive commit |
| GET `/records/{record_id}` | UUID; optional literal `include_record=true` or `false` | Owned archive metadata; unchanged E/1 payload only when requested | Stored payload, request/index and complete owned member/link/pin binding only |
| POST `/records/{record_id}/revalidate` | Strict empty JSON object `{}`; optional literal `include_index=true` or `false` | `CURRENT_SOURCES_MATCH_ARCHIVED_COHORT_WITH_LIMITATIONS`; summary by default | Actual revalidation-time C assembler matching the retained complete index |

The D `/assemble` endpoint and its index remain unchanged. The router is
registered in the existing API. Every response has `Cache-Control: no-store`.
GET summaries never stand in for full-payload hash verification; record UUID
and server creation time remain outside the unchanged E/1 record hash.

## Owner and transaction boundary

The API selects the existing user by `demo_user_email`. It does not create a
user, accept an owner selector or authenticate a remote caller. The request's
`athlete_id` is only a checked pin. This is the project's existing configured
local demo API, not a new multi-user authentication scheme.

Capture first rejects active transactions/pending work. It selects only the
owner UUID, ends its own lookup transaction, then invokes the unchanged E/2
capture service with that trusted owner and a clean request session. E/2 runs
the actual C source checks on every capture, including repeats, and owns the
separate atomic storage transaction. There is no API-local archive writer.

The receipt comes directly from the trusted E/2 service after transactional
readback and acknowledged commit. Capture does not add a fallible second read
after commit. New records have all selected whole-session member links; a
repeat returns the original record ID, timestamp and stable commitments.

Missing and foreign record UUIDs return the same 404 response. Archive reads
and revalidation use only the configured owner's record and complete owned
source links. No list, delete, retention or automatic replacement endpoint is
added. Explicit changed manifest content remains a separate immutable capture.

## Historical read and current revalidation

GET performs no Polar call, token access, source assembly or storage write.
Its top-level `source_evidence_verified` and
`current_source_evidence_verified` are false. Historical C claims inside
`record_payload.cohort_index` remain unchanged. A source change or missing
Polar connection therefore does not turn a historical read into a new proof.

Revalidation reads the checked retained manifest, runs the actual C assembler
with chronology enabled, verifies index integrity and requires exact equality
with the complete archived index. It rechecks the owned archive after source
assembly to detect deletion, corruption or link changes during the operation.
No local candidate, supplied index, updated pin or request authority is accepted.

Source failure withholds proof without falling back to the archive. A valid
different current index yields `COHORT_ARCHIVE_CURRENT_INDEX_CHANGED` (409);
it does not overwrite or promote the retained record. A changed archive during
the operation yields `COHORT_ARCHIVE_CHANGED_DURING_REVALIDATION` (409).
Success is per-member revalidation-time verification, not a simultaneous
provider/database snapshot or a guarantee that sources will never change.

## Bounded requests and safe failures

POST requires JSON, accepts a Windows UTF-8 BOM and rejects duplicate keys,
nonfinite numbers, invalid UTF-8 and malformed/deeply nested JSON. A 128-KiB
streamed body limit applies before Pydantic, database and provider calls.
GET forbids a body. Unknown/duplicate query parameters and caller authority
fields are rejected. Validation details expose only allowlisted field paths
and error types, with at most 20 errors; private values/key names are redacted.

| Failure | HTTP |
| --- | --- |
| Malformed JSON / media type / byte limit | 400 / 415 / 413 |
| Strict request, path, query or execution member limit | 422 |
| Owner pin mismatch / missing Polar scope | 403 |
| Missing configured owner, owned record or source | 404 |
| Pin/source/archive integrity or revalidation conflict | 409 |
| Provider request or malformed current source | 502 |
| Storage/internal dependency | 503 |
| Assembly/storage timeout | 504 |

The capture failure's generic `COHORT_CURRENT_SOURCE_CHECK_FAILED` is paired
with a fixed allowlisted `upstream_reason`; the HTTP status follows the known
assembler reason. Failed operations return no record/hash/payload/index or
successful member prefix. Raw dependency messages and credentials are omitted.
Before attempted storage, writes are zero. After attempted or uncertain storage,
the outcome is `NOT_CONFIRMED` and persisted/write counts are null; failure
does not falsely assert that an acknowledged/lost commit wrote nothing.

## Reusable live control

`tools/check_response_cohort_api_capture.py` accepts the existing pinned
`cohort_request.json` and either a complete C index or D `api_full_1.json`.
It requires the same local E/2 database head and a loopback HTTP API; redirects
and proxy forwarding are disabled. Output is a fresh exclusive directory.

The control first checks local payload/hash binding, then obtains the actual
D current full index. It requires equality with the supplied C/D reference
**before issuing any capture**. It never edits pins or captures new environment
evidence to repair a mismatch. Local integrity is only a comparison target.

It captures twice, checks the original record ID/time, expected E/1 record
hash, acknowledged readback and complete member count. It reads summary and
full archives, compares repeated bytes and checks that ordinary readback has
no current proof. Explicit summary/full revalidation must match the original
C/D index without archive writes.

Wrong snapshot pin, wrong owner pin, forbidden authority, uploaded local
candidate, missing record and forbidden revalidation authority are then
rejected. The original archived bytes must remain unchanged. Foreign record
access is covered by automated API tests; the live control does not create a
second owner or assert a new live foreign-record experiment.

Read-only database checks compare all 14 pre-existing scientific table counts,
exact hashes of the complete HR timebase/acquisition rows, and record/member
count deltas. Negative controls must not change storage. This is count
preservation for other scientific tables, not byte-for-byte verification of
all normalized data. Existing token refresh may persist credentials; neither
capture nor revalidation calls environmental providers or writes scientific
evidence, global split assignments or HR proofs.

The original request/reference bytes are preserved. Raw API results and the
final `live_summary.json` / `storage_preservation.json` are saved in the new
output directory. A repeated successful run may start with `ALREADY_PRESENT`
and adds no archive rows. A stopped run retains results and any acknowledged
archive; no archive is automatically deleted, repaired or replaced.

## Scientific scope and validation

Training/numeric authority remains false; no model fit, imputation, fatigue
label, fixed HR shift or physiological lag estimate is introduced. The saved
1,663-ms export-clock mapping is not physiological delay. A limited single
session can be archived/revalidated while relative chronology and the complete
TRAIN/VALIDATION/TEST split remain unverified.

Tests exercise the actual API handlers, C assembler, E/2 capture/read service,
SQL serialization, transactions and foreign keys on SQLite. Only provider,
credential and async database adapters use controlled fixtures. The reusable
control runs through these actual handlers and executes its actual SQL count
and HR-row checks. Existing D behavior, migration head and E/1 contract are
covered by the full regression. The release records actual test counts in
`VALIDATION.json`; local fixtures are not a new live Polar/Windows/PostgreSQL
run. The user's supplied Windows control is the live verification step.
