"""Adapter semantics and deterministic source replay; no production services."""
from copy import deepcopy
import math

import pytest

from app.planning_contracts.contract_checks import ContractError, validate_contract
from app.planning_contracts.execution_adapter import (
    ExecutionAdapterError, build_execution_read, verify_execution_read,
)
from app.services.plan_contract_read import build_plan_read

CAPTURED = "2026-10-15T12:00:00+00:00"


def source():
    return {"id": "session-test", "user_id": "athlete-test", "planned_workout_id": None,
            "planned_workout_link_source": None, "external_provider": "POLAR", "external_id": "polar-test",
            "sport": "KAYAK", "name": "source", "started_at": "2026-08-01T09:00:00+00:00",
            "ended_at": "2026-08-01T09:01:40+00:00", "duration_sec": 99, "distance_m": 198,
            "avg_hr": 130, "avg_speed": 7.2, "cardio_load": 10, "rpe": None,
            "raw_data": {"identifier": {"id": "polar-test"}, "startTime": "2026-08-01T11:00:00",
                "stopTime": "2026-08-01T11:01:40", "timezoneOffsetMinutes": 120, "durationMillis": 99001,
                "distanceMeters": 198, "hrAvg": 130, "trainingTarget": {"id": "1450000123"},
                "exerciseSamples": [{"samples": {"samples": [
                    {"type": kind, "intervalMillis": 1000, "values": values}
                    for kind, values in (("DISTANCE", list(range(0, 202, 2))),
                                         ("HEART_RATE", [130] * 101), ("SPEED", [7.2] * 101))]}}]}}


def phase(kind="DURATION", value=30000, change="AUTOMATIC"):
    return {"name": "source label", "changeType": change, "phaseOrRepeat": [],
            "goal": {"type": kind, "duration" if kind == "DURATION" else "distance": value},
            "intensity": {"type": "HEART_RATE_ZONES", "lowerZone": 2, "upperZone": 3}}


def plan_capture(phases=None):
    raw = {"session": {"id": "1450000123", "version": 2, "name": "source plan", "description": "",
            "startTime": {"year": 2026, "month": 8, "day": 1, "hour": 11, "min": 0, "sec": 0}},
           "exercise": [{"idx": 0, "sportId": "95", "type": "PHASED",
                         "phaseOrRepeat": phases if phases is not None else [phase(), phase("DISTANCE", 60)]}]}
    stored = {"id": "plan-test", "user_id": "athlete-test", "source": "POLAR", "raw_data": raw,
              "polar_target_id": "1450000123", "title": "source plan", "date": "2026-08-01", "blocks": []}
    return build_plan_read(stored, captured_at=CAPTURED)


def build(snapshot=None, plan=None, **kwargs):
    return build_execution_read(source() if snapshot is None else snapshot, captured_at=CAPTURED, plan_read=plan, **kwargs)


def executed(value):
    return value["adapter_result"]["executed"]


def metric(block, name):
    return next(m for m in block["metrics"] if m["metric_name"] == name)


def candidates(value):
    return [b for b in executed(value)["blocks"] if b["execution_role"] == "PLAN_PHASE_CANDIDATE"]


def test_whole_session_is_complete_source_capture_with_distinct_durations():
    value = build()
    item = executed(value)
    validate_contract(item)
    assert verify_execution_read(value)
    assert value["source_snapshot"] == source()
    assert item["reported_duration_s"] == 99.001
    assert item["wall_clock_duration_s"] == 100
    assert item["active_duration_s"] is None
    assert item["plan_ref"] is None and item["plan_link_status"] == "UNKNOWN"
    assert metric(item["blocks"][0], "MEAN_SPEED")["status"] == "UNRESOLVED"
    assert item["speed_results"] == []
    assert all(e["available_at"] is None for e in item["evidence"])


def test_declared_provider_timezone_precedes_different_stored_clock_without_mutating_source():
    s = source(); s["started_at"] = "2026-08-01T11:00:00+00:00"
    v = build(s)
    assert executed(v)["start_time"] == "2026-08-01T09:00:00+00:00"
    assert v["adapter_result"]["clock_audit"]["stored_clock_differences"] == [{"field": "started_at", "stored_minus_selected_seconds": 7200}]
    assert v["source_snapshot"]["started_at"] == s["started_at"]


@pytest.mark.parametrize("offset", [None, "120", True, 900])
def test_naive_provider_clock_never_gets_an_assumed_timezone(offset):
    s = source(); s["raw_data"]["timezoneOffsetMinutes"] = offset
    with pytest.raises(ExecutionAdapterError, match="DECLARED_OFFSET"):
        build(s)


def test_explicit_provider_utc_offset_needs_no_separate_offset_field():
    s = source(); s["raw_data"].update(startTime="2026-08-01T11:00:00+02:00", stopTime="2026-08-01T11:01:40+02:00")
    del s["raw_data"]["timezoneOffsetMinutes"]
    assert executed(build(s))["start_time"] == "2026-08-01T09:00:00+00:00"


def test_no_stored_offset_and_no_raw_start_is_withheld():
    s = source(); s["raw_data"].pop("startTime"); s["started_at"] = "2026-08-01T09:00:00"
    with pytest.raises(ExecutionAdapterError, match="OFFSET_AWARE"):
        build(s)


def test_missing_end_does_not_invent_end_or_active_time_from_duration():
    s = source(); s["raw_data"].pop("stopTime"); s["ended_at"] = None
    item = executed(build(s))
    assert item["end_time"] is None and item["wall_clock_duration_s"] is None
    assert item["blocks"][0]["boundary"]["status"] == "UNRESOLVED"
    assert item["active_duration_s"] is None


def test_end_before_start_is_withheld():
    s = source(); s["raw_data"]["stopTime"] = "2026-08-01T10:59:59"
    with pytest.raises(ExecutionAdapterError, match="END_BEFORE_START"):
        build(s)


def test_source_identifier_conflict_is_withheld():
    s = source(); s["raw_data"]["identifier"]["id"] = "different"
    with pytest.raises(ExecutionAdapterError, match="SESSION_ID_CONFLICT"):
        build(s)


def test_zero_duration_is_present_while_missing_hr_remains_null():
    s = source(); s["raw_data"].update(durationMillis=0, hrAvg=0); s["avg_hr"] = 0
    item = executed(build(s))
    assert item["reported_duration_s"] == 0
    assert metric(item["blocks"][0], "MEAN_HEART_RATE")["value"] is None
    assert metric(item["blocks"][0], "MEAN_HEART_RATE")["status"] == "MISSING"


def test_exact_id_links_current_plan_without_promoting_historical_content():
    value = build(plan=plan_capture())
    item = executed(value)
    assert item["plan_link_status"] == "EXACT_PROVIDER_ID"
    assert item["plan_content_at_execution_status"] == "UNVERIFIED"
    assert len(candidates(value)) == 2
    assert [b["boundary"]["end_offset_s"] for b in candidates(value)] == [30, 60]
    assert all(b["observed_block_type"] == "UNKNOWN" for b in item["blocks"])
    assert item["native_time_origin_status"] == "UNVERIFIED"
    assert item["hr_acquisition_quality"] == "NOT_ESTABLISHED"


def test_manual_and_unproven_stored_links_have_different_statuses():
    s = source(); s["raw_data"].pop("trainingTarget"); s["planned_workout_id"] = "plan-test"
    s["planned_workout_link_source"] = "MANUAL_CONFIRMED"
    assert executed(build(s, plan_capture()))["plan_link_status"] == "MANUAL_CONFIRMED"
    s["planned_workout_link_source"] = "PROVIDER_EXACT"
    assert executed(build(s, plan_capture()))["plan_link_status"] == "CANDIDATE"


def test_conflicting_current_plan_is_retained_as_source_but_not_linked():
    s = source(); s["raw_data"]["trainingTarget"]["id"] = "different-target"
    v = build(s, plan_capture())
    assert executed(v)["plan_ref"] is None
    assert not candidates(v)
    assert v["plan_capture"] is not None
    assert v["adapter_result"]["plan_link_audit"]["reason"] == "PROVIDER_TARGET_ID_CONFLICT"


def test_cross_athlete_plan_is_rejected():
    s = source(); s["user_id"] = "different-athlete"
    with pytest.raises(ExecutionAdapterError, match="CROSS_ATHLETE"):
        build(s, plan_capture())


def test_millisecond_fraction_is_preserved_in_phase_boundary():
    value = build(plan=plan_capture([phase(value=30500.5)]))
    assert candidates(value)[0]["boundary"]["end_offset_s"] == 30.5005


def test_manual_phase_stops_candidate_reconstruction_without_inventing_executed_blocks():
    value = build(plan=plan_capture([phase(), phase(change="MANUAL"), phase()]))
    assert len(candidates(value)) == 1
    audit = value["adapter_result"]["phase_audit"]
    assert audit[1]["status"] == "MANUAL_OR_UNSUPPORTED_TRANSITION"
    assert audit[2]["candidate_start_s"] is None


def test_pure_manual_repeat_container_keeps_automatic_leaf_transitions_as_candidates():
    container = {"name": "repeat", "changeType": "MANUAL", "repeatCount": 2,
                 "phaseOrRepeat": [phase(value=10000), phase(value=10000)]}
    value = build(plan=plan_capture([phase(), container, phase()]))
    assert len(candidates(value)) == 6
    audit = value["adapter_result"]["phase_audit"]
    assert len(audit) == 6
    assert [r["candidate_end_s"] for r in audit] == [30, 40, 50, 60, 70, 100]
    assert value["adapter_result"]["repeat_container_audit"][0]["policy"] == "STRUCTURAL_REPEAT_CHILDREN_KEEP_OWN_TRANSITION_RULES_CANDIDATE"


def test_automatic_repeat_expansion_maps_each_unique_occurrence():
    container = {"name": "repeat", "changeType": "AUTOMATIC", "repeatCount": 2,
                 "phaseOrRepeat": [phase(value=10000), phase(value=15000)]}
    blocks = candidates(build(plan=plan_capture([container])))
    assert [b["boundary"]["end_offset_s"] for b in blocks] == [10, 25, 35, 50]
    assert len({b["planned_occurrence_id"] for b in blocks}) == 4
    assert len({b["planned_block_id"] for b in blocks}) == 2


def test_partial_phase_stops_at_last_declared_native_slot():
    value = build(plan=plan_capture([phase(value=150000), phase()]))
    assert len(candidates(value)) == 1
    assert candidates(value)[0]["boundary"]["end_offset_s"] == 100
    assert value["adapter_result"]["phase_audit"][0]["partial_recording_phase"]
    assert value["adapter_result"]["phase_audit"][1]["candidate_start_s"] is None


def test_phase_boundaries_do_not_depend_on_heart_rate_outcomes():
    s = source(); before = build(s, plan_capture())
    s["raw_data"]["exerciseSamples"][0]["samples"]["samples"][1]["values"] = [180] * 101
    after = build(s, plan_capture())
    assert [(b["boundary"]["start_offset_s"], b["boundary"]["end_offset_s"]) for b in candidates(before)] == [(b["boundary"]["start_offset_s"], b["boundary"]["end_offset_s"]) for b in candidates(after)]


def test_missing_and_zero_hr_slots_are_excluded_without_interpolation():
    s = source(); hr = s["raw_data"]["exerciseSamples"][0]["samples"]["samples"][1]["values"]
    hr[5:9] = [0, None, "NaN", 150]
    block = candidates(build(s, plan_capture()))[0]
    m = metric(block, "MEAN_HEART_RATE")
    assert m["sample_count"] == 17
    assert math.isclose(m["value"], (16 * 130 + 150) / 17)
    assert metric(block, "MEAN_SPEED")["value"] == 2


def test_mismatched_hr_grid_does_not_assign_wrong_hr_to_phases():
    s = source(); s["raw_data"]["exerciseSamples"][0]["samples"]["samples"][1]["values"] = [130] * 51
    block = candidates(build(s, plan_capture()))[0]
    assert metric(block, "MEAN_HEART_RATE")["value"] is None
    assert metric(block, "MEAN_HEART_RATE")["status"] == "UNRESOLVED"


def test_nonmonotonic_distance_blocks_distance_phase_and_following_occurrences():
    s = source(); s["raw_data"]["exerciseSamples"][0]["samples"]["samples"][0]["values"][10] = 1
    v = build(s, plan_capture())
    assert len(candidates(v)) == 1
    assert v["adapter_result"]["phase_audit"][1]["status"] == "DISTANCE_CHANNEL_UNRESOLVED"


def test_multiple_exercises_are_kept_as_raw_without_false_single_grid_projection():
    s = source(); s["raw_data"]["exerciseSamples"] *= 2
    v = build(s, plan_capture())
    assert not candidates(v)
    assert v["adapter_result"]["native_grid_audit"]["blocking_reason"] == "NATIVE_SINGLE_EXERCISE_REQUIRED"


def test_conflicting_sample_views_are_not_silently_selected():
    s = source(); s["raw_data"]["exercises"] = deepcopy(s["raw_data"]["exerciseSamples"])
    s["raw_data"]["exercises"][0]["samples"]["samples"][0]["values"][2] = 99
    v = build(s, plan_capture())
    assert not candidates(v)
    assert v["adapter_result"]["native_grid_audit"]["blocking_reason"] == "NATIVE_SAMPLE_VIEWS_CONFLICT"


def test_complete_saved_response_roundtrip_detects_contract_audit_and_source_edits():
    v = build(plan=plan_capture())
    for path in ("metric", "audit", "source"):
        changed = deepcopy(v)
        if path == "metric":
            changed["adapter_result"]["executed"]["reported_duration_s"] = 99
        elif path == "audit":
            changed["adapter_result"]["clock_audit"]["native_sample_origin_verified"] = True
        else:
            changed["source_snapshot"]["raw_data"]["note"] = "edited"
        with pytest.raises(ExecutionAdapterError, match="REPLAY_DIFFERS"):
            verify_execution_read(changed)


def test_source_and_capture_identity_are_separate():
    one = build(plan=plan_capture())
    two = build_execution_read(source(), captured_at="2026-10-15T12:00:01+00:00", plan_read=plan_capture())
    assert one["source_content_sha256"] == two["source_content_sha256"]
    assert executed(one)["executed_workout_id"] != executed(two)["executed_workout_id"]
    assert verify_execution_read(one) and verify_execution_read(two)


def test_source_size_limit_is_explicit(monkeypatch):
    from app.planning_contracts import execution_adapter as module
    monkeypatch.setattr(module, "MAX_SOURCE_BYTES", 10)
    with pytest.raises(ExecutionAdapterError, match="SOURCE_BYTE_LIMIT"):
        build()


def test_nonpolar_source_summary_uses_aware_stored_clock_without_polar_assumptions():
    s = source(); s.update(external_provider="MANUAL", raw_data={})
    item = executed(build(s))
    assert item["native_time_origin_status"] == "UNKNOWN"
    assert item["hr_acquisition_quality"] == "UNKNOWN"
    assert item["reported_duration_s"] == 99


def test_offline_projection_is_not_labelled_an_authenticated_stored_db_read():
    v = build(source_mode="OFFLINE_RAW_POLAR_PROJECTION")
    assert v["identity_scope"] == "OFFLINE_REFERENCE_IDENTITY_NOT_LIVE_AUTHENTICATION"
    assert verify_execution_read(v)
