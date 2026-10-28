# P2.4C10R1 — reviewed motion candidates for manual phase transitions

The session analysis UI now offers candidate next-start references after a known
manual phase advance. Candidate inspection never changes phase statistics. Only
an explicit acceptance or a user-entered correction adds a timing reference.

## Sources and inference

`phase-candidates.ts` follows the low-speed/resumption hypothesis rules already
used by `planning_contracts/phase_reconciliation.py`. It is an adapter to the
chart projection, not a call to the older research reconciliation endpoint.
It supports the chart's original sampling interval and first-recorded-distance
crossings, without resampling or interpolating either source channel.

Only one original SPEED channel in km/h and one DISTANCE channel in metres may
participate. Their exercise, interval and array length must match. The interval
must be 1–5000 milliseconds. Heart rate, target adherence and displayed speed
units do not affect candidate selection. A recording-clock issue, counter reset,
ambiguous channel or unsupported grid withholds suggestions. Original source
curves and manual input remain available.

The rules look for low speed at or below 2 km/h for at least 3 seconds, followed
within 60 seconds by movement at or above 4 km/h for at least 5 seconds. Both
segments need at least two observations. Distance must increase during the
resumption, and a local missing observation cannot be bridged. Search is limited
to five minutes after the nominal preceding goal completion and eight options.
This is an uncalibrated heuristic, not a comprehensive detector of waiting:
an athlete may wait while moving, and a speed change does not identify a button
press or establish a recording pause.

If the next declared phase has an explicit automatic duration of at most 30
seconds and precedes a distance or longer-duration phase, a second interpretation
subtracts that short duration from the detected movement time. It does not infer
the duration from a title such as `start`. The UI explains the short-phase
assumption, and also offers the direct-motion interpretation. Neither is selected
automatically. The nominal ±5 second inspection interval expands to two source
intervals for a coarser grid; it is not a calibrated error bound or a guarantee
that the true phase start is inside it.

Only the first unresolved transition is considered. An accepted start continues
the existing C10 plan alignment and reveals the next unresolved transition.
The last phase does not generate another transition. Time after the final
prescribed phase remains unassigned, rather than being relabeled as waiting.

## Interaction and provenance

- `Vizsgálat a grafikonon` zooms all charts and displays a dashed inspection band.
  It creates no timing reference and no subsequent work statistics.
- A chart click selects an original-clock point independently of the hover
  cursor. The short-duration offset is retained so a following distance phase
  starts on an exact source sample. A keyboard-editable clock field is also
  available. The corrected point can be outside the initial inspection interval.
- Explicit acceptance records the rule version, candidate identifier, suggested
  point, accepted point, preceding goal, inspection interval and short duration.
  Corrected and directly accepted estimates have distinct UI labels.
- `Most nem tudom` leaves timing unresolved and clears the preview. Proposals
  can be reopened. There is no implicit zero-wait acceptance.
- Editing an earlier reference clears dependent later references and receipts.
  Resubmitting the same numeric point retains valid later references. Editing a
  candidate-derived point through the ordinary manual input removes its estimate
  receipt and makes it a plain user reference.

The existing tab-local sessionStorage key binds athlete, session, exercise,
plan hash and sample hash. The transition payload remains backwards compatible
with `phase-transitions-v0.1`; optional `motion_receipts` are validated against
the saved occurrence and selected time. Legacy C10 starts still load. Source
hash changes now also remount chart state, clearing stale previews and full
manual references. A storage failure leaves a clearly labeled temporary reference.
Closing the tab does not provide application-level persistence.

Accepted references remain user-reviewed estimates, not provider-recorded events.
The existing C10 statistics retain separate neutral waiting intervals with their
own observed distance and physiology. Waiting has no active prescribed target
and is excluded from work-zone compliance. All observed intervals remain in the
source. This change performs no writes to workouts, plans or learning evidence.

## Validation

The targeted tests cover sequential decisions, independent repeated occurrences,
several sampling intervals, fractional short durations, holes and counter resets,
duplicate channels, recording pauses, source-clock mismatch, provenance recovery,
bounded search, escaped labels, preview-only behavior and retained wait samples.
The real supplied August 14 projection is used privately as a development example.
Its curves, identifiers and raw sample values are not shipped as fixtures and do
not constitute an independent evaluation of detection accuracy.

No backend route, dependency, migration, provider request, model training or
application database write is introduced by this frontend change.
