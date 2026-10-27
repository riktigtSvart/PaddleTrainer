"""Distance prescriptions survive the owned read; repeat containers are not phases."""
from copy import deepcopy
import json
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from app.models.entities import BlockType, PlannedWorkout, WorkoutSession
from app.services.session_plan_timeline import plan_timeline
from tests.planning.test_p2_4c6_calendar_workspace import ACTUAL, PLAN, agenda
from tests.planning.test_p2_4c9_session_analysis import get


def native():
    def group(zone):
        return {"repeatCount": 2, "phaseOrRepeat": [
            {"name": "12 minute work", "goal": {"type": "DURATION", "duration": 720000},
             "intensity": {"type": "SPEED_ZONES", "lowerZone": zone, "upperZone": zone}},
            {"name": "2 minute rest", "goal": {"type": "DURATION", "duration": 120000}},
        ]}
    return {"session": {"id": "synthetic-mixed-target"}, "exercise": [{"phaseOrRepeat": [
        {"name": "Distance warmup", "goal": {"type": "DISTANCE", "distance": 2600}},
        group(2), group(5),
    ]}]}


def plan(raw=None, blocks=None):
    return SimpleNamespace(id=UUID(PLAN), blocks=blocks or [], source="POLAR",
                           polar_target_id="synthetic-mixed-target", raw_data=raw)


def test_native_distance_survives_both_repeat_groups_without_inventing_a_duration():
    raw = native()
    before = deepcopy(raw)
    result = plan_timeline(plan(raw))
    phases = result["parts"][0]["phases"]
    assert len(phases) == 9
    assert phases[0]["distance_m"] == 2600 and phases[0]["duration_ms"] is None
    assert phases[0]["from_ms"] == 0 and phases[0]["to_ms"] is None
    assert all(p["from_ms"] is None and p["to_ms"] is None for p in phases[1:])
    assert [p["duration_ms"] for p in phases[1:]] == [720000, 120000] * 4
    assert "1/2" in phases[1]["label"] and "2/2" in phases[3]["label"]
    assert raw == before


def test_stored_parent_repeat_counts_expand_children_instead_of_becoming_unknown_phases():
    def block(index, parent, position, kind, seconds=None, metres=None, count=1):
        return SimpleNamespace(id=UUID(int=index), parent_block_id=UUID(int=parent) if parent else None,
                               position=position, block_type=kind, name=None,
                               duration_sec=seconds, distance_m=metres, repeat_count=count)
    blocks = [block(1, None, 0, BlockType.WARMUP, metres=2600),
              block(2, None, 1, BlockType.REPEAT, count=2),
              block(3, 2, 0, BlockType.WORK, seconds=720),
              block(4, 2, 1, BlockType.RECOVERY, seconds=120),
              block(5, None, 2, BlockType.REPEAT, count=2),
              block(6, 5, 0, BlockType.WORK, seconds=720),
              block(7, 5, 1, BlockType.RECOVERY, seconds=120)]
    result = plan_timeline(plan(native(), list(reversed(blocks))))
    phases = result["parts"][0]["phases"]
    assert result["source"] == "stored_blocks" and len(phases) == 9
    assert [p["source_block_id"] for p in phases] == [str(UUID(int=i)) for i in (1, 3, 4, 3, 4, 6, 7, 6, 7)]
    assert phases[0]["distance_m"] == 2600


@pytest.mark.parametrize("value", [True, -1, "2600", float("inf"), None])
def test_invalid_distance_does_not_turn_into_an_alignable_goal(value):
    raw = native()
    raw["exercise"][0]["phaseOrRepeat"][0]["goal"]["distance"] = value
    assert "distance_m" not in plan_timeline(plan(raw))["parts"][0]["phases"][0]


def test_explicit_zero_distance_survives_and_distance_alone_changes_fingerprint():
    raw = native()
    first = plan_timeline(plan(raw))
    raw["exercise"][0]["phaseOrRepeat"][0]["goal"]["distance"] = 0
    second = plan_timeline(plan(raw))
    assert second["parts"][0]["phases"][0]["distance_m"] == 0
    assert first["content_hash"] != second["content_hash"]


def test_native_goal_type_determines_which_quantity_is_used():
    raw = native()
    goal = raw["exercise"][0]["phaseOrRepeat"][0]["goal"]
    goal["duration"] = 12000
    phase = plan_timeline(plan(raw))["parts"][0]["phases"][0]
    assert phase["duration_ms"] is None and phase["distance_m"] == 2600
    goal["type"] = "DURATION"
    phase = plan_timeline(plan(raw))["parts"][0]["phases"][0]
    assert phase["duration_ms"] == 12000 and "distance_m" not in phase


def test_owned_api_delivers_mixed_goals_and_original_distance_samples_without_writes(agenda):
    raw = {"exercises": [{"startTime": "2026-08-01T06:00:00", "samples": {"samples": [
        {"type": "DISTANCE", "intervalMillis": 1000, "values": [i * 2.6 for i in range(4436)]},
        {"type": "SPEED", "intervalMillis": 1000, "values": [9.36] * 4436},
        {"type": "HEART_RATE", "intervalMillis": 1000, "values": [140] * 4436},
    ]}}]}
    with Session(agenda.engine) as db:
        p = db.get(PlannedWorkout, UUID(PLAN))
        p.source, p.polar_target_id, p.raw_data = "POLAR", "synthetic-mixed-target", native()
        db.get(WorkoutSession, UUID(ACTUAL)).raw_data = raw
        db.commit()
    result = get(agenda)
    assert result["plan_timeline"]["parts"][0]["phases"][0]["distance_m"] == 2600
    assert len(result["plan_timeline"]["parts"][0]["phases"]) == 9
    assert result["samples"]["series"][0]["values"] == raw["exercises"][0]["samples"]["samples"][0]["values"]
    assert result["workouts_changed"] is False and result["planning_authorized"] is False
    with Session(agenda.engine) as db:
        assert db.get(WorkoutSession, UUID(ACTUAL)).raw_data == raw
        assert db.get(PlannedWorkout, UUID(PLAN)).blocks == []
    output = os.environ.get("P24C9R8_FIXTURE_OUTPUT")
    if output:
        Path(output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
