# V24.10-E/1: immutable cohort storage contract

This batch defines a stable record payload and implements its **pure local**
integrity/binding checks. It adds no database model, migration, endpoint or
live-source verification. The committed D foundation is
`cf00b88e96b4a8ebf02839517fadbdad0e770b3b`; Alembic remains `d83b9c61f204`.

## Record payload — implemented

`app.services.response_cohort_storage_contract` exports
`build_cohort_record_payload(manifest, index, owner_id=...)` and
`check_cohort_record_payload(payload)`.

| Field | Meaning |
| --- | --- |
| `record_schema_version` | `0.1` |
| `owner_id` | Canonical UUID bound to every selected member's athlete pin |
| `task` | `RETROSPECTIVE_HR_RESPONSE_WITHIN_ATHLETE` |
| `claim_scope` | `ARCHIVED_REQUEST_AND_ASSEMBLER_INDEX_ONLY` |
| `request_manifest_hash` | Existing A commitment to the canonical request |
| `cohort_index_hash` | Existing C/D commitment to the complete unchanged index |
| `request_manifest` | Full canonical manifest, including the requested split |
| `cohort_index` | Full C `assembly_version=0.2.0` index, not an API summary/envelope |
| `record_hash` | SHA-256 of all preceding fields using existing canonical JSON |

Only these nine record fields are accepted. The owner and version participate
in the record hash. The future row's UUID and server creation timestamp are
outside the stable payload hash: repeat capture of identical content must not
create a different content identity. A creation timestamp describes storage
time, not the exercise wall clock, HR sample clock or physiological lag.

The index is copied intact; its hash, member source commitments, temporal
evidence, requested splits, missing-feature/history summaries and limitations
remain unchanged. Raw observation and HR arrays are not added. The payload
limit is 2 MiB, the nested C index limit is 1 MiB, and the execution membership
limit is the existing 20 whole sessions.

The checker requires the complete supported C index and checks its hash/counts,
request identity/hash, canonical membership order, every snapshot/evidence/
replay/version pin, owner, session group, and exact requested split resolution.
It checks strict count types, source commitment hash syntax, temporal evidence
commitments, and agreement with a recomputed **pure metadata** temporal audit.
It rejects unknown root/member fields, removed training limitations, boolean
counts, promoted permissions, imputation/fitting, sensor-quality promotion,
fixed HR shifts and any physiological lag value. Rehashing altered JSON does
not excuse mismatched request/index bindings. These checks do not reconstruct
the member dataset or prove that its source claims are true.

## Meaning of local success — implemented

`LOCALLY_VALID_COHORT_RECORD_PAYLOAD` has claim scope
`LOCAL_PAYLOAD_INTEGRITY_AND_REQUEST_INDEX_BINDING_ONLY`.
`payload_integrity_verified` and `request_index_binding_verified` are true;
ownership authorization, source/current-source proof, verified chronology,
persisted database record/split and training/numeric authority are false.

The original nested index can still contain its historical assembler source
or chronology claims. The local checker does not promote them into new live
proof. A locally consistent fabricated payload is not authenticated by its
hash. Hashes are not signatures, database receipts or evidence of source
freshness. Server persistence must run its own actual assembler.

`tools/check_response_cohort_storage.py` offers:

```text
prepare --manifest request.json --index chronology_index.json --output candidate.json
prepare --manifest request.json --api-response api_full_1.json --output candidate.json
check candidate.json
```

The API-envelope input is explicit and requires `FULL_INDEX`; summary and
withheld responses cannot become candidates. The CLI accepts UTF-8 BOM files,
bounds input reads, rejects duplicate keys/non-finite JSON and redacts errors.
`prepare` writes one **new local file**, never a database record or an existing
output. `storage_writes=0` describes database/scientific storage; its successful
prepare result separately states `local_candidate_written=true`. No Polar or
environmental calls, token access or database-engine initialization occur.

## Capture and idempotency — E/2 implementation requirements

The persistence service will accept a strict manifest and a server-selected
owner, not an uploaded index/candidate or caller proof flags. For every capture:

1. Resolve the existing configured owner using D's current local demo mode.
2. Run the actual C assembler against owner-bound selected database snapshots,
   normalized evidence/lineage, current Polar routes/samples and pinned HR proof
   state. Require all members to pass; chronology limitations may remain.
3. Build this payload from that result. Recheck owned member-row relationships
   inside the storage transaction before insertion; provider checks remain
   sequential per member, not one atomic instant across Polar and the database.
4. Atomically store the immutable record and its complete member links. Enforce
   unique `(owner_id, record_schema_version, record_hash)` and unique session
   membership/canonical position per record. Member links must bind the actual
   owned workout, replay snapshot and evidence rows; no client-selected owner.
5. On a duplicate, verify the existing payload and complete links and return
   `ALREADY_PRESENT` with the original record UUID. A new insert returns
   `CREATED`. Both require exact readback; an inconsistent existing record is
   withheld, not repaired or replaced. Race/conflict and partial-write controls
   belong in the persistence tests.

A failed current check cannot fall back to an older stored index, insert a
partial prefix or refresh pins automatically. An explicitly changed, valid
request/result creates a different immutable record. `manifest_id` is a label,
not a unique mutable slot or active-version selector. There is no automatic
superseding, renaming, replacement or migration of an old record.

The member-link design must prevent silent retargeting or orphaned membership.
E/2 must define and test deletion order/retention with existing owner and source
foreign keys, including explicit user deletion. A record is immutable while
retained; payload hashing is not tamper-proof storage against a database writer.

## Read and explicit revalidation — E/3 API requirements

Ordinary readback will verify actual record ownership, stored-row/payload hash
binding and complete stored member links. It reports an archived record, with
`current_source_evidence_verified=false`, and performs no Polar/environmental
calls. It does not imply that current normalized evidence or provider data still
matches the historical result. Missing and foreign records are indistinguishable.

Explicit revalidation will run the actual assembler on the **stored original
manifest** and compare its resulting full index to the archived commitment.
It may report fresh current-source proof only after that real check succeeds.
Changed source/proof/pins, removed scope, corruption and dependency/provider
failures remain bounded diagnostics; historical records are never overwritten.
Revalidation itself does not create records or persist split assignments.

## Requested split versus stored dataset assignment

Archiving `request_manifest.split_manifest` preserves a request. The nested
index's `split_assignment_persisted=false` must remain unchanged after capture;
its hash cannot be rewritten merely because its container was stored.
Future persistence receipts may say `split_request_archived=true`, but must
keep `dataset_split_assignment_persisted=false`. Membership stays whole-session.
This contract does not define or authorize a global dataset split registry.

## Preserved scientific boundaries

Source truth, payload integrity, chronology, requested split and model readiness
remain separate. Single-session time bounds are valid historical content with
relative order and evaluation-split flags false. Multi-session non-overlap does
not establish independence or a washout period. All current training/numeric,
causal and pre-exercise permissions stay false. There is no feature fitting,
missing-value imputation, sensor-quality promotion, fatigue label or constant
HR shift. The 1,663-ms export-clock origin is not physiological lag.

## Release acceptance

E/1 tests bind real assembler outputs produced on SQLite/current-source fixtures
and test changed requests/pins/splits, malformed/withheld/summary inputs, strict
types, temporal audit inconsistency, authority, tampering and deterministic local
readback. Fresh subprocess tests with an invalid database URL establish the
offline CLI path. Installed-package and staged-new-file checks are required.
The user's control uses the saved actual D request and full API response; it is
a local commitment check and performs no new live-source verification.
