"""Repeat semantics, clock frames, inverse metric mapping, and legacy replay."""
from copy import deepcopy

import pytest

from test_executed_workout_adapter import source, phase, plan_capture, build, candidates, metric
from app.planning_contracts.execution_adapter import (
    ADAPTER_VERSION, ExecutionAdapterError, verify_execution_read, legacy_v01,
    LEGACY_METHOD_SHA256,
    _repeat_policy,
)
from app.services.plan_contract_read import PlanReadError
from app.services.plan_execution_comparison_read import build_comparison_read, verify_comparison_read


def routed_source(first_ms=2000):
    s = source()
    raw = s["raw_data"]
    raw["stopTime"] = "2026-08-01T11:01:43"
    e = raw["exerciseSamples"][0]
    e.update(startTime="2026-08-01T11:00:00", stopTime="2026-08-01T11:01:42",
             timezoneOffsetMinutes=120, durationMillis=102000,
             routes={"route": {"startTime": "2026-08-01T11:00:00.500",
                              "wayPoints": [{"elapsedMillis": first_ms + 1000*i} for i in range(101)]}},
             pauseTimes=[{"startTime": "2026-08-01T11:01:42.500", "endTime": "2026-08-01T11:01:43"}])
    return s


def timebase(value):
    return value["adapter_result"]["native_grid_audit"]["phase_timebase"]


def test_distance_prefix_uses_source_route_clock_not_native_zero():
    v = build(routed_source(), plan_capture([phase("DISTANCE", 60), phase(value=20000)]))
    b = candidates(v)
    assert [x["boundary"]["end_offset_s"] for x in b] == [32.5, 52.5]
    assert b[0]["boundary"]["start_offset_s"] == 0
    assert b[0]["boundary"]["clock_domain"] == "WALL_CLOCK_UTC"
    assert b[0]["boundary"]["clock_anchor"] == "2026-08-01T09:00:00+00:00"
    assert metric(b[0], "DURATION")["value"] == 32.5
    assert metric(b[0], "DISTANCE")["value"] == 60
    assert v["adapter_result"]["phase_audit"][0]["unobserved_prefix_s"] == 2.5
    assert timebase(v)["selected_native_origin_s"] == 2.5
    assert timebase(v)["hr_clock_transfer_verified"] is False
    assert v["actual_phase_alignment_verified"] is False
    assert verify_execution_read(v)


def test_metric_core_indices_are_translated_back_from_selected_clock():
    s = routed_source()
    s["raw_data"]["exerciseSamples"][0]["samples"]["samples"][1]["values"] = list(range(100, 201))
    v = build(s, plan_capture([phase(value=30000)]))
    b = candidates(v)[0]
    # Core [5,25) in the elapsed frame maps to native indices 3..22.
    assert metric(b, "MEAN_HEART_RATE")["sample_count"] == 20
    assert metric(b, "MEAN_HEART_RATE")["value"] == 112.5
    assert b["boundary"]["end_offset_s"] == 30


def test_partial_end_uses_last_native_slot_in_the_selected_clock():
    v = build(routed_source(), plan_capture([phase(value=150000), phase()]))
    b = candidates(v)
    assert len(b) == 1
    assert b[0]["boundary"]["end_offset_s"] == 102.5
    assert v["adapter_result"]["phase_audit"][0]["partial_recording_phase"]
    assert v["adapter_result"]["phase_audit"][1]["candidate_start_s"] is None


def test_a_short_unobserved_prefix_does_not_invent_distance_or_hr():
    v = build(routed_source(), plan_capture([phase(value=1000)]))
    b = candidates(v)[0]
    assert metric(b, "DISTANCE")["status"] == "UNRESOLVED"
    assert metric(b, "DISTANCE")["value"] is None
    assert metric(b, "MEAN_HEART_RATE")["value"] is None


def test_distance_goal_after_a_pre_sample_phase_needs_an_observed_baseline():
    v = build(routed_source(), plan_capture([phase(value=1000), phase("DISTANCE", 20), phase()]))
    assert len(candidates(v)) == 1
    assert v["adapter_result"]["phase_audit"][1]["status"] == "DISTANCE_BASELINE_BEFORE_FIRST_NATIVE_SAMPLE_UNRESOLVED"


@pytest.mark.parametrize("change,reason", [
    ("missing_route", "SOURCE_ROUTE_NOT_STORED"),
    ("different_count", "ROUTE_POINT_COUNT_DIFFERS_FROM_NATIVE_SLOT_COUNT"),
    ("bad_elapsed", "ROUTE_ELAPSED_TIME_INVALID"),
    ("bool_elapsed", "ROUTE_ELAPSED_TIME_INVALID"),
    ("duplicate", "ROUTE_GRID_NOT_ONE_SECOND_REGULAR"),
    ("gap", "ROUTE_GRID_NOT_ONE_SECOND_REGULAR"),
    ("missing_pauses", "PAUSE_INVENTORY_NOT_EXPLICITLY_RETURNED"),
    ("interior_pause", "INTERIOR_PAUSE_REQUIRES_TIMEBASE_RECONCILIATION"),
    ("bad_pause", "PAUSE_CLOCK_INVALID"),
    ("later_start", "ROUTE_START_OUTSIDE_REPORTED_EXERCISE_START_PRECISION"),
    ("early_stop", "ROUTE_GRID_OUTSIDE_REPORTED_EXERCISE_CLOCK"),
    ("huge_elapsed", "ROUTE_CLOCK_OUT_OF_RANGE"),
])
def test_incompatible_route_clock_retains_explicit_index_fallback(change, reason):
    s = routed_source(); e = s["raw_data"]["exerciseSamples"][0]
    if change == "missing_route": e.pop("routes")
    elif change == "different_count": e["routes"]["route"]["wayPoints"].pop()
    elif change == "bad_elapsed": e["routes"]["route"]["wayPoints"][0]["elapsedMillis"] = "2000"
    elif change == "bool_elapsed": e["routes"]["route"]["wayPoints"][0]["elapsedMillis"] = True
    elif change == "duplicate": e["routes"]["route"]["wayPoints"][1]["elapsedMillis"] = 2000
    elif change == "gap": e["routes"]["route"]["wayPoints"][10]["elapsedMillis"] += 2
    elif change == "missing_pauses": e.pop("pauseTimes")
    elif change == "interior_pause": e["pauseTimes"] = [{"startTime": "2026-08-01T11:00:30", "endTime": "2026-08-01T11:00:35"}]
    elif change == "bad_pause": e["pauseTimes"] = [None]
    elif change == "later_start": e["routes"]["route"]["startTime"] = "2026-08-01T11:00:02"
    elif change == "early_stop": e["stopTime"] = "2026-08-01T11:01:40"
    elif change == "huge_elapsed":
        for i, p in enumerate(e["routes"]["route"]["wayPoints"]): p["elapsedMillis"] = 10**100 + i*1000
    v = build(s, plan_capture([phase("DISTANCE", 60)]))
    assert timebase(v)["status"] == "NATIVE_INDEX_FALLBACK"
    assert reason in timebase(v)["blocking_reasons"]
    assert candidates(v)[0]["boundary"]["clock_domain"] == "NATIVE_INDEX_CANDIDATE"
    assert candidates(v)[0]["boundary"]["clock_anchor"] is None
    assert candidates(v)[0]["boundary"]["end_offset_s"] == 30


def test_explicit_empty_pauses_are_different_from_missing_inventory():
    s = routed_source(); s["raw_data"]["exerciseSamples"][0]["pauseTimes"] = []
    assert timebase(build(s, plan_capture()))["status"] == "DECLARED_ROUTE_INDEX_TRANSFER_CANDIDATE"


def test_origin_is_recalculated_for_each_source_and_not_fitted_to_outcomes():
    s = routed_source(); before = build(s, plan_capture([phase("DISTANCE", 60)]))
    e = s["raw_data"]["exerciseSamples"][0]
    for series in e["samples"]["samples"]:
        if series["type"] in ("HEART_RATE", "SPEED"): series["values"] = [170] * 101
    after = build(s, plan_capture([phase("DISTANCE", 60)]))
    assert ({k:v for k,v in candidates(before)[0]["boundary"].items() if k!='evidence_refs'} ==
            {k:v for k,v in candidates(after)[0]["boundary"].items() if k!='evidence_refs'})
    other = routed_source(first_ms=1000)
    assert timebase(build(other, plan_capture()))["selected_native_origin_s"] == 1.5


def test_manual_leaf_inside_pure_repeat_still_blocks_downstream_phases():
    repeat = {"changeType": "MANUAL", "repeatCount": 2,
              "phaseOrRepeat": [phase(value=10000), phase(change="MANUAL")]}
    v = build(plan=plan_capture([repeat, phase()]))
    assert len(candidates(v)) == 1
    assert v["adapter_result"]["phase_audit"][1]["status"] == "MANUAL_OR_UNSUPPORTED_TRANSITION"
    assert v["adapter_result"]["phase_audit"][2]["candidate_start_s"] is None


@pytest.mark.parametrize("field", ["goal", "intensity"])
def test_repeat_with_own_goal_or_intensity_keeps_its_ambiguity_blocker(field):
    repeat = {"changeType": "MANUAL", "repeatCount": 2, "phaseOrRepeat": [phase(value=10000)]}
    repeat[field] = {"type": "DURATION", "duration": 20000} if field == "goal" else {"type": "FREE"}
    # The existing plan adapter already withholds this unsupported structure.
    with pytest.raises(PlanReadError, match="SOURCE_CONVERSION_WITHHELD"):
        plan_capture([phase(), repeat])
    pure = dict(repeat); pure.pop(field)
    captured = plan_capture([phase(), pure])
    captured["source_snapshot"]["raw_data"]["exercise"][0]["phaseOrRepeat"][1][field] = repeat[field]
    blocked, audit = _repeat_policy(captured)
    assert blocked == {audit[0]["block_id"]}
    assert audit[0]["policy"] == "CONTAINER_EVENT_SEMANTICS_UNRESOLVED"


def test_pinned_legacy_method_replays_original_capture_without_reinterpreting_it():
    assert legacy_v01.METHOD_SHA256 == LEGACY_METHOD_SHA256
    repeat = {"changeType": "MANUAL", "repeatCount": 2,
              "phaseOrRepeat": [phase(value=10000), phase(value=10000)]}
    plan = plan_capture([phase(), repeat, phase()])
    old = legacy_v01.build_execution_read(source(), captured_at="2026-10-15T12:00:00+00:00", plan_read=plan)
    assert old["adapter_version"] != ADAPTER_VERSION
    assert len(candidates(old)) == 1
    assert verify_execution_read(old)
    new = build(plan=plan)
    assert len(candidates(new)) == 6
    assert verify_execution_read(new)
    changed = deepcopy(old); changed["adapter_result"]["executed"]["reported_duration_s"] += 1
    with pytest.raises(ExecutionAdapterError): verify_execution_read(changed)


def test_new_clock_and_repeat_candidates_round_trip_through_comparator_contracts():
    repeat = {"changeType": "MANUAL", "repeatCount": 2,
              "phaseOrRepeat": [phase(value=10000), phase(value=10000)]}
    read = build(routed_source(), plan_capture([phase("DISTANCE", 20), repeat, phase()]))
    result = build_comparison_read(read, include_bundle=True, include_source=True)
    assert verify_comparison_read(result)
    assert sum(row["alignment_status"] == "MATCHED_CANDIDATE" for row in result["comparison"]["rows"]) == 6
    assert result["actual_phase_alignment_verified"] is False
    assert result["numeric_output_authorized"] is False
