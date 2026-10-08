from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from sqlalchemy import select
from test_heart_rate_sample_validation import session as _session_fixture
from test_polar_hr_acquisition_api import environment as _base_environment_fixture
from test_polar_hr_acquisition_api import post as post_declaration
from test_polar_hr_diagnostics_api import evidence_rows, save_clock
from test_response_dataset_split import manifest
from test_route_input_diagnostics import environment as complete_environment
from test_training_data_readiness_audit import sources as _sources_fixture

from app.api.router import api_router
from app.api.routes import polar
from app.api.routes import polar_response_dataset as module
from app.integrations.polar.client import PolarAPIError
from app.models.hr_acquisition_declaration import HRAcquisitionDeclaration
from app.models.hr_timebase_snapshot import HeartRateTimebaseSnapshot
from app.services.heart_rate_sample_validation import build_training_session_heart_rate_validation
from app.services.route_response_dataset import verify_route_response_dataset

base_environment = _base_environment_fixture
sources = _sources_fixture
session = _session_fixture
BASE = "/api/v1/integrations/polar/sessions/hr-session/response-dataset/inspect"


@pytest.fixture
def environment(base_environment, sources, monkeypatch):
    env = base_environment
    HeartRateTimebaseSnapshot.__table__.create(env.db.session.get_bind())
    env.client.app.include_router(module.router, prefix="/api/v1")
    env.route_sessions = [deepcopy(env.source)]
    env.sample_sessions = [deepcopy(env.source)]

    async def provider(*args, features):
        return {
            "trainingSessions": env.route_sessions
            if features == ["routes"]
            else env.sample_sessions
        }

    env.dataset_provider = AsyncMock(side_effect=provider)
    monkeypatch.setattr(polar, "get_or_create_demo_user", env.user)
    monkeypatch.setattr(polar, "get_valid_access_token", env.token)
    monkeypatch.setattr(
        polar, "PolarClient", lambda: SimpleNamespace(list_training_sessions=env.dataset_provider)
    )
    monkeypatch.setattr(polar, "build_route_expected_response_input", lambda *a, **kw: sources[0])
    monkeypatch.setattr(
        polar,
        "build_trusted_route_environment_context",
        lambda *a, **kw: complete_environment(sources),
    )
    monkeypatch.setattr(
        polar,
        "load_and_bind_athlete_state_scientific_views",
        AsyncMock(return_value={"status": "NOT_BOUND", "athlete_state_context": None}),
    )
    env.writes = AsyncMock(side_effect=AssertionError("Dataset inspection must not write evidence"))
    monkeypatch.setattr(polar, "persist_route_environment_evidence", env.writes)
    return env


def post(env, body=None, **query):
    return env.client.post(BASE, params={"route_date": "2026-09-30", **query}, json=body)


def test_actual_api_preserves_database_proofs_and_returns_separate_source_bound_labels(environment):
    env = environment
    saved = save_clock(env)
    assert post_declaration(env).status_code == 200
    before = evidence_rows(env)
    commits = env.db.commit_count
    original = deepcopy((env.source, env.route_sessions, env.sample_sessions))
    raw = build_training_session_heart_rate_validation(
        env.source, expected_session_external_id="hr-session", sample_session_match_count=1
    )
    response = post(env, {"include_payload": True})
    assert response.status_code == 200
    value = response.json()
    assert verify_route_response_dataset(value)
    assert value["athlete_id"] == str(env.connection.user_id)
    assert value["session_external_id"] == "hr-session"
    assert value["observation_count"] == value["preparation_candidate_count"] == 2
    assert value["hr_slot_count"] == 4
    assert value["routes"][0]["hr_timebase"]["snapshot_id"] == saved["snapshot_id"]
    assert value["hr_streams"][0]["sample_grid_origin_us"] == 500000
    assert (
        value["hr_streams"][0]["samples"][0]["mapped_timestamp_utc"]
        == "2026-09-30T15:00:00.500000+00:00"
    )
    assert value["routes"][0]["hr_acquisition"]["source_binding_verified"] is True
    assert value["training_authorized"] is value["pre_exercise_prediction_authorized"] is False
    assert evidence_rows(env) == before and env.db.commit_count == commits
    assert (env.source, env.route_sessions, env.sample_sessions) == original
    assert (
        build_training_session_heart_rate_validation(
            env.source, expected_session_external_id="hr-session", sample_session_match_count=1
        )
        == raw
    )
    assert (
        "private-test-token" not in response.text and "unused-encrypted-token" not in response.text
    )
    env.writes.assert_not_awaited()


def test_default_summary_and_full_payload_have_identical_package_commitment(environment):
    save_clock(environment)
    summary = post(environment).json()
    full = post(environment, {"include_payload": True}).json()
    assert summary["package_hash"] == full["package_hash"]
    assert summary["payload_included"] is False and full["payload_included"] is True
    assert "observations" not in summary and "samples" not in summary["hr_streams"][0]
    assert len(summary["observation_preview"]) == 2
    assert environment.db.commit_count == 1


@pytest.mark.parametrize("split", ["TRAIN", "VALIDATION", "TEST"])
def test_explicit_split_applies_to_every_route_history_and_label_without_storage(
    environment, split
):
    env = environment
    save_clock(env)
    assignment = manifest(split, owner=str(env.connection.user_id), session="hr-session")
    before = evidence_rows(env)
    value = post(env, {"include_payload": True, "split_manifest": assignment}).json()
    assert value["split_assignment"]["status"] == "ASSIGNED"
    assert value["split_assignment"]["split"] == split
    assert all(
        row["split"] == split and row["session_group_key"] == value["session_group_key"]
        for row in value["observations"]
    )
    assert value["training_authorized"] is False
    assert value["split_assignment"]["assignment_persisted"] is False
    assert evidence_rows(env) == before and env.db.commit_count == 1


@pytest.mark.parametrize(
    "body",
    [
        {"include_payload": "true"},
        {"include_payload": 1},
        {"training_authorized": True},
        {"athlete_id": "other-owner"},
        {"physiological_lag_ms": 5000},
        {"split_manifest": manifest() | {"assignments": []}},
        {"split_manifest": manifest() | {"schema_version": "0.2"}},
    ],
)
def test_invalid_request_is_rejected_before_provider_or_storage(environment, body):
    response = post(environment, body)
    assert response.status_code == 422
    environment.dataset_provider.assert_not_awaited()
    assert environment.db.commit_count == 0
    environment.writes.assert_not_awaited()


def test_conflicting_session_splits_are_rejected_before_provider(environment):
    assignment = manifest(owner=str(environment.connection.user_id), session="hr-session")
    duplicate = deepcopy(assignment["assignments"][0])
    duplicate["split"] = "TRAIN"
    assignment["assignments"].append(duplicate)
    assert post(environment, {"split_manifest": assignment}).status_code == 422
    environment.dataset_provider.assert_not_awaited()


def test_fragment_assignment_is_rejected_before_provider(environment):
    assignment = manifest()
    assignment["assignments"][0]["order_index"] = 0
    assert post(environment, {"split_manifest": assignment}).status_code == 422
    environment.dataset_provider.assert_not_awaited()


def test_other_owner_manifest_does_not_change_connected_owner_or_assignment(environment):
    save_clock(environment)
    value = post(
        environment, {"split_manifest": manifest(owner="other", session="hr-session")}
    ).json()
    assert value["athlete_id"] == str(environment.connection.user_id)
    assert value["split_assignment"]["status"] == "UNASSIGNED"
    assert value["split_assignment"]["split"] is None
    assert "other" not in str(value["split_assignment"])


@pytest.mark.parametrize("scope_present,status", [(False, 403), (True, 404)])
def test_owned_connection_and_read_scope_are_required(environment, scope_present, status):
    if scope_present:
        environment.db.session.delete(environment.connection)
    else:
        environment.connection.scopes = []
    environment.db.session.commit()
    assert post(environment).status_code == status
    environment.dataset_provider.assert_not_awaited()


@pytest.mark.parametrize("route_count,status", [(0, 404), (2, 409)])
def test_missing_or_duplicate_target_session_is_rejected(environment, route_count, status):
    environment.route_sessions = [environment.source] * route_count
    assert post(environment).status_code == status
    environment.writes.assert_not_awaited()
    assert environment.db.commit_count == 0


def test_requested_session_filter_does_not_assemble_other_sessions_on_same_day(environment):
    other = deepcopy(environment.source)
    other["identifier"]["id"] = "another-session"
    environment.route_sessions.insert(0, other)
    environment.sample_sessions.insert(0, other)
    value = post(environment).json()
    assert value["session_external_id"] == "hr-session"
    assert "another-session" not in str(value)
    assert environment.db.commit_count == 0


def test_ambiguous_sample_source_withholds_package_without_touching_proofs(environment):
    save_clock(environment)
    before = evidence_rows(environment)
    environment.sample_sessions *= 2
    value = post(environment, {"include_payload": True}).json()
    assert value["status"] == "WITHHELD"
    assert value["hr_streams"] == value["observations"] == []
    assert "SAMPLE_SESSION_MISSING_OR_AMBIGUOUS" in value["blocking_reasons"]
    assert evidence_rows(environment) == before


def test_router_exposes_read_only_post_dataset_contract_and_does_not_add_put_or_delete():
    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")
    route = app.openapi()["paths"][
        "/api/v1/integrations/polar/sessions/{session_external_id}/response-dataset/inspect"
    ]
    assert set(route) == {"post"} and "requestBody" in route["post"]


def test_existing_get_inspection_returns_bounded_dataset_contract_without_storage(environment):
    save_clock(environment)
    environment.client.app.include_router(polar.router, prefix="/api/v1")
    response = environment.client.get(
        "/api/v1/integrations/polar/sessions/routes/inspect", params={"route_date": "2026-09-30"}
    )
    assert response.status_code == 200
    value = response.json()["route_sessions"][0]
    contract = value["response_dataset_contract"]
    assert contract["payload_included"] is False
    assert "observations" not in contract and "samples" not in contract["hr_streams"][0]
    assert (
        contract["input_provenance"]["audit_decision_hash"]
        == value["training_data_readiness_audit"]["decision_hash"]
    )
    assert environment.db.commit_count == 1
    assert len(environment.db.session.scalars(select(HeartRateTimebaseSnapshot)).all()) == 1
    assert environment.db.session.scalars(select(HRAcquisitionDeclaration)).all() == []


def test_provider_failure_returns_502_without_exposing_tokens_or_writing(environment):
    environment.dataset_provider.side_effect = PolarAPIError("private-test-token upstream failure")
    response = post(environment)
    assert response.status_code == 502
    assert response.json()["detail"] == "Dataset source request failed"
    assert "private-test-token" not in response.text
    assert environment.db.commit_count == 0
    environment.writes.assert_not_awaited()
