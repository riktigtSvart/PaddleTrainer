# P0.11 — REANCHOR Golden Scenario

P0.11 is the first structural end-to-end acceptance slice for the accepted
2026-10-16 through 2026-10-22 reanchor microcycle.

The golden fixture is explicitly **synthetic at the evidence level**. It does
not invent or claim real training metrics. A single historical exposure with
UNKNOWN duration exists only to exercise the missing-data path that produces:

```text
OPEN_WITH_CONSTRAINTS
+ CONSERVATIVE_REANCHOR
```

The accepted schedule itself is encoded as decision-relevant availability and
microcycle intent, then assembled into a typed `MicrocyclePlan`.

Expected structure:

```text
Fri AM   easy kayak
Fri PM   preferred strength candidate
Sat AM   long easy/moderate kayak
Sun AM   short easy kayak
Sun day  family hike -> external physical-load observation
Sun PM   strength fallback only
Mon      planned rest
Tue dawn PFT + easy kayak composition
Wed PM   preferred strength candidate
Thu dawn easy kayak; easy run fallback if kayak impossible
```

Strength frequency remains conditional:

```text
minimum 1
preferred 2
maximum 2
priority candidates Fri + Wed
Sunday PM fallback only
```

Important boundaries:

- PFT + easy kayak is a session-composition pattern, not a workout family.
- The family hike is external physical load, not planned training.
- RUN fallback preserves general aerobic intent but does not claim kayak
  specificity.
- The plan protects recovery reserve, technical quality, no major progression
  and no maximal testing during reanchor.
- The base P0.7 context remains provisional. P0.11 adds an explicit
  `MicrocyclePlanningResolution` that records how all six previously unresolved
  dimensions were resolved for this acceptance scenario.

This is an acceptance harness for the planning contracts, not yet the final
general-purpose microcycle optimizer. It proves that the contracts can express
and deterministically reproduce the accepted reanchor decision without prose
or invented measurements.
