"""Deterministic local, archived-contract-bound interval inputs; no model fitting.

Predictors are shared observed interval arrays. History windows reference those
arrays and clip only interval support, never interpolate values or move HR.
Reconstruction checks local bytes and policy, not current sources or ownership.
"""

import math
from bisect import bisect_right
from collections import Counter
from copy import deepcopy

from app.schemas.response_experiment import ResponseExperimentManifest
from app.services.environment_replay_snapshot import canonical_hash
from app.services.response_dataset_integrity import (
    check_response_dataset_integrity,
    require_json_size,
)
from app.services.response_experiment_contract import (
    check_response_experiment_manifest,
    extract_cohort_record,
)
from app.services.route_response_dataset import FEATURES

INPUT_VERSION = "0.1.0"
CHECK_SCOPE = "LOCAL_PINNED_PAYLOAD_AND_INTERVAL_INPUT_RECONSTRUCTION_ONLY"
MAX_INPUT_BYTES = 256 * 1024 * 1024
MAX_TOTAL_OBSERVATIONS = 200_000
MAX_TOTAL_HR_SLOTS = 400_000
MASKS = {"AVAILABLE", "MISSING", "WITHHELD", "NOT_APPLICABLE"}
WORKLOAD_UNITS = {
    "gps_ground_speed_mps": "m/s",
    "ground_speed_change_from_previous_mps": "m/s",
    "ground_speed_change_rate_mps2": "m/s2",
    "absolute_bearing_change_from_previous_deg": "deg",
}


def _require(condition, code):
    if not condition:
        raise ValueError(code)


def _finite(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _identity(value):
    return value["athlete_id"], value["session_external_id"]


def _hash_package(value):
    return canonical_hash({k: v for k, v in value.items() if k != "input_package_hash"})


def check_member_dataset_binding(dataset, archived_member):
    """Check full unassigned replay bytes against historical pins, without promotion."""
    integrity = check_response_dataset_integrity(dataset)
    _require(
        _identity(dataset) == _identity(archived_member), "MODEL_INPUT_MEMBER_IDENTITY_MISMATCH"
    )
    _require(
        dataset["package_hash"] == archived_member["unassigned_replay_package_hash"],
        "MODEL_INPUT_REPLAY_PACKAGE_PIN_MISMATCH",
    )
    _require(
        dataset["status"] == "OBSERVATION_PACKAGE_WITH_LIMITATIONS"
        and not dataset["blocking_reasons"],
        "MODEL_INPUT_SOURCE_PACKAGE_WITHHELD",
    )
    _require(
        dataset["split_assignment"]["status"] == "UNASSIGNED"
        and dataset["split_assignment"]["split"] is None,
        "MODEL_INPUT_UNASSIGNED_REPLAY_REQUIRED",
    )
    evidence = dataset["replay_evidence"]
    for source, pin in (
        ("snapshot_id", "replay_snapshot_id"),
        ("snapshot_hash", "snapshot_hash"),
        ("evidence_set_id", "evidence_set_id"),
        ("evidence_hash", "evidence_hash"),
    ):
        _require(
            evidence[source] == archived_member[pin], "MODEL_INPUT_REPLAY_EVIDENCE_PIN_MISMATCH"
        )
    _require(
        evidence["status"] == "VERIFIED_SAVED_ENVIRONMENT_REPLAY"
        and type(evidence["environmental_provider_calls"]) is int
        and evidence["environmental_provider_calls"] == 0
        and type(evidence["replay_storage_writes"]) is int
        and evidence["replay_storage_writes"] == 0,
        "MODEL_INPUT_UNEXPECTED_REPLAY_EXECUTION",
    )
    _require(
        {key: dataset[key] for key in archived_member["counts"]} == archived_member["counts"]
        and dataset["feature_status_counts"] == archived_member["feature_status_counts"]
        and integrity["hr_window_status_counts"] == archived_member["hr_window_status_counts"],
        "MODEL_INPUT_ARCHIVED_COUNTS_MISMATCH",
    )
    return integrity


def _columns(contract):
    return [
        {"name": name, "source": "workload", "unit": WORKLOAD_UNITS[name]}
        for name in contract["inputs"]["workload_features"]
    ] + [
        {"name": name, "source": "environment", "unit": FEATURES[name][2]}
        for name in contract["inputs"]["environment_features"]
    ]


def _values(row, columns):
    values, masks = [], []
    for column in columns:
        name = column["name"]
        if column["source"] == "workload":
            value = row["workload_observation"].get(name)
            mask = (
                "WITHHELD"
                if row["workload_available"] is not True
                else "AVAILABLE"
                if _finite(value)
                else "MISSING"
            )
        else:
            feature = row["environment_features"][name]
            value, mask = feature["value"], feature["status"]
            _require(
                mask in MASKS
                and feature["unit"] == column["unit"]
                and feature["available"] is (mask == "AVAILABLE"),
                "MODEL_INPUT_FEATURE_MASK_OR_UNIT_INVALID",
            )
        _require(mask != "AVAILABLE" or _finite(value), "MODEL_INPUT_AVAILABLE_VALUE_NOT_FINITE")
        values.append(value if mask == "AVAILABLE" else None)
        masks.append(mask)
    return values, masks


def _sequence_index(dataset):
    """Recheck the temporal support actually consumed by the new arrays."""
    sequences = {}
    previous_by_route = {}
    previous_end_by_route = {}
    for index, row in enumerate(dataset["observations"]):
        key = (row["route_index"], row["exercise_index"])
        start, stop = row["start_exercise_elapsed_ms"], row["end_exercise_elapsed_ms"]
        _require(
            all(v is None or type(v) is int for v in (start, stop)),
            "MODEL_INPUT_INTERVAL_TYPE_INVALID",
        )
        sequence = row["history_ref"]["sequence_index"]
        if sequence is None:
            previous_by_route[key] = None
            continue
        _require(
            start is not None
            and stop is not None
            and start >= 0
            and stop > start
            and row["workload_available"] is True,
            "MODEL_INPUT_SEQUENCE_SUPPORT_INVALID",
        )
        workload, temporal = row["workload_observation"], row["temporal_context"]
        _require(
            workload["start_exercise_elapsed_ms"] == start
            and workload["end_exercise_elapsed_ms"] == stop
            and (
                "interval_ms" not in workload
                or type(workload["interval_ms"]) is int
                and workload["interval_ms"] == stop - start
            )
            and temporal["current_workload_available_not_before_exercise_elapsed_ms"] == stop,
            "MODEL_INPUT_WORKLOAD_TIME_BINDING_INVALID",
        )
        last_end = previous_end_by_route.get(key)
        _require(last_end is None or start >= last_end, "MODEL_INPUT_INTERVALS_OVERLAP_OR_REVERSE")
        previous_end_by_route[key] = stop
        seq_key = (*key, sequence)
        run = sequences.setdefault(seq_key, [])
        _require(temporal["sequence_position"] == len(run), "MODEL_INPUT_SEQUENCE_POSITION_INVALID")
        if run:
            previous = previous_by_route.get(key)
            _require(
                previous is not None
                and previous["history_ref"]["sequence_index"] == sequence
                and previous["end_exercise_elapsed_ms"] == start
                and previous["order_index"] + 1 == row["order_index"]
                and workload.get("source_contiguous_with_previous") is not False
                and run[-1] + 1 == index,
                "MODEL_INPUT_SEQUENCE_BOUNDARY_INVALID",
            )
        run.append(index)
        previous_by_route[key] = row
    return sequences


def _history(row, index, sequence, lookbacks, columns):
    if sequence is None:
        return [
            {
                "lookback_ms": width,
                "status": "NO_SUPPORTED_SEQUENCE",
                "window_ref": None,
                "unavailable_features": [],
            }
            for width in lookbacks
        ]
    starts, stops, indices, bad_prefixes = sequence
    end = row["end_exercise_elapsed_ms"]
    results = []
    for width in lookbacks:
        start = end - width
        if start < starts[0]:
            results.append(
                {
                    "lookback_ms": width,
                    "status": "LEFT_CENSORED_HISTORY",
                    "window_ref": None,
                    "unavailable_features": [],
                }
            )
            continue
        first = bisect_right(stops, start)
        # Every interval in this range intersects [start, end). End is the target
        # interval's stop, so later rows are present in the table but never referenced.
        count = index - indices[0] + 1
        unavailable = [
            columns[c]["name"]
            for c, prefix in enumerate(bad_prefixes)
            if prefix[count] - prefix[first]
        ]
        ref = {
            "lookback_ms": width,
            "start_exercise_elapsed_ms": start,
            "stop_exercise_elapsed_ms": end,
            "first_input_row_index_inclusive": indices[first],
            "stop_input_row_index_exclusive": index + 1,
            "first_interval_clip_ms": start - starts[first],
            "covered_duration_ms": width,
            "window_semantics": "HALF_OPEN_START_INCLUSIVE_END_EXCLUSIVE",
        }
        results.append(
            {
                "lookback_ms": width,
                "status": "SELECTED_INPUT_MASKED" if unavailable else "COMPLETE",
                "window_ref": ref,
                "unavailable_features": unavailable,
            }
        )
    return results


def _materialize_member(dataset, archived_member, columns, lookbacks):
    rows = dataset["observations"]
    arrays = {
        name: []
        for name in (
            "source_row_ids",
            "route_indices",
            "exercise_indices",
            "order_indices",
            "sequence_indices",
            "start_exercise_elapsed_ms",
            "stop_exercise_elapsed_ms",
            "values",
            "masks",
        )
    }
    status_counts = {c["name"]: Counter() for c in columns}
    for row in rows:
        values, masks = _values(row, columns)
        for name, value in (
            ("source_row_ids", row["row_id"]),
            ("route_indices", row["route_index"]),
            ("exercise_indices", row["exercise_index"]),
            ("order_indices", row["order_index"]),
            ("sequence_indices", row["history_ref"]["sequence_index"]),
            ("start_exercise_elapsed_ms", row["start_exercise_elapsed_ms"]),
            ("stop_exercise_elapsed_ms", row["end_exercise_elapsed_ms"]),
            ("values", values),
            ("masks", masks),
        ):
            arrays[name].append(value)
        for column, mask in zip(columns, masks):
            status_counts[column["name"]][mask] += 1
    sequences = {}
    for key, indices in _sequence_index(dataset).items():
        prefixes = [[0] for _ in columns]
        for index in indices:
            for c, prefix in enumerate(prefixes):
                prefix.append(prefix[-1] + (arrays["masks"][index][c] != "AVAILABLE"))
        sequences[key] = (
            [rows[i]["start_exercise_elapsed_ms"] for i in indices],
            [rows[i]["end_exercise_elapsed_ms"] for i in indices],
            indices,
            prefixes,
        )
    streams = {s["stream_id"]: s for s in dataset["hr_streams"]}
    targets, row_audit = [], []
    exclusion_counts = Counter()
    history_status_counts = {str(w): Counter() for w in lookbacks}
    for index, row in enumerate(rows):
        seq_key = (row["route_index"], row["exercise_index"], row["history_ref"]["sequence_index"])
        history = _history(row, index, sequences.get(seq_key), lookbacks, columns)
        reasons = []
        if row["preparation_candidate"] is not True or row["exclusion_reasons"]:
            reasons.append("SOURCE_PREPARATION_CANDIDATE_UNAVAILABLE")
        if row["hr_label_ref"]["status"] != "COMPLETE":
            reasons.append("COMPLETE_HR_LABEL_REQUIRED")
        for window in history:
            history_status_counts[str(window["lookback_ms"])][window["status"]] += 1
            if window["status"] != "COMPLETE":
                reasons.append(window["status"])
        reasons = sorted(set(reasons))
        target_index = None
        if not reasons:
            label = row["hr_label_ref"]
            stream = streams[label["stream_id"]]
            _require(
                stream["time_mapping_verified"] is True, "MODEL_INPUT_VERIFIED_EXPORT_GRID_REQUIRED"
            )
            first, stop = label["grid_start_index_inclusive"], label["grid_stop_index_exclusive"]
            try:
                target = math.fsum(s["value_bpm"] for s in stream["samples"][first:stop]) / (
                    stop - first
                )
            except (OverflowError, ZeroDivisionError) as exc:
                raise ValueError("MODEL_INPUT_TARGET_AGGREGATION_NOT_FINITE") from exc
            _require(_finite(target) and target > 0, "MODEL_INPUT_TARGET_AGGREGATION_NOT_FINITE")
            target_index = len(targets)
            targets.append(
                {
                    "input_row_index": index,
                    "source_row_id": row["row_id"],
                    "recorded_hr_mean_bpm": target,
                    "hr_label_ref": deepcopy(label),
                    "history_windows": [h["window_ref"] for h in history],
                }
            )
        exclusion_counts.update(reasons)
        row_audit.append(
            {
                "input_row_index": index,
                "source_row_id": row["row_id"],
                "eligible_for_experiment_input": not reasons,
                "target_index": target_index,
                "hr_label_status": row["hr_label_ref"]["status"],
                "source_preparation_candidate": row["preparation_candidate"],
                "source_exclusion_reasons": deepcopy(row["exclusion_reasons"]),
                "exclusion_reasons": reasons,
                "history_checks": history,
            }
        )
    return {
        "provider": "POLAR",
        "athlete_id": dataset["athlete_id"],
        "session_external_id": dataset["session_external_id"],
        "session_group_key": dataset["session_group_key"],
        "split": archived_member["requested_split"]["split"],
        "source_unassigned_replay_package_hash": dataset["package_hash"],
        "source_replay_snapshot_id": archived_member["replay_snapshot_id"],
        "source_snapshot_hash": archived_member["snapshot_hash"],
        "source_hr_proof_state_hash": archived_member["source_commitments"]["hr_proof_state_hash"],
        "source_counts": deepcopy(archived_member["counts"]),
        "input_arrays": arrays,
        "targets": targets,
        "row_audit": row_audit,
        "sequence_metadata": [
            {"route_index": r["route_index"], "exercise_index": r["exercise_index"], **deepcopy(s)}
            for r in dataset["routes"]
            for s in r["sequences"]
        ],
        "coverage": {
            "source_observation_count": len(rows),
            "model_input_row_count": len(targets),
            "excluded_observation_count": len(rows) - len(targets),
            "selected_feature_status_counts": {
                n: dict(sorted(c.items())) for n, c in status_counts.items()
            },
            "exclusion_reason_counts": dict(sorted(exclusion_counts.items())),
            "history_status_counts": {
                w: dict(sorted(c.items())) for w, c in history_status_counts.items()
            },
        },
    }


def build_response_model_input_package(manifest, archive, datasets):
    """Consume every exact pinned member or fail; excluded rows remain represented."""
    contract_check = check_response_experiment_manifest(manifest, archive)
    contract = ResponseExperimentManifest.model_validate(manifest).committed_payload()
    record = extract_cohort_record(archive)
    _require(isinstance(datasets, list), "MODEL_INPUT_DATASET_LIST_REQUIRED")
    expected_members = record["cohort_index"]["members"]
    _require(len(datasets) == len(expected_members), "MODEL_INPUT_EXACT_MEMBER_SET_REQUIRED")
    lookup = {}
    for dataset in datasets:
        identity = _identity(dataset)
        _require(identity not in lookup, "MODEL_INPUT_DUPLICATE_MEMBER")
        lookup[identity] = dataset
    _require(
        set(lookup) == {_identity(m) for m in expected_members},
        "MODEL_INPUT_EXACT_MEMBER_SET_REQUIRED",
    )
    _require(
        sum(d["observation_count"] for d in datasets) <= MAX_TOTAL_OBSERVATIONS
        and sum(d["hr_slot_count"] for d in datasets) <= MAX_TOTAL_HR_SLOTS,
        "MODEL_INPUT_COHORT_SIZE_LIMIT",
    )
    columns = _columns(contract)
    members = []
    for member in expected_members:
        dataset = lookup[_identity(member)]
        check_member_dataset_binding(dataset, member)
        members.append(
            _materialize_member(
                dataset, member, columns, contract["temporal"]["lookback_windows_ms"]
            )
        )
    per_split = {}
    for split in ("TRAIN", "VALIDATION", "TEST"):
        selected = [m for m in members if m["split"] == split]
        per_split[split] = {
            "member_count": len(selected),
            "source_observation_count": sum(
                m["coverage"]["source_observation_count"] for m in selected
            ),
            "model_input_row_count": sum(m["coverage"]["model_input_row_count"] for m in selected),
            "excluded_observation_count": sum(
                m["coverage"]["excluded_observation_count"] for m in selected
            ),
        }
    empty_splits = [s for s, c in per_split.items() if c["model_input_row_count"] == 0]
    limitations = [
        r
        for r in contract_check["limitations"]
        if r
        not in (
            "ROW_LEVEL_INPUT_AND_HISTORY_COVERAGE_NOT_CHECKED",
            "PREPARATION_CANDIDATES_ARE_NOT_MODEL_INPUT_ROWS",
        )
    ]
    if empty_splits:
        limitations.append("ONE_OR_MORE_PARTITIONS_HAVE_NO_COMPLETE_MODEL_INPUT_ROWS")
    package = {
        "schema_version": "0.1",
        "input_version": INPUT_VERSION,
        "status": "MODEL_INPUT_PACKAGE_WITH_LIMITATIONS"
        if not empty_splits
        else "MODEL_INPUT_PACKAGE_WITH_EMPTY_PARTITIONS",
        "experiment_manifest_hash": contract["experiment_manifest_hash"],
        "cohort_record_hash": record["record_hash"],
        "cohort_index_hash": record["cohort_index_hash"],
        "request_manifest_hash": record["request_manifest_hash"],
        "columns": columns,
        "lookback_windows_ms": contract["temporal"]["lookback_windows_ms"],
        "representation": "SHARED_OBSERVED_INTERVAL_ARRAYS_WITH_CLIPPED_WINDOW_REFERENCES",
        "members": members,
        "per_split_coverage": per_split,
        "empty_input_partitions": empty_splits,
        "totals": {
            "member_count": len(members),
            "source_observation_count": sum(
                c["source_observation_count"] for c in per_split.values()
            ),
            "source_hr_slot_count": sum(m["source_counts"]["hr_slot_count"] for m in members),
            "source_preparation_candidate_count": sum(
                m["source_counts"]["preparation_candidate_count"] for m in members
            ),
            "model_input_row_count": sum(c["model_input_row_count"] for c in per_split.values()),
            "excluded_observation_count": sum(
                c["excluded_observation_count"] for c in per_split.values()
            ),
        },
        "policy": {
            "history_anchor": "TARGET_WINDOW_END_RETROSPECTIVE_CONDITIONING",
            "window_semantics": "HALF_OPEN_START_INCLUSIVE_END_EXCLUSIVE",
            "all_source_observations_referenced": True,
            "unlabelled_workload_history_retained": True,
            "source_unassigned_replay_preserved": True,
            "raw_source_payloads_embedded": False,
            "raw_source_payloads_modified": False,
            "labels_in_predictor_arrays": False,
            "history_crosses_sequence_or_member_boundary": False,
            "future_workload_referenced": False,
            "rectangular_tensor_or_resampling_performed": False,
            "interval_clipping_role": "OBSERVATION_SUPPORT_ONLY_NOT_CONTINUOUS_PHYSICAL_TRAJECTORY",
            "fitted_preprocessing_scope": "TRAIN_ONLY",
            "fitted_preprocessing_performed": False,
            "missing_values_imputed": False,
            "withheld_values_promoted": False,
            "fixed_hr_shift_applied": False,
            "physiological_lag_ms": None,
            "initial_physiological_state": "UNKNOWN_RETAINED",
            "sensor_identity_or_quality_promoted": False,
            "pft_data_used": False,
            "model_fit_performed": False,
        },
        "claim_scope": CHECK_SCOPE,
        "source_evidence_verified": False,
        "current_source_evidence_verified": False,
        "owner_authorization_verified": False,
        "split_assignment_persisted": False,
        "training_authorized": False,
        "numeric_output_authorized": False,
        "pre_exercise_prediction_authorized": False,
        "causal_prediction_authorized": False,
        "polar_provider_calls": 0,
        "environmental_provider_calls": 0,
        "database_storage_writes": 0,
        "execution_limits": {
            "max_input_bytes": MAX_INPUT_BYTES,
            "max_total_observations": MAX_TOTAL_OBSERVATIONS,
            "max_total_hr_slots": MAX_TOTAL_HR_SLOTS,
        },
        "limitations": limitations,
    }
    package["input_package_hash"] = _hash_package(package)
    require_json_size(package, MAX_INPUT_BYTES, "MODEL_INPUT_PACKAGE_SIZE_LIMIT")
    return package


def check_response_model_input_package(package, manifest, archive, datasets):
    """Reconstruct all values, masks, target means and window refs from pinned inputs."""
    require_json_size(package, MAX_INPUT_BYTES, "MODEL_INPUT_PACKAGE_SIZE_LIMIT")
    _require(
        package.get("input_package_hash") == _hash_package(package),
        "MODEL_INPUT_PACKAGE_HASH_MISMATCH",
    )
    expected = build_response_model_input_package(manifest, archive, datasets)
    _require(
        package["input_package_hash"] == expected["input_package_hash"],
        "MODEL_INPUT_RECONSTRUCTION_MISMATCH",
    )
    return {
        "status": "LOCALLY_VERIFIED_RESPONSE_MODEL_INPUT_PACKAGE",
        "claim_scope": CHECK_SCOPE,
        "input_package_hash": expected["input_package_hash"],
        "experiment_manifest_hash": expected["experiment_manifest_hash"],
        "cohort_record_hash": expected["cohort_record_hash"],
        "cohort_index_hash": expected["cohort_index_hash"],
        "payload_integrity_verified": True,
        "contract_archive_binding_verified": True,
        "archived_replay_package_pins_verified": True,
        "model_input_arrays_checked": True,
        "row_level_history_coverage_verified": True,
        "reconstruction_verified": True,
        "source_observation_count": expected["totals"]["source_observation_count"],
        "model_input_row_count": expected["totals"]["model_input_row_count"],
        "excluded_observation_count": expected["totals"]["excluded_observation_count"],
        "per_split_coverage": deepcopy(expected["per_split_coverage"]),
        "empty_input_partitions": expected["empty_input_partitions"],
        "source_evidence_verified": False,
        "current_source_evidence_verified": False,
        "owner_authorization_verified": False,
        "database_record_persisted": False,
        "split_assignment_persisted": False,
        "fitted_preprocessing_performed": False,
        "missing_values_imputed": False,
        "model_fit_performed": False,
        "pft_data_used": False,
        "fixed_hr_shift_applied": False,
        "physiological_lag_ms": None,
        "training_authorized": False,
        "numeric_output_authorized": False,
        "pre_exercise_prediction_authorized": False,
        "causal_prediction_authorized": False,
        "polar_provider_calls": 0,
        "environmental_provider_calls": 0,
        "database_storage_writes": 0,
    }
