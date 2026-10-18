"""Real HTTP routing, ORM persistence, owner isolation and version retention."""
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import UTC, datetime
import json
from types import SimpleNamespace
from uuid import UUID
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.routes import pft as module
from app.models.entities import User
from app.models.pft_measurement import PftMeasurement, PftRecording
from test_pft_processing_integration import CONTEXT, FIXTURE

OWNER = UUID("00000000-0000-0000-0000-000000001101")
OTHER = UUID("00000000-0000-0000-0000-000000001102")
BASE = "/api/v1/pft/measurements"


class AsyncBridge:
    def __init__(self, sync):
        self.session = sync

    async def execute(self, statement):
        return self.session.execute(statement)

    def add(self, row):
        self.session.add(row)

    async def flush(self):
        self.session.flush()

    async def commit(self):
        self.session.commit()

    @asynccontextmanager
    async def begin_nested(self):
        with self.session.begin_nested():
            yield


@pytest.fixture
def environment(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
    for model in (User, PftRecording, PftMeasurement):
        model.__table__.create(engine)
    with Session(engine, expire_on_commit=False) as sync:
        sync.add_all([User(id=OWNER, email="pft-owner@example.test", created_at=datetime.now(UTC)),
                      User(id=OTHER, email="pft-other@example.test", created_at=datetime.now(UTC))])
        sync.commit()
        env = SimpleNamespace(owner=OWNER, session=sync)
        async def owner(db):
            return SimpleNamespace(id=env.owner)
        monkeypatch.setattr(module, "get_or_create_demo_user", owner)
        app = FastAPI()
        app.include_router(module.router, prefix="/api/v1")
        app.dependency_overrides[module.get_db] = lambda: AsyncBridge(sync)
        with TestClient(app) as client:
            env.client = client
            yield env
    engine.dispose()


def upload(env, **changes):
    return env.client.post(
        BASE+"/tcx", content=FIXTURE.read_bytes(),
        headers={"Content-Type": "application/xml",
                 "X-PFT-Context": json.dumps({**CONTEXT, **changes})},
        params={"filename": FIXTURE.name},
    )


def test_upload_repeat_list_detail_and_raw_samples_round_trip(environment):
    first = upload(environment)
    assert first.status_code == 200, first.text
    data = first.json()
    repeated = upload(environment).json()
    assert data["persistence_status"] == "CREATED"
    assert repeated["persistence_status"] == "ALREADY_PRESENT"
    assert repeated["measurement_id"] == data["measurement_id"]
    assert len(environment.session.scalars(select(PftRecording)).all()) == 1
    assert len(environment.session.scalars(select(PftMeasurement)).all()) == 1
    listed = environment.client.get(BASE).json()
    assert len(listed["measurements"]) == 1
    detail = environment.client.get(BASE+"/"+data["measurement_id"],
                                    params={"include_samples": True})
    assert detail.status_code == 200
    assert len(detail.json()["recording_samples"]) == 787
    assert detail.json()["processing_output"]["features"][0]["value"] == 69
    assert detail.json()["state_estimation_authorized"] is False
    assert data["identity_scope"] == "APPLICATION_DEMO_USER"


@pytest.mark.parametrize("field,value", [
    ("user_id", str(OTHER)), ("sensor_identity_verified", True),
    ("state_estimation_authorized", True), ("training_plan_modification_authorized", True),
])
def test_invalid_claims_create_no_pft_rows(environment, field, value):
    response = upload(environment, **{field: value})
    assert response.status_code == 422
    assert environment.session.scalars(select(PftRecording)).all() == []
    assert environment.session.scalars(select(PftMeasurement)).all() == []


def test_other_owner_cannot_read_reprocess_or_compare_measurement(environment):
    first = upload(environment).json()
    identity = first["measurement_id"]
    environment.owner = OTHER
    assert environment.client.get(BASE+"/"+identity).status_code == 404
    assert environment.client.post(BASE+"/"+identity+"/reprocess", json=CONTEXT).status_code == 404
    assert environment.client.post(BASE+"/"+identity+"/compare",
                                   json={"reference_measurement_id": identity}).status_code == 404
    assert environment.client.get(BASE).json()["measurements"] == []
    second = upload(environment).json()
    assert second["recording_id"] != first["recording_id"]


def test_reprocess_preserves_old_result_and_does_not_add_an_independent_recording(environment):
    original = upload(environment).json()
    changed = environment.client.post(
        BASE+"/"+original["measurement_id"]+"/reprocess",
        json={**CONTEXT, "hydration_note": "Additional declaration"},
    )
    assert changed.status_code == 200, changed.text
    newer = changed.json()
    assert newer["measurement_id"] != original["measurement_id"]
    assert newer["recording_id"] == original["recording_id"]
    saved_old = environment.client.get(BASE+"/"+original["measurement_id"]).json()
    assert saved_old["declared_context"]["hydration_note"] is None
    assert len(environment.session.scalars(select(PftRecording)).all()) == 1
    assert len(environment.session.scalars(select(PftMeasurement)).all()) == 2
    comparison = environment.client.post(
        BASE+"/"+newer["measurement_id"]+"/compare",
        json={"reference_measurement_id": original["measurement_id"]},
    )
    assert comparison.status_code == 200, comparison.text
    assert comparison.json()["independent_recordings"] is False
    assert comparison.json()["reference_available_before_current_start"] is False
    assert comparison.json()["pre_exercise_prediction_authorized"] is False


def test_changed_target_profile_cannot_be_silently_compared(environment):
    original = upload(environment).json()
    newer = environment.client.post(
        BASE+"/"+original["measurement_id"]+"/reprocess",
        json={**CONTEXT, "target_power_w": {"p0": 380, "p1": 460, "p2": 570}},
    ).json()
    response = environment.client.post(
        BASE+"/"+newer["measurement_id"]+"/compare",
        json={"reference_measurement_id": original["measurement_id"]},
    )
    assert response.status_code == 409
    assert "CONTEXT_DIFFERS" in response.json()["detail"]


@pytest.mark.parametrize("table,field,value", [
    (PftMeasurement, "result_json", {}),
    (PftMeasurement, "processing_manifest", {}),
    (PftRecording, "raw_tcx", b"damaged"),
])
def test_corruption_is_withheld(environment, table, field, value):
    data = upload(environment).json()
    row = environment.session.scalar(select(table))
    setattr(row, field, value)
    environment.session.commit()
    response = environment.client.get(BASE+"/"+data["measurement_id"])
    assert response.status_code == 409
    assert "processing_output" not in response.json()


def test_body_limit_and_invalid_xml_do_not_create_rows(environment, monkeypatch):
    monkeypatch.setattr(module, "MAX_PFT_IMPORT_BYTES", 8)
    assert upload(environment).status_code == 413
    assert environment.session.scalars(select(PftRecording)).all() == []
    monkeypatch.setattr(module, "MAX_PFT_IMPORT_BYTES", 1024)
    response = environment.client.post(BASE+"/tcx", content=b"not xml",
        headers={"X-PFT-Context": json.dumps(CONTEXT), "Content-Type": "application/xml"})
    assert response.status_code == 422
    assert environment.session.scalars(select(PftMeasurement)).all() == []


def test_openapi_and_router_contract_expose_measured_data_without_readiness(environment):
    schema = environment.client.get("/openapi.json").json()
    assert "/api/v1/pft/measurements/tcx" in schema["paths"]
    assert schema["paths"]["/api/v1/pft/measurements/tcx"]["post"]["requestBody"]["content"]["application/xml"]
    capabilities = environment.client.get("/api/v1/pft/capabilities").json()
    assert capabilities["supported_sources"] == ["TCX_UPLOAD"]
    assert capabilities["state_estimation_authorized"] is False
