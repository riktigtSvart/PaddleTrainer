"""Real sync, link writes and calendar reads on disposable SQLite."""

import asyncio
from copy import deepcopy
from datetime import UTC, date, datetime
from uuid import UUID

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from sqlalchemy.sql.dml import Update

from app.models.entities import PlannedWorkout, Sport, WorkoutLinkSource, WorkoutSession, WorkoutStatus
from app.services import data_connections as service
from app.services.polar_matching import link_exact_polar_sessions_after_import
from tests.planning.test_p2_4a2_planning_utility_storage import AsyncSQLiteBridge
from tests.planning.test_p2_4c3_goal_workflow_api import ATHLETE, OTHER
from tests.planning.test_p2_4c7_data_connections import connections as connections
from tests.planning.test_p2_4c7_data_connections import get, post, proposal


def historical_pair(env, *, target="historical-target", owner=ATHLETE,
                    session_owner=None, session_provider="POLAR", existing=None, provenance=None):
    with Session(env.engine) as db:
        plan = PlannedWorkout(user_id=UUID(owner), date=date(2019, 1, 1),
            title="Historical Polar plan", sport=Sport.KAYAK, source="POLAR",
            status=WorkoutStatus.PLANNED, polar_target_id=target,
            raw_data={"sourcePreserved": True})
        db.add(plan)
        db.flush()
        actual = WorkoutSession(user_id=UUID(session_owner or owner),
            external_provider=session_provider, external_id="historical-" + target,
            sport=Sport.KAYAK, name="Historical actual", started_at=datetime(2019, 1, 1, 8, tzinfo=UTC),
            planned_workout_id=existing, planned_workout_link_source=provenance,
            raw_data={"trainingTarget": {"id": target}, "sourcePreserved": True})
        db.add(actual)
        db.commit()
        return plan.id, actual.id


def session_link(env, identity):
    with Session(env.engine) as db:
        row = db.get(WorkoutSession, identity)
        return row.planned_workout_id, row.planned_workout_link_source, deepcopy(row.raw_data)


def test_imported_exact_reference_links_after_target_import_and_reaches_calendar(connections):
    connections.session_payload["trainingSessions"][0]["trainingTarget"] = {"id": "new-target"}
    result = post(connections)
    assert result["run"]["state"] == "succeeded"
    reports = result["run"]["datasets"]
    assert "pairing" not in reports[0]
    assert reports[1]["pairing"]["linked"] == 1
    assert reports[1]["pairing"]["unmatched"] == 0
    with Session(connections.engine) as db:
        actual = db.scalar(select(WorkoutSession).where(WorkoutSession.external_id == "new-session"))
        plan = db.scalar(select(PlannedWorkout).where(PlannedWorkout.polar_target_id == "new-target"))
        assert actual.planned_workout_id == plan.id
        assert actual.planned_workout_link_source == WorkoutLinkSource.PROVIDER_EXACT
        assert plan.status == WorkoutStatus.PLANNED
        assert actual.raw_data["unknownProviderField"] == {"retained": True}
        plan_id = str(plan.id)
    feed = connections.client.get("/api/v1/planning/calendar/feed?start_date=2026-10-22&end_date=2026-10-22").json()
    assert next(x for x in feed["sessions"] if x["external_id"] == "new-session")["planned_workout_id"] == plan_id
    assert get(connections)["providers"][0]["last_success_at"] == result["result"]["created_at"]


def test_explicit_sync_backfills_historical_ids_without_a_new_target_request(connections):
    plan, actual = historical_pair(connections)
    get(connections)
    connections.client.get("/api/v1/planning/calendar/feed")
    assert session_link(connections, actual)[0] is None
    result = post(connections, proposal(datasets=["sessions"]))
    assert result["run"]["datasets"][0]["pairing"]["linked"] == 1
    linked, provenance, raw = session_link(connections, actual)
    assert (linked, provenance) == (plan, WorkoutLinkSource.PROVIDER_EXACT)
    assert raw == {"trainingTarget": {"id": "historical-target"}, "sourcePreserved": True}
    assert all(call[0] != "targets" for call in connections.provider_calls)
    with Session(connections.engine) as db:
        assert db.get(PlannedWorkout, plan).status == WorkoutStatus.PLANNED
        assert db.get(PlannedWorkout, plan).raw_data == {"sourcePreserved": True}


def test_target_only_sync_can_link_previously_stored_completion(connections):
    plan, actual = historical_pair(connections, target="new-target")
    result = post(connections, proposal(datasets=["targets"]))
    assert result["run"]["datasets"][0]["pairing"]["linked"] == 1
    assert session_link(connections, actual)[0] == plan


def test_replay_does_not_relink_and_old_receipt_stays_byte_identical(connections):
    plan, actual = historical_pair(connections)
    first = post(connections, proposal(datasets=["sessions"]))
    with Session(connections.engine) as db:
        db.execute(update(WorkoutSession).where(WorkoutSession.id == actual).values(
            planned_workout_id=None, planned_workout_link_source=None))
        db.commit()
    replay = post(connections, proposal(datasets=["sessions"]), status=200)
    assert replay["result"] == first["result"]
    assert session_link(connections, actual)[0] is None
    later = post(connections, proposal(token=770002, datasets=["sessions"]))
    assert later["run"]["datasets"][0]["pairing"]["linked"] == 1
    assert session_link(connections, actual)[0] == plan
    assert get(connections, "runs/" + proposal()["request_id"])["result"] == first["result"]


def test_existing_confirmed_link_retains_its_provenance(connections):
    plan, actual = historical_pair(connections)
    with Session(connections.engine) as db:
        db.execute(update(WorkoutSession).where(WorkoutSession.id == actual).values(
            planned_workout_id=plan, planned_workout_link_source=WorkoutLinkSource.MANUAL_CONFIRMED))
        db.commit()
    result = post(connections, proposal(datasets=["sessions"]))
    assert result["run"]["datasets"][0]["pairing"]["already_linked"] == 1
    assert session_link(connections, actual)[1] == WorkoutLinkSource.MANUAL_CONFIRMED


def test_conflicting_existing_link_is_preserved_and_reported_as_partial(connections):
    other_plan, _ = historical_pair(connections, target="other-target")
    _, actual = historical_pair(connections, existing=other_plan, provenance=WorkoutLinkSource.MANUAL_CONFIRMED)
    result = post(connections, proposal(datasets=["sessions"]))
    assert result["run"]["state"] == "partial"
    assert result["run"]["error_code"] == "DATA_SYNC_PAIRING_REVIEW_REQUIRED"
    assert result["run"]["datasets"][0]["pairing"]["conflicts"] == 1
    assert session_link(connections, actual)[:2] == (other_plan, WorkoutLinkSource.MANUAL_CONFIRMED)
    assert get(connections)["providers"][0]["last_success_at"] is None


def test_duplicate_owned_target_id_never_picks_an_arbitrary_plan(connections):
    _, actual = historical_pair(connections)
    with Session(connections.engine) as db:
        db.add(PlannedWorkout(user_id=UUID(ATHLETE), date=date(2019, 1, 1), title="Duplicate",
            sport=Sport.KAYAK, source="POLAR", polar_target_id="historical-target"))
        db.commit()
    result = post(connections, proposal(datasets=["sessions"]))
    assert result["run"]["datasets"][0]["pairing"]["ambiguous"] == 1
    assert result["run"]["state"] == "partial"
    assert session_link(connections, actual)[0] is None


def test_other_owner_plan_and_non_polar_completion_are_not_linked(connections):
    _, foreign_reference = historical_pair(connections, owner=OTHER, session_owner=ATHLETE)
    _, non_polar = historical_pair(connections, target="garmin", session_provider="GARMIN")
    post(connections, proposal(datasets=["sessions"]))
    assert session_link(connections, foreign_reference)[0] is None
    assert session_link(connections, non_polar)[0] is None


@pytest.mark.parametrize("raw", [None, [], {}, {"trainingTarget": []}, {"trainingTarget": {"id": True}},
                                 {"trainingTarget": {"id": " historical-target"}}, {"trainingTarget": {"id": 0}}])
def test_missing_or_malformed_reference_never_becomes_a_time_or_sport_guess(connections, raw):
    _, actual = historical_pair(connections)
    with Session(connections.engine) as db:
        db.execute(update(WorkoutSession).where(WorkoutSession.id == actual).values(raw_data=raw))
        db.commit()
    result = post(connections, proposal(datasets=["sessions"]))
    assert result["run"]["state"] == "succeeded"
    # The base calendar fixture, this historical row and the new import each lack a usable reference.
    assert result["run"]["datasets"][0]["pairing"]["missing_reference"] == 3
    assert session_link(connections, actual)[0] is None


def test_commit_time_assignment_is_not_overwritten(connections):
    other_plan, _ = historical_pair(connections, target="other-target")
    _, actual = historical_pair(connections)

    class RacingBridge(AsyncSQLiteBridge):
        async def scalars(self, query):
            return self.session.scalars(query)

        async def execute(self, query):
            if isinstance(query, Update):
                self.session.execute(update(WorkoutSession).where(WorkoutSession.id == actual).values(
                    planned_workout_id=other_plan, planned_workout_link_source=WorkoutLinkSource.MANUAL_CONFIRMED))
            return self.session.execute(query)

    with Session(connections.engine, expire_on_commit=False) as db:
        result = asyncio.run(link_exact_polar_sessions_after_import(RacingBridge(db), type("Owner", (), {"id": UUID(ATHLETE)})()))
    assert result["conflicts"] == 1
    assert session_link(connections, actual)[:2] == (other_plan, WorkoutLinkSource.MANUAL_CONFIRMED)


def test_skip_reasons_distinguish_incomplete_records_from_protected_plans(connections):
    valid = deepcopy(connections.target_payload[0])
    no_start = deepcopy(valid)
    no_start["session"].pop("startTime")
    connections.target_payload = [valid, no_start, {"session": {}}, {"session": []}]
    result = post(connections)
    target = result["run"]["datasets"][1]
    assert target["skipped"] == 3
    assert target["skip_reasons"] == {"missing_start": 1, "missing_target_id": 1, "invalid_record": 1}
    assert target["error_code"] == "DATA_SYNC_SOURCE_RECORDS_SKIPPED"
    assert result["run"]["state"] == "partial"


def test_pairing_failure_preserves_imports_and_never_claims_a_successful_run(connections, monkeypatch):
    async def fail_pairing(*args):
        raise RuntimeError("private diagnostic")

    monkeypatch.setattr(service, "link_exact_polar_sessions_after_import", fail_pairing)
    result = post(connections)
    assert result["run"]["state"] == "partial"
    assert result["run"]["error_code"] == "DATA_SYNC_PAIRING_FAILED"
    assert all(d["state"] == "succeeded" for d in result["run"]["datasets"])
    assert "pairing" not in result["run"]["datasets"][-1]
    assert "private diagnostic" not in str(result)
    assert get(connections)["providers"][0]["last_success_at"] is None


def test_timeout_during_pairing_never_records_full_completion(connections, monkeypatch):
    async def slow_pairing(*args):
        await asyncio.sleep(2)

    monkeypatch.setattr(service, "link_exact_polar_sessions_after_import", slow_pairing)
    monkeypatch.setattr(service, "TIMEOUT_SECONDS", 1)
    result = post(connections)
    assert result["run"]["state"] == "partial"
    assert result["run"]["error_code"] == "DATA_SYNC_TIMEOUT"


@pytest.mark.parametrize("details", [{"pairing": {"linked": -1}}, {"skip_reasons": {"protected_plan": True}, "skipped": 1},
                                     {"skip_reasons": {"missing_start": 2}, "skipped": 1}])
def test_invalid_additional_run_details_are_rejected(details):
    with pytest.raises(service.SyncRuleError):
        service.validate_details(details, "DATA_SYNC_STORAGE_INVALID")
