"""Pure local experiment/archive binding; does not materialize or fit model data."""

from collections import Counter
from copy import deepcopy

from app.schemas.response_experiment import ResponseExperimentManifest
from app.services.response_cohort_storage_contract import (
    MAX_RECORD_BYTES,
    check_cohort_record_payload,
)
from app.services.response_dataset_integrity import require_json_size

MAX_EXPERIMENT_BYTES = 64 * 1024
CHECK_SCOPE = "LOCAL_EXPERIMENT_POLICY_AND_ARCHIVED_PAYLOAD_BINDING_ONLY"


def _require(condition, code):
    if not condition:
        raise ValueError(code)


def extract_cohort_record(archive):
    """Accept an E/1 record or a full E/3 archive, never a summary or local index."""
    _require(isinstance(archive, dict), "EXPERIMENT_FULL_COHORT_RECORD_REQUIRED")
    require_json_size(archive, MAX_RECORD_BYTES + 1024 * 1024, "EXPERIMENT_ARCHIVE_SIZE_LIMIT")
    if "record_payload" in archive:
        record = archive["record_payload"]
        _require(isinstance(record, dict), "EXPERIMENT_FULL_COHORT_RECORD_REQUIRED")
        for key in ("record_hash", "cohort_index_hash", "request_manifest_hash"):
            _require(archive.get(key) == record.get(key), "EXPERIMENT_ARCHIVE_ENVELOPE_MISMATCH")
    else:
        record = archive
    check_cohort_record_payload(record)
    return record


def _reference(record):
    return {
        key: record[key]
        for key in (
            "record_schema_version",
            "record_hash",
            "cohort_index_hash",
            "request_manifest_hash",
            "owner_id",
        )
    }


def _members(record):
    return [
        {
            "provider": member["provider"],
            "athlete_id": member["athlete_id"],
            "session_external_id": member["session_external_id"],
            "split": member["requested_split"]["split"],
        }
        for member in record["cohort_index"]["members"]
    ]


def _complete_archived_split(record):
    index = record["cohort_index"]
    audit = index["temporal_audit"]
    _require(
        index["chronological_cohort_order_verified"] is True
        and index["chronological_split_verified"] is True
        and audit["chronological_order_supported"] is True
        and audit["chronological_split_supported"] is True
        and not audit["chronology_blocking_reasons"]
        and not audit["split_blocking_reasons"],
        "EXPERIMENT_COMPLETE_ARCHIVED_CHRONOLOGICAL_SPLIT_REQUIRED",
    )
    _require(not audit["possible_duplicate_pairs"], "EXPERIMENT_ARCHIVED_DUPLICATE_FLAGGED")


def build_response_experiment_manifest(
    archive,
    *,
    experiment_id,
    workload_features=None,
    environment_features=None,
    lookback_windows_ms=None,
):
    """Commit an explicit plan; the defaults are engineering choices, not fitted lag."""
    record = extract_cohort_record(archive)
    _complete_archived_split(record)
    inputs, temporal = {}, {}
    if workload_features is not None:
        inputs["workload_features"] = workload_features
    if environment_features is not None:
        inputs["environment_features"] = environment_features
    if lookback_windows_ms is not None:
        temporal["lookback_windows_ms"] = lookback_windows_ms
    model = ResponseExperimentManifest.model_validate(
        {
            "schema_version": "0.1",
            "experiment_id": experiment_id,
            "cohort": _reference(record),
            "members": _members(record),
            "inputs": inputs,
            "temporal": temporal,
            "experiment_manifest_hash": "0" * 64,
        }
    )
    payload = model.committed_payload()
    check_response_experiment_manifest(payload, archive)
    return payload


def check_response_experiment_manifest(payload, archive):
    """Verify local structure, commitment and binding; historical claims stay historical."""
    require_json_size(payload, MAX_EXPERIMENT_BYTES, "EXPERIMENT_MANIFEST_SIZE_LIMIT")
    model = ResponseExperimentManifest.model_validate(payload)
    _require(model.experiment_manifest_hash == model.computed_hash(), "EXPERIMENT_HASH_MISMATCH")
    record = extract_cohort_record(archive)
    _complete_archived_split(record)
    _require(
        model.cohort.model_dump(mode="json") == _reference(record), "EXPERIMENT_COHORT_PIN_MISMATCH"
    )
    expected_members = sorted(
        _members(record), key=lambda m: (m["provider"], m["athlete_id"], m["session_external_id"])
    )
    _require(
        model.canonical_body()["members"] == expected_members,
        "EXPERIMENT_ARCHIVED_MEMBERSHIP_OR_SPLIT_MISMATCH",
    )
    index = record["cohort_index"]
    train_members = [m for m in index["members"] if m["requested_split"]["split"] == "TRAIN"]
    train_support = {}
    for feature in model.inputs.environment_features:
        counts = Counter()
        for member in train_members:
            counts.update(member["feature_status_counts"][feature])
        _require(counts.get("AVAILABLE", 0) > 0, "EXPERIMENT_SELECTED_FEATURE_UNOBSERVED_IN_TRAIN")
        train_support[feature] = dict(sorted(counts.items()))
    split_counts = dict(sorted(Counter(m.split for m in model.members).items()))
    limitations = [
        "ROW_LEVEL_INPUT_AND_HISTORY_COVERAGE_NOT_CHECKED",
        "PREPARATION_CANDIDATES_ARE_NOT_MODEL_INPUT_ROWS",
        "RECORDED_SENSOR_HR_QUALITY_NOT_ESTABLISHED",
        "DECLARED_MODALITY_NOT_INDEPENDENTLY_VERIFIED",
        "GPS_MOTION_IS_NOT_MEASURED_MECHANICAL_POWER",
        "PHYSIOLOGICAL_LAG_NOT_ESTIMATED",
        "INDEPENDENCE_BETWEEN_SESSIONS_NOT_ESTABLISHED",
        "PFT_DATA_AND_PERSONAL_BASELINE_NOT_INCLUDED",
        "NO_MODEL_FIT_OR_EVALUATION_PERFORMED",
    ]
    if split_counts["TRAIN"] == 1:
        limitations.append("SINGLE_TRAIN_SESSION")
    return {
        "status": "LOCALLY_VALID_RESPONSE_EXPERIMENT_CONTRACT",
        "schema_version": model.schema_version,
        "experiment_id": model.experiment_id,
        "experiment_manifest_hash": model.computed_hash(),
        "cohort_record_hash": record["record_hash"],
        "cohort_index_hash": record["cohort_index_hash"],
        "request_manifest_hash": record["request_manifest_hash"],
        "member_count": len(model.members),
        "requested_split_counts": split_counts,
        "archived_counts": deepcopy(index["totals"]),
        "selected_train_environment_status_counts": dict(sorted(train_support.items())),
        "claim_scope": CHECK_SCOPE,
        "payload_integrity_verified": True,
        "contract_archive_binding_verified": True,
        "declared_policy_consistency_verified": True,
        "embedded_historical_chronological_order_claim": index[
            "chronological_cohort_order_verified"
        ],
        "embedded_historical_chronological_split_claim": index["chronological_split_verified"],
        "source_evidence_verified": False,
        "current_source_evidence_verified": False,
        "owner_authorization_verified": False,
        "database_record_persisted": False,
        "chronological_cohort_order_verified": False,
        "chronological_split_verified": False,
        "split_assignment_persisted": False,
        "declared_modality_verified": False,
        "model_input_arrays_checked": False,
        "row_level_history_coverage_verified": False,
        "model_input_row_count": None,
        "fitted_preprocessing_performed": False,
        "missing_values_imputed": False,
        "model_fit_performed": False,
        "pft_data_used": False,
        "personal_baseline_temporal_availability_verified": False,
        "fixed_hr_shift_applied": False,
        "physiological_lag_ms": None,
        "training_authorized": False,
        "numeric_output_authorized": False,
        "pre_exercise_prediction_authorized": False,
        "causal_prediction_authorized": False,
        "polar_provider_calls": 0,
        "environmental_provider_calls": 0,
        "database_storage_writes": 0,
        "limitations": limitations,
    }
