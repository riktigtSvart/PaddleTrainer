"""Real FastAPI/SQLite comparator reads, ownership and no-write assertions."""
from copy import deepcopy
from uuid import uuid4

import pytest

from test_plan_contract_read_api import environment, OWNER, OTHER, NOW, polar_target
from test_executed_workout_read_api import executions
from app.api.routes import plan_execution_comparisons as routes
from app.main import app
from app.models.entities import Sport, User
from app.planning_contracts.comparison_evidence import PROTECTED_EXTERNAL_IDS
from app.planning_contracts.contract_checks import validate_contract
from app.services import plan_execution_comparison_read as service

BASE = "/api/v1/planning/plan-execution-comparisons"


def good(env, **kwargs):
    env.add(source="POLAR", raw=polar_target(duration=30000))
    return env.add_execution(**kwargs)


def get(env, row, *, full=False, **kwargs):
    params = {"include_bundle": "true", "include_source": "true"} if full else {}
    params.update(kwargs.pop("params", {}))
    return env.client.get(f"/api/v1/sessions/{row.id}/plan-execution-comparison", params=params, **kwargs)


def test_detail_real_app_is_replayable_and_select_only(executions):
    env = executions; row = good(env)
    original_raw = deepcopy(row.raw_data)
    response = get(env, row, full=True)
    assert response.status_code == 200, response.text
    value = response.json()
    assert service.verify_comparison_read(value)
    assert validate_contract(value["comparison"])
    assert validate_contract(value["integration_bundle"])
    assert row.raw_data == original_raw and row.planned_workout_id is None
    assert response.headers["cache-control"] == "no-store"
    assert env.sql and set(env.sql) == {"SELECT"}


def test_default_view_omits_large_replay_material_and_bundle(executions):
    env = executions; row = good(env)
    value = get(env, row).json()
    assert value["source_execution_read"] is None and value["integration_bundle"] is None
    assert not value["include_source"] and not value["include_bundle"]
    assert not value["source_replay_material_included"]
    assert validate_contract(value["comparison"])
    with pytest.raises(service.ComparisonReadError, match="SOURCE_READ_REQUIRED"):
        service.verify_comparison_read(value)


@pytest.mark.parametrize("bundle,source", [(True, False), (False, True), (True, True)])
def test_optional_views_are_independent(executions, bundle, source):
    env = executions; row = good(env)
    v = get(env, row, params={"include_bundle": str(bundle).lower(), "include_source": str(source).lower()}).json()
    assert (v["integration_bundle"] is not None) is bundle
    assert (v["source_execution_read"] is not None) is source
    if source:
        assert service.verify_comparison_read(v)


def test_observed_rows_not_promotion_to_verified_adherence(executions):
    env = executions; row = good(env)
    v = get(env, row, full=True).json()
    assert v["comparison"]["coverage"] == "COMPLETE"
    assert {r["alignment_status"] for r in v["comparison"]["rows"]} == {"MATCHED_CANDIDATE", "UNRESOLVED"}
    for r in v["comparison"]["rows"]:
        for assessment in r["target_adherence"]:
            assert assessment["status"] == "NOT_EVALUABLE"
            assert assessment["inside_s"] is None and assessment["observed_s"] is None
    assert v["numeric_output_authorized"] is False and v["historical_plan_content_verified"] is False
    assert v["actual_phase_alignment_verified"] is False and v["capability_update_performed"] is False


def test_missing_and_foreign_sessions_are_same_404(executions):
    env = executions; row = env.add_execution(owner=OTHER)
    foreign = get(env, row)
    missing = env.client.get(f"/api/v1/sessions/{uuid4()}/plan-execution-comparison")
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()
    assert set(env.sql) == {"SELECT"}


def test_foreign_linked_plan_not_exposed(executions):
    env = executions; p = env.add(owner=OTHER, source="POLAR", raw=polar_target())
    row = env.add_execution(plan=p)
    response = get(env, row, full=True)
    assert response.status_code == 409
    assert response.json()["detail"]["blocking_reason"] == "COMPARISON_NO_USABLE_OWNED_PLAN"
    assert str(p.id) not in response.text


def test_no_plan_withheld_instead_of_synthetic_plan(executions):
    env = executions; row = env.add_execution()
    response = get(env, row)
    assert response.status_code == 409 and response.headers["cache-control"] == "no-store"
    detail = response.json()["detail"]
    assert detail["comparison"] is None and detail["integration_bundle"] is None
    assert detail["blocking_reason"] == "COMPARISON_NO_USABLE_OWNED_PLAN"
    assert set(env.sql) == {"SELECT"}


def test_duplicate_owned_target_does_not_choose_one(executions):
    env = executions
    env.add(source="POLAR", raw=polar_target()); env.add(source="POLAR", raw=polar_target())
    row = env.add_execution()
    assert get(env, row).json()["detail"]["blocking_reason"] == "COMPARISON_NO_USABLE_OWNED_PLAN"


@pytest.mark.parametrize("external", sorted(PROTECTED_EXTERNAL_IDS))
def test_protected_session_guard_precedes_numerical_execution_read(executions, monkeypatch, external):
    env = executions; row = env.add_execution(sid=external.upper())
    async def forbidden(*args, **kwargs):
        pytest.fail("protected session reached execution adapter")
    monkeypatch.setattr(service, "read_owned_execution", forbidden)
    response = get(env, row, full=True)
    assert response.status_code == 409
    assert response.json()["detail"]["blocking_reason"] == "COMPARISON_PROTECTED_SESSION_METADATA_ONLY"
    assert "source_snapshot" not in response.text and "metrics" not in response.text
    assert set(env.sql) == {"SELECT"}


def test_unresolved_sport_encoding_withheld(executions):
    env = executions
    raw = polar_target(); raw["exercise"][0]["sportId"] = "15"
    env.add(source="POLAR", raw=raw)
    row = env.add_execution(); row.sport = Sport.STRENGTH; env.session.commit(); env.sql.clear()
    response = get(env, row)
    assert response.status_code == 409
    assert response.json()["detail"]["blocking_reason"] == "COMPARISON_PLAN_EXECUTION_SPORT_MISMATCH"


def test_manual_transition_unresolved_not_missed(executions):
    env = executions; env.add(source="POLAR", raw=polar_target(change="MANUAL", duration=30000))
    row = env.add_execution()
    value = get(env, row, full=True).json()
    assert {r["alignment_status"] for r in value["comparison"]["rows"]} == {"UNRESOLVED"}
    assert service.verify_comparison_read(value)


def test_missing_native_samples_not_zero_or_failed(executions):
    env = executions; env.add(source="POLAR", raw=polar_target(duration=30000))
    from test_executed_workout_adapter import source
    raw = source()["raw_data"]; raw.pop("exerciseSamples")
    row = env.add_execution(raw=raw)
    v = get(env, row, full=True).json()
    assert {r["alignment_status"] for r in v["comparison"]["rows"]} == {"UNRESOLVED"}
    assert v["descriptive_comparison"]["occurrences"][0]["matching_status"] == "UNASSIGNED"
    assert service.verify_comparison_read(v)


def test_list_counts_withheld_and_owner_scoped_pagination(executions):
    env = executions; first = good(env, day=0)
    protected = env.add_execution(sid=sorted(PROTECTED_EXTERNAL_IDS)[0], day=1)
    last = env.add_execution(day=2); foreign = env.add_execution(owner=OTHER, day=-1)
    p = env.client.get(BASE + "?limit=2").json()
    assert p["returned_count"] == 2 and p["converted_count"] == 1 and p["withheld_count"] == 1
    assert {i["session_id"] for i in p["items"]} == {str(first.id), str(protected.id)}
    assert p["has_more"] and p["next_offset"] == 2
    p2 = env.client.get(BASE + "?limit=2&offset=2").json()
    assert p2["returned_count"] == 1 and p2["items"][0]["session_id"] == str(last.id)
    assert not p2["has_more"] and p2["next_offset"] is None
    assert set(env.sql) == {"SELECT"}


def test_byte_truncation_offsets_use_returned_not_requested_count(executions, monkeypatch):
    env = executions; good(env, day=0); env.add_execution(day=1); env.add_execution(day=2)
    first = env.client.get(BASE + "?limit=1").json()
    monkeypatch.setattr(routes, "MAX_PAGE_BYTES", len(routes.canonical_bytes(first)) + 100)
    p = env.client.get(BASE + "?limit=3").json()
    assert p["returned_count"] == 1 and p["next_offset"] == 1 and p["has_more"]
    assert len(routes.canonical_bytes(p)) <= routes.MAX_PAGE_BYTES
    p2 = env.client.get(BASE + "?limit=3&offset=1").json()
    assert p2["items"][0]["session_id"] != p["items"][0]["session_id"]


def test_first_item_exceeding_page_budget_reports_413(executions, monkeypatch):
    env = executions; good(env)
    monkeypatch.setattr(routes, "MAX_PAGE_BYTES", 100)
    assert env.client.get(BASE).status_code == 413


def test_detail_response_budget_is_enforced(executions, monkeypatch):
    env = executions; row = good(env)
    monkeypatch.setattr(service, "MAX_RESPONSE_BYTES", 100)
    response = get(env, row)
    assert response.status_code == 413 and response.json()["detail"]["blocking_reason"] == "COMPARISON_RESPONSE_BYTE_LIMIT"


@pytest.mark.parametrize("query", ["athlete_id=other", "captured_at=2026-01-01", "plan_id=invented",
    "include_source=true&include_source=false", "include_bundle=bad", "limit=0", "limit=11", "offset=-1", "offset=100001"])
def test_list_rejects_unknown_authority_or_resource_overrides(executions, query):
    assert executions.client.get(BASE + "?" + query).status_code == 422


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_new_routes_expose_no_write_methods(executions, method):
    env = executions; row = env.add_execution()
    assert getattr(env.client, method)(BASE).status_code == 405
    assert getattr(env.client, method)(f"/api/v1/sessions/{row.id}/plan-execution-comparison").status_code == 405


def test_pending_objects_are_not_flushed(executions):
    env = executions; row = good(env)
    pending = User(id=uuid4(), email="pending-comparison@example.test", created_at=NOW)
    env.session.add(pending)
    assert get(env, row).status_code == 200
    assert pending in env.session.new and set(env.sql) == {"SELECT"}
    env.session.expunge(pending)


def test_missing_configured_owner_does_not_create_one(executions):
    env = executions; env.session.get(User, OWNER).email = "renamed@example.test"; env.session.commit(); env.sql.clear()
    assert env.client.get(BASE).status_code == 404
    assert set(env.sql) == {"SELECT"}


def test_broken_execution_source_is_explicit_withheld_item(executions):
    env = executions; good(env, day=0)
    row = env.add_execution(raw={"startTime": "2026-08-01T11:00:00"}, day=1)
    p = env.client.get(BASE + "?limit=2").json()
    assert p["withheld_count"] == 1
    item = next(i for i in p["items"] if i["session_id"] == str(row.id))
    assert item["upstream_reason"] == "EXECUTION_NAIVE_PROVIDER_CLOCK_REQUIRES_DECLARED_OFFSET"


def test_capabilities_and_old_routes_remain_available(executions):
    env = executions; cap = env.client.get("/api/v1/planning/contracts/capabilities").json()
    assert cap["plan_execution_comparison_available"]
    assert cap["plan_execution_comparison_api_version"] == service.API_RULES_VERSION
    paths = app.openapi()["paths"]
    assert "/api/v1/sessions/{session_id}/plan-execution-comparison" in paths
    assert "/api/v1/planning/plan-execution-comparisons" in paths
    assert "/api/v1/sessions/{session_id}/executed-workout" in paths
    assert "/api/v1/workouts/{workout_id}/plan-contract" in paths
    assert env.client.get("/api/v1/pft/capabilities").status_code == 200


def test_saved_response_replay_catches_contract_tampering(executions):
    env = executions; row = good(env)
    value = get(env, row, full=True).json()
    value["comparison"]["rows"][0]["alignment_status"] = "MISSED"
    with pytest.raises(service.ComparisonReadError, match="FULL_SOURCE_REPLAY_DIFFERS"):
        service.verify_comparison_read(value)
