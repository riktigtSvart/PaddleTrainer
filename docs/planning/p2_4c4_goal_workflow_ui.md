# P2.4C4 — Cycle-goal and measurement frontend

Baseline: `7c81046ec1d8231eedc2e7adb95842734ab0a095`.

This slice connects the C1–C3 workflow to the existing Next application at
`/planning-goals`. The Coach page and macrocycle/mesocycle detail pages link
to it. A period detail link carries its exact period UUID; a mesocycle opens
the protocol step. This is a source change to the existing application, not
a separate hosted site.

The backend contracts, adapters, planning runtime, models, dependency lockfile
and database schema are unchanged. The only existing frontend edits are the
two navigation links. New forms use the existing configured application owner.
This slice does not add authentication or athlete selection.

## User workflow

The page has a period selector, four workflow steps and separately selectable
saved history. History contains all owned cycles and loads 25 records at a
time, with an explicit load-more control. A failed read is reported rather
than presented as an empty list. No latest-version substitution is performed.
The saved artifacts come from C3's verified full-artifact list responses.

### Macrocycle capability allocation

Select an existing macrocycle and start a first version, or select an exact
saved version and explicitly start its next revision. Each selected capability
needs its own macrocycle role/rationale and a role/rationale for every current
direct mesocycle. The four roles are primary development, secondary development,
maintenance and permitted temporary decline. No role is selected by default.

The UI does not translate legacy weighted objectives into roles. An omitted
capability remains unassigned, not permitted to decline. The server remains
authoritative for the current hierarchy, frozen source snapshot, complete
decomposition, revision slots and immutable version chain.

### Prospective measurement protocol

Select a mesocycle, then an explicit saved macrocycle version containing that
mesocycle. An endpoint chooses a metric from the assigned capabilities and
records its primary/supporting/context role. At least one primary endpoint is
required for every assigned capability. The UI supports up to 64 endpoints.

The form requires the actual procedure key/version, origin, source, modality,
exercise/task, full procedure, equipment/processing and an ordered list of
unique comparability conditions. It supplies no scientific procedure defaults
and does not claim that a reference alone establishes standardization.
Measured/estimated VO2, absolute/relative VO2, power/RFD and distinct threshold
metrics remain separate catalog entries. Metric labels and interpretation limits
are displayed in Hungarian; unknown interpretation text remains visible.

Each endpoint has prospective, nonoverlapping baseline and follow-up windows.
The form shows all datetime fields explicitly as UTC. Converting a field to
an aware ISO timestamp does not use the browser's timezone or DST rules.
The frozen source timezone is separately shown; C1 checks the mesocycle's
calendar boundaries in that timezone and durable registration before baseline.

Primary endpoints require an explicit favourable absolute/percent change
requirement. The form explains the favourable sign and the four-role rules.
Ratio-scale eligibility for percent change is checked without converting
outcome values to JavaScript numbers. Maintenance/decline/development target
validation remains in C1. Optional measurement error and its source must
occur together. Missing error remains null, not zero. There are no default
thresholds or assumed uncertainty values.

A new protocol revision explicitly selects its parent macrocycle version and
pins the exact selected previous protocol reference. C1 still rejects conflicts
and changes in mutable period snapshots; the frontend cannot override them.

### Measurement registration

Select an exact protocol version and endpoint. The request supplies only the
observed scalar, actual execution interval, completion/result level, ordered
condition observations with evidence, optional retained body mass and overall
execution evidence. Metric, unit, procedure and evidence kind come from C3's
server-side endpoint copy and are not editable request fields.

The complete execution must fit one endpoint window, including when a server
timestamp uses a different equivalent UTC notation. Unknown/not-met conditions
and partial trial results remain explicit rather than being promoted to complete
eligible results. Missing body mass for measured relative VO2 remains subject
to C2's existing unresolved behavior.

Values are entered as text. A decimal comma is accepted and trailing decimal
zeros are normalized to the backend's canonical plain notation. No arithmetic
or rounding of outcomes is performed with JavaScript Number. The C3 Float
round-trip retention check remains authoritative; unsupported precision is
rejected rather than silently rounded.

### Goal assessment and frozen history

Select an exact protocol and an explicit nonfuture activity cutoff. The server
runs C2's existing source census and exact comparison. The UI distinguishes:

- descriptive absolute and percentage changes;
- met/not-met under the declared measurement error;
- withheld and descriptive-only statuses;
- missing, ambiguous, unresolved, incomplete and not-yet-closed windows;
- unknown error and error ranges crossing a requirement boundary.

Backend rational values and decimal displays are rendered as supplied; exact
fractions are available under details. Missing values are not rendered as zero.
All primary criteria remain conjunctive, with no cross-unit composite score.
The error range is labeled a conditional sensitivity analysis, not a confidence
interval or validation of the error model. A criterion's success is not displayed
as proof of physiological adaptation, causality or planner utility.

The cutoff concerns activity time, while the census captures currently available
mutable rows. The UI explains that identical cutoffs restore the original frozen
assessment and later cutoffs may include late records. Measurement history shows
the original immutable registration, not a claim that raw source rows are immutable.
The exact artifact reference/hash and durable persistence time remain inspectable.

## Submission and retry behavior

A single pending submission is serialized before the first POST and retained
in the current tab's sessionStorage. This retains the exact request body and
client measurement UUID across a connection failure, tab refresh and component
remount. Opening the page never automatically submits a pending request.
The user can explicitly retry the exact same body. All editing writes are
disabled while the result is uncertain; no fresh measurement UUID is silently
generated for that retry. An in-flight guard also blocks double submissions.

A valid C3 receipt must identify the supported schema/owner scope, confirm a
durable commit and retain the false authority flags before the UI displays
success. A malformed success response is treated as uncertain. A successful
receipt clears the pending request, closes the form and adds/selects that exact
saved record in history. A known rejecting 4xx offers a return to the existing
form for correction. Network/5xx uncertainty retains the exact pending request.
The server still owns idempotency and persistence; client storage is no substitute.

Session storage contains the submitted form body until resolution and is scoped
to the tab. It is not a general measurement archive, server backup or offline
database. Closing/clearing the tab's storage can lose this retry token; check
saved history before entering the same measurement as a new request. If browser
storage cannot be written, no POST is sent. Ordinary unsubmitted form drafts
are not persisted across workflow navigation.

## Same-origin HTTP boundary

The browser calls `/api/goal-workflow/[...path]`. The Next route handler forwards
only GET catalog/periods, GET collections/details and POST collections for the
four C3 resources. It cannot forward an arbitrary URL or planning operation.
Periods use the existing training-period listing endpoint. The upstream root is
`PADDLETRAINER_API_URL`, otherwise existing `NEXT_PUBLIC_API_URL`, otherwise
`http://127.0.0.1:8000`; the existing `/api/v1` prefix remains the integration path.
Set the root on the Next server, with no `/api/v1` suffix. Existing public API
configuration continues to work with the other pages.

The boundary checks the browser Origin against incoming Host and request scheme,
including when Next constructs request.url with an internal hostname. It does
not trust a forwarded-host override or pass client cookies/authorization headers
to this demo-owner service. JSON POSTs are limited by actual streamed bytes to
1 MiB before forwarding; duplicate/unsupported query fields are rejected.
Requests and responses are no-store. Fetch does not follow upstream redirects,
has a 60-second upstream timeout and exposes a stable generic error if the API
is unavailable or returns non-JSON. C3 owns semantic validation and ownership.

This is the existing demo-owner deployment model, not a multiuser authentication
boundary. C3's false planning/utility/adaptation flags remain unchanged. No
provider request or live application database access is needed for the gate.

## Verification

The portable frontend gate uses only existing project dependencies:

1. 43 Node tests for exact decimal handling, UTC/offset windows, all four explicit
   roles, complete endpoint/condition payloads, unknown error, immutable references,
   stable retry bodies, receipt validation, pagination, escaped text, withheld
   rendering, proxy allowlists/origin checks/body limits/errors.
2. Next route type generation and the full frontend TypeScript check.
3. ESLint on every changed frontend source/test file. The period page's two
   pre-existing unused-helper warnings remain; there are no new lint errors.
4. The normal production Next build, using the existing dependency lockfile.

An additional local React DOM/JSDOM integration check starts the production Next
server and calls the real C3 HTTP services/production adapters on isolated SQLite.
It creates a macrocycle plan, a prospective protocol, two measurements and a C2
assessment. A synthetic disconnect after the first measurement actually commits
is followed by remount/refresh recovery and identical retry: exactly two scalar
rows and five audit artifacts exist at completion, not a duplicate baseline.
The report displays the synthetic 10% change and conditional met criterion.
Production proxy list/detail reads return that exact assessment.

The local host cannot run Chromium, so DOM checks are not a visual browser test.
The local Node host also lacks a readable RSS system interface: local production
builds use an external test-only RSS-reporting fallback. No such shim or browser
package is shipped or added to project dependencies. The Windows gate runs the
ordinary build without the fallback. This does not establish live PostgreSQL
integration, real athlete outcomes or scientific validity.

After the Windows gate, check `/planning-goals` at desktop/mobile widths, the two
navigation links, labels/focus, long protocol text and saved result expansion.
Use an isolated development database with future test periods for any manual
write/assessment rehearsal; the installer itself does not access an application DB.
