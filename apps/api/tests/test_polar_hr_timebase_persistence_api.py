from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from test_hr_timebase_snapshot import record
from test_polar_tcx_timebase_api import XML
from test_polar_tcx_timebase_api import environment as _environment_fixture

from app.api.router import api_router
from app.api.routes import polar_tcx as module
from app.services.hr_timebase_snapshot import build_hr_timebase_snapshot
from app.services.tcx_heart_rate_timebase import build_tcx_heart_rate_timebase

environment = _environment_fixture
BASE = "/api/v1/integrations/polar/sessions/api-session/hr-timebase"


def post(environment, *, content=XML, params=None, headers=None):
    return environment.client.post(
        BASE + "/persist-tcx",
        params={"sample_date": "2025-02-12", **(params or {})},
        content=content,
        headers={"content-type": "application/xml", **(headers or {})},
    )


def get(environment, **params):
    return environment.client.get(BASE + "/saved", params={"sample_date": "2025-02-12", **params})


def saved_records(environment):
    evidence = build_tcx_heart_rate_timebase(
        XML,
        environment.session,
        expected_session_external_id="api-session",
        sample_session_match_count=1,
    )
    return [
        record(
            build_hr_timebase_snapshot(
                evidence,
                environment.session,
                athlete_id="synthetic-athlete",
                session_external_id="api-session",
                sample_session_match_count=1,
            )
        )
    ]


def test_persist_uses_fresh_verification_and_current_connection_owner(environment, monkeypatch):
    saver = AsyncMock(return_value={"status": "CREATED", "round_trip_verified": True})
    monkeypatch.setattr(module, "persist_hr_timebase_snapshot", saver)
    response = post(environment)
    assert response.status_code == 200
    data = response.json()
    assert data["verification"]["export_timebase_verified"] is True
    assert data["persistence"]["status"] == "CREATED"
    args, kwargs = saver.await_args
    assert args[0] is environment.db
    assert args[1] == data["verification"]
    assert args[2] is environment.session
    assert kwargs == {
        "athlete_id": "synthetic-athlete",
        "session_external_id": "api-session",
        "sample_session_match_count": 1,
    }
    assert "synthetic-test-token" not in response.text


@pytest.mark.parametrize("failure", ["XML", "VALUES", "START", "DUPLICATE", "MISSING", "SELECTOR"])
def test_failed_export_or_ambiguous_source_never_calls_storage(environment, monkeypatch, failure):
    saver = AsyncMock(side_effect=AssertionError("invalid evidence must not be persisted"))
    monkeypatch.setattr(module, "persist_hr_timebase_snapshot", saver)
    content, params = XML, {}
    if failure == "XML":
        content = b"<broken"
    elif failure == "VALUES":
        environment.session["exercises"][0]["samples"]["samples"][0]["values"][0] = 119
    elif failure == "START":
        environment.session["exercises"][0]["startTime"] = "2025-02-12T10:00:01"
    elif failure in ("DUPLICATE", "MISSING"):
        environment.provider.return_value = {
            "trainingSessions": [environment.session] * (2 if failure == "DUPLICATE" else 0)
        }
    else:
        params["exercise_external_id"] = "missing-exercise"
    response = post(environment, content=content, params=params)
    assert response.status_code == 200
    assert response.json()["persistence"]["status"] == "NOT_STORED"
    assert response.json()["verification"]["export_timebase_verified"] is False
    saver.assert_not_awaited()


def test_storage_consistency_failure_is_generic_conflict(environment, monkeypatch):
    monkeypatch.setattr(
        module,
        "persist_hr_timebase_snapshot",
        AsyncMock(side_effect=ValueError("private database details")),
    )
    response = post(environment)
    assert response.status_code == 409
    assert "private database details" not in response.text


def test_existing_verify_endpoint_keeps_its_original_read_only_contract(environment, monkeypatch):
    saver = AsyncMock(side_effect=AssertionError("verify endpoint is read only"))
    monkeypatch.setattr(module, "persist_hr_timebase_snapshot", saver)
    response = environment.client.post(
        BASE + "/verify-tcx",
        params={"sample_date": "2025-02-12"},
        content=XML,
        headers={"content-type": "application/xml"},
    )
    assert response.status_code == 200
    assert response.json()["policy"]["persists_timebase_evidence"] is False
    saver.assert_not_awaited()


def test_saved_lookup_revalidates_against_current_api_without_file_upload(environment, monkeypatch):
    records = saved_records(environment)
    loader = AsyncMock(return_value=records)
    monkeypatch.setattr(module, "load_current_hr_timebase_snapshots", loader)
    response = get(environment)
    assert response.status_code == 200
    data = response.json()
    assert data["stored_current_source_snapshot_count"] == 1
    assert data["saved_timebase"]["verified_exercise_count"] == 1
    assert data["current_api_source_hash"] == records[0]["snapshot"]["api_source_hash"]
    assert data["training_authorized"] is data["numeric_prediction_authorized"] is False
    loader.assert_awaited_once_with(
        environment.db,
        environment.session,
        athlete_id="synthetic-athlete",
        session_external_id="api-session",
        sample_session_match_count=1,
    )
    environment.provider.assert_awaited_once()
    assert "synthetic-test-token" not in response.text


@pytest.mark.parametrize("failure", ["OWNER", "SOURCE", "COLUMN", "NO_RECORD"])
def test_saved_lookup_cannot_reuse_invalid_or_missing_proof(environment, monkeypatch, failure):
    records = saved_records(environment)
    if failure == "OWNER":
        environment.user.return_value = SimpleNamespace(id="another-athlete")
    elif failure == "SOURCE":
        environment.session["modified"] = "2025-02-13T00:00:00Z"
    elif failure == "COLUMN":
        records[0]["column_identity"]["source_provider"] = "OTHER"
    else:
        records = []
    monkeypatch.setattr(
        module, "load_current_hr_timebase_snapshots", AsyncMock(return_value=records)
    )
    data = get(environment).json()
    assert data["saved_timebase"]["verified_exercise_count"] == 0
    assert data["training_authorized"] is False


@pytest.mark.parametrize("method", ["POST", "GET"])
@pytest.mark.parametrize("scopes,status", [(None, 404), ([], 403)])
def test_new_endpoints_require_owned_connection_and_scope_before_storage(
    environment, monkeypatch, method, scopes, status
):
    environment.db.scalar.return_value = None if scopes is None else SimpleNamespace(scopes=scopes)
    saver, loader = AsyncMock(), AsyncMock()
    monkeypatch.setattr(module, "persist_hr_timebase_snapshot", saver)
    monkeypatch.setattr(module, "load_current_hr_timebase_snapshots", loader)
    response = post(environment) if method == "POST" else get(environment)
    assert response.status_code == status
    environment.provider.assert_not_awaited()
    saver.assert_not_awaited()
    loader.assert_not_awaited()


@pytest.mark.parametrize(
    "headers,status",
    [
        ({"content-type": "application/json"}, 415),
        ({"content-length": str(module.MAX_IMPORT_BYTES + 1)}, 413),
    ],
)
def test_persist_body_guards_run_before_provider_or_storage(
    environment, monkeypatch, headers, status
):
    saver = AsyncMock()
    monkeypatch.setattr(module, "persist_hr_timebase_snapshot", saver)
    assert post(environment, headers=headers).status_code == status
    environment.provider.assert_not_awaited()
    saver.assert_not_awaited()


def test_saved_lookup_rejects_maximum_date_before_provider_request(environment):
    assert get(environment, sample_date="9999-12-31").status_code == 422
    environment.provider.assert_not_awaited()


def test_both_new_endpoints_are_registered_with_binary_upload_schema():
    app = FastAPI()
    app.include_router(api_router)
    schema = app.openapi()
    base = "/integrations/polar/sessions/{session_external_id}/hr-timebase"
    assert "get" in schema["paths"][base + "/saved"]
    body = schema["paths"][base + "/persist-tcx"]["post"]["requestBody"]
    assert body["content"]["application/zip"]["schema"]["format"] == "binary"
