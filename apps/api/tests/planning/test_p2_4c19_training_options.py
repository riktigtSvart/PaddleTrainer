"""Actual owner-scoped HTTP, durable revisions and location-specific planner inputs."""

from copy import deepcopy
from datetime import UTC, date, datetime
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from app.api.routes import training_options as routes
from app.models.entities import PlannedWorkout, Sport
from app.planning.domain import training_options as domain
from app.planning.domain.athlete_setup import digest
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from app.schemas.training_options import OptionsInput
from app.services import training_options as service
from tests.planning.test_p2_4c3_goal_workflow_api import ATHLETE, OTHER_EMAIL, count
from tests.planning.test_p2_4c18_4_training_plan import planner as planner_fixture
from tests.planning.test_p2_4c18_4_training_plan import review

BASE = "/api/v1/planning/training-options"
WATER, POOL, HOME, SLOT = [str(UUID(int=i)) for i in range(190001, 190005)]


@pytest.fixture
def opportunities(tmp_path, monkeypatch):
    wrapper = planner_fixture.__wrapped__(tmp_path, monkeypatch)
    env = next(wrapper)
    env.app.include_router(routes.router, prefix="/api/v1")
    monkeypatch.setattr(service, "_now", env.clock.tick)
    try:
        yield env
    finally:
        wrapper.close()


def body(token=191001, previous=None, **changes):
    value = {"request_id": str(UUID(int=token)), "previous_reference": previous, "data": {
        "timezone_name": "Europe/Budapest", "schedule_start_date": "2026-10-23", "schedule_end_date": None,
        "locations": [
            {"id": WATER, "name": "Sirály csónakház", "sports": ["KAYAK"], "resources": ["Kajak"]},
            {"id": POOL, "name": "Csillaghegyi uszoda", "sports": ["SWIMMING"], "resources": []},
            {"id": HOME, "name": "Otthon", "sports": ["RUNNING", "GYMNASTICS", "STRETCHING"], "resources": []},
        ],
        "weekly_slots": [{"id": SLOT, "start_date": "2026-10-23", "end_date": None, "weekdays": list(range(7)),
            "details": {"start_time": "08:00", "end_time": "10:00", "max_minutes": 90, "location_ids": [WATER, POOL]}}],
        "exceptions": [], "restrictions": [], **changes,
    }}
    return OptionsInput.model_validate(value).model_dump(mode="json")


def save(env, value, expected=201):
    response = env.client.post(BASE, json=value)
    assert response.status_code == expected, response.text
    assert response.headers["Cache-Control"] == "no-store"
    return response.json()


def context(env, first="2026-10-24", last="2026-10-30"):
    response = env.client.get(BASE, params={"start_date": first, "end_date": last})
    assert response.status_code == 200, response.text
    return response.json()


def test_empty_read_is_read_only_and_does_not_guess_places(opportunities):
    before = count(opportunities, PlanningAuditArtifactRow)
    value = context(opportunities)
    assert value["data"]["locations"] == [] and value["data"]["schedule_start_date"] is None
    assert value["reference"] is None and value["groups"] == []
    assert value["workouts_changed"] is False and value["planning_authorized"] is False
    assert count(opportunities, PlanningAuditArtifactRow) == before
    assert all(not session.in_transaction() for session in opportunities.requests)


def test_durable_exact_retry_and_old_revision_do_not_mutate_workouts(opportunities):
    original = body()
    before = count(opportunities, PlannedWorkout)
    receipt = save(opportunities, original)
    retried = save(opportunities, original, 200)
    assert retried["reused"] and retried["artifact"] == receipt["artifact"]
    assert receipt["artifact"]["proposal"] == original
    assert context(opportunities)["reference"] == service.reference(receipt["artifact"])
    changed = body(191002, service.reference(receipt["artifact"]))
    changed["data"]["locations"][0]["notes"] = "A saját megadott lehetőségeim."
    newer = save(opportunities, changed)
    assert newer["artifact"]["revision"] == 2
    assert save(opportunities, original, 200)["artifact"] == receipt["artifact"]
    assert context(opportunities)["reference"] == service.reference(newer["artifact"])
    assert count(opportunities, PlannedWorkout) == before
    assert all(not session.in_transaction() for session in opportunities.requests)


def test_reused_token_and_stale_parent_cannot_overwrite_current_state(opportunities):
    original = body()
    receipt = save(opportunities, original)
    modified = deepcopy(original)
    modified["data"]["locations"][0]["name"] = "Másik név"
    assert save(opportunities, modified, 409)["detail"]["code"] == "TRAINING_OPTIONS_REQUEST_CONFLICT"
    assert save(opportunities, body(191002), 409)["detail"]["code"] == "TRAINING_OPTIONS_REVISION_CONFLICT"
    assert context(opportunities)["reference"] == service.reference(receipt["artifact"])


def test_location_alternatives_reach_real_inputs_without_profile_resource_union(opportunities):
    save(opportunities, body())
    result = review(opportunities)
    day = result["inputs"]["days"][0]
    assert len(day["opportunities"]) == 2
    assert {group["constraints"]["location"] for group in day["opportunities"]} == {"Sirály csónakház", "Csillaghegyi uszoda"}
    assert {group["constraints"]["alternative_group_key"] for group in day["opportunities"]} == {"options:" + SLOT + ":2026-10-24"}
    pool = next(group for group in day["opportunities"] if group["constraints"]["location_id"] == POOL)
    assert pool["constraints"]["sports"] == ["SWIMMING"] and pool["constraints"]["resources"] == []
    assert pool["constraints"]["resources_scope"] == "location"
    assert all(WATER in candidate["opportunity_key"] for candidate in result["result"]["proposals"])
    assert "training_options_reference" in result["inputs"]
    assert len(result["result"]["proposals"]) <= 3


def test_dated_restriction_expires_and_does_not_change_general_possibilities(opportunities):
    value = body()
    value["data"]["restrictions"] = [{"id": str(UUID(int=193001)), "location_id": WATER,
        "start_date": "2026-10-24", "end_date": "2026-10-24", "unavailable_sports": ["KAYAK"], "reason": "Hajózási zárlat"}]
    save(opportunities, value)
    result = context(opportunities)
    first = next(group for group in result["groups"] if group["date"] == "2026-10-24")
    next_day = next(group for group in result["groups"] if group["date"] == "2026-10-25")
    assert first["alternatives"][0]["sports"] == []
    assert next_day["alternatives"][0]["sports"] == ["KAYAK"]
    assert result["data"]["locations"][0]["sports"] == ["KAYAK"]
    assert result["data"]["weekly_slots"][0]["details"]["location_ids"] == [WATER, POOL]


def test_closed_day_overrides_old_general_availability_without_free_fallback(opportunities):
    value = body()
    value["data"]["exceptions"] = [{"slot_id": SLOT, "date": "2026-10-24", "replacement": None}]
    save(opportunities, value)
    result = review(opportunities)
    day = result["inputs"]["days"][0]
    assert day["opportunities"] == []
    assert day["availability_state"] == "declared_unavailable"
    assert all(candidate["date"] != "2026-10-24" for candidate in result["result"]["proposals"])


def test_general_weekdays_make_other_days_explicitly_unavailable(opportunities):
    value = body()
    value["data"]["weekly_slots"][0]["weekdays"] = [4]
    save(opportunities, value)
    result = review(opportunities)
    assert result["inputs"]["days"][0]["availability_state"] == "declared_unavailable"


def test_mobile_boat_transport_is_a_declared_location_condition(opportunities):
    value = body()
    value["data"]["locations"][0].update(kind="mobile", boat_transport=False)
    save(opportunities, value)
    first = context(opportunities)["groups"][0]
    assert first["alternatives"][0]["sports"] == []
    assert "BOAT_TRANSPORT_NOT_DECLARED" in first["alternatives"][0]["issues"]


def test_foreign_owner_cannot_use_another_owners_parent(opportunities):
    value = save(opportunities, body())
    opportunities.email = OTHER_EMAIL
    assert context(opportunities)["reference"] is None
    response = save(opportunities, body(191002, service.reference(value["artifact"])), 409)
    assert response["detail"]["code"] == "TRAINING_OPTIONS_REVISION_CONFLICT"


@pytest.mark.parametrize("mutation", [
    lambda value: value["data"]["weekly_slots"][0]["details"].update(location_ids=[str(UUID(int=99))]),
    lambda value: value["data"]["weekly_slots"][0]["details"].update(max_minutes=999),
    lambda value: value["data"].update(schedule_end_date="2026-02-30"),
    lambda value: value["data"]["locations"].append(deepcopy(value["data"]["locations"][0])),
])
def test_invalid_declarations_do_not_write(opportunities, mutation):
    value = body()
    mutation(value)
    before = count(opportunities, PlanningAuditArtifactRow)
    response = opportunities.client.post(BASE, json=value)
    assert response.status_code == 422, response.text
    assert count(opportunities, PlanningAuditArtifactRow) == before


def test_projection_identity_and_capacity_are_stable_not_added_for_alternatives():
    data = body()["data"]
    result = domain.expand(data, "2026-10-24", "2026-10-24", "Europe/Budapest")
    assert len(result["occurrences"]) == 2
    assert {occurrence["details"]["max_minutes"] for occurrence in result["occurrences"]} == {90}
    assert len({occurrence["details"]["alternative_group_key"] for occurrence in result["occurrences"]}) == 1
    assert digest(result) == digest(domain.expand(data, "2026-10-24", "2026-10-24", "Europe/Budapest"))


def test_existing_protected_workout_gets_location_conflict_without_mutation(opportunities):
    value = body()
    value["data"]["weekly_slots"][0]["details"]["location_ids"] = [POOL]
    save(opportunities, value)
    key = UUID(int=194100)
    with Session(opportunities.engine) as db:
        db.add(PlannedWorkout(id=key, user_id=UUID(ATHLETE), date=date(2026, 10, 24), planned_start_time=datetime(2026, 10, 24, 6, tzinfo=UTC), sport=Sport.KAYAK, title="Megőrzött saját terv", duration_sec=1800, source="POLAR"))
        db.commit()
    response = opportunities.client.get("/api/v1/planning/calendar/constraints", params={"start_date": "2026-10-24", "end_date": "2026-10-30"})
    assert response.status_code == 200, response.text
    assert any(item["code"] == "SPORT_NOT_AVAILABLE_AT_LOCATION" and item["plan_id"] == str(key) for item in response.json()["conflicts"])
    result = review(opportunities)
    assert str(key) in result["result"]["protected_workout_ids"] and str(key) not in result["result"]["cancel"]


def test_ambiguous_recurring_hour_is_unknown_until_fold_is_declared():
    value = body()["data"]
    value["weekly_slots"][0]["details"].update(start_time="02:30", end_time="03:30", max_minutes=60)
    projection = domain.expand(value, "2026-10-25", "2026-10-25", "Europe/Budapest")
    assert all(item["start_at"] is None and item["issue"] == "ATHLETE_TIME_IS_AMBIGUOUS" for item in projection["occurrences"])
    value["weekly_slots"][0]["details"]["start_fold"] = 1
    projection = domain.expand(value, "2026-10-25", "2026-10-25", "Europe/Budapest")
    assert all(item["issue"] is None and item["elapsed_minutes"] == 60 for item in projection["occurrences"])
