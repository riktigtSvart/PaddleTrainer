"""Real HTTP/repositories/importers; disposable DB and synthetic Polar transport."""

import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.api.routes import data_connections as api
from app.core.security import encrypt_secret
from app.db.base import Base
from app.integrations.polar.client import PolarAPIError, PolarClient
from app.models.entities import ExternalConnection, PlannedWorkout, ProviderDataRecord, WorkoutSession
from app.planning.domain.persistence.audit import AuditArtifactKind as Kind
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow, PlanningLogicalPlanRow, PlanningPlanRevisionRow
from app.services import data_connections as service
from tests.planning.test_p2_4a2_planning_utility_storage import AsyncSQLiteBridge
from tests.planning.test_p2_4c3_goal_workflow_api import ATHLETE, OTHER, count
from tests.planning.test_p2_4c6_calendar_workspace import agenda as agenda_fixture

BASE = "/api/v1/data-connections"


@pytest.fixture
def connections(tmp_path, monkeypatch):
    wrapper = agenda_fixture.__wrapped__(tmp_path, monkeypatch)
    env = next(wrapper)
    Base.metadata.create_all(env.engine, tables=[PlanningLogicalPlanRow.__table__, PlanningPlanRevisionRow.__table__])
    env.app.include_router(api.router, prefix="/api/v1")
    monkeypatch.setattr(api, "configured", lambda: True)
    monkeypatch.setattr(service, "_now", env.clock.tick)

    async def scalar(self, query):
        return self.session.scalar(query)

    async def scalars(self, query):
        return self.session.scalars(query)

    async def remove(self, row):
        self.session.delete(row)

    monkeypatch.setattr(AsyncSQLiteBridge, "scalar", scalar, raising=False)
    monkeypatch.setattr(AsyncSQLiteBridge, "scalars", scalars, raising=False)
    monkeypatch.setattr(AsyncSQLiteBridge, "delete", remove, raising=False)
    with Session(env.engine) as session:
        session.add(ExternalConnection(user_id=UUID(ATHLETE), provider="POLAR",
            access_token_encrypted=encrypt_secret("synthetic-access-token"),
            refresh_token_encrypted=encrypt_secret("synthetic-refresh-token"),
            expires_at=datetime(2099, 1, 1, tzinfo=UTC),
            scopes=["training_sessions:read", "training_targets:read", "sports:read"]))
        session.commit()
    env.provider_calls, env.failures = [], {}
    env.session_payload = {"trainingSessions": [{"identifier": {"id": "new-session"},
        "startTime": "2026-10-22T07:00:00Z", "stopTime": "2026-10-22T08:00:00Z",
        "name": "Actual imported", "sport": {"id": "95"}, "durationMillis": 3600000,
        "calories": 0, "hrAvg": 140, "unknownProviderField": {"retained": True}}]}
    env.target_payload = [{"session": {"id": "new-target", "name": "Target imported", "done": False,
        "startTime": {"year": 2026, "month": 10, "day": 22, "hour": 18}},
        "exercise": [{"sportId": "95", "duration": 2700000, "phaseOrRepeat": []}]}]

    async def sports(self, token):
        env.provider_calls.append(("sports", None, None))
        return [{"id": "95", "name": "WATERSPORTS_KAYAKING"}]

    async def sessions(self, token, first, last, features=None):
        env.provider_calls.append(("sessions", first.isoformat(), last.isoformat()))
        assert features is None  # The quick calendar sync does not silently request sample histories.
        if "sessions" in env.failures:
            raise env.failures["sessions"]
        return deepcopy(env.session_payload)

    async def targets(self, token, first, last, **options):
        env.provider_calls.append(("targets", first.isoformat(), last.isoformat()))
        if "targets" in env.failures:
            raise env.failures["targets"]
        return deepcopy(env.target_payload)

    monkeypatch.setattr(PolarClient, "list_sports", sports)
    monkeypatch.setattr(PolarClient, "list_training_sessions", sessions)
    monkeypatch.setattr(PolarClient, "list_training_targets", targets)
    try:
        yield env
    finally:
        wrapper.close()


def proposal(token=770001, **changes):
    return {"request_id": str(UUID(int=token)), "provider": "POLAR", "datasets": ["sessions", "targets"], "past_days": 35, "future_days": 30, **changes}


def post(env, body=None, status=201):
    r = env.client.post(BASE + "/sync", json=body or proposal())
    assert r.status_code == status, r.text
    assert r.headers["Cache-Control"] == "no-store"
    return r.json()


def get(env, suffix="status", status=200):
    r = env.client.get(BASE + "/" + suffix)
    assert r.status_code == status, r.text
    assert r.headers["Cache-Control"] == "no-store"
    return r.json()


def test_opening_status_is_local_read_only_and_retains_unknown_freshness(connections):
    data = get(connections)
    polar = data["providers"][0]
    assert polar["connection_state"] == "connected" and polar["last_success_at"] is None
    assert polar["latest_session_at"] is not None
    assert polar["last_run"] is None and polar["allowed_datasets"] == ["sessions", "targets", "session_details"]
    assert all(not p["implemented"] and not p["manual_sync_supported"] for p in data["providers"][1:])
    assert connections.provider_calls == [] and count(connections, PlanningAuditArtifactRow) == 0
    assert "token" not in str(data).lower() and "scopes" not in str(data)


def test_real_imports_reach_calendar_with_durable_completion_and_frozen_today_window(connections):
    result = post(connections)
    assert result["committed"] and result["run"]["state"] == "succeeded"
    assert result["result"]["start_reference"] == service.reference(result["start"])
    assert result["run"]["datasets"][0]["imported"] == 1
    assert result["run"]["datasets"][1]["imported"] == 1
    assert connections.provider_calls[1] == ("sessions", "2026-09-18", "2026-10-23")
    assert connections.provider_calls[2] == ("targets", "2026-09-18", "2026-11-22")
    feed = connections.client.get("/api/v1/planning/calendar/feed?start_date=2026-10-22&end_date=2026-10-22").json()
    assert any(s["external_id"] == "new-session" and s["calories"] == 0 for s in feed["sessions"])
    assert any(p["title"] == "Target imported" for p in feed["planned"])
    assert count(connections, ProviderDataRecord) == 2
    assert get(connections)["providers"][0]["last_success_at"] == result["result"]["created_at"]


def test_retry_never_repeats_provider_work_or_activates_a_new_request(connections):
    first = post(connections)
    calls = len(connections.provider_calls)
    connections.clock.current += timedelta(days=1)
    replay = post(connections, status=200)
    assert replay["reused"] and replay["start"] == first["start"] and replay["result"] == first["result"]
    assert len(connections.provider_calls) == calls
    assert count(connections, PlanningAuditArtifactRow) == 2
    post(connections, proposal(past_days=7), 409)
    post(connections, proposal(provider="GARMIN"), 409)
    assert len(connections.provider_calls) == calls


def test_identical_provider_payloads_keep_one_session_and_content_addressed_archives(connections):
    post(connections)
    post(connections, proposal(token=770002))
    with Session(connections.engine) as session:
        rows = session.scalars(select(WorkoutSession).where(WorkoutSession.external_id == "new-session")).all()
        assert len(rows) == 1 and rows[0].raw_data["unknownProviderField"] == {"retained": True}
    # One extra previous-target snapshot, not another copy of the two responses.
    assert count(connections, ProviderDataRecord) == 3


def test_partial_import_preserves_successful_data_and_previous_success_time(connections):
    first = post(connections)
    connections.failures["targets"] = PolarAPIError("secret response body must not escape", status_code=403)
    partial = post(connections, proposal(token=770002))
    assert partial["run"]["state"] == "partial"
    assert partial["run"]["datasets"][1]["error_code"] == "DATA_SYNC_PERMISSION_MISSING"
    assert "secret response body" not in str(partial)
    assert get(connections)["providers"][0]["last_success_at"] == first["result"]["created_at"]


@pytest.mark.parametrize("upstream,expected", [(401, "DATA_SYNC_RECONNECT_REQUIRED"), (429, "DATA_SYNC_RATE_LIMITED"), (500, "DATA_SYNC_PROVIDER_HTTP_500")])
def test_provider_errors_are_sanitized_and_not_success(connections, upstream, expected):
    connections.failures["sessions"] = PolarAPIError("Bearer do-not-return", status_code=upstream)
    value = post(connections, proposal(datasets=["sessions"]))
    assert value["run"]["state"] == "failed" and value["run"]["error_code"] == expected
    assert value["run"]["datasets"][0]["imported"] is None
    assert "Bearer" not in str(value)
    assert get(connections)["providers"][0]["last_success_at"] is None


def test_empty_success_and_explicit_zero_are_valid_without_fabricating_activity(connections):
    before = count(connections, WorkoutSession)
    connections.session_payload = {"trainingSessions": []}
    connections.target_payload = []
    value = post(connections)
    assert value["run"]["state"] == "succeeded"
    assert all(d["imported"] == d["updated"] == d["skipped"] == 0 for d in value["run"]["datasets"])
    assert count(connections, WorkoutSession) == before


def test_reading_another_owner_cannot_expose_request_or_latest_session(connections):
    post(connections)
    with Session(connections.engine) as session:
        session.execute(update(WorkoutSession).where(WorkoutSession.user_id == UUID(OTHER)).values(started_at=datetime(2020, 1, 1, tzinfo=UTC)))
        session.commit()
    connections.email = "goal-api-other@example.invalid"
    result = get(connections)
    assert result["athlete_id"] == OTHER
    assert result["providers"][0]["last_run"] is None and result["providers"][0]["latest_session_at"].startswith("2020-01-01")
    get(connections, "runs/" + proposal()["request_id"], 404)
    post(connections, proposal(token=770002), 409)


@pytest.mark.parametrize("changes", [{"datasets": []}, {"datasets": ["sessions", "sessions"]}, {"datasets": ["unknown"]}, {"past_days": 90}, {"past_days": True}, {"future_days": -1}, {"provider": "OTHER"}, {"request_id": "bad"}, {"arbitrary_url": "http://elsewhere.invalid"}])
def test_invalid_requests_are_rejected_before_provider_or_audit_access(connections, changes):
    post(connections, proposal(**changes), 422)
    assert connections.provider_calls == [] and count(connections, PlanningAuditArtifactRow) == 0


@pytest.mark.parametrize("provider", ["GARMIN", "SUUNTO"])
def test_unimplemented_providers_have_no_fake_sync(connections, provider):
    post(connections, proposal(provider=provider), 409)
    assert connections.provider_calls == [] and count(connections, PlanningAuditArtifactRow) == 0


def test_scope_and_connection_requirements_are_checked_before_reservation(connections):
    with Session(connections.engine) as session:
        connection = session.scalar(select(ExternalConnection))
        connection.scopes = ["training_sessions:read", "sports:read"]
        session.commit()
    post(connections, status=409)
    polar = get(connections)["providers"][0]
    assert polar["allowed_datasets"] == ["sessions", "session_details"]
    post(connections, proposal(datasets=["sessions"]))


def test_active_reservation_blocks_new_jobs_and_expired_retry_does_not_repeat(connections):
    body = proposal()
    with Session(connections.engine, expire_on_commit=False) as session:
        assert asyncio.run(service.reserve(AsyncSQLiteBridge(session), ATHLETE, body, configured=True))
    post(connections, status=202)
    post(connections, proposal(token=770002), 409)
    assert connections.provider_calls == []
    connections.clock.current += timedelta(seconds=service.LEASE_SECONDS + 1)
    value = get(connections, "runs/" + body["request_id"])
    assert value["run"]["state"] == "interrupted"
    post(connections, status=200)
    assert connections.provider_calls == []
    post(connections, proposal(token=770002))


def test_completed_run_can_be_found_after_a_lost_http_reply(connections, monkeypatch):
    original = service.finish

    async def lose_reply(*args):
        await original(*args)
        raise RuntimeError("synthetic lost reply after commit")

    monkeypatch.setattr(service, "finish", lose_reply)
    post(connections, status=503)
    value = get(connections, "runs/" + proposal()["request_id"])
    assert value["run"]["state"] == "succeeded"
    calls = len(connections.provider_calls)
    post(connections, status=200)
    assert len(connections.provider_calls) == calls


def test_tampered_run_history_is_rejected_instead_of_displayed(connections):
    post(connections)
    with Session(connections.engine) as session:
        session.execute(update(PlanningAuditArtifactRow).where(PlanningAuditArtifactRow.artifact_kind == Kind.DATA_SYNC_SUCCEEDED.value).values(content_hash="0" * 64))
        session.commit()
    get(connections, status=503)
    get(connections, "runs/" + proposal()["request_id"], 503)


def test_no_connection_and_missing_configuration_do_not_create_jobs(connections, monkeypatch):
    with Session(connections.engine) as session:
        session.execute(delete(ExternalConnection))
        session.commit()
    assert get(connections)["providers"][0]["connection_state"] == "not_connected"
    post(connections, status=409)
    monkeypatch.setattr(api, "configured", lambda: False)
    assert get(connections)["providers"][0]["connection_state"] == "configuration_required"
    post(connections, status=409)
    assert count(connections, PlanningAuditArtifactRow) == 0


def test_unknown_queries_and_bad_run_id_are_rejected(connections):
    get(connections, "status?unexpected=1", 422)
    get(connections, "runs/not-a-uuid", 422)


def test_protected_planning_owned_target_is_preserved_and_reported(connections):
    post(connections)
    with Session(connections.engine) as session:
        workout = session.scalar(select(PlannedWorkout).where(PlannedWorkout.polar_target_id == "new-target"))
        session.add(PlanningLogicalPlanRow(logical_plan_id="protected-plan", athlete_id=UUID(ATHLETE), source_workout_id=workout.id,
            current_revision_number=0, created_at=connections.clock.tick(), updated_at=connections.clock.tick()))
        session.commit()
    connections.target_payload[0]["session"]["name"] = "Attempted replacement"
    result = post(connections, proposal(token=770002))
    assert result["run"]["state"] == "partial" and result["run"]["datasets"][1]["skipped"] == 1
    assert result["run"]["datasets"][1]["skip_reasons"] == {"protected_plan": 1}
    assert result["run"]["error_code"] == "DATA_SYNC_PROTECTED_PLANS_SKIPPED"
    with Session(connections.engine) as session:
        assert session.scalar(select(PlannedWorkout.title).where(PlannedWorkout.polar_target_id == "new-target")) == "Target imported"


def test_today_zero_duration_is_preserved_and_malformed_response_is_not_empty_success(connections):
    connections.session_payload["trainingSessions"][0]["durationMillis"] = 0
    value = post(connections, proposal(datasets=["sessions"]))
    assert value["run"]["state"] == "succeeded"
    with Session(connections.engine) as session:
        assert session.scalar(select(WorkoutSession.duration_sec).where(WorkoutSession.external_id == "new-session")) == 0
    connections.session_payload = {"unexpected": []}
    value = post(connections, proposal(token=770002, datasets=["sessions"]))
    assert value["run"]["state"] == "failed"


def test_timeout_is_reported_and_never_claims_full_completion(connections, monkeypatch):
    original = service.import_dataset

    async def slow_target(session, user, dataset, window, report):
        if dataset == "targets":
            await asyncio.sleep(0.2)
        else:
            await original(session, user, dataset, window, report)

    monkeypatch.setattr(service, "import_dataset", slow_target)
    monkeypatch.setattr(service, "TIMEOUT_SECONDS", 0.05)
    value = post(connections)
    assert value["run"]["state"] == "partial"
    assert value["run"]["datasets"][1]["error_code"] == "DATA_SYNC_TIMEOUT"


def test_uncommitted_reservation_never_launches_a_provider_call(connections, monkeypatch):
    async def fail_commit(session):
        raise RuntimeError("synthetic commit failure")

    monkeypatch.setattr(service.transactions, "commit", fail_commit)
    post(connections, status=503)
    assert connections.provider_calls == [] and count(connections, PlanningAuditArtifactRow) == 0


def test_documented_target_envelope_imports_and_preserves_unmapped_fields(connections):
    connections.target_payload = {"trainingTarget": connections.target_payload, "unknownProviderField": {"preserved": True}}
    value = post(connections)
    assert value["run"]["state"] == "succeeded" and value["run"]["datasets"][1]["imported"] == 1
    with Session(connections.engine) as session:
        raw = session.scalar(select(ProviderDataRecord.raw_data).where(ProviderDataRecord.data_type == "DATA_SYNC_TARGETS"))
        assert raw == connections.target_payload


def test_target_http_query_and_default_envelope_unwrapping_follow_provider_contract(connections, monkeypatch):
    from datetime import date
    import httpx

    original_client = httpx.AsyncClient
    captured = []
    payload = {"trainingTarget": connections.target_payload, "unmapped": "retained"}

    def transport(request):
        captured.append(request)
        if "from" not in request.url.params:
            return httpx.Response(400, json={"errorMessage": (
                "Call to path training-target/calendar-targets with method GET failed "
                "due to an invalid request: Query parameter 'from' is required"
            )})
        assert request.url.path == "/v4/data/training-target/calendar-targets"
        assert list(request.url.params.multi_items()) == [
            ("from", "2026-10-01"), ("to", "2026-10-26"),
        ]
        assert request.headers["Authorization"] == "Bearer synthetic"
        return httpx.Response(200, json=payload)

    def client(**kwargs):
        return original_client(transport=httpx.MockTransport(transport), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client)
    # Exercise the real client method, rather than the fixture's synthetic dataset transport.
    from pathlib import Path
    import importlib.util
    specification = importlib.util.spec_from_file_location("polar_transport_under_test", Path(__file__).resolve().parents[2] / "app/integrations/polar/client.py")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    loaded = asyncio.run(module.PolarClient().list_training_targets("synthetic", date(2026, 10, 1), date(2026, 10, 26)))
    assert loaded == connections.target_payload
    raw = asyncio.run(module.PolarClient().list_training_targets("synthetic", date(2026, 10, 1), date(2026, 10, 26), raw_response=True))
    assert raw == payload
    assert len(captured) == 2
    assert all(dict(r.url.params) == {"from": "2026-10-01", "to": "2026-10-26"} for r in captured)


@pytest.mark.parametrize("upstream", [400, 404, 422, 500, 502, 503, 599])
def test_target_http_failure_is_durable_specific_and_keeps_imported_sessions(connections, upstream):
    private_message = "Bearer private-provider-response-must-stay-private"
    connections.failures["targets"] = PolarAPIError(private_message, status_code=upstream)
    result = post(connections)
    expected = f"DATA_SYNC_PROVIDER_HTTP_{upstream}"
    assert result["run"]["state"] == "partial"
    assert result["run"]["error_code"] == expected
    reports = result["run"]["datasets"]
    assert reports[0]["state"] == "succeeded" and reports[0]["imported"] == 1
    assert reports[1]["state"] == "failed" and reports[1]["error_code"] == expected
    assert reports[1]["imported"] is None and reports[1]["skipped"] is None
    assert private_message not in str(result)
    calls = list(connections.provider_calls)
    receipt = get(connections, "runs/" + proposal()["request_id"])
    assert receipt["result"] == result["result"]
    replay = post(connections, status=200)
    assert replay["result"] == result["result"]
    assert connections.provider_calls == calls
    state = get(connections)["providers"][0]
    assert state["last_run"]["datasets"][1]["error_code"] == expected
    assert state["last_success_at"] is None
    assert private_message not in str(state)
    with Session(connections.engine) as session:
        assert session.scalar(select(WorkoutSession).where(WorkoutSession.external_id == "new-session")) is not None
        assert session.scalar(select(PlannedWorkout).where(PlannedWorkout.polar_target_id == "new-target")) is None


@pytest.mark.parametrize("upstream", [None, "400", True, False, 399, 600, 200])
def test_unverified_http_status_is_not_presented_as_a_verified_provider_code(upstream):
    assert service.failure_code(
        PolarAPIError("private message", status_code=upstream)
    ) == "DATA_SYNC_PROVIDER_REJECTED"


def test_legacy_generic_failure_remains_readable_after_a_later_success(connections):
    connections.failures["targets"] = PolarAPIError("private message")
    original = post(connections)
    assert original["run"]["error_code"] == "DATA_SYNC_PROVIDER_REJECTED"
    connections.failures.clear()
    current = post(connections, proposal(token=770002))
    assert current["run"]["state"] == "succeeded"
    historical = get(connections, "runs/" + proposal()["request_id"])
    assert historical["result"] == original["result"]
    assert historical["result"]["content_hash"] == original["result"]["content_hash"]
    assert get(connections)["providers"][0]["last_success_at"] == current["result"]["created_at"]
