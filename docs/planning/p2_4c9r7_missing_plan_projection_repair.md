# P2.4C9R7 — Restore a missing local plan-block projection

## Evidence and scope

The supplied historical-day diagnostic establishes that the August 12 completed
session and its stored target have matching native target IDs. Both the stored
native target and a fresh successful calendar-target response contain the full
phase tree, while the local `WorkoutBlock` list is empty. The tree consists of a
2600 m warmup, two repetitions of work/recovery with speed zone 2, and another
two repetitions with speed zone 5. That produces seven stored hierarchy nodes
and nine expanded planned phases.

The fresh session response requested statistics, laps and pause times and returned
an empty lap object. Therefore this evidence supports restoring the planned
projection; it does not supply the recorded phase transitions visible in Flow.
It also does not establish a general absence of phases in every Polar API response.
The distance warmup has no declared duration. Its end and later absolute phase
times remain unknown; no 18:43 timing or shortened final recovery is invented.

## Report-pinned repair

`tools/repair_polar_plan_blocks.py` accepts the original diagnostic report,
the repository and output directory, and either `--check` or `--apply`.
It selects the sole reported plan, or an explicit `--plan-id` when needed.
Only a complete, untruncated single-exercise report with an empty recorded block
list can authorize a repair. No private diagnostic report is included in source
control or this package.

The configured existing athlete is resolved independently of the report.
Ownership, plan ID, native target ID, source, calendar date, status and complete
phase tree must match the live stored source. Missing or altered source data
stops the operation before writes. A protected planning-owned source retains
the same protection as the ordinary target importer.

`--check` previews the exact proposed block hierarchy and performs no DB write.
On PostgreSQL, its repair-read transaction is explicitly read-only. `--apply`
serializes writes in owner-then-plan order and can only insert into a currently
empty block list. It never invokes the replacing/deleting import routine.
An existing different projection is refused. An already matching projection
returns `already_repaired`, retaining persistent block IDs without another write.

All `PlannedWorkout` columns, including native raw data and timestamps, are
fingerprinted and verified unchanged after insertion. The inserted hierarchy
is reread and compared to the exact proposal. A repair receipt under
`DATA_SYNC_PLAN_PROJECTION_REPAIR` and the block inserts commit together.
Insertion, verification or receipt failure rolls the transaction back. A failed
commit acknowledgement is reported as an unknown outcome and must be checked
again; a retry recognizes an already matching projection.

The CLI saves an explicit preview/result JSON to the requested output directory.
This file identifies the source contract, proposed fields, and, after repair,
the inserted block IDs. It contains no access credentials or measured sample
series. There is no provider request, OAuth operation, session edit, timetable
change, native-plan rewrite, migration or Git operation.

## Validation

The combined gate passes 401 backend cases. The new cases exercise the actual
repositories and the CLI against isolated SQLite, including the seven-node /
nine-phase structure, unchanged native plan and measured sessions, ownership,
source drift, existing blocks, planning protection, rollback, competing data,
report truncation, archived receipt and idempotent retries. The prior C9 through
C9R6, source-reconciliation, calendar and synchronization regressions also run.
No frontend files or dependencies change.

The guarded package requires the exact applied C9 through C9R6 state above
`5dbcf3b9b038f63c5b17eafa496eb3e0ea1014ca`. Applying the code and running its
isolated test gate do not access the application database. Only the separately
invoked repair CLI accesses the configured database; `--apply` performs the
explicit bounded repair. Native Windows and the user's actual DB operation
remain to be verified by their run.
