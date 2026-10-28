# P2.4C10R2 — known nonzero distance at observed-clock origin

The supplied July 25 projection starts its cumulative DISTANCE series at 0.5 m.
The old frontend required the first sample to equal zero, even though it already
defines chart 0:00 as the first observed sample. It consequently withheld the
first distance-goal end and never reached manual-transition candidate generation.

The nominal distance projection now applies one consistent rule at every known
phase start: target = observed counter at that start + prescribed phase distance.
A known positive initial value is an observed reference, not a missing sample.
No counter is overwritten, rebased in storage or extrapolated backwards. This is
consistent with the relative goal arithmetic in the existing research phase
reconciliation module, while retaining the chart's first-recorded-crossing rule.

`DISTANCE_INITIAL_OFFSET` makes the source basis visible in the boundary controls.
The UI states the actual first counter value and labels the alignment as computed.
It does not establish when the provider's actual first phase started, recover an
unobserved prefix, or prove a native phase transition. Observed window distance
remains endpoint difference, while the full session summary and native first
counter value remain unchanged. A constant counter offset should leave the
computed windows and motion suggestions invariant.

Unknown first samples, fractional start clocks without exact source samples,
counter resets, ambiguous channels, missing crossing observations, unreached
goals and numeric overflow retain their existing withholding behavior. Manual
start proposals still require explicit user review before later phase statistics
are computed. No provider request, dependency, backend route, migration or
application-level write is introduced.

Structured phase dose takes precedence over its descriptive label: the supplied
July 25 phase named `rest 2'` contains a 300000 ms duration, so its nominal rest
remains five minutes. Duration is never inferred from that name.

Regression checks cover nonzero, missing and zero start values; shift invariance;
sampling intervals; exact threshold selection; preserved waits and source data;
fractional clocks; gaps, resets and overflow. The supplied July 25 and August 14
projections are inspected privately as development examples. Their personal
identifiers and sample arrays are not packaged as fixtures or represented as an
independent detector-accuracy evaluation.
