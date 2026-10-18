# P0.4 — CurrentTrainingState + LoadAnchorState v0.1

P0.4 is intentionally descriptive. It does **not** decide whether training may
progress, should be held, or should be reduced. Those decisions belong to the
EntryGate/policy layers.

## Executed training evidence

The v0.1 training-exposure evidence payload is:

```json
{
  "schema_version": "executed_training_session_evidence_v0.1",
  "session_id": "...",
  "modality_key": "KAYAK",
  "duration_status": "known | unknown | ...",
  "duration_s": 3600
}
```

`modality_key` is an open registry key. P0.4 does not convert RUN exposure into
KAYAK exposure or infer stimulus equivalence.

## Coverage is explicit

Observed records are not automatically assumed to represent all training.

`EvidenceCoverage`:

- COMPLETE
- PARTIAL
- UNKNOWN
- NOT_APPLICABLE

Therefore:

```text
no observed sessions + UNKNOWN coverage
    -> UNKNOWN current exposure

no observed sessions + COMPLETE coverage
    -> VERIFIED_ZERO_EXPOSURE
```

This distinction is essential for missing-data safety.

## LoadAnchorState

The first load anchor is deliberately modest: a duration/frequency exposure
anchor over an explicitly supplied window.

It is a **descriptive prior**, never a prescription target.

P0.4 does not infer:

- physiological training load from duration alone;
- capability from exposure;
- fatigue/readiness from volume;
- a progression target from historical or recent totals.

## No hidden freshness constants

P0.4 stores exact observation times and `age_s_at_cutoff`. It does not hard-code
a universal rule such as "14 days = stale". Freshness interpretation belongs
to a versioned EntryGate/policy in P0.5.
