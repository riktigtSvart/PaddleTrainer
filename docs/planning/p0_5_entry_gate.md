# P0.5 — Current Training State & Entry Gate runtime v0.1

P0.5 is the first planning-core component that turns descriptive current state
into an operational gate. It deliberately remains separate from actual workout
selection.

## Global gate

```text
OPEN
OPEN_WITH_CONSTRAINTS
HOLD
BLOCKED
REVIEW_REQUIRED
```

## Entry mode

```text
NORMAL_START
CONSERVATIVE_REANCHOR
RECOVERY_FIRST
RETURN_FROM_INTERRUPTION
CONSTRAINT_LIMITED
DATA_LIMITED
```

## Stimulus gate

```text
BUILD_ALLOWED
HOLD_ONLY
CONSOLIDATE
REDUCE_REQUIRED
SUSPEND
UNKNOWN
```

`BUILD_ALLOWED` means permission only. It never requires progression.

## No hidden freshness constant

The resolver receives a versioned `EntryGatePolicy` containing
`recent_exposure_max_age_s_for_normal_start`. The domain engine contains no
universal 7/14/28-day freshness rule.

## Important safety/uncertainty semantics

- stale training evidence does not become a fatigue diagnosis;
- missing/unknown evidence does not automatically become REDUCE_REQUIRED;
- professional review is preserved as REVIEW_REQUIRED, not silently rewritten
  as BLOCKED;
- explicit upstream BLOCKED status is respected;
- recovery-first and no-availability-window produce HOLD for different reasons;
- RETURN_FROM_INTERRUPTION is distinct from new/data-limited start;
- stimulus-specific authorization remains separate from the global gate.

## Stimulus signal conflicts

The resolver does not average conflicting stimulus signals. Restrictive signals
have precedence over permissive ones. An unresolved UNKNOWN signal prevents an
otherwise isolated BUILD_ALLOWED signal from being promoted to permission.
This preserves uncertainty without inventing REDUCE_REQUIRED.

The next slice is P0.6: `WorkoutFamilyPrescription v0.1` runtime contracts.
