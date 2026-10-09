# V24.11-B — pinned interval inputs and row coverage

V24.11-A committed an experiment policy against a complete archived cohort.
V24.11-B consumes the **full, exact UNASSIGNED replay of every archived member**
and builds deterministic predictor arrays, recorded-HR targets, lookback
references and one audit entry for every observation. It checks actual values
and time support. It does not fit a model, estimate physiological lag, verify
sensor quality, derive PFT/fatigue targets or authorize training.

No dependency, database migration, API route or existing source file changes.
The A manifest, original cohort record, replay payloads, HR proofs and split
pins remain unchanged. New input packages are local files, not scientific
database evidence or persisted split assignments.

## Local binding and authority

`build_response_model_input_package(manifest, archive, datasets)` first applies
the A validator and the existing full-dataset integrity checker. It requires
every exact athlete/session member once, matching the archived replay package
hash, snapshot/evidence pins, counts, feature-mask counts and HR-window counts.
A failed member aborts assembly; no partial input package is returned.

`check_response_model_input_package(package, manifest, archive, datasets)` checks
the package hash, reconstructs the entire package from those pinned inputs and
compares the reconstruction hash. A valid newly calculated hash does not make
an edited value, mask, target, split, future-window reference, omitted audit row
or extra HR predictor acceptable. JSON commitment distinguishes booleans and
numeric aliases. Both checker and builder keep source/owner/training authority
false. Their claim scope is:

`LOCAL_PINNED_PAYLOAD_AND_INTERVAL_INPUT_RECONSTRUCTION_ONLY`.

The archive contains historical source and chronological split claims. The
local materializer does not renew them or prove that a file came from the
claimed owner. Cryptographic pins are local commitments, not signatures.

## Representation 0.1.0

The root contains the experiment/record/index/request hashes, canonical feature
columns, committed lookback widths, members, per-split coverage, limits and the
`input_package_hash`. Member order follows the archive's canonical identity
order, which can differ from chronological or TRAIN/VALIDATION/TEST order.

Each member has:

| Field | Meaning |
| --- | --- |
| `input_arrays` | Shared parallel arrays for every source observation: row IDs, route/exercise/order/sequence, interval bounds, selected values and masks. |
| `targets` | Eligible rows only: source row ID, input index, mean recorded HR, original HR grid reference and lookback references. |
| `row_audit` | Exactly one entry per source row, including eligibility, all applicable exclusion codes, source exclusion codes and each window's support check. |
| `sequence_metadata` | Original sequence bounds, unknown initial state, censored history/recovery and unverified physiological reset. |
| `coverage` | Source/eligible/excluded counts, selected mask counts, overlapping exclusion-reason counts and per-lookback support counts. |

Predictor columns contain the contract's sorted workload features followed by
its sorted environment features. HR and HR-derived values are absent from
predictor arrays. Targets retain the recorded sensor HR in bpm; they are not
predictions or a verified physiological reference.

AVAILABLE finite selected values are copied without scaling or fitting.
MISSING, WITHHELD and NOT_APPLICABLE remain distinct and have `null` values.
Nonfinite/non-numeric workload values, including booleans, are unavailable.
Unselected channels do not become model requirements. The original pinned
source files preserve their full raw observations, HR slots and provenance;
the new package references every observation but does not embed another full
copy of those source payloads. Keep the original files with the package.

## Time windows and eligibility

For a target interval ending at exercise elapsed time `T`, width `L` describes
`[T-L, T)`. The reference gives a half-open range of shared input row indices,
the first interval's left clipping in milliseconds and both window bounds.
The last referenced row is the target's current observed workload interval.
This is the A contract's retrospective conditioning policy. It does not prove
that these observed GPS/environment values were published in real time.

Clipping defines observation support only. It does not interpolate a physical
trajectory, invent GPS samples, resample a tensor or claim a constant physical
load within an interval. A later model/adapter must commit any further
representation and preprocessing policy explicitly.

All selected windows must have uninterrupted time support in the same member,
route, exercise and observed sequence. Every intersecting interval must have
all selected feature values AVAILABLE and finite. No history crosses a gap,
unsupported row or session boundary; no later row is referenced. Prefix mask
counts and binary interval searches avoid copying full histories for every
target. The output grows with observations × features/windows, not the number
of samples repeatedly duplicated inside each lookback.

Each target additionally requires a source preparation candidate without
source exclusions and a COMPLETE, positive-finite verified-export HR grid
window. HR aggregation is the arithmetic mean of its actual referenced slots.
The export clock offset remains technical timestamp alignment. No fixed shift
or physiological lag is applied. Missing HR prevents that row from becoming a
target but preserves its usable workload in later history windows.

Exclusion codes include `SOURCE_PREPARATION_CANDIDATE_UNAVAILABLE`,
`COMPLETE_HR_LABEL_REQUIRED`, `NO_SUPPORTED_SEQUENCE`, `LEFT_CENSORED_HISTORY`
and `SELECTED_INPUT_MASKED`. One row can have several reasons; reason counts
can exceed the number of excluded rows. Eligible plus excluded rows always
equals the complete source observation count.

An empty partition produces `MODEL_INPUT_PACKAGE_WITH_EMPTY_PARTITIONS` with
explicit split names and complete audits. This is a valid coverage diagnosis,
not permission to pad data or change the frozen experiment automatically.
Training and numeric model-output authorization remain false even when all
partitions have eligible rows.

## CLI

Run from the project root with the project's virtual-environment Python. The
tool sets its own API import path; offline commands do not load database
settings or contact providers.

```text
python tools/build_response_model_inputs.py build --manifest contract.json --archive archive.json --dataset first.json --dataset second.json --dataset third.json --output inputs.json
python tools/build_response_model_inputs.py check inputs.json --manifest contract.json --archive archive.json --dataset first.json --dataset second.json --dataset third.json
python tools/build_response_model_inputs.py control --manifest contract.json --archive archive.json --dataset first.json --dataset second.json --dataset third.json --output-dir new-folder
```

`control` produces `model_inputs.json`, `model_inputs_repeat.json`,
`model_inputs_check.json` and `model_inputs_control_summary.json`. It repeats
assembly with reversed dataset-file order, reconstructs the package and runs
negative controls with valid recomputed hashes except the intentional hash
tampering case. Target/window tampering controls report `null` if there are no
eligible targets; they are not falsely reported as performed.

`fetch-control` obtains the exact archived snapshots through the existing
loopback API replay endpoint before running the same local control:

```text
python tools/build_response_model_inputs.py fetch-control --manifest contract.json --archive archive.json --output-dir new-folder
```

It sends `include_payload=true` with each explicit archived snapshot ID and its
archived query date. It sends no split manifest, so original UNASSIGNED replay
hashes remain comparable. It does not select the latest snapshot, capture new
environment data or retry with alternate pins. Only
`http://127.0.0.1:8000/api/v1/integrations/polar` (or an explicitly selected
localhost/IPv6-loopback host/port with the same path) is accepted. Redirects and
configured HTTP proxies are disabled. Each member's exact returned bytes are
saved as `member_000_replay.json`, etc., after local pin checks.

The local materializer reports zero provider calls/database writes. A fetch
run reports its actual replay API request count separately, plus the replay
endpoint's reported zero environment-provider calls/replay storage writes.
These counters are not an audit of every server database table or OAuth token
refresh. Local `CurrentSourceEvidenceVerified` remains false; the API replay
performed its own source checks at request time. A changed live source/proof
can therefore stop retrieval with 409 instead of silently using a replacement.

Output files/directories must be new. On a later fetch failure, successfully
saved raw replay files remain for diagnosis, and no partial model-input
package is emitted. Existing archives and output folders are never removed.

## Bounds and validation

The A/archive and per-dataset size/reference bounds remain active. B adds at
most 200,000 observations, 400,000 HR slots and 256 MiB canonical package bytes
across the cohort. CLI reads allow 96 MiB per full replay file, 256 MiB of
replay file bytes in total, 3 MiB archive bytes and the A 64 KiB manifest bound.
Formatted output is also bounded to 256 MiB. Replay fetching has a 180-second
total budget and at most 60 seconds per request; completed source files remain
when it stops. No unbounded automatic retry is used.

Tests use the real prior assembler/record fixtures and separate explicitly
synthetic long arrays. They cover analytic HR means, exact half-open/clipped
history, the default 30/60/120-second widths, mask propagation and restoration,
unlabelled history, empty partitions, sequence gaps, whole-session splits,
tampered inputs, redacted errors, input preservation, output collisions,
bounded reads and loopback retrieval/redirect/failure behavior. They do not
constitute a run against Gyula's Windows API or his real archive.

The Windows control should preserve the known totals (3 members, 7,762 source
observations, 8,045 HR slots, 7,757 preparation candidates) and the A manifest
hash. Its eligible model-input count is computed from actual coverage and is
not assumed to equal the preparation-candidate count. Review those per-session
and per-split results before committing the next experimental-model slice.
