import asyncio
import math
from copy import deepcopy
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from test_environment_replay_persistence import scientific_state
from test_response_cohort_assembly import full_replay
from test_response_cohort_chronology import add_session, assemble, member_pins
from test_response_model_inputs import (
    archive as _archive,
    chronological as _chronological,
    completed as _completed,
    environment as _environment,
    inputs as _inputs,
    long_local_fixture,
    masked_fixture,
    plan as input_plan,
    repin_local_fixture,
    sources as _sources,
)

from app.schemas.response_baseline_experiment import ResponseBaselinePlan
from app.services import response_baseline_experiment as module
from app.services.environment_replay_snapshot import canonical_hash
from app.services.response_cohort_storage_contract import build_cohort_record_payload
from app.services.response_experiment_contract import build_response_experiment_manifest
from app.services.response_model_inputs import build_response_model_input_package

archive, chronological, completed, environment, inputs, sources = (
    _archive,
    _chronological,
    _completed,
    _environment,
    _inputs,
    _sources,
)


def make(record, datasets, manifest=None):
    manifest = manifest or input_plan(record)
    package = build_response_model_input_package(manifest, record, datasets)
    policy = module.build_response_baseline_plan(
        package, manifest, record, datasets, run_id="development-tests"
    )
    return policy, package, manifest, record, datasets


@pytest.fixture
def ready(inputs):
    return make(*inputs)


def run(data):
    return module.run_response_baseline_experiment(*data)


def rehash(value):
    value["run_hash"] = canonical_hash({k: v for k, v in value.items() if k != "run_hash"})
    return value


def test_single_train_full_source_reconstruction_preserves_sources_and_reserves_test(
    ready, completed
):
    env, _ = completed
    before = scientific_state(env), env.provider.await_count, env.db.commit_count
    original = deepcopy(ready)
    result = run(ready)
    checked = module.check_response_baseline_experiment(result, *ready)
    assert checked["reconstruction_verified"] is checked["train_only_fit_verified"] is True
    assert result["status"] == "SINGLE_TRAIN_SESSION_BASELINE_SMOKE_ONLY"
    assert result["parameters"]["ridge"]["status"] == "WITHHELD_MULTIPLE_TRAIN_SESSIONS_REQUIRED"
    assert result["parameters"]["ridge"]["coefficients"] is None
    assert result["ridge_fit_performed"] is False
    assert (
        result["constant_baseline_fit_performed"]
        is result["train_preprocessing_fit_performed"]
        is True
    )
    assert result["adapter"]["development_row_count"] == 2
    assert len(result["adapter"]["columns"]) == 8
    assert [m["session_external_id"] for m in result["adapter"]["members"]] == [
        "session-1",
        "session-3",
    ]
    assert result["reserved_test_coverage"]["model_input_row_count"] == 1
    assert result["development_report"]["test_metrics"] is None
    assert all("ridge" not in s["metrics"] for s in result["development_report"]["sessions"])
    for key in (
        "source_evidence_verified",
        "current_source_evidence_verified",
        "owner_authorization_verified",
        "training_authorized",
        "numeric_output_authorized",
        "generalization_evidence_verified",
        "split_assignment_persisted",
        "test_scoring_performed",
        "pft_data_used",
        "fixed_hr_shift_applied",
        "missing_values_imputed",
    ):
        assert result[key] is False
    assert result["test_payload_read_for_integrity_only"] is True
    assert result["test_adapted_row_count"] == 0
    assert result["physiological_lag_ms"] is None
    assert (
        result["polar_provider_calls"]
        == result["environmental_provider_calls"]
        == result["database_storage_writes"]
        == 0
    )
    assert ready == original
    assert before == (scientific_state(env), env.provider.await_count, env.db.commit_count)
    for member in result["adapter"]["members"]:
        assert member["sequence_metadata"][0]["initial_physiological_state"] == "UNKNOWN"


def test_clipped_irregular_interval_mean_uses_duration_not_number_of_rows(ready):
    result = run(ready)
    arrays = ready[1]["members"][0]["input_arrays"]
    vector = result["adapter"]["members"][0]["rows"][0]["values"]
    columns = len(ready[1]["columns"])
    assert vector[:columns] == pytest.approx(arrays["values"][1])
    assert vector[columns:] == pytest.approx([(a + 2 * b) / 3 for a, b in zip(*arrays["values"])])


def test_default_long_windows_keep_exact_duration_and_unknown_history(inputs):
    record, datasets = long_local_fixture(inputs)
    manifest = build_response_experiment_manifest(record, experiment_id="long-window-baseline")
    result = run(make(record, datasets, manifest))
    assert result["adapter"]["development_row_count"] == 562
    assert len(result["adapter"]["columns"]) == 12
    row = result["adapter"]["members"][0]["rows"][0]
    assert row["input_row_index"] == 119
    assert [row["values"][i] for i in (0, 4, 8)] == pytest.approx([2.1045, 2.0895, 2.0595])
    assert row["recorded_hr_mean_bpm"] == 111.9
    assert [w["covered_duration_ms"] for w in row["history_windows"]] == [30000, 60000, 120000]
    assert all(w["stop_input_row_index_exclusive"] == 120 for w in row["history_windows"])


@pytest.mark.parametrize("split", ["VALIDATION", "TEST"])
def test_changed_local_holdout_predictors_and_labels_cannot_change_train_parameters(inputs, split):
    original = make(*inputs)
    first = run(original)
    record, datasets = deepcopy(inputs)
    sid = next(m["session_external_id"] for m in original[1]["members"] if m["split"] == split)
    dataset = next(d for d in datasets if d["session_external_id"] == sid)
    for row in dataset["observations"]:
        row["workload_observation"]["gps_ground_speed_mps"] += 100
        row["environment_features"]["air_temperature_c"]["value"] += 80
    for slot in dataset["hr_streams"][0]["samples"]:
        slot["value_bpm"] += 50
    record = repin_local_fixture(record, datasets)
    # Synthetic local re-commitment tests information flow, not live source proof.
    second = run(make(record, datasets))
    assert first["parameters"] == second["parameters"]
    assert first["plan"]["input_package_hash"] != second["plan"]["input_package_hash"]
    assert first["run_hash"] != second["run_hash"]
    if split == "TEST":
        assert first["adapter"] == second["adapter"]
        assert first["development_report"] == second["development_report"]
    else:
        assert first["development_report"] != second["development_report"]
        assert any(
            second["development_report"]["sessions"][1]["outside_train_range_row_counts_by_column"]
        )


def test_reordered_exact_sources_produce_identical_artifact(ready):
    assert run(ready) == run((*ready[:-1], list(reversed(ready[-1]))))


@pytest.mark.parametrize(
    "field,value",
    [
        ("fit_scope", "ALL_SPLITS"),
        ("test_role", "FINAL_SCORING"),
        ("ridge_alpha", 0.0),
        ("ridge_alpha", 1.0),
        ("ridge_alpha", 10),
        ("ridge_alpha", "10.0"),
        ("ridge_min_nonempty_train_sessions", 1),
        ("ridge_min_nonempty_train_sessions", True),
        ("ridge_min_nonempty_train_sessions", 2.0),
        ("training_authorized", True),
        ("training_authorized", 0),
        ("generalization_evidence_verified", True),
        ("fatigue_target_used", True),
        ("pft_data_used", True),
        ("physiological_lag_ms", 30000),
        ("missing_values_imputed", True),
        ("fixed_hr_shift_applied", True),
        ("hyperparameter_search_performed", True),
        ("extra", False),
    ],
)
def test_policy_rejects_override_or_python_boolean_numeric_alias(ready, field, value):
    changed = deepcopy(ready[0])
    changed[field] = value
    with pytest.raises(ValidationError):
        ResponseBaselinePlan.model_validate(changed)


@pytest.mark.parametrize(
    "case",
    [
        "mean",
        "metric",
        "adapter_value",
        "test_metrics",
        "authority",
        "dropped_column",
        "bool_alias",
        "extra",
    ],
)
def test_rehashed_forged_calculation_or_test_claim_is_reconstructed_and_rejected(ready, case):
    result = run(ready)
    if case == "mean":
        result["parameters"]["constant_hr_mean_bpm"] += 1
    elif case == "metric":
        result["development_report"]["sessions"][0]["metrics"]["constant"]["MAE_BPM"] += 1
    elif case == "adapter_value":
        result["adapter"]["members"][0]["rows"][0]["values"][0] += 1
    elif case == "test_metrics":
        result["development_report"]["test_metrics"] = {"MAE_BPM": 0}
    elif case == "authority":
        result["training_authorized"] = True
    elif case == "dropped_column":
        result["parameters"]["preprocessing"]["dropped_numerical_constant_column_indices"] = []
    elif case == "bool_alias":
        result["test_scoring_performed"] = 0
    else:
        result["uncommitted_extra"] = True
    rehash(result)
    with pytest.raises(ValueError, match="BASELINE_RECONSTRUCTION_MISMATCH"):
        module.check_response_baseline_experiment(result, *ready)


def test_changed_test_source_with_valid_new_hash_but_old_pin_cannot_pass_integrity(ready):
    changed = deepcopy(ready)
    sid = next(m["session_external_id"] for m in changed[1]["members"] if m["split"] == "TEST")
    dataset = next(d for d in changed[-1] if d["session_external_id"] == sid)
    dataset["hr_streams"][0]["samples"][0]["value_bpm"] += 5
    dataset["package_hash"] = canonical_hash(
        {k: v for k, v in dataset.items() if k != "package_hash"}
    )
    with pytest.raises(ValueError, match="MODEL_INPUT_REPLAY_PACKAGE_PIN_MISMATCH"):
        run(changed)


def test_masked_inputs_are_excluded_without_imputation_and_empty_train_fails(inputs):
    record, datasets = masked_fixture(inputs, "WITHHELD")
    with pytest.raises(ValueError, match="BASELINE_NONEMPTY_TRAIN_REQUIRED"):
        run(make(record, datasets))
    record, datasets = long_local_fixture(inputs, 200)
    manifest = build_response_experiment_manifest(record, experiment_id="masked-baseline")
    result = run(make(record, datasets, manifest))
    assert result["adapter"]["development_row_count"] == 322
    assert result["parameters"]["train_row_count"] == 161
    assert result["missing_values_imputed"] is False


@pytest.mark.parametrize(
    "name,limit,code",
    [
        ("MAX_ADAPTER_COLUMNS", 1, "BASELINE_ADAPTER_COLUMN_LIMIT"),
        ("MAX_DEVELOPMENT_ROWS", 1, "BASELINE_DEVELOPMENT_ROW_LIMIT"),
        ("MAX_INTEGRATION_TERMS", 1, "BASELINE_INTEGRATION_WORK_LIMIT"),
    ],
)
def test_adapter_limits_reject_without_downsampling_or_partial_results(
    ready, monkeypatch, name, limit, code
):
    monkeypatch.setattr(module, name, limit)
    with pytest.raises(ValueError, match=code):
        run(ready)


def test_session_balanced_train_fit_and_fixed_ridge_have_analytic_solution():
    # This numerical kernel fixture deliberately has two independent session keys.
    columns = [{"name": "x"}]
    train = [
        {
            "session_external_id": "first",
            "rows": [{"values": [-1.0], "recorded_hr_mean_bpm": 100.0}],
        },
        {
            "session_external_id": "second",
            "rows": [{"values": [1.0], "recorded_hr_mean_bpm": 102.0}],
        },
    ]
    result = module._fit(train, columns, 10.0)
    assert result["constant_hr_mean_bpm"] == 101
    assert result["preprocessing"]["means"] == [0]
    assert result["preprocessing"]["population_scales"] == [1]
    assert result["ridge"]["fit_performed"] is True
    assert result["ridge"]["intercept_bpm"] == 101
    assert result["ridge"]["coefficients"] == pytest.approx([2 / 12])
    assert module._cholesky_solve([[4.0, 1.0], [1.0, 3.0]], [9.0, 7.0]) == pytest.approx(
        [20 / 11, 19 / 11]
    )


def test_longer_session_does_not_dominate_session_balanced_target_or_preprocessing():
    train = [
        {
            "session_external_id": "short",
            "rows": [
                {"values": [1.0], "recorded_hr_mean_bpm": 100.0},
                {"values": [3.0], "recorded_hr_mean_bpm": 102.0},
            ],
        },
        {
            "session_external_id": "long",
            "rows": [{"values": [1.0], "recorded_hr_mean_bpm": 130.0}] * 6,
        },
    ]
    result = module._fit(train, [{"name": "x"}], 10.0)
    assert result["constant_hr_mean_bpm"] == pytest.approx((101 + 130) / 2)
    assert result["preprocessing"]["means"] == pytest.approx([1.5])
    assert result["preprocessing"]["population_scales"] == pytest.approx([math.sqrt(0.75)])


def test_true_four_session_assembler_runs_guarded_ridge_without_generalization_claim(
    chronological, sources
):
    env = chronological
    holder, saved = asyncio.run(add_session(env, sources, 4, datetime(2026, 10, 1, 16, tzinfo=UTC)))
    package = full_replay(holder, saved)
    env.holders.append(holder)
    env.saved.append(saved)
    env.packages.append(package)
    env.route_sources.append(deepcopy(holder.inputs["route_session"]))
    env.sample_sources.append(deepcopy(holder.inputs["sample_session"]))
    env.request["members"].append(member_pins(holder, saved, package))
    for assignment in env.request["split_manifest"]["assignments"]:
        if assignment["session_external_id"] == "session-3":
            assignment["split"] = "TRAIN"
    env.request["split_manifest"]["assignments"].append(
        {
            "provider": "POLAR",
            "athlete_id": str(env.user.id),
            "session_external_id": "session-4",
            "split": "VALIDATION",
        }
    )
    index = assemble(env)
    assert index["chronological_split_verified"] is True
    record = build_cohort_record_payload(env.request, index, owner_id=env.user.id)
    ready = make(record, deepcopy(env.packages))
    before = scientific_state(env), env.provider.await_count, env.db.commit_count
    result = run(ready)
    assert result["parameters"]["train_session_count"] == 2
    assert result["ridge_fit_performed"] is True
    assert result["parameters"]["constant_hr_mean_bpm"] == pytest.approx((112.5 + 142.5) / 2)
    assert all("ridge" in s["metrics"] for s in result["development_report"]["sessions"])
    assert result["development_report"]["test_metrics"] is None
    assert result["generalization_evidence_verified"] is result["training_authorized"] is False
    assert before == (scientific_state(env), env.provider.await_count, env.db.commit_count)
