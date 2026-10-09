from copy import deepcopy

import pytest
from pydantic import ValidationError
from test_environment_replay_persistence import scientific_state
from test_response_cohort_storage_contract import (
    chronological as _chronological,
    completed as _completed,
    environment as _environment,
    sources as _sources,
)

from app.schemas.response_experiment import ResponseExperimentManifest
from app.services.environment_replay_snapshot import canonical_hash
from app.services.response_cohort_storage_contract import build_cohort_record_payload
from app.services.response_experiment_contract import (
    build_response_experiment_manifest as build,
    check_response_experiment_manifest as check,
)

completed, chronological, environment, sources = _completed, _chronological, _environment, _sources


@pytest.fixture
def archive(completed):
    env, index = completed
    return build_cohort_record_payload(env.request, index, owner_id=env.user.id)


def envelope(archive):
    return {
        "record_hash": archive["record_hash"],
        "cohort_index_hash": archive["cohort_index_hash"],
        "request_manifest_hash": archive["request_manifest_hash"],
        "record_payload": deepcopy(archive),
        "source_evidence_verified": False,
        "current_source_evidence_verified": False,
    }


def rehash(payload):
    return ResponseExperimentManifest.model_validate(payload).committed_payload()


def test_real_assembler_record_binds_plan_without_new_source_or_science_claims(archive, completed):
    env, _ = completed
    before, calls, commits = scientific_state(env), env.provider.await_count, env.db.commit_count
    original = deepcopy(archive)
    payload = build(archive, experiment_id="retrospective-motion-weather")
    result = check(payload, envelope(archive))
    assert result["status"] == "LOCALLY_VALID_RESPONSE_EXPERIMENT_CONTRACT"
    assert result["contract_archive_binding_verified"] is True
    assert result["payload_integrity_verified"] is True
    assert result["requested_split_counts"] == {"TRAIN": 1, "VALIDATION": 1, "TEST": 1}
    assert result["embedded_historical_chronological_order_claim"] is True
    assert result["embedded_historical_chronological_split_claim"] is True
    for name in (
        "source_evidence_verified",
        "current_source_evidence_verified",
        "owner_authorization_verified",
        "database_record_persisted",
        "chronological_cohort_order_verified",
        "chronological_split_verified",
        "split_assignment_persisted",
        "declared_modality_verified",
        "model_input_arrays_checked",
        "row_level_history_coverage_verified",
        "fitted_preprocessing_performed",
        "missing_values_imputed",
        "model_fit_performed",
        "pft_data_used",
        "personal_baseline_temporal_availability_verified",
        "fixed_hr_shift_applied",
        "training_authorized",
        "numeric_output_authorized",
        "pre_exercise_prediction_authorized",
        "causal_prediction_authorized",
    ):
        assert result[name] is False
    assert result["physiological_lag_ms"] is result["model_input_row_count"] is None
    assert result["polar_provider_calls"] == result["environmental_provider_calls"] == 0
    assert result["database_storage_writes"] == 0
    assert "SINGLE_TRAIN_SESSION" in result["limitations"]
    assert payload["target"]["hr_derived_predictors_used"] is False
    assert archive == original and scientific_state(env) == before
    assert env.provider.await_count == calls and env.db.commit_count == commits


def test_members_features_and_windows_have_stable_canonical_identity(archive):
    payload = build(archive, experiment_id="stable")
    changed = deepcopy(payload)
    changed["members"].reverse()
    changed["inputs"]["environment_features"].reverse()
    changed["temporal"]["lookback_windows_ms"].reverse()
    changed["evaluation"]["requested_metrics"].reverse()
    assert rehash(changed) == payload
    assert check(changed, archive) == check(payload, archive)
    assert build(envelope(archive), experiment_id="stable") == payload


def test_explicit_new_lookback_changes_plan_hash_not_export_clock_or_archive(archive):
    first = build(archive, experiment_id="history", lookback_windows_ms=[30_000])
    second = build(archive, experiment_id="history", lookback_windows_ms=[60_000])
    assert first["experiment_manifest_hash"] != second["experiment_manifest_hash"]
    assert first["cohort"] == second["cohort"]
    assert check(first, archive)["physiological_lag_ms"] is None
    assert check(second, archive)["fixed_hr_shift_applied"] is False


@pytest.mark.parametrize("field", ["record_hash", "cohort_index_hash", "request_manifest_hash"])
def test_rehashed_wrong_archive_pin_rejected(archive, field):
    payload = build(archive, experiment_id="pin")
    payload["cohort"][field] = "f" * 64
    with pytest.raises(ValueError, match="EXPERIMENT_COHORT_PIN_MISMATCH"):
        check(rehash(payload), archive)


def test_valid_hash_cannot_reassign_archived_whole_session_split(archive):
    payload = build(archive, experiment_id="split")
    train = next(m for m in payload["members"] if m["split"] == "TRAIN")
    test = next(m for m in payload["members"] if m["split"] == "TEST")
    train["split"], test["split"] = test["split"], train["split"]
    with pytest.raises(ValueError, match="MEMBERSHIP_OR_SPLIT_MISMATCH"):
        check(rehash(payload), archive)


def test_edited_plan_requires_new_commitment(archive):
    payload = build(archive, experiment_id="hash")
    payload["experiment_id"] = "changed"
    with pytest.raises(ValueError, match="EXPERIMENT_HASH_MISMATCH"):
        check(payload, archive)


@pytest.mark.parametrize(
    "section,field,value",
    [
        ("inputs", "workload_features", ["recorded_hr_bpm"]),
        ("inputs", "workload_features", ["HR_P2_MEDIAN"]),
        ("inputs", "environment_features", ["readiness_pct"]),
        ("inputs", "missing_value_imputation", "ZERO_FILL"),
        ("inputs", "withheld_values_promoted", True),
        ("target", "label_used_as_predictor", True),
        ("target", "hr_derived_predictors_used", True),
        ("target", "physiological_ground_truth_claimed", True),
        ("context", "declared_modality", "KAYAK_ERG"),
        ("context", "sensor_identity_or_quality_promoted", True),
        ("temporal", "fixed_hr_shift_applied", True),
        ("temporal", "physiological_lag_ms", 1663),
        ("temporal", "future_workload_used", True),
        ("temporal", "history_scope", "ALL_SESSIONS"),
        ("temporal", "history_coverage", "ZERO_PAD"),
        ("temporal", "initial_physiological_state", "RESTED"),
        ("temporal", "sequence_boundaries_preserved", False),
        ("evaluation", "fitted_preprocessing_scope", "ALL_SPLITS"),
        ("evaluation", "data_driven_feature_selection_scope", "TEST"),
        ("evaluation", "test_role", "MODEL_SELECTION_ONLY"),
        ("evaluation", "independence_between_sessions_claimed", True),
        ("pft", "pft_features_used", True),
        ("pft", "fitness_or_fatigue_targets_used", True),
        ("pft", "readiness_score_computed", True),
        ("pft", "future_baseline_cutoff", "INCLUDE_TARGET_SESSION"),
        ("pft", "future_baseline_update_order", "UPDATE_THEN_COMPARE"),
    ],
)
def test_leakage_and_scientific_scope_changes_rejected_even_before_hash(
    archive, section, field, value
):
    payload = build(archive, experiment_id="negative")
    payload[section][field] = value
    with pytest.raises(ValidationError):
        check(payload, archive)


@pytest.mark.parametrize("value", [0, 0.0, "false", None])
def test_false_policy_does_not_accept_boolean_aliases(archive, value):
    payload = build(archive, experiment_id="types")
    payload["temporal"]["fixed_hr_shift_applied"] = value
    with pytest.raises(ValidationError):
        check(payload, archive)


@pytest.mark.parametrize(
    "windows",
    [[], [0], [-1], [True], [30_000.0], ["30000"], [30_000, 30_000], [600_001], list(range(1, 10))],
)
def test_invalid_history_windows_rejected(archive, windows):
    with pytest.raises(ValidationError):
        build(archive, experiment_id="windows", lookback_windows_ms=windows)


def test_partition_identity_and_duplicate_feature_failures(archive):
    base = build(archive, experiment_id="groups")
    for change in (
        lambda p: p["members"].append(deepcopy(p["members"][0])),
        lambda p: p["members"].pop(),
        lambda p: p["inputs"]["workload_features"].append("gps_ground_speed_mps"),
        lambda p: p["inputs"]["environment_features"].append("air_temperature_c"),
        lambda p: p.update(training_authorized=True),
    ):
        payload = deepcopy(base)
        change(payload)
        with pytest.raises(ValidationError):
            check(payload, archive)


def test_train_support_cannot_be_borrowed_from_validation_or_test(archive):
    changed = deepcopy(archive["cohort_index"])
    feature = "water_level_cm"
    for member in changed["members"]:
        status = "WITHHELD" if member["requested_split"]["split"] == "TRAIN" else "AVAILABLE"
        member["feature_status_counts"][feature] = {status: member["counts"]["observation_count"]}
    changed["cohort_index_hash"] = canonical_hash(
        {key: value for key, value in changed.items() if key != "cohort_index_hash"}
    )
    record = build_cohort_record_payload(
        archive["request_manifest"], changed, owner_id=archive["owner_id"]
    )
    with pytest.raises(ValueError, match="SELECTED_FEATURE_UNOBSERVED_IN_TRAIN"):
        build(record, experiment_id="no-hydro-support", environment_features=[feature])
    result = check(build(record, experiment_id="motion-only", environment_features=[]), record)
    assert result["selected_train_environment_status_counts"] == {}


def test_summary_bad_envelope_and_corrupt_record_cannot_be_source_reference(archive):
    payload = build(archive, experiment_id="archive")
    inputs = [{"record_payload": None}, {"cohort_index": archive["cohort_index"]}]
    mismatched = envelope(archive)
    mismatched["record_hash"] = "f" * 64
    inputs.append(mismatched)
    corrupted = deepcopy(archive)
    corrupted["cohort_index"]["members"][0]["counts"]["hr_slot_count"] += 1
    inputs.append(corrupted)
    for value in inputs:
        with pytest.raises((ValueError, ValidationError)):
            check(payload, value)


def test_envelope_historical_or_current_claims_are_never_promoted(archive):
    wrapped = envelope(archive)
    wrapped["current_source_evidence_verified"] = True
    wrapped["source_evidence_verified"] = True
    result = check(build(wrapped, experiment_id="scope"), wrapped)
    assert result["source_evidence_verified"] is False
    assert result["current_source_evidence_verified"] is False


def test_single_session_archive_cannot_prepare_complete_experiment(completed):
    # Exercise the actual C assembler and E/1 record constructor for limited archives.
    import asyncio

    from app.services.response_cohort_assembly import assemble_response_cohort

    env, _ = completed
    request = deepcopy(env.request)
    request["members"] = request["members"][:1]
    request["split_manifest"] = None
    index = asyncio.run(
        assemble_response_cohort(env.db, request, user_id=env.user.id, verify_chronology=True)
    )
    record = build_cohort_record_payload(request, index, owner_id=env.user.id)
    with pytest.raises(ValueError, match="COMPLETE_ARCHIVED_CHRONOLOGICAL_SPLIT_REQUIRED"):
        build(record, experiment_id="limited")
