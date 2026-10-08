# V24.8: retrospective response dataset contract

V24.8 assembles source-bound observations for later response-model work. It keeps observed external workload and environmental context in one chronological table, with heart-rate target slots in separate streams. It does not fit a model or authorize training, numerical predictions, causal inference, or pre-exercise forecasting.

## API

`POST /api/v1/integrations/polar/sessions/{session_external_id}/response-dataset/inspect?route_date=YYYY-MM-DD`

The POST is read-only: its body carries an optional split manifest. It never persists environmental evidence, HR proofs, sensor declarations, or split assignments. Session selection uses the existing token-bound owner and Polar scopes, selects exactly one requested session, and returns 404 for a missing session or 409 for duplicate matches. Client-supplied owner, readiness claims, physiological lag, and unknown fields are rejected with 422 before provider calls. Source transport failures return a generic 502.

The body is optional. `{}` produces a summary; `{"include_payload": true}` includes all observations and HR slots. `include_payload` is a strict JSON boolean.

Environmental provider parameters match route inspection: `weather_provider`, `hydrology_provider`, `hydrology_station_registry_number`, `hydrology_relation_provider`, `waterbody_provider`, `water_surface_provider`, and `marine_surface_provider`. `artifact_policy_profile` is also supported. Providers are selected explicitly; a provider omitted from the query does not become available because an earlier request saved evidence.

Existing `GET /api/v1/integrations/polar/sessions/routes/inspect` includes `response_dataset_contract` as a summary for each returned session. The legacy readiness audit retains its original semantics and decision hash for identical inputs.

## Payload and chronology

| Field | Meaning |
| --- | --- |
| `observations` | Every source window, including windows without an eligible HR label and out-of-duration windows. |
| `workload_observation` | Allowlisted retrospective GPS ground-motion fields, with no target HR fields. Ground speed is not boat speed relative to water. |
| `history_ref` | Route, exercise, sequence, first order, and last completed prior order in the shared observation table. |
| `temporal_context` | Source order, gaps, workload availability time, unknown initial physiological state, and censoring boundaries. |
| `hr_streams` | Deduplicated normalized HR series with original slot positions, values, validity masks, and verified export-grid timestamps when available. |
| `hr_label_ref` | Exact half-open `[start, end)` grid indices plus recorded, unrecorded, and invalid counts. References may extend beyond the actual recorded stream without creating samples. |
| `environment_components` | Component status, applicability, trust basis, source references, and limitations. |
| `environment_features` | Each metric's unit, availability state, value or null, and limitations. |
| `preparation_candidate` | Existing source/input eligibility plus a current verified export clock. This is a data-preparation candidate, not training authorization. |

History pointers avoid copying the entire past into each row. Missing HR does not remove a supported workload observation from later history. A gap starts a new observed sequence but does not establish a physiological reset. Sequence starts have unknown initial state and censored preceding history; their ends are also censored. There is no fixed history horizon or estimated response lag.

Current-window workload is available only after its observed interval and is marked for retrospective conditioning. The package does not select a causal predictor history. HR label values are never copied into workload conditioning.

Only an export proof bound to the current API source and owner supplies mapped HR timestamps. The verified export offset is not physiological HR lag. Native API sample-clock and pause-clock semantics remain unverified. Without a verified export clock, original HR slots remain available, timestamps and label mappings are null, and dataset preparation candidates are withheld. Duplicate or ambiguous owner/route/order/source bindings withhold the payload rather than silently sorting or aliasing rows.

## Environmental masks

Features distinguish `AVAILABLE`, `MISSING`, `WITHHELD`, and `NOT_APPLICABLE`. Numeric values are exposed only when finite and supported by a usable, applicable trusted component. Hydrological values additionally require the individual metric's availability and expected unit. No missing feature is imputed, no scaler is fitted, and unavailable wind direction is not guessed.

Weather retains sample time, provider/model-grid provenance, spatial and temporal match context. Hydrology retains metric measurement IDs, times, deltas, quality codes, and trust limitations. Water level and discharge are not converted to river-current velocity. Historical weather remains retrospective context; availability before an exercise is not established.

## Whole-session split manifest

```json
{
  "include_payload": true,
  "split_manifest": {
    "schema_version": "0.1",
    "manifest_id": "cohort-plan-001",
    "assignments": [
      {
        "provider": "POLAR",
        "athlete_id": "owner-returned-by-the-api",
        "session_external_id": "requested-session-id",
        "split": "TRAIN"
      }
    ]
  }
}
```

Assignments select whole `(provider, athlete, session)` groups and allow only `TRAIN`, `VALIDATION`, or `TEST`. Every route, exercise, history pointer, and HR stream for that session shares the assignment. A duplicate group is rejected even if its two assignments agree. Fragment-level assignments and authority claims are not accepted. Manifest order is canonicalized before hashing; another owner's matching session identifier never assigns this owner's session. Other manifest identities are not echoed in the result.

No manifest, or a manifest without the current group, yields `UNASSIGNED`. The manifest is used for this request only. Assigning a session does not establish chronological cohort separation, independence between sessions, or generalization to unseen athletes. It does not change the legacy audit's split-unassigned state or enable training. Those checks require a later cohort-level contract. Any future fitted preprocessing must use the training split only.

Primary references for later cohort design: [scikit-learn grouped cross-validation](https://scikit-learn.org/stable/modules/cross_validation.html#cross-validation-iterators-for-grouped-data), [GroupKFold](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.GroupKFold.html), and [data leakage and preprocessing](https://scikit-learn.org/stable/common_pitfalls.html#data-leakage).

## Integrity and limits

`package_hash` is SHA-256 of the full payload without the hash field, using sorted-key compact JSON, `allow_nan=False`, and the default ASCII string escaping. It commits to the owner, source/audit hashes, proofs, manifest, all rows, and all HR slots. `verify_route_response_dataset` verifies full-payload integrity only; it does not certify the trustworthiness of arbitrary client claims.

The summary keeps the full payload's commitment, four or fewer observation previews, no HR samples, and at most 25 sequences per route with truncation indicators. Its own bytes cannot be verified against the full-payload hash. Identical captured inputs produce identical packages; recapturing live providers can change hashes because upstream runtime metadata may change.

`input_provenance.scope` is `CURRENT_PROVIDED_SOURCE_AND_PROOFS`. `database_environment_replay_verified` is false: this release uses the existing current-source inspection pipeline, not an offline replay of saved environmental snapshots. Retain a full JSON payload when a reproducible captured package is needed.

No migration or new dependency is required. The migration head remains `c5e83a9d2714`. Scientific evidence persistence remains owned by the existing explicit endpoints.

## Validation

The new split, dataset, and API suites cover strict manifests, owner isolation, source binding, precise grid boundaries, missing labels and history, withheld environmental components, metric masks, ambiguous chronology, deduplicated streams, summary bounds, integrity, API errors, and database evidence preservation. A private control probe uses the supplied real HR series and TCX with an explicitly synthetic workload/environment scaffold. Actual Windows installation and live provider inspection require the supplied user-side check.
