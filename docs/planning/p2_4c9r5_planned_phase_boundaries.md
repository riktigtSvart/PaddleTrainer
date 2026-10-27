# P2.4C9R5 — Planned phase boundaries on session charts

The chart now draws vertical markers at the declared start and end of each
time-based planned phase. Every displayed metric uses the same marker positions,
independent of units, measured values, decimation and zoom. The measured traces
and stored workout linkage remain unchanged.

## Reading the plan

The owned session-analysis GET response adds the optional `plan_timeline`
projection (`session-plan-timeline-v0.1`). Existing consumers can ignore it.
The first source is the linked plan's stored blocks. Parent/child order and
repeat containers are expanded without flattening away the hierarchy.

When those blocks are empty, the projection can read the linked plan's preserved
native Polar target. It requires `source=POLAR` and an exact match between the
preserved session ID and `polar_target_id`. Only explicit `DURATION` goals supply
time. Native durations retain their millisecond precision, and an explicitly
prescribed recovery after the final repetition is retained. Separate target
exercises retain separate clocks; they are never joined or automatically matched
to a multisport recording.

An unknown, distance-based or manually ended phase prevents precise placement of
later boundaries. Its duration remains unknown, rather than becoming zero.
Malformed order, hierarchy or repeat counts produce an unavailable projection;
the workout title and observed intensity peaks never invent phase timings.
Expansion is bounded by source, depth and expanded-phase limits. Ownership checks
are inherited from session analysis; there is no provider request or database write.

The projection contains a deterministic SHA-256 fingerprint of the source clock.
This identifies the version of a local chart reference, not a planning-authority
artifact. Stored raw target data and the `plan.blocks` response remain unchanged.

## Chart controls

`Szakaszhatárok` offers a visibility toggle and a collapsible table of exact
planned starts, ends and durations. `Mutasd` zooms every chart to a selected phase.
All visible boundaries retain their lines; crowded timestamp labels are reduced
without discarding boundaries. Hovering a line identifies its time and phases.

The plan clock starts at the selected recording exercise's sample-time zero.
A marker describes the intended transition; it does not assert that the athlete
changed phase at that exact time. The existing warning about sample clocks,
recording pauses and elapsed wall time remains applicable.

The initial view retains the actual sample extent. If the declared plan extends
beyond it, `Mutasd a terv végéig` explicitly extends the axis; the sample duration
and trace are not extended or interpolated. Unknown or zero-length phases cannot
be used as a zoom interval.

## Missing structure and manual references

The supplied screenshot shows zero stored plan blocks for the 4×12′ workout.
That title does not specify the first work start or intervening recoveries.
The preserved native target may recover a clock, but its availability on the
user's machine has not been demonstrated by the screenshot.

If no exact stored clock is available, `Kézi tervjelölés megadása` accepts the
user's known first work start, work duration, intervening recovery and repeat
count. `4 × 12 perc kitöltése` fills only the known work duration and count;
start and recovery remain explicitly required, including an explicit `0:00`.
There are N work phases and N−1 intervening recoveries. No final recovery or
cooldown is invented. Other repeat counts and work durations are also supported.

The applied overlay is labeled `Kézzel megadott tervjelölés` and uses dotted
markers. It does not edit the plan or measured data. Browser-tab session storage
is scoped by athlete, session, recording exercise and plan fingerprint. Changing
the plan version does not reuse the old reference. Denied storage still permits
a temporary in-memory reference and gives a clear notice.

## Validation and deployment

The targeted combined backend gate passes 326 cases, including owned read-only
projection, repeat expansion, exact native-source identity, absent timings,
malformed structures and unchanged raw data. All 553 frontend cases pass, along
with Next route type generation, full TypeScript, changed-source ESLint and the
production build. The frontend fixture comes from the actual owned FastAPI read.

Thirteen combined DOM cases exercise actual React controls, the closed read
proxy and isolated FastAPI/SQLite, including the zero-block case, exact manual
declarations, shared marker geometry, phase zoom, units, visibility, local reload,
source recovery, plan-fingerprint isolation and denied browser storage. These
are DOM harness checks, not a native browser or live Polar test. Actual SVG
output is also inspected with dark and light palettes using synthetic source data.

The guarded package requires the exact applied C9 through C9R4 source state above
`5dbcf3b9b038f63c5b17eafa496eb3e0ea1014ca`. It preserves existing uncommitted
work, backs up original bytes and refuses unknown or staged changes. There is
no migration or dependency change. The verified Windows-compatible C9R1 child
runner is retained. Installation does not stage, commit, push, fetch, access the
application database or contact a provider.
