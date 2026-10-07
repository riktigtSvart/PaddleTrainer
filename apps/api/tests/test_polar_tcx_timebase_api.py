from copy import deepcopy
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.router import api_router
from app.api.routes import polar_tcx as module
from app.integrations.polar.client import PolarAPIError

XML = b"""<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">
<Activities><Activity Sport="Other"><Id>2025-02-12T09:00:00.137Z</Id>
<Lap StartTime="2025-02-12T09:00:00.137Z"><TotalTimeSeconds>5</TotalTimeSeconds><Track>
<Trackpoint><Time>2025-02-12T09:00:01.137Z</Time><HeartRateBpm><Value>120</Value></HeartRateBpm></Trackpoint>
<Trackpoint><Time>2025-02-12T09:00:02.137Z</Time><HeartRateBpm><Value>122</Value></HeartRateBpm></Trackpoint>
</Track></Lap></Activity></Activities></TrainingCenterDatabase>"""
URL = "/api/v1/integrations/polar/sessions/api-session/hr-timebase/verify-tcx"


@pytest.fixture
def environment(monkeypatch):
    db = SimpleNamespace(
        scalar=AsyncMock(return_value=SimpleNamespace(scopes=["training_sessions:read"]))
    )
    session = {
        "identifier": {"id": "api-session"},
        "timezoneOffsetMinutes": 60,
        "exercises": [
            {
                "identifier": {"id": "api-exercise"},
                "startTime": "2025-02-12T10:00:00",
                "stopTime": "2025-02-12T10:00:05",
                "durationMillis": 5000,
                "samples": {
                    "samples": [
                        {
                            "type": "HEART_RATE",
                            "intervalMillis": 1000,
                            "values": [120, 122],
                        }
                    ]
                },
            }
        ],
    }
    provider = AsyncMock(return_value={"trainingSessions": [session]})
    user = AsyncMock(return_value=SimpleNamespace(id="synthetic-athlete"))
    token = AsyncMock(return_value="synthetic-test-token")
    monkeypatch.setattr(module, "get_or_create_demo_user", user)
    monkeypatch.setattr(module, "get_valid_access_token", token)
    monkeypatch.setattr(
        module, "PolarClient", lambda: SimpleNamespace(list_training_sessions=provider)
    )
    app = FastAPI()
    app.include_router(module.router, prefix="/api/v1")
    app.dependency_overrides[module.get_db] = lambda: db
    with TestClient(app) as client:
        yield SimpleNamespace(
            client=client, provider=provider, user=user, token=token, db=db, session=session
        )


def post(environment, *, content=XML, params=None, headers=None):
    return environment.client.post(
        URL,
        params={"sample_date": "2025-02-12", **(params or {})},
        content=content,
        headers={"content-type": "application/xml", **(headers or {})},
    )


def test_raw_upload_exposes_verified_export_without_token_or_gps(environment):
    response = post(environment)
    assert response.status_code == 200
    data = response.json()
    assert data["export_timebase_verified"] is True
    assert data["timebase"]["first_sample_offset_from_api_exercise_start_ms"] == 1137
    assert data["training_authorized"] is False
    assert data["numeric_prediction_authorized"] is False
    assert "synthetic-test-token" not in response.text
    environment.provider.assert_awaited_once_with(
        "synthetic-test-token", date(2025, 2, 12), date(2025, 2, 13), features=["samples"]
    )


def test_exercise_selector_is_forwarded(environment):
    other = deepcopy(environment.session["exercises"][0])
    other["identifier"]["id"] = "second"
    environment.session["exercises"].append(other)
    assert post(environment).json()["export_timebase_verified"] is False
    data = post(environment, params={"exercise_external_id": "second"}).json()
    assert data["export_timebase_verified"] is True
    assert data["exercise_external_id"] == "second"


@pytest.mark.parametrize("count", [0, 2])
def test_missing_or_duplicate_provider_sessions_are_withheld(environment, count):
    environment.provider.return_value = {"trainingSessions": [environment.session] * count}
    response = post(environment)
    assert response.status_code == 200
    assert response.json()["export_timebase_verified"] is False
    assert "SAMPLE_SESSION_MISSING_OR_AMBIGUOUS" in response.json()["blocking_reasons"]


def test_wrong_session_is_not_assigned_by_list_position(environment):
    environment.session["identifier"]["id"] = "another-session"
    assert post(environment).json()["export_timebase_verified"] is False


@pytest.mark.parametrize("scopes,status", [(None, 404), ([], 403)])
def test_connection_and_read_scope_are_required(environment, scopes, status):
    environment.db.scalar.return_value = None if scopes is None else SimpleNamespace(scopes=scopes)
    assert post(environment).status_code == status
    environment.token.assert_not_awaited()
    environment.provider.assert_not_awaited()


@pytest.mark.parametrize(
    "payload", [None, [], {}, {"trainingSessions": {}}, {"trainingSessions": None}]
)
def test_bad_provider_shape_is_a_controlled_gateway_error(environment, payload):
    environment.provider.return_value = payload
    assert post(environment).status_code == 502


def test_provider_failure_does_not_leak_credentials(environment):
    environment.provider.side_effect = PolarAPIError("private upstream details")
    response = post(environment)
    assert response.status_code == 502
    assert "private upstream details" not in response.text


@pytest.mark.parametrize(
    "headers,status",
    [
        ({"content-type": "multipart/form-data"}, 415),
        ({"content-type": "application/json"}, 415),
        ({"content-encoding": "gzip"}, 415),
        ({"content-length": "invalid"}, 400),
        ({"content-length": "-1"}, 400),
        ({"content-length": str(module.MAX_IMPORT_BYTES + 1)}, 413),
    ],
)
def test_http_upload_guards_run_before_provider_request(environment, headers, status):
    assert post(environment, headers=headers).status_code == status
    environment.provider.assert_not_awaited()


def test_streamed_body_limit_does_not_trust_content_length(environment, monkeypatch):
    monkeypatch.setattr(module, "MAX_IMPORT_BYTES", 8)
    response = post(environment, content=iter([b"123456", b"123456"]))
    assert response.status_code == 413
    environment.provider.assert_not_awaited()


def test_corrupt_xml_is_a_withheld_audit_result(environment):
    response = post(environment, content=b"<broken")
    assert response.status_code == 200
    assert "TCX_XML_INVALID" in response.json()["blocking_reasons"]


def test_maximum_sample_date_is_rejected_before_date_arithmetic(environment):
    assert post(environment, params={"sample_date": "9999-12-31"}).status_code == 422
    environment.provider.assert_not_awaited()


def test_route_is_registered_in_application_router_and_documents_raw_bytes():
    path = "/integrations/polar/sessions/{session_external_id}/hr-timebase/verify-tcx"
    app = FastAPI()
    app.include_router(api_router)
    schema = app.openapi()
    assert "post" in schema["paths"][path]
    body = schema["paths"][path]["post"]["requestBody"]
    assert body["content"]["application/zip"]["schema"]["format"] == "binary"
