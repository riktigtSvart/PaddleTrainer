"""Source projection and owned read-only HTTP, using the existing isolated DB fixture."""
from copy import deepcopy
from uuid import UUID
import json
import os
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.models.entities import PlannedWorkout, User, WorkoutBlock, WorkoutSession, BlockType
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from app.services import session_analysis as service
from tests.planning.test_p2_4c6_calendar_workspace import agenda, ACTUAL, PLAN, OTHER_PLAN
from tests.planning.test_p2_4c3_goal_workflow_api import count, OTHER_EMAIL

BASE = "/api/v1/planning/calendar/sessions/"


def raw():
    return {"exerciseSamples": [{"startTime": "2026-10-23T17:35:00", "samples": {"samples": [
        {"type": "HEART_RATE", "intervalMillis": 1000, "values": [100, 101, None, 103, 0]},
        {"type": "SPEED", "intervalMillis": 2000, "values": [12, 0, 10, None]},
        {"type": "DISTANCE", "intervalMillis": 1000, "values": [0, 3, 6, 9]},
        {"type": "CADENCE", "intervalMillis": 1000, "values": [30, 31, 32]},
        {"type": "LEFT_CRANK_CURRENT_POWER", "intervalMillis": 1000, "values": [90, 100]},
        {"type": "RIGHT_CRANK_CURRENT_POWER", "intervalMillis": 1000, "values": [95, 105]},
        {"type": "ALTITUDE", "intervalMillis": 1000, "values": [-2, 0, 2]},
        {"type": "TEMPERATURE", "intervalMillis": None, "values": [-4, 2]},
        {"type": "UNKNOWN_INTERVAL", "values": [1, 2]},
    ]}}]}


def get(env, identity=ACTUAL, status=200, query=""):
    response = env.client.get(BASE + identity + query)
    assert response.status_code == status, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def test_real_details_keep_owner_summary_plan_source_and_zero_without_writes(agenda):
    source = raw()
    with Session(agenda.engine) as db:
        db.get(WorkoutSession, UUID(ACTUAL)).raw_data = source
        db.add(WorkoutBlock(id=UUID(int=90001), workout_id=UUID(PLAN), position=0, block_type=BlockType.WARMUP,
            name="Warmup <script>literal</script>", distance_m=1000, repeat_count=1))
        db.commit()
    result = get(agenda)
    assert result["session"]["calories"] == 0 and result["session"]["avg_hr"] is None
    assert result["plan"]["id"] == PLAN and result["plan"]["blocks"][0]["duration_sec"] is None
    assert result["plan"]["planned_start_time"].endswith("+00:00")
    assert result["session"]["started_at"].endswith("+00:00")
    assert not result["workouts_changed"] and not result["planning_authorized"]
    assert result["link_state"] == "linked" and len(result["samples"]["series"]) == 8
    assert count(agenda, PlanningAuditArtifactRow) == 0
    with Session(agenda.engine) as db:
        assert db.get(WorkoutSession, UUID(ACTUAL)).raw_data == source
        assert db.get(PlannedWorkout, UUID(PLAN)).duration_sec == 2700
    assert all(not request.in_transaction() for request in agenda.requests)
    target = os.environ.get("P24C9_FIXTURE_OUTPUT")
    if target:
        Path(target).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_other_owner_and_missing_session_are_indistinguishable(agenda):
    one = get(agenda, str(UUID(int=702099)), 404)
    two = get(agenda, str(UUID(int=123)), 404)
    assert one == two == {"detail": {"code": "CALENDAR_SESSION_NOT_FOUND"}}


def test_linked_foreign_plan_never_exposes_its_fields(agenda):
    with Session(agenda.engine) as db:
        db.get(WorkoutSession, UUID(ACTUAL)).planned_workout_id = UUID(OTHER_PLAN)
        db.commit()
    result = get(agenda)
    assert result["plan"] is None and result["link_state"] == "linked_plan_unavailable"
    assert "Other owner" not in json.dumps(result)


def test_unlinked_session_never_gains_a_plan_by_name_or_time(agenda):
    with Session(agenda.engine) as db:
        row = db.get(WorkoutSession, UUID(ACTUAL)); row.planned_workout_id = None
        row.name = db.get(PlannedWorkout, UUID(PLAN)).title
        db.commit()
    result = get(agenda)
    assert result["plan"] is None and result["link_state"] == "unlinked"


def test_query_fields_and_write_methods_are_closed(agenda):
    for query in ("?include_raw=true", "?start_date=2026-10-23", "?url=http://invalid.example", "?a=1&a=2"):
        get(agenda, status=422, query=query)
    assert agenda.client.post(BASE + ACTUAL, json={}).status_code == 405
    assert agenda.client.patch(BASE + ACTUAL, json={}).status_code == 405
    get(agenda, "bad-id", 422)


def test_read_without_configured_owner_does_not_create_one(agenda, monkeypatch):
    from types import SimpleNamespace
    from app.api.routes import planning_goals
    before = count(agenda, User)
    monkeypatch.setattr(planning_goals, "get_settings", lambda: SimpleNamespace(demo_user_email="missing@example.invalid"))
    get(agenda, status=404)
    assert count(agenda, User) == before


def test_nonpolar_summary_remains_available_without_guessed_samples(agenda):
    with Session(agenda.engine) as db:
        row = db.get(WorkoutSession, UUID(ACTUAL)); row.external_provider = "FUTURE_PROVIDER"; row.raw_data = raw(); db.commit()
    result = get(agenda)
    assert result["session"]["distance_m"] == 8000
    assert result["samples"]["series"] == [] and result["samples"]["issues"] == ["PROVIDER_SAMPLES_UNSUPPORTED"]


def test_invalid_values_keep_source_indices_and_missing_counts():
    source = {"exerciseSamples": [{"samples": [{"type": "SPEED", "intervalMillis": 1000,
        "values": [None, True, "2", float("nan"), float("inf"), -2, 0, 12]}]}]}
    series = service.samples(source, "POLAR")["series"][0]
    assert series["values"] == [None] * 6 + [0, 12]
    assert series["missing_sample_count"] == 6 and series["valid_sample_count"] == 2
    assert series["source_path"] == "exerciseSamples[0].samples[0]"
    assert source["exerciseSamples"][0]["samples"][0]["values"][1] is True


@pytest.mark.parametrize("interval", [None, 0, -1, True, 1.5, "1000", 86_400_001])
def test_unknown_or_invalid_sample_interval_never_invents_timing(interval):
    source = raw(); source["exerciseSamples"][0]["samples"]["samples"][0]["intervalMillis"] = interval
    series = service.samples(source, "POLAR")["series"][0]
    assert series["interval_ms"] is None and series["values"][:2] == [100, 101]


def test_native_exercise_container_and_two_exercises_stay_separate():
    source = raw(); exercises = source.pop("exerciseSamples"); source["exercises"] = exercises * 2
    result = service.samples(source, "POLAR")
    assert [e["index"] for e in result["exercises"]] == [0, 1]
    assert len(result["series"]) == 16
    assert result["series"][8]["source_path"] == "exercises[1].samples.samples[0]"


def test_two_native_views_are_not_counted_twice():
    source = raw(); source["exercises"] = deepcopy(source["exerciseSamples"])
    result = service.samples(source, "POLAR")
    assert len(result["series"]) == 8 and "PREFERRED_EXERCISE_SAMPLES_VIEW" in result["issues"]


def test_unknown_channels_and_malformed_containers_remain_explained():
    source = {"exerciseSamples": [None, {"samples": []}, {"samples": {"samples": [
        False, {"type": "HEART_RATE", "values": "invalid"}, {"type": "FUTURE_SIGNAL", "values": [2]},
    ]}}]}
    result = service.samples(source, "POLAR")
    assert result["series"][0]["values"] == []
    assert result["unsupported"][0]["source_type"] == "FUTURE_SIGNAL"
    assert result["issues"] == ["EXERCISE_INVALID:0", "SERIES_INVALID:2:0"]


@pytest.mark.parametrize("limit", ["MAX_EXERCISES", "MAX_SERIES", "MAX_SERIES_SLOTS", "MAX_SLOTS"])
def test_oversized_sources_are_rejected_not_silently_truncated(monkeypatch, limit):
    monkeypatch.setattr(service, limit, 0)
    with pytest.raises(service.CalendarRuleError, match="SOURCE_TOO_LARGE"):
        service.samples(raw(), "POLAR")


def test_large_source_error_remains_read_only_and_actionable(agenda, monkeypatch):
    with Session(agenda.engine) as db: db.get(WorkoutSession, UUID(ACTUAL)).raw_data = raw(); db.commit()
    monkeypatch.setattr(service, "MAX_SLOTS", 1)
    result = get(agenda, status=409)
    assert result["detail"]["code"] == "CALENDAR_SESSION_SOURCE_TOO_LARGE"
    assert count(agenda, PlanningAuditArtifactRow) == 0
    assert all(not r.in_transaction() for r in agenda.requests)
