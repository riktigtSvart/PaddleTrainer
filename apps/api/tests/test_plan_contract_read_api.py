"""Real HTTP + SQLAlchemy/SQLite tests; no production DB or provider calls."""
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.routes import plan_contracts as routes
from app.api.routes import pft
from app.main import app
from app.models.entities import (BlockType, PlannedWorkout, Sport, TrainingPeriod,
                                 User, WorkoutBlock, WorkoutStatus)
from app.models.pft_measurement import PftMeasurement, PftRecording
from app.planning_contracts.contract_checks import structural, validate_contract
from app.planning_contracts.legacy_plan_adapter import canonical_bytes, verify_result
from app.services import plan_contract_read as service

OWNER = UUID("00000000-0000-0000-0000-000000008801")
OTHER = UUID("00000000-0000-0000-0000-000000008802")
NOW = datetime(2026, 10, 15, 10, tzinfo=timezone.utc)


class AsyncBridge:
    def __init__(self, session):
        self.session = session

    @property
    def no_autoflush(self):
        return self.session.no_autoflush

    async def scalar(self, statement):
        return self.session.scalar(statement)

    async def scalars(self, statement):
        return self.session.scalars(statement)

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


def polar_target(change="AUTOMATIC", duration=1500.5):
    return {"session": {"id": "1450000123", "version": 2, "name": "6km fartlek", "description": "",
            "startTime": {"year": 2026, "month": 8, "day": 1, "hour": 10, "min": 0, "sec": 0}},
            "exercise": [{"idx": 0, "sportId": "95", "type": "PHASED", "duration": duration,
                "phaseOrRepeat": [{"name": "source phase", "changeType": change,
                    "goal": {"type": "DURATION", "duration": duration}, "phaseOrRepeat": [],
                    "intensity": {"type": "HEART_RATE_ZONES", "lowerZone": 1, "upperZone": 4}}]}]}


@pytest.fixture
def environment(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    sql = []
    @event.listens_for(engine, "before_cursor_execute")
    def record_sql(connection, cursor, statement, parameters, context, many):
        sql.append(statement.lstrip().split()[0].upper())
    for model in (User, TrainingPeriod, PlannedWorkout, WorkoutBlock, PftRecording, PftMeasurement):
        model.__table__.create(engine)
    with Session(engine, expire_on_commit=False) as session:
        session.add_all([User(id=OWNER, email="plan-owner@example.test", created_at=NOW),
                         User(id=OTHER, email="plan-other@example.test", created_at=NOW)])
        session.commit()
        def add_plan(*, owner=OWNER, day=date(2026, 8, 1), source="MANUAL", raw=None, dual=False):
            row = PlannedWorkout(id=uuid4(), user_id=owner, date=day, sport=Sport.KAYAK,
                title="6km fartlek" if source == "POLAR" else "Synthetic stored plan", description=None,
                duration_sec=120, distance_m=1000 if dual else None, source=source,
                status=WorkoutStatus.PLANNED, raw_data=raw,
                polar_target_id=raw["session"]["id"] if raw and "session" in raw else None,
                created_at=NOW, updated_at=NOW, blocks=[])
            if not dual:
                row.blocks.append(WorkoutBlock(id=uuid4(), workout_id=row.id, position=0,
                    block_type=BlockType.WORK, name="Synthetic source block", duration_sec=120,
                    intensity_type="NONE", intensity_min=0, intensity_max=0))
            session.add(row); session.commit(); sql.clear()
            return row
        monkeypatch.setattr(routes, "get_settings", lambda: SimpleNamespace(demo_user_email="plan-owner@example.test"))
        async def pft_owner(db):
            return SimpleNamespace(id=OWNER)
        monkeypatch.setattr(pft, "get_or_create_demo_user", pft_owner)
        old_overrides = dict(app.dependency_overrides)
        app.dependency_overrides[routes.get_db] = lambda: AsyncBridge(session)
        sql.clear()
        with TestClient(app) as client:
            yield SimpleNamespace(client=client, session=session, add=add_plan, sql=sql)
        app.dependency_overrides.clear(); app.dependency_overrides.update(old_overrides)
    engine.dispose()


def detail(env, row, **kwargs):
    return env.client.get(f"/api/v1/workouts/{row.id}/plan-contract", **kwargs)


def test_read_http_contract_is_valid_and_executes_selects_only(environment):
    row = environment.add()
    response = detail(environment, row)
    assert response.status_code == 200, response.text
    value = response.json()
    validate_contract(value["adapter_result"]["plan"])
    verify_result(value["adapter_result"])
    assert value["source_snapshot"]["id"] == str(row.id)
    assert value["adapter_result"]["plan"]["blocks"][0]["block_type"] == "UNKNOWN"
    assert value["numeric_output_authorized"] is False
    assert response.headers["cache-control"] == "no-store"
    assert set(environment.sql) <= {"SELECT"}


def test_repeated_reads_have_fresh_capture_ids_and_equal_content_hash(environment):
    row = environment.add()
    a, b = detail(environment, row).json(), detail(environment, row).json()
    assert a["source_content_sha256"] == b["source_content_sha256"]
    assert a["capture_id"] != b["capture_id"]
    assert a["adapter_result"]["plan"]["plan_id"] != b["adapter_result"]["plan"]["plan_id"]
    assert a["adapter_result"]["plan"]["evidence"][0]["available_at"] is None


def test_saved_capture_is_deterministic_and_does_not_mutate_source(environment):
    row = environment.add()
    snapshot = service.stored_workout_snapshot(row, OWNER)
    original = deepcopy(snapshot)
    a = service.build_plan_read(snapshot, captured_at=NOW.isoformat())
    b = service.build_plan_read(snapshot, captured_at=NOW.isoformat())
    assert a == b and snapshot == original
    verify_result(a["adapter_result"])


def test_polar_raw_snapshot_preserves_fractional_seconds_and_unbound_zones(environment):
    raw = polar_target()
    row = environment.add(source="POLAR", raw=raw)
    value = detail(environment, row).json()
    assert value["source_kind"] == "STORED_POLAR_TARGET"
    leaf = value["adapter_result"]["plan"]["blocks"][0]["children"][0]
    assert leaf["duration_s"] == 1.5005
    assert leaf["intensity"]["type"] == "UNKNOWN"
    restored = deepcopy(value["adapter_result"]["source"]["payload"])
    del restored[service.CAPTURE_KEY]
    assert restored == raw == row.raw_data
    assert all(not d["numeric_result_allowed"] for d in value["applicability_decisions"])


def test_manual_polar_goal_not_promoted_to_fixed_end(environment):
    row = environment.add(source="POLAR", raw=polar_target(change="MANUAL", duration=120000))
    value = detail(environment, row).json()
    leaf = value["adapter_result"]["plan"]["blocks"][0]["children"][0]
    assert leaf["completion_condition"] == "MANUAL" and leaf["duration_s"] is None
    assert value["source_snapshot"]["raw_data"]["exercise"][0]["phaseOrRepeat"][0]["goal"]["duration"] == 120000


def test_provider_and_orm_description_difference_is_disclosed(environment):
    row = environment.add(source="POLAR", raw=polar_target())
    row.title = "Edited ORM title"; environment.session.commit()
    value = detail(environment, row).json()
    assert value["adapter_result"]["plan"]["title"] == "6km fartlek"
    assert value["source_snapshot"]["title"] == "Edited ORM title"
    assert value["provider_orm_basic_field_differences"] == ["TITLE"]
    assert value["source_views_fully_reconciled"] is False


@pytest.mark.parametrize("corruption", ["MISSING", "WRONG_ID", "BAD_GOAL", "CAPTURE_KEY"])
def test_invalid_provider_source_is_withheld_without_orm_fallback(environment, corruption):
    row = environment.add(source="POLAR", raw=polar_target())
    if corruption == "MISSING": row.raw_data = None
    elif corruption == "WRONG_ID": row.polar_target_id = "another-target"
    elif corruption == "BAD_GOAL":
        raw = deepcopy(row.raw_data); raw["exercise"][0]["phaseOrRepeat"][0]["goal"]["type"] = "UNSUPPORTED"; row.raw_data = raw
    else:
        raw = deepcopy(row.raw_data); raw[service.CAPTURE_KEY] = {}; row.raw_data = raw
    environment.session.commit(); environment.sql.clear()
    response = detail(environment, row)
    assert response.status_code == 409
    assert "adapter_result" not in response.json()
    assert set(environment.sql) <= {"SELECT"}


def test_other_owner_and_missing_workout_are_indistinguishable(environment):
    other = environment.add(owner=OTHER)
    a = detail(environment, other)
    b = environment.client.get(f"/api/v1/workouts/{uuid4()}/plan-contract")
    assert a.status_code == b.status_code == 404 and a.json() == b.json()


def test_missing_configured_owner_does_not_create_a_user(environment, monkeypatch):
    monkeypatch.setattr(routes, "get_settings", lambda: SimpleNamespace(demo_user_email="absent@example.test"))
    response = environment.client.get("/api/v1/planning/plan-contracts")
    assert response.status_code == 404
    assert set(environment.sql) <= {"SELECT"}
    assert len(environment.session.scalars(select(User)).all()) == 2


def test_date_filtered_pagination_is_owned_and_has_no_duplicate_rows(environment):
    first = environment.add(day=date(2026, 8, 1)); second = environment.add(day=date(2026, 8, 2))
    environment.add(owner=OTHER, day=date(2026, 8, 1))
    environment.add(day=date(2026, 8, 10))
    a = environment.client.get("/api/v1/planning/plan-contracts", params={"date_from": "2026-08-01", "date_to": "2026-08-03", "limit": 1}).json()
    assert a["returned_count"] == 1 and a["has_more"] and a["next_offset"] == 1
    assert a["items"][0]["workout_id"] == str(first.id)
    b = environment.client.get("/api/v1/planning/plan-contracts", params={"date_from": "2026-08-01", "date_to": "2026-08-03", "limit": 1, "offset": 1}).json()
    assert b["items"][0]["workout_id"] == str(second.id) and not b["has_more"]
    assert set(environment.sql) <= {"SELECT"}


def test_empty_list_is_not_a_capture_or_a_claim_of_missing_training(environment):
    value = environment.client.get("/api/v1/planning/plan-contracts").json()
    assert value["returned_count"] == 0 and value["items"] == [] and not value["has_more"]
    assert value["numeric_output_authorized"] is False


def test_one_unconvertible_plan_does_not_hide_other_page_items(environment):
    environment.add(dual=True); environment.add()
    response = environment.client.get("/api/v1/planning/plan-contracts")
    assert response.status_code == 200
    value = response.json()
    assert value["converted_count"] == value["withheld_count"] == 1
    assert value["returned_count"] == 2


@pytest.mark.parametrize("params", [{"limit": 26}, {"offset": -1}, {"date_from": "2026-08-03", "date_to": "2026-08-01"},
                                    {"athlete_id": str(OTHER)}, {"captured_at": "2000-01-01T00:00:00Z"}])
def test_invalid_or_authority_changing_queries_are_rejected(environment, params):
    assert environment.client.get("/api/v1/planning/plan-contracts", params=params).status_code == 422
    assert not environment.sql


def test_detail_rejects_client_owner_override_and_bad_uuid(environment):
    row = environment.add()
    assert detail(environment, row, params={"athlete_id": str(OTHER)}).status_code == 422
    assert environment.client.get("/api/v1/workouts/not-a-uuid/plan-contract").status_code == 422
    assert not environment.sql


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_read_endpoint_does_not_accept_write_methods(environment, method):
    row = environment.add()
    response = getattr(environment.client, method)(f"/api/v1/workouts/{row.id}/plan-contract")
    assert response.status_code == 405 and not environment.sql


def test_oversized_source_is_not_serialized(environment, monkeypatch):
    row = environment.add()
    monkeypatch.setattr(service, "MAX_STORED_PLAN_BYTES", 1)
    assert detail(environment, row).status_code == 413


def test_page_byte_budget_preserves_a_continuation(environment, monkeypatch):
    first, second = environment.add(), environment.add()
    size = len(canonical_bytes(detail(environment, first).json()))
    monkeypatch.setattr(routes, "MAX_PAGE_BYTES", size + 200)
    response = environment.client.get("/api/v1/planning/plan-contracts")
    assert response.status_code == 200, response.text
    value = response.json()
    assert value["returned_count"] == 1 and value["has_more"] and value["next_offset"] == 1


def test_schema_is_self_contained_and_matches_the_returned_plan(environment):
    row = environment.add()
    plan = detail(environment, row).json()["adapter_result"]["plan"]
    response = environment.client.get("/api/v1/planning/contracts/schemas/WorkoutPlanContract")
    assert response.status_code == 200
    schema = response.json()
    structural(plan, schema, schema)
    assert schema["$ref"] == "#/$defs/WorkoutPlanContract"
    assert environment.client.get("/api/v1/planning/contracts/schemas/Unknown").status_code == 404


def test_full_app_keeps_pft_routes_and_exposes_no_numeric_authority(environment):
    capabilities = environment.client.get("/api/v1/planning/contracts/capabilities").json()
    assert capabilities["read_only"] and not capabilities["numeric_output_authorized"]
    old = environment.client.get("/api/v1/pft/capabilities")
    assert old.status_code == 200 and old.json()["supported_sources"] == ["TCX_UPLOAD"]
    paths = app.openapi()["paths"]
    assert "/api/v1/pft/measurements/tcx" in paths
    assert "/api/v1/workouts/{workout_id}/plan-contract" in paths
    assert "/api/v1/integrations/polar/sessions/{session_external_id}/response-dataset/replay" in paths


def synthetic_pft_tcx():
    # Deliberately synthetic. Never substitute this for the user's real PFT fixture.
    points = []
    for t in range(781):
        hr = 70 if t < 120 else 120 if t < 300 else 145 if t < 480 else 165 if t < 660 else 165 - (t-660)*0.5
        watts = 0 if t < 120 or t >= 660 else 380 if t < 300 else 460 if t < 480 else 550
        clock = (NOW + timedelta(seconds=t)).isoformat()
        points.append(f'<Trackpoint><Time>{clock}</Time><HeartRateBpm><Value>{hr}</Value></HeartRateBpm><Extensions><a:TPX><a:Watts>{watts}</a:Watts></a:TPX></Extensions></Trackpoint>')
    return ('<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2" xmlns:a="http://www.garmin.com/xmlschemas/ActivityExtension/v2"><Activities><Activity Sport="Running"><Lap><Track>' + ''.join(points) + '</Track></Lap></Activity></Activities></TrainingCenterDatabase>').encode()


def test_plan_reads_and_existing_pft_ingestion_work_in_the_same_app(environment):
    row = environment.add()
    assert detail(environment, row).status_code == 200
    context = {"profile_id": "SYNTHETIC_API_REGRESSION", "target_power_w": {"p0": 380, "p1": 460, "p2": 550}}
    response = environment.client.post("/api/v1/pft/measurements/tcx", content=synthetic_pft_tcx(),
        headers={"X-PFT-Context": json.dumps(context), "Content-Type": "application/xml"})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["persistence_status"] == "CREATED" and data["state_estimation_authorized"] is False
    environment.sql.clear()
    assert detail(environment, row).status_code == 200
    assert set(environment.sql) <= {"SELECT"}
    detail_pft = environment.client.get("/api/v1/pft/measurements/" + data["measurement_id"])
    assert detail_pft.status_code == 200 and detail_pft.json()["recording_id"] == data["recording_id"]


@pytest.mark.parametrize("with_plan", [False, True])
def test_running_api_probe_saves_an_honest_review_archive(environment, tmp_path, monkeypatch, with_plan):
    if with_plan:
        environment.add()
    path = Path(__file__).resolve().parents[3] / "tools/probe_plan_contract_api.py"
    spec = importlib.util.spec_from_file_location("plan_contract_probe_test", path)
    probe = importlib.util.module_from_spec(spec); spec.loader.exec_module(probe)
    def get_json(base, request_path):
        response = environment.client.get(request_path)
        assert response.status_code == 200, response.text
        return response.json()
    monkeypatch.setattr(probe, "get_json", get_json)
    output = tmp_path / "probe results"
    monkeypatch.setattr(sys, "argv", [str(path), "--output", str(output)])
    assert probe.main() == 0
    saved = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert saved["sample_contract_round_trip_verified"] is with_plan
    assert saved["empty_stored_plan_list"] is not with_plan
    assert output.with_suffix(".zip").is_file()
