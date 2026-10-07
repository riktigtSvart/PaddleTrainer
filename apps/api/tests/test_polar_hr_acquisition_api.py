from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from test_heart_rate_sample_validation import session as _session_fixture
from test_hr_acquisition_declarations import PAYLOAD
from test_hr_acquisition_persistence import OWNER
from test_hr_timebase_persistence import AsyncSQLiteBridge

from app.api.router import api_router
from app.api.routes import polar_hr_acquisition as module
from app.api.routes import polar_tcx as provider_module
from app.models.entities import ExternalConnection, User
from app.models.hr_acquisition_declaration import HRAcquisitionDeclaration

session = _session_fixture
BASE = "/api/v1/integrations/polar/sessions/hr-session/hr-acquisition"


class APIBridge(AsyncSQLiteBridge):
    async def scalar(self, statement):
        return self.session.scalar(statement)


@pytest.fixture
def environment(monkeypatch, session):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    for model in (User, ExternalConnection, HRAcquisitionDeclaration):
        model.__table__.create(engine)
    with Session(engine, expire_on_commit=False) as sync:
        sync.add(
            User(id=OWNER, email="declaration-owner@example.test", created_at=datetime.now(UTC))
        )
        sync.flush()
        connection = ExternalConnection(
            user_id=OWNER,
            provider="POLAR",
            access_token_encrypted="unused-encrypted-token",
            expires_at=datetime.now(UTC) + timedelta(days=1),
            scopes=["training_sessions:read"],
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        sync.add(connection)
        sync.commit()
        db = APIBridge(sync)
        user = AsyncMock(return_value=SimpleNamespace(id=OWNER))
        token = AsyncMock(return_value="private-test-token")
        provider = AsyncMock(return_value={"trainingSessions": [session]})
        monkeypatch.setattr(provider_module, "get_or_create_demo_user", user)
        monkeypatch.setattr(provider_module, "get_valid_access_token", token)
        monkeypatch.setattr(
            provider_module, "PolarClient", lambda: SimpleNamespace(list_training_sessions=provider)
        )
        app = FastAPI()
        app.include_router(module.router, prefix="/api/v1")
        app.dependency_overrides[module.get_db] = lambda: db
        with TestClient(app) as client:
            yield SimpleNamespace(
                client=client,
                db=db,
                source=session,
                connection=connection,
                user=user,
                token=token,
                provider=provider,
            )
    engine.dispose()


def post(env, **changes):
    return env.client.post(
        BASE + "/declarations", params={"sample_date": "2026-09-30"}, json={**PAYLOAD, **changes}
    )


def get(env, date_value="2026-09-30"):
    return env.client.get(BASE, params={"sample_date": date_value})


def test_actual_api_database_round_trip_preserves_provenance_and_never_quality_authority(
    environment,
):
    first, repeat = post(environment), post(environment)
    assert first.status_code == repeat.status_code == 200
    data, repeated = first.json(), repeat.json()
    assert data["persistence"]["status"] == "CREATED"
    assert repeated["persistence"]["status"] == "ALREADY_PRESENT"
    assert data["persistence"]["declaration_id"] == repeated["persistence"]["declaration_id"]
    assert data["persistence"]["round_trip_verified"] is True
    saved = get(environment)
    result = saved.json()
    assert result["stored_current_source_declaration_count"] == 1
    assert result["source_binding_verified"] is True
    assert result["acquisition_context"]["status"] == "USER_DECLARED_WITH_LIMITATIONS"
    sensor = result["acquisition_context"]["exercises"][0]
    assert sensor["declaration_source"] == "USER_DECLARATION"
    assert sensor["declared_sensor"]["sensor_model"] == "Example Wearable"
    assert sensor["sensor_identity_verified"] is sensor["acquisition_quality_verified"] is False
    assert result["training_authorized"] is result["numeric_prediction_authorized"] is False
    assert len(result["declaration_history"]) == 1
    assert "private-test-token" not in saved.text + first.text
    assert "unused-encrypted-token" not in saved.text + first.text
    assert "values" not in saved.text
    environment.provider.assert_awaited_with(
        "private-test-token", date(2026, 9, 30), date(2026, 10, 1), features=["samples"]
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("athlete_id", "other-owner"),
        ("source_kind", "PROVIDER_VERIFIED"),
        ("sensor_identity_verified", True),
        ("acquisition_quality_verified", True),
        ("training_authorized", True),
        ("numeric_prediction_authorized", True),
        ("sensor_modality", "invented"),
        ("sensor_model", 123),
    ],
)
def test_invalid_client_claims_are_rejected_before_provider_or_storage(environment, field, value):
    response = post(environment, **{field: value})
    assert response.status_code == 422
    environment.provider.assert_not_awaited()
    assert environment.db.session.scalars(select(HRAcquisitionDeclaration)).all() == []


def test_unknown_exercise_or_ambiguous_session_cannot_be_persisted(environment):
    response = post(environment, exercise_external_id="missing-exercise")
    assert response.status_code == 409
    assert "EXERCISE_MISSING_OR_AMBIGUOUS" in response.json()["detail"]
    environment.provider.return_value = {"trainingSessions": [environment.source] * 2}
    assert post(environment).status_code == 409
    result = get(environment).json()
    assert result["source_binding_verified"] is False
    assert result["acquisition_context"]["status"] == "WITHHELD"
    assert environment.db.session.scalars(select(HRAcquisitionDeclaration)).all() == []


@pytest.mark.parametrize("method", ["POST", "GET"])
@pytest.mark.parametrize("connection_present,status", [(False, 404), (True, 403)])
def test_owned_connection_and_read_scope_are_required(
    environment, method, connection_present, status
):
    if connection_present:
        environment.connection.scopes = []
    else:
        environment.db.session.delete(environment.connection)
    environment.db.session.commit()
    response = post(environment) if method == "POST" else get(environment)
    assert response.status_code == status
    environment.provider.assert_not_awaited()
    environment.token.assert_not_awaited()


def test_explicit_correction_has_readable_history_and_does_not_reactivate_old_request(environment):
    first_id = post(environment).json()["persistence"]["declaration_id"]
    corrected = post(
        environment, sensor_model="Corrected Device", supersedes_declaration_ids=[first_id]
    ).json()
    assert corrected["persistence"]["status"] == "CREATED"
    assert post(environment).json()["persistence"]["declaration_active"] is False
    result = get(environment).json()
    assert len(result["declaration_history"]) == 2
    context = result["acquisition_context"]["exercises"][0]
    assert context["declared_sensor"]["sensor_model"] == "Corrected Device"
    assert context["active_declaration_ids"] == [corrected["persistence"]["declaration_id"]]
    response = post(
        environment, sensor_model="Stale Correction", supersedes_declaration_ids=[first_id]
    )
    assert response.status_code == 409
    assert "CORRECTION_TARGETS_NOT_CURRENT" in response.json()["detail"]


def test_source_change_requires_new_declaration_without_destroying_old_rows(environment):
    first = post(environment).json()
    environment.source["modified"] = "2025-03-01T00:00:00Z"
    current = get(environment).json()
    assert current["stored_current_source_declaration_count"] == 0
    assert current["acquisition_context"]["status"] == "NOT_DECLARED"
    response = post(
        environment, supersedes_declaration_ids=[first["persistence"]["declaration_id"]]
    )
    assert response.status_code == 409
    assert len(environment.db.session.scalars(select(HRAcquisitionDeclaration)).all()) == 1


def test_corrupted_database_payload_is_withheld_without_exposing_invalid_history(environment):
    post(environment)
    row = environment.db.session.scalar(select(HRAcquisitionDeclaration))
    row.declaration_json = {}
    environment.db.session.commit()
    response = get(environment)
    assert response.status_code == 200
    data = response.json()
    assert data["acquisition_context"]["status"] == "WITHHELD"
    assert data["history_available"] is False
    assert data["declaration_history"] == []


@pytest.mark.parametrize("method", ["POST", "GET"])
def test_maximum_date_is_rejected_before_provider_request(environment, method):
    if method == "POST":
        response = environment.client.post(
            BASE + "/declarations", json=PAYLOAD, params={"sample_date": "9999-12-31"}
        )
    else:
        response = get(environment, "9999-12-31")
    assert response.status_code == 422
    environment.provider.assert_not_awaited()


def test_schema_exposes_json_declarations_with_no_client_quality_flags():
    app = FastAPI()
    app.include_router(api_router)
    schema = app.openapi()
    base = "/integrations/polar/sessions/{session_external_id}/hr-acquisition"
    assert "get" in schema["paths"][base]
    assert (
        "application/json"
        in schema["paths"][base + "/declarations"]["post"]["requestBody"]["content"]
    )
    body = schema["components"]["schemas"]["HRAcquisitionDeclarationCreate"]
    assert body["additionalProperties"] is False
    assert "acquisition_quality_verified" not in body["properties"]
