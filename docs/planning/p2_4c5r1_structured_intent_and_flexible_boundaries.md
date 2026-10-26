# P2.4C5R1 — structured intent, usable review and provisional mesocycle dates

This revision applies on top of the exact already-applied, uncommitted C5 payload.
The Git baseline remains `3ca1165cc9d21b6b83a3b1e95090261d49524173`.
Existing unrelated periods and immutable C1–C5 records are preserved.
No migration, dependency change or application database access is part of installation.

## Reported failure and review flow

The supplied screenshot reports `CYCLE_DATE_ORDER` during preview. It does not
show the actual date fields, so it cannot identify which interval was reversed.
C5 allowed dates on either side of a shared mesocycle boundary to be edited
independently; changing one could produce invalid neighbouring windows. A global
409 message did not identify the offending interval or explain why saving was
unavailable.

The revised wizard:

- displays the selected entry mode and all four named steps;
- checks the initial horizon and goals before leaving step one;
- checks event dates and structured data before generating cycles;
- identifies the event/period, dates and input when local date validation fails;
- preserves entered state on validation failure;
- moves the neighbour's start when a draft shared end is changed, and vice versa;
- offers **Tovább az áttekintéshez és mentéshez** at step three;
- shows the server-checked proposal and explicit final creation button at step four.

The backend's calendar invariants remain required. Invalid intervals are explained,
not silently reordered or accepted. Native required/date validation and backend
validation remain in addition to client feedback. Unsaved wizard drafts are still
held in component state; refreshing the tab before a write is prepared discards
that unsaved draft. Pending writes retain exact bodies in session storage.

## Two-number body-mass goal

Selecting weight loss or maintenance displays only current and target body mass,
both explicitly labelled kg. The frontend accepts comma or period decimals;
normalization preserves the digits as positive decimal strings with at most
three decimal places. No binary float is stored as the declared value.

`ProgramGoal.body_mass` contains `current_kg` and `target_kg`. The compatibility
`target_description` is generated from these two values before preview/freezing;
the user does not enter a separate prose weight target. Weight loss requires a
lower target than the declared current mass. Maintenance does not infer an
allowable variation or a clinical target.

This is self-reported goal context at registration, not a new physiological
measurement, a change to the user's measurement history or a nutrition plan.
No calorie target, rate of loss, deadline safety inference or meal plan is
calculated. A later nutrition module can consume these separate numeric fields
and their immutable registration time without parsing prose. Recreation
continuation retains the target but requires current mass to be entered again.

## Competition requirements

`CompetitionInput.profile` records:

- discipline/event description and event type;
- distance as an exact decimal string plus m/km, or explicit unknown/inapplicable;
- expected duration in minutes when known;
- course/environment notes;
- declared capability keys and the basis of that profile.

Unknown distance is null, never zero. Unassessed requirements remain visibly
unassessed, never a claim that no capability is needed. The fields are preserved
in registrations, event refinements, previews, pending retries and summaries.
Changing event requirements resets a prior suggested profile for review.

An optional qualitative suggestion supports explicitly described canoe/kayak
sprint events at 200, 500 and 1000 m (including equivalent km inputs). It is an
application interpretation of the ICF Canoe Sprint Coaching Manual, including
chapter 26; the implementation mapping is versioned `icf_sprint_v0_1`:

<https://www.canoeicf.com/sites/default/files/icf_canoe_sprint_coaching_manual_2-3.pdf>

The mapping retains technique, fatigue-resistant technique, strength, power,
start speed, high-intensity profile and aerobic capacity in its candidate set;
the 500/1000 m set also includes peripheral oxidative capacity, muscular endurance
and pacing. These are qualitative candidate requirements, not tested individual
weaknesses, numerical contributions, development priorities or training doses.
Other sports, unsupported distances and explicitly different paddling disciplines
retain unassessed/manual requirements. No sprint profile is extrapolated to them.

The existing 13-capability vocabulary is reused. Users can edit the candidate
set, which changes its provenance to `coach_declared`. Macro/mesocycle goal links
carry the owned program reference. The C1 goal page loads the relevant declared
race demands and offers an explicit button to select their candidate capabilities.
Roles and rationale in every mesocycle still require explicit input; omission
continues to mean unassigned rather than permitted decline.

## Provisional plans and explicit boundary review

New programs capture `planning_basis` version `cycle-planning-basis-v0.1`:
`mesocycle_dates = provisional` and an editable initial block length. The initial
28 days remains a UI suggestion. Arbitrary supported calendar lengths and local
boundary edits are allowed; resource bounds (64 mesocycles per macrocycle, 256
periods per registration) are product limits rather than biological cycle rules.
Main/supporting races are visible beside overlapping draft mesocycles.

A saved program offers **Mezociklushatár felülvizsgálata**. This is a human-reviewed
calendar operation, not an automated fatigue diagnosis or training optimizer:

1. Select two adjoining mesocycles under the same macrocycle.
2. Enter a changed common end, reason, observations about fatigue/fitness/progress
   and rationale for reviewing the following cycle.
3. Review the resulting two windows and explicitly approve the change.
4. Commit both period dates and an immutable boundary record in one transaction.

Shortening and extension keep both periods nonempty and the pair's outer dates
unchanged. Macro/season horizons and all exact or approximate competition dates
remain pinned. A completed boundary, or a new boundary before the owner's local
day at creation, cannot be rewritten through this operation. The owner timezone
and decision day are frozen in the record for deterministic later replay.

The previous source snapshot and latest competition revision must match. The
application locks managed period rows, verifies their ownership, hierarchy,
titles/dates and original registration identity, and rejects unrecorded source
drift. Events use the same period-row lock when appending a refinement so a new
boundary review cannot silently adopt a different competition head. Each program
has 64 sequential, deterministic boundary slots; conflicting retries are rejected.

The two mesocycle rows are flushed, independently read back, and saved with the
boundary audit before commit is acknowledged. Existing workouts and nested
periods must still fit their assigned periods; otherwise the operation rejects
and requires the affected plan to be reviewed first. It does not move workouts,
change their doses, reassign actual activities, create workouts or authorize an
existing planner decision. Those existing responsibilities remain separate.

Each saved change explicitly records required reviews of training load,
mesocycle capability roles and measurement windows. This list records the review
requirement; it does not implement a task-completion tracker. The UI shows both
the original registered schedule and the latest approved boundary schedule.
A boundary is a planning date, not an actual execution or physiological phase-end
measurement.

Existing prospective goal protocols and measurements retain their original
windows and source hashes. They are not rewritten to match a later boundary.
The linked goal workflow highlights the need to review roles/windows against
current period data; subsequent protocols must still satisfy C1 prospectivity.
No past outcome is retroactively reclassified as preregistered success.

Automatic estimation of fatigue/fitness, deciding when a mesocycle should end,
and optimizing subsequent training load for one or more race peaks are not
implemented by this calendar operation. The preserved intent, event demands,
observations and version chain are inputs for that later planning workflow.

## API and compatibility

Existing cycle URLs remain under `/api/v1/planning/cycles`. New endpoint:

| Method | Path | Result |
| --- | --- | --- |
| POST | `/boundary-revisions` | 201 new committed revision; 200 exact retry |
| GET | `/programs/{identity}` | Original program, event revisions and boundary revisions |

The closed Next proxy adds only this exact POST route. Existing same-origin,
actual streamed byte, JSON, no-store and no-credential-forwarding rules apply.

New structured records use `cycle-program-registration-v0.2` or
`cycle-competition-revision-v0.2`, with `cycle-creation-rules-v0.2`.
Legacy v0.1 requests/receipts, including pending writes, are still supported.
Optional extension fields absent in v0.1 are not inserted into its frozen shape.
There is no prose parsing, backfill or automatic conversion of old goals/events.

Boundary records use audit kind `cycle_mesocycle_boundary_revision` and schema
`cycle-mesocycle-boundary-revision-v0.1`. Kind storage is already textual, so the
existing `a2c31f5d9b70` database head suffices.

Successful receipts require matching schema, full request, SHA-256 content and
committed/authority flags. Network loss after commit keeps the exact pending body;
retry restores its original immutable receipt and never repairs later live edits.
Pending request storage remains `paddletrainer.cycle-creation.pending.v1` and now
also supports operation `boundary-revisions`. Opening the page does not auto-submit.

## Verification

Portable gate: 572 backend tests (36 new), 93 frontend tests (22 new), Next route
type generation, full TypeScript, ESLint on every changed frontend file, and
normal Turbopack production build. Python source/test lint uses Ruff.
Storage/API tests use isolated SQLite with production adapters; they do not prove
PostgreSQL row-lock concurrency or access application/provider data. Local React
DOM integration uses a production Next proxy and real API routers over disposable
SQLite, including the reported two-race/weight flow and interrupted boundary save.
It is not a visual browser test.
