import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_environment_replay_persistence import environment as _environment_fixture
from test_environment_replay_persistence import save, scientific_state
from test_response_dataset_split import manifest
from test_training_data_readiness_audit import sources as _sources_fixture

from app.api.routes import polar
from app.api.routes import polar_environment_replay as module
from app.integrations.polar.client import PolarAPIError
from app.models import EnvironmentReplaySnapshot, HeartRateTimebaseSnapshot
from app.models.entities import RouteEnvironmentSegment
from app.services.route_response_dataset import verify_route_response_dataset

environment = _environment_fixture
sources = _sources_fixture
BASE = "/api/v1/integrations/polar/sessions/session-1/response-dataset"
REAL_BUILD = polar._build_training_session_route_inspection


@pytest.fixture
def api(environment, monkeypatch):
    env = environment
    env.saved = asyncio.run(save(env))
    env.route_sources = [deepcopy(env.inputs["route_session"])]
    env.sample_sources = [deepcopy(env.inputs["sample_session"])]

    async def provider(*args, features):
        return {
            "trainingSessions": env.route_sources if features == ["routes"] else env.sample_sources
        }

    env.provider = AsyncMock(side_effect=provider)
    env.owner = AsyncMock(return_value=env.user)
    env.token = AsyncMock(return_value="private-test-token")
    env.environment_path = AsyncMock(
        side_effect=AssertionError("Replay must never refetch environmental providers")
    )
    monkeypatch.setattr(polar, "get_or_create_demo_user", env.owner)
    monkeypatch.setattr(polar, "get_valid_access_token", env.token)
    monkeypatch.setattr(polar, "_build_training_session_route_inspection", env.environment_path)
    monkeypatch.setattr(
        module, "PolarClient", lambda: SimpleNamespace(list_training_sessions=env.provider)
    )
    app = FastAPI()
    app.include_router(module.router, prefix="/api/v1")
    app.dependency_overrides[module.get_db] = lambda: env.db
    with TestClient(app) as client:
        env.client = client
        yield env


def post(env, body=None, **query):
    return env.client.post(
        BASE + "/replay",
        params={"route_date": "2026-09-30", **query},
        json=body
        if body is not None
        else {"replay_snapshot_id": env.saved["snapshot_id"], "include_payload": True},
    )


def test_database_verified_replay_is_deterministic_and_has_no_environment_calls_or_writes(api):
    before, commits = scientific_state(api), api.db.commit_count
    first, second = post(api), post(api)
    assert first.status_code == second.status_code == 200
    value = first.json()
    assert value == second.json() and verify_route_response_dataset(value)
    assert value["input_provenance"]["database_environment_replay_verified"] is True
    assert value["replay_evidence"]["snapshot_id"] == api.saved["snapshot_id"]
    assert (
        value["replay_evidence"]["environmental_provider_calls"]
        == value["replay_evidence"]["replay_storage_writes"]
        == 0
    )
    assert value["hr_slot_count"] == 4 and value["preparation_candidate_count"] == 2
    assert scientific_state(api) == before and api.db.commit_count == commits
    assert len(api.db.session.scalars(select(EnvironmentReplaySnapshot)).all()) == 1
    assert [call.kwargs["features"] for call in api.provider.await_args_list] == [
        ["routes"],
        ["samples"],
    ] * 2
    api.environment_path.assert_not_awaited()
    assert "private-test-token" not in first.text and "unused-private-token" not in first.text


def test_default_summary_keeps_pinned_full_hash_without_hr_sample_payload(api):
    full = post(api).json()
    summary = post(api, {"replay_snapshot_id": api.saved["snapshot_id"]}).json()
    assert summary["payload_included"] is False and summary["package_hash"] == full["package_hash"]
    assert "observations" not in summary and "samples" not in summary["hr_streams"][0]


@pytest.mark.parametrize("split", ["TRAIN", "VALIDATION", "TEST"])
def test_replay_split_is_whole_session_and_only_for_the_request(api, split):
    value = post(
        api,
        {
            "replay_snapshot_id": api.saved["snapshot_id"],
            "include_payload": True,
            "split_manifest": manifest(split, owner=str(api.user.id)),
        },
    ).json()
    assert value["split_assignment"]["split"] == split
    assert all(row["split"] == split for row in value["observations"])
    assert (
        value["training_authorized"] is value["split_assignment"]["assignment_persisted"] is False
    )
    assert post(api).json()["split_assignment"]["status"] == "UNASSIGNED"


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"replay_snapshot_id": "not-a-uuid"},
        {"replay_snapshot_id": 123},
        {"replay_snapshot_id": str(UUID(int=303)), "include_payload": "true"},
        {"replay_snapshot_id": str(UUID(int=303)), "database_environment_replay_verified": True},
        {"replay_snapshot_id": str(UUID(int=303)), "athlete_id": "another-owner"},
        {"replay_snapshot_id": str(UUID(int=303)), "physiological_lag_ms": 5000},
    ],
)
def test_invalid_replay_claims_are_rejected_before_owner_provider_or_database_changes(api, body):
    commits = api.db.commit_count
    assert post(api, body).status_code == 422
    api.provider.assert_not_awaited()
    api.owner.assert_not_awaited()
    assert api.db.commit_count == commits


def test_conflicting_session_splits_fail_before_provider(api):
    assignment = manifest(owner=str(api.user.id))
    assignment["assignments"].append(assignment["assignments"][0] | {"split": "TEST"})
    assert (
        post(
            api, {"replay_snapshot_id": api.saved["snapshot_id"], "split_manifest": assignment}
        ).status_code
        == 422
    )
    api.provider.assert_not_awaited()


@pytest.mark.parametrize("method", ["list", "replay"])
@pytest.mark.parametrize("state,status", [("missing", 404), ("scope", 403)])
def test_connection_and_scope_are_owner_bound_without_fallback(api, method, state, status):
    if state == "missing":
        api.db.session.delete(api.connection)
    else:
        api.connection.scopes = []
    api.db.session.commit()
    response = api.client.get(BASE + "/replay-snapshots") if method == "list" else post(api)
    assert response.status_code == status
    api.provider.assert_not_awaited()
    api.token.assert_not_awaited()


@pytest.mark.parametrize("which", ["unknown", "wrong_session", "wrong_owner"])
def test_unowned_or_unknown_capture_has_no_provider_calls(api, which):
    if which == "wrong_owner":
        row = api.db.session.scalar(select(EnvironmentReplaySnapshot))
        row.user_id = UUID(int=999)
        api.db.session.commit()
        response = post(api)
    elif which == "wrong_session":
        response = api.client.post(
            BASE.replace("session-1", "other-session") + "/replay",
            params={"route_date": "2026-09-30"},
            json={"replay_snapshot_id": api.saved["snapshot_id"]},
        )
    else:
        response = post(api, {"replay_snapshot_id": str(UUID(int=999))})
    assert response.status_code == 404
    api.provider.assert_not_awaited()
    api.token.assert_not_awaited()


@pytest.mark.parametrize("which", ["route", "samples", "proof", "evidence"])
def test_changed_source_or_proof_state_is_withheld_without_writes(api, which):
    if which == "route":
        api.route_sources[0]["modified"] = "changed"
    elif which == "samples":
        api.sample_sources[0]["exercises"][0]["samples"]["samples"][0]["values"][0] = 99
    elif which == "proof":
        row = api.db.session.scalar(select(HeartRateTimebaseSnapshot))
        row.snapshot_json = row.snapshot_json | {"snapshot_hash": "0" * 64}
        api.db.session.commit()
    else:
        api.db.session.scalar(select(RouteEnvironmentSegment)).gps_ground_speed_mps = 999.0
        api.db.session.commit()
    commits = api.db.commit_count
    response = post(api)
    assert response.status_code == 409 and "REPLAY_" in response.json()["detail"]
    assert api.db.commit_count == commits
    api.environment_path.assert_not_awaited()


@pytest.mark.parametrize("feature", ["routes", "samples"])
@pytest.mark.parametrize("count,status", [(0, 404), (2, 409)])
def test_missing_or_ambiguous_current_polar_source_never_matches_a_saved_capture(
    api, feature, count, status
):
    if feature == "routes":
        api.route_sources *= count
    else:
        api.sample_sources *= count
    assert post(api).status_code == status


@pytest.mark.parametrize(
    "error",
    [
        PolarAPIError("private-token-secret"),
        httpx.RequestError(
            "private-token-secret",
            request=httpx.Request("GET", "https://example.test/private-token-secret"),
        ),
    ],
)
def test_source_transport_failures_are_generic_502_without_secret_echo(api, error):
    api.provider.side_effect = error
    response = post(api)
    assert response.status_code == 502 and "private-token-secret" not in response.text


def test_list_is_bounded_local_metadata_and_does_not_refresh_tokens_or_providers(api):
    response = api.client.get(BASE + "/replay-snapshots")
    assert response.status_code == 200
    value = response.json()
    assert (
        value["total_count"] == 1
        and value["snapshots"][0]["snapshot_id"] == api.saved["snapshot_id"]
    )
    assert "snapshot_json" not in response.text and "samples" not in response.text
    api.provider.assert_not_awaited()
    api.token.assert_not_awaited()


def test_maximum_date_fails_before_provider(api):
    assert post(api, route_date="9999-12-31").status_code == 422
    api.provider.assert_not_awaited()


@pytest.mark.parametrize(
    "body",
    [
        {"athlete_id": "other"},
        {"training_authorized": True},
        {"snapshot_json": {}},
        {"physiological_lag_ms": 5000},
        {"include_payload": True},
    ],
)
def test_capture_cannot_accept_client_supplied_payload_or_authority(api, body):
    response = api.client.post(BASE + "/capture", params={"route_date": "2026-09-30"}, json=body)
    assert response.status_code == 422
    api.environment_path.assert_not_awaited()


def test_capture_is_an_explicit_targeted_write_handoff_using_server_inputs(api):
    api.environment_path.side_effect = None
    api.environment_path.return_value = {
        "route_sessions": [
            {
                "environment_replay_snapshot_persistence": api.saved,
                "environment_evidence_persistence": {"status": "ALREADY_CURRENT"},
                "response_dataset_contract": {"training_authorized": False},
            }
        ]
    }
    response = api.client.post(
        BASE + "/capture",
        params={
            "route_date": "2026-09-30",
            "weather_provider": "OPEN_METEO_HISTORICAL",
            "hydrology_provider": "OVF_VRAQUERY",
            "hydrology_station_registry_number": 1026,
        },
    )
    assert response.status_code == 200 and response.json()["persistence"] == api.saved
    kwargs = api.environment_path.await_args.kwargs
    assert kwargs["persist_environment_evidence"] is kwargs["capture_environment_replay"] is True
    assert kwargs["response_dataset_session_id"] == "session-1"
    assert kwargs["hydrology_station_registry_number"] == 1026
    assert "split_manifest" not in kwargs


@pytest.mark.parametrize(
    "payload", [None, {}, {"trainingSessions": None}, {"trainingSessions": "invalid"}]
)
def test_malformed_provider_payload_never_becomes_verified_replay(api, payload):
    api.provider.side_effect = None
    api.provider.return_value = payload
    assert post(api).status_code == 502


def test_explicit_pinned_capture_remains_stable_when_evidence_is_no_longer_current(api):
    from app.models.entities import RouteEnvironmentEvidenceSet

    before = post(api).json()
    api.db.session.scalar(select(RouteEnvironmentEvidenceSet)).is_current = False
    api.db.session.commit()
    assert post(api).json() == before


def test_actual_capture_pipeline_stores_full_server_projection_and_can_replay_it(api, monkeypatch):
    import json

    from test_environment_replay_persistence import legacy_tables

    # Controlled server-side scaffold, not a claim that live providers were probed.
    full = deepcopy(api.inputs["trusted_environment"])
    unavailable = {
        "status": "UNAVAILABLE",
        "available": False,
        "included": False,
        "applicable": True,
        "usable_for_downstream_environment_context": False,
        "trust_basis": [],
        "limitations": [],
    }
    for segment in full["routes"][0]["segments"]:
        segment["water_identity"] = deepcopy(unavailable)
        segment["hydrology"] = deepcopy(unavailable)
        segment["component_statuses"]["water_identity"] = "UNAVAILABLE"
        segment["component_statuses"]["hydrology"] = "UNAVAILABLE"
    expected = deepcopy(api.inputs["expected_response_input"])
    for row, component in zip(
        expected["routes"][0]["segments"], full["routes"][0]["segments"], strict=True
    ):
        row["environment_context"] = deepcopy(component)
    record = deepcopy(api.inputs["evidence_record"])
    record.pop("route_water_environment_identity_snapshot")
    record.pop("water_environment_identity_hash_binding")
    monkeypatch.setattr(polar, "_build_training_session_route_inspection", REAL_BUILD)
    monkeypatch.setattr(
        polar, "PolarClient", lambda: SimpleNamespace(list_training_sessions=api.provider)
    )
    monkeypatch.setattr(
        polar, "build_trusted_route_environment_context", lambda *a, **k: deepcopy(full)
    )
    monkeypatch.setattr(
        polar, "build_route_expected_response_input", lambda *a, **k: deepcopy(expected)
    )
    monkeypatch.setattr(
        polar, "build_route_environment_evidence_record", lambda *a, **k: deepcopy(record)
    )
    monkeypatch.setattr(
        polar,
        "load_and_bind_athlete_state_scientific_views",
        AsyncMock(return_value={"status": "NOT_BOUND", "athlete_state_context": None}),
    )

    async def persist_projection(db, *, evidence_set_id, snapshot):
        stored = legacy_tables["trusted_projection"]
        existing = api.db.session.execute(
            select(stored.c.id).where(
                stored.c.evidence_set_id == UUID(evidence_set_id),
                stored.c.projection_hash == snapshot["projection_hash"],
            )
        ).scalar_one_or_none()
        if existing is None:
            api.db.session.execute(
                stored.insert().values(
                    id=UUID(int=888),
                    evidence_set_id=UUID(evidence_set_id),
                    projection_hash=snapshot["projection_hash"],
                    snapshot_json=json.loads(json.dumps(snapshot)),
                )
            )
            api.db.session.commit()
        return {
            "status": "CREATED" if existing is None else "ALREADY_CURRENT",
            "snapshot_id": str(existing or UUID(int=888)),
            "round_trip_verified": True,
        }

    monkeypatch.setattr(
        polar, "persist_trusted_route_environment_context_snapshot", persist_projection
    )
    response = api.client.post(BASE + "/capture", params={"route_date": "2026-09-30"})
    assert response.status_code == 200, response.text
    result = response.json()["persistence"]
    assert result["round_trip_verified"] is True and result["status"] == "CREATED"
    replayed = post(api, {"replay_snapshot_id": result["snapshot_id"], "include_payload": True})
    assert replayed.status_code == 200, replayed.text
    assert replayed.json()["input_provenance"]["database_environment_replay_verified"] is True
    assert replayed.json()["training_authorized"] is False
