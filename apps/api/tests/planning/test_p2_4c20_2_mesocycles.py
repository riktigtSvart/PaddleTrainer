"""Civil-date coordination and immutable cycle references through owned HTTP."""
import asyncio
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from itertools import pairwise
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from app.models.entities import PlannedWorkout, Sport, WorkoutSession
from app.services import training_mesocycles as cycles
from app.services import training_plans
from tests.planning.test_p2_4a2_planning_utility_storage import AsyncSQLiteBridge
from tests.planning.test_p2_4c3_goal_workflow_api import ATHLETE, count
from tests.planning.test_p2_4c5r2_athlete_setup import post as setup_post
from tests.planning.test_p2_4c5r2_athlete_setup import profile
from tests.planning.test_p2_4c18_4_training_plan import accept, add_session, post, review
from tests.planning.test_p2_4c19_plan_choices import assessed_strength, choice, configure
from tests.planning.test_p2_4c19_training_options import HOME, SLOT, WATER, body, save
from tests.planning.test_p2_4c19_training_options import opportunities as opportunities_fixture


@pytest.fixture
def planner(tmp_path, monkeypatch):
    yield from opportunities_fixture.__wrapped__(tmp_path, monkeypatch)


def full(env, reset=False, first="2026-10-24", last="2026-12-17"):
    return post(env, "review", {"start_date": first, "end_date": last,
        **({"coordinate_mesocycles": True} if reset else {})})["review"]


def prepared(env):
    configure(env)
    add_session(env, token=202001, duration_sec=4500,
        started_at=datetime(2026, 10, 12, 6, tzinfo=UTC), ended_at=datetime(2026, 10, 12, 7, 15, tzinfo=UTC))


@pytest.mark.parametrize("length", [14, 21, 28, 29, 35, 42])
def test_saved_lengths_partition_real_civil_dates_across_dst(length):
    first = date(2026, 10, 22)
    data = {"start_date": first.isoformat(), "end_date": (first + timedelta(days=length - 1)).isoformat(),
        "periods": [{"id": "cycle", "period_type": "MESOCYCLE", "start_date": first.isoformat(), "end_date": (first + timedelta(days=length - 1)).isoformat()}]}
    budget = {"max_sessions_per_7_days": 3, "max_minutes_per_7_days": 180}
    blocks = cycles.build(data, budget)["blocks"]
    assert blocks[0]["start_date"] == "2026-10-22" and blocks[-1]["end_date"] == data["end_date"]
    assert sum((date.fromisoformat(b["end_date"]) - date.fromisoformat(b["start_date"])).days + 1 for b in blocks) == length
    assert all(date.fromisoformat(a["end_date"]) + timedelta(days=1) == date.fromisoformat(b["start_date"]) for a, b in pairwise(blocks))
    assert all(0 <= b["max_minutes"] <= 180 and b["max_minutes"] % 5 == 0 for b in blocks)
    if length == 28:
        assert [b["volume_percent"] for b in blocks] == [80, 90, 100, 70]
        assert [b["max_minutes"] for b in blocks] == [140, 160, 180, 125]
    if length == 29:
        assert blocks[-1]["max_minutes"] == 20 and blocks[-1]["volume_percent"] == 80
    assert cycles.build({**data, "start_date": (first + timedelta(days=3)).isoformat()}, budget, True)["blocks"][0] == blocks[0]


def test_full_horizon_fits_blocks_shared_rolling_budgets_and_repeated_acceptance(planner):
    prepared(planner)
    before = count(planner, PlannedWorkout)
    value = full(planner, True)
    context, proposals = value["result"]["mesocycle_coordination"], value["result"]["proposals"]
    assert context["mode"] == "coordinated" and len(context["recommended_mesocycle_ids"]) == 2
    assert count(planner, PlannedWorkout) == before and proposals
    assert proposals == sorted(proposals, key=lambda c: c["date"])
    for b in context["blocks"]:
        rows = [c for c in proposals if b["start_date"] <= c["date"] <= b["end_date"]]
        assert len(rows) <= b["max_sessions"] and sum(c["duration_sec"] for c in rows) <= b["max_minutes"] * 60
        assert all(c["training_period_id"] == b["mesocycle_id"] for c in rows)
    for c in proposals:
        rows = [v for v in proposals if 0 <= (date.fromisoformat(v["date"]) - date.fromisoformat(c["date"])).days <= 6]
        assert len(rows) <= 3 and sum(v["duration_sec"] for v in rows) <= 10800
    assert all((datetime.fromisoformat(b["start_at"]) - datetime.fromisoformat(a["start_at"])).total_seconds() >= (48 if a["sport"] == b["sport"] == "STRENGTH" else 24 if "STRENGTH" in [a["sport"], b["sport"]] or a["sport"] == b["sport"] else 12) * 3600 for a, b in pairwise(proposals))
    assert full(planner)["artifact_id"] == value["artifact_id"]
    accept(planner, value)
    repeated = full(planner)
    assert not repeated["result"]["create"] and not repeated["result"]["cancel"]


def test_primary_strength_and_technique_are_separately_represented(planner):
    prepared(planner)
    value = full(planner)
    b = value["result"]["mesocycle_coordination"]["blocks"][0]
    keys = {c["capability_key"] for c in value["result"]["proposals"] if c["date"] <= b["end_date"]}
    assert {"MAX_STRENGTH", "TECHNICAL_SKILL"} <= keys


def test_sunday_only_strength_remains_available_beside_daily_running(planner):
    value = body()
    value["data"]["locations"][0].update(sports=["KAYAK", "STRENGTH"], resources=["Kajak", "Kézisúlyzó"])
    value["data"]["weekly_slots"] = [{"id": SLOT, "start_date": "2026-10-23", "end_date": None, "weekdays": [6], "details": {"start_time": "08:00", "end_time": "10:00", "max_minutes": 90, "location_ids": [WATER]}},
        {"id": str(UUID(int=202010)), "start_date": "2026-10-23", "end_date": None, "weekdays": [0, 1, 2, 3, 4, 5], "details": {"start_time": "08:00", "end_time": "10:00", "max_minutes": 90, "location_ids": [HOME]}}]
    save(planner, value)
    add_session(planner, token=202011, sport=Sport.STRENGTH)
    add_session(planner, token=202012, sport=Sport.RUNNING, started_at=datetime(2026, 10, 18, 6, tzinfo=UTC), ended_at=datetime(2026, 10, 18, 6, 45, tzinfo=UTC), duration_sec=2700)
    assessed_strength(planner)
    assert next(c for c in full(planner)["result"]["proposals"] if c["date"] == "2026-10-25")["sport"] == "STRENGTH"


def test_short_mode_is_compatible_and_explicit_mode_requires_a_boolean(planner):
    assert review(planner)["result"]["mesocycle_coordination"]["mode"] == "short_review"
    assert full(planner, True, last="2026-10-29")["coordinate_mesocycles"]
    r = planner.client.post(planner.plan_url + "/review", json={"start_date": "2026-10-24", "end_date": "2026-10-29", "coordinate_mesocycles": 1})
    assert r.status_code == 422


def test_shorter_completion_does_not_ratchet_frozen_duration_or_weekly_base(planner):
    prepared(planner)
    first = full(planner, True)
    budget = deepcopy(first["result"]["prescription_context"]["starting_budget"])
    add_session(planner, token=202030, duration_sec=1200, started_at=datetime(2026, 10, 22, 6, tzinfo=UTC), ended_at=datetime(2026, 10, 22, 6, 20, tzinfo=UTC))
    frozen = full(planner)
    assert frozen["calibration_review"]["artifact_id"] == first["artifact_id"]
    for key in ["mode", "max_sessions_per_7_days", "max_minutes_per_7_days"]:
        assert frozen["result"]["prescription_context"]["starting_budget"][key] == budget[key]
    assert all(m["reference_cap_seconds"] == 4500 for m in frozen["result"]["prescription_context"]["by_candidate"].values() if m["family_key"] == "KAYAK_EASY_TECHNICAL")
    reset = full(planner, True)
    assert reset["calibration_review"] is None
    assert any(m["reference_cap_seconds"] == 1200 for m in reset["result"]["prescription_context"]["by_candidate"].values() if m["family_key"] == "KAYAK_EASY_TECHNICAL")


def test_lower_current_profile_cap_wins_over_frozen_base(planner):
    prepared(planner)
    full(planner, True)
    p = profile(token=202040, previous=planner.profile)
    p["data"].update(target_sport="Kajak", resources=["Kajak", "Kézisúlyzó"], typical_days_per_week=2, typical_minutes_per_week=90)
    setup_post(planner, "profiles", p)
    prep = full(planner)["result"]["preparation"]
    assert prep["max_sessions_per_7_days"] == 2 and prep["max_minutes_per_7_days"] == 90


def test_corrected_source_requires_fresh_base(planner):
    prepared(planner)
    full(planner, True)
    with Session(planner.engine) as db:
        db.get(WorkoutSession, UUID(int=202001)).duration_sec = 1200
        db.commit()
    r = post(planner, "review", {"start_date": "2026-10-24", "end_date": "2026-12-17"}, 409)
    assert r["detail"]["code"] == "TRAINING_PLAN_CALIBRATION_CHANGED"
    assert full(planner, True)["calibration_review"] is None


def test_choice_and_monitor_keep_explicit_future_review_beyond_old_acceptance(planner):
    prepared(planner)
    old = accept(planner, review(planner))["artifact"]
    initial = full(planner, True)
    group = next(g for g in initial["result"]["alternatives"] if len(g["candidates"]) > 1)
    other = next(c for c in group["candidates"] if c["candidate_key"] != group["selected_candidate_key"])
    selected = choice(planner, initial, group["date"], other["candidate_key"])["review"]
    assert selected["coordinate_mesocycles"] and selected["end_date"] > old["end_date"]
    before = count(planner, PlannedWorkout)

    async def refresh():
        with Session(planner.engine) as db:
            return await training_plans.refresh_active(AsyncSQLiteBridge(db), ATHLETE)

    result = asyncio.run(refresh())
    assert result[0]["review"]["end_date"] == selected["end_date"]
    assert count(planner, PlannedWorkout) == before
