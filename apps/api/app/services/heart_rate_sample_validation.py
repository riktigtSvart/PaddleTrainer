from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

VALIDATION_VERSION = "0.1.0"
CONTRACT_ID = "POLAR_V4_INTERVAL_VALUES_2026_10_06"
LIMITATIONS = [
    "HR_SAMPLE_TIME_ORIGIN_NOT_VERIFIED",
    "HR_PAUSE_CLOCK_SEMANTICS_NOT_VERIFIED",
    "HR_SENSOR_IDENTITY_NOT_ESTABLISHED",
    "HR_ACQUISITION_QUALITY_NOT_ESTABLISHED",
    "DESCRIPTIVE_PATTERNS_ARE_NOT_VALIDATED_ARTIFACT_DETECTION",
]


def build_training_session_heart_rate_validation(
    sample_session: Mapping[str, Any] | None,
    *,
    expected_session_external_id: Any,
    sample_session_match_count: int,
) -> dict[str, Any]:
    """Check raw HR values and clock consistency without certifying HR labels.

    Works independently of weather, model inputs and route readiness. Numeric
    summaries describe recorded values; they are not physiological predictions.
    An IntervalValues interval supplies neither sample-zero time nor HR sensor
    identity. Duration agreement, flat runs and RR presence cannot supply them.
    """
    session = _mapping(sample_session)
    identity = _id(expected_session_external_id)
    reasons = []
    if identity is None or identity != _identifier(session):
        reasons.append("SAMPLE_SESSION_IDENTITY_UNVERIFIABLE")
    if not _integer(sample_session_match_count) or sample_session_match_count != 1:
        reasons.append("SAMPLE_SESSION_MISSING_OR_AMBIGUOUS")
    source_hash = _hash(
        {
            "sample_session": session,
            "expected_session_external_id": expected_session_external_id,
            "sample_session_match_count": sample_session_match_count,
        }
    )
    if source_hash is None:
        reasons.append("HR_SOURCE_NOT_CANONICAL_JSON")
    exercises = session.get("exercises")
    if not isinstance(exercises, list):
        exercises = []
        reasons.append("SAMPLE_EXERCISES_MISSING_OR_INVALID")
    ids = [_identifier(e) for e in exercises]
    results = []
    for index, exercise in enumerate(exercises):
        exercise_reasons = list(reasons)
        if ids[index] is not None and ids.count(ids[index]) > 1:
            exercise_reasons.append("SAMPLE_EXERCISE_IDENTITY_AMBIGUOUS")
        results.append(_exercise_result(exercise, session, index, exercise_reasons))
    clean = sum(e["technical_status"] == "TECHNICALLY_CLEAN_WITH_LIMITATIONS" for e in results)
    result = {
        "provider": "PADDLETRAINER",
        "schema_version": "0.1",
        "validation_version": VALIDATION_VERSION,
        "source_contract_id": CONTRACT_ID,
        "session_external_id": identity,
        "source_binding_verified": not reasons,
        "available": any(e["hr_series_count"] > 0 for e in results),
        "status": "WITHHELD"
        if reasons
        else "CHECKED_WITH_ISSUES"
        if clean < len(results)
        else "CHECKED_WITH_LIMITATIONS"
        if results
        else "UNAVAILABLE",
        "exercise_count": len(results),
        "technically_clean_exercise_count": clean,
        "exercise_with_technical_issues_count": len(results) - clean,
        "timebase_review_required_exercise_count": sum(
            e["timebase"]["consistency_status"] != "CONSISTENT_WITH_REPORTED_METADATA"
            for e in results
        ),
        "verified_hr_label_count": 0,
        "training_authorized": False,
        "numeric_prediction_authorized": False,
        "blocking_reasons": reasons,
        "limitations": list(LIMITATIONS),
        "input_provenance": {"source_hash": source_hash},
        "policy": {
            "raw_values_checked_before_normalization": True,
            "sample_grid_zero_origin_is_assumed_only": True,
            "sample_values_modified": False,
            "missing_values_interpolated": False,
            "physiological_outlier_threshold_configured": False,
            "artifact_detector_validated": False,
            "recording_product_is_not_hr_sensor_identity": True,
            "rr_presence_is_not_hr_quality_proof": True,
            "promotes_training_data_readiness": False,
            "persists_validation": False,
        },
        "exercises": results,
    }
    result["decision_hash"] = _hash(result)
    return result


def _exercise_result(exercise, session, index, reasons):
    if not isinstance(exercise, Mapping):
        reasons.append("SAMPLE_EXERCISE_INVALID")
    exercise = _mapping(exercise)
    container = exercise.get("samples")
    limitations = list(LIMITATIONS)
    if isinstance(container, list):
        series = container
        limitations.append("NONSTANDARD_SAMPLES_CONTAINER")
    elif isinstance(container, Mapping):
        series = _list(container.get("samples"))
        if "samples" in container and not isinstance(container["samples"], list):
            reasons.append("HR_SAMPLES_CONTAINER_INVALID")
    else:
        series = []
        if container is not None:
            reasons.append("HR_SAMPLES_CONTAINER_INVALID")
    hr = [s for s in series if isinstance(s, Mapping) and s.get("type") == "HEART_RATE"]
    if len(hr) != 1:
        reasons.append("HEART_RATE_SERIES_MISSING_OR_AMBIGUOUS")
    selected = hr[0] if len(hr) == 1 else {}
    interval = selected.get("intervalMillis")
    if not _integer(interval, positive=True) or interval > 2**63 - 1:
        interval = None
        reasons.append("HEART_RATE_INTERVAL_INVALID")
    values = selected.get("values")
    if not isinstance(values, list):
        if "values" in selected:
            reasons.append("HEART_RATE_VALUES_CONTAINER_INVALID")
        values = []
    if not values:
        reasons.append("HEART_RATE_VALUES_MISSING_OR_EMPTY")
    categories = [_value_category(v) for v in values]
    if any(c != "POSITIVE_FINITE" for c in categories):
        reasons.append("HEART_RATE_INVALID_OR_MISSING_VALUES")
    unknown = sorted(str(k) for k in selected if k not in {"type", "intervalMillis", "values"})
    if unknown:
        limitations.append("UNRECOGNIZED_HR_SERIES_FIELDS_REQUIRE_REVIEW")
    reasons = list(dict.fromkeys(reasons))
    product = _mapping(session.get("product")).get("modelName")
    product = product if isinstance(product, str) and product.strip() else None
    return {
        "exercise_index": index,
        "source_exercise_id": _identifier(exercise),
        "technical_status": "WITHHELD"
        if len(hr) > 1
        or any(
            r in reasons
            for r in (
                "SAMPLE_SESSION_IDENTITY_UNVERIFIABLE",
                "SAMPLE_SESSION_MISSING_OR_AMBIGUOUS",
                "HR_SOURCE_NOT_CANONICAL_JSON",
                "SAMPLE_EXERCISE_IDENTITY_AMBIGUOUS",
            )
        )
        else "UNAVAILABLE"
        if not hr
        else "TECHNICAL_ISSUES"
        if reasons
        else "TECHNICALLY_CLEAN_WITH_LIMITATIONS",
        "hr_series_count": len(hr),
        "technical_blocking_reasons": reasons,
        "time_origin_verified": False,
        "acquisition_quality_verified": False,
        "verified_hr_label_count": 0,
        "training_authorized": False,
        "value_quality": _value_quality(values, categories, interval),
        "timebase": _timebase(exercise, session, len(values), interval),
        "acquisition": {
            "status": "NOT_ESTABLISHED",
            "recording_product_model_name": product,
            "hr_sensor_identity": None,
            "hr_sensor_modality": None,
            "signal_quality_metric": None,
            "independent_reference_available": False,
            "rr_inventory": _rr_inventory(_mapping(container)),
            "transition_hr_series_count": sum(
                isinstance(s, Mapping) and s.get("type") == "HEART_RATE"
                for s in _list(_mapping(container).get("transitionSamples"))
            ),
        },
        "unrecognized_hr_series_fields": unknown,
        "limitations": limitations,
    }


def _value_quality(values, categories, interval):
    flags = [c == "POSITIVE_FINITE" for c in categories]
    positive = [float(v) for v, valid in zip(values, flags) if valid]
    changes = [
        abs(float(values[i]) - float(values[i - 1]))
        for i in range(1, len(values))
        if flags[i] and flags[i - 1]
    ]
    run = longest = 0
    previous = None
    for value, valid in zip(values, flags):
        current = float(value) if valid else None
        run = run + 1 if valid and current == previous else 1 if valid else 0
        longest = max(longest, run)
        previous = current
    first = next((i for i, valid in enumerate(flags) if valid), None)
    last = next((i for i in range(len(flags) - 1, -1, -1) if flags[i]), None)
    missing_run = longest_missing = 0
    for valid in flags:
        missing_run = 0 if valid else missing_run + 1
        longest_missing = max(longest_missing, missing_run)
    max_change = max(changes) if changes else None
    return {
        "slot_count": len(values),
        "interval_ms": interval,
        "positive_finite_sample_count": len(positive),
        "invalid_or_missing_sample_count": len(values) - len(positive),
        "invalid_value_counts": {
            c: categories.count(c)
            for c in (
                "MISSING",
                "BOOLEAN",
                "NON_NUMERIC",
                "NON_FINITE",
                "ZERO",
                "NEGATIVE",
            )
        },
        "first_positive_slot_index": first,
        "last_positive_slot_index": last,
        "leading_invalid_slots": first if first is not None else len(values),
        "trailing_invalid_slots": len(values) - last - 1 if last is not None else len(values),
        "longest_invalid_run_slots": longest_missing,
        "longest_invalid_run_nominal_ms": longest_missing * interval if interval else None,
        "observed_min_bpm": min(positive) if positive else None,
        "observed_max_bpm": max(positive) if positive else None,
        "adjacent_valid_pair_count": len(changes),
        "largest_adjacent_change_bpm": max_change,
        "largest_adjacent_change_bpm_per_second": _finite(max_change / (interval / 1000))
        if max_change is not None and interval
        else None,
        "longest_constant_run_slots": longest,
        "longest_constant_run_span_ms": (longest - 1) * interval if longest and interval else None,
        "artifact_status": "NOT_ASSESSED",
        "physiological_plausibility_status": "NOT_ASSESSED",
    }


def _timebase(exercise, session, slots, interval):
    start, stop = (
        _timestamp(exercise.get("startTime"), exercise, session),
        _timestamp(exercise.get("stopTime"), exercise, session),
    )
    duration = exercise.get("durationMillis")
    duration = duration if _integer(duration, positive=True) else None
    wall = _millis(stop - start) if start is not None and stop is not None else None
    reasons = []
    if start is None:
        reasons.append("EXERCISE_START_TIME_UNVERIFIABLE")
    if stop is None:
        reasons.append("EXERCISE_STOP_TIME_UNVERIFIABLE")
    if wall is not None and wall <= 0:
        reasons.append("EXERCISE_STOP_NOT_AFTER_START")
    if duration is None:
        reasons.append("EXERCISE_DURATION_UNVERIFIABLE")
    if interval is None:
        reasons.append("HR_GRID_INTERVAL_UNVERIFIABLE")
    pauses = _pauses(exercise, session, start, stop)
    if pauses["status"] == "INVALID":
        reasons.append("PAUSE_METADATA_INVALID")
    adjusted_wall = (
        wall - pauses["union_duration_ms"]
        if wall is not None and pauses["status"] == "VALID"
        else None
    )
    relation = (
        "UNVERIFIABLE"
        if wall is None or wall <= 0 or duration is None
        else (
            "DECLARED_EQUALS_WALL_CLOCK"
            if duration == wall
            else "DECLARED_EQUALS_WALL_MINUS_REPORTED_PAUSES"
            if duration == adjusted_wall
            else "DECLARED_DIFFERS_FROM_REPORTED_CLOCKS"
        )
    )
    expected = (duration + interval - 1) // interval if duration and interval else None
    count_delta = slots - expected if expected is not None else None
    if relation == "DECLARED_DIFFERS_FROM_REPORTED_CLOCKS":
        reasons.append("EXERCISE_DURATION_CLOCK_RELATION_REQUIRES_REVIEW")
    if count_delta is not None and count_delta != 0:
        reasons.append("HR_SLOT_COUNT_DIFFERS_FROM_ZERO_ORIGIN_HALF_OPEN_GRID")
    return {
        "consistency_status": "REVIEW_REQUIRED" if reasons else "CONSISTENT_WITH_REPORTED_METADATA",
        "time_origin_status": "NOT_VERIFIED",
        "first_sample_timestamp_utc": None,
        "pause_clock_status": "NOT_VERIFIED",
        "exercise_start_utc": _iso(start),
        "exercise_stop_utc": _iso(stop),
        "declared_duration_ms": duration,
        "wall_clock_duration_ms": wall,
        "reported_pause_adjusted_wall_duration_ms": adjusted_wall,
        "duration_clock_relation": relation,
        "pause_inventory": pauses,
        "grid_convention": "ASSUMED_FIRST_SLOT_AT_EXERCISE_ZERO",
        "expected_half_open_grid_slot_count": expected,
        "slot_count_minus_expected_half_open_grid": count_delta,
        "assumed_last_slot_elapsed_ms": (slots - 1) * interval if slots and interval else None,
        "sample_grid_span_ms": (slots - 1) * interval if slots and interval else None,
        "nominal_slot_occupancy_ms": slots * interval if interval else None,
        "review_reasons": reasons,
    }


def _pauses(exercise, session, start, stop):
    raw = exercise.get("pauseTimes")
    windows = []
    invalid = 0
    if isinstance(raw, list):
        for item in raw:
            item = _mapping(item)
            a, b = (
                _timestamp(item.get("startTime"), exercise, session),
                _timestamp(item.get("endTime"), exercise, session),
            )
            if (
                a is None
                or b is None
                or start is None
                or stop is None
                or not start <= a < b <= stop
            ):
                invalid += 1
            else:
                windows.append((a, b))
    elif "pauseTimes" in exercise:
        invalid = 1
    merged = []
    overlap = False
    for a, b in sorted(windows):
        if merged and a < merged[-1][1]:
            overlap = True
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
        else:
            merged.append((a, b))
    return {
        "status": "INVALID"
        if invalid or overlap
        else "VALID"
        if isinstance(raw, list)
        else "NOT_PROVIDED",
        "record_count": len(raw) if isinstance(raw, list) else 0,
        "invalid_record_count": invalid,
        "overlap_detected": overlap,
        "union_duration_ms": sum(_millis(b - a) for a, b in merged),
    }


def _rr_inventory(container):
    raw = container.get("rrSamples")
    values = _list(raw)
    return {
        "status": "PRESENT"
        if isinstance(raw, list)
        else "MALFORMED"
        if "rrSamples" in container
        else "NOT_PROVIDED",
        "sample_count": len(values),
        "positive_duration_count": sum(
            _integer(_mapping(v).get("durationMillis"), positive=True) for v in values
        ),
        "offline_count": sum(_mapping(v).get("offline") is True for v in values),
        "invalid_offline_flag_count": sum(
            not isinstance(_mapping(v).get("offline"), bool) for v in values
        ),
        "hr_quality_verified": False,
    }


def _timestamp(value, exercise, session):
    if not isinstance(value, str) or "T" not in value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            offset = exercise.get("timezoneOffsetMinutes", session.get("timezoneOffsetMinutes"))
            if not isinstance(offset, int) or isinstance(offset, bool) or abs(offset) >= 1440:
                return None
            parsed = parsed.replace(tzinfo=timezone(timedelta(minutes=offset)))
        return parsed.astimezone(UTC)
    except (ValueError, OverflowError):
        return None


def _value_category(value):
    if value is None:
        return "MISSING"
    if isinstance(value, bool):
        return "BOOLEAN"
    if not isinstance(value, (int, float)):
        return "NON_NUMERIC"
    if _finite(value) is None:
        return "NON_FINITE"
    return "POSITIVE_FINITE" if value > 0 else "ZERO" if value == 0 else "NEGATIVE"


def _finite(value):
    try:
        return float(value) if math.isfinite(value) else None
    except (ValueError, TypeError, OverflowError):
        return None


def _integer(value, positive=False):
    return (
        isinstance(value, int) and not isinstance(value, bool) and value >= (1 if positive else 0)
    )


def _id(value):
    return (
        str(value)
        if isinstance(value, (int, str)) and not isinstance(value, bool) and str(value).strip()
        else None
    )


def _identifier(value):
    return _id(_mapping(_mapping(value).get("identifier")).get("id"))


def _mapping(value):
    return value if isinstance(value, Mapping) else {}


def _list(value):
    return value if isinstance(value, list) else []


def _iso(value):
    return value.isoformat() if value is not None else None


def _millis(value):
    return value // timedelta(microseconds=1) / 1000


def _hash(value):
    try:
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest()
    except (TypeError, ValueError, OverflowError):
        return None
