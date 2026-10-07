"""Localize recorded HR patterns without certifying acquisition or physiology.

Absolute timestamps come only from current, owner-bound export evidence. Without
that proof, positions are indices and offsets from the first recorded HR slot.
The V24.2 validator and all existing export/declaration evidence stay independent.
"""

import hashlib
import heapq
import json
import math
from collections import Counter
from collections.abc import Mapping
from copy import deepcopy
from functools import partial

from app.services.heart_rate_sample_validation import (
    _value_category,
    build_training_session_heart_rate_validation,
)
from app.services.hr_acquisition_declarations import resolve_hr_acquisition_declarations
from app.services.hr_timebase_snapshot import resolve_hr_timebase_snapshots

DIAGNOSTICS_VERSION = "0.1.0"
DEFAULT_DETAIL_LIMIT = 25
MAX_DETAIL_LIMIT = 100
MAX_DIAGNOSTIC_SLOTS = 100_000
MAX_DIAGNOSTIC_EXERCISES = 64
INVALID_CATEGORIES = ("MISSING", "BOOLEAN", "NON_NUMERIC", "NON_FINITE", "ZERO", "NEGATIVE")


def build_training_session_hr_signal_diagnostics(
    sample_session,
    *,
    athlete_id,
    session_external_id,
    sample_session_match_count,
    hr_timebase_snapshots=None,
    hr_acquisition_declarations=None,
    detail_limit=DEFAULT_DETAIL_LIMIT,
):
    """Describe all slots; bound only returned detail, never the aggregate counts."""
    if type(detail_limit) is not int or not 1 <= detail_limit <= MAX_DETAIL_LIMIT:
        raise ValueError("Diagnostic detail limit must be an integer from 1 to 100.")
    result = {
        "provider": "PADDLETRAINER",
        "schema_version": "0.1",
        "diagnostics_version": DIAGNOSTICS_VERSION,
        "session_external_id": _id(session_external_id),
        "status": "WITHHELD",
        "source_binding_verified": False,
        "available": False,
        "exercise_count": 0,
        "diagnosed_exercise_count": 0,
        "verified_clock_exercise_count": 0,
        "detail_limit": detail_limit,
        "acquisition_quality_verified": False,
        "artifact_detector_validated": False,
        "training_authorized": False,
        "numeric_prediction_authorized": False,
        "blocking_reasons": [],
        "limitations": [
            "DESCRIPTIVE_PATTERNS_ARE_NOT_VALIDATED_ARTIFACT_DETECTION",
            "HR_ACQUISITION_QUALITY_NOT_ESTABLISHED",
            "API_NATIVE_SAMPLE_CLOCK_SEMANTICS_NOT_VERIFIED",
            "HR_PAUSE_CLOCK_SEMANTICS_NOT_VERIFIED",
        ],
        "input_provenance": {
            "athlete_id": _id(athlete_id),
            "source_provider": "POLAR",
            "api_source_hash": None,
            "raw_validation_decision_hash": None,
        },
        "policy": {
            "read_only": True,
            "persists_diagnostics": False,
            "recorded_samples_modified": False,
            "missing_samples_interpolated": False,
            "physiological_threshold_configured": False,
            "change_threshold_configured": False,
            "constant_run_minimum_slots": 2,
            "constant_run_minimum_is_a_pattern_definition": True,
            "detail_limit_does_not_limit_analysis": True,
            "invalid_run_selection": "FIRST_IN_SAMPLE_ORDER",
            "constant_run_selection": "LONGEST_THEN_FIRST_INDEX",
            "change_selection": "LARGEST_ABSOLUTE_CHANGE_THEN_FIRST_INDEX",
            "unverified_origin_assumed_zero": False,
            "utc_requires_current_owned_export_proof": True,
            "nominal_occupancy_is_not_observed_duration": True,
            "promotes_training_data_readiness": False,
        },
        "exercises": [],
    }
    raw = _mapping(sample_session)
    exercises = raw.get("exercises")
    if isinstance(exercises, list):
        slot_count = sum(
            len(s.get("values", []))
            for exercise in exercises
            for s in _hr_series(exercise)
            if isinstance(s.get("values"), list)
        )
        if len(exercises) > MAX_DIAGNOSTIC_EXERCISES or slot_count > MAX_DIAGNOSTIC_SLOTS:
            result["blocking_reasons"] = ["HR_DIAGNOSTICS_SOURCE_LIMIT_EXCEEDED"]
            return _finish(result)
    validation = build_training_session_heart_rate_validation(
        sample_session,
        expected_session_external_id=session_external_id,
        sample_session_match_count=sample_session_match_count,
    )
    result["input_provenance"].update(
        api_source_hash=validation["input_provenance"]["source_hash"],
        raw_validation_decision_hash=validation["decision_hash"],
    )
    result["blocking_reasons"] = list(validation["blocking_reasons"])
    if _id(athlete_id) is None:
        result["blocking_reasons"].append("HR_DIAGNOSTICS_OWNER_MISSING")
    if result["blocking_reasons"]:
        return _finish(result)
    result["source_binding_verified"] = True
    clocks = resolve_hr_timebase_snapshots(
        hr_timebase_snapshots,
        sample_session,
        athlete_id=athlete_id,
        session_external_id=session_external_id,
        sample_session_match_count=sample_session_match_count,
    )
    acquisition = resolve_hr_acquisition_declarations(
        hr_acquisition_declarations,
        sample_session,
        athlete_id=athlete_id,
        session_external_id=session_external_id,
        sample_session_match_count=sample_session_match_count,
    )
    result["timebase_evidence"] = {k: v for k, v in clocks.items() if k != "by_exercise"}
    result["acquisition_evidence"] = {
        k: deepcopy(v) for k, v in acquisition.items() if k not in ("by_exercise", "exercises")
    }
    identities = [_identifier(exercise) for exercise in exercises]
    for index, (exercise, technical) in enumerate(zip(exercises, validation["exercises"])):
        identity = identities[index]
        reasons = list(technical["technical_blocking_reasons"])
        if identity is None or identities.count(identity) != 1:
            reasons.append("HR_DIAGNOSTICS_EXERCISE_IDENTITY_MISSING_OR_AMBIGUOUS")
        series = _hr_series(exercise)
        selected = series[0] if len(series) == 1 else {}
        period = selected.get("intervalMillis")
        period = period if type(period) is int and 0 < period <= 2**63 - 1 else None
        recorded = selected.get("values")
        recorded = recorded if isinstance(recorded, list) else []
        binding = (
            identity is not None
            and identities.count(identity) == 1
            and technical["technical_status"] != "WITHHELD"
            and len(series) == 1
        )
        clock = clocks["by_exercise"].get(identity, {}) if binding else {}
        clock_summary = _clock_summary(clock, clocks["blocking_reasons"], period, len(recorded))
        sensor = acquisition["by_exercise"].get(identity, {}) if binding else {}
        entry = {
            "exercise_index": index,
            "exercise_external_id": identity,
            "status": "DESCRIPTIVE_DIAGNOSTICS_WITH_LIMITATIONS" if binding else "WITHHELD",
            "source_binding_verified": binding,
            "available": binding and bool(recorded),
            "technical_status": technical["technical_status"],
            "technical_blocking_reasons": list(dict.fromkeys(reasons)),
            "technical_limitations": list(technical["limitations"]),
            "interval_ms": period,
            "slot_count": len(recorded) if binding else None,
            "positive_finite_sample_count": None,
            "invalid_or_missing_sample_count": None,
            "invalid_category_counts": None,
            "adjacent_valid_pair_count": None,
            "observed_nonzero_change_pair_count": None,
            "timebase": clock_summary,
            "acquisition_context": _sensor_summary(sensor),
            "acquisition_quality_verified": False,
            "artifact_status": "NOT_ASSESSED",
            "physiological_plausibility_status": "NOT_ASSESSED",
            "training_authorized": False,
            "numeric_prediction_authorized": False,
            "input_provenance": {"hr_series_hash": _hash(selected) if binding else None},
            "observations": {
                key: _packet([], None, selection)
                for key, selection in (
                    ("invalid_runs", "FIRST_IN_SAMPLE_ORDER"),
                    ("constant_runs", "LONGEST_THEN_FIRST_INDEX"),
                    ("largest_adjacent_changes", "LARGEST_ABSOLUTE_CHANGE_THEN_FIRST_INDEX"),
                )
            },
        }
        if binding and recorded:
            categories = [_value_category(value) for value in recorded]
            positive = [c == "POSITIVE_FINITE" for c in categories]
            entry.update(
                positive_finite_sample_count=sum(positive),
                invalid_or_missing_sample_count=len(recorded) - sum(positive),
                invalid_category_counts={c: categories.count(c) for c in INVALID_CATEGORIES},
                adjacent_valid_pair_count=sum(
                    positive[i - 1] and positive[i] for i in range(1, len(recorded))
                ),
            )
            times = clock.get("timebase", {}).get("sample_timestamps_utc", [])
            if not clock_summary["time_mapping_available"]:
                times = []
            position = partial(_position, period=period, times=times, clock=clock_summary)
            invalid = _invalid_runs(categories)
            constants = _constant_runs(recorded, positive)
            nonzero_count = sum(1 for _ in _changes(recorded, positive))
            largest = heapq.nsmallest(
                detail_limit, _changes(recorded, positive), key=lambda p: (-p[0], p[1])
            )
            entry["observed_nonzero_change_pair_count"] = nonzero_count
            entry["observations"] = {
                "invalid_runs": _packet(
                    [
                        {**position(a, b), "category_counts": dict(Counter(categories[a:b]))}
                        for a, b in invalid[:detail_limit]
                    ],
                    len(invalid),
                    "FIRST_IN_SAMPLE_ORDER",
                ),
                "constant_runs": _packet(
                    [
                        {**position(a, b), "recorded_bpm": float(recorded[a])}
                        for a, b in heapq.nsmallest(
                            detail_limit, constants, key=lambda p: (-(p[1] - p[0]), p[0])
                        )
                    ],
                    len(constants),
                    "LONGEST_THEN_FIRST_INDEX",
                ),
                "largest_adjacent_changes": _packet(
                    [
                        {
                            **position(i - 1, i + 1),
                            "from_bpm": float(recorded[i - 1]),
                            "to_bpm": float(recorded[i]),
                            "signed_change_bpm": _finite(recorded[i] - recorded[i - 1]),
                            "absolute_change_bpm": magnitude,
                            "absolute_change_bpm_per_nominal_second": _finite(
                                magnitude / (period / 1000)
                            )
                            if period
                            else None,
                        }
                        for magnitude, i in largest
                    ],
                    nonzero_count,
                    "LARGEST_ABSOLUTE_CHANGE_THEN_FIRST_INDEX",
                ),
            }
            if reasons:
                entry["status"] = "DIAGNOSTICS_WITH_TECHNICAL_ISSUES"
        elif binding:
            entry["status"] = "UNAVAILABLE"
        result["exercises"].append(entry)
    result["exercise_count"] = len(result["exercises"])
    result["diagnosed_exercise_count"] = sum(e["available"] for e in result["exercises"])
    result["verified_clock_exercise_count"] = sum(
        e["timebase"]["time_mapping_available"] for e in result["exercises"]
    )
    result["available"] = bool(result["diagnosed_exercise_count"])
    result["status"] = (
        "DIAGNOSTICS_WITH_TECHNICAL_ISSUES"
        if any(
            e["status"] in ("WITHHELD", "DIAGNOSTICS_WITH_TECHNICAL_ISSUES")
            for e in result["exercises"]
        )
        else "DESCRIPTIVE_DIAGNOSTICS_WITH_LIMITATIONS"
        if result["available"]
        else "UNAVAILABLE"
    )
    return _finish(result)


def build_hr_segment_diagnostics(raw_exercise, exercise_diagnostics, *, saved_clock, windows):
    """Attach verified export-grid observations to half-open exercise windows.

    All prefixes are built once per route. An absent/stale clock never supplies
    assumed exercise-zero timestamps. This function does not change eligibility.
    """
    report = _mapping(exercise_diagnostics)
    clock_summary = _mapping(report.get("timebase"))
    series = _hr_series(raw_exercise)
    selected = series[0] if len(series) == 1 else {}
    valid_source = (
        report.get("source_binding_verified") is True
        and report.get("exercise_external_id") == _identifier(raw_exercise)
        and _hash(selected) == _mapping(report.get("input_provenance")).get("hr_series_hash")
    )
    timebase = _mapping(_mapping(saved_clock).get("timebase"))
    mapped = (
        valid_source
        and clock_summary.get("time_mapping_available") is True
        and _mapping(saved_clock).get("export_timebase_verified") is True
        and _hash(timebase) == clock_summary.get("export_grid_hash")
    )
    recorded = selected.get("values", []) if valid_source else []
    period = selected.get("intervalMillis")
    categories = [_value_category(v) for v in recorded] if mapped else []
    prefixes = {}
    if mapped:
        flags = [c == "POSITIVE_FINITE" for c in categories]
        for key in (
            *INVALID_CATEGORIES,
            "POSITIVE_FINITE",
            "VALID_PAIR",
            "CHANGED_PAIR",
            "CONSTANT_PAIR",
        ):
            counts = [0]
            for i, category in enumerate(categories):
                pair = i > 0 and flags[i - 1] and flags[i]
                observed = (
                    pair
                    if key == "VALID_PAIR"
                    else pair and recorded[i] != recorded[i - 1]
                    if key == "CHANGED_PAIR"
                    else pair and recorded[i] == recorded[i - 1]
                    if key == "CONSTANT_PAIR"
                    else category == key
                )
                counts.append(counts[-1] + int(observed))
            prefixes[key] = counts
    output = []
    for window in windows:
        window = _mapping(window)
        start, end = window.get("start_exercise_elapsed_ms"), window.get("end_exercise_elapsed_ms")
        entry = {
            "order_index": window.get("order_index"),
            "status": "TIMEBASE_NOT_VERIFIED" if valid_source else "SOURCE_NOT_APPLIED",
            "source_binding_verified": valid_source,
            "mapped_to_verified_export_clock": mapped,
            "start_exercise_elapsed_ms": start,
            "end_exercise_elapsed_ms": end,
            "first_grid_slot_index": None,
            "stop_grid_slot_index_exclusive": None,
            "expected_grid_slot_count": None,
            "recorded_grid_slot_count": None,
            "positive_finite_sample_count": None,
            "invalid_category_counts": None,
            "unrecorded_grid_slot_count": None,
            "adjacent_valid_pair_count": None,
            "observed_nonzero_change_pair_count": None,
            "observed_constant_pair_count": None,
            "first_recorded_timestamp_utc": None,
            "last_recorded_timestamp_utc": None,
            "acquisition_quality_verified": False,
            "artifact_status": "NOT_ASSESSED",
        }
        if mapped:
            duration = _mapping(raw_exercise).get("durationMillis")
            if not (
                type(start) is int
                and type(end) is int
                and 0 <= start < end
                and type(duration) is int
                and end <= duration
            ):
                entry["status"] = "INVALID_WINDOW"
                entry["mapped_to_verified_export_clock"] = False
            else:
                step = period * 1000
                origin = timebase["first_sample_offset_from_api_exercise_start_us"]
                first = max(0, -(-(start * 1000 - origin) // step))
                stop = max(0, -(-(end * 1000 - origin) // step))
                a, b = min(first, len(recorded)), min(stop, len(recorded))
                expected = stop - first
                positive = prefixes["POSITIVE_FINITE"][b] - prefixes["POSITIVE_FINITE"][a]
                pair_start = min(a + 1, b)
                times = timebase["sample_timestamps_utc"]
                entry.update(
                    status="NO_GRID_SLOTS"
                    if not expected
                    else "COMPLETE_WITH_LIMITATIONS"
                    if positive == expected
                    else "PARTIAL_WITH_LIMITATIONS"
                    if positive
                    else "NO_POSITIVE_FINITE_SAMPLES",
                    first_grid_slot_index=first,
                    stop_grid_slot_index_exclusive=stop,
                    expected_grid_slot_count=expected,
                    recorded_grid_slot_count=b - a,
                    positive_finite_sample_count=positive,
                    invalid_category_counts={
                        c: prefixes[c][b] - prefixes[c][a] for c in INVALID_CATEGORIES
                    },
                    unrecorded_grid_slot_count=expected - (b - a),
                    adjacent_valid_pair_count=prefixes["VALID_PAIR"][b]
                    - prefixes["VALID_PAIR"][pair_start],
                    observed_nonzero_change_pair_count=prefixes["CHANGED_PAIR"][b]
                    - prefixes["CHANGED_PAIR"][pair_start],
                    observed_constant_pair_count=prefixes["CONSTANT_PAIR"][b]
                    - prefixes["CONSTANT_PAIR"][pair_start],
                    first_recorded_timestamp_utc=times[a] if b > a else None,
                    last_recorded_timestamp_utc=times[b - 1] if b > a else None,
                )
        output.append(entry)
    return output


def summarize_hr_signal_diagnostics(report):
    return {
        k: deepcopy(v)
        for k, v in report.items()
        if k not in ("exercises", "acquisition_evidence", "timebase_evidence")
    }


def summarize_hr_exercise_diagnostics(entry, windows, *, detail_limit=DEFAULT_DETAIL_LIMIT):
    result = {k: deepcopy(v) for k, v in entry.items() if k != "observations"}
    result["observation_counts"] = {
        key: packet["total_count"] for key, packet in entry.get("observations", {}).items()
    }
    result["window_count"] = len(windows)
    result["window_status_counts"] = dict(Counter(window["status"] for window in windows))
    incomplete = [w for w in windows if w["status"] != "COMPLETE_WITH_LIMITATIONS"]
    result["windows_requiring_coverage_review"] = _packet(
        deepcopy(incomplete[:detail_limit]), len(incomplete), "FIRST_IN_ROUTE_ORDER"
    )
    return result


def _clock_summary(clock, reasons, period, slot_count):
    source = _mapping(clock.get("timebase"))
    verified = (
        clock.get("export_timebase_verified") is True
        and source.get("interval_ms") == period
        and source.get("sample_count") == slot_count
    )
    return {
        "status": "VERIFIED_SAVED_EXPORT_TIMEBASE" if verified else "NOMINAL_SAMPLE_GRID_ONLY",
        "time_mapping_available": verified,
        "snapshot_id": clock.get("snapshot_id") if verified else None,
        "snapshot_hash": clock.get("snapshot_hash") if verified else None,
        "verification_decision_hash": clock.get("verification_decision_hash") if verified else None,
        "export_grid_hash": _hash(source) if verified else None,
        "first_sample_offset_from_api_exercise_start_us": source.get(
            "first_sample_offset_from_api_exercise_start_us"
        )
        if verified
        else None,
        "first_sample_timestamp_utc": source.get("first_sample_timestamp_utc")
        if verified
        else None,
        "last_sample_timestamp_utc": source.get("last_sample_timestamp_utc") if verified else None,
        "native_clock_semantics_verified": False,
        "pause_clock_semantics_verified": False,
        "blocking_reasons": list(clock.get("blocking_reasons", reasons)),
    }


def _sensor_summary(sensor):
    known = sensor.get("source_binding_verified") is True and sensor.get("status") not in (
        "WITHHELD",
        "REVIEW_REQUIRED",
    )
    return {
        "status": sensor.get("status", "NOT_DECLARED"),
        "source_binding_verified": sensor.get("source_binding_verified", False),
        "declaration_source": sensor.get("declaration_source") if known else None,
        "active_declaration_ids": deepcopy(sensor.get("active_declaration_ids", [])),
        "declared_sensor": deepcopy(sensor.get("declared_sensor")) if known else None,
        "reported_issue_codes": deepcopy(sensor.get("reported_issue_codes", [])) if known else [],
        "blocking_reasons": deepcopy(sensor.get("blocking_reasons", [])),
        "sensor_identity_verified": False,
        "acquisition_quality_verified": False,
    }


def _position(first, stop, period, times, clock):
    mapped = bool(times)
    origin = clock["first_sample_offset_from_api_exercise_start_us"] if mapped else None
    return {
        "start_sample_index": first,
        "end_sample_index_exclusive": stop,
        "sample_count": stop - first,
        "nominal_first_sample_offset_ms": first * period if period else None,
        "nominal_last_sample_offset_ms": (stop - 1) * period if period else None,
        "nominal_slot_occupancy_ms": (stop - first) * period if period else None,
        "sample_span_ms": (stop - first - 1) * period if period else None,
        "first_sample_timestamp_utc": times[first] if mapped else None,
        "last_sample_timestamp_utc": times[stop - 1] if mapped else None,
        "first_sample_offset_from_exercise_start_us": origin + first * period * 1000
        if mapped
        else None,
        "last_sample_offset_from_exercise_start_us": origin + (stop - 1) * period * 1000
        if mapped
        else None,
        "time_mapping_available": mapped,
        "observation_kind": "DESCRIPTIVE_RECORDED_PATTERN",
    }


def _invalid_runs(categories):
    result = []
    first = None
    for i, category in enumerate([*categories, "POSITIVE_FINITE"]):
        if category != "POSITIVE_FINITE" and first is None:
            first = i
        elif category == "POSITIVE_FINITE" and first is not None:
            result.append((first, i))
            first = None
    return result


def _constant_runs(recorded, positive):
    runs = []
    first = 0
    for i in range(1, len(recorded) + 1):
        if i < len(recorded) and positive[i] and positive[i - 1] and recorded[i] == recorded[i - 1]:
            continue
        if i - first >= 2 and positive[first]:
            runs.append((first, i))
        first = i
    return runs


def _changes(recorded, positive):
    for i in range(1, len(recorded)):
        if positive[i - 1] and positive[i]:
            magnitude = _finite(abs(recorded[i] - recorded[i - 1]))
            if magnitude:
                yield magnitude, i


def _packet(items, total, selection):
    return {
        "assessed": total is not None,
        "total_count": total,
        "returned_count": len(items),
        "truncated": total is not None and len(items) < total,
        "selection": selection,
        "items": items,
    }


def _hr_series(exercise):
    container = _mapping(exercise).get("samples")
    series = container if isinstance(container, list) else _mapping(container).get("samples")
    return (
        [s for s in series if isinstance(s, Mapping) and s.get("type") == "HEART_RATE"]
        if isinstance(series, list)
        else []
    )


def _mapping(value):
    return value if isinstance(value, Mapping) else {}


def _identifier(value):
    return _id(_mapping(_mapping(value).get("identifier")).get("id"))


def _id(value):
    return (
        str(value)
        if isinstance(value, (str, int)) and not isinstance(value, bool) and str(value).strip()
        else None
    )


def _finite(value):
    try:
        return float(value) if math.isfinite(value) else None
    except (ValueError, TypeError, OverflowError):
        return None


def _hash(value):
    try:
        return hashlib.sha256(
            json.dumps(
                value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
            ).encode()
        ).hexdigest()
    except (ValueError, TypeError, OverflowError):
        return None


def _finish(result):
    result["decision_hash"] = _hash(result)
    return result
