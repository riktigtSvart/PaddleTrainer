"""Owned C10 prescriptions, manual leaves, repeat wrappers and sample clock guards."""
from copy import deepcopy
import json
import os
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from app.models.entities import BlockType, PlannedWorkout, WorkoutBlock, WorkoutSession
from app.services.session_plan_timeline import plan_timeline
from app.services.polar_plan_projection_repair import normalized
from app.services.session_sample_clock import clock_issues, sample_clock_issues
from tests.planning.test_p2_4c6_calendar_workspace import ACTUAL, PLAN, OTHER_PLAN, agenda
from tests.planning.test_p2_4c9_session_analysis import get


def native():
    return {"session": {"id": "c10-synthetic-target"}, "exercise": [{"type": "PHASED", "phaseOrRepeat": [
        {"name": "Warmup", "changeType": "AUTOMATIC", "goal": {"type": "DURATION", "duration": 10000}},
        {"repeatCount": 2, "changeType": "MANUAL", "phaseOrRepeat": [
            {"name": "Work <script>literal</script>", "changeType": "MANUAL", "goal": {"type": "DURATION", "duration": 6000},
             "intensity": {"type": "SPEED_ZONES", "lowerZone": 2, "upperZone": 2}},
            {"name": "Rest", "changeType": "AUTOMATIC", "goal": {"type": "DURATION", "duration": 2000},
             "intensity": {"type": "HEART_RATE_ZONES", "lowerZone": 1, "upperZone": 3}},
        ]},
    ]}]}


def measured():
    return {"exerciseSamples": [{"startTime": "2026-08-01T06:00:00", "stopTime": "2026-08-01T06:00:36", "pauseTimes": [],
        "zones": [{"type": "ZONE_TYPE_SPEED", "zones": [{"lowerLimit": a, "higherLimit": b} for a, b in [(0, 8), (8, 12), (12, 16), (16, 20), (20, 40)]]},
                  {"type": "ZONE_TYPE_HEART_RATE", "zones": [{"lowerLimit": a, "higherLimit": a + 20} for a in [80, 100, 120, 140, 160]]}],
        "samples": {"samples": [
            {"type": "DISTANCE", "intervalMillis": 1000, "values": [3 * i for i in range(37)]},
            {"type": "HEART_RATE", "intervalMillis": 1000, "values": [100 + i for i in range(37)]},
            {"type": "SPEED", "intervalMillis": 1000, "values": [[6, 10, 14][i % 3] for i in range(37)]},
            {"type": "LEFT_CRANK_CURRENT_POWER", "intervalMillis": 1000, "values": [50] * 37},
            {"type": "RIGHT_CRANK_CURRENT_POWER", "intervalMillis": 1000, "values": [60] * 37},
        ]}}]}


def seed(env, *, blocks=True):
    source = native()
    with Session(env.engine) as db:
        plan = db.get(PlannedWorkout, UUID(PLAN))
        plan.source, plan.polar_target_id, plan.raw_data = "POLAR", "c10-synthetic-target", source
        if blocks:
            nodes = normalized(source["exercise"][0]["phaseOrRepeat"])
            ids = {node["key"]: UUID(int=910000 + i) for i, node in enumerate(nodes)}
            for i, node in enumerate(nodes):
                db.add(WorkoutBlock(id=ids[node["key"]], workout_id=UUID(PLAN), position=i,
                    parent_block_id=ids.get(node["parent_key"]), block_type=BlockType(node["block_type"]),
                    **{k: node[k] for k in ("name", "duration_sec", "distance_m", "intensity_type", "intensity_min", "intensity_max", "repeat_count")}))
        db.get(WorkoutSession, UUID(ACTUAL)).raw_data = measured()
        db.commit()


def test_actual_owned_read_restores_leaf_metadata_from_the_exact_matching_native_tree(agenda):
    seed(agenda)
    before = measured()
    data = get(agenda)
    phases = data["plan_timeline"]["parts"][0]["phases"]
    assert len(phases) == 5 and [p["advance"] for p in phases] == ["AUTOMATIC", "MANUAL", "AUTOMATIC", "MANUAL", "AUTOMATIC"]
    assert phases[1]["target"] == {"type": "SPEED_ZONES", "low": 2, "high": 2}
    assert phases[1]["source_block_id"] == phases[3]["source_block_id"]
    assert phases[1]["id"] != phases[3]["id"]
    assert phases[1]["source_pointer"] == "exercise[0].phaseOrRepeat[1].phaseOrRepeat[0]"
    assert len(data["samples"]["content_hash"]) == 64
    assert data["samples"]["exercises"][0]["clock_issues"] == []
    with Session(agenda.engine) as db:
        assert db.get(WorkoutSession, UUID(ACTUAL)).raw_data == before
        assert db.get(PlannedWorkout, UUID(PLAN)).raw_data == native()
        assert len(db.get(PlannedWorkout, UUID(PLAN)).blocks) == 4
    assert all(not s.in_transaction() for s in agenda.requests)
    output = os.environ.get("P24C10_FIXTURE_OUTPUT")
    if output:
        Path(output).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_raw_fallback_preserves_leaf_rules_without_assigning_container_manual_to_children(agenda):
    seed(agenda, blocks=False)
    data = get(agenda)
    assert data["plan_timeline"]["source"] == "stored_polar_target"
    assert [p["advance"] for p in data["plan_timeline"]["parts"][0]["phases"]] == ["AUTOMATIC", "MANUAL", "AUTOMATIC", "MANUAL", "AUTOMATIC"]


@pytest.mark.parametrize("mutation", ["target_id", "duration", "name", "repeat", "intensity", "source"])
def test_mismatching_native_metadata_cannot_be_applied_to_stored_blocks(agenda, mutation):
    seed(agenda)
    with Session(agenda.engine) as db:
        p = db.get(PlannedWorkout, UUID(PLAN))
        raw = deepcopy(p.raw_data)
        if mutation == "target_id": raw["session"]["id"] = "other"
        elif mutation == "duration": raw["exercise"][0]["phaseOrRepeat"][0]["goal"]["duration"] += 1000
        elif mutation == "name": raw["exercise"][0]["phaseOrRepeat"][0]["name"] = "Different"
        elif mutation == "repeat": raw["exercise"][0]["phaseOrRepeat"][1]["repeatCount"] = 3
        elif mutation == "intensity": raw["exercise"][0]["phaseOrRepeat"][1]["phaseOrRepeat"][0]["intensity"]["lowerZone"] = 1
        else: p.source = "MANUAL"
        p.raw_data = raw
        db.commit()
    phases = get(agenda)["plan_timeline"]["parts"][0]["phases"]
    assert all(p["advance"] == "UNKNOWN" and p["source_pointer"] is None for p in phases)


def test_a_change_only_in_advance_mode_invalidates_the_plan_fingerprint(agenda):
    seed(agenda)
    first = get(agenda)
    with Session(agenda.engine) as db:
        p = db.get(PlannedWorkout, UUID(PLAN))
        raw = deepcopy(p.raw_data)
        raw["exercise"][0]["phaseOrRepeat"][0]["changeType"] = "MANUAL"
        p.raw_data = raw
        db.commit()
    second = get(agenda)
    assert first["plan_timeline"]["content_hash"] != second["plan_timeline"]["content_hash"]
    assert first["samples"]["content_hash"] == second["samples"]["content_hash"]


def test_sample_changes_invalidate_reference_binding_without_using_retrieval_time(agenda):
    seed(agenda)
    first, again = get(agenda), get(agenda)
    assert first["samples"]["content_hash"] == again["samples"]["content_hash"]
    with Session(agenda.engine) as db:
        row = db.get(WorkoutSession, UUID(ACTUAL))
        raw = deepcopy(row.raw_data)
        raw["exerciseSamples"][0]["samples"]["samples"][1]["values"][0] += 1
        row.raw_data = raw
        db.commit()
    assert first["samples"]["content_hash"] != get(agenda)["samples"]["content_hash"]


def test_foreign_link_never_exposes_the_other_plan_transition_rules(agenda):
    seed(agenda)
    with Session(agenda.engine) as db:
        db.get(WorkoutSession, UUID(ACTUAL)).planned_workout_id = UUID(OTHER_PLAN)
        db.commit()
    data = get(agenda)
    assert data["plan"] is None and data["plan_timeline"]["parts"] == []


def test_interior_recording_pause_is_not_treated_as_an_ordinary_manual_wait(agenda):
    seed(agenda)
    with Session(agenda.engine) as db:
        row = db.get(WorkoutSession, UUID(ACTUAL))
        raw = deepcopy(row.raw_data)
        raw["exerciseSamples"][0]["pauseTimes"] = [{"startTime": "2026-08-01T06:00:12", "endTime": "2026-08-01T06:00:14"}]
        row.raw_data = raw
        db.commit()
    assert get(agenda)["samples"]["exercises"][0]["clock_issues"] == ["INTERIOR_RECORDING_PAUSE_REQUIRES_CLOCK_ALIGNMENT"]


def test_terminal_pause_does_not_invent_an_interior_gap():
    exercise = measured()["exerciseSamples"][0]
    exercise["pauseTimes"] = [{"startTime": "2026-08-01T06:00:36.500", "endTime": "2026-08-01T06:00:39"}]
    assert clock_issues(exercise) == []


@pytest.mark.parametrize("pauses", [[None], [{"startTime": "invalid"}], "invalid"])
def test_invalid_pause_clock_is_explicitly_unresolved(pauses):
    exercise = measured()["exerciseSamples"][0]
    exercise["pauseTimes"] = pauses
    assert clock_issues(exercise) == ["RECORDING_PAUSE_CLOCK_UNRESOLVED"]


def test_a_pause_in_the_exact_other_native_view_cannot_be_hidden_by_preferred_samples():
    raw = measured()
    primary = raw["exerciseSamples"][0]
    other = deepcopy(primary)
    other["pauseTimes"] = [{"startTime": "2026-08-01T06:00:12", "endTime": "2026-08-01T06:00:14"}]
    raw["exercises"] = [other]
    assert sample_clock_issues(primary, raw, 0, "exerciseSamples") == ["INTERIOR_RECORDING_PAUSE_REQUIRES_CLOCK_ALIGNMENT"]


def test_an_ambiguous_other_pause_clock_is_withheld_instead_of_merged():
    raw = measured()
    other = deepcopy(raw["exerciseSamples"][0])
    other["startTime"] = "2026-08-01T07:00:00"
    other["pauseTimes"] = [{"startTime": "2026-08-01T07:00:12", "endTime": "2026-08-01T07:00:14"}]
    raw["exercises"] = [other]
    assert sample_clock_issues(raw["exerciseSamples"][0], raw, 0, "exerciseSamples") == ["RECORDING_PAUSE_CLOCK_UNRESOLVED"]


@pytest.mark.parametrize("field", ["goal", "intensity"])
def test_nonstructural_manual_repeat_wrapper_does_not_provide_automatic_child_clocks(agenda, field):
    seed(agenda)
    with Session(agenda.engine) as db:
        p = db.get(PlannedWorkout, UUID(PLAN))
        raw = deepcopy(p.raw_data)
        raw["exercise"][0]["phaseOrRepeat"][1][field] = {"type": "MANUAL"}
        p.raw_data = raw
        db.commit()
    assert all(p["advance"] == "UNKNOWN" for p in get(agenda)["plan_timeline"]["parts"][0]["phases"])


def test_exact_native_fractional_duration_is_kept_when_the_orm_projection_truncates_seconds(agenda):
    seed(agenda)
    with Session(agenda.engine) as db:
        p = db.get(PlannedWorkout, UUID(PLAN))
        raw = deepcopy(p.raw_data)
        raw["exercise"][0]["phaseOrRepeat"][0]["goal"]["duration"] = 10000.5
        p.raw_data = raw
        db.commit()
    phases = get(agenda)["plan_timeline"]["parts"][0]["phases"]
    assert phases[0]["duration_ms"] == 10000.5 and phases[0]["advance"] == "AUTOMATIC"
