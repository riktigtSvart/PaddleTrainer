# V24.11-D1.1 — bounded waiting and transport diagnostics

The user's first D1 inventory stopped during the route inspection of the
2026-09-01 session. A separate Windows probe returned HTTP 200 after 126.41
seconds. The original client used a 45-second socket timeout and grouped
timeouts and connection failures under one error code. The successful slow
probe supports extending this waiting allowance; it does not independently
prove the cause of every historical failure or establish data eligibility.

This fix changes the inventory CLI and adds timeout tests. It keeps the
session selection, source checks, report reconstruction, protected cohort,
write-request policy and model-authorization boundaries unchanged.

## Execution limits

The request socket timeout defaults to 180 seconds and the batch deadline to
900 seconds. `--request-timeout-seconds` accepts 1–300 seconds;
`--batch-timeout-seconds` accepts 1–1800 seconds. Invalid limits fail before
creating an output folder or contacting the API. Every socket timeout is
clipped to the remaining batch budget.

The first retry uses one session, a 180-second request timeout and a
360-second batch deadline. It creates a new output directory and keeps the
earlier partial inventory. There are no automatic retries, new capture or
science-evidence write requests, additional environmental providers, model
fits or TEST scores.

The timeout passed to urllib controls blocking socket operations. The batch
deadline is checked before a request and after a successful bounded read; it
does not cancel an already running server operation at an exact wall-clock
instant. Client timings are descriptive elapsed times, not trusted provider
clocks. The response-byte and source-size limits remain unchanged.

## Diagnostics and capture compatibility

`INVENTORY_LOCAL_API_TIMEOUT` identifies a direct or urllib-wrapped
`TimeoutError`. `INVENTORY_LOCAL_API_CONNECTION_FAILED` identifies other
transport/read failures, including interrupted response bodies. HTTP errors
retain their existing `INVENTORY_HTTP_NNN` code. Both new transport failure
codes stop the batch with a reconstructible saved checkpoint. Invalid or
incomplete response bodies are not published as successful captures.

New capture ledgers use schema `0.2` and include the configured execution
limits plus each request's effective timeout and elapsed seconds. The local
checker validates timing field types, finite nonnegative elapsed values,
allowed limits, exact request paths, response bytes and full report
reconstruction. The report's existing descriptive claim scope is unchanged.
Old schema `0.1` ledgers remain checkable without rewriting them or their
reports. Repeated local reconstruction does not repeat provider requests.

The control summary now includes `ExecutionLimits` and `RequestTimings`.
As before, a stored replay listing is not fresh replay source proof, and a
recording product is not an HR sensor declaration. Availability failures do
not imply missing GPS or HR data.

## Installation and validation

The fix package verifies the 140 committed C-baseline file contents and all
five installed D1 source files. D1 can still be untracked or already committed;
a separate D1 commit is not required to install this fix. Only the exact
original or already updated CLI is accepted. Different target contents and
unrelated tracked/staged changes are rejected before mutation.

The installer backs up the original CLI bytes, including CRLF, in the supplied
new backup directory outside the project, then replaces that one file and adds
this document and the timeout test file. It checks the diff with a temporary
Git index. The real Git index and earlier inventory exports are not modified.
Repeated installation preserves already updated files. Failed installation
restores its own known changes and retains the backup.

Tests simulate a 126.41-second read without sleeping, distinguish HTTP and
transport errors, verify remaining-budget clipping, old-capture compatibility,
invalid timing rejection and saved failed-inspection progress. The local
tests use synthetic fixtures; the user's actual API retry remains a separate
control. The original D1 document describes its initial limits; the execution
limits and capture compatibility in this document supersede those sections.
