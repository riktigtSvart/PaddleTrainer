# V24.11-D2.1 — bounded four-session assembly time

The first four-session preparation request stopped with HTTP 504,
`COHORT_EXECUTION_TIME_LIMIT`, and canonical member position 3. The client
allowed 180 seconds, but the server gave the entire sequential assembly only
120 seconds. No successful member prefix or cohort proof was published.

The execution budget is now selected from the requested member count:

| Requested members | Server assembly budget | Suggested client timeout |
| --- | --- | --- |
| 1–3 | 120 seconds | 180 seconds |
| 4–20 | 360 seconds | 420 seconds |

The three-session control retains its original committed execution-limit
metadata. The count boundary is an execution policy for the known control;
it is not a sample-size, independence, or scientific-readiness threshold.

Both the `asyncio.timeout` context and every monotonic deadline checkpoint use
the same selected budget. The selected limit is published under
`execution_limits.max_assembly_seconds`. Member, source, snapshot, dataset,
and index size bounds are unchanged. A slow awaited operation is cancelled;
the existing synchronous-stage checkpoints still enforce elapsed time.

All owner checks, exact replay pins, database-row verification, current Polar
route/sample checks, HR proof checks, complete replay integrity, and chronology
checks remain in place. There is no automatic retry, fallback snapshot,
environmental refetch, split reassignment, fitting, or scientific-record write.
The existing three-session archive and experiment remain valid unchanged.
No dependency, migration, endpoint, request field, or query option is added.

Restart the API process after applying the patch. A reload-enabled development
process can detect the change automatically, but restart it explicitly before
the live retry. Retry the exact prepared four-session request once in a new
output folder, allowing 420 seconds on the client. Preserve any non-200 JSON
response for diagnosis; it must not be counted as a verified cohort.

Seven new orchestration tests use virtual elapsed time and mocked member
verification. They cover completion beyond 120 seconds, the preserved
three-session deadline, the finite extended budget, the exact 360-second
boundary, cancellation of an awaited member, and evidence failure after a
completed prefix. Existing SQLite assembly, chronology and API tests continue
to cover the actual owner/database/source verification pipeline.

`tools/probe_response_cohort_assembly.py` makes one POST to the loopback
assembly endpoint, with a 420-second client timeout and no redirects or proxy.
It saves both successful and non-200 response bytes, checks the request pins,
split binding and complete index hash on HTTP 200, and writes a compact
`cohort_probe_summary.json`. Output directories must be new. Two further tests
cover retained HTTP 504 JSON without prefix promotion and output preservation.

The local conversation runtime runs the new orchestration tests against the
unchanged selected core definitions from the patched source. Its transport
dependencies are unavailable, so this is not the full API regression suite.
The supplied Windows control runs the new tests and the existing assembly,
chronology, and cohort API suites using the project's virtual environment.
Actual four-session completion is established only by the next live response.
