# V24.10-E/2: immutable cohort database archives

This batch adds database storage behind the unchanged E/1 payload contract.
The committed E/1 foundation is `d9224fb0b3ea75b8095af2c93a36db4d8c827e79`.
Migration `e4f7a92c1836` extends `d83b9c61f204` and creates only two tables.
No cohort capture/read/delete endpoint is exposed in this batch; E/3 will bind
the services to the existing configured-owner API and perform the live control.

## Stored content and membership

`response_cohort_records` stores the E/1 nine-field `record_json`, its schema,
task, owner and three commitment columns, member count, generated record UUID
and server creation time. UUID/time stay outside the stable payload hash. The
complete request and C/D index are copied unchanged, including temporal/source
claims, missing-feature/history summaries, limitations and requested splits.
No full member observations, raw HR arrays, authentication token or source ZIP
is added to the archive.

Database uniqueness is `(user_id, record_schema_version, record_hash)`. Neither
`manifest_id` nor its split-manifest label is a mutable slot. Explicitly changed
valid content creates another immutable archive; no record is superseded,
repaired, renamed or overwritten automatically.

`response_cohort_members` contains exactly one link per whole selected session,
with canonical position, owner, actual workout, selected replay snapshot,
evidence set, provider and external session ID. The primary key is
`(record_id, canonical_index)`; workouts, replays and evidence sets are unique
within a record. A composite FK binds each member's `(record_id, user_id)` to
its owned parent. Count/position constraints bound the archive to 1–20 members.
Complete membership and its exact relation to the immutable payload are
verified by the service; foreign keys alone do not authenticate source truth.

## Capture service

`capture_response_cohort_record(db, manifest, user_id=...)` accepts the strict
existing `ResponseCohortManifest` and a **trusted server-selected** owner. It
does not accept a local E/1 candidate, API response/index or caller proof flags.
The athlete IDs in the request are checked pins. E/3 will select the configured
demo owner; this internal service is not authentication of a remote caller.

Use a fresh SQLAlchemy session with no transaction or pending work:

```python
async with SessionLocal() as db:
    receipt = await capture_response_cohort_record(
        db, manifest, user_id=server_selected_owner_id
    )
```

An active transaction, including one started by a caller's read or Core SQL
write, is rejected without committing or rolling back caller work. Capture
owns its subsequent transactions and cleanup. Ordinary readback below may
participate in a caller's read transaction.

Every capture, including a duplicate, runs the **actual C assembler** with
`verify_chronology=True`: all selected owned replay/normalized/lineage evidence,
current Polar routes/samples and pinned HR proof state must pass. It never
falls back to an archived index, omits a failing suffix or updates pins. The
existing token service may refresh and persist credentials; there are no
environmental provider calls or writes to scientific evidence/HR tables.

After E/1 builds and validates the payload, the assembler's read transaction
ends. A separate root write transaction locks the owner and selected source
parents, rechecks every owned session/replay/evidence relationship and pin,
and inserts the record and all links atomically. This is deliberately a root
transaction, not a savepoint that could accidentally commit a partial prefix.
Canonical source order plus the owner lock serializes cooperating captures;
database uniqueness remains the final guard against other writers.

The service reselects the serialized record with `populate_existing=True` and
verifies exact payload/column binding and every stored member before commit.
An existing archive and its member rows are locked and checked as well. Capture
requires acknowledged commit after this transactional readback. The 30-second
storage timeout bounds lock/transaction waits; the assembler retains its own
existing execution limits. Source checks occur per member during capture,
not at one simultaneous instant across Polar and the database.

| Result | Meaning |
| --- | --- |
| `CREATED` | Complete new record committed; original UUID/time returned |
| `ALREADY_PRESENT` | Identical retained record verified; original UUID/time returned |
| `REJECTED` | Invalid strict request or non-clean caller session |
| `WITHHELD` | Current source, ownership/pins, stored integrity, timeout or storage dependency failed |

A uniqueness race rolls back the entire attempted transaction. Its only
recovery is a new transaction that verifies an already committed, complete,
identical winner; it does not try another insert. Corrupt/incomplete winners
are withheld without repair. A damaged duplicated lookup hash can also be
found through the payload commitment and is rejected, not replaced.

Successful capture receipts state `database_record_persisted=true`, exact
record/index/request commitments, complete count, `round_trip_verified=true`
and `commit_acknowledged=true`. Source/current-source proof describes the
actual capture-time assembler checks. `cohort_storage_rows_written` is
`1 + member_count` for a new record and zero for an identical winner/repeat.

Failure never publishes a verified prefix, record commitment, raw exception,
token or private input value. Before storage, `storage_outcome=NOT_ATTEMPTED`
and database writes are zero. After an attempted write it reports
`NOT_CONFIRMED`, with persisted/write-count values **null**: a lost commit
acknowledgement can be ambiguous. This is not permission to fall back to a
prior source proof. The tested failures roll back all new archive rows.

## Archived readback and removal

`load_owned_response_cohort_record(db, record_id, user_id=...)` returns the
owned payload after its hash/row checks and complete stored source-link/pin
metadata checks. Missing and foreign record IDs both return `None`. Broken
owned payloads or links raise a fixed `CohortStorageError`; they never produce
an apparently complete record.

This read has no Polar calls, token access, assembler call or storage writes.
Its top-level source/current-source and chronology verification flags are
false. Historical C claims inside `record_payload.cohort_index` remain intact.
The read does not check current Polar/HR proof state or every normalized
measurement against the historical dataset. Explicit revalidation is E/3.

An archive is immutable while retained; this does not claim tamper-proof
storage against a database writer. The reader detects altered payloads,
duplicated commitment columns and incomplete/retargeted membership.

The member-to-source FKs use **NO ACTION, DEFERRABLE INITIALLY DEFERRED**, rather
than cascading away part of a retained archive. Deleting a linked workout,
replay or evidence set cannot commit while a retained member still refers to
it. Owner deletion cascades records, member links and the existing owned source
graph; deferred source checks allow that operation without ordering problems.

`delete_owned_response_cohort_record` is an explicit internal owner-authorized
removal helper. It deletes only the selected owned record and all its members,
retains source/HR evidence and requires a clean session. It can remove an owned
corrupt archive without needing current sources, so corruption cannot prevent
explicit removal. Source deletion may then proceed. No deletion endpoint or
automatic retention policy is added here. Migration downgrade removes only
the two new archive tables; it deliberately discards their archived records.

## Preserved scientific boundaries

`split_request_archived=true` describes archiving the full request, including a
null split manifest. It is not a global dataset assignment. Both receipt
`dataset_split_assignment_persisted` and the unchanged nested index's
`split_assignment_persisted` remain false. A single-session limited index may
be archived without promoting relative chronology or an evaluation split.

Training/numeric, causal and pre-exercise authority stays false. No model fit,
imputation, physiological lag estimate, fixed HR shift, fatigue label,
sensor-identity or acquisition-quality promotion is performed. The verified
1,663-ms export-clock origin remains a clock mapping, not a physiological lag.

## Validation scope

Tests execute actual ORM JSON serialization, SQL constraints, root
commit/rollback, migration-created tables and the C assembler on SQLite with
foreign keys enabled; current Polar/token inputs are controlled fixtures.
They cover repeated/source-changed requests, fresh-session ownership, metadata
rechecks after assembly, stored corruption and partial writes, commit failure,
timeout/cancellation, complete/incomplete simulated uniqueness-race winners,
source retention, explicit record/owner deletion and unchanged scientific rows.
PostgreSQL DDL is compiled and the additive migration chain is checked; an
actual local PostgreSQL migration/schema control is supplied for the user.
This local test suite does not claim a new live Polar/Windows/PostgreSQL run.
