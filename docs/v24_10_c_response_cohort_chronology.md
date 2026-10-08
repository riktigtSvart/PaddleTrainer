# V24.10-C — source-bound whole-session chronology

C extends the B assembler only when trusted code supplies
`verify_chronology=True`, or the local operator runs
`tools/build_response_cohort_index.py verify MANIFEST --chronology --output NEW_INDEX`.
The default B mode and its hashes remain unchanged. No endpoint, migration,
new dependency, scientific write or model fitting is added.

## Source and authority

Every selected member first passes B's actual configured-owner, database,
normalized environment/lineage, current Polar, persisted HR proof, expected pin,
full UNASSIGNED replay hash and payload-reference checks. No supplied index or
JSON verification flag replaces those checks. The two existing Polar feature
requests supply the raw temporal metadata; C adds no provider requests.

The pure temporal helpers check metadata only. Their
`source_verification_performed=False` is intentional. Only the assembler,
after verifying every selected source, issues root
`chronological_cohort_order_verified` and
`chronological_split_verified`. The chronology claim covers **declared,
source-bound Polar wall-clock metadata**, not physical clock accuracy.

References: [Polar v4](https://www.polar.com/polar-api-v4/),
schemas `trainingsessionTrainingSession` and `trainingsessionExercise`.
Polar publishes explicit startTime/stopTime, optional timezoneOffsetMinutes,
durationMillis and exercise identifiers. C's stricter acceptance rules below
are project policies, rather than a claim that every Polar payload meets them.

## Complete session bounds

Both routes and samples responses must have a positive explicit session interval
and a nonempty, matching set of all published exercises, including unrouted
ones. Every exercise requires explicit positive start/stop, must lie inside the
header interval, and must agree between feature responses in UTC, sport and
duration metadata. Match unique provider exercise IDs; when absent, use unique
UTC start/stop/sport/duration metadata. Mixed/ambiguous memberships are withheld.
Feature response order may differ; source indices remain explicit.

Accepted timestamps: calendar date, T, hours/minutes/seconds, optional 1–6
fraction digits, optional Z or ±HH:MM. Naive times require an explicit integer
offset within ±14 hours. An exercise's own offset is used first; a session offset
may resolve an otherwise naive exercise. Aware timestamps are self-contained;
an explicitly supplied offset on the same object must agree. A parent offset
does not reinterpret an aware exercise. Reject unknown -00:00, invalid calendar
values, minute overflow, fractional/boolean offsets and excess precision.
No operating-system timezone or client route_date becomes timing evidence.

durationMillis does not replace a missing stop or shorten a declared interval.
Wall-clock-minus-duration differences are retained without inferring pauses.
Reported timestamp precision/serialization uncertainty and device clock accuracy
are not verified. Provider-hidden exercises cannot be ruled out. Native HR/pause
clock semantics and physiological lag remain outside this proof.

The actual attached control has a session stop four seconds later than its
exercise stop. Its declared UTC session bounds are 2026-09-30 15:35:18–16:26:05;
the exercise stops at 16:26:01. C therefore uses the full session header.

## Chronology and split

Members remain in canonical identity order. A separate list of member indices
orders their declared intervals by UTC. All pairs are checked, not only adjacent
starts. Overlap or touching bounds withhold strict separation, even within one
requested split. No arbitrary washout interval is introduced.

One session can support only its own bounds:
`SINGLE_SESSION_TIME_BOUNDS_ONLY`, relative order=False, complete split=False.
At least two members, every supported interval, no overlaps/touches and no
detected exact reuse are required for cohort order. For a complete evaluation
split, every member must be assigned and TRAIN, VALIDATION and TEST must all be
nonempty. max(TRAIN.stop) < min(VALIDATION.start), and
max(VALIDATION.stop) < min(TEST.start). All routes, exercises, labels and
histories stay with their whole session. This stricter whole-cohort rule also
rejects same-split overlaps. The request assignment is not persisted or applied
to the base UNASSIGNED payload.

Source success can coexist with a withheld temporal audit. It retains all
verified members, counts and source commitments, reports the failed temporal
member indices, and never promotes order or evaluation. Source verification
failure still withholds the entire index; no successful prefix is emitted.
A valid source index with a withheld temporal audit returns CLI exit 0; inspect
the separate chronology/split flags. Source failure returns nonzero and creates
no index file.

## Possible duplicate sources

Check reuse across selected sessions of provider exercise IDs, anonymous exact
route/sample feature content, or exact HR series (type, interval and all values).
Fingerprint feature bodies without exercise/session IDs or absolute header
time, so renaming or shifting a copied import does not automatically hide it.
An HR fingerprint requires at least one finite positive label; identical empty
or invalid-only HR arrays are not HR-copy evidence. Route-only similarity does
not block repeated legitimate courses. Raw coordinates and labels are not
copied into the index.

Matching fingerprints flag **possible** copies, never silently delete or merge
records. Exact feature reuse, including invalid-only identical feature bodies,
may still flag a pair. Approximate copies, resampling, changed relative GPS
timestamps, different numeric serialization and unseen records are not covered.
`all_possible_duplicates_ruled_out=False` and statistical independence=False
remain explicit. Fingerprint IDs/hashes are compact references, not sensor
identity/acquisition-quality proof.

## Version, limits and hashes

Request schema and dataset version remain 0.1 and 0.1.0. C-mode index assembly
version is 0.2.0. B mode stays 0.1.0 and preserves its previous serialized output.
C adds temporal evidence and its hash, the compact audit and scoped root flags;
the complete C index hash covers all its fields except its own hash.
Local index integrity checks prove hash/count consistency only, never live
source authority. C's member temporal hash includes the actual binding scope.

B's limits remain: 20 members, 120 seconds, 16 MiB selected current session,
64 MiB snapshot/dataset, 100000 observations, 200000 HR slots, 256 dataset routes
per member, 1 MiB index. C requires at most 256 published exercises per feature
response. Exceeding that temporal bound withholds chronology without truncating
the published set. An overall time/size failure withholds the entire source
index. Duplicate diagnostics are bounded by 190 member pairs, using hash-to-set
lookups rather than exercise cross-products.

All preprocessing fitted later must use TRAIN only. No preprocessing is fitted
now; unknown initial states, censored histories, missing environment features,
excluded observations and verified export clock origin remain unchanged.
Nonoverlap does not establish physiological/statistical independence or unseen
athlete generalization. A chronological split does not authorize training,
numeric estimates, causal prediction or pre-exercise prediction.

## Validation and live control

Tests cover strict UTC offsets/unknown boundaries, full unrouted exercise sets,
source disagreement, touching/overlapping and nested intervals, incomplete and
reversed partitions, copied identifiers/features/labels, pure-helper authority
limits and execution bounds. Three-session SQLite fixtures use actual normalized
science rows, saved lineage and HR/snapshot services, with synthetic Polar
responses. They establish source-bound order and a complete chronological
requested split without scientific writes. Existing B tests remain unchanged.

The full-size probe uses the attached real 3038 HR slots and matching TCX, with
explicitly synthetic 2913 route/workload/environment observations. It is not a
live GPS/environment or PostgreSQL/multiple-actual-session validation.

The Windows delivery README has self-contained inline blocks for installation,
targeted/full tests, the existing single actual B request, deterministic C
indexes, original replay/hash/HR commitments, wrong-pin refusal, forbidden
authority refusal and exact-file git commit/push. There is no PowerShell script
execution-policy change. No local Windows/PostgreSQL/live multi-session run is
claimed. Multiple actual prepared session snapshots are still needed for a live
positive TRAIN–VALIDATION–TEST control.
