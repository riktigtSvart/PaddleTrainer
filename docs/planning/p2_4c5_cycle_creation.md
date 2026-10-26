# P2.4C5 — Four entry modes for creating training cycles

Baseline: `3ca1165cc9d21b6b83a3b1e95090261d49524173`.

The `/planning-cycles` page creates the calendar structure needed by the existing
cycle-goal workflow. Coach and `/planning-goals` link to it, including an explicit
empty state when no macrocycle exists. All four entry modes create at least one
real `TrainingPeriod` macrocycle and its direct mesocycles. Existing standalone
mesocycles are preserved without reparenting.

## Entry modes and local calendar dates

The default start is the athlete's local current date, obtained from the existing
`User.timezone`. Date fields are local calendar dates; browser timezone and DST do
not change them. Changing an untouched default start moves the seasonal or
recreational default end. An explicitly edited end remains explicit. Actual
creation time and DB insertion time are separately retained for historical starts.

| Mode | Structure | Initial default |
| --- | --- | --- |
| Olympic | Olympic cycle, consecutive seasons, macrocycles, mesocycles | Sport-based suggestion of the next known summer/winter edition; explicit edition selection |
| Season | One season, one or more macrocycles, mesocycles | One calendar year from the chosen start |
| Race | One macrocycle and mesocycles | Explicit target-race date; no invented date |
| Recreation | Open-ended program intent, finite macrocycle and mesocycles | 12-week first macrocycle; an explicit continuation creates its next block |

The versioned Olympic calendar uses IOC dates checked on 2026-10-22: LA 2028
(2028-07-14–2028-07-30), Alpes 2030 (2030-02-01–2030-02-17), Brisbane 2032
(2032-07-23–2032-08-08), and Utah 2034 (2034-02-10–2034-02-26). Later dates are
not extrapolated. Each Olympic registration retains the exact source/version;
retry and history never replace it with a newer calendar.

Source: <https://www.olympics.com/ioc/faq/sports-programme-and-results/where-will-the-next-olympic-games-be-held>.

The first Olympic season requires a planned main competition, with an exact day
or approximate interval. Later seasons may initially omit races. Seasons are
initially anniversary-based, with an optional shorter final season; boundaries
can be edited before registration. The initial proposal contains one macrocycle
per season and 28-day mesocycles, retaining a shorter final block. These are
editable calendar suggestions, not scientific prescriptions. Seasonal macrocycles
can be split; all block names/dates can be edited. Server validation requires
correct parents, unique keys, containment and full coverage without sibling gaps
or overlaps before any row is written.

## Versioned policy and resource bounds

`cycle-creation-rules-v0.1` accepts an inclusive race preparation span of at least
28 calendar days, ending before the first calendar anniversary of its start.
This is the agreed onboarding policy, not a universal physiological minimum or
a finding that a particular performance target is feasible. Leap years use real
calendar anniversaries. A close event can be retained in an existing program's
calendar. A distant aspiration can be kept in the goal description while a nearer
milestone is selected for the current preparation.

Resource bounds are distinct from adaptation claims: 256 created periods,
24 macrocycles, eight seasons, 64 mesocycles per macrocycle, 64 competitions,
eight goal intents, 64 competition revisions, and 1 MiB actual request bytes.
An Olympic horizon is at most 1461 days, a season 550 days, and a recreational
macrocycle 366 days. ISO date years are 1900–2100. Changing the product policy
requires a supported new rule version; old registrations keep their meaning.

## Goal intent and C1–C4 integration

The first step records explicit textual intent for performance, aerobic fitness,
strength, regular activity, weight loss, weight maintenance, well-being and/or
mobility. At least one goal is required. No numerical weight-loss, VO2, error or
training-dose target is invented. Weight loss and maintenance are separate keys;
habit frequency and well-being remain distinct from measured capability change.

These are program intents, not automatic C1 capability roles or C2 measurement
criteria. After creation, exact UUID links open the existing macrocycle allocation
and mesocycle protocol forms. Every selected capability still needs an explicit
role/rationale in every direct mesocycle. Prospective registration and measurement
comparability/error rules remain owned by C1–C3. C5 creates calendar periods and
an audit receipt, without creating workouts or authorizing planner actions.
It does not add a weight-management assessment engine or treat an activity count
as proof of physiological adaptation.

## Preview, atomic creation and retries

Four wizard steps cover horizon/goals, competitions, editable structure and
server-validated preview. The read-only preview checks the full explicit graph
and binds its normalized proposal hash, including parent-reference hashes.
Confirmation sends exactly the reviewed proposal.

Period UUIDs are deterministic in the owner's scope, program UUID and node key.
The service owns a fresh session, inserts periods parent-first and the immutable
audit artifact, verifies read-back, and commits once. Failures roll back the full
graph. The existing audit adapter assigns durable insertion time in the database.
A committed receipt is returned only after successful transaction closure.

Before POST, the browser retains the exact serialized operation/body in the tab's
sessionStorage, including the original program UUID and parent reference. Page
open never automatically submits. While an outcome is uncertain, new editing
writes are locked and explicit retry sends identical bytes. Success requires a
supported committed receipt, matching full proposal/content hash, durable identity
and false authority flags. Known rejecting 4xx responses allow return to editing.
Browser storage failure prevents transport.

Server retry restores the original immutable receipt. It does not recapture
current timezone/calendar defaults, repair missing mutable periods or overwrite
later edits. The receipt is the registered original structure; C1 source capture
still describes current period state. Closing/clearing the tab can lose a pending
token; check saved history before starting a replacement. Unsubmitted drafts are
not persisted across a refresh.

## Event refinement and recreation continuation

Each competition retains a stable key, title, exact day or full approximate
window, priority and planned/cancelled status. Exact precision requires equal
start/end, a window distinct bounds. The whole interval must fit the program
and one season where seasons exist.

The selected program exposes refinement. An immutable new version pins the
original program reference and exact previous revision hash. Old event keys
cannot disappear: cancellation is explicit and replacements can be appended.
Concurrent different attempts at one revision conflict; exact retry restores
the same version. The UI shows the current declared calendar and original/older
versions, including rationale.

Refinement preserves period boundaries and registered measurement windows. It
does not silently reschedule a plan. An event postponed outside the current
horizon requires a separately reviewed new preparation. This slice implements
creation and event refinement, not a general editor for registered structures.

A recreation continuation has a new program UUID and finite macrocycle, shares
the original program family, and pins its exact predecessor. The UI carries over
editable goals. The start follows the predecessor's end, defaulting to the later
of its next calendar day and local today. One deterministic continuation slot
per predecessor prevents parallel copies of the same next step. Overall intent
remains open ended.

## HTTP and persistence

The existing configured demo owner remains the identity scope. Reads never
create a user. This slice adds neither authentication nor athlete selection.
Missing/foreign references return 404, rejected structures/conflicts 409, strict
input validation 422, oversized bodies 413 and storage failures 503. All responses
are no-store; validation responses do not echo user input.

| Method | Path under `/api/v1/planning/cycles` | Operation |
| --- | --- | --- |
| GET | `/catalog` | Local date/timezone, rules, Olympic dates and intent labels |
| POST | `/preview` | Read-only complete-structure validation |
| POST | `/programs` | Atomic creation; 201 new, 200 exact retry |
| GET | `/programs?limit=25&offset=0` | Owned verified registrations, explicit pagination |
| GET | `/programs/{artifact_id}` | Exact registration and retained competition revisions |
| POST | `/competition-revisions` | Append refinement; 201 new, 200 exact retry |

The existing proxy adds only these closed operations under
`/api/goal-workflow/cycles`, retaining Origin/Host checks, actual streamed-byte
limits, strict queries, no credential forwarding, no redirects and timeout.
It exposes no generic training-period mutation endpoint.

The generic audit table stores two new textual kinds, so no new migration is
needed. Existing schema must already be at `a2c31f5d9b70`, as confirmed for this
installation. No dependency is added. The installer/gate never accesses the
application database.

## Verification and manual check

The new backend tests join the existing A–C3 regression gate. They cover all four
structures, C1 integration, ownership, strict inputs, policy boundaries, partial
flush rollback, exact retry, frozen calendar/timezone, nonrepair of later edits,
event history and continuation conflicts. Storage tests use production adapters
over isolated SQLite with an async bridge, not a live PostgreSQL instance.

Frontend tests cover local/leap calendar arithmetic, complete structures,
explicit splits, canonical UTF-8 hashing, retained request bytes, receipts,
escaped rendering and closed proxy paths/methods. Existing C4 tests remain,
followed by Next type generation, full TypeScript, targeted ESLint and production
Next build.

A separate local React DOM/JSDOM run uses the production Next server and real
C5/C3 HTTP routers/adapters on disposable SQLite. Nine scenarios cover empty
onboarding, a lost post-commit response/remount/retry, recreation continuation,
C1 assignment, seasonal split, date refinement, winter Olympic selection and
target-race creation: 36 periods and seven audit artifacts. JSDOM does not verify
visual layout; desktop/mobile rendering still needs a real browser. Local build
uses an external workaround for this container's missing RSS system call; it is
not shipped. Windows runs the normal project build.

After installation restart API/web, open `http://localhost:3000/planning-cycles`,
create an actual reviewed future program and follow the macrocycle link to
allocate capabilities before preregistering measurements. Use a separate test
database for synthetic rehearsal.
