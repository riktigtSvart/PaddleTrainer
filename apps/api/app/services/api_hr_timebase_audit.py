"""Audit declared API clocks and report HR-origin hypotheses without selecting one.

The v4 IntervalValues contract supplies a period, not a first HR timestamp.
Equal array lengths are structural evidence only. No hypothesis is promoted to
export evidence, a physiological delay, or a training-readiness decision.
"""

import hashlib
import json
import math
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta, timezone

from app.services.heart_rate_sample_validation import build_training_session_heart_rate_validation

AUDIT_VERSION = "0.2.0"
MAX_EXERCISES = 64
MAX_POINTS = 100_000
MAX_SOURCE_BYTES = 32 * 1024 * 1024
ROUTE_GRID_TOLERANCE_MS = 10
DOC_URL = "https://www.polar.com/polar-api-v4/"


def _map(value):
    return value if isinstance(value, Mapping) else {}


def _id(value):
    return str(value) if isinstance(value, (str, int)) and not isinstance(value, bool) and str(value).strip() else None


def _identifier(value):
    return _id(_map(_map(value).get("identifier")).get("id"))


def _hash(value):
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode()
        return hashlib.sha256(raw).hexdigest() if len(raw) <= MAX_SOURCE_BYTES else None
    except (TypeError, ValueError, RecursionError):
        return None


def _integer(value, *, positive=False):
    return type(value) is int and (value > 0 if positive else value >= 0) and value <= 2**63 - 1


def _time(value, exercise, session):
    try:
        if not isinstance(value, str) or "T" not in value:
            return None
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.utcoffset() is None:
            offset = exercise.get("timezoneOffsetMinutes", session.get("timezoneOffsetMinutes"))
            if type(offset) is not int or abs(offset) >= 1440:
                return None
            result = result.replace(tzinfo=timezone(timedelta(minutes=offset)))
        return result.astimezone(UTC)
    except (ValueError, OverflowError, TypeError):
        return None


def _iso(value):
    return value.isoformat() if value is not None else None


def _us(delta):
    return (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds


def _series(exercise, kind):
    container = exercise.get("samples")
    items = container if isinstance(container, list) else _map(container).get("samples")
    matches = [s for s in items if isinstance(s, Mapping) and s.get("type") == kind] if isinstance(items, list) else []
    return matches[0] if len(matches) == 1 else {}, len(matches)


def _compatible_series(exercise, kind, hr, clean):
    series, count = _series(exercise, kind)
    values = series.get("values")
    valid = isinstance(values, list) and all(
        isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v >= 0
        for v in values
    )
    compatible = bool(clean and count == 1 and isinstance(values, list) and len(values) == len(hr.get("values", []))
                      and series.get("intervalMillis") == hr.get("intervalMillis"))
    return {"type": kind, "series_count": count, "slot_count": len(values) if isinstance(values, list) else 0,
            "interval_ms": series.get("intervalMillis") if _integer(series.get("intervalMillis"), positive=True) else None,
            "numeric_values_valid": valid, "same_slot_count_and_interval_as_hr": compatible,
            "eligible_for_unmodified_relative_pairing": compatible and valid,
            "common_time_origin_verified": False,
            "status": "STRUCTURALLY_COMPATIBLE_WITH_LIMITATIONS" if compatible and valid
            else "STRUCTURALLY_COMPATIBLE_VALUES_REQUIRE_REVIEW" if compatible else "REVIEW_REQUIRED"}


def build_api_pause_clock_inventory(exercise, session, *, feature_requested=False):
    """Separate duration-end pause markers from earlier intervals without certifying a clock.

    The original HR validator is left unchanged. Its strict exercise-stop
    boundary cannot interpret a pause marker at the timer's duration end.
    Duration sums and endpoint residuals are reported as a hypothesis only.
    """
    raw = exercise.get("pauseTimes")
    route_start = _time(_map(_map(exercise.get("routes")).get("route")).get("startTime"), exercise, session)
    duration = exercise.get("durationMillis")
    anchor = None
    if route_start is not None and _integer(duration, positive=True):
        try:
            anchor = route_start + timedelta(milliseconds=duration)
        except OverflowError:
            pass
    session_start = _time(session.get("startTime"), exercise, session)
    session_stop = _time(session.get("stopTime"), exercise, session)
    events, valid, invalid = [], [], 0
    if isinstance(raw, list):
        for index, item in enumerate(raw):
            item = _map(item)
            a = _time(item.get("startTime"), exercise, session)
            b = _time(item.get("endTime"), exercise, session)
            malformed = a is None or b is None or a >= b
            outside = False
            if not malformed and session_start is not None and session_stop is not None:
                try:
                    outside = a < session_start - timedelta(seconds=1) or b > session_stop + timedelta(seconds=1)
                except OverflowError:
                    outside = True
            if malformed or outside:
                invalid += 1
                role = "UNUSABLE_PAUSE_INTERVAL"
            elif anchor is None:
                role = "DURATION_ANCHOR_UNAVAILABLE"
                valid.append((a, b))
            else:
                valid.append((a, b))
                role = "AT_DURATION_END_ANCHOR" if a == anchor else (
                    "BEFORE_DURATION_END_ANCHOR" if b <= anchor else
                    "AFTER_DURATION_END_ANCHOR" if a > anchor else "CROSSES_DURATION_END_ANCHOR")
            events.append({"source_index": index, "start_timestamp_utc_as_reported": _iso(a),
                           "end_timestamp_utc_as_reported": _iso(b),
                           "duration_ms": _us(b-a)/1000 if not malformed else None,
                           "role": role, "outside_reported_session_precision_window": outside})
    elif "pauseTimes" in exercise:
        invalid = 1
    overlap = any(b > c for (_, b), (c, _) in zip(sorted(valid), sorted(valid)[1:]))
    out_of_order = any(a > c for (a, _), (c, _) in zip(valid, valid[1:]))
    merged = []
    for a, b in sorted(valid):
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
        else:
            merged.append((a, b))
    total_us = sum(_us(b-a) for a,b in valid)
    lifted_end = None
    if anchor is not None and isinstance(raw, list) and raw and not invalid:
        try:
            lifted_end = anchor + timedelta(microseconds=total_us)
        except OverflowError:
            pass
    residual_us = _us(lifted_end-session_stop) if lifted_end is not None and session_stop is not None else None
    result = {
        "status": "INVALID" if invalid else "REVIEW_REQUIRED" if overlap or out_of_order
        else "CHECKED_WITH_LIMITATIONS" if isinstance(raw, list) else "NOT_PROVIDED",
        "record_count": len(raw) if isinstance(raw, list) else 0,
        "invalid_record_count": invalid, "overlap_detected": overlap, "source_order_requires_review": out_of_order,
        "union_duration_ms": sum(_us(b-a) for a,b in merged)/1000,
        "pause_duration_sum_ms": total_us/1000,
        "before_duration_end_record_count": sum(e["role"]=="BEFORE_DURATION_END_ANCHOR" for e in events),
        "at_duration_end_record_count": sum(e["role"]=="AT_DURATION_END_ANCHOR" for e in events),
        "events": events, "feature_requested": feature_requested,
        "absence_is_proof_of_no_pause": False, "pause_clock_semantics_verified": False,
        "duration_end_anchor_from_route_start_utc": _iso(anchor),
        "reported_session_start_utc": _iso(session_start), "reported_session_stop_utc": _iso(session_stop),
        "session_clock_hypothesis": {
            "hypothesis_id": "ROUTE_START_PLUS_DURATION_PLUS_SUM_REPORTED_PAUSE_DURATIONS",
            "candidate_session_end_utc": _iso(lifted_end),
            "candidate_minus_reported_session_stop_ms": residual_us/1000 if residual_us is not None else None,
            "precision_comparison_tolerance_ms": 1000,
            "endpoint_within_precision_comparison": abs(residual_us)<=1_000_000 if residual_us is not None else None,
            "provider_rounding_rule_verified": False, "clock_semantics_verified": False,
            "applied_to_hr_or_gps_samples": False},
    }
    return result


def _clock(exercise, session, hr_slots, interval):
    route = _map(_map(exercise.get("routes")).get("route"))
    points = route.get("wayPoints")
    points = points if isinstance(points, list) else []
    start = _time(route.get("startTime"), exercise, session)
    reasons = []
    if start is None:
        reasons.append("ROUTE_START_UNUSABLE")
    if not points or len(points) > MAX_POINTS:
        reasons.append("ROUTE_POINTS_MISSING_OR_OVER_LIMIT")
    elapsed = [p.get("elapsedMillis") if isinstance(p, Mapping) else None for p in points]
    invalid = sum(not _integer(t) for t in elapsed)
    if invalid:
        reasons.append("ROUTE_ELAPSED_TIME_INVALID")
    nonincreasing = sum(b <= a for a, b in zip(elapsed, elapsed[1:])) if elapsed and not invalid else 0
    if nonincreasing:
        reasons.append("ROUTE_TIMES_NOT_STRICTLY_INCREASING")
    first = last = None
    if start is not None and elapsed and not invalid:
        try:
            first = start + timedelta(milliseconds=elapsed[0])
            last = start + timedelta(milliseconds=elapsed[-1])
        except OverflowError:
            reasons.append("ROUTE_TIMESTAMP_OVERFLOW")
    deltas = [b - a for a, b in zip(elapsed, elapsed[1:])] if elapsed and not invalid else []
    grid_error = max((abs(t - elapsed[0] - i * interval) for i, t in enumerate(elapsed)), default=None) if elapsed and not invalid and interval else None
    point_transfer = bool(not reasons and interval and len(points) == hr_slots
                          and grid_error is not None and grid_error <= ROUTE_GRID_TOLERANCE_MS)
    return {
        "status": "RECONSTRUCTED_FROM_DECLARED_API_ROUTE_CLOCK" if not reasons else "REVIEW_REQUIRED",
        "route_start_utc": _iso(start), "first_point_utc": _iso(first), "last_point_utc": _iso(last),
        "waypoint_count": len(points), "first_elapsed_ms": elapsed[0] if elapsed and not invalid else None,
        "last_elapsed_ms": elapsed[-1] if elapsed and not invalid else None,
        "invalid_elapsed_count": invalid, "nonincreasing_time_count": nonincreasing,
        "point_count_equals_hr_slot_count": len(points) == hr_slots,
        "uniform_grid_max_deviation_ms": grid_error,
        "uniform_grid_tolerance_ms": ROUTE_GRID_TOLERANCE_MS,
        "point_index_transfer_structurally_compatible": point_transfer,
        "hr_clock_transfer_verified": False,
        "absolute_wall_clock_timestamp_verified": False, "pause_clock_semantics_verified": False,
        "step_min_ms": min(deltas) if deltas else None, "step_max_ms": max(deltas) if deltas else None,
        "non_nominal_step_count": sum(t != interval for t in deltas) if interval else None,
        "step_histogram_ms": {str(k): v for k, v in sorted(Counter(deltas).items())[:64]},
        "blocking_reasons": reasons,
    }, start, first


def _candidate(name, first, start, stop, stop_value, slots, interval, assumption):
    last = None
    if first is not None:
        try:
            last = first + timedelta(milliseconds=(slots - 1) * interval)
        except OverflowError:
            return None
    if first is None or start is None or stop is None or last is None:
        return None
    # A reported whole second is compared as an interval, not as a claim about
    # Polar's rounding rule. No candidate is selected using this check.
    coarse_stop = isinstance(stop_value, str) and "." not in stop_value.split("T")[-1]
    try:
        upper = stop + timedelta(microseconds=1_000_000 if coarse_stop else 1)
    except OverflowError:
        return None
    return {
        "candidate_id": name, "status": "UNVERIFIED_HR_ORIGIN_HYPOTHESIS",
        "first_sample_timestamp_utc": _iso(first), "last_sample_timestamp_utc": _iso(last),
        "first_sample_offset_from_reported_exercise_start_us": _us(first - start),
        "sample_count": slots, "interval_ms": interval,
        "inside_reported_exercise_window_under_precision_policy": start <= first <= last < upper,
        "assumption": assumption, "api_native_time_origin_verified": False,
        "clock_convention": "UNIFORM_ELAPSED_GRID_HYPOTHESIS_BEFORE_PAUSE_ADJUSTMENT",
        "sample_values_modified": False, "selected_for_downstream_use": False,
    }


def _exercise(exercise, route_exercise, sample_session, route_session, technical, features):
    reasons = []
    for key in ("startTime", "stopTime", "durationMillis"):
        if exercise.get(key) != route_exercise.get(key):
            reasons.append("SAMPLE_ROUTE_" + key.upper() + "_MISMATCH")
    start = _time(exercise.get("startTime"), exercise, sample_session)
    stop = _time(exercise.get("stopTime"), exercise, sample_session)
    route_exercise_start = _time(route_exercise.get("startTime"), route_exercise, route_session)
    route_exercise_stop = _time(route_exercise.get("stopTime"), route_exercise, route_session)
    if start is None or stop is None or start >= stop:
        reasons.append("EXERCISE_CLOCK_UNUSABLE")
    if (start, stop) != (route_exercise_start, route_exercise_stop):
        reasons.append("SAMPLE_ROUTE_UTC_METADATA_MISMATCH")
    hr, hr_count = _series(exercise, "HEART_RATE")
    unknown_fields = sorted(str(k) for k in hr if k not in {"type", "intervalMillis", "values"})
    if unknown_fields:
        reasons.append("UNRECOGNIZED_HR_SERIES_FIELDS_REQUIRE_REVIEW")
    values = hr.get("values")
    slots = len(values) if isinstance(values, list) else 0
    interval = hr.get("intervalMillis")
    interval = interval if _integer(interval, positive=True) else None
    clean = technical.get("technical_status") == "TECHNICALLY_CLEAN_WITH_LIMITATIONS"
    if not clean:
        reasons.extend(technical.get("technical_blocking_reasons", ["HR_SERIES_NOT_TECHNICALLY_CLEAN"]))
        if not reasons:
            reasons.append("HR_SERIES_NOT_TECHNICALLY_CLEAN")
    if slots > MAX_POINTS:
        reasons.append("HR_SLOT_LIMIT")
    compatibility = [_compatible_series(exercise, kind, hr, clean) for kind in ("SPEED", "DISTANCE")]
    clock, route_start, first_point = _clock(route_exercise, route_session, slots, interval)
    candidates = []
    if not reasons and slots >= 2 and interval and not clock["blocking_reasons"]:
        definitions = [("PROJECT_EXERCISE_ZERO", start, "FIRST_HR_SLOT_AT_REPORTED_EXERCISE_START")]
        if route_start is not None:
            try:
                definitions.append(("API_ROUTE_START_PLUS_ONE_INTERVAL", route_start + timedelta(milliseconds=interval),
                                    "HR_FIRST_SLOT_ONE_PERIOD_AFTER_ROUTE_START_NOT_DOCUMENTED_BY_INTERVALVALUES"))
            except OverflowError:
                pass
        if clock["point_index_transfer_structurally_compatible"]:
            definitions.append(("API_ROUTE_FIRST_POINT_REGULAR_GRID", first_point,
                                "COMMON_HR_AND_GPS_ARRAY_ORIGIN_NOT_DOCUMENTED_BY_INTERVALVALUES"))
        for name, first, assumption in definitions:
            candidate = _candidate(name, first, start, stop, exercise.get("stopTime"), slots, interval, assumption)
            if candidate is not None:
                candidates.append(candidate)
    legacy_pauses = technical.get("timebase", {}).get("pause_inventory", {})
    pauses = build_api_pause_clock_inventory(exercise, sample_session, feature_requested="pause-times" in features)
    return {
        "exercise_external_id": _identifier(exercise),
        "status": "API_TIMEBASE_AUDITED_WITH_LIMITATIONS" if not reasons else "REVIEW_REQUIRED",
        "exercise_start_utc": _iso(start), "exercise_stop_utc": _iso(stop),
        "declared_duration_ms": exercise.get("durationMillis"),
        "hr_series_count": hr_count, "hr_slot_count": slots, "hr_interval_ms": interval,
        "unrecognized_hr_series_fields": unknown_fields,
        "hr_values_technically_clean": clean,
        "hr_time_origin_status": "NOT_EXPLICITLY_PROVIDED_BY_INTERVALVALUES",
        "relative_series_compatibility": compatibility,
        "gps_clock": clock,
        "pause_inventory": pauses,
        "legacy_hr_validation_pause_inventory": legacy_pauses,
        "candidate_hr_timebases": candidates, "selected_hr_timebase": None,
        "absolute_hr_time_mapping_verified": False, "pause_clock_semantics_verified": False,
        "blocking_reasons": sorted(set(reasons)),
        "limitations": ["API_HR_FIRST_TIMESTAMP_NOT_EXPLICIT", "HR_GPS_SHARED_ORIGIN_NOT_VERIFIED",
                        "HR_SPEED_SHARED_ORIGIN_NOT_VERIFIED", "PAUSE_CLOCK_SEMANTICS_NOT_VERIFIED",
                        "MISSING_PAUSE_FIELD_IS_NOT_PROOF_OF_NO_PAUSE"],
    }


def build_api_hr_timebase_audit(sample_session, route_session, *, expected_session_external_id,
                              sample_session_match_count, route_session_match_count,
                              expected_exercise_external_id=None, requested_features=()):
    sample, route = _map(sample_session), _map(route_session)
    features = sorted(set(requested_features))
    context = {"sample_session": sample, "route_session": route,
               "expected_session_external_id": expected_session_external_id,
               "sample_session_match_count": sample_session_match_count,
               "route_session_match_count": route_session_match_count,
               "expected_exercise_external_id": expected_exercise_external_id,
               "requested_features": features}
    source_hash = _hash(context)
    reasons = []
    sid = _id(expected_session_external_id)
    if sid is None or _identifier(sample) != sid or _identifier(route) != sid:
        reasons.append("SESSION_SOURCE_IDENTITY_MISMATCH")
    if type(sample_session_match_count) is not int or type(route_session_match_count) is not int or sample_session_match_count != 1 or route_session_match_count != 1:
        reasons.append("SESSION_SOURCE_MISSING_OR_AMBIGUOUS")
    if source_hash is None:
        reasons.append("SOURCE_NOT_BOUNDED_CANONICAL_JSON")
    samples, routes = sample.get("exercises"), route.get("exercises")
    sample_ids = [_identifier(e) for e in samples] if isinstance(samples, list) else []
    route_ids = [_identifier(e) for e in routes] if isinstance(routes, list) else []
    if not sample_ids or len(sample_ids) > MAX_EXERCISES or None in sample_ids or len(sample_ids) != len(set(sample_ids)):
        reasons.append("SAMPLE_EXERCISES_MISSING_OR_AMBIGUOUS")
    if not route_ids or len(route_ids) > MAX_EXERCISES or None in route_ids or len(route_ids) != len(set(route_ids)) or set(sample_ids) != set(route_ids):
        reasons.append("ROUTE_EXERCISE_IDENTITY_MISMATCH")
    selector = _id(expected_exercise_external_id)
    if expected_exercise_external_id is not None and selector not in sample_ids:
        reasons.append("EXPECTED_EXERCISE_NOT_FOUND")
    exercises = []
    if not reasons:
        validation = build_training_session_heart_rate_validation(
            sample, expected_session_external_id=sid, sample_session_match_count=sample_session_match_count)
        by_route = {_identifier(e): e for e in routes}
        for index, exercise in enumerate(samples):
            if selector is None or sample_ids[index] == selector:
                exercises.append(_exercise(exercise, by_route[sample_ids[index]], sample, route,
                                           validation["exercises"][index], features))
    result = {
        "provider": "PADDLETRAINER", "schema_version": "0.1", "audit_version": AUDIT_VERSION,
        "session_external_id": sid,
        "status": "WITHHELD" if reasons else "API_TIMEBASE_AUDITED_WITH_LIMITATIONS",
        "source_binding_verified": not reasons,
        "input_provenance": {"source_hash": source_hash, "requested_features": features},
        "exercise_count": len(exercises), "exercises": exercises,
        "blocking_reasons": sorted(set(reasons)),
        "api_native_time_origin_verified": False, "export_timebase_verified": False,
        "pause_clock_semantics_verified": False, "acquisition_quality_verified": False,
        "training_authorized": False, "numeric_prediction_authorized": False,
        "policy": {"read_only": True, "science_storage_writes": 0,
                   "environment_provider_calls": 0, "sample_values_modified": False,
                   "missing_values_interpolated": False, "automatic_candidate_selection": False,
                   "hr_speed_correlation_used_to_fit_clock": False,
                   "physiological_delay_estimated": False, "changes_existing_export_evidence": False,
                   "model_fit_performed": False, "test_scoring_performed": False,
                   "documentation_url": DOC_URL,
                   "route_clock_rule": "ROUTE_START_PLUS_DECLARED_ELAPSED_MILLIS",
                   "hr_contract": "INTERVAL_AND_VALUES_WITHOUT_EXPLICIT_FIRST_TIMESTAMP",
                   "coarse_exercise_window_rule": "WHOLE_REPORTED_STOP_SECOND_ALLOWED_NOT_PROVIDER_ROUNDING_PROOF"},
    }
    result["audit_hash"] = _hash(result)
    return result


def verify_api_hr_timebase_audit(audit, sample_session, route_session, **context):
    try:
        expected = build_api_hr_timebase_audit(sample_session, route_session, **context)
        return isinstance(audit, Mapping) and expected["audit_hash"] is not None and dict(audit) == expected
    except (TypeError, ValueError, KeyError, OverflowError):
        return False
