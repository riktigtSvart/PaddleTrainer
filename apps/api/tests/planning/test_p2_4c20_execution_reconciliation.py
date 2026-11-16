"""Owned HTTP reviews reconcile durable imports without rewriting source workouts."""

import asyncio
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes import data_connections as sync_api
from app.core.security import encrypt_secret
from app.models.entities import (
    ExternalConnection,
    PlannedWorkout,
    Sport,
    WorkoutSession,
    WorkoutStatus,
)
from app.planning.domain.persistence.audit import AuditArtifactKind as Kind
from app.planning.infrastructure.repositories.postgres_planning_audit import (
    SqlAlchemyPlanningAuditRepository,
)
from app.schemas.data_connections import DataSyncInput
from app.services import data_connections as sync_service
from app.services import training_execution_reconciliation as execution
from app.services import training_plans
from tests.planning.test_p2_4a2_planning_utility_storage import AsyncSQLiteBridge
from tests.planning.test_p2_4c3_goal_workflow_api import ATHLETE, OTHER, count
from tests.planning.test_p2_4c18_4_training_plan import accept, add_session, owned_plans, review
from tests.planning.test_p2_4c18_4_training_plan import planner as planner_fixture


@pytest.fixture
def planner(tmp_path, monkeypatch):
    yield from planner_fixture.__wrapped__(tmp_path, monkeypatch)


def old_plan(env, token=200001, **changes):
    values = {"id": UUID(int=token), "user_id": UUID(ATHLETE), "date": date(2026, 10, 22),
              "planned_start_time": datetime(2026, 10, 22, 6, tzinfo=UTC),
              "duration_sec": 1800, "sport": Sport.KAYAK, "title": "Lejárt kajak",
              "source": "POLAR", "polar_target_id": f"target-{token}",
              "created_at": datetime(2026, 10, 20, tzinfo=UTC),
              "raw_data": {"source": "unchanged"}}
    values.update(changes)
    with Session(env.engine) as db:
        db.add(PlannedWorkout(**values))
        db.commit()
    return str(values["id"])


def sync_receipt(env, token=200101, *, owner=ATHLETE, started=None, first="2026-10-01",
                 last="2026-10-25", datasets=None, reports=None, zone="Europe/Budapest"):
    started = started or env.clock.current - timedelta(minutes=30)
    proposal = DataSyncInput.model_validate({"request_id": str(UUID(int=token)), "provider": "POLAR",
                                            "datasets": datasets or ["sessions", "targets"]}).model_dump(mode="json")
    start = {"schema_version": sync_service.RUN_SCHEMA, "artifact_id": sync_service.identity(owner, proposal),
             "athlete_id": owner, "proposal": proposal, "request_hash": sync_service.digest(proposal),
             "stage": "started", "created_at": started.isoformat(),
             "deadline_at": (started + timedelta(seconds=240)).isoformat(),
             "window": {"from_date": first, "sessions_to_exclusive": last,
                        "targets_to_exclusive": "2026-11-24", "timezone_name": zone},
             "planning_authorized": False}
    reports = reports or [{"dataset": dataset, "state": "succeeded", "imported": 0,
                           "updated": 0, "skipped": 0, "error_code": None} for dataset in proposal["datasets"]]

    async def write():
        with Session(env.engine) as db:
            bridge = AsyncSQLiteBridge(db)
            repository = SqlAlchemyPlanningAuditRepository(bridge)
            await sync_service.write(bridge, repository, owner, start, Kind.DATA_SYNC_STARTED)
            complete = all(r["state"] == "succeeded" and r["skipped"] == 0 and r["error_code"] is None for r in reports)
            end = {"schema_version": sync_service.RUN_SCHEMA, "artifact_id": start["artifact_id"],
                   "athlete_id": owner, "proposal": proposal, "request_hash": start["request_hash"],
                   "stage": "finished", "created_at": (started + timedelta(seconds=30)).isoformat(),
                   "start_reference": sync_service.reference(start), "outcome": "succeeded" if complete else "partial",
                   "datasets": reports, "error_code": None if complete else "DATA_SYNC_SOURCE_RECORDS_SKIPPED",
                   "may_have_saved_data": True, "planning_authorized": False}
            await sync_service.write(bridge, repository, owner, end, Kind.DATA_SYNC_SUCCEEDED if complete else Kind.DATA_SYNC_FAILED)
            return end
    return asyncio.run(write())


def event_for(value, plan_id):
    return next(item for item in value["result"]["events"] if item.get("workout_id") == plan_id)


def test_covered_empty_import_releases_recent_uncertainty_without_mutating_plan(planner):
    plan_id = old_plan(planner)
    before = review(planner)
    assert event_for(before, plan_id)["kind"] == "execution_unknown"
    assert before["result"]["days_without_proposal"][0]["reason"] == "RECENT_EXECUTION_REVIEW"
    source = sync_receipt(planner)
    after = review(planner)
    event = event_for(after, plan_id)
    assert event["kind"] == "not_recorded_after_sync" and not event["can_confirm_missed"]
    assert event["sync_reference"] == sync_service.reference(source)
    assert after["result"]["proposals"]
    with Session(planner.engine) as db:
        row = db.get(PlannedWorkout, UUID(plan_id))
        assert row.status == WorkoutStatus.PLANNED and row.raw_data == {"source": "unchanged"}
        assert db.scalar(select(WorkoutSession.id).where(WorkoutSession.user_id == UUID(ATHLETE))) is None


def test_missing_plan_duration_is_not_invented_or_kept_as_unknown_load_after_sync(planner):
    plan_id = old_plan(planner, duration_sec=None)
    sync_receipt(planner)
    value = review(planner)
    assert event_for(value, plan_id)["kind"] == "not_recorded_after_sync"
    assert plan_id not in value["result"]["preparation"]["unknown_duration_workout_ids"]
    assert value["result"]["proposals"]
    assert next(p for p in value["plan_snapshots"] if p["workout"]["id"] == plan_id)["workout"]["duration_sec"] is None


@pytest.mark.parametrize("problem", ["failed_sessions", "skipped_session", "targets_only", "before_plan_end",
                                     "outside_window", "foreign_owner", "future_receipt", "unknown_counts"])
def test_incomplete_uncovered_or_foreign_import_never_proves_absence(planner, problem):
    plan_id = old_plan(planner)
    options = {}
    reports = [{"dataset": "sessions", "state": "succeeded", "imported": 0, "updated": 0, "skipped": 0, "error_code": None}]
    if problem == "failed_sessions":
        reports[0].update(state="failed", error_code="DATA_SYNC_PROVIDER_NETWORK_UNAVAILABLE")
    elif problem == "skipped_session":
        reports[0].update(skipped=1, skip_reasons={"missing_start": 1})
    elif problem == "targets_only":
        options["datasets"] = ["targets"]
        reports[0]["dataset"] = "targets"
    elif problem == "before_plan_end":
        options["started"] = datetime(2026, 10, 22, 6, 29, 50, tzinfo=UTC)
    elif problem == "outside_window":
        options["first"] = "2026-10-23"
    elif problem == "foreign_owner":
        options["owner"] = OTHER
    elif problem == "future_receipt":
        options["started"] = planner.clock.current + timedelta(hours=1)
    elif problem == "unknown_counts":
        reports[0]["imported"] = None
    sync_receipt(planner, datasets=options.pop("datasets", ["sessions"]), reports=reports, **options)
    value = review(planner)
    assert event_for(value, plan_id)["kind"] == "execution_unknown"
    assert value["result"]["days_without_proposal"][0]["reason"] == "RECENT_EXECUTION_REVIEW"


def test_clean_sessions_are_usable_when_only_target_import_is_partial(planner):
    plan_id = old_plan(planner)
    sync_receipt(planner, reports=[
        {"dataset": "sessions", "state": "succeeded", "imported": 0, "updated": 0, "skipped": 0, "error_code": None},
        {"dataset": "targets", "state": "succeeded", "imported": 0, "updated": 0, "skipped": 4,
         "skip_reasons": {"protected_application_plan": 4}, "error_code": "DATA_SYNC_PROTECTED_PLANS_SKIPPED"},
    ])
    assert event_for(review(planner), plan_id)["kind"] == "not_recorded_after_sync"


def test_late_stored_completion_supersedes_absence_and_is_counted_once(planner):
    plan_id = old_plan(planner)
    sync_receipt(planner)
    assert event_for(review(planner), plan_id)["kind"] == "not_recorded_after_sync"
    add_session(planner, planned_workout_id=UUID(plan_id), started_at=datetime(2026, 10, 22, 6, tzinfo=UTC),
                ended_at=datetime(2026, 10, 22, 6, 30, tzinfo=UTC), duration_sec=1800)
    result = review(planner)
    events = [event for event in result["result"]["events"] if event.get("workout_id") == plan_id]
    assert len(events) == 1 and events[0]["kind"] == "planned_completed"


def test_exact_stored_provider_reference_is_resolved_without_name_or_time_guess(planner):
    plan_id = old_plan(planner)
    add_session(planner, external_provider="POLAR", raw_data={"trainingTarget": {"id": "target-200001"}})
    value = review(planner)
    assert event_for(value, plan_id)["kind"] == "planned_completed"
    assert value["result"]["execution_reconciliation"]["resolved_links"] == [{
        "session_id": str(UUID(int=180499)), "workout_id": plan_id, "basis": "provider_exact", "provider": "POLAR"}]
    with Session(planner.engine) as db:
        assert db.get(WorkoutSession, UUID(int=180499)).planned_workout_id is None


def test_duplicate_provider_target_is_not_arbitrarily_linked_or_marked_absent(planner):
    first = old_plan(planner)
    second = old_plan(planner, token=200002, polar_target_id="target-200001")
    add_session(planner, external_provider="POLAR", raw_data={"trainingTarget": {"id": "target-200001"}})
    sync_receipt(planner)
    value = review(planner)
    assert value["result"]["execution_reconciliation"]["resolved_links"] == []
    for plan_id in [first, second]:
        event = event_for(value, plan_id)
        assert event["kind"] == "execution_unknown"
        assert event["reconciliation_issue"] == "AMBIGUOUS_PROVIDER_TARGET"


def test_equivalent_successful_sync_reuses_original_review_and_provenance(planner):
    old_plan(planner)
    sync_receipt(planner)
    initial = review(planner)
    sync_receipt(planner, token=200102, started=planner.clock.current - timedelta(minutes=10))
    later = review(planner)
    assert later == initial


def test_existing_conflicting_link_is_preserved_and_only_affected_target_stays_unknown(planner):
    first = old_plan(planner)
    second = old_plan(planner, token=200002)
    add_session(planner, planned_workout_id=UUID(second), external_provider="POLAR",
                raw_data={"trainingTarget": {"id": "target-200001"}})
    sync_receipt(planner)
    value = review(planner)
    assert event_for(value, first)["reconciliation_issue"] == "AMBIGUOUS_PROVIDER_TARGET"
    assert event_for(value, first)["kind"] == "execution_unknown"
    assert event_for(value, second)["kind"] == "planned_completed"
    with Session(planner.engine) as db:
        assert db.get(WorkoutSession, UUID(int=180499)).planned_workout_id == UUID(second)


def test_incomplete_recorded_completion_never_becomes_an_assumed_miss(planner):
    plan_id = old_plan(planner)
    add_session(planner, planned_workout_id=UUID(plan_id), duration_sec=None, ended_at=None)
    sync_receipt(planner)
    value = review(planner)
    assert event_for(value, plan_id)["kind"] == "execution_incomplete"


def test_explicit_completed_skipped_and_cancelled_states_keep_their_meaning(planner):
    completed = old_plan(planner, status=WorkoutStatus.COMPLETED)
    skipped = old_plan(planner, token=200002, status=WorkoutStatus.SKIPPED)
    cancelled = old_plan(planner, token=200003, status=WorkoutStatus.CANCELLED)
    sync_receipt(planner)
    value = review(planner)
    assert event_for(value, completed)["kind"] == "reported_completed"
    assert event_for(value, skipped)["kind"] == "confirmed_missed"
    assert not any(event.get("workout_id") == cancelled for event in value["result"]["events"])


def test_new_absence_evidence_invalidates_previously_open_review_before_acceptance(planner):
    old_plan(planner)
    before = review(planner)
    sync_receipt(planner)
    assert accept(planner, before, expected=409)["detail"]["code"] == "TRAINING_PLAN_REVIEW_CHANGED"


def test_own_accepted_miss_does_not_create_an_automatic_replacement(planner):
    saved = accept(planner, review(planner))["artifact"]
    row = owned_plans(planner)[0]
    planner.clock.current = datetime(2026, 10, 24, 12, tzinfo=UTC)
    sync_receipt(planner)
    value = review(planner, first="2026-10-24", last="2026-10-30")
    assert event_for(value, str(row.id))["kind"] == "not_recorded_after_sync"
    assert not value["result"]["create"]
    assert set(saved["created_workouts"]) <= {str(p.id) for p in owned_plans(planner)}


@pytest.mark.asyncio
async def test_monitor_refreshes_a_blocked_review_before_first_acceptance(planner):
    # Prepare synchronous fixture evidence outside this async test's event loop.
    old_plan(planner)
    review(planner)
    before = count(planner, PlannedWorkout)
    with Session(planner.engine) as db:
        result = await training_plans.refresh_active(AsyncSQLiteBridge(db), ATHLETE)
    assert len(result) == 1 and result[0]["review"]["committed_plan"] is False
    assert count(planner, PlannedWorkout) == before


def test_dst_window_uses_real_utc_bounds_and_waits_for_the_whole_unknown_clock_day():
    workout = {"id": "plan", "date": "2026-10-25", "planned_start_time": None, "duration_sec": None}
    first, last = execution.planned_span(workout, "Europe/Budapest")
    assert (last.astimezone(UTC) - first.astimezone(UTC)).total_seconds() == 25 * 3600
    context = execution.empty(ATHLETE)
    context["sync_windows"] = [{"started_at": "2026-10-25T22:30:00+00:00",
                                "from_at": "2026-10-24T22:00:00+00:00", "to_exclusive_at": "2026-10-25T23:00:00+00:00"}]
    assert execution.absence_source(workout, "Europe/Budapest", context) is None
    context["sync_windows"][0]["started_at"] = "2026-10-25T23:30:00+00:00"
    assert execution.absence_source(workout, "Europe/Budapest", context)


def test_real_sync_receipt_and_monitor_unblock_review_without_first_acceptance(planner, monkeypatch):
    plan_id = old_plan(planner)
    before = review(planner)
    assert event_for(before, plan_id)["kind"] == "execution_unknown"
    planner.app.include_router(sync_api.router, prefix="/api/v1")
    monkeypatch.setattr(sync_api, "configured", lambda: True)
    monkeypatch.setattr(sync_service, "_now", planner.clock.tick)

    async def empty_import(session, user, dataset, window, report):
        assert user.id == UUID(ATHLETE) and dataset == "sessions"
        report.update(imported=0, updated=0, skipped=0, skip_reasons={})

    async def empty_pairing(session, user):
        return {"linked": 0, "already_linked": 0, "unmatched": 0, "missing_reference": 0, "conflicts": 0, "ambiguous": 0}

    monkeypatch.setattr(sync_service, "import_dataset", empty_import)
    monkeypatch.setattr(sync_service, "link_exact_polar_sessions_after_import", empty_pairing)
    ExternalConnection.__table__.create(planner.engine, checkfirst=True)
    with Session(planner.engine) as db:
        db.add(ExternalConnection(user_id=UUID(ATHLETE), provider="POLAR",
                                  access_token_encrypted=encrypt_secret("synthetic-token"),
                                  refresh_token_encrypted=encrypt_secret("synthetic-refresh"),
                                  expires_at=datetime(2099, 1, 1, tzinfo=UTC),
                                  scopes=["training_sessions:read", "sports:read"]))
        db.commit()
    response = planner.client.post("/api/v1/data-connections/sync", json={
        "request_id": str(UUID(int=200180)), "provider": "POLAR", "datasets": ["sessions"],
        "past_days": 35, "future_days": 0,
    })
    assert response.status_code == 201, response.text
    assert response.json()["run"]["state"] == "succeeded"
    count_before = count(planner, PlannedWorkout)

    async def refresh():
        with Session(planner.engine) as db:
            return await training_plans.refresh_active(AsyncSQLiteBridge(db), ATHLETE)

    after = asyncio.run(refresh())[0]["review"]
    assert event_for(after, plan_id)["kind"] == "not_recorded_after_sync"
    assert after["result"]["proposals"]
    assert asyncio.run(refresh())[0]["reused"] is True
    assert count(planner, PlannedWorkout) == count_before
