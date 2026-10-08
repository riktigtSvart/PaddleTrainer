# V24.9: reproducible dataset assembly from saved environmental evidence

V24.8 assembles a retrospective observation package with explicit missingness,
unlabelled workload history, censored sequence boundaries, source-bound HR
evidence, and a whole-session split contract. V24.9 adds a complete saved
environment input snapshot so repeated assembly does not refetch weather,
hydrology, waterbody, or water-surface providers.

## Why a new capture is required

The earlier normalized environment tables and compact decision snapshots do not
store every field of the full trusted per-window projection. Their hashes cannot
be inverted into missing inputs. A V24.8 exported dataset is also insufficient to
recover that full projection. Existing evidence remains valid for its original
scope; it is not silently upgraded into a replay snapshot.

An explicit capture runs the existing live inspection and environment persistence
pipeline once, then stores its complete environment assembly inputs and decision
lineage. It requires a source-bound observation package. Replaying requires an
explicit snapshot UUID; there is no implicit selection of the latest record.

## Migration and storage

Alembic revision `d83b9c61f204` follows `c5e83a9d2714`. Apply the migration before
starting a backend that uses the new endpoints. It creates only
`route_environment_replay_snapshots` and its owner/session index. It does not
alter or relabel existing environment, HR-clock, or acquisition records.

Each immutable snapshot contains its owner/session/evidence binding, hashes of
the exact Polar route and sample sources, a digest of the current HR evidence,
the normalized environment persistence record, full expected-response and
trusted-environment inputs, provider/weather metadata, and all five possible
compact decision lineages. Raw Polar HR and route payloads are not duplicated.
The full inputs include derived route/workload geometry required for assembly.
Canonical JSON rejects non-finite numbers; capture size is capped at 64 MiB.
The schema version is `0.1`. An identical payload for the same evidence set is
idempotent (`CREATED`, then `ALREADY_PRESENT`) and is verified after read-back.
Different live metadata can produce a new capture even when normalized
environment measurements remain unchanged.

## API

All paths below are relative to `/api/v1/integrations/polar/sessions/{session_id}`.
They use the existing owner/Polar connection and `training_sessions:read` scope.
The existing demo-user authentication model is unchanged.

| Method and suffix | Purpose |
| --- | --- |
| `GET /response-dataset/replay-snapshots?limit=25` | List owned snapshot metadata locally; maximum page size 100, with total count and truncation indicator. |
| `POST /response-dataset/capture?route_date=YYYY-MM-DD` | Capture complete inputs using the existing environment provider selectors. Body is absent or `{}`; client evidence and authority claims are rejected. |
| `POST /response-dataset/replay?route_date=YYYY-MM-DD` | Verify an explicitly selected saved snapshot and reconstruct the dataset from its environment inputs plus current Polar sources. |

Replay body:

```json
{
  "replay_snapshot_id": "a canonical UUID returned by capture",
  "include_payload": true
}
```

The body also accepts the existing V24.8 `split_manifest` contract. A whole-session
split remains request-only; it is never saved to the snapshot. Conflicting split
assignments return 422. The default remains `UNASSIGNED`. Summary and full
responses commit to the same package for the same request.

The capture accepts the existing weather, hydrology, station, relation,
waterbody, and water-surface query selectors. Replay has no environment provider
selectors and invokes no environmental provider pipeline. It still requires
current Polar `routes` and `samples` reads to verify source identity; it is not
an offline raw-source archive.

## Verification and failure behavior

Replay verifies the owner/session binding and the snapshot checksum, then checks
the actual saved evidence-set metadata, all normalized weather and hydrology
rows, route/segment fields, child foreign keys, and compact lineage payloads and
hashes against the captured inputs. It does not substitute a stored hash for
verification of the rows. An explicitly pinned historical evidence set can be
used even after another set becomes current.

The current Polar route/sample hashes and current HR-clock/acquisition evidence
digest must equal the captured values. The unassigned baseline dataset must
reproduce its captured hash before request-only split selection is applied.
Changed raw sources, HR proofs, measurements, geometry, lineage, or incompatible
assembly behavior stop replay with 409. There is no live environment fallback
and no automatic new capture. Unknown or unowned snapshot UUIDs return 404 before
source calls; malformed requests return 422. Polar transport failures return a
generic 502 without exposing credentials or provider exception text.

Only the API path that actually verifies database rows sets
`input_provenance.database_environment_replay_verified=true`. The pure snapshot
assembly function cannot establish that claim. Replay adds the pinned snapshot
and evidence commitments under `replay_evidence` and rehashes the complete
package, so its hash differs from a V24.8 live package while remaining stable
across repeated replay requests. The dataset version stays `0.1.0`; the existing
full-payload hash/reference checker remains compatible.

`replay_evidence.environmental_provider_calls=0` and
`replay_evidence.replay_storage_writes=0` concern
the replay science/evidence path. Ordinary authentication can still refresh and
persist an expired Polar access token. Listing does not refresh a token. Replay
does not persist a dataset, split, HR proof, or new environment snapshot.

## Scientific scope retained

The package remains `OBSERVATION_PACKAGE_WITH_LIMITATIONS`, with
`training_authorized=false` and `numeric_output_authorized=false`. Replay proves
source binding, saved-input consistency, and reproducible assembly; it does not
prove sensor identity, HR acquisition quality, causal predictor availability, or
physiological validity. Missing water temperature and unavailable wind geometry
remain missing. No imputation, model fitting, fixed HR shift, or physiological
lag estimate is introduced. Unlabelled history, native recorded HR slots, the
verified export clock offset, and unknown/censored physiological boundaries are
preserved. Export-clock alignment remains distinct from delayed physiological
HR response.

## Validation

New tests cover deterministic assembly, actual database row and lineage
verification, ownership and scope, idempotent/concurrent capture, immutable
historical selection, malformed/conflicting requests, provider failures,
current-source/evidence drift, read-only science behavior, and integration with
the existing capture pipeline. Migration tests check the Alembic chain, model
constraints and PostgreSQL DDL; SQLite exercises ORM persistence and replay.
The release guide includes the real PostgreSQL migration and live Windows probe,
which must run in the user's environment before declaring that deployment
verified.
