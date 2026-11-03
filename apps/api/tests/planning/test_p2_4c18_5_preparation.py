"""Owned HTTP, immutable history, ongoing availability and bounded extrapolation."""
from datetime import UTC, date, datetime, timedelta
from math import log2
from uuid import UUID

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.entities import PlannedWorkout, Sport, WorkoutSession
from app.planning.domain import calendar_duration as duration
from app.planning.domain.athlete_setup import digest
from app.planning.domain.common.serialization import canonical_json
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from app.schemas.athlete_setup import ProfileData, SessionWindow
from tests.planning.test_p2_4c18_4_training_plan import planner, review, add_session
from tests.planning.test_p2_4c5r2_athlete_setup import intake, profile, post as setup_post, get as setup_get
from tests.planning.test_p2_4c81r1_calendar_duration import agenda, get, observation, NOW, TARGET, ATHLETE
from tests.planning.test_p2_4c81_calendar_constraints import body, details, rule


@pytest.mark.parametrize("target", [5000, 6000, 7000, 8000, 10000])
def test_five_km_supports_nearby_unseen_distances_with_five_percent_per_doubling(target):
    e = duration.estimate(owner=ATHLETE, plan_id=TARGET, sport="KAYAK", distance_m=target,
        cutoff=NOW, observations=[observation(distance=5000, seconds=1500)])
    assert e["duration_sec"] == round(1500 * (target / 5000) ** (1 + log2(1.05)))
    assert e["method"] == "personal_power_law_median_v1"
    assert not e["range_is_calibrated"] and not e["personal_coefficient_fitted"]
    assert e["conditions_verified"] is False and e["coefficient_source"] == "planning_default"
    assert e["extrapolated"] == (target != 5000)


@pytest.mark.parametrize("distance", [50, 2000, 10001, 42000])
def test_large_distance_changes_stay_unestimated(distance):
    assert duration.estimate(owner=ATHLETE, plan_id=TARGET, sport="RUNNING", distance_m=distance,
        cutoff=NOW, observations=[observation(sport="RUNNING", distance=5000, seconds=1500)]) is None


def test_future_knowledge_and_short_sprint_do_not_become_endurance_references():
    for row in [observation(available_at=(NOW + timedelta(seconds=1)).isoformat()), observation(seconds=299)]:
        assert duration.estimate(owner=ATHLETE, plan_id=TARGET, sport="KAYAK", distance_m=6000,
            cutoff=NOW, observations=[row]) is None


@pytest.mark.parametrize("value", [-1, 21, True, 1.5])
def test_profile_rejects_invalid_slowdown_setting(value):
    with pytest.raises(ValueError):
        ProfileData(duration_doubling_slowdown_pct=value)


def test_new_time_window_has_general_opportunity_defaults_but_explicit_unknown_survives():
    args = dict(key="w", start_time="18:00", end_time="19:00", max_minutes=60)
    general = SessionWindow(**args)
    assert general.sport_scope == general.effort_cap == "any"
    unknown = SessionWindow(**args, sport_scope="unknown", effort_cap="unknown")
    assert unknown.sport_scope == unknown.effort_cap == "unknown"


def test_pre_c18_5_profile_is_still_readable_and_can_be_revised(intake):
    saved = setup_post(intake, "profiles", profile())["artifact"]
    saved["proposal"]["data"].pop("duration_doubling_slowdown_pct")
    saved["content_hash"] = digest({k: v for k, v in saved.items() if k != "content_hash"})
    with Session(intake.engine) as db:
        row = db.scalar(select(PlanningAuditArtifactRow).where(PlanningAuditArtifactRow.artifact_id == saved["artifact_id"]))
        row.contract_json, row.content_hash = canonical_json(saved), saved["content_hash"]
        db.commit()
    assert setup_get(intake, "context")["profile"]["artifact"] == saved
    proposal = profile(token=185001, previous={k: saved[k] for k in ("artifact_id", "content_hash")})
    proposal["data"]["duration_doubling_slowdown_pct"] = 7
    new = setup_post(intake, "profiles", proposal)["artifact"]
    assert new["revision"] == 2 and new["proposal"]["data"]["duration_doubling_slowdown_pct"] == 7


def test_longer_calendar_plan_gets_estimate_without_rewriting_source(agenda):
    with Session(agenda.engine) as db:
        db.execute(update(PlannedWorkout).where(PlannedWorkout.id == UUID(TARGET)).values(distance_m=12000))
        db.commit()
    p = next(p for p in get(agenda)["planned"] if p["id"] == TARGET)
    e = p["duration_estimate"]
    assert p["duration_sec"] is None and e["duration_sec"] == 4200 and e["extrapolated"]
    assert e == get(agenda, "constraints")["duration_estimates"][TARGET]
    with Session(agenda.engine) as db:
        assert db.get(PlannedWorkout, UUID(TARGET)).duration_sec is None


def test_profile_coefficient_is_versioned_and_applies_only_to_its_target_sport(agenda):
    p = profile(token=185005)
    p["data"].update(target_sport="Kajak-Kenu / Kajak", duration_doubling_slowdown_pct=10)
    agenda.clock.current = NOW - timedelta(minutes=1)
    saved = setup_post(agenda, "profiles", p)["artifact"]
    with Session(agenda.engine) as db:
        db.execute(update(PlannedWorkout).where(PlannedWorkout.id == UUID(TARGET)).values(distance_m=12000))
        db.commit()
    e = get(agenda, "constraints")["duration_estimates"][TARGET]
    assert e["duration_sec"] == 4400 and e["doubling_slowdown_pct"] == 10
    assert e["coefficient_profile_reference"] == {k: saved[k] for k in ("artifact_id", "content_hash")}
    assert e["coefficient_source"] == "profile_setting"
    assert not duration.profile_matches_sport("Kajak-Kenu / Kajak", "RUNNING")


def test_weekly_general_agreement_continues_months_later_and_one_exception_is_local(agenda):
    c = get(agenda, "constraints")
    r = rule(id=str(UUID(int=185010)), start_date="2026-10-26", weekdays=list(range(7)),
        details=details(kind="available", sport_scope="any", effort_cap="any", max_minutes=60))
    proposal = body(token=185011, previous=c["reference"], rules=[r])
    response = agenda.client.post("/api/v1/planning/calendar/constraints", json=proposal)
    assert response.status_code == 201, response.text
    c = response.json()["artifact"]
    proposal = body(token=185012, previous={k: c[k] for k in ("artifact_id", "content_hash")}, rules=[r],
        exceptions=[{"rule_id": r["id"], "date": "2026-10-28", "replacement": None}])
    assert agenda.client.post("/api/v1/planning/calendar/constraints", json=proposal).status_code == 201
    current = get(agenda, "constraints")
    assert not any(g["source_date"] == "2026-10-28" for g in current["opportunities"])
    future = get(agenda, "constraints", first="2027-04-01", last="2027-04-07")
    assert len(future["opportunities"]) == 7
    assert all(g["constraints"]["sport_scope"] == g["constraints"]["effort_cap"] == "any" for g in future["opportunities"])
    assert all(g["known"] and g["usable_minutes"] == 60 for g in future["opportunities"])


def test_planner_uses_estimated_upper_bound_and_polling_stays_idempotent(planner):
    add_session(planner, distance_m=6000, duration_sec=2000,
        ended_at=datetime(2026, 10, 21, 6, 33, 20, tzinfo=UTC))
    imported = UUID(int=185020)
    with Session(planner.engine) as db:
        db.add(PlannedWorkout(id=imported, user_id=UUID(ATHLETE), sport=Sport.KAYAK,
            title="9km continuous", date=date(2026, 10, 24),
            planned_start_time=datetime(2026, 10, 24, 6, tzinfo=UTC),
            distance_m=9000, duration_sec=None, source="POLAR"))
        db.commit()
    v = review(planner)
    prep = v["result"]["preparation"]
    assert str(imported) in prep["estimated_duration_workout_ids"]
    assert str(imported) not in prep["unknown_duration_workout_ids"]
    e = next(p for p in v["plan_snapshots"] if p["workout"]["id"] == str(imported))["duration_estimate"]
    assert e["upper_sec"] > e["duration_sec"]
    assert review(planner) == v
    assert v["result"]["create"]
    with Session(planner.engine) as db:
        assert db.get(PlannedWorkout, imported).duration_sec is None


def test_data_gaps_have_specific_codes_without_turning_other_sport_plans_into_strength(planner):
    p = profile(token=185030, previous={k: planner.profile[k] for k in ("artifact_id", "content_hash")})
    p["data"].update(target_sport="Kajak", resources=[])
    setup_post(planner, "profiles", p)
    # Per-window resources are separate declarations and must also be absent.
    c = planner.availability["proposal"].copy()
    c["request_id"] = str(UUID(int=185031))
    c["previous_reference"] = {k: planner.availability[k] for k in ("artifact_id", "content_hash")}
    for day in c["data"]["days"]:
        for w in day["windows"]: w["resources"] = []
    setup_post(planner, "availability", c)
    v = review(planner)
    assert not v["result"]["create"]
    prep = v["result"]["preparation"]
    assert not prep["equipment_declared"]
    assert all("EQUIPMENT_NOT_DECLARED" in d["codes"] for d in prep["selection_issues"])
    assert not prep["reference_templates"]
