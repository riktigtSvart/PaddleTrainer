"""Personal starting doses through owned HTTP; no production DB/provider calls."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from app.models.entities import Sport, WorkoutSession
from app.services import training_plan_policy as policy
from app.services import training_prescriptions as doses
from tests.planning.test_p2_4c3_goal_workflow_api import ATHLETE, OTHER
from tests.planning.test_p2_4c5r2_athlete_setup import post as setup_post
from tests.planning.test_p2_4c5r2_athlete_setup import profile
from tests.planning.test_p2_4c18_4_training_plan import accept, add_session, owned_plans, review
from tests.planning.test_p2_4c19_training_options import HOME, SLOT, WATER, body, save
from tests.planning.test_p2_4c19_training_options import opportunities as opportunities_fixture
from tests.planning.test_p2_4c20_execution_reconciliation import sync_receipt


@pytest.fixture
def planner(tmp_path, monkeypatch):
    yield from opportunities_fixture.__wrapped__(tmp_path, monkeypatch)


def locations(env, *, places=None, minutes=90):
    value = body()
    value["data"]["weekly_slots"] = [{"id": SLOT, "start_date": "2026-10-23", "end_date": None,
        "weekdays": list(range(7)), "details": {"start_time": "08:00", "end_time": "10:00",
        "max_minutes": minutes, "location_ids": places or [HOME]}}]
    return save(env, value)


def completed(env, token, sport=Sport.RUNNING, minutes=35, day="2026-10-18", **changes):
    start = datetime.fromisoformat(day).replace(hour=6, tzinfo=UTC)
    add_session(env, token=token, sport=sport, started_at=start,
                ended_at=start + timedelta(minutes=minutes), duration_sec=minutes * 60, **changes)


def test_home_running_needs_no_borrowed_boat_or_dumbbell(planner):
    locations(planner, minutes=25)
    completed(planner, 201001)
    value = review(planner)
    candidates = value["result"]["proposals"]
    assert candidates and all(c["sport"] == "RUNNING" and c["duration_sec"] == 1500 for c in candidates)
    for c in candidates:
        assert sum(b["duration_sec"] for b in c["blocks"]) == c["duration_sec"]
        meta = value["result"]["prescription_context"]["by_candidate"][c["candidate_key"]]
        assert meta["reference_session_ids"] == [str(UUID(int=201001))]
        assert not meta["progression_applied"] and meta["rpe"] == {"min": 2, "max": 3}
    assert not any("EQUIPMENT_NOT_DECLARED" in issue["codes"] for issue in value["result"]["preparation"]["selection_issues"])
    assert any(d["reason"] == "PLANNED_RECOVERY_DAY" for d in value["result"]["days_without_proposal"])
    saved = accept(planner, value)["artifact"]
    assert len(owned_plans(planner)) == len(saved["created_workouts"])
    repeated = review(planner)
    assert not repeated["result"]["create"] and not repeated["result"]["cancel"]


def test_kayak_history_is_not_a_personal_running_reference(planner):
    locations(planner)
    completed(planner, 201002, Sport.KAYAK, 60)
    value = review(planner)
    assert value["result"]["proposals"]
    for meta in value["result"]["prescription_context"]["by_candidate"].values():
        assert meta["reference_session_ids"] == [] and meta["product_default_used"]
        assert meta["running"]["mode"] == "run_walk_start"


@pytest.mark.parametrize("minutes,expected", [(19, None), (20, 20), (27, 25), (37, 35), (55, 45)])
def test_runtime_duration_fits_reference_and_window(planner, minutes, expected):
    locations(planner, minutes=minutes)
    completed(planner, 201003, minutes=45)
    value = review(planner)
    assert {c["duration_sec"] // 60 for c in value["result"]["proposals"]} == ({expected} if expected else set())


def test_reference_uses_latest_three_usable_same_sport_runs_and_skips_shorter_history(planner):
    locations(planner)
    for token, minutes, day in [(201010, 45, "2026-09-14"), (201011, 40, "2026-10-09"),
                                 (201012, 25, "2026-10-10"), (201013, 35, "2026-10-11")]:
        completed(planner, token, minutes=minutes, day=day)
    completed(planner, 201014, sport=Sport.KAYAK, minutes=90)
    completed(planner, 201015, minutes=15, user_id=UUID(OTHER))
    value = review(planner)
    assert {p["duration_sec"] for p in value["result"]["proposals"]} == {1500}
    assert all(meta["reference_session_ids"] == [str(UUID(int=i)) for i in [201013, 201012, 201011]]
               for meta in value["result"]["prescription_context"]["by_candidate"].values())
    with Session(planner.engine) as db:
        row = db.get(WorkoutSession, UUID(int=201013))
        row.duration_sec = 900
        db.commit()
    later = review(planner)
    assert later["result"]["proposals"]
    assert all(meta["reference_cap_seconds"] == 1500 and meta["reference_session_ids"] ==
        [str(UUID(int=i)) for i in [201012, 201011, 201010]]
        for meta in later["result"]["prescription_context"]["by_candidate"].values())


def test_private_history_is_56_days_while_public_input_contract_stays_14(planner):
    locations(planner)
    completed(planner, 201020, day="2026-09-15")
    value = review(planner)
    assert value["result"]["proposals"]
    assert str(UUID(int=201020)) in {s["id"] for s in value["inputs"]["recent_sessions"]}
    response = planner.client.get("/api/v1/planning/cycles/programs/" + planner.program["artifact_id"] + "/planning-inputs",
                                  params={"start_date": "2026-10-24", "end_date": "2026-10-29"})
    assert response.status_code == 200, response.text
    assert str(UUID(int=201020)) not in {s["id"] for s in response.json()["recent_sessions"]}


@pytest.mark.parametrize("problem", ["unknown_duration", "inconsistent_duration", "not_finished", "future", "too_old"])
def test_unusable_own_records_never_authorize_a_personal_running_dose(planner, problem):
    locations(planner)
    completed(planner, 201030, day="2026-08-01" if problem == "too_old" else "2026-10-18")
    with Session(planner.engine) as db:
        row = db.get(WorkoutSession, UUID(int=201030))
        if problem == "unknown_duration": row.duration_sec = None
        elif problem == "inconsistent_duration": row.duration_sec = 7200
        elif problem == "not_finished": row.ended_at = None
        elif problem == "future":
            row.started_at = datetime(2026, 10, 25, 6, tzinfo=UTC)
            row.ended_at = datetime(2026, 10, 25, 7, tzinfo=UTC)
        db.commit()
    value = review(planner)
    assert value["result"]["proposals"]
    for meta in value["result"]["prescription_context"]["by_candidate"].values():
        assert meta["reference_session_ids"] == [] and meta["reference_cap_seconds"] is None
        assert meta["product_default_used"] and meta["duration_sec"] == 1200
        assert meta["running"]["mode"] == ("experience_start" if problem == "too_old" else "run_walk_start")


def historic_weeks(env, *, empty_last=False, unknown=False):
    p = profile(token=201099, previous=env.profile)
    p["data"].update(target_sport="Kajak", resources=["Kajak"], typical_days_per_week=6, typical_minutes_per_week=600)
    setup_post(env, "profiles", p)
    for week, first in enumerate([datetime(2026, 10, 5), datetime(2026, 10, 12)]):
        for index in range(0 if empty_last and week == 1 else 4):
            completed(env, 201100 + week * 10 + index, Sport.KAYAK, 60,
                      day=(first + timedelta(days=index)).date().isoformat())
    if unknown:
        with Session(env.engine) as db:
            db.get(WorkoutSession, UUID(int=201110)).duration_sec = None
            db.commit()


def test_larger_starting_budget_requires_two_complete_verified_weeks(planner):
    historic_weeks(planner)
    locations(planner, places=[WATER, HOME])
    assert review(planner)["result"]["preparation"]["max_sessions_per_7_days"] == 3
    sync_receipt(planner, first="2026-10-05", last="2026-10-19")
    value = review(planner)
    budget = value["result"]["prescription_context"]["starting_budget"]
    assert budget["mode"] == "observed_covered_weeks"
    assert budget["used_week_starts"] == ["2026-10-05", "2026-10-12"]
    assert budget["max_sessions_per_7_days"] == 4 and budget["max_minutes_per_7_days"] == 240
    assert value["result"]["preparation"]["max_minutes_per_7_days"] == 240
    for week in budget["weeks"]:
        if week["status"] == "coverage_missing": assert week["duration_sec"] is None
    assert all(c["duration_sec"] <= 3600 for c in value["result"]["proposals"])
    sync_receipt(planner, token=201199, first="2026-10-05", last="2026-10-19")
    assert review(planner)["artifact_id"] == value["artifact_id"]


@pytest.mark.parametrize("problem", ["empty_week", "incomplete_records", "skipped_import"])
def test_missing_unknown_or_empty_weeks_do_not_invent_personal_capacity(planner, problem):
    historic_weeks(planner, empty_last=problem == "empty_week", unknown=problem == "incomplete_records")
    reports = None
    if problem == "skipped_import":
        reports = [{"dataset": "sessions", "state": "succeeded", "imported": 8,
                    "updated": 0, "skipped": 1, "skip_reasons": {"missing_start": 1}, "error_code": None}]
    sync_receipt(planner, first="2026-10-05", last="2026-10-19", datasets=["sessions"], reports=reports)
    budget = review(planner)["result"]["prescription_context"]["starting_budget"]
    assert budget["mode"] == "declared_and_product_defaults"
    assert budget["max_sessions_per_7_days"] == 3 and budget["max_minutes_per_7_days"] == 180
    assert budget["used_week_starts"] == []


def test_strength_duration_alone_does_not_imply_assessed_familiarity(planner):
    completed(planner, 201300, Sport.STRENGTH, minutes=25)
    value = review(planner)
    candidates = [c for g in value["result"]["alternatives"] for c in g["candidates"] if c["sport"] == "STRENGTH"]
    assert candidates and all(c['template_version'] == 'v0.4' and not c.get('strength_prescription') for c in candidates)
    assert all(value['result']['prescription_context']['by_candidate'][c['candidate_key']]['introductory_strength']['full_development_claim'] is False for c in candidates)
    assert value['result']['strength_assessment']['issues'] == ['STRENGTH_ASSESSMENT_MISSING']


def test_older_covered_weeks_cannot_replace_a_missing_recent_week(planner):
    historic_weeks(planner)
    for index in range(4):
        completed(planner, 201400 + index, Sport.KAYAK, 60,
                  day=(datetime(2026, 9, 28) + timedelta(days=index)).date().isoformat())
    sync_receipt(planner, first="2026-09-28", last="2026-10-12")
    budget = review(planner)["result"]["prescription_context"]["starting_budget"]
    assert sum(w["status"] == "covered" for w in budget["weeks"]) == 2
    assert budget["mode"] == "declared_and_product_defaults"
    assert budget["used_week_starts"] == []


def test_short_recorded_kayak_never_falls_back_to_longer_product_default():
    template = next(t for t in policy.TEMPLATES if t["key"] == "KAYAK_EASY_TECHNICAL")
    value, error = doses.parameterize(template, available_seconds=3600, block=policy.block,
                                    reference={"cap_seconds": 900, "session_ids": [ATHLETE], "anchor_id": ATHLETE})
    assert value is None and error == "PERSONAL_DURATION_REFERENCE_TOO_SHORT"
