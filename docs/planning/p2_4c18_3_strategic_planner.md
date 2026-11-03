# P2.4C18.3 — First populated mesocycle strategy

The application now proposes macrocycle and mesocycle capability roles. It no
longer requires the athlete to invent every role before a strategic starter can
exist. This is a versioned, qualitative, evidence-informed product heuristic;
it is not an individualized physiological model or a workout-dose generator.

## Evidence and boundary of inference

Sources checked on 2026-10-30:

- García-Pallarés et al. (2010), DOI 10.1007/s00421-010-1484-9,
  https://pubmed.ncbi.nlm.nih.gov/20414669/ . A comparison in ten elite kayakers
  supports using explicit, sequenced training emphases as a relevant planning
  example. It does not establish universal block durations, superiority for all
  athletes, or an individual expected response. No elite training volume or
  reported percentage improvement is copied into this planner.
- García-Pallarés et al. (2009), DOI 10.1007/s00421-009-1061-2,
  https://pubmed.ncbi.nlm.nih.gov/19396614/ . A periodized combined endurance and
  strength cycle in elite kayakers supplies a practical research example of
  coordinated cardiovascular and neuromuscular preparation. Generalization to
  beginners, minors, returning or constrained athletes is limited.
- Bosquet et al. (2007), DOI 10.1249/mss.0b013e31806010e0,
  https://pubmed.ncbi.nlm.nih.gov/17762369/ . The taper meta-analysis supports
  separating pre-competition freshness from further capacity building. Its
  group-level findings motivate a readiness window, not a personal dose here.

The following are our explicit implementation choices, not research-established
constants: 42-day specific-preparation threshold, 14-day readiness threshold,
7-day transition window, at most two newly proposed primary capabilities, and
capability ranking by phase. The source abstracts do not validate these exact
choices. The full policy is returned alongside the proposal, so these defaults
can be reviewed and versioned rather than hidden in a purported learned model.

## Strategy behavior

- A planned main event anchors preparation; supporting events do not create
  independent tapers. A main event in the following macrocycle can inform the
  preceding preparation. Original event dates and cycle boundaries are retained.
- General preparation emphasizes the available foundational candidates. Specific
  preparation shifts emphasis toward event-relevant capabilities; the declared
  200 m profile has a distinct sprint/power ordering. Other profiles use a generic
  qualitative ordering with reduced certainty, not an invented discipline model.
- The readiness and transition windows propose maintenance roles. Maintenance
  means strategic intent only: no maintenance frequency, load or reduction is
  prescribed. Permitted decline is never newly inferred automatically.
- A date window is not silently converted into an exact race day or taper date.
  Closely spaced main events are evaluated together; the second race is not
  treated as a new long foundational cycle.
- Each mesocycle has an exact, gapless list of date segments. Its single role
  matrix uses its dominant phase by number of remaining days. The UI exposes
  mixed phases rather than calling an entire 28-day block a taper. These windows
  do not move period boundaries or override a later daily planner.
- Recorded roles and rationales remain authoritative input and are preserved.
  Explicit maintenance intent is not silently turned into development.
- No personal history is needed to obtain a populated theoretical starter when
  capability intent is available. Missing event profiles remain visible with
  human event names. Weight goals are retained and not relabelled as VO2 goals.
  If neither a capability goal nor an assessed event profile exists, the system
  reports insufficient goal context instead of fabricating race requirements.

## Athlete context and response observations

The current profile influences the strategic starter. Explicit beginners,
returning athletes and minors receive a conservative foundational ordering;
anaerobic/sprint/power development is not inferred for them by default. Unknown
sport history stays unknown. Sex is not used to stereotype role priorities;
age alone is not a disease or a permission to prescribe. Adaptations and
functional restrictions are surfaced for review, not interpreted by string
matching as a medical clearance. Paused or professional-review participation
produces a nonprescriptive maintenance scaffold and an explicit review note.

Recent next-morning fatigue/soreness reports and reported illness can add a
current recovery-review overlay. The 48-hour / 7-of-10 thresholds are transparent
product review rules, not diagnostic cutoffs. Immediate post-workout fatigue or
RPE is not interpreted as failed adaptation. A local signal does not rewrite an
entire mesocycle, change race dates, infer improvement, or prescribe a recovery
dose. Future and stale reports are excluded; corrected feedback selection is
inherited from C18.1.

The personal training-response model is explicitly **not applied** in this
version. Existing descriptive datasets and correlation estimates do not by
themselves authorize prescription changes. Validated individual response
policies remain a separate connection to implement. A large count of sessions
alone never flips that flag. The UI states this limitation clearly; this release
must not be presented as completed adaptive optimization.

## Contract, UI and persistence

The additive suggestions subsection is now `planning-goal-suggestions-v0.2`,
with `mesocycle-strategy-v0.1` rules and `planning-strategy-v0.1` strategy metadata.
The owned C18.1 capture and content hash cover it. The client still reads old
v0.1 vocabulary fixtures, but checks complete nonnull roles, current parent and
period census, gapless segments and false authority flags for strategic data.

A compact strategy table appears above the existing role editor after the
explicit proposal request. It includes mesocycle emphases, capability roles,
date-segment details, sources and limitations. All roles are editable. Nothing
is saved automatically. Existing goal save, explicit review, immutable revisions,
receipt validation and exact-request retries remain in place. Goal versions
flow back into subsequent daily planning-input captures. No older measurement
protocol is automatically rewritten.

No database migration, provider request, workout creation or plan mutation is
introduced. The strategic starter does not connect dose/family eligibility or
bypass the existing planning authorization boundaries.
