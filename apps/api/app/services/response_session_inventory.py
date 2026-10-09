"""Bounded, captured-response inventory; no cohort expansion, fitting or authority."""

import math
from collections import Counter
from datetime import UTC, date, datetime
from urllib.parse import quote, urlencode
from uuid import UUID

from app.services.environment_replay_snapshot import canonical_hash
from app.services.heart_rate_sample_validation import build_training_session_heart_rate_validation
from app.services.polar_training_routes import normalize_polar_training_routes
from app.services.response_dataset_integrity import require_json_size
from app.services.response_experiment_contract import (
    check_response_experiment_manifest,
    extract_cohort_record,
)

MAX_SESSIONS = 1000
MAX_BATCH_SIZE = 8
MAX_ARTIFACT_BYTES = 4 * 1024 * 1024
MAX_SOURCE_POINTS = 100_000
SCOPE = "LOCAL_CAPTURED_API_AVAILABILITY_AND_REPORTED_EVIDENCE_STATES_ONLY"


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def seal(value, key):
    return {**value, key: canonical_hash(value)}


def _started(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(UTC) if parsed.utcoffset() is not None else None
    except (ValueError, TypeError, AttributeError, OverflowError):
        return None


def _identifier(value):
    return isinstance(value, str) and 0 < len(value) <= 200


def prepare_session_inventory(manifest, archive, sessions, *, batch_size=4, skip_ids=None):
    check_response_experiment_manifest(manifest, archive)
    record = extract_cohort_record(archive)
    require(type(batch_size) is int and 1 <= batch_size <= MAX_BATCH_SIZE, "INVENTORY_BATCH_LIMIT")
    require(
        isinstance(sessions, list) and len(sessions) <= MAX_SESSIONS,
        "INVENTORY_SESSION_LIST_LIMIT_OR_SHAPE",
    )
    ids, external = set(), set()
    for item in sessions:
        require(
            isinstance(item, dict) and _identifier(item.get("external_id")),
            "INVENTORY_SESSION_ID_INVALID",
        )
        require(
            str(UUID(item["id"])) == item["id"] and item["id"] not in ids,
            "INVENTORY_DATABASE_SESSION_ID_INVALID_OR_DUPLICATE",
        )
        ids.add(item["id"])
        require(
            isinstance(item.get("external_provider"), str)
            and isinstance(item.get("sport"), str)
            and (item.get("started_at") is None or isinstance(item["started_at"], str)),
            "INVENTORY_SESSION_METADATA_INVALID",
        )
        key = (item.get("external_provider"), item["external_id"])
        require(key not in external, "INVENTORY_PROVIDER_SESSION_DUPLICATE")
        external.add(key)
    protected = sorted(m["session_external_id"] for m in record["cohort_index"]["members"])
    starts = [
        _started(m["temporal_evidence"]["start_utc"]) for m in record["cohort_index"]["members"]
    ]
    require(all(t is not None for t in starts), "INVENTORY_PROTECTED_TIME_METADATA_REQUIRED")
    # Only a stored-metadata selection boundary; not a new chronology proof.
    cutoff = min(starts).date().isoformat()
    kayaking = [
        s for s in sessions if s.get("external_provider") == "POLAR" and s.get("sport") == "KAYAK"
    ]
    eligible = [
        s
        for s in kayaking
        if s["external_id"] not in protected
        and _started(s.get("started_at")) is not None
        and _started(s["started_at"]).date().isoformat() < cutoff
    ]
    eligible.sort(key=lambda s: (_started(s["started_at"]), s["external_id"]), reverse=True)
    skipped = [] if skip_ids is None else skip_ids
    require(
        isinstance(skipped, list)
        and all(_identifier(s) for s in skipped)
        and len(skipped) == len(set(skipped))
        and set(skipped) <= {s["external_id"] for s in eligible},
        "INVENTORY_SKIP_IDENTITIES_INVALID",
    )
    selected = [s for s in eligible if s["external_id"] not in skipped][:batch_size]
    return seal(
        {
            "schema_version": "0.1",
            "inventory_version": "0.1.0",
            "experiment_manifest_hash": manifest["experiment_manifest_hash"],
            "cohort_record_hash": record["record_hash"],
            "cohort_index_hash": record["cohort_index_hash"],
            "expected_owner_id": record["owner_id"],
            "session_list_hash": canonical_hash(sessions),
            "protected_session_ids": protected,
            "older_than_stored_utc_date": cutoff,
            "selection_scope": "STORED_METADATA_ONLY_NOT_SOURCE_CHRONOLOGY_OR_SAMPLE_ADEQUACY",
            "batch_size": batch_size,
            "operator_skip_session_ids": sorted(skipped),
            "selected_session_ids": [s["external_id"] for s in selected],
            "eligible_older_session_count": len(eligible),
            "policy": {
                "http_methods": ["GET"],
                "environment_provider_parameters_sent": [],
                "scientific_evidence_write_requests": 0,
                "existing_cohort_split_changed": False,
                "sensor_inferred_from_recording_product": False,
                "model_fit_performed": False,
                "test_scoring_performed": False,
                "training_authorized": False,
            },
        },
        "inventory_plan_hash",
    )


def request_path(kind, session=None, route_date=None):
    if kind == "sessions":
        return "/sessions?include_raw=false"
    if kind == "detail":
        return "/sessions/" + quote(session["id"], safe="") + "?include_raw=true"
    if kind == "inspection":
        return "/integrations/polar/sessions/routes/inspect?" + urlencode(
            {"route_date": route_date}
        )
    require(kind == "replays", "INVENTORY_REQUEST_KIND_INVALID")
    return (
        "/integrations/polar/sessions/"
        + quote(session["external_id"], safe="")
        + "/response-dataset/replay-snapshots?limit=100"
    )


def provider_date(session, detail):
    require(
        isinstance(detail, dict)
        and all(
            detail.get(k) == session.get(k)
            for k in ("id", "external_id", "external_provider", "sport", "started_at")
        ),
        "INVENTORY_DETAIL_IDENTITY_OR_START_CHANGED",
    )
    raw = detail.get("raw_data")
    require(
        isinstance(raw, dict)
        and isinstance(raw.get("identifier"), dict)
        and str(raw["identifier"].get("id")) == session["external_id"],
        "INVENTORY_STORED_PROVIDER_IDENTITY_INVALID",
    )
    try:
        value = datetime.fromisoformat(raw["startTime"].replace("Z", "+00:00")).date()
    except (KeyError, AttributeError, TypeError, ValueError):
        raise ValueError("INVENTORY_PROVIDER_QUERY_DATE_UNAVAILABLE") from None
    require(value != date.max, "INVENTORY_PROVIDER_QUERY_DATE_INVALID")
    return value.isoformat()


def _count(value):
    require(type(value) is int and value >= 0, "INVENTORY_REPORTED_COUNT_INVALID")
    return value


def _matches(payload, identity):
    require(
        isinstance(payload, dict) and isinstance(payload.get("trainingSessions"), list),
        "INVENTORY_SOURCE_PAYLOAD_INVALID",
    )
    return [
        s
        for s in payload["trainingSessions"]
        if isinstance(s, dict)
        and isinstance(s.get("identifier"), dict)
        and str(s["identifier"].get("id")) == identity
    ]


def _gps(route):
    normalized = normalize_polar_training_routes(route)
    points = [p for r in normalized["routes"] for p in r["points"]]
    require(len(points) <= MAX_SOURCE_POINTS, "INVENTORY_GPS_SOURCE_LIMIT")
    valid = [
        p
        for p in points
        if all(
            type(p[k]) in (int, float) and math.isfinite(p[k])
            for k in ("latitude_deg", "longitude_deg")
        )
        and -90 <= p["latitude_deg"] <= 90
        and -180 <= p["longitude_deg"] <= 180
    ]
    return {
        "route_count": normalized["route_count"],
        "waypoint_count": len(points),
        "finite_in_range_coordinate_count": len(valid),
        "timestamped_coordinate_count": sum(
            type(p["source_elapsed_ms"]) is int and p["source_elapsed_ms"] >= 0 for p in valid
        ),
        "motion_or_coverage_eligibility_verified": False,
    }


def _candidate(session, detail, inspection, replay, owner, cutoff):
    day = provider_date(session, detail)
    require(day < cutoff, "INVENTORY_PROVIDER_DATE_OUTSIDE_OLDER_WINDOW")
    require(inspection.get("route_date") == day, "INVENTORY_QUERY_DATE_RESPONSE_MISMATCH")
    identity = session["external_id"]
    routes = _matches(inspection["raw"]["routes"], identity)
    samples = _matches(inspection["raw"]["samples"], identity)
    result = {
        "provider_query_date": day,
        "route_session_match_count": len(routes),
        "sample_session_match_count": len(samples),
        "gps": None,
        "hr": None,
        "reported_export_timebase": None,
        "reported_sensor_declaration": None,
        "reported_replay_storage": None,
        "environment_feature_coverage": "NOT_CHECKED_FROM_PINNED_REPLAY",
        "model_input_coverage": "NOT_CHECKED",
        "preparation_actions": [],
    }
    actions = result["preparation_actions"]
    if len(routes) != 1 or len(samples) != 1:
        actions.append("CURRENT_ROUTE_AND_SAMPLE_SOURCE_MATCH_REQUIRED")
        return result
    sample = samples[0]
    exercises = sample.get("exercises")
    require(
        isinstance(exercises, list) and len(exercises) <= 64, "INVENTORY_HR_EXERCISE_LIMIT_OR_SHAPE"
    )
    slot_count = 0
    for exercise in exercises:
        require(isinstance(exercise, dict), "INVENTORY_HR_EXERCISE_INVALID")
        container = exercise.get("samples")
        series = (
            container.get("samples", [])
            if isinstance(container, dict)
            else container
            if isinstance(container, list)
            else []
        )
        require(isinstance(series, list), "INVENTORY_HR_SERIES_SHAPE")
        slot_count += sum(
            len(s["values"])
            for s in series
            if isinstance(s, dict)
            and s.get("type") == "HEART_RATE"
            and isinstance(s.get("values"), list)
        )
    require(slot_count <= MAX_SOURCE_POINTS, "INVENTORY_HR_SLOT_LIMIT")
    validation = build_training_session_heart_rate_validation(
        sample, expected_session_external_id=identity, sample_session_match_count=1
    )
    summaries = [s for s in inspection["route_sessions"] if s.get("external_id") == identity]
    require(len(summaries) == 1, "INVENTORY_INSPECTION_SUMMARY_AMBIGUOUS")
    summary = summaries[0]
    require(
        canonical_hash(summary["heart_rate_sample_validation"]) == canonical_hash(validation),
        "INVENTORY_HR_VALIDATION_SOURCE_MISMATCH",
    )
    diagnostics = summary["heart_rate_signal_diagnostics"]
    provenance = diagnostics["input_provenance"]
    require(
        provenance["athlete_id"] == owner
        and diagnostics["session_external_id"] == identity
        and provenance["raw_validation_decision_hash"] == validation["decision_hash"],
        "INVENTORY_REPORTED_HR_OWNER_OR_SOURCE_MISMATCH",
    )
    result["gps"] = _gps(routes[0])
    result["hr"] = {
        "validation_status": validation["status"],
        "diagnostics_status": diagnostics["status"],
        "available": validation["available"],
        "exercise_count": validation["exercise_count"],
        "slot_count": slot_count,
        "value_count_scope": "UNAMBIGUOUS_SINGLE_HR_SERIES_PER_EXERCISE_ONLY",
        "positive_finite_sample_count": sum(
            e["value_quality"]["positive_finite_sample_count"] for e in validation["exercises"]
        ),
        "invalid_or_missing_sample_count": sum(
            e["value_quality"]["invalid_or_missing_sample_count"] for e in validation["exercises"]
        ),
        "technical_issue_exercise_count": validation["exercise_with_technical_issues_count"],
        "validation_decision_hash": validation["decision_hash"],
    }
    if any(e["hr_series_count"] != 1 for e in validation["exercises"]):
        result["hr"].update(positive_finite_sample_count=None, invalid_or_missing_sample_count=None)
    clock = diagnostics.get("timebase_evidence", {})
    verified = _count(clock.get("verified_exercise_count", 0))
    result["reported_export_timebase"] = {
        "status": clock.get("status", "NOT_REPORTED"),
        "provided_record_count": _count(clock.get("provided_record_count", 0)),
        "verified_exercise_count": verified,
        "rejected_record_count": _count(clock.get("rejected_record_count", 0)),
        "blocking_reasons": clock.get("blocking_reasons", []),
        "claim_scope": "REPORTED_BY_CAPTURED_ROUTE_INSPECTION_ONLY",
    }
    acquisition = summary["heart_rate_acquisition_context"]
    require(
        acquisition["current_api_source_hash"] == validation["input_provenance"]["source_hash"],
        "INVENTORY_DECLARATION_SOURCE_MISMATCH",
    )
    declared = _count(acquisition["declared_exercise_count"])
    result["reported_sensor_declaration"] = {
        "status": acquisition["status"],
        "provided_record_count": _count(acquisition["provided_record_count"]),
        "declared_exercise_count": declared,
        "review_required_exercise_count": _count(acquisition["review_required_exercise_count"]),
        "sensor_identity_verified": False,
        "acquisition_quality_verified": False,
        "exercises": [
            {
                k: e.get(k)
                for k in (
                    "exercise_external_id",
                    "status",
                    "declaration_source",
                    "declared_sensor",
                    "reported_issue_codes",
                )
            }
            for e in acquisition.get("exercises", [])
        ],
    }
    total, returned = _count(replay["total_count"]), _count(replay["returned_count"])
    require(
        isinstance(replay["snapshots"], list)
        and returned == len(replay["snapshots"])
        and returned <= total
        and replay["truncated"] is (total > returned)
        and replay["status"] == ("AVAILABLE" if total else "CAPTURE_REQUIRED"),
        "INVENTORY_REPLAY_LIST_INCONSISTENT",
    )
    result["reported_replay_storage"] = {
        "status": replay["status"],
        "total_count": total,
        "returned_count": returned,
        "truncated": replay["truncated"],
        "snapshots": [
            {k: s[k] for k in ("snapshot_id", "snapshot_hash", "captured_unassigned_package_hash")}
            for s in replay["snapshots"]
        ],
        "current_source_binding_verified": False,
        "automatic_snapshot_selection_performed": False,
    }
    if result["gps"]["timestamped_coordinate_count"] < 2:
        actions.append("GPS_AVAILABILITY_AND_TIME_SUPPORT_REVIEW_REQUIRED")
    if (
        not validation["available"]
        or validation["blocking_reasons"]
        or validation["exercise_with_technical_issues_count"]
    ):
        actions.append("RAW_HR_TECHNICAL_REVIEW_REQUIRED")
    if (
        clock.get("status") != "VERIFIED_WITH_LIMITATIONS"
        or verified < len(exercises)
        or result["reported_export_timebase"]["rejected_record_count"]
    ):
        actions.append("TCX_EXPORT_TIMEBASE_MATCH_REQUIRED")
    if acquisition["status"] != "USER_DECLARED_WITH_LIMITATIONS" or declared < len(exercises):
        actions.append("SENSOR_DECLARATION_OR_CORRECTION_REQUIRED")
    actions.append(
        "EXPLICIT_PINNED_REPLAY_SOURCE_CHECK_REQUIRED"
        if total
        else "ENVIRONMENT_CAPTURE_AND_PINNED_REPLAY_REQUIRED"
    )
    actions.append("MODEL_INPUT_AND_HISTORY_COVERAGE_CHECK_REQUIRED")
    return result


def build_session_inventory(plan, sessions, observations, manifest, archive):
    expected = prepare_session_inventory(
        manifest,
        archive,
        sessions,
        batch_size=plan["batch_size"],
        skip_ids=plan["operator_skip_session_ids"],
    )
    require(canonical_hash(plan) == canonical_hash(expected), "INVENTORY_PLAN_BINDING_MISMATCH")
    require(isinstance(observations, list), "INVENTORY_OBSERVATIONS_INVALID")
    expected_ids = plan["selected_session_ids"][: len(observations)]
    require(
        [o["session_external_id"] for o in observations] == expected_ids,
        "INVENTORY_INSPECTION_ORDER_OR_IDENTITY_INVALID",
    )
    lookup = {s["external_id"]: s for s in sessions if s["external_provider"] == "POLAR"}
    captured = {}
    for observation in observations:
        sid = observation["session_external_id"]
        if observation["status"] == "REQUEST_FAILED":
            require(
                set(observation) == {"session_external_id", "status", "reason"}
                and isinstance(observation["reason"], str)
                and observation["reason"].startswith("INVENTORY_"),
                "INVENTORY_FAILURE_RECORD_INVALID",
            )
            captured[sid] = {
                "inspection_status": "REQUEST_FAILED",
                "request_failure_reason": observation["reason"],
                "preparation_actions": ["CURRENT_AVAILABILITY_CHECK_REQUIRED"],
            }
        else:
            require(
                observation["status"] == "CAPTURED"
                and set(observation)
                == {"session_external_id", "status", "detail", "inspection", "replays"},
                "INVENTORY_OBSERVATION_SHAPE",
            )
            captured[sid] = {
                "inspection_status": "CAPTURED_WITH_LIMITATIONS",
                **_candidate(
                    lookup[sid],
                    observation["detail"],
                    observation["inspection"],
                    observation["replays"],
                    plan["expected_owner_id"],
                    plan["older_than_stored_utc_date"],
                ),
            }
    rows = []
    for session in sorted(
        lookup.values(), key=lambda s: (s.get("started_at") or "", s["external_id"]), reverse=True
    ):
        if session["sport"] != "KAYAK":
            continue
        sid, started = session["external_id"], _started(session.get("started_at"))
        role = (
            "PROTECTED_CONTROL"
            if sid in plan["protected_session_ids"]
            else "OPERATOR_SKIPPED_THIS_BATCH"
            if sid in plan["operator_skip_session_ids"]
            else "STORED_START_METADATA_UNSUPPORTED"
            if started is None
            else "OUTSIDE_OLDER_DATA_WINDOW"
            if started.date().isoformat() >= plan["older_than_stored_utc_date"]
            else "SELECTED_THIS_BATCH"
            if sid in plan["selected_session_ids"]
            else "NOT_SELECTED_THIS_BATCH"
        )
        rows.append(
            {
                **{
                    k: session.get(k)
                    for k in ("id", "external_id", "started_at", "sport", "name", "duration_sec")
                },
                "role": role,
                **captured.get(
                    sid, {"inspection_status": "NOT_INSPECTED", "preparation_actions": []}
                ),
                "split_assignment": "EXISTING_CONTROL_RETAINED"
                if role == "PROTECTED_CONTROL"
                else "NOT_ASSIGNED",
                "cohort_member_added": False,
                "training_authorized": False,
            }
        )
    failed = sum(o["status"] == "REQUEST_FAILED" for o in observations)
    complete = len(observations) == len(plan["selected_session_ids"])
    result = seal(
        {
            "schema_version": "0.1",
            "inventory_version": "0.1.0",
            "status": "COMPLETED_WITH_REQUEST_ERRORS"
            if complete and failed
            else "COMPLETED_WITH_LIMITATIONS"
            if complete
            else "PARTIAL_INVENTORY",
            "plan": plan,
            "captured_observation_hash": canonical_hash(observations),
            "total_synced_sessions": len(sessions),
            "polar_session_count": sum(s["external_provider"] == "POLAR" for s in sessions),
            "kayak_session_count": len(rows),
            "sport_counts": dict(
                sorted(Counter(s.get("sport", "UNKNOWN") for s in sessions).items())
            ),
            "selected_session_count": len(plan["selected_session_ids"]),
            "completed_inspection_count": len(observations),
            "failed_inspection_count": failed,
            "sessions": rows,
            "scope": SCOPE,
            "environment_feature_coverage_verified": False,
            "current_replay_source_binding_verified": False,
            "source_evidence_verified": False,
            "owner_authorization_verified": False,
            "chronological_cohort_order_verified": False,
            "split_assignment_persisted": False,
            "cohort_members_added": 0,
            "model_fit_performed": False,
            "test_scoring_performed": False,
            "training_authorized": False,
            "numeric_output_authorized": False,
        },
        "inventory_hash",
    )
    require_json_size(result, MAX_ARTIFACT_BYTES, "INVENTORY_ARTIFACT_LIMIT")
    return result


def check_session_inventory(report, plan, sessions, observations, manifest, archive):
    require_json_size(report, MAX_ARTIFACT_BYTES, "INVENTORY_ARTIFACT_LIMIT")
    require(
        report.get("inventory_hash")
        == canonical_hash({k: v for k, v in report.items() if k != "inventory_hash"}),
        "INVENTORY_REPORT_HASH_MISMATCH",
    )
    expected = build_session_inventory(plan, sessions, observations, manifest, archive)
    require(
        report["inventory_hash"] == expected["inventory_hash"], "INVENTORY_RECONSTRUCTION_MISMATCH"
    )
    return {
        "status": "LOCALLY_RECONSTRUCTED_SESSION_INVENTORY",
        "inventory_hash": report["inventory_hash"],
        "payload_integrity_verified": True,
        "reconstruction_verified": True,
        "source_evidence_verified": False,
        "current_replay_source_binding_verified": False,
        "training_authorized": False,
        "scope": SCOPE,
    }
