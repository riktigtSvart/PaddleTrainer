# V24.11-C — bounded retrospective development baseline

C adds a fixed offline experiment plan, duration-weighted history adapter,
TRAIN-only preprocessing/constant comparator, and a guarded small ridge kernel.
The current three-session cohort has only one TRAIN session. It therefore runs
the constant comparator and withholds ridge. TEST is not adapted or scored.
This slice verifies a development pipeline; it establishes no generalization,
fitness, fatigue, physiological delay, production readiness or scientific
numeric-output authority. There is no migration, endpoint or new dependency.

## Sample size and evaluation unit

The confirmed B package contains 6834 eligible observations: TRAIN 2522,
VALIDATION 1750, TEST 2562. There is one whole session in each partition.
Adjacent HR/workload rows and overlapping 30/60/120-second windows are correlated.
Thousands of rows are not thousands of independent sessions. A single TRAIN
session cannot establish coverage of day-to-day workload, environment or initial
state variation. A single VALIDATION or TEST session does not establish stable
between-session performance. Repeating the same fixture adds no observations.

The TRAIN partition fits parameters and preprocessing. VALIDATION diagnostics
can guide subsequent development, but do not then constitute an untouched final
assessment. TEST must not guide repeated feature, model or hyperparameter
changes. Its payload is still read and reconstructed by B's integrity checker;
it is not concealed from the operator. C performs no TEST adapter calculation,
parameter fitting, prediction or error scoring.

Official methodological references:

- [scikit-learn cross-validation guide](https://scikit-learn.org/stable/modules/cross_validation.html):
  dependent groups/time series require validation that respects the dependency;
  test-based iterative tuning leaks information into development.
- [scikit-learn common pitfalls](https://scikit-learn.org/stable/common_pitfalls.html):
  learn transformations on training data, and apply the resulting transformation
  to held-out data without fitting it there.
- [Ridge objective](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Ridge.html):
  L2-regularized squared error supplies a small comparison model, not evidence
  that its fit is scientifically useful.

The conclusion about this cohort's insufficiency is our methodological
assessment, not a universal published sample-size threshold. There is no
universally sufficient number of sessions specified by this slice.

## Exact local binding

`ResponseBaselinePlan` pins the A manifest, B input package and cohort
record/index/request hashes. It expands fixed policy defaults and commits a
canonical SHA-256 `plan_hash`. Extra fields, boolean/numeric aliases and policy
overrides are rejected. Its machine-readable schema is
`docs/contracts/response_baseline_plan_v0_1.schema.json`.

Every prepare/run/check invokes the full B reconstruction from the original
A contract, archive and exactly all pinned UNASSIGNED member replays. A B
summary or its own hash alone is insufficient. Wrong or missing pins, changed
values, labels, splits, masks or windows cannot be bypassed by rehashing a C
artifact. B/A flags describing their own earlier no-fit processes are retained
unchanged. C reports its new experimental computations separately.

All source/current-source/owner verification claims remain false for this
offline work. The original archive's historical evidence is not promoted to a
fresh live proof. No Polar/environmental call, database write, split-assignment
persistence or new proof acquisition occurs. Original source files are never
rewritten. CLI controls also compare the original file bytes after execution.

## Fixed adapter and numerical bounds

Only TRAIN and VALIDATION members are adapted. For each B-eligible target and
selected lookback, each selected column becomes its duration-weighted observed
interval mean. For a window `[T-L,T)`, let `d_i` be the overlap in milliseconds
of source interval `i` with that window. The value is `sum(v_i*d_i/L)`.
`math.fsum` sums the terms; no resampling or interpolation is performed.
Clipped first intervals get their actual overlap weight. Every required window
must have complete, finite, available support within its original
session/route/exercise/sequence. B already verifies these conditions; C rechecks
the consumed support. Missing/withheld inputs remain excluded, without imputation.

Columns are ordered by ascending lookback then B column order. The actual
four selected features times three lookbacks produce twelve columns. Labels
remain outside each row's predictor `values`. References to the source rows,
target interval, clipped windows, coverage and unknown/censored sequence metadata
are retained. Current completed workload is permitted for retrospective
conditioning. This does not establish an available pre-exercise predictor,
continuous physical power or a physiological delay. Technical export-clock
alignment is retained without fixed HR shift.

Limits are 32 adapted columns, 20000 development rows, 20000000 weighted
integration terms and 64 MiB per C artifact. The work count is checked before
integration. Oversized cases fail without downsampling or partial success.
Nonfinite calculations fail closed. B's own stricter source-binding/interval
checks and original input limits still apply.

## TRAIN-only fitting

Each nonempty TRAIN session gets equal total fitting weight. If there are `M`
sessions, `N` total rows and `n_s` rows in session `s`, each row's weight is
`N/(M*n_s)`. Weights sum to `N`. The constant comparator is the resulting
weighted TRAIN HR mean. Long recordings therefore do not dominate the session
mean simply because they have more rows.

Predictor means and population standard deviations use the same TRAIN-only
weights. Columns whose TRAIN range is at most
`1e-12 * max(1, abs(train_min), abs(train_max))` are treated as numerical
constants and omitted from ridge. This fixed roundoff guard is not target-based
feature selection. Validation changes never alter retained columns, means,
scales, constant value or coefficients. Validation values outside the observed
TRAIN ranges are counted; they are neither clamped nor used to refit.

Ridge requires at least two distinct, nonempty TRAIN sessions. This is a
technical guard against the current single-session fit, **not a scientifically
sufficient sample size**. It cannot be opted out of in this version. With only
one session the status is `WITHHELD_MULTIPLE_TRAIN_SESSIONS_REQUIRED`;
coefficients/intercept and ridge metrics are absent. With at least two, a
bounded Cholesky kernel solves the weighted standardized squared-error objective
with fixed `alpha=10.0`, no interactions and no hyperparameter search. The
unpenalized intercept is the TRAIN target mean. The value 10.0 is an engineering
commitment for this comparator, not a validated optimum. A fit with all constant
columns legitimately reduces to an intercept-only comparator.

`parameter_hash` commits only the TRAIN design, fixed columns, TRAIN-derived
statistics and model parameters. Full-cohort pins belong to the wrapper plan
and `run_hash`. Thus changing a locally re-committed synthetic VALIDATION/TEST
payload changes the wrapper binding without changing TRAIN parameters. Real
inputs are never re-committed automatically. Unannounced holdout changes fail
the original source pins.

## Reports and claims

Reports contain MAE, RMSE and mean signed error (`prediction - recorded HR`) per
TRAIN/VALIDATION session, coverage and out-of-TRAIN-range column counts. TRAIN
errors are resubstitution diagnostics. VALIDATION errors are development-only.
Partition summaries are arithmetic means of per-session metrics, not pooled
row metrics. Empty validation sessions have null metrics and retained coverage.
An entirely empty TRAIN partition stops the run. TEST metrics are null.

There are no IID confidence intervals, significance tests, automatic model
selection or readiness gates. `generalization_evidence_verified` stays false
even in the multi-session branch. Grit X wrist sensor identity/acquisition
quality, GPS-to-power equivalence and unknown physiological state are not
upgraded. No PFT data, fatigue target, recovery score or lag estimate is used.

`constant_baseline_fit_performed` and `train_preprocessing_fit_performed` are
true for a successful C run. `experimental_numeric_calculations_performed` is
true; the user has authorized this development calculation. The existing
`training_authorized` and `numeric_output_authorized` science-readiness fields
remain false. They do not erase the reported fact of the experimental
calculation. Ridge's fit flag is separately guarded.

The reconstruction checker rebuilds the whole adapter, TRAIN parameters and
development metrics from pinned originals. A hash alone is not validation of
the computations. Floating computations are deterministic for repeated runs
on the same supported runtime; cross-platform byte identity of new floating
artifacts is not claimed.

## CLI and the real control

`tools/run_response_baseline_experiment.py` bootstraps the API package path for
direct invocation. It offers `prepare`, `run`, `check` and `control`; every mode
requires the A manifest, full cohort archive, B package and all member replays.
`run`/`check` also require the committed plan. There is no TEST scoring switch,
alpha search switch, source fallback, HTTP client or database setup.

The bundled Hungarian README contains independent PowerShell blocks using the
confirmed A/archive/B paths. The C control creates a new exclusive output
folder and writes `baseline_plan.json` **before** computing development metrics.
It writes two identical run artifacts, a reconstruction check, per-session
development report, TRAIN parameter artifact and control summary (seven files).
Duplicate JSON keys, nonfinite JSON, oversized files and output collisions are
rejected. A stopped run retains the committed plan and any finished files for
inspection; it does not automatically remove the output folder.

Expected control for the current pinned cohort:

| Field | Expected |
| --- | --- |
| source observations / B model rows | 7762 / 6834 |
| adapter columns / development rows | 12 / 4272 |
| TRAIN sessions / TRAIN rows | 1 / 2522 |
| VALIDATION rows / reserved TEST rows | 1750 / 2562 |
| constant comparator / preprocessing fit | true / true |
| ridge fit / TEST adapted rows / TEST scoring | false / 0 / false |
| generalized performance established | false |

No MAE/RMSE value is guessed or required in advance. The independent tests use
synthetic fixtures, including an actual four-session fixture assembly for the
two-TRAIN branch and analytical weighted regression solutions. They are not
live evaluation of the user's recordings.

## Next data step

Keep the three-session package as a regression/integration control. Before
using the flexible model for a scientific conclusion, prepare more whole
sessions with varied recorded workload and conditions and the same source
proof/coverage checks. Design forward chronological evaluation folds at the
whole-session level; do not randomly split correlated rows. Refit preprocessing
and models only inside each fold's TRAIN sessions. Track per-session variation
and learning curves as the TRAIN cohort expands. Preselect later, untouched
final sessions and avoid tuning against their errors. Do not move the current
TEST into training merely to improve the development results.
