# V24 — Expected-response model foundation

## Baseline and scope

Baseline: `8ef00ec5c35b287f7ca423fcdede5db616567569`, V23.5 closed,
680 passed, 1 warning. The historical positive production flood-stage projection
remains unavailable for the athlete's existing routes. Its documented domain
is unchanged, and no additional V23.5 live positive control is required here.

V24 introduces a provider-independent, versioned model decision contract after
the existing V21/V22 route input assembly. It is a foundation milestone;
it does not introduce a calibrated physiological estimator.

`route_expected_response_input.model_ready` remains input readiness.
It is not evidence of model calibration, physiological validity, or a prediction.

The shared Polar route-inspection builder now returns the compact contract under
`route_sessions[].route_expected_response_model`, on both inspect and existing
environment-persistence responses. No new query parameter, dependency or migration
is required. Model decisions are not stored in the database in V24.

## Contract

Model ID: `PADDLETRAINER_EXPECTED_RESPONSE_FOUNDATION`.
Model version: `0.1.0`. Output schema: `0.1`. Accepted input schema: `0.1`.
Stage: `FOUNDATION_ONLY`.

| Field | Meaning |
| --- | --- |
| `available` | At least one route decision exists; does not mean a response exists. |
| `input_eligible_route_count` | Routes that satisfy the input-boundary checks. |
| `input_blocked_route_count` | Routes blocked by explicit input reasons. |
| `estimated_route_count` | Always zero in this foundation. |
| `response_available` | Always false in this foundation. |
| `response_withheld_route_count` | All route outputs, including eligible routes. |
| `model.numeric_output_authorized` | Always false until a validated estimator is introduced. |
| `routes[].input_status` | Original V21 readiness status, retained without promotion. |
| `routes[].input_eligible` | Boundary eligibility, not model-specific physiological sufficiency. |
| `routes[].input_blocking_reasons` | Input failures, distinct from missing-estimator reasons. |
| `routes[].expected_response` | Withheld response with null value and unit. |

Overall status:

- `UNAVAILABLE`: no route decisions.
- `WITHHELD`: routes exist, but none satisfies the boundary checks.
- `NOT_ESTIMATED`: at least one route satisfies the boundary; there is no estimator.

Mixed routes retain individual eligibility and reasons. No partial-route
physiological prediction is authorized. Per-segment diagnostics are available
from the full service result; the API summary omits them.

Even eligible routes have `expected_response.status = WITHHELD` and reason
`PHYSIOLOGICAL_RESPONSE_MODEL_NOT_CONFIGURED`. Unknown uncertainty remains
`NOT_ESTABLISHED`; interval and confidence are null, not zero.

## Checks and evidence commitments

The boundary requires the full input, not the V21 compact summary. It checks:

- explicit supported schema and upstream route readiness;
- bound AthleteState and usable route environment;
- unique route and segment identities;
- alignment, actual workload/environment payloads, nested environment trust;
- declared segment counts against the full segment list;
- verifiable timezone-aware state/target timestamps and carry-forward policy;
- recomputed state age, no future state, and no out-of-policy state;
- equality of the supplied state context with the V22 bound context;
- canonical JSON evidence, rejecting NaN, infinity and unknown object types.

The existing V22 binder retains authority over snapshot selection and the
prior-local-day production source policy. V24 does not reinterpret component
recency or change the upstream carry-forward policy. A legacy caller-only
`BOUND` flag without temporal evidence is insufficient for this boundary.

Input hash: SHA256 over the entire V21 input, including measurements, uncertainty,
provenance, state and binding. Canonical representation uses sorted object keys,
UTF-8, no whitespace, strict finite JSON numbers, and ISO serialization of native
Python dates/datetimes. List order is significant. This is an exact input
commitment, not a semantic equivalence resolver.

Decision hash: SHA256 over the full V24 output before adding `decision_hash`.
It includes the model version and full-input hash. The API summary retains this
full-decision commitment; hashing the compact summary itself is not equivalent.
These hashes provide traceability, not database-backed immutable persistence.

Binding provenance retains selected snapshot ID/hash/source, timestamps, source
policy and limitations without repeating candidate or whole-state payloads.
Route and segment limitations survive. An interval water level is committed as
an interval; it is not converted to a scalar or local current estimate.

Optional hydrology can remain withheld while the upstream environment aggregate
is usable through other components. V24 does not require every optional component
to become trusted and does not promote their individual trust.

## Validation completed in the development workspace

- Original baseline: **680 passed, 1 warning**.
- New V24 tests: **48**.
- Focused V24 + input/binding suite: **115 passed**.
- Full API regression: **728 passed, 1 warning**.
- Ruff check and formatting of the new service/tests: passed.
- Real route-orchestration tests cover empty inputs and prepared eligible/withheld
  V21 inputs. External I/O is mocked; they do not constitute athlete live validation.
- Native and API-serialized dates produce the same input/decision commitments.
- Read-only inspect orchestration does not invoke environment persistence.

Runtime: Python 3.12.14 on Linux, with dependencies installed from the existing
`apps/api/pyproject.toml`. The one warning is the installed FastAPI/Starlette
test-client deprecation. User Windows regression and real athlete live validation
are pending. No Git commit or push was made for V24.

## Apply the full-file ZIP patch on Windows

Run from `C:\Users\gyula\OneDrive\Dokumentumok\PaddleTrainerProject`.
Save `paddletrainer_v24_expected_response_model_foundation.zip` into Downloads,
or adjust `$v24PatchPath`. Verify its SHA256 against the value supplied with the
download before extraction. The archive has exactly the four commit-scope files
listed below; it does not contain `.env`, a virtualenv, databases or Git metadata.

```powershell
$v24PatchPath = Join-Path $env:USERPROFILE 'Downloads\paddletrainer_v24_expected_response_model_foundation.zip'
Get-FileHash -LiteralPath $v24PatchPath -Algorithm SHA256

$v24Base = (git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $v24Base -ne '8ef00ec5c35b287f7ca423fcdede5db616567569') {
    throw 'V24 patch requires the exact 8ef00ec baseline.'
}
$v24Files = @(
    'apps/api/app/api/routes/polar.py'
    'apps/api/app/services/route_expected_response_model.py'
    'apps/api/tests/test_route_expected_response_model.py'
    'docs/v24_expected_response_model_foundation.md'
)
$v24LocalChanges = @(git status --porcelain -- $v24Files)
if ($LASTEXITCODE -ne 0 -or $v24LocalChanges.Count -gt 0) {
    throw 'An affected file already has local changes; review before replacing it.'
}
Expand-Archive -LiteralPath $v24PatchPath -DestinationPath . -Force
git diff --check
git status --short
```

The three intentionally untracked temporary files remain untouched and must not
be added to Git. This patch does not change V23 hydrology, existing persistence
schemas, model input construction or bootstrap settings.

## Focused and full regression

```powershell
.\.venv\Scripts\python.exe -m pytest apps/api/tests/test_route_expected_response_model.py apps/api/tests/test_route_expected_response_input.py apps/api/tests/test_athlete_state_temporal_binding.py apps/api/tests/test_athlete_state_live_binding.py apps/api/tests/test_athlete_state_scientific_view_adapter.py apps/api/tests/test_athlete_state_scientific_view_live_source.py -q
if ($LASTEXITCODE -ne 0) { throw 'V24 focused tests failed.' }

.\.venv\Scripts\python.exe -m pytest apps/api/tests -q
if ($LASTEXITCODE -ne 0) { throw 'V24 full regression failed.' }
```

Expected: **115 passed** focused; **728 passed** full. Warning text/count can
depend on locally installed dependency versions.

## Live validation — existing Duna control

Restart Uvicorn in a separate PowerShell window:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir apps/api --host 127.0.0.1 --port 8000
```

Use the existing Duna 2026-09-30 direct control. The URL below uses the already
supported provider parameters; any existing successful inspect URL can be reused.

```powershell
$v24Url = 'http://127.0.0.1:8000/api/v1/integrations/polar/sessions/routes/inspect?route_date=2026-09-30&weather_provider=OPEN_METEO_HISTORICAL&hydrology_provider=OVF_VRAQUERY&hydrology_station_registry_number=1026&waterbody_provider=EEA_WISE_WFD&water_surface_provider=EEA_EU_HYDRO'
$v24Result = Invoke-RestMethod -Uri $v24Url
foreach ($v24Session in $v24Result.route_sessions) {
    $v24Input = $v24Session.route_expected_response_input
    $v24Model = $v24Session.route_expected_response_model
    [PSCustomObject]@{
        ExternalId = $v24Session.external_id
        InputStatus = $v24Input.status
        UpstreamModelReady = $v24Input.model_ready_route_count
        ModelStatus = $v24Model.status
        ModelId = $v24Model.model.model_id
        ModelVersion = $v24Model.model.model_version
        ModelStage = $v24Model.model.stage
        InputEligible = $v24Model.input_eligible_route_count
        InputBlocked = $v24Model.input_blocked_route_count
        EstimatedRoutes = $v24Model.estimated_route_count
        ResponseAvailable = $v24Model.response_available
        NumericAuthorized = $v24Model.model.numeric_output_authorized
        InputHash = $v24Model.input_provenance.expected_response_input_hash
        DecisionHash = $v24Model.decision_hash
        StateSourcePolicy = $v24Model.input_provenance.athlete_state_binding.selected_snapshot.source.source_policy
    } | Format-List
    $v24Model.routes | Select-Object route_index, exercise_index, input_status, input_eligible, status, input_blocking_reasons | Format-List
    $v24Model.routes.expected_response | Format-List
}
```

For the previously working Duna route, expect upstream `READY_WITH_LIMITATIONS`,
one eligible input route, `ModelStatus = NOT_ESTIMATED`, `FOUNDATION_ONLY`,
`EstimatedRoutes = 0`, `ResponseAvailable = False`, `NumericAuthorized = False`,
two 64-character hashes, and withheld response reason
`PHYSIOLOGICAL_RESPONSE_MODEL_NOT_CONFIGURED`. The state source policy remains
`PRIOR_LOCAL_DAY_CLOSED_WINDOW`.

If eligibility differs, report `input_blocking_reasons` and upstream input/binding
status. Do not relax a gate just to obtain a ready result. A source service can
fail independently of V24; such failure is not a successful live validation.

Optional negative control: inspect the same date without environment providers.

```powershell
$v24Negative = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/v1/integrations/polar/sessions/routes/inspect?route_date=2026-09-30'
$v24Negative.route_sessions.route_expected_response_model | Select-Object status, input_eligible_route_count, input_blocked_route_count, estimated_route_count, response_available | Format-List
$v24Negative.route_sessions.route_expected_response_model.routes | Select-Object input_status, input_eligible, input_blocking_reasons | Format-List
```

With route data but no usable environment, expect `WITHHELD`, zero eligible
routes, zero estimates, and explicit input reasons.

## Git checkpoint — only after Windows regression and live validation

```powershell
git diff --check
git add -- apps/api/app/api/routes/polar.py apps/api/app/services/route_expected_response_model.py apps/api/tests/test_route_expected_response_model.py docs/v24_expected_response_model_foundation.md
git diff --cached --stat
git commit -m "Add expected-response model foundation"
git status --short
```

Next estimator milestone must specify a response target, a scientifically
supported model, explicit calibration/validity domain, model-specific input
requirements, uncertainty and temporal separation from actual response. Those
are not established by the V24 input-eligibility flags.
