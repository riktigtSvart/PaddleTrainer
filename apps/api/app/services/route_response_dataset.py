"""Source-bound retrospective observations and HR targets, without model fitting."""

import hashlib
import json
import math
from collections import Counter
from collections.abc import Mapping
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from typing import Any

from app.services.hr_response_temporal_context import hr_response_temporal_policy
from app.services.polar_training_samples import normalize_polar_training_samples
from app.services.response_dataset_split import resolve_dataset_split
from app.services.training_data_readiness_audit import build_route_training_data_readiness_audit

DATASET_VERSION = "0.1.0"
COMPONENTS = ("water_identity", "weather", "wind", "hydrology")
WORKLOAD_FIELDS = (
    "order_index",
    "segment_index",
    "segment_index_scope",
    "source_segment_index",
    "source_segment_index_scope",
    "source_segment_index_status",
    "source_waypoint_contiguous",
    "start_waypoint_index",
    "end_waypoint_index",
    "start_exercise_elapsed_ms",
    "end_exercise_elapsed_ms",
    "segment_midpoint_exercise_elapsed_ms",
    "interval_ms",
    "surface_distance_m",
    "cumulative_trusted_surface_distance_m",
    "gps_ground_speed_mps",
    "initial_bearing_deg",
    "motion_available",
    "motion_reason",
    "source_contiguous_with_previous",
    "previous_segment_index",
    "previous_source_segment_index",
    "previous_gps_ground_speed_mps",
    "ground_speed_change_from_previous_mps",
    "segment_midpoint_separation_from_previous_ms",
    "ground_speed_change_rate_mps2",
    "absolute_bearing_change_from_previous_deg",
)
FEATURES = {
    "air_temperature_c": ("weather", ("sample", "air_temperature_c"), "degC"),
    "weather_wind_speed_mps": ("weather", ("sample", "wind_speed_mps"), "m/s"),
    "weather_wind_direction_from_deg": ("weather", ("sample", "wind_direction_from_deg"), "deg"),
    "weather_wind_gust_mps": ("weather", ("sample", "wind_gust_mps"), "m/s"),
    "headwind_component_mps": ("wind", ("headwind_component_mps",), "m/s"),
    "tailwind_component_mps": ("wind", ("tailwind_component_mps",), "m/s"),
    "crosswind_magnitude_mps": ("wind", ("crosswind_magnitude_mps",), "m/s"),
    "relative_air_speed_mps": ("wind", ("relative_air_speed_mps",), "m/s"),
    "water_level_cm": ("hydrology", ("context", "water_level", "value"), "cm"),
    "discharge_m3_s": ("hydrology", ("context", "discharge", "value"), "m3/s"),
    "water_temperature_c": ("hydrology", ("context", "water_temperature", "value"), "degC"),
}


def build_route_response_dataset(
    expected_response_input: Mapping[str, Any] | None,
    normalized_samples: Mapping[str, Any] | None,
    *,
    session_external_id: Any,
    athlete_id: Any,
    route_session: Mapping[str, Any] | None,
    sample_session: Mapping[str, Any] | None,
    sample_session_match_count: int,
    hr_timebase_snapshots: list[Mapping[str, Any]] | None = None,
    hr_acquisition_declarations: list[Mapping[str, Any]] | None = None,
    trusted_environment: Mapping[str, Any] | None = None,
    provider_selection: Mapping[str, Any] | None = None,
    weather_source: Mapping[str, Any] | None = None,
    split_manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Reproduce the audit from owner-bound inputs; never accept client audit claims.

    All observation windows survive, including unlabelled or ineligible rows.
    History is represented by pointers into one shared chronological row table.
    Raw HR slot positions survive normalization; only a current verified export
    supplies mapped timestamps, never a guessed physiological lag.
    """
    audit = build_route_training_data_readiness_audit(
        expected_response_input,
        normalized_samples,
        session_external_id=session_external_id,
        athlete_id=athlete_id,
        route_session=route_session,
        sample_session=sample_session,
        sample_session_match_count=sample_session_match_count,
        hr_timebase_snapshots=hr_timebase_snapshots,
        hr_acquisition_declarations=hr_acquisition_declarations,
        trusted_environment=trusted_environment,
        provider_selection=provider_selection,
        weather_source=weather_source,
    )
    split = resolve_dataset_split(
        split_manifest,
        athlete_id=audit["athlete_id"],
        session_external_id=audit["session_external_id"],
    )
    binding_reasons = list(audit["blocking_reasons"])
    if audit["session_group_key"] is None:
        binding_reasons.append("DATASET_SESSION_GROUP_UNVERIFIABLE")
    if any(
        not route["input_diagnostics"]["environment_detail_binding_verified"]
        for route in audit["routes"]
    ):
        binding_reasons.append("DATASET_ENVIRONMENT_DETAIL_BINDING_UNVERIFIED")
    route_keys = [(r["route_index"], r["exercise_index"]) for r in audit["routes"]]
    if any(
        type(a) is not int or type(b) is not int or a < 0 or b < 0 for a, b in route_keys
    ) or len(set(route_keys)) != len(route_keys):
        binding_reasons.append("DATASET_ROUTE_IDENTITY_INVALID_OR_AMBIGUOUS")
    if any(route["temporal_context"]["blocking_reasons"] for route in audit["routes"]):
        binding_reasons.append("DATASET_CHRONOLOGY_INVALID_OR_AMBIGUOUS")
    streams, rows, route_summaries = {}, [], []
    inputs = _items(_mapping(expected_response_input).get("routes"))
    environment_routes = _items(_mapping(trusted_environment).get("routes"))
    samples = normalize_polar_training_samples(
        {"exerciseSamples": _mapping(sample_session).get("exercises")}
    )
    component_counts = {name: Counter() for name in COMPONENTS}
    feature_counts = {name: Counter() for name in FEATURES}
    for route in audit["routes"]:
        matching = [
            item
            for item in inputs
            if (item.get("route_index"), item.get("exercise_index"))
            == (route["route_index"], route["exercise_index"])
        ]
        input_rows = _items(matching[0].get("segments")) if len(matching) == 1 else []
        by_order = _lookup(input_rows)
        matching_environment = [
            item
            for item in environment_routes
            if (item.get("route_index"), item.get("exercise_index"))
            == (route["route_index"], route["exercise_index"])
        ]
        environment_by_order = _lookup(
            _items(matching_environment[0].get("segments"))
            if len(matching_environment) == 1
            else []
        )
        stream = _stream(route, samples, audit["session_group_key"], split["split"])
        if stream is not None:
            streams[stream["stream_id"]] = stream
        route_rows = []
        for window in route["segments"]:
            candidates = by_order.get(window["order_index"], [])
            source = candidates[0] if len(candidates) == 1 else {}
            matching_components = environment_by_order.get(window["order_index"], [])
            environment = matching_components[0] if len(matching_components) == 1 else {}
            components = {name: _component(environment.get(name)) for name in COMPONENTS}
            features = _features(environment)
            for name, component in components.items():
                component_counts[name][component["status"]] += 1
            for name, feature in features.items():
                feature_counts[name][feature["status"]] += 1
            row_id = _hash(
                [
                    audit["session_group_key"],
                    route["route_index"],
                    route["exercise_index"],
                    window["order_index"],
                ]
            )
            temporal = deepcopy(window["temporal_context"])
            supported = temporal["status"] == "OBSERVED_WORKLOAD_SEQUENCE"
            row = {
                "row_id": row_id,
                "route_index": route["route_index"],
                "exercise_index": route["exercise_index"],
                "order_index": window["order_index"],
                "session_group_key": audit["session_group_key"],
                "split": split["split"],
                "start_exercise_elapsed_ms": window["start_exercise_elapsed_ms"],
                "end_exercise_elapsed_ms": window["end_exercise_elapsed_ms"],
                "workload_observation": {
                    key: deepcopy(_mapping(source.get("external_workload"))[key])
                    for key in WORKLOAD_FIELDS
                    if key in _mapping(source.get("external_workload"))
                },
                "workload_available": source.get("workload_available") is True,
                "environment_components": components,
                "environment_features": features,
                "conditioning_role": "RETROSPECTIVE_OBSERVATION_ONLY",
                "temporal_context": temporal,
                "history_ref": {
                    "route_index": route["route_index"],
                    "exercise_index": route["exercise_index"],
                    "sequence_index": temporal["sequence_index"],
                    "first_order_index": temporal["history_start_order_index"],
                    "completed_end_order_index": temporal["completed_history_end_order_index"],
                    "includes_current_workload_for_retrospective_conditioning": supported,
                    "causal_predictor_history_selected": False,
                },
                "hr_label_ref": _label_ref(window, stream),
                "existing_preparation_candidate": window["candidate_for_data_preparation"] is True,
                "preparation_candidate": not binding_reasons
                and window["candidate_for_data_preparation"] is True
                and route["export_timebase_verified"] is True,
                "exclusion_reasons": _exclusions(window, route, binding_reasons),
            }
            route_rows.append(row)
        rows.extend(route_rows)
        route_summaries.append(
            {
                "route_index": route["route_index"],
                "exercise_index": route["exercise_index"],
                "sample_exercise_index": route["sample_exercise_index"],
                "exercise_start_utc": route["exercise_start_utc"],
                "sport_id": route["sport_id"],
                "observation_count": len(route_rows),
                "supported_workload_observation_count": sum(
                    row["temporal_context"]["status"] == "OBSERVED_WORKLOAD_SEQUENCE"
                    for row in route_rows
                ),
                "complete_hr_window_count": route["fully_covered_grid_segment_count"],
                "preparation_candidate_count": sum(
                    row["preparation_candidate"] for row in route_rows
                ),
                "hr_stream_id": stream["stream_id"] if stream else None,
                "hr_timebase": deepcopy(route["hr_timebase"]),
                "hr_acquisition": deepcopy(route["hr_acquisition"]),
                "limitations": deepcopy(route["limitations"]),
                "blocking_reasons": deepcopy(route["blocking_reasons"]),
                "sequence_count": len(_sequences(route_rows)),
                "sequences": _sequences(route_rows),
            }
        )
    # Uncanonical/ambiguous owners cannot produce source-bound payloads.
    if binding_reasons:
        rows, streams = [], {}
        for route in route_summaries:
            route["preparation_candidate_count"] = 0
            route["hr_stream_id"] = None
    result = {
        "provider": "PADDLETRAINER",
        "schema_version": "0.1",
        "dataset_version": DATASET_VERSION,
        "payload_included": True,
        "status": "OBSERVATION_PACKAGE_WITH_LIMITATIONS" if rows else "WITHHELD",
        "domain": "RETROSPECTIVE_CONDITIONAL_RESPONSE",
        "athlete_id": audit["athlete_id"],
        "session_external_id": audit["session_external_id"],
        "session_group_key": audit["session_group_key"],
        "split_assignment": split,
        "training_authorized": False,
        "numeric_output_authorized": False,
        "pre_exercise_prediction_authorized": False,
        "causal_prediction_authorized": False,
        "observation_count": len(rows),
        "source_observation_count": sum(r["segment_count"] for r in audit["routes"]),
        "route_count": len(route_summaries),
        "hr_stream_count": len(streams),
        "hr_slot_count": sum(s["slot_count"] for s in streams.values()),
        "existing_preparation_candidate_count": audit["candidate_segment_count"],
        "preparation_candidate_count": sum(row["preparation_candidate"] for row in rows),
        "complete_hr_window_count": sum(
            r["fully_covered_grid_segment_count"] for r in audit["routes"]
        ),
        "excluded_observation_count": sum(not row["preparation_candidate"] for row in rows),
        "component_status_counts": {
            name: dict(sorted(counts.items())) for name, counts in component_counts.items()
        },
        "feature_status_counts": {
            name: dict(sorted(counts.items())) for name, counts in feature_counts.items()
        },
        "blocking_reasons": list(dict.fromkeys(binding_reasons)),
        "training_blocking_reasons": list(
            dict.fromkeys(
                [
                    *binding_reasons,
                    *split["blocking_reasons"],
                    "HR_ACQUISITION_QUALITY_NOT_ESTABLISHED",
                    "RESPONSE_MODEL_NOT_CONFIGURED",
                    "COHORT_EVALUATION_NOT_ESTABLISHED",
                ]
            )
        ),
        "input_provenance": {
            "audit_version": audit["audit_version"],
            "audit_source_hash": audit["input_provenance"]["source_hash"],
            "audit_decision_hash": audit["decision_hash"],
            "raw_hr_validation_decision_hash": audit["hr_signal_diagnostics_evidence"][
                "input_provenance"
            ]["raw_validation_decision_hash"],
            "hr_signal_diagnostics_decision_hash": audit["input_provenance"][
                "hr_signal_diagnostics_decision_hash"
            ],
            "expected_response_input_hash": audit["input_provenance"][
                "expected_response_input_hash"
            ],
            "split_manifest_hash": split["manifest_hash"],
            "scope": "CURRENT_PROVIDED_SOURCE_AND_PROOFS",
            "database_environment_replay_verified": False,
        },
        "policy": {
            **hr_response_temporal_policy(),
            "split_assigned": split["status"] == "ASSIGNED",
            "all_observations_preserved_before_label_filtering": not binding_reasons,
            "history_storage": "SHARED_CHRONOLOGICAL_OBSERVATIONS_WITH_ROUTE_SEQUENCE_POINTERS",
            "hr_labels_stored_separately_from_conditioning": True,
            "hr_timestamp_basis": "VERIFIED_EXPORT_GRID_ONLY_NOT_NATIVE_API_SAMPLE_CLOCK",
            "feature_missing_values_imputed": False,
            "feature_fit_performed": False,
            "component_masks_and_limitations_preserved": True,
            "current_velocity_estimated": False,
            "boat_through_water_speed_estimated": False,
            "cross_route_target_overlap_evaluated": False,
            "split_assignments_persisted": False,
        },
        "routes": route_summaries,
        "hr_streams": list(streams.values()),
        "observations": rows,
    }
    result["package_hash"] = _hash(result)
    return result


def verify_route_response_dataset(dataset: Mapping[str, Any]) -> bool:
    """Verify full-payload integrity, not the trustworthiness of a caller's claims."""
    return (
        dataset.get("payload_included") is True
        and dataset.get("package_hash") is not None
        and dataset["package_hash"]
        == _hash({key: value for key, value in dataset.items() if key != "package_hash"})
    )


def summarize_route_response_dataset(dataset: Mapping[str, Any]) -> dict[str, Any]:
    """Stable full-package commitment; no full labels or observation rows in inspect."""
    result = deepcopy(dict(dataset))
    rows = result.pop("observations")
    result["payload_included"] = False
    result["observation_preview"] = rows[:2] + rows[max(2, len(rows) - 2) :] if rows else []
    for stream in result["hr_streams"]:
        stream.pop("samples")
        stream["samples_included"] = False
    for route in result["routes"]:
        route["sequences_truncated"] = len(route["sequences"]) > 25
        route["sequences"] = route["sequences"][:25]
    return result


def _stream(
    route: Mapping[str, Any], samples: Mapping[str, Any], group: str | None, split: str | None
):
    matches = [
        s
        for s in samples["series"]
        if s["exercise_index"] == route["sample_exercise_index"]
        and s["metric_key"] == "heart_rate_bpm"
    ]
    if len(matches) != 1 or type(matches[0]["interval_ms"]) is not int:
        return None
    series = matches[0]
    interval_us = series["interval_ms"] * 1000
    verified = route["export_timebase_verified"] is True
    origin = route["hr_timebase"]["sample_grid_origin_us"] if verified else None
    start = (
        datetime.fromisoformat(route["exercise_start_utc"]) if route["exercise_start_utc"] else None
    )
    stream_id = _hash(
        [
            group,
            route["sample_exercise_index"],
            route["exercise_start_utc"],
            origin,
            interval_us,
            _hash(series),
        ]
    )
    slots = []
    for index, value in enumerate(series["values"]):
        elapsed = origin + index * interval_us if verified else None
        slots.append(
            {
                "sample_index": index,
                "value_bpm": value,
                "positive_finite": _positive(value),
                "exercise_elapsed_us": elapsed,
                "mapped_timestamp_utc": (start + timedelta(microseconds=elapsed))
                .astimezone(UTC)
                .isoformat()
                if start and elapsed is not None
                else None,
            }
        )
    return {
        "stream_id": stream_id,
        "session_group_key": group,
        "split": split,
        "sample_exercise_index": route["sample_exercise_index"],
        "metric": "heart_rate_bpm",
        "unit": "bpm",
        "interval_us": interval_us,
        "slot_count": len(slots),
        "positive_finite_sample_count": sum(s["positive_finite"] for s in slots),
        "time_mapping_verified": verified,
        "sample_grid_origin_us": origin,
        "timestamp_basis": "VERIFIED_SAVED_EXPORT_GRID" if verified else "NOT_MAPPED",
        "native_provider_per_sample_timestamps_present": False,
        "samples": slots,
    }


def _label_ref(window, stream):
    valid = (
        stream
        and stream["time_mapping_verified"]
        and window["grid_coverage_status"] != "INVALID_WINDOW"
    )
    first = stop = None
    if valid:
        origin, interval = stream["sample_grid_origin_us"], stream["interval_us"]
        first = max(0, -(-(window["start_exercise_elapsed_ms"] * 1000 - origin) // interval))
        stop = max(0, -(-(window["end_exercise_elapsed_ms"] * 1000 - origin) // interval))
    recorded = (
        max(0, min(stop, stream["slot_count"]) - min(first, stream["slot_count"])) if valid else 0
    )
    return {
        "stream_id": stream["stream_id"] if stream else None,
        "status": window["grid_coverage_status"]
        if valid
        else "TIME_MAPPING_UNAVAILABLE"
        if window["grid_coverage_status"] != "INVALID_WINDOW"
        else "INVALID_WINDOW",
        "grid_start_index_inclusive": first,
        "grid_stop_index_exclusive": stop,
        "recorded_slot_count": recorded,
        "unrecorded_grid_slot_count": stop - first - recorded if valid else None,
        "expected_grid_slot_count": window["expected_grid_slot_count"] if valid else None,
        "positive_finite_grid_sample_count": window["positive_finite_grid_sample_count"]
        if valid
        else None,
        "missing_or_invalid_grid_slot_count": window["missing_or_invalid_grid_slot_count"]
        if valid
        else None,
        "window_semantics": "HALF_OPEN_START_INCLUSIVE_END_EXCLUSIVE",
        "label_used_as_predictor": False,
    }


def _features(environment):
    result = {}
    for name, (component_name, path, unit) in FEATURES.items():
        component = _mapping(environment.get(component_name))
        allowed = (
            component.get("available") is True
            and component.get("usable_for_downstream_environment_context") is True
            and component.get("status") in ("TRUSTED", "TRUSTED_WITH_LIMITATIONS")
            and component.get("applicable") is not False
        )
        value = component
        for field in path:
            value = _mapping(value).get(field)
        status = (
            "AVAILABLE"
            if allowed and _finite(value)
            else "WITHHELD"
            if component.get("status") == "WITHHELD"
            else "NOT_APPLICABLE"
            if component.get("applicable") is False
            else "MISSING"
        )
        if component_name == "hydrology":
            metric = _mapping(_mapping(component.get("context")).get(path[1]))
            if metric.get("available") is not True or metric.get("unit") != unit:
                status = "MISSING" if allowed else status
        result[name] = {
            "value": value if status == "AVAILABLE" else None,
            "available": status == "AVAILABLE",
            "status": status,
            "unit": unit,
            "source_component": component_name,
            "pre_exercise_predictor_authorized": False,
        }
    return result


def _component(value):
    value = _mapping(value)
    result = {
        key: deepcopy(value[key])
        for key in (
            "status",
            "available",
            "applicable",
            "usable_for_downstream_environment_context",
            "trust_basis",
            "limitations",
            "source_status",
            "sample_id",
            "absolute_time_delta_seconds",
            "surface_distance_to_sample_m",
            "environment_type",
            "resolution_status",
            "resolved_river_inland_identity",
            "resolved_marine_region_identity",
        )
        if key in value
    }
    result.setdefault("status", "COMPONENT_DETAIL_NOT_PROVIDED")
    if not isinstance(result["status"], str):
        result["status"] = "COMPONENT_STATUS_INVALID"
    result.setdefault("available", False)
    result.setdefault("usable_for_downstream_environment_context", False)
    # Metadata identifies the measurements; numeric features remain separately masked.
    sample = _mapping(value.get("sample"))
    if sample:
        result["weather_provenance"] = {
            key: deepcopy(sample[key])
            for key in (
                "sample_timestamp",
                "source_provider",
                "source_product",
                "source_type",
                "spatial_support",
                "temporal_resolution_seconds",
                "latitude_deg",
                "longitude_deg",
            )
            if key in sample
        }
    context = _mapping(value.get("context"))
    if context:
        result["hydrology_provenance"] = {
            metric: {
                key: deepcopy(_mapping(context.get(metric)).get(key))
                for key in (
                    "available",
                    "status",
                    "measurement_id",
                    "observed_at",
                    "absolute_time_delta_seconds",
                    "data_type_code",
                    "data_quality_code",
                    "field_quality_code",
                )
            }
            for metric in ("water_level", "discharge", "water_temperature")
        }
    return result


def _exclusions(window, route, binding_reasons):
    reasons = [*binding_reasons, *route["blocking_reasons"]]
    if not route["export_timebase_verified"]:
        reasons.append("VERIFIED_EXPORT_CLOCK_REQUIRED_FOR_DATASET_LABELS")
    if window["grid_coverage_status"] != "COMPLETE":
        reasons.append(
            "HR_WINDOW_INVALID"
            if window["grid_coverage_status"] == "INVALID_WINDOW"
            else "HR_LABEL_GRID_INCOMPLETE"
        )
    if window["temporal_context"]["status"] != "OBSERVED_WORKLOAD_SEQUENCE":
        reasons.append("TEMPORAL_WINDOW_SUPPORT_UNAVAILABLE")
    return list(dict.fromkeys(reasons))


def _sequences(rows):
    sequences = {}
    for row in rows:
        index = row["temporal_context"]["sequence_index"]
        if index is None:
            continue
        if index not in sequences:
            sequences[index] = {
                "sequence_index": index,
                "first_order_index": row["order_index"],
                "last_order_index": row["order_index"],
                "start_exercise_elapsed_ms": row["start_exercise_elapsed_ms"],
                "end_exercise_elapsed_ms": row["end_exercise_elapsed_ms"],
                "observation_count": 0,
                "initial_physiological_state": "UNKNOWN",
                "pre_observation_history_censored": True,
                "post_observation_recovery_censored": True,
                "physiological_reset_verified": False,
            }
        seq = sequences[index]
        seq["last_order_index"] = row["order_index"]
        seq["end_exercise_elapsed_ms"] = row["end_exercise_elapsed_ms"]
        seq["observation_count"] += 1
    return list(sequences.values())


def _lookup(items):
    result = {}
    for item in items:
        order = item.get("order_index")
        if type(order) is int and order >= 0:
            result.setdefault(order, []).append(item)
    return result


def _mapping(value):
    return value if isinstance(value, Mapping) else {}


def _items(value):
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _finite(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _positive(value):
    return _finite(value) and value > 0


def _hash(value):
    def default(item):
        if isinstance(item, (date, datetime)):
            return item.isoformat()
        raise TypeError("Unsupported dataset input")

    try:
        return hashlib.sha256(
            json.dumps(
                value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=default
            ).encode()
        ).hexdigest()
    except (TypeError, ValueError, OverflowError):
        return None
