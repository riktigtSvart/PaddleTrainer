# P2.4C9R6 — Preserve Polar phase imports and inspect one historical workout

The supplied Flow screenshot shows recorded outcomes for the August 12 workout:
a distance-based warmup lasting 18:43, four 12-minute work periods, intervening
recoveries and a shortened final recovery. These are observed phase results,
not a constant time schedule recoverable from the title. The public v4 target
schema and the recorded lap schema are different sources. This change does not
assume that Flow's complete phase table is exposed through AccessLink.

## Proven importer defects addressed

Previously `_replace_workout_blocks` deleted the existing tree before checking
whether the incoming response contained any phases. A later empty or partial
response could therefore clear an earlier prescription. The importer also
assigned new block IDs on identical imports, treated missing repeat counts as
one, and cleared known summary values when a field was absent.

The importer now validates the entire incoming tree before normalization and
before any block deletion. Empty, malformed or incomplete phased exercise
structures cannot replace an existing phase tree or preserved native phases.
One malformed record does not prevent a separate valid record from importing.
Missing repeat counts and boolean/fractional/oversized counts are rejected;
unknown duration is not turned into zero. Explicit zero summary values remain
distinct from missing values. Missing title, description and sport metadata do
not erase known fields, and a session-level sport reference can supply an omitted
exercise-level reference.

A canonical comparison of ordered block fields and parent positions avoids
replacing IDs when the structure has not changed. A complete changed source can
still replace its projection; the old raw source is archived first. A complete
source can rebuild missing blocks on the next ordinary target import. No clock
is invented for a distance warmup and no observed phase means are fabricated.

The untouched incoming response is content-addressed and archived for both the
normal sync entry and the older importer entry. Prior native sources are also
archived before accepted updates. A target skipped because its known structure
would be lost reports `incomplete_phase_structure`; invalid structure reports
`invalid_phase_structure`. Such an incomplete import remains a truthful partial
sync result. The historical run receipt is not rewritten to claim success.
Existing approved-plan protections, owner checks and local timetable moves
remain in effect. Implicit conversion of a phased plan into an empty plan is
withheld for review even if the new payload declares a non-phased type.

## Diagnostic workflow

`tools/diagnose_polar_phases.py --repo PATH --date 2026-08-12 --output-dir PATH`
reads the existing athlete, owned sessions, plans and matching target archives.
It never creates a demo user. PostgreSQL reads start with `SET TRANSACTION READ
ONLY`; the transaction always rolls back. No import, repair, token refresh,
Git operation or source change is performed.

With `--fetch-provider`, it additionally uses the existing unexpired access token
for two date-scoped GET operations: sessions with `statistics`, `laps` and
`pause-times`, and calendar targets. A token expiring within two minutes or
missing access prevents provider requests; local evidence is still reported.
The user can renew access through the ordinary application sync and retry.

The JSON report compares exact native session/target IDs, retains native lap
timings and both native/enriched exercise views, and discovers additional
phase/lap fields without assuming their undocumented meaning. It exports sample
clock metadata, not sample arrays. Credentials, GPS coordinates and private
error bodies are excluded. Archive scanning is bounded and any limit is explicit;
an incomplete scan does not prove an archive absent.

Possible findings distinguish an unprojected stored source, available archived
structure, a fresh complete target not projected locally, an incomplete returned
target, and a target not returned for the selected day. The last finding is
limited to that particular day/response: a rescheduled target may have a
different planned calendar date, which is included in the report. Multiple
archived native snapshots remain separate evidence; none is silently promoted
to a repaired plan.

Run the diagnostic before another ordinary sync when access permits, and attach
the generated `PaddleTrainer_polar_phases_2026-08-12_*.json`. The user's live
response is necessary to establish the actual August 12 failure and to map any
returned recorded phase data into chart boundaries. This patch prevents proven
loss mechanisms; it does not claim that the historical workout is already repaired.

## Validation and deployment

Tests use the actual sync route, importer and repositories with disposable SQLite
and synthetic source transport. They cover source retention, stable IDs, valid
updates and archival, empty/malformed/multisport responses, direct replacement,
legacy imports, unknown repeats and missing-versus-zero metadata. Diagnostic
tests exercise owner isolation, native lap times, archive evidence, exact one-day
HTTP requests, denied scope, sanitized errors, read-only transaction setup,
rollback and expired access without credential renewal. The preceding C9 and
calendar/data-connection regressions plus P1.4 source reconciliation also run.

This is a backend/tool change; frontend sources and dependencies are unchanged.
The package requires the exact applied C9 through C9R5 source state above
`5dbcf3b9b038f63c5b17eafa496eb3e0ea1014ca`. The gate has no application DB or
live provider access. The verified Windows parent/child test runner is retained.
There is no migration, staging, commit, push or fetch. Native Windows and the
live August 12 source require the user's diagnostic run.
