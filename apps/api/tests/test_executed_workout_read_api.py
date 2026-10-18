"""HTTP/SQLite ownership, read-only queries and execution contract round trips."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import sys
from uuid import uuid4
import zipfile

import pytest

from test_plan_contract_read_api import environment, OWNER, OTHER, NOW, polar_target
from test_executed_workout_adapter import source
from app.api.routes import executed_workouts as routes
from app.models.entities import Sport, User, WorkoutLinkSource, WorkoutSession
from app.planning_contracts.execution_adapter import verify_execution_read


@pytest.fixture
def executions(environment):
    env = environment
    WorkoutSession.__table__.create(env.session.bind)
    def add(*, owner=OWNER, plan=None, raw=None, sid=None, day=0, link_source=None):
        raw = deepcopy(source()["raw_data"] if raw is None else raw)
        external = sid or "session-" + uuid4().hex
        if isinstance(raw, dict) and "identifier" in raw:
            raw["identifier"]["id"] = external
        row = WorkoutSession(id=uuid4(), user_id=owner, planned_workout_id=plan.id if plan else None,
            planned_workout_link_source=link_source, external_provider="POLAR", external_id=external,
            sport=Sport.KAYAK, started_at=NOW + timedelta(days=day), ended_at=NOW + timedelta(days=day, seconds=100),
            duration_sec=99, distance_m=198, avg_hr=130, avg_speed=7.2, cardio_load=10,
            raw_data=raw, created_at=NOW)
        env.session.add(row); env.session.commit(); env.sql.clear()
        return row
    env.add_execution = add
    return env


def read(env, row, **kwargs):
    return env.client.get(f"/api/v1/sessions/{row.id}/executed-workout", **kwargs)


def test_full_app_execution_detail_uses_only_selects_and_preserves_all_orm_columns(executions):
    env = executions; row = env.add_execution()
    response = read(env, row)
    assert response.status_code == 200, response.text
    v = response.json()
    assert verify_execution_read(v)
    assert set(v["source_snapshot"]) == set(WorkoutSession.__table__.columns.keys())
    assert v["adapter_result"]["executed"]["provider_session_id"] == row.external_id
    assert response.headers["cache-control"] == "no-store"
    assert env.sql and set(env.sql) == {"SELECT"}


def test_exact_source_id_lookup_without_stored_foreign_key_is_read_only(executions):
    env = executions; plan = env.add(source="POLAR", raw=polar_target(duration=30000))
    row = env.add_execution()
    response = read(env, row)
    assert response.status_code == 200, response.text
    v = response.json(); item = v["adapter_result"]["executed"]
    assert item["plan_link_status"] == "EXACT_PROVIDER_ID"
    assert item["plan_ref"]["plan_id"] == v["plan_capture"]["adapter_result"]["plan"]["plan_id"]
    assert any(b["execution_role"] == "PLAN_PHASE_CANDIDATE" for b in item["blocks"])
    assert row.planned_workout_id is None
    assert verify_execution_read(v)
    assert set(env.sql) == {"SELECT"}


def test_duplicate_source_target_ids_do_not_select_an_arbitrary_plan(executions):
    env = executions
    plans = [env.add(source="POLAR", raw=polar_target()) for _ in range(2)]
    row = env.add_execution()
    v = read(env, row).json()
    assert v["plan_capture"] is None
    assert v["plan_selection"]["status"] == "AMBIGUOUS_OWNED_TARGET_ID"
    assert v["adapter_result"]["executed"]["plan_ref"] is None


def test_missing_or_foreign_session_has_identical_404(executions):
    env = executions; row = env.add_execution(owner=OTHER)
    forbidden = read(env, row)
    missing = env.client.get(f"/api/v1/sessions/{uuid4()}/executed-workout")
    assert forbidden.status_code == missing.status_code == 404
    assert forbidden.json() == missing.json()


def test_foreign_linked_plan_is_not_exposed_or_joined(executions):
    env = executions; plan = env.add(owner=OTHER, source="POLAR", raw=polar_target())
    row = env.add_execution(plan=plan)
    v = read(env, row).json()
    assert v["plan_capture"] is None
    assert v["plan_selection"]["status"] == "PLAN_NOT_AVAILABLE_FOR_OWNER"
    assert v["adapter_result"]["executed"]["plan_ref"] is None


def test_broken_plan_projection_does_not_destroy_valid_session_summary(executions):
    env = executions; plan = env.add(source="POLAR", raw=polar_target())
    plan.raw_data = {"session": {"id": "1450000123"}}; env.session.commit()
    row = env.add_execution(plan=plan)
    response = read(env, row)
    assert response.status_code == 200
    v = response.json()
    assert v["plan_selection"]["status"] == "PLAN_CAPTURE_WITHHELD"
    assert v["adapter_result"]["executed"]["blocks"][0]["execution_role"] == "WHOLE_SESSION_SUMMARY"
    assert verify_execution_read(v)


def test_list_is_owner_scoped_paginated_and_reports_withheld_rows(executions):
    env = executions
    rows = [env.add_execution(day=i) for i in range(3)]
    foreign = env.add_execution(owner=OTHER, day=-1)
    rows[1].raw_data = {"startTime": "2026-08-01T11:00:00"}; env.session.commit(); env.sql.clear()
    page = env.client.get("/api/v1/planning/executed-workouts?limit=2").json()
    assert page["returned_count"] == 2 and page["converted_count"] == 1 and page["withheld_count"] == 1
    assert page["has_more"] and page["next_offset"] == 2
    assert {i["session_id"] for i in page["items"]} == {str(rows[0].id), str(rows[1].id)}
    assert page["items"][1]["blocking_reason"] == "EXECUTION_NAIVE_PROVIDER_CLOCK_REQUIRES_DECLARED_OFFSET"
    last = env.client.get("/api/v1/planning/executed-workouts?limit=2&offset=2").json()
    assert last["returned_count"] == 1 and last["next_offset"] is None and not last["has_more"]
    assert last["items"][0]["session_id"] == str(rows[2].id)
    assert set(env.sql) == {"SELECT"}


def test_byte_shortened_page_offset_follows_returned_count(executions, monkeypatch):
    env = executions; rows = [env.add_execution(day=i) for i in range(3)]
    value = read(env, rows[0]).json()
    monkeypatch.setattr(routes, "MAX_PAGE_BYTES", len(routes.canonical_bytes(value)) + 100)
    page = env.client.get("/api/v1/planning/executed-workouts?limit=3").json()
    assert page["returned_count"] == 1 and page["has_more"] and page["next_offset"] == 1
    second = env.client.get("/api/v1/planning/executed-workouts?limit=3&offset=1").json()
    assert second["items"][0]["session_id"] == str(rows[1].id)


@pytest.mark.parametrize("query", ["athlete_id=other", "captured_at=2026-01-01", "limit=0", "limit=11", "offset=-1", "offset=100001"])
def test_list_rejects_authority_timestamp_and_resource_limit_overrides(executions, query):
    assert executions.client.get("/api/v1/planning/executed-workouts?" + query).status_code == 422


def test_detail_rejects_client_supplied_plan_or_clock(executions):
    env = executions; row = env.add_execution()
    assert read(env, row, params={"plan_id": "invented"}).status_code == 422


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_execution_routes_have_no_write_methods(executions, method):
    env = executions; row = env.add_execution()
    assert getattr(env.client, method)(f"/api/v1/sessions/{row.id}/executed-workout").status_code == 405


def test_no_configured_owner_does_not_auto_create_one(executions):
    env = executions
    owner = env.session.get(User, OWNER); owner.email = "renamed@example.test"; env.session.commit(); env.sql.clear()
    assert env.client.get("/api/v1/planning/executed-workouts").status_code == 404
    assert set(env.sql) == {"SELECT"}


def test_unflushed_pending_objects_are_not_written_by_new_reads(executions):
    env = executions; row = env.add_execution()
    pending = User(id=uuid4(), email="pending@example.test", created_at=NOW)
    env.session.add(pending)
    assert read(env, row).status_code == 200
    assert pending in env.session.new
    assert set(env.sql) == {"SELECT"}
    env.session.expunge(pending)


def test_capability_announces_execution_adapter_without_removing_old_paths(executions):
    env = executions
    caps = env.client.get("/api/v1/planning/contracts/capabilities").json()
    assert caps["executed_workout_adapter_available"]
    assert caps["executed_workout_adapter_version"] == "executed-workout-adapter-0.1-draft2"
    for typ in ("ExecutedWorkout", "WorkoutPlanContract"):
        assert env.client.get("/api/v1/planning/contracts/schemas/" + typ).status_code == 200
    assert env.client.get("/api/v1/pft/capabilities").status_code == 200


def load_probe():
    path = Path(__file__).resolve().parents[3] / "tools/probe_executed_workout_api.py"
    spec = importlib.util.spec_from_file_location("execution_probe_for_test", path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("has_sample", [True, False])
def test_user_probe_creates_valid_archive_for_real_app_responses(executions, tmp_path, monkeypatch, has_sample):
    env = executions
    if has_sample:
        plan = env.add(source="POLAR", raw=polar_target(duration=30000))
        row = env.add_execution()
    module = load_probe()
    def fetch(base, path):
        response = env.client.get(path)
        assert response.status_code == 200, response.text
        return response.json()
    monkeypatch.setattr(module, "get_json", fetch)
    output = tmp_path / "probe with spaces"
    monkeypatch.setattr(sys, "argv", ["probe", "--output", str(output)])
    assert module.main() == 0
    with zipfile.ZipFile(output.with_suffix(".zip")) as z:
        summary = json.loads(z.read("summary.json"))
        assert summary["sample_contract_round_trip_verified"] is has_sample
        if has_sample:
            assert summary["status"] == "EXECUTED_WORKOUT_API_READ_PROBE_PASSED"
            assert summary["candidate_phase_count_on_probe_page"] == 1
            assert verify_execution_read(json.loads(z.read("detail.json")))
        else:
            assert summary["status"] == "EXECUTED_WORKOUT_API_REACHABLE_WITHOUT_CONVERTED_SAMPLE"
            assert summary["empty_stored_session_list"]
