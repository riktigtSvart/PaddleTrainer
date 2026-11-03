"""Real owned HTTP and SQLite transactions; no provider or production DB."""

from datetime import UTC, date, datetime
from uuid import UUID

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.routes import training_plans as api
from app.models.entities import (
    AthleteReadiness,
    PlannedWorkout,
    Sport,
    WorkoutBlock,
    WorkoutSession,
)
from app.planning.domain.athlete_setup import digest, reference
from app.planning.domain.persistence.audit import AuditArtifactKind as Kind
from app.services import training_plans as service
from tests.planning.test_p2_4c3_goal_workflow_api import ATHLETE, OTHER_EMAIL, count
from tests.planning.test_p2_4c5r2_athlete_setup import calendar, profile, window
from tests.planning.test_p2_4c5r2_athlete_setup import post as setup_post
from tests.planning.test_p2_4c18_planning_inputs import inputs as inputs_fixture


@pytest.fixture
def planner(tmp_path, monkeypatch):
    wrapper = inputs_fixture.__wrapped__(tmp_path, monkeypatch)
    env = next(wrapper)
    env.clock.current = datetime(2026, 10, 23, 10, tzinfo=UTC)
    monkeypatch.setattr(service, "_now", env.clock.tick)
    env.app.include_router(api.router, prefix="/api/v1")
    env.plan_url = (
        "/api/v1/planning/cycles/programs/" + env.program["artifact_id"] + "/training-plan"
    )
    with Session(env.engine) as db:
        db.execute(delete(WorkoutSession).where(WorkoutSession.user_id == UUID(ATHLETE)))
        db.execute(delete(PlannedWorkout).where(PlannedWorkout.user_id == UUID(ATHLETE)))
        db.commit()
    p = profile()
    p["data"].update(
        target_sport="Kajak",
        resources=["Kajak", "Kézisúlyzó"],
        typical_days_per_week=3,
        typical_minutes_per_week=180,
    )
    env.profile = setup_post(env, "profiles", p)["artifact"]
    c = calendar(first="2026-10-23", length=8)
    for day in c["data"]["days"]:
        day.update(
            status="available",
            max_total_minutes=90,
            windows=[
                {
                    **window(start="08:00", end="10:00", minutes=90),
                    "sports": ["Kajak", "Erőnlét"],
                    "effort_cap": "moderate",
                    "resources": ["Kajak", "Kézisúlyzó"],
                }
            ],
        )
    env.availability = setup_post(env, "availability", c)["artifact"]
    macro = next(p for p in env.program["periods"] if p["period_type"] == "MACROCYCLE")
    mesos = [p for p in env.program["periods"] if p["period_type"] == "MESOCYCLE"]
    keys = ["TECHNICAL_SKILL", "PERIPHERAL_OXIDATIVE_CAPACITY", "MAX_STRENGTH"]
    goals = {
        "macrocycle_period_id": macro["id"],
        "revision": 1,
        "supersedes": None,
        "goals": [
            {"capability_key": key, "role": "primary_development", "rationale": "explicit"}
            for key in keys
        ],
        "mesocycle_directives": [
            {
                "mesocycle_period_id": p["id"],
                "capability_key": key,
                "role": "primary_development",
                "rationale": "explicit",
            }
            for p in mesos
            for key in keys
        ],
        "rationale": "test",
    }
    response = env.client.post("/api/v1/planning/goals/macrocycle-plans", json=goals)
    assert response.status_code == 201, response.text
    try:
        yield env
    finally:
        wrapper.close()


def post(env, operation, body, expected=200):
    r = env.client.post(env.plan_url + "/" + operation, json=body)
    assert r.status_code == expected, r.text
    assert r.headers["Cache-Control"] == "no-store"
    return r.json()


def review(env, first="2026-10-24", last="2026-10-29"):
    return post(env, "review", {"start_date": first, "end_date": last})["review"]


def accept(env, value, token=180401, expected=201):
    return post(
        env,
        "accept",
        {
            "request_id": str(UUID(int=token)),
            "review_reference": reference(value),
            "acknowledge_reviewed_plan": True,
        },
        expected,
    )


def add_session(env, token=180499, **changes):
    row = {
        "id": UUID(int=token),
        "user_id": UUID(ATHLETE),
        "external_provider": "MANUAL",
        "external_id": str(token),
        "sport": Sport.KAYAK,
        "started_at": datetime(2026, 10, 21, 6, tzinfo=UTC),
        "ended_at": datetime(2026, 10, 21, 7, tzinfo=UTC),
        "duration_sec": 3600,
        "created_at": datetime(2026, 10, 21, 8, tzinfo=UTC),
        "raw_data": {},
    }
    row.update(changes)
    with Session(env.engine) as db:
        db.add(WorkoutSession(**row))
        db.commit()


def owned_plans(env):
    with Session(env.engine) as db:
        return db.scalars(
            select(PlannedWorkout)
            .where(PlannedWorkout.user_id == UUID(ATHLETE))
            .order_by(PlannedWorkout.date)
        ).all()


def test_first_plan_is_hashed_durable_but_creates_no_workout_until_explicit_acceptance(planner):
    before = count(planner, PlannedWorkout)
    v = review(planner)
    assert v["content_hash"] == digest({k: x for k, x in v.items() if k != "content_hash"})
    assert v["result"]["create"] and not v["result"]["cancel"]
    assert all(c["template_key"] == "KAYAK_EASY_TECHNICAL" for c in v["result"]["create"])
    assert not v["committed_plan"] and not v["result"]["personal_model_applied"]
    assert count(planner, PlannedWorkout) == before
    saved = accept(planner, v)
    assert len(saved["artifact"]["created_workouts"]) == len(v["result"]["create"])
    for row in owned_plans(planner):
        assert row.source == "PADDLETRAINER_C18_4" and row.training_period_id is not None
    assert all(not r.in_transaction() for r in planner.requests)


def test_same_review_and_exact_acceptance_retry_do_not_duplicate(planner):
    v = review(planner)
    assert review(planner) == v
    saved = accept(planner, v)
    assert accept(planner, v, expected=200)["artifact"] == saved["artifact"]
    accept(planner, v, token=180402, expected=409)
    assert len(owned_plans(planner)) == len(v["result"]["create"])
    later = review(planner)
    assert not later["result"]["create"] and not later["result"]["cancel"]
    assert set(later["result"]["keep"]) == set(saved["artifact"]["created_workouts"])


def test_long_and_strength_samples_need_actual_sport_references(planner):
    add_session(planner)
    add_session(
        planner,
        token=180498,
        sport=Sport.STRENGTH,
        started_at=datetime(2026, 10, 18, 6, tzinfo=UTC),
        ended_at=datetime(2026, 10, 18, 6, 30, tzinfo=UTC),
        duration_sec=1800,
    )
    v = review(planner)
    kinds = {p["template_key"] for p in v["result"]["proposals"]}
    assert "KAYAK_LONG_AEROBIC" in kinds and "STRENGTH_REFERENCE_AND_DEVELOPMENT" in kinds
    assert all(
        p["duration_reference_session_id"]
        for p in v["result"]["proposals"]
        if p["template_key"] != "KAYAK_EASY_TECHNICAL"
    )


def test_new_execution_after_preview_rejects_stale_acceptance_without_partial_writes(planner):
    v = review(planner)
    add_session(planner)
    before = count(planner, PlannedWorkout)
    result = accept(planner, v, expected=409)
    assert result["detail"]["code"] == "TRAINING_PLAN_REVIEW_CHANGED"
    assert count(planner, PlannedWorkout) == before


def test_manual_edit_and_imported_plan_are_preserved(planner):
    saved = accept(planner, review(planner))["artifact"]
    key = next(iter(saved["created_workouts"]))
    with Session(planner.engine) as db:
        db.get(PlannedWorkout, UUID(key)).title = "My manually edited plan"
        db.add(
            PlannedWorkout(
                id=UUID(int=180496),
                user_id=UUID(ATHLETE),
                sport=Sport.KAYAK,
                title="Imported",
                date=date(2026, 10, 25),
                source="POLAR",
                polar_target_id="keep-me",
                duration_sec=1800,
            )
        )
        db.commit()
    v = review(planner)
    assert key in v["result"]["protected_workout_ids"]
    assert key not in v["result"]["cancel"]
    assert str(UUID(int=180496)) in v["result"]["protected_workout_ids"]


def test_elapsed_unknown_is_not_missed_and_late_sync_corrects_it(planner):
    saved = accept(planner, review(planner))["artifact"]
    row = owned_plans(planner)[0]
    planner.clock.current = datetime(2026, 10, 24, 12, tzinfo=UTC)
    v = review(planner)
    unknown = next(e for e in v["result"]["events"] if e.get("workout_id") == str(row.id))
    assert unknown["kind"] == "execution_unknown" and unknown["can_confirm_missed"]
    assert str(row.id) not in v["result"]["cancel"]
    add_session(
        planner,
        planned_workout_id=row.id,
        started_at=datetime(2026, 10, 24, 6, tzinfo=UTC),
        ended_at=datetime(2026, 10, 24, 6, 30, tzinfo=UTC),
        duration_sec=1800,
        created_at=planner.clock.current,
    )
    later = review(planner)
    assert any(
        e["kind"] == "planned_completed" and e["workout_id"] == str(row.id)
        for e in later["result"]["events"]
    )
    assert not any(
        e["kind"] == "execution_unknown" and e["workout_id"] == str(row.id)
        for e in later["result"]["events"]
    )
    assert set(saved["created_workouts"]) <= {str(p.id) for p in owned_plans(planner)}


def test_confirmed_miss_is_idempotent_and_never_increases_dose(planner):
    initial = review(planner, last="2026-10-30")
    accept(planner, initial)
    row = owned_plans(planner)[0]
    planner.clock.current = datetime(2026, 10, 24, 12, tzinfo=UTC)
    v = review(planner)
    event = next(e for e in v["result"]["events"] if e.get("workout_id") == str(row.id))
    body = {
        "request_id": str(UUID(int=180490)),
        "workout_id": str(row.id),
        "expected_workout_hash": event["workout_hash"],
    }
    a = post(planner, "missed", body, 201)
    assert post(planner, "missed", body, 200)["artifact"] == a["artifact"]
    later = review(planner, last="2026-10-30")
    assert any(e["kind"] == "confirmed_missed" for e in later["result"]["events"])
    assert max((p["duration_sec"] for p in later["result"]["proposals"]), default=0) <= 1800
    assert not later["result"]["create"], (
        "A miss must not free a placement quota for a replacement workout."
    )


def test_foreign_owner_cannot_read_or_write_plan(planner):
    v = review(planner)
    planner.email = OTHER_EMAIL
    assert planner.client.get(planner.plan_url).status_code == 404
    post(planner, "review", {"start_date": "2026-10-24", "end_date": "2026-10-29"}, 404)
    accept(planner, v, expected=409)


@pytest.mark.parametrize(
    "change",
    [
        {"acknowledge_reviewed_plan": False},
        {"acknowledge_reviewed_plan": 1},
        {"duration_sec": 9999},
    ],
)
def test_acceptance_rejects_missing_review_or_smuggled_dose(planner, change):
    v = review(planner)
    post(
        planner,
        "accept",
        {
            "request_id": str(UUID(int=180402)),
            "review_reference": reference(v),
            "acknowledge_reviewed_plan": True,
            **change,
        },
        422,
    )


def test_profile_pause_and_resource_restriction_block_prescription(planner):
    p = profile(61002, planner.profile)
    p["data"].update(participation="paused", target_sport="Kajak")
    setup_post(planner, "profiles", p)
    v = review(planner)
    assert v["result"]["blockers"] and not v["result"]["create"]


def test_failed_second_insertion_rolls_back_every_workout(planner, monkeypatch):
    v = review(planner)
    original = service.persist

    async def fail(repo, owner, kind, value):
        if kind == Kind.TRAINING_PLAN_ACCEPTANCE:
            raise RuntimeError("synthetic write failure")
        return await original(repo, owner, kind, value)

    monkeypatch.setattr(service, "persist", fail)
    accept(planner, v, expected=503)
    assert not owned_plans(planner)
    monkeypatch.setattr(service, "persist", original)
    assert accept(planner, v)["committed"]


def test_lost_reply_can_recover_original_receipt(planner, monkeypatch):
    v = review(planner)
    original = service.transactions.commit

    async def disconnected(session):
        await original(session)
        raise RuntimeError("synthetic lost reply")

    monkeypatch.setattr(service.transactions, "commit", disconnected)
    accept(planner, v, expected=503)
    monkeypatch.setattr(service.transactions, "commit", original)
    assert accept(planner, v, expected=200)["reused"]


@pytest.mark.asyncio
async def test_monitor_catches_unplanned_execution_and_coalesces_repeat(planner):
    accept(planner, review(planner))
    from tests.planning.test_p2_4a2_planning_utility_storage import AsyncSQLiteBridge

    with Session(planner.engine, expire_on_commit=False) as db:
        first = await service.refresh_active(AsyncSQLiteBridge(db), ATHLETE)
    add_session(planner)
    with Session(planner.engine, expire_on_commit=False) as db:
        next_run = await service.refresh_active(AsyncSQLiteBridge(db), ATHLETE)
        again = await service.refresh_active(AsyncSQLiteBridge(db), ATHLETE)
    assert not next_run[0]["reused"] and again[0]["reused"]
    assert any(
        e["kind"] == "unplanned_completed" for e in next_run[0]["review"]["result"]["events"]
    )
    assert first


def test_changed_calendar_replaces_only_untouched_future_samples_and_keeps_history(planner):
    original = accept(planner, review(planner))["artifact"]
    c = calendar(token=62002, previous=planner.availability, first="2026-10-23", length=8)
    for d in c["data"]["days"]:
        d.update(status="unavailable", windows=[], max_total_minutes=None)
    setup_post(planner, "availability", c)
    v = review(planner)
    assert set(v["result"]["cancel"]) == set(original["created_workouts"])
    accepted = accept(planner, v, token=180402)["artifact"]
    assert not accepted["created_workouts"]
    assert {str(w.id) for w in owned_plans(planner)} == set(original["created_workouts"])
    assert all(w.status.value == "CANCELLED" for w in owned_plans(planner))


def test_link_arriving_before_acceptance_blocks_the_stale_change(planner):
    accept(planner, review(planner))
    row = owned_plans(planner)[0]
    # An unplanned execution changes the proposal but must not give it a right
    # to cancel a plan linked by a subsequent sync while the preview is open.
    add_session(planner)
    v = review(planner)
    add_session(planner, token=180497, planned_workout_id=row.id)
    accept(planner, v, token=180402, expected=409)
    with Session(planner.engine) as db:
        assert db.get(PlannedWorkout, row.id).status.value == "PLANNED"


def test_manual_block_change_is_protected_even_when_title_and_duration_are_unchanged(planner):
    accept(planner, review(planner))
    row = owned_plans(planner)[0]
    with Session(planner.engine) as db:
        block = db.scalars(select(WorkoutBlock).where(WorkoutBlock.workout_id == row.id)).first()
        block.name = "My revised technical cue"
        db.commit()
    v = review(planner)
    assert str(row.id) in v["result"]["protected_workout_ids"]
    assert str(row.id) not in v["result"]["cancel"]


def test_recent_illness_and_next_morning_feedback_request_review_without_claiming_adaptation(
    planner,
):
    with Session(planner.engine) as db:
        db.add(
            AthleteReadiness(user_id=UUID(ATHLETE), recorded_date=date(2026, 10, 23), illness=True)
        )
        db.commit()
    v = review(planner)
    assert "CURRENT_ILLNESS_REVIEW" in v["result"]["blockers"]
    assert not v["result"]["create"] and not v["result"]["personal_model_applied"]


def test_unknown_sport_window_does_not_become_permission(planner):
    c = calendar(token=62002, previous=planner.availability, first="2026-10-23", length=8)
    for d in c["data"]["days"]:
        d.update(
            status="available",
            max_total_minutes=45,
            windows=[{**window(), "sport_scope": "unknown", "sports": []}],
        )
    setup_post(planner, "availability", c)
    assert not review(planner)["result"]["create"]


def test_reaching_start_time_invalidates_open_preview_and_never_mutates_the_past(planner):
    v = review(planner)
    planner.clock.current = datetime(2026, 10, 24, 7, tzinfo=UTC)
    accept(planner, v, expected=409)
    assert not owned_plans(planner)


@pytest.mark.asyncio
async def test_monitor_catches_expiry_without_a_sync_and_does_not_extend_the_accepted_horizon(
    planner,
):
    accept(planner, review(planner))
    from tests.planning.test_p2_4a2_planning_utility_storage import AsyncSQLiteBridge

    planner.clock.current = datetime(2026, 10, 24, 12, tzinfo=UTC)
    with Session(planner.engine, expire_on_commit=False) as db:
        expired = await service.refresh_active(AsyncSQLiteBridge(db), ATHLETE)
    assert any(e["kind"] == "execution_unknown" for e in expired[0]["review"]["result"]["events"])
    planner.clock.current = datetime(2026, 10, 30, 12, tzinfo=UTC)
    with Session(planner.engine, expire_on_commit=False) as db:
        ended = await service.refresh_active(AsyncSQLiteBridge(db), ATHLETE)
    assert not ended[0]["review"]["result"]["proposals"]
    assert (
        ended[0]["review"]["result"]["days_without_proposal"][0]["reason"]
        == "ACCEPTED_WINDOW_ENDED"
    )


def test_budget_checks_include_future_commitments_across_the_week_boundary():
    from app.services.training_plan_policy import fits_rolling_budget

    target = date(2026, 10, 26)  # Monday
    commitments = [
        {"date": date(2026, 10, 25), "seconds": 3600},
        {"date": date(2026, 10, 28), "seconds": 3600},
    ]
    assert not fits_rolling_budget(commitments, target, 1800, 2, 10800)
    assert not fits_rolling_budget(commitments, target, 1800, 3, 7200)
    assert fits_rolling_budget(commitments, target, 1800, 3, 10800)
    assert not fits_rolling_budget([{"date": target, "seconds": None}], target, 1800, 3, 10800)


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"birth_date": None}, "AGE_UNKNOWN"),
        ({"target_sport": ""}, "TARGET_SPORT_UNKNOWN"),
        ({"sport_history_status": "unknown", "sport_history": []}, "SPORT_HISTORY_UNKNOWN"),
        ({"constraint_status": "unknown"}, "FUNCTIONAL_CONSTRAINTS_UNKNOWN"),
        ({"participation": "unknown"}, "PARTICIPATION_UNKNOWN"),
    ],
)
def test_profile_block_retains_the_specific_reason_and_no_prescription(planner, changes, reason):
    p = profile(61002, planner.profile)
    p["data"].update(changes)
    setup_post(planner, "profiles", p)
    result = review(planner)["result"]
    assert "PROFILE_REVIEW_REQUIRED" in result["blockers"]
    assert reason in result["entry_review"]["reasons"]
    assert not result["create"] and not result["cancel"]


def test_events_retain_session_name_sport_and_local_date(planner):
    add_session(planner, name="Saját technikai evezés")
    value = review(planner)
    session = next(
        s for s in value["inputs"]["recent_sessions"] if s["id"] == str(UUID(int=180499))
    )
    event = next(e for e in value["result"]["events"] if e.get("session_id") == session["id"])
    assert session["name"] == event["title"] == "Saját technikai evezés"
    assert event["sport"] == "KAYAK" and event["date"] == "2026-10-21"
    assert event["started_at"] == "2026-10-21T06:00:00+00:00"
    assert event["kind"] == "unplanned_completed"


def test_untitled_linked_session_uses_the_preserved_plan_title(planner):
    accept(planner, review(planner))
    row = owned_plans(planner)[0]
    planner.clock.current = datetime(2026, 10, 24, 12, tzinfo=UTC)
    add_session(
        planner,
        planned_workout_id=row.id,
        name=None,
        started_at=datetime(2026, 10, 24, 6, tzinfo=UTC),
        ended_at=datetime(2026, 10, 24, 6, 30, tzinfo=UTC),
        duration_sec=1800,
        created_at=planner.clock.current,
    )
    event = next(
        e
        for e in review(planner)["result"]["events"]
        if e.get("session_id") == str(UUID(int=180499))
    )
    assert event["title"] == row.title and event["date"] == "2026-10-24"
    assert event["kind"] == "planned_completed"
