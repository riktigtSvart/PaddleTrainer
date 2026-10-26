"""Calendar HTTP contract, durable goal retries and owner-safe real projections."""

from datetime import UTC, date, datetime
from uuid import UUID

import pytest
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.api.routes import planning_calendar as api
from app.db.base import Base
from app.models.entities import PlannedWorkout, Sport, WorkoutBlock, WorkoutSession, WorkoutStatus
from app.planning.application import calendar_workspace as service
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from tests.planning.test_p2_4c3_goal_workflow_api import ATHLETE, OTHER, count
from tests.planning.test_p2_4c5r2_athlete_setup import calendar, intake as intake_fixture

BASE = "/api/v1/planning/calendar"
PLAN = str(UUID(int=701001))
UNTIMED = str(UUID(int=701002))
ACTUAL = str(UUID(int=702001))
OTHER_PLAN = str(UUID(int=701099))


@pytest.fixture
def agenda(tmp_path, monkeypatch):
    wrapper = intake_fixture.__wrapped__(tmp_path, monkeypatch)
    env = next(wrapper)
    Base.metadata.create_all(env.engine, tables=[WorkoutBlock.__table__])
    env.app.include_router(api.router, prefix="/api/v1")
    monkeypatch.setattr(service, "_now", env.clock.tick)
    with Session(env.engine) as session:
        session.add_all([
            PlannedWorkout(id=UUID(PLAN), user_id=UUID(ATHLETE), date=date(2026, 10, 23),
                planned_start_time=datetime(2026, 10, 23, 15, 30, tzinfo=UTC),
                sport=Sport.KAYAK, title="VO2 in name is not a goal declaration", duration_sec=2700),
            PlannedWorkout(id=UUID(UNTIMED), user_id=UUID(ATHLETE), date=date(2026, 10, 23),
                planned_start_time=None, sport=Sport.RUNNING, title="Untimed", duration_sec=None),
            PlannedWorkout(id=UUID(OTHER_PLAN), user_id=UUID(OTHER), date=date(2026, 10, 23),
                sport=Sport.STRENGTH, title="Other owner"),
        ])
        session.flush()
        session.add_all([
            WorkoutSession(id=UUID(ACTUAL), user_id=UUID(ATHLETE), external_provider="POLAR", external_id="calendar-session",
                sport=Sport.KAYAK, started_at=datetime(2026, 10, 23, 15, 35, tzinfo=UTC),
                ended_at=datetime(2026, 10, 23, 16, 25, tzinfo=UTC), duration_sec=2700,
                distance_m=8000, calories=0, avg_hr=None, planned_workout_id=UUID(PLAN), raw_data={"unchanged": True}),
            WorkoutSession(id=UUID(int=702099), user_id=UUID(OTHER), external_provider="POLAR", external_id="other-calendar-session",
                sport=Sport.RUNNING, started_at=datetime(2026, 10, 23, 15, 35, tzinfo=UTC), raw_data={}),
        ])
        session.commit()
    try:
        yield env
    finally:
        wrapper.close()


def get(env, query="?start_date=2026-10-23&end_date=2026-10-23", status=200):
    response = env.client.get(BASE + "/feed" + query)
    assert response.status_code == status, response.text
    assert response.headers["Cache-Control"] == "no-store"
    return response.json()


def goal(entity=PLAN, kind="planned", token=710001, primary="VO2_CAPACITY", previous=None):
    return {"request_id": str(UUID(int=token)), "entity_kind": kind, "entity_id": entity,
        "primary_goal": primary, "previous_reference": previous}


def post(env, payload, status=201):
    response = env.client.post(BASE + "/goals", json=payload)
    assert response.status_code == status, response.text
    assert response.headers["Cache-Control"] == "no-store"
    return response.json()


def test_bounded_feed_preserves_unknowns_and_never_infers_a_goal(agenda):
    data = get(agenda)
    assert data["schema_version"] == service.SCHEMA
    assert len(data["planned"]) == 2 and len(data["sessions"]) == 1
    assert data["sessions"][0]["calories"] == 0
    assert data["sessions"][0]["avg_hr"] is None
    assert all(p["goal_tag"] is None for p in data["planned"])
    untimed = next(p for p in data["planned"] if p["id"] == UNTIMED)
    assert untimed["planned_start_time"] is None and untimed["duration_sec"] is None
    assert next(p for p in data["planned"] if p["id"] == PLAN)["planned_start_time"].endswith("+00:00")
    assert data["availability"]["days"] == []
    assert data["availability"]["absence_means_unavailable"] is False
    assert count(agenda, PlanningAuditArtifactRow) == 0
    assert all(not request.in_transaction() for request in agenda.requests)


def test_explicit_goal_is_durable_and_does_not_change_prescription_or_raw_data(agenda):
    saved = post(agenda, goal())
    assert saved["committed"] and not saved["workouts_changed"] and not saved["planning_authorized"]
    assert saved["artifact"]["content_hash"] == service.artifact_hash(saved["artifact"])
    data = get(agenda)
    assert next(p for p in data["planned"] if p["id"] == PLAN)["goal_tag"]["primary_goal"] == "VO2_CAPACITY"
    assert data["sessions"][0]["linked_goal_tag"]["primary_goal"] == "VO2_CAPACITY"
    assert data["sessions"][0]["goal_tag"] is None
    with Session(agenda.engine) as session:
        p, a = session.get(PlannedWorkout, UUID(PLAN)), session.get(WorkoutSession, UUID(ACTUAL))
        assert p.duration_sec == 2700 and p.status == WorkoutStatus.PLANNED
        assert p.planned_start_time.hour == 15
        assert a.raw_data == {"unchanged": True}


def test_identical_retry_is_one_audit_record_and_changed_payload_is_rejected(agenda):
    body = goal()
    first = post(agenda, body)
    again = post(agenda, body, 200)
    assert again["reused"] and again["artifact"] == first["artifact"]
    post(agenda, {**body, "primary_goal": "MAX_STRENGTH"}, 409)
    assert count(agenda, PlanningAuditArtifactRow) == 1


def test_request_uuid_cannot_be_retargeted_to_another_owned_workout(agenda):
    post(agenda, goal())
    post(agenda, goal(entity=ACTUAL, kind="session"), 409)
    assert count(agenda, PlanningAuditArtifactRow) == 1


def test_revision_cas_clear_and_historical_retry_does_not_restore_old_goal(agenda):
    old = post(agenda, goal())["artifact"]
    ref = service.reference(old)
    new_body = goal(token=710002, primary=None, previous=ref)
    new = post(agenda, new_body)["artifact"]
    assert new["revision"] == 2 and new["proposal"]["primary_goal"] is None
    assert new["content_hash"] == service.artifact_hash(new)
    post(agenda, goal(token=710003, primary="MAX_STRENGTH"), 409)
    post(agenda, goal(), 200)
    current = next(p for p in get(agenda)["planned"] if p["id"] == PLAN)["goal_tag"]
    assert current["artifact_id"] == new["artifact_id"] and current["primary_goal"] is None


def test_actual_can_have_its_own_explicit_goal(agenda):
    post(agenda, goal())
    post(agenda, goal(entity=ACTUAL, kind="session", token=710002, primary="RECOVERY"))
    actual = get(agenda)["sessions"][0]
    assert actual["goal_tag"]["primary_goal"] == "RECOVERY"
    assert actual["linked_goal_tag"]["primary_goal"] == "VO2_CAPACITY"


@pytest.mark.parametrize("entity,kind", [(OTHER_PLAN, "planned"), (str(UUID(int=999999)), "session")])
def test_other_owner_or_missing_entity_cannot_be_tagged(agenda, entity, kind):
    post(agenda, goal(entity=entity, kind=kind), 404)
    assert count(agenda, PlanningAuditArtifactRow) == 0


@pytest.mark.parametrize("query", ["?start_date=2026-10-23", "?start_date=2026-02-30&end_date=2026-03-01", "?start_date=2026-10-23&end_date=2026-10-22", "?start_date=2025-01-01&end_date=2026-10-23", "?start_date=2026-10-23&start_date=2026-10-24&end_date=2026-10-24", "?unknown=1"])
def test_bad_ranges_and_queries_are_rejected(agenda, query):
    get(agenda, query, 422)


@pytest.mark.parametrize("changes", [{"primary_goal": "RUNNING"}, {"primary_goal": "MAX_STRENGTH", "duration_sec": 1200}, {"entity_kind": "other"}, {"entity_id": "bad"}])
def test_input_cannot_smuggle_a_plan_mutation(agenda, changes):
    post(agenda, {**goal(), **changes}, 422)
    assert count(agenda, PlanningAuditArtifactRow) == 0


def test_overnight_session_and_availability_are_retained_at_range_start(agenda):
    with Session(agenda.engine) as session:
        session.add(WorkoutSession(user_id=UUID(ATHLETE), external_provider="POLAR", external_id="overnight",
            sport=Sport.KAYAK, started_at=datetime(2026, 10, 22, 21, 30, tzinfo=UTC),
            ended_at=None, duration_sec=7200, raw_data={}))
        session.commit()
    body = calendar(first="2026-10-22", length=2)
    body["data"]["days"][0]["windows"] = [{**body["data"]["days"][0]["windows"][0],
        "start_time": "23:00", "end_time": "01:00", "ends_next_day": True, "max_minutes": 60}]
    body["data"]["days"][0]["max_total_minutes"] = 60
    response = agenda.client.post("/api/v1/planning/athlete/availability", json=body)
    assert response.status_code == 201, response.text
    data = get(agenda)
    assert any(s["external_id"] == "overnight" for s in data["sessions"])
    assert len(data["availability"]["carry_windows"]) == 1


def test_dense_range_is_explicitly_rejected_never_silently_truncated(agenda, monkeypatch):
    monkeypatch.setattr(service, "ROW_LIMIT", 1)
    result = get(agenda, status=409)
    assert result["detail"]["code"] == "CALENDAR_RANGE_TOO_DENSE"


def test_tampered_annotation_is_not_used_for_display(agenda):
    saved = post(agenda, goal())["artifact"]
    with Session(agenda.engine) as session:
        session.execute(update(PlanningAuditArtifactRow).where(PlanningAuditArtifactRow.artifact_id == saved["artifact_id"]).values(content_hash="0" * 64))
        session.commit()
    get(agenda, status=503)


def test_commit_outcome_can_be_recovered_with_the_same_body(agenda, monkeypatch):
    original = service.setup.commit
    async def disconnected_after_commit(session):
        await original(session)
        raise RuntimeError("synthetic lost reply")
    monkeypatch.setattr(service.setup, "commit", disconnected_after_commit)
    body = goal()
    post(agenda, body, 503)
    assert count(agenda, PlanningAuditArtifactRow) == 1
    monkeypatch.setattr(service.setup, "commit", original)
    assert post(agenda, body, 200)["reused"]
