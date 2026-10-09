"""Offline retrospective development baseline, with reserved TEST and small-sample guard.

Every run rechecks the full B reconstruction. Duration means describe recorded
interval support, not continuous mechanics or a measured physiological delay.
Two TRAIN sessions are a technical guard, never a sample adequacy assertion.
"""

import math
from copy import deepcopy

from app.schemas.response_baseline_experiment import ResponseBaselinePlan
from app.services.environment_replay_snapshot import canonical_hash
from app.services.response_dataset_integrity import require_json_size
from app.services.response_model_inputs import check_response_model_input_package

MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
MAX_ADAPTER_COLUMNS = 32
MAX_DEVELOPMENT_ROWS = 20_000
MAX_INTEGRATION_TERMS = 20_000_000
CHECK_SCOPE = "LOCAL_RECONSTRUCTION_AND_TRAIN_ONLY_DEVELOPMENT_CALCULATIONS"
PIN_KEYS = (
    "experiment_manifest_hash",
    "input_package_hash",
    "cohort_record_hash",
    "cohort_index_hash",
    "request_manifest_hash",
)


def _require(condition, code):
    if not condition:
        raise ValueError(code)


def _finite(value):
    _require(math.isfinite(value), "BASELINE_NONFINITE_CALCULATION")
    return value


def _seal(body, key):
    return {**body, key: canonical_hash(body)}


def _assert_hash(value, key):
    require_json_size(value, MAX_ARTIFACT_BYTES, "BASELINE_ARTIFACT_SIZE_LIMIT")
    _require(
        value.get(key) == canonical_hash({k: v for k, v in value.items() if k != key}),
        "BASELINE_ARTIFACT_HASH_MISMATCH",
    )


def build_response_baseline_plan(package, manifest, archive, datasets, *, run_id):
    check_response_model_input_package(package, manifest, archive, datasets)
    value = ResponseBaselinePlan.model_validate(
        {"run_id": run_id, **{k: package[k] for k in PIN_KEYS}, "plan_hash": "0" * 64}
    )
    return value.committed_payload()


def _validated_plan(plan, package):
    value = ResponseBaselinePlan.model_validate(plan).committed_payload()
    _require(value["plan_hash"] == plan["plan_hash"], "BASELINE_PLAN_HASH_MISMATCH")
    _require(all(value[k] == package[k] for k in PIN_KEYS), "BASELINE_PLAN_SOURCE_PIN_MISMATCH")
    return value


def _adapter(package):
    columns = [
        {
            "name": f"{column['name']}__duration_mean_{width}ms",
            "source_feature": column["name"],
            "source": column["source"],
            "unit": column["unit"],
            "lookback_ms": width,
        }
        for width in package["lookback_windows_ms"]
        for column in package["columns"]
    ]
    _require(len(columns) <= MAX_ADAPTER_COLUMNS, "BASELINE_ADAPTER_COLUMN_LIMIT")
    selected = [m for m in package["members"] if m["split"] in ("TRAIN", "VALIDATION")]
    _require(
        sum(len(m["targets"]) for m in selected) <= MAX_DEVELOPMENT_ROWS,
        "BASELINE_DEVELOPMENT_ROW_LIMIT",
    )
    terms = sum(
        (w["stop_input_row_index_exclusive"] - w["first_input_row_index_inclusive"])
        * len(package["columns"])
        for m in selected
        for t in m["targets"]
        for w in t["history_windows"]
    )
    _require(terms <= MAX_INTEGRATION_TERMS, "BASELINE_INTEGRATION_WORK_LIMIT")
    members = []
    for member in selected:
        arrays, rows = member["input_arrays"], []
        for target in member["targets"]:
            vector = []
            for window in target["history_windows"]:
                first = window["first_input_row_index_inclusive"]
                stop = window["stop_input_row_index_exclusive"]
                support = [
                    min(arrays["stop_exercise_elapsed_ms"][i], window["stop_exercise_elapsed_ms"])
                    - max(
                        arrays["start_exercise_elapsed_ms"][i],
                        window["start_exercise_elapsed_ms"],
                    )
                    for i in range(first, stop)
                ]
                _require(
                    all(d > 0 for d in support) and sum(support) == window["lookback_ms"],
                    "BASELINE_HISTORY_SUPPORT_INVALID",
                )
                for col in range(len(package["columns"])):
                    vector.append(
                        _finite(
                            math.fsum(
                                arrays["values"][i][col] * (d / window["lookback_ms"])
                                for i, d in zip(range(first, stop), support)
                            )
                        )
                    )
            index = target["input_row_index"]
            rows.append(
                {
                    "source_row_id": target["source_row_id"],
                    "input_row_index": index,
                    "route_index": arrays["route_indices"][index],
                    "exercise_index": arrays["exercise_indices"][index],
                    "sequence_index": arrays["sequence_indices"][index],
                    "target_start_exercise_elapsed_ms": arrays["start_exercise_elapsed_ms"][index],
                    "target_stop_exercise_elapsed_ms": arrays["stop_exercise_elapsed_ms"][index],
                    "values": vector,
                    "recorded_hr_mean_bpm": target["recorded_hr_mean_bpm"],
                    "history_windows": deepcopy(target["history_windows"]),
                }
            )
        members.append(
            {
                **{k: member[k] for k in ("athlete_id", "session_external_id", "split")},
                "source_unassigned_replay_package_hash": member[
                    "source_unassigned_replay_package_hash"
                ],
                "coverage": deepcopy(member["coverage"]),
                "sequence_metadata": deepcopy(member["sequence_metadata"]),
                "rows": rows,
            }
        )
    return _seal(
        {
            "columns": columns,
            "members": members,
            "development_row_count": sum(len(m["rows"]) for m in members),
            "test_adapted_row_count": 0,
            "integration_terms": terms,
            "semantics": "RECORDED_INTERVAL_SUPPORT_ONLY_RETROSPECTIVE_CONDITIONING",
        },
        "adapter_hash",
    )


def _cholesky_solve(matrix, rhs):
    """Small positive definite system; fixed L2 penalty supplies the diagonal."""
    size = len(rhs)
    lower = [[0.0] * size for _ in range(size)]
    for i in range(size):
        for j in range(i + 1):
            residual = _finite(
                matrix[i][j] - math.fsum(lower[i][k] * lower[j][k] for k in range(j))
            )
            if i == j:
                _require(residual > 0, "BASELINE_RIDGE_SYSTEM_NOT_POSITIVE_DEFINITE")
                lower[i][j] = math.sqrt(residual)
            else:
                lower[i][j] = _finite(residual / lower[j][j])
    forward = []
    for i in range(size):
        forward.append(
            _finite((rhs[i] - math.fsum(lower[i][j] * forward[j] for j in range(i))) / lower[i][i])
        )
    result = [0.0] * size
    for i in range(size - 1, -1, -1):
        result[i] = _finite(
            (forward[i] - math.fsum(lower[j][i] * result[j] for j in range(i + 1, size)))
            / lower[i][i]
        )
    return result


def _fit(train, columns, alpha):
    """No VALIDATION or TEST argument exists on this fitting boundary."""
    train = [m for m in train if m["rows"]]
    _require(bool(train), "BASELINE_NONEMPTY_TRAIN_REQUIRED")
    row_count, session_count = sum(len(m["rows"]) for m in train), len(train)
    rows = [r for m in train for r in m["rows"]]
    weights = [row_count / (session_count * len(m["rows"])) for m in train for _ in m["rows"]]
    normalized = [w / row_count for w in weights]
    target_mean = _finite(
        math.fsum(w * r["recorded_hr_mean_bpm"] for w, r in zip(normalized, rows))
    )
    means, scales, bounds, active, dropped = [], [], [], [], []
    for col in range(len(columns)):
        values = [r["values"][col] for r in rows]
        mean = _finite(math.fsum(w * v for w, v in zip(normalized, values)))
        low, high = min(values), max(values)
        constant = high - low <= 1e-12 * max(1.0, abs(low), abs(high))
        scale = (
            None
            if constant
            else _finite(
                math.sqrt(math.fsum(w * (v - mean) ** 2 for w, v in zip(normalized, values)))
            )
        )
        _require(constant or scale > 0, "BASELINE_TRAIN_SCALE_INVALID")
        means.append(mean)
        scales.append(scale)
        bounds.append({"min": low, "max": high})
        (dropped if constant else active).append(col)
    ridge = {
        "status": "WITHHELD_MULTIPLE_TRAIN_SESSIONS_REQUIRED"
        if session_count < 2
        else "FITTED_WITH_LIMITATIONS",
        "fit_performed": session_count >= 2,
        "alpha": alpha,
        "intercept_bpm": None,
        "coefficients": None,
        "active_column_indices": active,
    }
    if session_count >= 2:
        standardized = [[(r["values"][c] - means[c]) / scales[c] for c in active] for r in rows]
        centered = [r["recorded_hr_mean_bpm"] - target_mean for r in rows]
        matrix = [
            [
                _finite(
                    math.fsum(w * z[i] * z[j] for w, z in zip(weights, standardized))
                    + (alpha if i == j else 0.0)
                )
                for j in range(len(active))
            ]
            for i in range(len(active))
        ]
        rhs = [
            _finite(math.fsum(w * z[i] * y for w, z, y in zip(weights, standardized, centered)))
            for i in range(len(active))
        ]
        ridge.update(intercept_bpm=target_mean, coefficients=_cholesky_solve(matrix, rhs))
    return _seal(
        {
            "train_design_hash": canonical_hash(train),
            "train_session_ids": [m["session_external_id"] for m in train],
            "train_session_count": session_count,
            "train_row_count": row_count,
            "columns": deepcopy(columns),
            "weighting": "EQUAL_SESSION_TOTAL_WEIGHT_SUM_EQUALS_TRAIN_ROW_COUNT",
            "constant_hr_mean_bpm": target_mean,
            "preprocessing": {
                "fit_scope": "TRAIN_ONLY",
                "means": means,
                "population_scales": scales,
                "train_bounds": bounds,
                "dropped_numerical_constant_column_indices": dropped,
            },
            "ridge": ridge,
        },
        "parameter_hash",
    )


def _metrics(observed, predicted):
    errors = [_finite(p - y) for p, y in zip(predicted, observed)]
    count = len(errors)
    return {
        "MAE_BPM": _finite(math.fsum(abs(e) / count for e in errors)),
        "RMSE_BPM": _finite(math.sqrt(math.fsum((e * e) / count for e in errors))),
        "MEAN_SIGNED_ERROR_BPM": _finite(math.fsum(e / count for e in errors)),
    }


def _report(adapter, parameters):
    sessions = []
    for member in adapter["members"]:
        rows = member["rows"]
        observed = [r["recorded_hr_mean_bpm"] for r in rows]
        metrics = None
        outside = None
        if rows:
            metrics = {
                "constant": _metrics(observed, [parameters["constant_hr_mean_bpm"]] * len(rows))
            }
            if parameters["ridge"]["fit_performed"]:
                preprocessing, ridge = parameters["preprocessing"], parameters["ridge"]
                predicted = [
                    _finite(
                        ridge["intercept_bpm"]
                        + math.fsum(
                            coef
                            * (r["values"][c] - preprocessing["means"][c])
                            / preprocessing["population_scales"][c]
                            for c, coef in zip(
                                ridge["active_column_indices"], ridge["coefficients"]
                            )
                        )
                    )
                    for r in rows
                ]
                metrics["ridge"] = _metrics(observed, predicted)
            outside = [
                sum(not bound["min"] <= r["values"][c] <= bound["max"] for r in rows)
                for c, bound in enumerate(parameters["preprocessing"]["train_bounds"])
            ]
        sessions.append(
            {
                "session_external_id": member["session_external_id"],
                "split": member["split"],
                "row_count": len(rows),
                "coverage": deepcopy(member["coverage"]),
                "metrics": metrics,
                "outside_train_range_row_counts_by_column": outside,
                "interpretation": "TRAIN_RESUBSTITUTION_DIAGNOSTIC"
                if member["split"] == "TRAIN"
                else "VALIDATION_DEVELOPMENT_ONLY",
            }
        )
    macro = {}
    for split in ("TRAIN", "VALIDATION"):
        scored = [s for s in sessions if s["split"] == split and s["metrics"] is not None]
        macro[split] = (
            None
            if not scored
            else {
                model: {
                    metric: math.fsum(s["metrics"][model][metric] / len(scored) for s in scored)
                    for metric in scored[0]["metrics"][model]
                }
                for model in scored[0]["metrics"]
            }
        )
    return {
        "sessions": sessions,
        "partition_macro_mean_of_session_metrics": macro,
        "test_metrics": None,
        "test_scoring_performed": False,
        "model_selection_performed": False,
        "confidence_intervals_computed": False,
        "generalization_evidence_verified": False,
    }


def run_response_baseline_experiment(plan, package, manifest, archive, datasets):
    check_response_model_input_package(package, manifest, archive, datasets)
    policy = _validated_plan(plan, package)
    adapter = _adapter(package)
    parameters = _fit(
        [m for m in adapter["members"] if m["split"] == "TRAIN"],
        adapter["columns"],
        policy["ridge_alpha"],
    )
    train_count = parameters["train_session_count"]
    validation_count = sum(
        m["split"] == "VALIDATION" and bool(m["rows"]) for m in adapter["members"]
    )
    limitations = [
        "TECHNICAL_MULTIPLE_TRAIN_SESSION_GUARD_IS_NOT_SAMPLE_ADEQUACY",
        "GENERALIZATION_NOT_ESTABLISHED",
        "CORRELATED_ROWS_ARE_NOT_INDEPENDENT_SESSIONS",
        "RECORDED_WRIST_HR_QUALITY_NOT_PROMOTED",
        "OBSERVED_GPS_MOTION_IS_NOT_MEASURED_POWER",
        "LOOKBACK_SUMMARIES_DO_NOT_IDENTIFY_PHYSIOLOGICAL_LAG",
        "INITIAL_STATE_AND_CENSORED_HISTORY_RETAINED",
        "TEST_READ_FOR_INTEGRITY_ONLY_NOT_SCORED",
    ]
    if train_count == 1:
        limitations.append("SINGLE_TRAIN_SESSION_RIDGE_WITHHELD")
    if validation_count < 2:
        limitations.append("FEWER_THAN_TWO_NONEMPTY_VALIDATION_SESSIONS")
    run = _seal(
        {
            "schema_version": "0.1",
            "baseline_version": "0.1.0",
            "status": "SINGLE_TRAIN_SESSION_BASELINE_SMOKE_ONLY"
            if train_count == 1
            else "MULTISESSION_DEVELOPMENT_EXPERIMENT_WITH_LIMITATIONS",
            "plan": policy,
            "adapter": adapter,
            "parameters": parameters,
            "development_report": _report(adapter, parameters),
            "reserved_test_coverage": deepcopy(package["per_split_coverage"]["TEST"]),
            "execution_limits": {
                "max_artifact_bytes": MAX_ARTIFACT_BYTES,
                "max_adapter_columns": MAX_ADAPTER_COLUMNS,
                "max_development_rows": MAX_DEVELOPMENT_ROWS,
                "max_integration_terms": MAX_INTEGRATION_TERMS,
            },
            "constant_baseline_fit_performed": True,
            "train_preprocessing_fit_performed": True,
            "ridge_fit_performed": parameters["ridge"]["fit_performed"],
            "experimental_numeric_calculations_performed": True,
            "test_payload_read_for_integrity_only": True,
            "test_adapted_row_count": 0,
            "test_scoring_performed": False,
            "source_evidence_verified": False,
            "current_source_evidence_verified": False,
            "owner_authorization_verified": False,
            "database_record_persisted": False,
            "split_assignment_persisted": False,
            "generalization_evidence_verified": False,
            "training_authorized": False,
            "numeric_output_authorized": False,
            "pre_exercise_prediction_authorized": False,
            "causal_prediction_authorized": False,
            "missing_values_imputed": False,
            "pft_data_used": False,
            "fixed_hr_shift_applied": False,
            "physiological_lag_ms": None,
            "polar_provider_calls": 0,
            "environmental_provider_calls": 0,
            "database_storage_writes": 0,
            "claim_scope": CHECK_SCOPE,
            "limitations": limitations,
        },
        "run_hash",
    )
    require_json_size(run, MAX_ARTIFACT_BYTES, "BASELINE_ARTIFACT_SIZE_LIMIT")
    return run


def check_response_baseline_experiment(run, plan, package, manifest, archive, datasets):
    _assert_hash(run, "run_hash")
    expected = run_response_baseline_experiment(plan, package, manifest, archive, datasets)
    _require(run["run_hash"] == expected["run_hash"], "BASELINE_RECONSTRUCTION_MISMATCH")
    return {
        "status": "LOCALLY_RECONSTRUCTED_DEVELOPMENT_BASELINE",
        "run_hash": expected["run_hash"],
        "parameter_hash": expected["parameters"]["parameter_hash"],
        "plan_hash": expected["plan"]["plan_hash"],
        "payload_integrity_verified": True,
        "reconstruction_verified": True,
        "train_only_fit_verified": True,
        "ridge_fit_performed": expected["ridge_fit_performed"],
        "test_scoring_performed": False,
        "generalization_evidence_verified": False,
        "training_authorized": False,
        "numeric_output_authorized": False,
        "source_evidence_verified": False,
        "current_source_evidence_verified": False,
        "owner_authorization_verified": False,
        "claim_scope": CHECK_SCOPE,
    }
