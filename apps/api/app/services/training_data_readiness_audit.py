from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any

from app.services.hr_timebase_snapshot import resolve_hr_timebase_snapshots
from app.services.hr_acquisition_declarations import resolve_hr_acquisition_declarations
from app.services.polar_training_samples import normalize_polar_training_samples
from app.services.route_expected_response_model import build_route_expected_response_model

AUDIT_VERSION = "0.3.0"
LIMITATIONS = [
    "HR_SAMPLE_TIME_ORIGIN_NOT_VERIFIED",
    "HR_ACQUISITION_QUALITY_NOT_ESTABLISHED",
    "HISTORICAL_FEATURE_AVAILABILITY_NOT_ESTABLISHED",
    "DATASET_SPLIT_NOT_ASSIGNED",
    "RETROSPECTIVE_GPS_IS_NOT_A_PRE_EXERCISE_PREDICTOR",
]


def build_route_training_data_readiness_audit(
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
) -> dict[str, Any]:
    """Audit retrospective HR label candidates; never authorize model training.

    A current, athlete-bound export proof supplies this exercise's grid origin.
    Without it, sample zero at exercise zero is an unverified project convention.
    Raw provider identities are matched before looking up normalized series.
    """
    source = _mapping(expected_response_input)
    samples = _mapping(normalized_samples)
    raw_route, raw_sample = _mapping(route_session), _mapping(sample_session)
    timebase_resolution = resolve_hr_timebase_snapshots(
        hr_timebase_snapshots,
        raw_sample,
        athlete_id=athlete_id,
        session_external_id=session_external_id,
        sample_session_match_count=sample_session_match_count,
    )
    acquisition_resolution = resolve_hr_acquisition_declarations(
        hr_acquisition_declarations, raw_sample, athlete_id=athlete_id,
        session_external_id=session_external_id,
        sample_session_match_count=sample_session_match_count,
    )
    boundary = build_route_expected_response_model(source)
    identity, athlete = _id(session_external_id), _id(athlete_id)
    reasons = []
    if identity is None or identity != _identifier(raw_route):
        reasons.append("SESSION_IDENTITY_UNVERIFIABLE")
    if athlete is None:
        reasons.append("ATHLETE_IDENTITY_MISSING")
    if not _integer(sample_session_match_count) or sample_session_match_count != 1:
        reasons.append("SAMPLE_SESSION_MISSING_OR_AMBIGUOUS")
    if identity is None or identity != _identifier(raw_sample):
        reasons.append("SAMPLE_SESSION_IDENTITY_MISMATCH")
    # Reproduce the normalization instead of trusting claimed counts/indices.
    reproduced = normalize_polar_training_samples({"exerciseSamples": raw_sample.get("exercises")})
    if samples.get("provider") != "POLAR" or samples != reproduced:
        reasons.append("NORMALIZED_SAMPLES_SOURCE_MISMATCH")
    source_hash = _hash(
        {
            "expected_response_input": source,
            "normalized_samples": samples,
            "route_session": raw_route,
            "sample_session": raw_sample,
            "sample_session_match_count": sample_session_match_count,
            "session_external_id": session_external_id,
            "athlete_id": athlete_id,
            "hr_timebase_snapshots": hr_timebase_snapshots,
            "hr_acquisition_declarations": hr_acquisition_declarations,
        }
    )
    if source_hash is None:
        reasons.append("AUDIT_SOURCE_NOT_CANONICAL_JSON")
    route_exercises, sample_exercises = (
        _list(raw_route.get("exercises")),
        _list(raw_sample.get("exercises")),
    )
    series = _list(samples.get("series"))
    routes = []
    input_routes = [r for r in _list(source.get("routes")) if isinstance(r, Mapping)]
    for input_route, model_route in zip(input_routes, boundary["routes"]):
        input_route = _mapping(input_route)
        blockers = [*reasons, *model_route["input_blocking_reasons"]]
        index = input_route.get("exercise_index")
        exercise = (
            _mapping(route_exercises[index])
            if _integer(index) and index < len(route_exercises)
            else {}
        )
        matched_index, match_basis, match_reasons = _match_exercise(
            exercise, route_exercises, sample_exercises, raw_route, raw_sample
        )
        blockers.extend(match_reasons)
        hr = [
            s
            for s in series
            if isinstance(s, Mapping)
            and s.get("metric_key") == "heart_rate_bpm"
            and s.get("exercise_index") == matched_index
            and matched_index is not None
        ]
        if len(hr) != 1:
            blockers.append("HEART_RATE_SERIES_MISSING_OR_AMBIGUOUS")
        hr_series = _mapping(hr[0]) if len(hr) == 1 else {}
        interval, values = hr_series.get("interval_ms"), _list(hr_series.get("values"))
        if not _integer(interval, positive=True) or hr_series.get("unit") != "bpm":
            blockers.append("HEART_RATE_GRID_INVALID")
        duration = exercise.get("durationMillis")
        matched_exercise = (
            _mapping(sample_exercises[matched_index]) if matched_index is not None else {}
        )
        saved_timebase = timebase_resolution["by_exercise"].get(_identifier(matched_exercise), {})
        acquisition = acquisition_resolution["by_exercise"].get(_identifier(matched_exercise), {})
        acquisition_applied = (
            acquisition.get("source_binding_verified") is True
            and not reasons and not match_reasons
        )
        if acquisition_resolution["blocking_reasons"] or acquisition.get("status") in (
            "WITHHELD", "REVIEW_REQUIRED",
        ):
            blockers.append("HR_ACQUISITION_DECLARATION_UNUSABLE")
        if acquisition_applied:
            blockers.extend(acquisition["blocking_reasons"])
        timebase_verified = (
            saved_timebase.get("export_timebase_verified") is True
            and not reasons
            and not match_reasons
        )
        origin_us = (
            saved_timebase["timebase"]["first_sample_offset_from_api_exercise_start_us"]
            if timebase_verified
            else 0
        )
        if (
            timebase_resolution["status"] == "WITHHELD"
            or saved_timebase.get("status") == "WITHHELD"
        ):
            blockers.append("SAVED_HR_TIMEBASE_UNUSABLE")
        segments = [
            _coverage(segment, values, interval, duration, origin_us=origin_us)
            for segment in _list(input_route.get("segments"))
        ]
        full_count = sum(s["grid_coverage_status"] == "COMPLETE" for s in segments)
        if not full_count:
            blockers.append("NO_FULLY_COVERED_HR_SEGMENT")
        blockers = list(dict.fromkeys(blockers))
        for segment in segments:
            segment["candidate_for_data_preparation"] = (
                not blockers and segment["grid_coverage_status"] == "COMPLETE"
            )
        routes.append(
            {
                "route_index": input_route.get("route_index"),
                "exercise_index": index,
                "sample_exercise_index": matched_index,
                "exercise_match_basis": match_basis,
                "sport_id": _sport(exercise),
                "exercise_start_utc": _iso(_timestamp(exercise, raw_route)),
                "input_eligible": model_route["input_eligible"],
                "status": "WITHHELD" if blockers else "CANDIDATE_WITH_LIMITATIONS",
                "candidate_for_data_preparation": not blockers,
                "blocking_reasons": blockers,
                "segment_count": len(segments),
                "fully_covered_grid_segment_count": full_count,
                "candidate_segment_count": sum(
                    s["candidate_for_data_preparation"] for s in segments
                ),
                "hr_inventory": {
                    "series_count": len(hr),
                    "slot_count": len(values),
                    "positive_finite_sample_count": sum(_positive(v) for v in values),
                    "invalid_or_missing_sample_count": sum(not _positive(v) for v in values),
                    "interval_ms": interval,
                },
                "export_timebase_verified": timebase_verified,
                "user_declared_acquisition_applied": acquisition_applied,
                "hr_acquisition": {
                    "status": acquisition.get("status", acquisition_resolution["status"])
                    if acquisition_applied or not acquisition.get("source_binding_verified")
                    else "NOT_APPLIED",
                    "source_binding_verified": acquisition_applied,
                    "declaration_source": "USER_DECLARATION" if acquisition_applied else None,
                    "declared_sensor": acquisition.get("declared_sensor")
                    if acquisition_applied else None,
                    "active_declaration_ids": acquisition.get("active_declaration_ids", [])
                    if acquisition_applied else [],
                    "reported_issue_codes": acquisition.get("reported_issue_codes", [])
                    if acquisition_applied else [],
                    "sensor_identity_verified": False,
                    "acquisition_quality_verified": False,
                    "blocking_reasons": [
                        *acquisition_resolution["blocking_reasons"],
                        *acquisition.get("blocking_reasons", []),
                    ],
                },
                "hr_timebase": {
                    "status": saved_timebase.get("status", timebase_resolution["status"]),
                    "sample_grid_source": "VERIFIED_SAVED_EXPORT"
                    if timebase_verified
                    else "PROJECT_ZERO_ORIGIN_CONVENTION",
                    "sample_grid_origin_us": origin_us,
                    "snapshot_id": saved_timebase.get("snapshot_id") if timebase_verified else None,
                    "snapshot_hash": saved_timebase.get("snapshot_hash")
                    if timebase_verified
                    else None,
                    "verification_decision_hash": saved_timebase.get("verification_decision_hash")
                    if timebase_verified
                    else None,
                    "blocking_reasons": [
                        *timebase_resolution["blocking_reasons"],
                        *saved_timebase.get("blocking_reasons", []),
                    ],
                },
                "limitations": [
                    *[
                        limitation
                        for limitation in LIMITATIONS
                        if not (
                            timebase_verified and limitation == "HR_SAMPLE_TIME_ORIGIN_NOT_VERIFIED"
                        )
                    ],
                    *(
                        [
                            "HR_API_NATIVE_SAMPLE_CLOCK_SEMANTICS_NOT_VERIFIED",
                            "HR_PAUSE_CLOCK_SEMANTICS_NOT_VERIFIED",
                        ]
                        if timebase_verified
                        else []
                    ),
                    *(["PARTIAL_HR_GRID_COVERAGE"] if full_count < len(segments) else []),
                    "HR_SENSOR_IDENTITY_NOT_ESTABLISHED",
                    "HR_SENSOR_DETAILS_USER_DECLARED_NOT_PROVIDER_VERIFIED"
                    if acquisition_applied else "HR_SENSOR_DETAILS_NOT_DECLARED",
                    *(["HR_USER_REPORTED_ISSUES_ARE_NOT_VALIDATED_ARTIFACT_DETECTION"]
                      if acquisition_applied and acquisition.get("reported_issue_codes") else []),
                ],
                "segments": segments,
            }
        )
    candidates = sum(r["candidate_for_data_preparation"] for r in routes)
    starts = sorted(r["exercise_start_utc"] for r in routes if r["exercise_start_utc"])
    result = {
        "provider": "PADDLETRAINER",
        "schema_version": "0.1",
        "audit_version": AUDIT_VERSION,
        "status": ("CANDIDATE_WITH_LIMITATIONS" if candidates else "WITHHELD")
        if routes
        else "UNAVAILABLE",
        "target": {
            "metric": "heart_rate_bpm",
            "unit": "bpm",
            "domain": "RETROSPECTIVE_CONDITIONAL_RESPONSE",
        },
        "training_authorized": False,
        "numeric_output_authorized": False,
        "session_external_id": identity,
        "athlete_id": athlete,
        "session_group_key": _hash(["POLAR", athlete, identity]) if athlete and identity else None,
        "first_exercise_start_utc": starts[0] if starts else None,
        "route_count": len(routes),
        "candidate_route_count": candidates,
        "candidate_segment_count": sum(r["candidate_segment_count"] for r in routes),
        "export_timebase_verified_route_count": sum(r["export_timebase_verified"] for r in routes),
        "user_declared_acquisition_route_count": sum(
            r["user_declared_acquisition_applied"] for r in routes
        ),
        "hr_acquisition_evidence": {
            key: value for key, value in acquisition_resolution.items()
            if key not in ("by_exercise", "exercises")
        },
        "hr_timebase_evidence": {
            key: value for key, value in timebase_resolution.items() if key != "by_exercise"
        },
        "blocking_reasons": reasons,
        "limitations": list(
            dict.fromkeys(limitation for route in routes for limitation in route["limitations"])
        )
        if routes
        else list(LIMITATIONS),
        "input_provenance": {
            "source_hash": source_hash,
            "expected_response_input_hash": boundary["input_provenance"][
                "expected_response_input_hash"
            ],
        },
        "policy": {
            "sample_grid": "EXERCISE_SPECIFIC_EXPORT_OR_PROJECT_ZERO_ORIGIN_CONVENTION",
            "provider_time_origin_verified": False,
            "verified_export_timebase_used_when_current_source_matches": True,
            "sensor_declarations_do_not_certify_hr_quality": True,
            "reported_acquisition_issues_require_preparation_review": True,
            "segment_window": "HALF_OPEN_START_INCLUSIVE_END_EXCLUSIVE",
            "exercise_matching_by_position_allowed": False,
            "missing_labels_interpolated": False,
            "grouping_unit": "ATHLETE_PROVIDER_SESSION",
            "audit_scope": "PROVIDED_SESSION_ONLY",
        },
        "routes": routes,
    }
    result["decision_hash"] = _hash(result)
    return result


def build_training_data_readiness_audit_summary(audit: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(audit))
    for route in result.get("routes", []):
        route.pop("segments", None)
        route["segments_included"] = False
    return result


def build_training_data_readiness_cohort_summary(audits: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Describe only the supplied cohort; do not infer whole-history readiness."""
    keys = [a.get("session_group_key") for a in audits if a.get("session_group_key")]
    duplicates = sorted({k for k in keys if keys.count(k) > 1})
    candidates = [
        a
        for a in audits
        if a.get("candidate_route_count", 0) > 0
        and a.get("session_group_key")
        and a["session_group_key"] not in duplicates
    ]
    count = len(candidates)
    result = {
        "schema_version": "0.1",
        "audit_version": AUDIT_VERSION,
        "audit_scope": "PROVIDED_SESSIONS_ONLY",
        "session_count": len(audits),
        "distinct_session_group_count": len(set(keys)),
        "duplicate_session_group_count": len(duplicates),
        "candidate_distinct_session_count": count,
        "candidate_segment_count": sum(a["candidate_segment_count"] for a in candidates),
        "candidate_utc_date_count": len(
            {
                a["first_exercise_start_utc"][:10]
                for a in candidates
                if a.get("first_exercise_start_utc")
            }
        ),
        "candidate_sport_ids": sorted(
            {
                r["sport_id"]
                for a in candidates
                for r in a["routes"]
                if r["candidate_for_data_preparation"] and r["sport_id"]
            }
        ),
        "split_status": "INSUFFICIENT_DISTINCT_SESSIONS" if count < 2 else "SPLIT_REVIEW_REQUIRED",
        "training_authorized": False,
        "split_assigned": False,
        "limitations": [
            *list(
                dict.fromkeys(
                    limitation
                    for audit in audits
                    for limitation in audit.get("limitations", LIMITATIONS)
                )
            ),
            "SESSION_COUNT_IS_NOT_EVIDENCE_OF_MODEL_VALIDITY",
            "PROVIDED_COHORT_IS_NOT_FULL_TRAINING_HISTORY",
        ],
        "session_decision_hashes": [a.get("decision_hash") for a in audits],
    }
    result["decision_hash"] = _hash(result)
    return result


def _match_exercise(exercise, route_exercises, sample_exercises, route_session, sample_session):
    if not exercise:
        return None, None, ["ROUTE_EXERCISE_MISSING"]
    identity = _identifier(exercise)
    if identity is not None:
        candidates = [i for i, e in enumerate(sample_exercises) if _identifier(e) == identity]
        route_duplicates = sum(_identifier(e) == identity for e in route_exercises) != 1
        basis = "PROVIDER_EXERCISE_ID"
    else:
        key = _exercise_key(exercise, route_session)
        candidates = [
            i
            for i, e in enumerate(sample_exercises)
            if key is not None
            and _identifier(e) is None
            and _exercise_key(e, sample_session) == key
        ]
        route_duplicates = (
            key is not None
            and sum(_exercise_key(e, route_session) == key for e in route_exercises) != 1
        )
        basis = "UNIQUE_START_SPORT_DURATION"
    if len(candidates) != 1 or route_duplicates:
        return None, None, ["EXERCISE_IDENTITY_MISSING_OR_AMBIGUOUS"]
    index = candidates[0]
    key, other_key = (
        _exercise_key(exercise, route_session),
        _exercise_key(sample_exercises[index], sample_session),
    )
    if key is None or other_key is None:
        return index, basis, ["EXERCISE_TIME_SPORT_DURATION_UNVERIFIABLE"]
    if key != other_key:
        return index, basis, ["EXERCISE_METADATA_MISMATCH"]
    return index, basis, []


def _coverage(segment, values, interval, duration, *, origin_us=0):
    segment = _mapping(segment)
    workload = _mapping(segment.get("external_workload"))
    start, end = workload.get("start_exercise_elapsed_ms"), workload.get("end_exercise_elapsed_ms")
    valid = (
        _integer(start)
        and _integer(end)
        and end > start
        and _integer(duration, positive=True)
        and end <= duration
        and _integer(interval, positive=True)
    )
    expected = observed = 0
    if valid:
        period_us = interval * 1000
        first = max(0, -(-(start * 1000 - origin_us) // period_us))
        stop = max(0, -(-(end * 1000 - origin_us) // period_us))
        expected = stop - first
        observed = sum(
            _positive(v) for v in values[min(first, len(values)) : min(stop, len(values))]
        )
    return {
        "order_index": segment.get("order_index"),
        "start_exercise_elapsed_ms": start,
        "end_exercise_elapsed_ms": end,
        "sample_grid_origin_us": origin_us,
        "expected_grid_slot_count": expected,
        "positive_finite_grid_sample_count": observed,
        "missing_or_invalid_grid_slot_count": expected - observed,
        "grid_coverage_status": (
            "COMPLETE"
            if expected and observed == expected
            else "PARTIAL"
            if observed
            else "NO_SAMPLES"
        )
        if valid
        else "INVALID_WINDOW",
    }


def _exercise_key(exercise, session):
    exercise = _mapping(exercise)
    timestamp, sport, duration = (
        _timestamp(exercise, session),
        _sport(exercise),
        exercise.get("durationMillis"),
    )
    return (
        (timestamp, sport, duration)
        if timestamp is not None and sport and _integer(duration, positive=True)
        else None
    )


def _timestamp(exercise, session):
    exercise, session = _mapping(exercise), _mapping(session)
    value = exercise.get("startTime")
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            offset = exercise.get("timezoneOffsetMinutes", session.get("timezoneOffsetMinutes"))
            if not isinstance(offset, int) or isinstance(offset, bool) or abs(offset) >= 24 * 60:
                return None
            parsed = parsed.replace(tzinfo=timezone(timedelta(minutes=offset)))
        return parsed.astimezone(UTC)
    except (ValueError, OverflowError):
        return None


def _sport(exercise):
    value = _mapping(exercise).get("sport")
    return _id(value.get("id")) if isinstance(value, Mapping) else _id(value)


def _identifier(value):
    return _id(_mapping(_mapping(value).get("identifier")).get("id"))


def _id(value):
    return (
        str(value)
        if not isinstance(value, bool) and isinstance(value, (int, str)) and str(value).strip()
        else None
    )


def _integer(value, positive=False):
    return (
        isinstance(value, int) and not isinstance(value, bool) and value >= (1 if positive else 0)
    )


def _positive(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value > 0
    )


def _mapping(value):
    return value if isinstance(value, Mapping) else {}


def _list(value):
    return value if isinstance(value, list) else []


def _iso(value):
    return value.isoformat() if value is not None else None


def _hash(value):
    def encode(item):
        if isinstance(item, (date, datetime)):
            return item.isoformat()
        raise TypeError("Unsupported audit source")

    try:
        return hashlib.sha256(
            json.dumps(
                value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=encode
            ).encode()
        ).hexdigest()
    except (TypeError, ValueError, OverflowError):
        return None
