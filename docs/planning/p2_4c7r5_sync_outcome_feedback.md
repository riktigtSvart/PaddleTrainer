# P2.4C7R5 — distinguish preserved plans from sync failures

R3 records a skipped protected/manual plan as a partial run, even when every
requested import completes and the plan is deliberately preserved. The old
control displayed this as a connection warning and showed no successful sync
timestamp. R5 refines the presentation of this specific completed outcome.

## Meaning of the displayed status

The control displays “Frissítés befejezve” with an informational preservation
note only when the full requested dataset census succeeded, the exact recorded
run error is `DATA_SYNC_PROTECTED_PLANS_SKIPPED`, the end timestamp is known,
all counts are known nonnegative integers, and every nonzero skipped count
is a targets-only `protected_plan` census matching that count. Every other
dataset must have zero skips and no error. Known pairing conflicts/ambiguity
also prevent this presentation. The reader continues to validate metadata.

Missing old reason metadata, generic skips, mixed/unknown omissions, failed or
unattempted datasets, provider/authentication/timeout failures and pairing issues
remain warnings. A preserved plan is counted as “megőrzött”, not a missing
record. Detailed reasons and counts remain accessible in the existing accordion.

Account configuration/permission warnings retain “Kapcsolat ellenőrzendő”.
Import issues with an otherwise configured connection use “Frissítés
ellenőrzendő”. Neither message can be hidden by a successful historical run.

## Clock and immutable history

The primary clock is labelled “Legutóbbi frissítés vége” and uses the latest
run's recorded `finished_at`, independently of its result. A running run says
“Folyamatban”; an unconfirmed termination says “Nem igazolható”; absent history
stays unknown. This clock never substitutes an activity date or an older
successful run. The latest stored activity remains a separate field.

The stricter historic `last_success_at` and its dataset scope remain visible in
the details as “Utolsó kihagyás nélküli frissítés”. Existing audit receipts,
hashes, raw run outcomes, status API fields and saved success timestamps are
unchanged. No history is rewritten, nor is a new timestamp fabricated.

This frontend-only patch operates on already recorded status data. It needs a
page refresh, not a new provider sync. The protected-plan import policy and
calendar pairing/display remain unchanged. There are no new dependencies,
database migrations or backend changes.

## Verification

The gate runs all frontend tests, Next route type generation, full TypeScript,
ESLint on changed frontend source/test files and the existing production build.
Regression cases cover strict positive recognition, mixed and unknown omissions,
incomplete census/counts, conflicts, service errors, account-state precedence,
timestamp semantics and the unchanged hash/outcome of verified receipts.
Actual React DOM checks cover the header, badge, panel details and comparison
with real failure/unknown-history cases using synthetic local responses.
