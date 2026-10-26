"""Real owned HTTP/storage writes and pure civil-time calendar projections."""

from copy import deepcopy
from datetime import UTC, date, datetime
from uuid import UUID

import pytest
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.entities import PlannedWorkout, Sport
from app.planning.application import calendar_constraints as service
from app.planning.domain import calendar_constraints as domain
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from app.schemas.calendar_constraints import ScheduleInput
from tests.planning.test_p2_4c3_goal_workflow_api import ATHLETE, count
from tests.planning.test_p2_4c5r2_athlete_setup import calendar
from tests.planning.test_p2_4c6_calendar_workspace import PLAN, agenda as agenda_fixture

BASE = "/api/v1/planning/calendar/constraints"
RULE = str(UUID(int=81001))
UNLINKED = str(UUID(int=81002))


def details(kind="busy", **changes):
    return {"kind": kind, "category": "work" if kind == "busy" else "training", "title": "Munka" if kind == "busy" else "Edzéslehetőség",
        "firmness": "fixed", "start_time": "17:00", "end_time": "18:00", "ends_next_day": False,
        "start_fold": None, "end_fold": None, "max_minutes": 30 if kind == "available" else None,
        "sport_scope": "unknown", "sports": [], "effort_cap": "unknown", "resources": [], "location": "", "notes": "", **changes}


def rule(**changes):
    return {"id": RULE, "start_date": "2026-10-19", "end_date": None,
        "repeat": "weekly", "weekdays": [0, 2, 4], "details": details(), **changes}


def body(token=81101, previous=None, rules=None, exceptions=None):
    return {"request_id": str(UUID(int=token)), "previous_reference": previous,
        "data": {"timezone_name": "Europe/Budapest", "rules": [rule()] if rules is None else rules,
            "exceptions": [] if exceptions is None else exceptions}}


@pytest.fixture
def agenda(tmp_path, monkeypatch):
    wrapper = agenda_fixture.__wrapped__(tmp_path, monkeypatch)
    env = next(wrapper)
    monkeypatch.setattr(service, "_now", env.clock.tick)
    with Session(env.engine) as db:
        db.add(PlannedWorkout(id=UUID(UNLINKED), user_id=UUID(ATHLETE), date=date(2026, 10, 23),
            planned_start_time=datetime(2026, 10, 23, 15, 40, tzinfo=UTC), sport=Sport.KAYAK,
            title="Separate plan", duration_sec=1200))
        db.commit()
    try:
        yield env
    finally:
        wrapper.close()


def post(env, data=None, expected=201, preview=False):
    payload = data or body()
    if preview:
        payload = {"proposal": payload, "start_date": "2026-10-19", "end_date": "2026-11-01"}
    response = env.client.post(BASE + ("/preview" if preview else ""), json=payload)
    assert response.status_code == expected, response.text
    assert response.headers["Cache-Control"] == "no-store"
    return response.json()


def get(env, start="2026-10-19", end="2026-11-01", expected=200):
    response = env.client.get(BASE, params={"start_date": start, "end_date": end})
    assert response.status_code == expected, response.text
    assert response.headers["Cache-Control"] == "no-store"
    return response.json()


def test_read_is_empty_owned_unknown_not_free_and_does_not_write(agenda):
    result = get(agenda)
    assert result["reference"] is None and result["saved"] is None
    assert result["data"]["rules"] == [] and result["occurrences"] == []
    assert result["opportunities"] == [] and result["absence_means_free"] is False
    assert result["planning_authorized"] is False and result["workouts_changed"] is False
    assert count(agenda, PlanningAuditArtifactRow) == 0
    assert all(not request.in_transaction() for request in agenda.requests)


def test_preview_is_read_only_and_records_exact_hash_and_only_unexecuted_owned_conflicts(agenda):
    result = post(agenda, expected=200, preview=True)
    assert len(result["occurrences"]) == 6
    assert result["proposal_hash"] == service.digest(body())
    assert {c["plan_id"] for c in result["conflicts"] if c["code"] == "WORKOUT_OVERLAP"} == {UNLINKED}
    assert all(c["plan_id"] != PLAN for c in result["conflicts"])
    assert any(c["code"] == "PLAN_TIME_UNKNOWN" and c["severity"] == "review" for c in result["conflicts"])
    assert result["conflicts"][0]["severity"] == "fixed"
    assert count(agenda, PlanningAuditArtifactRow) == 0


def test_save_is_durable_idempotent_and_does_not_mutate_workouts(agenda):
    saved = post(agenda)
    assert saved["committed"] and not saved["workouts_changed"] and not saved["planning_authorized"]
    assert saved["artifact"]["proposal"] == body()
    again = post(agenda, expected=200)
    assert again["artifact"] == saved["artifact"] and again["reused"]
    current = get(agenda)
    assert current["reference"] == service.reference(saved["artifact"])
    assert count(agenda, PlanningAuditArtifactRow) == 1
    with Session(agenda.engine) as db:
        assert db.get(PlannedWorkout, UUID(UNLINKED)).planned_start_time.hour == 15
        assert db.get(PlannedWorkout, UUID(PLAN)).duration_sec == 2700


def test_stale_revision_conflict_and_old_request_replay_never_restore_old_state(agenda):
    old = post(agenda)["artifact"]
    new = body(81102, service.reference(old), exceptions=[{"rule_id": RULE, "date": "2026-10-21", "replacement": None}])
    latest = post(agenda, new)["artifact"]
    assert latest["revision"] == 2
    post(agenda, body(81103), 409)
    post(agenda, expected=200)
    assert get(agenda)["reference"] == service.reference(latest)
    assert len(get(agenda)["occurrences"]) == 5


def test_request_uuid_cannot_be_reused_with_different_data(agenda):
    post(agenda)
    altered = body(); altered["data"]["rules"][0]["details"]["title"] = "Más munka"
    assert post(agenda, altered, 409)["detail"]["code"] == "CALENDAR_CONSTRAINT_REQUEST_CONFLICT"


def test_one_occurrence_changes_without_rewriting_the_weekly_rule(agenda):
    changed = details(start_time="19:00", end_time="20:00")
    payload = body(exceptions=[{"rule_id": RULE, "date": "2026-10-21", "replacement": changed}])
    post(agenda, payload)
    rows = get(agenda)["occurrences"]
    assert next(r for r in rows if r["source_date"] == "2026-10-21")["details"]["start_time"] == "19:00"
    assert all(r["details"]["start_time"] == "17:00" for r in rows if r["source_date"] != "2026-10-21")
    assert get(agenda)["data"]["rules"][0]["details"]["start_time"] == "17:00"


def test_future_split_retains_prior_occurrences_and_future_exceptions(agenda):
    split = str(UUID(int=81003))
    payload = body(rules=[rule(end_date="2026-10-21"), rule(id=split, start_date="2026-10-22", details=details(start_time="19:00", end_time="20:00"))],
        exceptions=[{"rule_id": split, "date": "2026-10-23", "replacement": None}])
    post(agenda, payload)
    rows = get(agenda)["occurrences"]
    assert next(o for o in rows if o["source_date"] == "2026-10-21")["details"]["start_time"] == "17:00"
    assert not any(o["source_date"] == "2026-10-23" for o in rows)
    assert next(o for o in rows if o["source_date"] == "2026-10-26")["details"]["start_time"] == "19:00"


def test_flexible_conflict_remains_distinct_from_a_fixed_block(agenda):
    result = post(agenda, body(rules=[rule(details=details(firmness="flexible"))]), 200, preview=True)
    assert result["conflicts"][0]["severity"] == "flexible"


def test_overnight_rule_intersects_first_visible_day_and_midnight_boundary_is_half_open(agenda):
    payload = body(rules=[rule(start_date="2026-10-22", end_date="2026-10-22", repeat="once", weekdays=[],
        details=details(start_time="23:00", end_time="01:00", ends_next_day=True))])
    post(agenda, payload)
    assert len(get(agenda, "2026-10-23", "2026-10-23")["occurrences"]) == 1
    assert get(agenda, "2026-10-24", "2026-10-24")["occurrences"] == []


def test_available_rule_and_fixed_busy_keep_one_shared_budget_across_split_intervals(agenda):
    payload = body(rules=[rule(details=details("available", start_time="16:00", end_time="19:00", max_minutes=90)),
        rule(id=str(UUID(int=81004)), details=details(start_time="17:00", end_time="18:00"))])
    post(agenda, payload)
    row = next(w for w in get(agenda)["opportunities"] if w["source_date"] == "2026-10-23")
    assert row["usable_minutes"] == 90 and row["max_minutes"] == 90
    assert len(row["intervals"]) == 2
    assert not get(agenda)["opportunities_are_required"]


def test_flexible_busy_does_not_erase_declared_opportunity(agenda):
    payload = body(rules=[rule(details=details("available", max_minutes=60)),
        rule(id=str(UUID(int=81005)), details=details(firmness="flexible"))])
    post(agenda, payload)
    assert all(w["usable_minutes"] == 60 for w in get(agenda)["opportunities"])


def test_existing_availability_is_retained_and_explicit_unavailable_day_wins(agenda):
    source = calendar(first="2026-10-23", length=2)
    source["data"]["days"][1].update(status="unavailable", windows=[], max_total_minutes=None)
    assert agenda.client.post("/api/v1/planning/athlete/availability", json=source).status_code == 201
    payload = body(rules=[rule(start_date="2026-10-24", end_date="2026-10-24", repeat="once", weekdays=[], details=details("available"))])
    post(agenda, payload)
    context = get(agenda)
    assert context["availability"]["artifact"]["proposal"] == source
    assert next(w for w in context["opportunities"] if w["source_date"] == "2026-10-24")["usable_minutes"] == 0


def test_timezone_change_marks_opportunities_unknown_instead_of_moving_rules_silently(agenda):
    from app.models.entities import User
    post(agenda, body(rules=[rule(details=details("available"))]))
    with Session(agenda.engine) as db:
        db.execute(update(User).where(User.id == UUID(ATHLETE)).values(timezone="UTC")); db.commit()
    result = get(agenda)
    assert result["timezone_review_required"]
    assert all(not w["known"] and w["usable_minutes"] is None for w in result["opportunities"])


@pytest.mark.parametrize("changes", [
    {"weekdays": []}, {"weekdays": [2, 0]}, {"weekdays": [0, 0]},
    {"start_date": "2026-02-30"}, {"end_date": "2026-01-01"},
])
def test_invalid_repeat_or_dates_are_rejected_without_writes(agenda, changes):
    post(agenda, body(rules=[rule(**changes)]), 409)
    assert count(agenda, PlanningAuditArtifactRow) == 0


@pytest.mark.parametrize("changes", [
    {"start_fold": True}, {"max_minutes": True}, {"category": "training"},
    {"start_time": "25:00"}, {"end_time": "16:00"}, {"title": " "},
])
def test_malformed_details_are_closed_input(agenda, changes):
    post(agenda, body(rules=[rule(details=details(**changes))]), 422)


def test_duplicate_rules_and_orphan_exceptions_are_rejected(agenda):
    post(agenda, body(rules=[rule(), rule()]), 409)
    post(agenda, body(exceptions=[{"rule_id": str(UUID(int=1)), "date": "2026-10-21", "replacement": None}]), 404)
    post(agenda, body(exceptions=[{"rule_id": RULE, "date": "2026-10-20", "replacement": None}]), 404)


def test_preview_and_write_reject_stale_and_cross_owner_references(agenda):
    saved = post(agenda)["artifact"]
    stale = body(81102)
    post(agenda, stale, 409, preview=True)
    foreign = {**service.reference(saved), "artifact_id": service.identity(str(UUID(int=999)), str(UUID(int=81101)))}
    post(agenda, body(81103, foreign), 409)


@pytest.mark.parametrize("start,end", [("2026-02-30", "2026-03-01"), ("2026-10-23", "2026-10-22"), ("2025-01-01", "2026-10-23")])
def test_invalid_query_range_is_bounded(agenda, start, end):
    get(agenda, start, end, 409)


def test_tampered_storage_is_not_projected(agenda):
    saved = post(agenda)["artifact"]
    with Session(agenda.engine) as db:
        db.execute(update(PlanningAuditArtifactRow).where(PlanningAuditArtifactRow.artifact_id == saved["artifact_id"]).values(content_hash="0" * 64)); db.commit()
    get(agenda, expected=503)


def test_lost_commit_reply_recovers_exact_receipt(agenda, monkeypatch):
    original = service.setup.commit
    async def lost(session):
        await original(session)
        raise RuntimeError("synthetic lost reply")
    monkeypatch.setattr(service.setup, "commit", lost)
    post(agenda, expected=503)
    monkeypatch.setattr(service.setup, "commit", original)
    assert post(agenda, expected=200)["reused"]
    assert count(agenda, PlanningAuditArtifactRow) == 1


def test_dense_projection_is_rejected_without_silent_truncation(agenda, monkeypatch):
    post(agenda)
    monkeypatch.setattr(domain, "MAX_OCCURRENCES", 1)
    assert get(agenda, expected=409)["detail"]["code"] == "CALENDAR_CONSTRAINT_RANGE_TOO_DENSE"


def test_dst_gap_is_a_visible_weekly_issue_and_not_free_time():
    data = body(rules=[rule(start_date="2026-03-01", weekdays=[6], details=details(start_time="02:30", end_time="04:00")),
        rule(id=str(UUID(int=81006)), start_date="2026-03-01", weekdays=[6],
            details=details("available", start_time="01:00", end_time="05:00", max_minutes=60))])["data"]
    rows = domain.expand(data, "2026-03-29", "2026-03-29", "Europe/Budapest")
    assert any(r["issue"] == "ATHLETE_TIME_DOES_NOT_EXIST" and r["start_at"] is None for r in rows)
    groups = domain.opportunities(None, rows, "2026-03-29", "2026-03-29", "Europe/Budapest")
    assert groups[0]["known"] is False and groups[0]["usable_minutes"] is None


def test_dst_repeated_hour_requires_a_fold_and_retains_real_elapsed_time():
    data = body(rules=[rule(start_date="2026-10-25", end_date="2026-10-25", repeat="once", weekdays=[],
        details=details(start_time="02:30", end_time="02:15", start_fold=0, end_fold=1))])["data"]
    ScheduleInput.model_validate({**body(), "data": data})
    row = domain.expand(data, "2026-10-25", "2026-10-25", "Europe/Budapest")[0]
    assert row["elapsed_minutes"] == 45


def test_duplicate_exception_and_unknown_zone_do_not_pass_validation(agenda):
    item = {"rule_id": RULE, "date": "2026-10-21", "replacement": None}
    post(agenda, body(exceptions=[item, deepcopy(item)]), 409)
    payload = body(); payload["data"]["timezone_name"] = "Not/AZone"
    post(agenda, payload, 422)


def test_legacy_availability_candidate_preview_is_exact_and_read_only(agenda):
    candidate = calendar(first="2026-10-23", length=2)
    result = agenda.client.post(BASE + "/preview", json={"proposal": body(rules=[]),
        "availability_proposal": candidate, "start_date": "2026-10-23", "end_date": "2026-10-24"})
    assert result.status_code == 200, result.text
    value = result.json()
    assert value["availability_proposal_hash"] == service.digest(candidate)
    assert value["availability"] is None
    assert value["opportunities"] and any(c["plan_id"] == UNLINKED and c["code"] == "OUTSIDE_OPPORTUNITY" for c in value["conflicts"])
    assert count(agenda, PlanningAuditArtifactRow) == 0


def test_stale_legacy_candidate_is_rejected_without_losing_saved_availability(agenda):
    candidate = calendar(first="2026-10-23", length=2)
    saved = agenda.client.post("/api/v1/planning/athlete/availability", json=candidate)
    assert saved.status_code == 201
    result = agenda.client.post(BASE + "/preview", json={"proposal": body(rules=[]),
        "availability_proposal": candidate, "start_date": "2026-10-23", "end_date": "2026-10-24"})
    assert result.status_code == 409
    assert result.json()["detail"]["code"] == "CALENDAR_CONSTRAINT_AVAILABILITY_CHANGED"
    assert count(agenda, PlanningAuditArtifactRow) == 1


@pytest.mark.parametrize("duration,expected", [(1200, "OUTSIDE_OPPORTUNITY"), (0, None), (None, "OPPORTUNITY_FIT_UNKNOWN")])
def test_individual_fit_keeps_budget_zero_and_unknown_distinct(agenda, duration, expected):
    with Session(agenda.engine) as db:
        db.execute(update(PlannedWorkout).where(PlannedWorkout.id == UUID(UNLINKED)).values(duration_sec=duration)); db.commit()
    proposal = body(rules=[rule(details=details("available", start_time="17:00", end_time="19:00", max_minutes=10))])
    value = post(agenda, proposal, 200, preview=True)
    impacts = [c for c in value["conflicts"] if c["plan_id"] == UNLINKED]
    assert [c["code"] for c in impacts] == ([expected] if expected else [])


def test_explicit_unavailable_day_is_a_conflict_and_unknown_other_day_is_not(agenda):
    candidate = calendar(first="2026-10-23", length=2)
    candidate["data"]["days"][0].update(status="unavailable", windows=[], max_total_minutes=None)
    assert agenda.client.post("/api/v1/planning/athlete/availability", json=candidate).status_code == 201
    assert any(c["plan_id"] == UNLINKED and c["code"] == "TRAINING_DAY_UNAVAILABLE" for c in get(agenda)["conflicts"])
    assert get(agenda, "2026-10-24", "2026-10-24")["conflicts"] == []


def test_known_oneoff_dst_gap_cannot_be_saved(agenda):
    payload = body(rules=[rule(start_date="2026-03-29", end_date="2026-03-29", repeat="once", weekdays=[],
        details=details(start_time="02:30", end_time="04:00"))])
    assert post(agenda, payload, 409)["detail"]["code"] == "ATHLETE_TIME_DOES_NOT_EXIST"
    assert count(agenda, PlanningAuditArtifactRow) == 0
