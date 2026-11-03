# P2.4C18.2 — Declared intent to reviewed capability roles

C18.1 planning inputs now include a hashed `goal_suggestions` section. The
existing owned read endpoint and its transaction, cutoff, limits and validation
are reused. No provider access or persistence occurs when a suggestion is read.

## Review workflow

1. In Felkészülés, assemble the planning inputs. Open the relevant macrocycle
   with **Céljavaslat és szerepek**.
2. In Célok és mérések, choose **Új első makrociklus-verzió**, or start a new
   version from the latest recorded macrocycle goal version.
3. Choose **Céljavaslat a felkészülés adataiból**. This explicit GET loads fresh
   inputs. It checks the owner, program, timezone, capture hash, exact current
   period census and the selected goal parent version before populating the form.
4. Review the capabilities and macrocycle roles. Choose every mesocycle role;
   the bulk button copies the chosen macro role only into empty mesocycle fields.
   Existing recorded directives, including permitted decline, remain unchanged.
5. Review the rationales and tick the review acknowledgement. Save through the
   existing immutable, versioned goal API and its existing exact-request retry
   and receipt checks. The next input capture reads the saved directives.

Loading a suggestion replaces the form's unsaved entries; use it before editing.
There is no automatic request when opening the form and no automatic save.
A different current parent version or changed period snapshot requires reloading
and starting from the current recorded version. This preserves existing CAS rules.
A later measurement protocol revision remains a separate explicit action; older
protocols are not rewritten when a new macrocycle goal version is saved.

## Rules and their limits

`declared-goal-review-v0.1` is a product vocabulary bridge, not a physiological
periodization model:

- Existing declared capability roles and rationales take precedence.
- Planned competition profiles overlapping the macrocycle supply capability
  candidates with the event key and its original declared profile basis.
  Race names, calendar distance to the race and unprofiled events do not invent
  capabilities or mesocycle roles. Cancelled/outside events are excluded.
- Explicit aerobic-fitness intent maps to VO2 and peripheral oxidative capability;
  explicit strength intent maps to maximal strength. Only an explicit `improve`
  or `maintain` direction offers a corresponding macrocycle role. These are
  editable vocabulary suggestions, not validated individual prescriptions.
- New mesocycle roles remain unassigned until review. There is no fabricated
  taper, maintenance dose, permitted decline, fitness response or training load.
- Body mass, mobility, regular activity and performance result intentions remain
  visible as unmapped here. They are retained in the program. A weight goal does
  not silently become a VO2 or strength goal. Manual capability selection remains
  available even when there are no suggested candidates.

## Workout family coverage

Capability links are read directly from the existing versioned builtin workout
family registry. The response includes its version and hash, primary/secondary
links, modality and explicit missing coverage. The form exposes them in an
optional disclosure. A link is not eligibility, selection or a prescription.
In particular, a RUN-family link is visibly a different modality and does not
become a kayak recommendation. Actual family eligibility (sport, health,
resources, environment, time), dose selection and weekly workout creation are
still future planner connections. No authorization gate is bypassed.

The additive capture remains `planning-inputs-v0.1`; the suggestions subsection
has its own schema/rules version. Existing clients can continue reading captures
without using the subsection. Source hashes cover it in new responses. Missing
suggestions fail closed only when the user explicitly requests this new feature.

## Validation

11 isolated backend tests cover owned HTTP, no writes, source precedence,
explicit directions, unmapped goals, event filtering, missing coverage and the
real goal-save → next-input loop. Regressions cover the C18.1 bridge, goal HTTP,
goal storage and cycle creation. Frontend tests cover real Python capture hash,
stale/foreign parent, period changes, matrix census and authority escalation.
React DOM checks cover explicit loading, role retention, bulk filling and the
existing proposal path. TypeScript, changed-file lint and production Next build
are included. No native Windows pixel rendering is claimed.
