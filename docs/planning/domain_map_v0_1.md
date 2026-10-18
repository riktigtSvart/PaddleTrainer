# PaddleTrainer Training Planning Core — Domain Map v0.1

Status: **DESIGNED / implementation started**

```text
OBSERVATION -> DOMAIN STATE -> ATHLETE PLANNING CONTEXT
-> POLICY-CONSTRAINED DECISION -> PLAN REVISION
-> EXECUTION -> OUTCOME -> LEARNING -> NEW DOMAIN STATE
```

Core boundary rules:
- measurement produces evidence, not a training decision;
- exposure is not capability;
- executed history does not prove prior planning intent;
- every decision uses an immutable decision-time context;
- later outcomes do not rewrite earlier rationale.
