"""Full replay payload integrity and references; never proof of source or quality."""

import json
import math
from collections import Counter
from datetime import datetime, timedelta

from app.services.environment_replay_snapshot import canonical_hash
from app.services.response_dataset_split import session_group_key

MAX_DATASET_BYTES = 64 * 1024 * 1024
MAX_OBSERVATIONS = 100_000
MAX_HR_SLOTS = 200_000
MAX_ROUTES = 256


def require(condition, code="DATASET_INTERNAL_REFERENCES_INVALID"):
    if not condition:
        raise ValueError(code)


def require_json_size(value, limit, code):
    """Bound serialized input without allocating another complete JSON string."""
    size = 0
    encoder = json.JSONEncoder(sort_keys=True, separators=(",", ":"), allow_nan=False)
    for chunk in encoder.iterencode(value):
        size += len(chunk.encode("utf-8"))
        require(size <= limit, code)
    return size


def _utc(value):
    parsed = datetime.fromisoformat(value)
    require(parsed.tzinfo is not None and parsed.utcoffset() == timedelta(0))
    return parsed


def _positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def _check(dataset):
    require(dataset.get("payload_included") is True, "DATASET_FULL_PAYLOAD_REQUIRED")
    require(dataset.get("dataset_version") == "0.1.0", "DATASET_VERSION_UNSUPPORTED")
    rows, streams, routes = dataset["observations"], dataset["hr_streams"], dataset["routes"]
    require(isinstance(rows, list) and isinstance(streams, list) and isinstance(routes, list))
    require(
        len(rows) <= MAX_OBSERVATIONS and len(routes) <= MAX_ROUTES, "DATASET_EXECUTION_SIZE_LIMIT"
    )
    require(all(type(s["slot_count"]) is int and s["slot_count"] >= 0 for s in streams))
    require(sum(s["slot_count"] for s in streams) <= MAX_HR_SLOTS, "DATASET_EXECUTION_SIZE_LIMIT")
    require_json_size(dataset, MAX_DATASET_BYTES, "DATASET_EXECUTION_SIZE_LIMIT")
    require(
        dataset["package_hash"]
        == canonical_hash({k: v for k, v in dataset.items() if k != "package_hash"}),
        "DATASET_PAYLOAD_HASH_MISMATCH",
    )
    for name in (
        "training_authorized",
        "numeric_output_authorized",
        "pre_exercise_prediction_authorized",
        "causal_prediction_authorized",
    ):
        require(dataset[name] is False, "DATASET_UNEXPECTED_AUTHORIZATION")
    policy = dataset["policy"]
    for name in (
        "fixed_hr_shift_applied",
        "feature_fit_performed",
        "feature_missing_values_imputed",
        "target_hr_used_as_predictor",
        "missing_workload_or_hr_interpolated",
        "post_recording_recovery_extrapolated",
        "current_velocity_estimated",
        "boat_through_water_speed_estimated",
    ):
        require(policy[name] is False, "DATASET_UNEXPECTED_TRANSFORMATION")
    require(policy["physiological_lag_ms"] is None, "DATASET_UNEXPECTED_TRANSFORMATION")
    group = dataset["session_group_key"]
    require(group == session_group_key(dataset["athlete_id"], dataset["session_external_id"]))
    split = dataset["split_assignment"]["split"]
    require(dataset["split_assignment"]["session_group_key"] == group)
    require(len(rows) == dataset["observation_count"] and len(routes) == dataset["route_count"])
    require(len(streams) == dataset["hr_stream_count"])
    require(sum(s["slot_count"] for s in streams) == dataset["hr_slot_count"])
    require(
        sum(r["preparation_candidate"] is True for r in rows)
        == dataset["preparation_candidate_count"]
    )
    require(
        dataset["excluded_observation_count"] == len(rows) - dataset["preparation_candidate_count"]
    )
    require(dataset["source_observation_count"] == len(rows))
    route_lookup = {(r["route_index"], r["exercise_index"]): r for r in routes}
    require(len(route_lookup) == len(routes))
    ids = {s["stream_id"]: s for s in streams}
    require(len(ids) == len(streams))
    prefixes = {}
    for stream in streams:
        require(stream["session_group_key"] == group and stream["split"] == split)
        require(type(stream["interval_us"]) is int and stream["interval_us"] > 0)
        require(len(stream["samples"]) == stream["slot_count"])
        linked = [r for r in routes if r["hr_stream_id"] == stream["stream_id"]]
        require(bool(linked))
        start = None
        if stream["time_mapping_verified"] is True:
            require(type(stream["sample_grid_origin_us"]) is int)
            starts = {_utc(r["exercise_start_utc"]) for r in linked}
            require(len(starts) == 1)
            start = next(iter(starts))
        else:
            require(
                stream["time_mapping_verified"] is False and stream["sample_grid_origin_us"] is None
            )
        prefix = [0]
        for index, slot in enumerate(stream["samples"]):
            require(type(slot["sample_index"]) is int and slot["sample_index"] == index)
            require(slot["positive_finite"] is _positive(slot["value_bpm"]))
            prefix.append(prefix[-1] + slot["positive_finite"])
            if start is not None:
                elapsed = stream["sample_grid_origin_us"] + index * stream["interval_us"]
                require(slot["exercise_elapsed_us"] == elapsed)
                require(
                    _utc(slot["mapped_timestamp_utc"]) == start + timedelta(microseconds=elapsed)
                )
            else:
                require(slot["exercise_elapsed_us"] is slot["mapped_timestamp_utc"] is None)
        require(prefix[-1] == stream["positive_finite_sample_count"])
        prefixes[stream["stream_id"]] = prefix
    by_route = {key: [] for key in route_lookup}
    row_ids = set()
    statuses = Counter()
    feature_counts = {name: Counter() for name in dataset["feature_status_counts"]}
    component_counts = {name: Counter() for name in dataset["component_status_counts"]}
    for row in rows:
        key = (row["route_index"], row["exercise_index"])
        require(key in by_route and row["row_id"] not in row_ids)
        row_ids.add(row["row_id"])
        require(row["row_id"] == canonical_hash([group, *key, row["order_index"]]))
        by_route[key].append(row)
        require(row["session_group_key"] == group and row["split"] == split)
        label, history = row["hr_label_ref"], row["history_ref"]
        require(history["route_index"] == key[0] and history["exercise_index"] == key[1])
        require(history["causal_predictor_history_selected"] is False)
        require(label["label_used_as_predictor"] is False)
        require(label["window_semantics"] == "HALF_OPEN_START_INCLUSIVE_END_EXCLUSIVE")
        require(label["stream_id"] == route_lookup[key]["hr_stream_id"])
        require(label["stream_id"] is None or label["stream_id"] in ids)
        require(set(row["environment_features"]) == set(feature_counts))
        require(set(row["environment_components"]) == set(component_counts))
        for name, feature in row["environment_features"].items():
            feature_counts[name][feature["status"]] += 1
            value = feature["value"]
            require(
                type(value) in (int, float) and math.isfinite(value)
                if feature["status"] == "AVAILABLE"
                else value is None
            )
        for name, component in row["environment_components"].items():
            component_counts[name][component["status"]] += 1
        first, stop = label["grid_start_index_inclusive"], label["grid_stop_index_exclusive"]
        if first is not None:
            stream = ids[label["stream_id"]]
            require(stream["time_mapping_verified"] is True)
            require(type(first) is type(stop) is int and 0 <= first <= stop)
            origin, interval = stream["sample_grid_origin_us"], stream["interval_us"]
            require(
                (first, stop)
                == tuple(
                    max(0, -(-(row[field] * 1000 - origin) // interval))
                    for field in ("start_exercise_elapsed_ms", "end_exercise_elapsed_ms")
                )
            )
            size = stream["slot_count"]
            recorded = max(0, min(stop, size) - min(first, size))
            positives = (
                prefixes[stream["stream_id"]][min(stop, size)]
                - prefixes[stream["stream_id"]][min(first, size)]
            )
            require(label["recorded_slot_count"] == recorded)
            require(label["expected_grid_slot_count"] == stop - first)
            require(label["unrecorded_grid_slot_count"] == stop - first - recorded)
            require(label["positive_finite_grid_sample_count"] == positives)
            require(label["missing_or_invalid_grid_slot_count"] == stop - first - positives)
            expected_status = (
                "COMPLETE"
                if stop > first and positives == stop - first
                else ("PARTIAL" if positives else "NO_SAMPLES")
            )
            require(label["status"] == expected_status)
        else:
            require(stop is None and label["recorded_slot_count"] == 0)
            require(label["status"] in {"INVALID_WINDOW", "TIME_MAPPING_UNAVAILABLE"})
            require(
                all(
                    label[field] is None
                    for field in (
                        "expected_grid_slot_count",
                        "unrecorded_grid_slot_count",
                        "positive_finite_grid_sample_count",
                        "missing_or_invalid_grid_slot_count",
                    )
                )
            )
        statuses[label["status"]] += 1
    for key, route_rows in by_route.items():
        route = route_lookup[key]
        orders = [r["order_index"] for r in route_rows]
        require(all(type(order) is int and order >= 0 for order in orders))
        require(orders == sorted(set(orders)))
        require(len(route_rows) == route["observation_count"])
        require(
            sum(r["preparation_candidate"] is True for r in route_rows)
            == route["preparation_candidate_count"]
        )
        if not any(r["hr_label_ref"]["status"] == "TIME_MAPPING_UNAVAILABLE" for r in route_rows):
            require(
                sum(r["hr_label_ref"]["status"] == "COMPLETE" for r in route_rows)
                == route["complete_hr_window_count"]
            )
        sequences = {}
        previous = None
        for row in route_rows:
            history, temporal = row["history_ref"], row["temporal_context"]
            index = history["sequence_index"]
            require(index == temporal["sequence_index"])
            if index is None:
                require(
                    history["first_order_index"] is history["completed_end_order_index"] is None
                )
                require(
                    history["includes_current_workload_for_retrospective_conditioning"] is False
                )
                previous = None
                continue
            require(type(index) is int and index >= 0)
            require(temporal["status"] == "OBSERVED_WORKLOAD_SEQUENCE")
            require(history["includes_current_workload_for_retrospective_conditioning"] is True)
            if index not in sequences:
                sequences[index] = []
                require(history["completed_end_order_index"] is None)
            else:
                require(previous is not None and previous["history_ref"]["sequence_index"] == index)
                require(history["completed_end_order_index"] == previous["order_index"])
                require(previous["end_exercise_elapsed_ms"] == row["start_exercise_elapsed_ms"])
            sequences[index].append(row)
            require(history["first_order_index"] == sequences[index][0]["order_index"])
            require(history["first_order_index"] == temporal["history_start_order_index"])
            require(
                history["completed_end_order_index"]
                == temporal["completed_history_end_order_index"]
            )
            previous = row
        require(len(sequences) == route["sequence_count"] == len(route["sequences"]))
        require(
            sum(len(s) for s in sequences.values()) == route["supported_workload_observation_count"]
        )
        for summary in route["sequences"]:
            sequence = sequences.pop(summary["sequence_index"], None)
            require(sequence is not None)
            require(
                summary["first_order_index"] == sequence[0]["order_index"]
                and summary["last_order_index"] == sequence[-1]["order_index"]
            )
            require(summary["observation_count"] == len(sequence))
            require(
                summary["start_exercise_elapsed_ms"] == sequence[0]["start_exercise_elapsed_ms"]
                and summary["end_exercise_elapsed_ms"] == sequence[-1]["end_exercise_elapsed_ms"]
            )
            require(summary["initial_physiological_state"] == "UNKNOWN")
            require(
                summary["pre_observation_history_censored"] is True
                and summary["post_observation_recovery_censored"] is True
                and summary["physiological_reset_verified"] is False
            )
    require(
        sum(r["complete_hr_window_count"] for r in routes) == dataset["complete_hr_window_count"]
    )
    require(
        dataset["feature_status_counts"]
        == {name: dict(count) for name, count in feature_counts.items()}
    )
    require(
        dataset["component_status_counts"]
        == {name: dict(count) for name, count in component_counts.items()}
    )
    return {
        "payload_hash_verified": True,
        "internal_references_verified": True,
        "claim_scope": "PAYLOAD_INTEGRITY_AND_INTERNAL_CONSISTENCY_ONLY",
        "hr_window_status_counts": dict(sorted(statuses.items())),
    }


def check_response_dataset_integrity(dataset):
    """Reject summaries, altered grids/history and unsupported transformations."""
    try:
        return _check(dataset)
    except (KeyError, TypeError, AttributeError, OverflowError, ZeroDivisionError) as exc:
        raise ValueError("DATASET_INTERNAL_REFERENCES_INVALID") from exc
