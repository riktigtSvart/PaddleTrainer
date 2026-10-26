# P2.4C7R4 — combined plan/completion calendar entries

R3 records exact Polar plan associations and exposes comparisons in the detail
panel. The clock and period views still drew every stored plan and completion
as separate calendar blocks. R4 gives an already linked pair one calendar entry.

## Calendar behavior

- A completion with a stored `planned_workout_id` represents its visible plan.
  The completion appears at its actual start, with its actual end/duration.
  Its original plan is available in the same entry's tooltip and detail table.
- Calendar + check icons mean a stored plan association. A check by itself
  denotes a completion. Association does not claim that a training objective
  was achieved, nor does it change the saved plan's completion status.
- The 1-, 7-, 28- and 144-day views, and the event list, share this projection.
  A pair counts once. Several sessions referencing one plan retain all measured
  sessions and each session's timing; durations and distances are never summed
  or overwritten as part of this display change.
- A completion on a different day appears on the day it occurred. The original
  plan date/start is still available in its tooltip and the comparison table.
  Multi-day completions retain their actual clipped calendar segments.
- The R3 minimum readable activity height stays 32 CSS pixels. Availability
  windows remain proportional. Unknown and zero measurements remain distinct.
- The original feed events remain available for selection and goal annotation.
  Editing a completion's goal still targets that completion; the attached plan
  does not become an inferred replacement for a measured goal annotation.

## Association limits

Only a stored ID links records. Date, time, sport and name similarity never
merge entries. A plan without a visible linked session remains visible.
An actual session whose referenced plan is outside the current response shows
its link indicator and existing details link; R4 invents no missing plan data.
The reader validates a plan reference as either null or a UUID before use.

This is a frontend-only patch on the verified R3 output. It changes no backend,
database schema, import logic, raw provider data or stored associations. Existing
associations appear together after a page refresh. Creating missing associations
still requires R3's explicit new sync and an exact provider reference.

## Validation and review

The portable gate runs all frontend contract/render/proxy tests, installed Next
route type generation, the full TypeScript check, ESLint on changed sources and
the new test file, and the existing production build. Dependencies and lockfiles
are unchanged. Synthetic cases cover exact/no/different references, actual-time
geometry, multiple completions, moved dates, overnight sessions, missing values,
all four view scales, and escaped labels.

The installer guards the complete R3 source state before replacing seven files.
It keeps exact byte backups, rejects unrelated/staged/source changes and partial
application, and supports a read-only check and a read-only diff. It never starts
provider sync, opens the application database, stages, commits, pushes or fetches.
