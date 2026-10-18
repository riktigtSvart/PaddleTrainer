"""Lossless stored-session capture and conservative ExecutedWorkout projection.

No providers, ORM operations, model inference or training. Native phase offsets
are plan candidates on the provider's declared sample grid, never device events.
"""
from __future__ import annotations

from bisect import bisect_left
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import math
from pathlib import Path
import re

from .contract_checks import ContractError, expand_plan, timestamp, validate_contract
from .legacy_plan_adapter import canonical_bytes, digest, verify_result

ADAPTER_VERSION = "executed-workout-adapter-0.1-draft1"
MAX_SOURCE_BYTES = 4 * 1024 * 1024
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_SLOTS = 20000
MAX_OCCURRENCES = 1000
GUARD_S = 5.0
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,199}$")
PLAN_CAPTURE_KEY = "__paddletrainer_plan_contract_api_capture__"
METHOD_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


class ExecutionAdapterError(ValueError):
    def __init__(self, code, status_code=409):
        super().__init__(code)
        self.code = code
        self.status_code = status_code


def require(condition, code, status_code=409):
    if not condition:
        raise ExecutionAdapterError(code, status_code)


def numeric(value, *, positive=False):
    return (type(value) in (int, float) and math.isfinite(value)
            and (value > 0 if positive else value >= 0))


def provider_target_id(raw):
    target = raw.get("trainingTarget")
    value = target.get("id") if isinstance(target, dict) else None
    if type(value) not in (int, str) or not str(value):
        return None
    return str(value)


def _aware(value):
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return result if result.tzinfo is not None and result.utcoffset() is not None else None


def _provider_time(raw, field):
    value = raw.get(field)
    if value is None:
        return None, None
    require(isinstance(value, str), "EXECUTION_PROVIDER_CLOCK_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ExecutionAdapterError("EXECUTION_PROVIDER_CLOCK_INVALID") from None
    if parsed.tzinfo is not None:
        return parsed.astimezone(timezone.utc), "PROVIDER_EXPLICIT_OFFSET"
    offset = raw.get("timezoneOffsetMinutes")
    require(type(offset) is int and -840 <= offset <= 840,
            "EXECUTION_NAIVE_PROVIDER_CLOCK_REQUIRES_DECLARED_OFFSET")
    return parsed.replace(tzinfo=timezone(timedelta(minutes=offset))).astimezone(timezone.utc), "PROVIDER_DECLARED_OFFSET_MINUTES"


def _clocks(snapshot):
    raw = snapshot["raw_data"] if snapshot["external_provider"] == "POLAR" else {}
    start, start_method = _provider_time(raw, "startTime")
    end, end_method = _provider_time(raw, "stopTime")
    stored_start, stored_end = _aware(snapshot.get("started_at")), _aware(snapshot.get("ended_at"))
    if start is None:
        start, start_method = stored_start, "STORED_OFFSET_AWARE_TIMESTAMP"
    if end is None and snapshot.get("ended_at") is not None:
        require(stored_end is not None, "EXECUTION_STORED_END_REQUIRES_OFFSET")
        end, end_method = stored_end, "STORED_OFFSET_AWARE_TIMESTAMP"
    require(start is not None, "EXECUTION_START_REQUIRES_OFFSET_AWARE_SOURCE")
    start = start.astimezone(timezone.utc)
    end = end.astimezone(timezone.utc) if end is not None else None
    require(end is None or end >= start, "EXECUTION_END_BEFORE_START")
    differences = []
    for name, provider_value, stored in (("started_at", start, stored_start), ("ended_at", end, stored_end)):
        if provider_value is not None and stored is not None and provider_value != stored:
            differences.append({"field": name, "stored_minus_selected_seconds": (stored - provider_value).total_seconds()})
    return start.isoformat(), end.isoformat() if end else None, {
        "start_method": start_method, "end_method": end_method,
        "stored_clock_differences": differences,
        "native_sample_origin_verified": False,
        "provider_pause_adjustment_applied": False,
        "naive_stored_timestamp_assumed_utc": False,
    }


def _evidence(kind, scope, source_ref, sha, captured_at, limitations):
    out = {"kind": kind, "scope": scope, "source_ref": source_ref, "sha256": sha,
           "collected_at": captured_at, "available_at": None,
           "verification_status": "VERIFIED_WITH_LIMITATIONS", "limitations": limitations}
    return {"evidence_id": "execution_evidence_" + digest(out), **out}


def _metric(name, value, unit, aggregation, evidence_refs, *, count=None, unresolved=False):
    available = numeric(value)
    return {"metric_name": name, "value": value if available else None, "unit": unit,
            "status": "AVAILABLE" if available else ("UNRESOLVED" if unresolved else "MISSING"),
            "aggregation": aggregation, "sample_count": count, "evidence_refs": evidence_refs}


def _plan_capture(plan_read, owner):
    if plan_read is None:
        return None
    require(isinstance(plan_read, dict), "EXECUTION_PLAN_CAPTURE_NOT_OBJECT")
    require(not plan_read.get("numeric_output_authorized") and not plan_read.get("database_writes")
            and not plan_read.get("provider_calls"), "EXECUTION_PLAN_CAPTURE_SCOPE_INVALID")
    original, result = plan_read["source_snapshot"], plan_read["adapter_result"]
    require(digest(original) == plan_read["source_content_sha256"], "EXECUTION_PLAN_SOURCE_HASH_CHANGED")
    require(original["user_id"] == owner == result["plan"]["athlete_id"], "EXECUTION_CROSS_ATHLETE_PLAN_REJECTED")
    require(original["id"] == plan_read["workout_id"], "EXECUTION_PLAN_STORAGE_ID_CHANGED")
    verify_result(result)
    payload = copy.deepcopy(result["source"]["payload"])
    context = payload.pop(PLAN_CAPTURE_KEY, None)
    require(isinstance(context, dict) and context.get("source_content_sha256") == plan_read["source_content_sha256"]
            and context.get("captured_at") == plan_read["captured_at"], "EXECUTION_PLAN_CAPTURE_BINDING_CHANGED")
    expected = original["raw_data"] if original["source"] == "POLAR" else original
    require(payload == expected, "EXECUTION_PLAN_ADAPTER_SOURCE_DIFFERS")
    require(result["source"]["collected_at"] == plan_read["captured_at"], "EXECUTION_PLAN_EVIDENCE_CAPTURE_TIME_DIFFERS")
    return result["plan"]


def _link(snapshot, plan_read):
    if plan_read is None:
        return "UNKNOWN", None, "NO_USABLE_OWNED_PLAN_CAPTURE"
    row = plan_read["source_snapshot"]
    stored = snapshot.get("planned_workout_id")
    raw_id = provider_target_id(snapshot["raw_data"]) if snapshot["external_provider"] == "POLAR" else None
    if stored is not None and stored != row["id"]:
        return "UNKNOWN", None, "STORED_PLAN_LINK_CONFLICTS_WITH_SELECTED_PLAN"
    target = row.get("polar_target_id") if row["source"] == "POLAR" else None
    if raw_id is not None and target is not None and raw_id != str(target):
        return "UNKNOWN", None, "PROVIDER_TARGET_ID_CONFLICT"
    if raw_id is not None and target is not None and raw_id == str(target):
        return "EXACT_PROVIDER_ID", raw_id, "SOURCE_TARGET_ID_MATCH"
    if stored == row["id"] and snapshot.get("planned_workout_link_source") == "MANUAL_CONFIRMED":
        return "MANUAL_CONFIRMED", None, "PERSISTED_EXPLICIT_MANUAL_LINK"
    if stored == row["id"]:
        return "CANDIDATE", None, "STORED_LINK_WITHOUT_CURRENT_EXACT_SOURCE_PROOF"
    return "UNKNOWN", None, "NO_EXACT_OR_PERSISTED_PLAN_LINK"


def _grid(raw):
    """Use only one unambiguous native one-second exercise; never interpolate HR."""
    sources = []
    for key in ("exerciseSamples", "exercises"):
        values = raw.get(key)
        if values is not None and values != []:
            require(isinstance(values, list), "NATIVE_EXERCISE_CONTAINER_INVALID")
            if any(isinstance(e, dict) and e.get("samples") for e in values):
                sources.append((key, values))
    if not sources:
        return None, {"status": "NATIVE_SAMPLES_NOT_STORED", "clock_domain": "UNKNOWN"}
    # Two views are acceptable only when the full sample-bearing exercises agree.
    require(len(sources) == 1 or sources[0][1] == sources[1][1], "NATIVE_SAMPLE_VIEWS_CONFLICT")
    key, exercises = sources[0]
    require(len(exercises) == 1 and isinstance(exercises[0], dict), "NATIVE_SINGLE_EXERCISE_REQUIRED")
    exercise = exercises[0]
    samples = exercise.get("samples")
    samples = samples.get("samples") if isinstance(samples, dict) else samples
    require(isinstance(samples, list), "NATIVE_SAMPLE_CONTAINER_INVALID")
    channels, issues = {}, []
    for kind in ("DISTANCE", "HEART_RATE", "SPEED"):
        series = [s for s in samples if isinstance(s, dict) and s.get("type") == kind]
        if not series:
            issues.append(kind + "_NOT_STORED")
            continue
        if len(series) != 1 or type(series[0].get("intervalMillis")) is not int or series[0]["intervalMillis"] != 1000:
            issues.append(kind + "_AMBIGUOUS_OR_UNSUPPORTED_NATIVE_GRID")
            continue
        values = series[0].get("values")
        if not isinstance(values, list) or not 1 < len(values) <= MAX_SLOTS:
            issues.append(kind + "_SAMPLE_COUNT_UNSUPPORTED")
            continue
        channels[kind] = values
    require(channels, "NATIVE_NO_SUPPORTED_ONE_SECOND_CHANNEL")
    # Distance is the geometrical candidate clock; otherwise one consistent
    # supported channel supplies recording extent for duration-only candidates.
    slots = len(channels.get("DISTANCE", next(iter(channels.values()))))
    for kind in list(channels):
        if len(channels[kind]) != slots:
            del channels[kind]
            issues.append(kind + "_SLOT_COUNT_DIFFERS_FROM_CANDIDATE_CLOCK")
    distances = channels.get("DISTANCE")
    if distances is not None and (not all(numeric(v) for v in distances)
                                 or any(b < a for a, b in zip(distances, distances[1:]))):
        del channels["DISTANCE"]
        issues.append("DISTANCE_INVALID_OR_NONMONOTONIC")
    return {"channels": channels, "slots": slots}, {
        "status": "ONE_SECOND_NATIVE_INDEX_CANDIDATE", "source_path": "/raw_data/" + key + "/0/samples",
        "clock_domain": "NATIVE_INDEX_CANDIDATE", "interval_s": 1, "slot_count": slots,
        "available_channels": sorted(channels), "issues": issues,
        "pause_record_count": len(exercise.get("pauseTimes") or []),
        "native_unit_policy": "EXISTING_POLAR_NORMALIZER_ASSUMPTIONS_DISTANCE_METRE_SPEED_KMH",
        "native_unit_independently_verified": False,
        "first_slot_origin_and_cross_channel_alignment_verified": False,
    }


def _distance_at(seconds, values):
    i = int(seconds)
    return values[i] if i == len(values) - 1 else values[i] + (seconds - i) * (values[i + 1] - values[i])


def _distance_end(start, goal, values):
    threshold = _distance_at(start, values) + goal
    if threshold > values[-1]:
        return None
    j = bisect_left(values, threshold)
    require(j > 0 and values[j] > values[j - 1], "NATIVE_DISTANCE_CROSSING_INVALID")
    return j - 1 + (threshold - values[j - 1]) / (values[j] - values[j - 1])


def _phases(plan, grid, execution_id, refs, manual_containers=()):
    occurrences = expand_plan(plan)
    require(len(occurrences) <= MAX_OCCURRENCES, "EXECUTION_PHASE_EXPANSION_LIMIT", 413)
    blocks, audit = [], []
    start, blocked, last = 0.0, None, float(grid["slots"] - 1)
    channels, distances = grid["channels"], grid["channels"].get("DISTANCE")
    for index, occurrence in enumerate(occurrences):
        row = {"planned_occurrence_id": occurrence["planned_occurrence_id"],
               "planned_block_id": occurrence["block_id"], "expanded_phase_index": index,
               "candidate_start_s": None, "candidate_end_s": None,
               "actual_boundary_verified": False, "outcome_hr_used_for_boundary": False}
        if blocked is None and any(part.rsplit("@", 1)[0] in manual_containers for part in occurrence["occurrence_path"]):
            blocked = "MANUAL_CONTAINER_EVENT_SEMANTICS_UNRESOLVED"
        if blocked or start is None:
            row["status"] = "UNASSIGNED_AFTER_" + (blocked or "RECORDING_END")
            audit.append(row)
            continue
        if start >= last:
            blocked = "RECORDING_END"
            row["status"] = "NO_POSITIVE_OBSERVED_INTERVAL_REMAINING"
            audit.append(row)
            continue
        kind = occurrence["completion_condition"]
        if kind == "DURATION":
            end = start + occurrence["duration_s"]
            method = "NOMINAL_TIMER_DURATION"
        elif kind == "DISTANCE" and distances is not None:
            end = _distance_end(start, occurrence["distance_m"], distances)
            method = "NATIVE_CUMULATIVE_DISTANCE_INTERPOLATION"
        else:
            blocked = "MANUAL_OR_UNSUPPORTED_TRANSITION" if kind != "DISTANCE" else "DISTANCE_CHANNEL_UNRESOLVED"
            row["status"] = blocked
            audit.append(row)
            continue
        partial = end is None or end > last
        stop = last if partial else end
        require(stop > start, "EXECUTION_NONPOSITIVE_CANDIDATE_INTERVAL")
        indices = range(max(0, math.ceil(start + GUARD_S)), min(grid["slots"], math.ceil(stop - GUARD_S)))
        indices = list(indices)
        metrics, counts = [], {}
        for channel, name, unit, divisor in (("HEART_RATE", "MEAN_HEART_RATE", "BPM", 1),
                                             ("SPEED", "MEAN_SPEED", "M_PER_S", 3.6)):
            values = channels.get(channel)
            valid = [values[i] for i in indices if numeric(values[i], positive=channel == "HEART_RATE")] if values is not None else []
            mean = math.fsum(valid) / len(valid) / divisor if valid else None
            metrics.append(_metric(name, mean, unit, "BLOCK_MEAN", refs,
                                   count=len(valid), unresolved=values is None))
            counts[channel] = {"core_slots": len(indices), "valid_slots": len(valid),
                               "missing_or_invalid_slots": len(indices) - len(valid)}
        distance = _distance_at(stop, distances) - _distance_at(start, distances) if distances is not None else None
        metrics.extend([_metric("DURATION", stop - start, "SECOND", "BLOCK_TOTAL", refs),
                        _metric("DISTANCE", distance, "METRE", "BLOCK_TOTAL", refs, unresolved=distances is None)])
        block_id = "executed_block_" + digest({"execution": execution_id, "occurrence": occurrence["planned_occurrence_id"]})
        blocks.append({"executed_block_id": block_id, "planned_block_id": occurrence["block_id"],
                       "planned_occurrence_id": occurrence["planned_occurrence_id"],
                       "observed_block_type": "UNKNOWN", "execution_role": "PLAN_PHASE_CANDIDATE",
                       "boundary": {"start_offset_s": start, "end_offset_s": stop,
                           "clock_domain": "NATIVE_INDEX_CANDIDATE", "clock_anchor": None,
                           "status": "CANDIDATE", "method": method + "; HALF_OPEN_INTERVAL; CORE_GUARD_5S_EACH_END",
                           "evidence_refs": refs}, "metrics": metrics})
        row.update(status="SOURCE_GRID_PLAN_CANDIDATE_PARTIAL" if partial else "SOURCE_GRID_PLAN_CANDIDATE",
                   candidate_start_s=start, candidate_end_s=stop, boundary_method=method,
                   partial_recording_phase=partial, metric_sample_counts=counts)
        audit.append(row)
        if partial:
            blocked, start = "INCOMPLETE_PLANNED_PHASE", None
        else:
            start = end
    return blocks, audit


def build_execution_read(snapshot, *, captured_at=None, plan_read=None, plan_selection=None,
                         source_mode="STORED_WORKOUT_SESSION"):
    """Freeze current source and optional current plan; never infer missing facts."""
    captured_at = captured_at or datetime.now(timezone.utc).isoformat()
    timestamp(captured_at)
    require(source_mode in ("STORED_WORKOUT_SESSION", "OFFLINE_RAW_POLAR_PROJECTION"), "EXECUTION_SOURCE_MODE_INVALID")
    original = copy.deepcopy(snapshot)
    require(isinstance(original, dict) and isinstance(original.get("raw_data"), dict), "EXECUTION_SOURCE_OBJECT_REQUIRED")
    require(len(canonical_bytes(original)) <= MAX_SOURCE_BYTES, "EXECUTION_SOURCE_BYTE_LIMIT", 413)
    for key in ("id", "user_id", "external_id"):
        require(isinstance(original.get(key), str) and ID_RE.fullmatch(original[key]), "EXECUTION_SOURCE_ID_INVALID")
    require(isinstance(original.get("external_provider"), str) and original["external_provider"], "EXECUTION_PROVIDER_REQUIRED")
    require(isinstance(original.get("sport"), str) and original["sport"], "EXECUTION_SPORT_REQUIRED")
    raw = original["raw_data"]
    if original["external_provider"] == "POLAR" and raw.get("identifier") is not None:
        require(isinstance(raw["identifier"], dict) and str(raw["identifier"].get("id")) == original["external_id"],
                "EXECUTION_RAW_SESSION_ID_CONFLICT")
    plan = _plan_capture(plan_read, original["user_id"])
    link, target_id, link_reason = _link(original, plan_read)
    selected_plan = plan if link != "UNKNOWN" else None
    start, end, clock_audit = _clocks(original)
    wall = (timestamp(end) - timestamp(start)).total_seconds() if end else None
    raw_duration = raw.get("durationMillis") if original["external_provider"] == "POLAR" else None
    reported = raw_duration / 1000 if numeric(raw_duration) else original.get("duration_sec")
    reported = reported if numeric(reported) else None
    content_hash = digest(original)
    context = {"adapter_version": ADAPTER_VERSION, "method_sha256": METHOD_SHA256, "captured_at": captured_at,
               "source_mode": source_mode,
               "source_content_sha256": content_hash,
               "plan_capture_id": plan_read["capture_id"] if plan_read else None,
               "plan_selection": copy.deepcopy(plan_selection)}
    capture_id = "execution_capture_" + digest(context)
    execution_id = "execution_" + digest(context)
    ref = "api:sessions/" + original["id"] + "/executed-workout#" + capture_id
    source_e = _evidence("RAW_SOURCE", "COMPLETE_STORED_SESSION_CANONICAL_JSON; preservation only, not physical accuracy or complete training history",
                         ref + "/source_snapshot", content_hash, captured_at,
                         ["AVAILABLE_AT_UNKNOWN", "SOURCE_HASH_DOES_NOT_ESTABLISH_SENSOR_ACCURACY"])
    method_e = _evidence("DERIVED_METHOD", "EXECUTED_WORKOUT_PROJECTION_AND_CANDIDATE_GRID_METHOD; " + ADAPTER_VERSION,
                         "code:app/planning_contracts/execution_adapter.py", METHOD_SHA256, captured_at,
                         ["NO_PROVIDER_PHASE_EVENTS", "NATIVE_ORIGIN_AND_NATIVE_UNIT_ASSUMPTIONS_UNVERIFIED",
                          "WHOLE_SESSION_SUMMARY_AND_PHASES_OVERLAP_AND_MUST_NOT_BE_SUMMED"])
    evidence, refs = [source_e, method_e], [source_e["evidence_id"], method_e["evidence_id"]]
    if selected_plan:
        evidence.extend(copy.deepcopy(selected_plan["evidence"]))
        link_refs = [source_e["evidence_id"]] + [e["evidence_id"] for e in selected_plan["evidence"]]
    else:
        link_refs = []
    distance = raw.get("distanceMeters") if numeric(raw.get("distanceMeters")) and original["external_provider"] == "POLAR" else original.get("distance_m")
    hr = raw.get("hrAvg") if numeric(raw.get("hrAvg"), positive=True) and original["external_provider"] == "POLAR" else original.get("avg_hr")
    if not numeric(hr, positive=True):
        hr = None
    load = original.get("cardio_load")
    # Existing ORM speed has no persisted physical unit declaration. Preserve
    # it in source; do not silently interpret it as m/s or km/h here.
    metrics = [_metric("MEAN_HEART_RATE", hr, "BPM", "WHOLE_SESSION", refs),
               _metric("MEAN_SPEED", None, "M_PER_S", "WHOLE_SESSION", refs, unresolved=original.get("avg_speed") is not None),
               _metric("DISTANCE", distance, "METRE", "WHOLE_SESSION", refs),
               _metric("DURATION", reported, "SECOND", "WHOLE_SESSION", refs),
               _metric("CARDIO_LOAD", load, "SOURCE_NATIVE", "WHOLE_SESSION", refs)]
    boundary = {"start_offset_s": 0 if wall and wall > 0 else None,
                "end_offset_s": wall if wall and wall > 0 else None,
                "clock_domain": "WALL_CLOCK_UTC" if wall and wall > 0 else "UNKNOWN",
                "clock_anchor": start if wall and wall > 0 else None,
                "status": "CANDIDATE" if wall and wall > 0 else "UNRESOLVED",
                "method": "DECLARED_SESSION_ENVELOPE_NOT_ACTIVE_TIME_OR_PHASE_EVENTS", "evidence_refs": refs}
    blocks = [{"executed_block_id": "executed_summary_" + digest(context), "planned_block_id": None,
               "planned_occurrence_id": None, "observed_block_type": "UNKNOWN",
               "execution_role": "WHOLE_SESSION_SUMMARY", "boundary": boundary, "metrics": metrics}]
    grid, phase_audit = None, []
    grid_audit = {"status": "NON_POLAR_SOURCE_NATIVE_GRID_NOT_ADAPTED"}
    if original["external_provider"] == "POLAR":
        try:
            grid, grid_audit = _grid(raw)
        except ExecutionAdapterError as exc:
            grid_audit = {"status": "NATIVE_GRID_WITHHELD", "blocking_reason": exc.code}
    source_is_phased = True
    manual_containers = set()
    if selected_plan and plan_read["source_kind"] == "STORED_POLAR_TARGET":
        target_exercises = plan_read["source_snapshot"]["raw_data"].get("exercise", [])
        source_is_phased = (len(target_exercises) == 1 and bool(target_exercises[0].get("phaseOrRepeat")))
        manual_containers = {m["block_id"] for m in plan_read["adapter_result"]["block_mapping"]
                             if m["source_type"] == "REPEAT" and m["source_change_type"] == "MANUAL"}
    phase_projection_status = "NO_USABLE_LINKED_PLAN" if not selected_plan else "NATIVE_GRID_NOT_AVAILABLE"
    if selected_plan and grid and selected_plan["sport"] == original["sport"] and source_is_phased:
        phase_blocks, phase_audit = _phases(selected_plan, grid, execution_id,
                                          refs + [e["evidence_id"] for e in selected_plan["evidence"]], manual_containers)
        blocks.extend(phase_blocks)
        phase_projection_status = "PLAN_LEAF_CANDIDATES_WITH_EXPLICIT_UNASSIGNED_AUDIT"
    elif selected_plan and grid and not source_is_phased:
        phase_projection_status = "SOURCE_TARGET_HAS_NO_SUPPORTED_SINGLE_PHASE_TREE"
    elif selected_plan and grid:
        grid_audit["plan_phase_projection_blocked_by"] = "PLAN_SESSION_SPORT_MISMATCH"
        phase_projection_status = "PLAN_SESSION_SPORT_MISMATCH"
    executed = {"contract_type": "ExecutedWorkout", "schema_version": "0.1",
                "executed_workout_id": execution_id, "execution_revision": 1,
                "athlete_id": original["user_id"], "sport": original["sport"],
                "provider": original["external_provider"], "provider_session_id": original["external_id"],
                "start_time": start, "end_time": end,
                "plan_ref": {"plan_id": selected_plan["plan_id"], "plan_revision": selected_plan["plan_revision"]} if selected_plan else None,
                "plan_link_status": link,
                "plan_content_at_execution_status": "UNVERIFIED" if selected_plan else "UNKNOWN",
                "plan_link_evidence_refs": link_refs, "reported_duration_s": reported,
                "active_duration_s": None, "wall_clock_duration_s": wall,
                "native_time_origin_status": "UNVERIFIED" if grid else "UNKNOWN",
                "hr_acquisition_quality": "NOT_ESTABLISHED" if original["external_provider"] == "POLAR" else "UNKNOWN",
                "blocks": blocks, "speed_results": [], "evidence": evidence}
    validate_contract(executed)
    result = {"status": "EXECUTED_WORKOUT_READ_WITH_LIMITATIONS", "adapter_version": ADAPTER_VERSION,
              "schema_version": "0.1", "contract_release": "DRAFT1", "source_mode": source_mode,
              "identity_scope": "APPLICATION_DEMO_USER" if source_mode == "STORED_WORKOUT_SESSION" else "OFFLINE_REFERENCE_IDENTITY_NOT_LIVE_AUTHENTICATION",
              "session_id": original["id"], "capture_id": capture_id, "captured_at": captured_at,
              "source_content_sha256": content_hash, "source_snapshot": original,
              "plan_capture": copy.deepcopy(plan_read), "plan_selection": copy.deepcopy(plan_selection),
              "adapter_result": {"executed": executed, "clock_audit": clock_audit,
                  "native_grid_audit": grid_audit, "phase_audit": phase_audit,
                  "phase_projection_status": phase_projection_status,
                  "plan_link_audit": {"status": link, "reason": link_reason, "exact_target_id": target_id},
                  "summary_field_audit": {
                      "reported_duration_source": "/raw_data/durationMillis" if numeric(raw_duration) else "/duration_sec",
                      "duration_preserves_fractional_seconds": numeric(raw_duration),
                      "stored_duration_sec": original.get("duration_sec"),
                      "whole_session_hr_source": "/raw_data/hrAvg" if original["external_provider"] == "POLAR" and numeric(raw.get("hrAvg"), positive=True) else "/avg_hr",
                      "stored_avg_speed_not_interpreted_without_unit_binding": original.get("avg_speed") is not None,
                      "cardio_load_unit": "SOURCE_NATIVE_NOT_STANDARDIZED",
                  },
                  "metric_scope": "WHOLE_SESSION_SUMMARY_OVERLAPS_PHASE_CANDIDATES; DO_NOT_SUM_ACROSS_SCOPES",
                  "sample_metric_policy": "HALF_OPEN_NATIVE_INDEX_INTERVAL; FIVE_SECOND_CORE_GUARD; NO_HR_INTERPOLATION",
                  "source_preservation": "COMPLETE_SESSION_ORM_COLUMNS_AND_RAW_JSON; UNPROJECTED_FIELDS_RETAINED"},
              "limitations": ["STATELESS_CAPTURE_NOT_PERSISTED_EXECUTION_REVISION", "AVAILABLE_AT_NOT_ESTABLISHED",
                  "HISTORICAL_PLAN_CONTENT_UNVERIFIED", "ACTUAL_PHASE_ALIGNMENT_UNVERIFIED",
                  "HR_ACQUISITION_QUALITY_NOT_ESTABLISHED", "SPEED_MODEL_NOT_RUN",
                  "ACTIVE_DURATION_NOT_INFERRED_FROM_REPORTED_DURATION", "SESSION_HISTORY_COMPLETENESS_NOT_ESTABLISHED"],
              "historical_plan_content_verified": False, "actual_phase_alignment_verified": False,
              "numeric_output_authorized": False, "state_estimation_authorized": False,
              "capability_update_performed": False, "database_writes": 0, "provider_calls": 0,
              "speed_model_retrained": False, "state_model_trained": False, "new_independent_test": False}
    require(len(canonical_bytes(result)) <= MAX_RESPONSE_BYTES, "EXECUTION_RESPONSE_BYTE_LIMIT", 413)
    return result


def verify_execution_read(value):
    """Verify saved source, contract and complete deterministic adapter replay."""
    require(isinstance(value, dict), "EXECUTION_RESPONSE_NOT_OBJECT")
    require(value.get("adapter_version") == ADAPTER_VERSION, "EXECUTION_ADAPTER_VERSION_DIFFERS")
    validate_contract(value["adapter_result"]["executed"])
    repeated = build_execution_read(value["source_snapshot"], captured_at=value["captured_at"],
                                   plan_read=value["plan_capture"], plan_selection=value["plan_selection"], source_mode=value["source_mode"])
    require(value == repeated, "EXECUTION_FULL_SOURCE_REPLAY_DIFFERS")
    return True
