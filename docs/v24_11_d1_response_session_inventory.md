# V24.11-D/1 — recorded-session inventory for cohort expansion

This slice inventories additional recorded Polar kayaking sessions before any
new cohort capture, split assignment, input materialization or model fit. The
validated V24.11-A contract and full archived cohort identify the protected
control sessions. Their recorded split is retained.

## Selection and requests

`tools/inspect_response_session_inventory.py fetch-control` uses the existing
local API. It first reads `/api/v1/sessions?include_raw=false`, counts all synced
sports, and includes every Polar kayaking session in the report. It selects at
most four additional sessions by default, ordered newest first, whose supported
stored UTC start date is strictly earlier than the earliest protected session's
UTC date. This is a selection boundary from stored metadata, not source-verified
cohort chronology or a statement of sufficient sample size. Unknown or naive
stored start times are explicitly unsupported.

Each selected session has three sequential GET requests:

1. `/api/v1/sessions/{database_uuid}?include_raw=true`, bound to the listed
   provider, session ID, sport and stored start time. The raw provider's
   declared `startTime` calendar date supplies the Polar query date; no local
   time zone is guessed.
2. `/api/v1/integrations/polar/sessions/routes/inspect?route_date={date}`,
   without environmental-provider parameters. The existing inspector reads
   routes and samples from Polar. Unique route/sample session matching and
   reconstruction of raw HR validation precede reporting availability.
3. `/api/v1/integrations/polar/sessions/{external_id}/response-dataset/replay-snapshots?limit=100`,
   to list reported stored replay pins, with any truncation retained.

The client sends only GET requests. It does not invoke synchronization,
environment capture, replay materialization, declaration persistence or cohort
capture. Normal API authentication housekeeping, including token refresh, is
outside the scientific-evidence write-request claim; this is not a proof of
zero writes to every database table. A successful four-session batch has
13 local GET request records and normally eight underlying Polar feature reads.
The saved request ledger records client requests, including requests that could
not be sent before a deadline.

## Availability and preparation actions

GPS counts describe finite coordinates and reported elapsed timestamps, not
usable motion features or model-input coverage. HR slot counts are technical
source availability. Positive and invalid value counts are withheld if any
exercise has ambiguous HR series. Captured HR diagnostics must refer to the
archived owner, current session and reconstructed raw-validation decision.

Export-clock and declaration states are reported from the captured inspector.
A recording product such as Grit X does not establish which HR sensor was used.
Sensor identity and acquisition quality remain unverified. Replay listing does
not establish current replay source binding or environmental feature coverage;
no listed snapshot is chosen automatically.

| State | Meaning |
| --- | --- |
| `NOT_INSPECTED` | No completed inspection in this batch; missing data is not inferred. |
| `REQUEST_FAILED` | Request, source shape, binding or execution limit prevented inspection. |
| `CAPTURED_WITH_LIMITATIONS` | Captured responses support the reported descriptive availability only. |

Successful inspections list the next applicable export-clock, explicit sensor
declaration, environment capture/pinned-replay and model-input history checks.
Ambiguous source matches are explicit; they do not silently select a match.
The report never labels a new session ready or eligible for training.

## Preservation and local checking

Every run requires a new output directory. Successful JSON response bytes are
written once, with SHA-256 references in a sealed capture ledger. Invalid JSON
and HTTP failures are failure records; they are not converted into zero GPS or
HR counts. Error response bodies are not printed or saved.

After the initial list, the plan and checkpoint zero are saved. Each completed
or failed selected-session attempt then saves a new immutable pair:
`capture_checkpoint_NNN.json` and `inventory_progress_NNN.json`. Earlier files
are not overwritten. A finished batch also writes `inventory_capture.json`,
`inventory_report.json`, `inventory_report_repeat.json`, `inventory_check.json`
and `inventory_control_summary.json`. The repeat is a second local
reconstruction of the same captured responses, not repeated live API reads.

The `check` subcommand verifies raw response byte hashes, exact allowed GET
paths and order, selected identities, A/archive binding, and the entire report's
reconstruction. It also works on a matching checkpoint/progress pair. This
provides local integrity and consistency, not independently established live
source or owner authorization. Rehashed authority and changed session-role
claims cannot pass this reconstruction.

`--skip-session-id` may be repeated to select a later batch from other older
sessions. Each new batch has a new directory and new captured responses. This
does not resume a previous capture or promote its report to fresh evidence.

## Limits and failure behavior

Default batch size is four; supported sizes are one through eight. The list is
limited to 1,000 sessions, each source to 100,000 GPS points or HR slots and
64 exercises. The client limits one response to 64 MiB, total responses to
256 MiB, a request to 45 seconds and the batch to 180 seconds. Plans, reports
and ledgers are limited to 4 MiB. Exceeding a limit fails explicitly rather
than silently truncating source data.

Individual HTTP 404/502 or malformed successful responses are recorded and the
batch continues. Authentication refusal, connection failure, total-response
limit or deadline stops the batch with saved progress and exit status 2.
Initial-list failure produces `initial_request_failure.json` when possible.
No archive, source file or previous output is automatically removed.

## Claim boundary and validation

The claim scope is
`LOCAL_CAPTURED_API_AVAILABILITY_AND_REPORTED_EVIDENCE_STATES_ONLY`.
New members added, scientific-evidence write requests, fitting and TEST scoring
are zero. New split assignments, current replay binding, source-evidence
verification, owner authorization, chronological cohort verification, training
authorization and numeric-output authorization remain false. No physiological
lag, fatigue target or PFT predictor is introduced.

This additive slice supplies five project files, with no new dependency,
migration or API route. Its 50 targeted tests cover bounded selection, protected
sessions, unsupported dates, source/owner binding, ambiguity, tampering,
checkpoint reconstruction, HTTP failures, redirects, deadlines and output
collisions using synthetic source payloads and a local HTTP server. Actual
Windows/API results are obtained separately through the supplied control.
