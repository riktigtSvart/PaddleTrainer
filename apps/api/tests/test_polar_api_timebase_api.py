"""HTTP routing and scope tests for the read-only API clock audit."""

from copy import deepcopy
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import polar_tcx as module
from app.integrations.polar.client import PolarAPIError
from app.services.api_hr_timebase_audit import verify_api_hr_timebase_audit

URL = "/api/v1/integrations/polar/sessions/synthetic-session/hr-timebase/api-audit"


@pytest.fixture
def environment(monkeypatch):
    db = SimpleNamespace(scalar=AsyncMock(return_value=SimpleNamespace(scopes=["training_sessions:read"])))
    session = {"identifier": {"id": "synthetic-session"}, "timezoneOffsetMinutes": 120,
               "exercises": [{"identifier": {"id": "synthetic-exercise"},
                              "startTime": "2026-07-03T14:49:54", "stopTime": "2026-07-03T14:50:04",
                              "durationMillis": 10000, "pauseTimes": [],
                              "samples": {"samples": [
                                  {"type": "HEART_RATE", "intervalMillis": 1000, "values": [120, 121, 122]},
                                  {"type": "SPEED", "intervalMillis": 1000, "values": [8, 9, 10]}]},
                              "routes": {"route": {"startTime": "2026-07-03T14:49:54.580",
                                                   "wayPoints": [{"elapsedMillis": 3100}, {"elapsedMillis": 4100}, {"elapsedMillis": 5100}]}}}]}
    provider = AsyncMock(return_value={"trainingSessions": [session]})
    token = AsyncMock(return_value="synthetic-private-token")
    monkeypatch.setattr(module, "get_or_create_demo_user", AsyncMock(return_value=SimpleNamespace(id="synthetic-owner")))
    monkeypatch.setattr(module, "get_valid_access_token", token)
    monkeypatch.setattr(module, "PolarClient", lambda: SimpleNamespace(list_training_sessions=provider))
    app = FastAPI()
    app.include_router(module.router, prefix="/api/v1")
    app.dependency_overrides[module.get_db] = lambda: db
    with TestClient(app) as client:
        yield SimpleNamespace(client=client, provider=provider, token=token, db=db, session=session)


def get(env, **params):
    return env.client.get(URL, params={"sample_date": "2026-07-03", **params})


def test_audit_requests_samples_routes_and_pause_times_once(environment):
    response = get(environment)
    assert response.status_code == 200
    data = response.json()
    environment.provider.assert_awaited_once_with(
        "synthetic-private-token", date(2026, 7, 3), date(2026, 7, 4),
        features=["samples", "routes", "pause-times"])
    assert data["audit"]["status"] == "API_TIMEBASE_AUDITED_WITH_LIMITATIONS"
    assert data["audit"]["api_native_time_origin_verified"] is False
    assert data["audit"]["export_timebase_verified"] is False
    assert data["raw_session"] is None
    assert data["science_storage_writes"] == 0
    assert "synthetic-private-token" not in response.text


def test_explicit_payload_can_be_independently_reconstructed(environment):
    data = get(environment, include_payload="true").json()
    assert data["raw_session"] == environment.session
    assert verify_api_hr_timebase_audit(
        data["audit"], data["raw_session"], data["raw_session"],
        expected_session_external_id="synthetic-session", sample_session_match_count=1,
        route_session_match_count=1, requested_features=["samples", "routes", "pause-times"])


@pytest.mark.parametrize("count", [0, 2])
def test_no_or_duplicate_target_session_is_withheld(environment, count):
    environment.provider.return_value = {"trainingSessions": [environment.session] * count}
    data = get(environment, include_payload="true").json()
    assert data["audit"]["status"] == "WITHHELD"
    assert data["raw_session"] is None


def test_extra_sessions_do_not_change_id_bound_selection(environment):
    another = deepcopy(environment.session)
    another["identifier"]["id"] = "other"
    environment.provider.return_value = {"trainingSessions": [another, environment.session]}
    data = get(environment, include_payload="true").json()
    assert data["provider_session_match_count"] == 1
    assert data["raw_session"] == environment.session


def test_exercise_selector_is_forwarded(environment):
    assert get(environment, exercise_external_id="another").json()["audit"]["status"] == "WITHHELD"


@pytest.mark.parametrize("scopes,status", [(None, 404), ([], 403)])
def test_existing_polar_connection_and_scope_are_required(environment, scopes, status):
    environment.db.scalar.return_value = None if scopes is None else SimpleNamespace(scopes=scopes)
    assert get(environment).status_code == status
    environment.provider.assert_not_awaited()
    environment.token.assert_not_awaited()


def test_bad_provider_shape_is_controlled_gateway_error(environment):
    environment.provider.return_value = {"trainingSessions": None}
    assert get(environment).status_code == 502


def test_upstream_failure_does_not_export_details(environment):
    environment.provider.side_effect = PolarAPIError("private token details")
    response = get(environment)
    assert response.status_code == 502
    assert "private token details" not in response.text


def test_required_and_terminal_query_dates_fail_before_upstream(environment):
    assert environment.client.get(URL).status_code == 422
    assert get(environment, sample_date="9999-12-31").status_code == 422
    environment.provider.assert_not_awaited()


def test_new_endpoint_does_not_accept_evidence_write(environment):
    assert environment.client.post(URL, params={"sample_date": "2026-07-03"}).status_code == 405
    environment.provider.assert_not_awaited()
