import asyncio
import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import httpx
import pytest
from cryptography.fernet import InvalidToken
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from test_environment_replay_persistence import scientific_state
from test_response_cohort_chronology import chronological as _chronological
from test_response_cohort_chronology import environment as _environment
from test_response_cohort_chronology import refresh_header_snapshot
from test_response_cohort_chronology import sources as _sources

from app.api.routes import polar_response_cohort as api
from app.models.entities import ExternalConnection, User
from app.models.environment_replay_snapshot import EnvironmentReplaySnapshot
from app.models.hr_timebase_snapshot import HeartRateTimebaseSnapshot
from app.services import response_cohort_assembly as assembly

chronological, environment, sources = _chronological, _environment, _sources
URI = "/api/v1/integrations/polar/response-cohorts/assemble"


@pytest.fixture
def bridge(chronological, monkeypatch):
    env = chronological
    monkeypatch.setattr(
        api, "get_settings", lambda: SimpleNamespace(demo_user_email=env.user.email)
    )
    env.execute = AsyncMock(wraps=env.db.execute)
    monkeypatch.setattr(env.db, "execute", env.execute)
    app = FastAPI()
    app.include_router(api.router, prefix="/api/v1")

    async def dependency():
        yield env.db

    app.dependency_overrides[api.get_db] = dependency
    with TestClient(app) as client:
        yield env, client


def post(bridge, body=None, *, query=""):
    env, client = bridge
    return client.post(URI + query, json=env.request if body is None else body)


def failed(response, status, code):
    assert response.status_code == status, response.text
    obj = response.json()
    assert obj["blocking_reasons"] == [code]
    assert obj["source_evidence_verified"] is False
    assert obj["verified_member_count"] == 0
    assert obj["cohort_index"] is obj["cohort_index_hash"] is obj["totals"] is None
    assert obj["members"] == []
    assert obj["temporal_audit"] is None
    for flag in (
        "training_authorized",
        "numeric_output_authorized",
        "chronological_cohort_order_verified",
        "chronological_split_verified",
        "split_assignment_persisted",
        "pre_exercise_prediction_authorized",
        "causal_prediction_authorized",
    ):
        assert obj[flag] is False
    assert obj["science_storage_writes"] == obj["environmental_provider_calls"] == 0
    assert response.headers["cache-control"] == "no-store"
    assert "secret-token" not in response.text
    return obj


def test_api_matches_actual_c_assembly_and_preserves_science(bridge):
    env, _ = bridge
    state, commits = scientific_state(env), env.db.commit_count
    snapshots = list(env.db.session.scalars(select(EnvironmentReplaySnapshot.id)))
    golden = asyncio.run(
        assembly.assemble_response_cohort(
            env.db,
            env.request,
            user_id=env.user.id,
            verify_chronology=True,
        )
    )
    env.provider.reset_mock()
    default = post(bridge)
    full = post(bridge, query="?include_index=true")
    repeat = post(bridge, query="?include_index=true")
    assert default.status_code == full.status_code == repeat.status_code == 200
    assert repeat.content == full.content
    a, b = default.json(), full.json()
    assert a["representation"] == "SUMMARY" and a["cohort_index"] is None
    assert b["representation"] == "FULL_INDEX" and b["cohort_index"] == golden
    assert b["summary"] == a["summary"]
    assert b["summary"]["cohort_index_hash"] == golden["cohort_index_hash"]
    assert assembly.verify_cohort_index_integrity(b["cohort_index"])
    assert not assembly.verify_cohort_index_integrity(a["summary"])
    assert "members" not in a["summary"]
    assert a["summary"]["chronological_cohort_order_verified"] is True
    assert a["summary"]["chronological_split_verified"] is True
    assert a["summary"]["training_authorized"] is False
    assert a["summary"]["independence_between_sessions_verified"] is False
    assert a["summary"]["policy"]["fixed_hr_shift_applied"] is False
    assert a["summary"]["policy"]["physiological_lag_ms"] is None
    assert a["summary"]["temporal_audit"]["ordered_member_canonical_indices"] == [0, 2, 1]
    assert env.provider.await_count == 18  # 3 calls * 3 members * 2 features.
    assert scientific_state(env) == state and env.db.commit_count == commits
    assert list(env.db.session.scalars(select(EnvironmentReplaySnapshot.id))) == snapshots
    assert default.headers["cache-control"] == "no-store"
    assert len(default.content) < len(full.content) / 2
    assert "unused-private-token" not in full.text


def test_single_session_is_success_without_relative_chronology(bridge):
    env, _ = bridge
    body = deepcopy(env.request)
    body["members"] = body["members"][:1]
    body["split_manifest"] = None
    response = post(bridge, body, query="?include_index=true")
    assert response.status_code == 200
    index = response.json()["cohort_index"]
    assert index["source_evidence_verified"] is True
    assert index["temporal_audit"]["status"] == "SINGLE_SESSION_TIME_BOUNDS_ONLY"
    assert index["chronological_cohort_order_verified"] is False
    assert index["chronological_split_verified"] is False
    assert index["training_authorized"] is False


def test_windows_utf8_bom_and_explicit_false_summary(bridge):
    env, client = bridge
    response = client.post(
        URI + "?include_index=false",
        content=b"\xef\xbb\xbf" + json.dumps(env.request).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["representation"] == "SUMMARY"
    assert response.json()["cohort_index"] is None


@pytest.mark.parametrize("case", ["incomplete_split", "reversed_split", "unsupported_interval"])
def test_temporal_limitations_do_not_discard_verified_source(bridge, case):
    env, _ = bridge
    body = deepcopy(env.request)
    if case == "incomplete_split":
        body["split_manifest"] = None
    elif case == "reversed_split":
        body["split_manifest"]["assignments"][0]["split"] = "TEST"
        body["split_manifest"]["assignments"][2]["split"] = "TRAIN"
    else:
        for source in (env.route_sources[1], env.sample_sources[1]):
            source.pop("stopTime")
        refresh_header_snapshot(env, 1)
        body = env.request
    response = post(bridge, body)
    assert response.status_code == 200, response.text
    summary = response.json()["summary"]
    assert summary["source_evidence_verified"] is True
    assert summary["verified_member_count"] == 3
    assert summary["chronological_split_verified"] is False
    assert summary["training_authorized"] is False
    assert summary["temporal_audit"]["split_blocking_reasons"]


@pytest.mark.parametrize(
    "case",
    [
        "different_owner",
        "missing_snapshot",
        "foreign_snapshot",
        "pin",
        "replay_pin",
        "environment_pin",
    ],
)
def test_actual_owner_and_pin_failures_before_provider_or_without_partial_index(bridge, case):
    env, _ = bridge
    body = deepcopy(env.request)
    member = body["members"][-1]
    if case == "different_owner":
        for value in body["members"]:
            value["athlete_id"] = (
                str(uuid4()) if value is body["members"][0] else body["members"][0]["athlete_id"]
            )
        body["split_manifest"] = None
        status, code = 403, "COHORT_OWNER_MISMATCH"
    elif case == "missing_snapshot":
        member["replay_snapshot_id"] = str(uuid4())
        status, code = 404, "COHORT_SNAPSHOT_NOT_FOUND_OR_NOT_OWNED"
    elif case == "foreign_snapshot":
        row = env.db.session.get(EnvironmentReplaySnapshot, UUID(member["replay_snapshot_id"]))
        row.user_id = uuid4()
        env.db.session.commit()
        status, code = 404, "COHORT_SNAPSHOT_NOT_FOUND_OR_NOT_OWNED"
    elif case == "pin":
        member["expected_snapshot_hash"] = "f" * 64
        status, code = 409, "COHORT_SNAPSHOT_PIN_MISMATCH"
    elif case == "environment_pin":
        member["expected_evidence_hash"] = "e" * 64
        status, code = 409, "COHORT_ENVIRONMENT_PIN_MISMATCH"
    else:
        member["expected_unassigned_replay_package_hash"] = "c" * 64
        status, code = 409, "COHORT_REPLAY_PACKAGE_PIN_MISMATCH"
    state, commits = scientific_state(env), env.db.commit_count
    result = failed(post(bridge, body, query="?include_index=true"), status, code)
    assert scientific_state(env) == state and env.db.commit_count == commits
    if case != "replay_pin":
        assert env.token.await_count == env.provider.await_count == 0
    else:
        assert env.provider.await_count == 6  # Prior successes are withheld too.
        assert result["failed_member_canonical_index"] == 2


def test_missing_and_foreign_snapshot_are_indistinguishable(bridge):
    env, _ = bridge
    body = deepcopy(env.request)
    member = body["members"][1]
    original = member["replay_snapshot_id"]
    member["replay_snapshot_id"] = str(uuid4())
    absent = post(bridge, body)
    member["replay_snapshot_id"] = original
    row = env.db.session.get(EnvironmentReplaySnapshot, UUID(original))
    row.user_id = uuid4()
    env.db.session.commit()
    foreign = post(bridge, body)
    assert absent.status_code == foreign.status_code == 404
    assert absent.content == foreign.content


@pytest.mark.parametrize(
    "case,status,code",
    [
        ("owner", 404, "COHORT_CONFIGURED_OWNER_REQUIRED"),
        ("connection", 404, "COHORT_POLAR_CONNECTION_REQUIRED"),
        ("scope", 403, "COHORT_POLAR_SCOPE_REQUIRED"),
        ("refresh_scope", 403, "COHORT_POLAR_SCOPE_REQUIRED"),
    ],
)
def test_existing_configured_owner_and_connection_required_without_creation(
    bridge, monkeypatch, case, status, code
):
    env, _ = bridge
    connection = env.db.session.scalar(select(ExternalConnection))
    if case == "owner":
        monkeypatch.setattr(
            api, "get_settings", lambda: SimpleNamespace(demo_user_email="absent@example.test")
        )
    elif case == "connection":
        env.db.session.delete(connection)
        env.db.session.commit()
    elif case == "scope":
        connection.scopes = []
        env.db.session.commit()
    else:

        async def refresh(*args):
            connection.scopes = []
            return "secret-token"

        env.token.side_effect = refresh
    users = list(env.db.session.scalars(select(User.id)))
    commits = env.db.commit_count
    failed(post(bridge), status, code)
    assert env.provider.await_count == 0
    assert list(env.db.session.scalars(select(User.id))) == users
    assert env.db.commit_count == commits


@pytest.mark.parametrize(
    "case,status,code,upstream",
    [
        (
            "changed_source",
            409,
            "COHORT_MEMBER_EVIDENCE_VERIFICATION_FAILED",
            "REPLAY_CURRENT_POLAR_SOURCE_CHANGED",
        ),
        (
            "changed_proof",
            409,
            "COHORT_MEMBER_EVIDENCE_VERIFICATION_FAILED",
            "REPLAY_HR_PROOF_STATE_CHANGED",
        ),
        (
            "corrupt_snapshot",
            409,
            "COHORT_MEMBER_EVIDENCE_VERIFICATION_FAILED",
            "REPLAY_STORED_SNAPSHOT_BINDING_FAILED",
        ),
        ("provider", 502, "COHORT_POLAR_SOURCE_REQUEST_FAILED", None),
        ("invalid_source", 502, "COHORT_CURRENT_SOURCE_PAYLOAD_INVALID", None),
        ("missing_source", 404, "COHORT_CURRENT_SOURCE_SESSION_MISSING", None),
        ("ambiguous_source", 409, "COHORT_CURRENT_SOURCE_SESSION_AMBIGUOUS", None),
    ],
)
def test_actual_source_and_storage_failures_do_not_publish_prefix(
    bridge, case, status, code, upstream
):
    env, _ = bridge
    if case == "changed_source":
        env.route_sources[-1]["exercises"][0]["durationMillis"] += 1
    elif case == "changed_proof":
        env.db.session.execute(delete(HeartRateTimebaseSnapshot))
        env.db.session.commit()
    elif case == "corrupt_snapshot":
        row = env.db.session.get(EnvironmentReplaySnapshot, UUID(env.saved[-1]["snapshot_id"]))
        value = deepcopy(row.snapshot_json)
        value["session_external_id"] = "corrupted-session"
        row.snapshot_json = value
        env.db.session.commit()
    elif case == "provider":
        env.provider.side_effect = httpx.ConnectError("secret-token https://private/owner")
    elif case == "invalid_source":
        env.provider.side_effect = None
        env.provider.return_value = {"unexpected": "private"}
    elif case == "missing_source":
        env.route_sources.pop()
    else:
        env.route_sources.append(deepcopy(env.route_sources[-1]))
    state, commits = scientific_state(env), env.db.commit_count
    result = failed(post(bridge, query="?include_index=true"), status, code)
    assert result["upstream_reason"] == upstream
    assert scientific_state(env) == state and env.db.commit_count == commits
    assert "https://private" not in json.dumps(result)


@pytest.mark.parametrize(
    "case",
    [
        "authority",
        "owner_selector",
        "index_as_input",
        "invalid_date",
        "different_type",
        "extra_member_field",
    ],
)
def test_invalid_body_rejected_before_owner_and_provider_with_redacted_values(bridge, case):
    env, _ = bridge
    body = deepcopy(env.request)
    marker = "private-credential-value"
    if case == "authority":
        body["source_evidence_verified"] = True
        body["training_authorized"] = marker
    elif case == "owner_selector":
        body[marker] = "foreign-owner"
    elif case == "index_as_input":
        body = {
            "status": "SOURCE_VERIFIED_COHORT_INDEX_WITH_LIMITATIONS",
            "source_evidence_verified": True,
            "private": marker,
        }
    elif case == "invalid_date":
        body["members"][0]["route_date"] = "2026-02-30"
    elif case == "different_type":
        body["members"][0]["expected_snapshot_hash"] = {"private": marker}
    else:
        body["members"][0][marker] = marker
    result = failed(post(bridge, body), 422, "COHORT_REQUEST_INVALID")
    assert marker not in json.dumps(result)
    assert env.execute.await_count == env.token.await_count == env.provider.await_count == 0


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"{",
        b"[]",
        b"null",
        b'{"a":1,"a":2}',
        b'{"a":NaN}',
        b'{"a":Infinity}',
        b'{"a":1e999}',
        b"\xff",
        b"[" * 20000 + b"]" * 20000,
    ],
    ids=[
        "empty",
        "incomplete",
        "array",
        "null",
        "duplicate",
        "nan",
        "infinity",
        "overflow",
        "encoding",
        "deep",
    ],
)
def test_malformed_or_duplicate_json_rejected_before_db(bridge, raw):
    env, client = bridge
    response = client.post(URI, content=raw, headers={"content-type": "application/json"})
    status, code = (
        (422, "COHORT_REQUEST_INVALID") if raw in (b"[]", b"null") else (400, "COHORT_JSON_INVALID")
    )
    failed(response, status, code)
    assert env.execute.await_count == env.provider.await_count == 0


@pytest.mark.parametrize(
    "query",
    [
        "?include_index=yes",
        "?include_index=1",
        "?include_index=TRUE",
        "?include_index=true&include_index=false",
        "?user_id=foreign",
        "?verify_chronology=false",
    ],
)
def test_only_explicit_boolean_and_single_known_query_supported(bridge, query):
    env, _ = bridge
    response = post(bridge, query=query)
    assert response.status_code == 422
    assert env.execute.await_count == env.provider.await_count == 0


@pytest.mark.parametrize("chunked", [False, True])
def test_body_byte_limit_including_stream_without_content_length(bridge, chunked):
    env, client = bridge
    raw = b" " * (api.MAX_REQUEST_BYTES + 1)
    content = iter([raw[: len(raw) // 2], raw[len(raw) // 2 :]]) if chunked else raw
    response = client.post(URI, content=content, headers={"content-type": "application/json"})
    failed(response, 413, "COHORT_REQUEST_SIZE_LIMIT")
    assert env.execute.await_count == env.provider.await_count == 0


def test_media_type_and_member_execution_limit(bridge):
    env, client = bridge
    failed(client.post(URI, content="{}"), 415, "COHORT_JSON_CONTENT_TYPE_REQUIRED")
    body = deepcopy(env.request)
    body["split_manifest"] = None
    body["members"] = [
        dict(
            body["members"][0], session_external_id=f"session-{i}", replay_snapshot_id=str(uuid4())
        )
        for i in range(21)
    ]
    failed(post(bridge, body), 422, "COHORT_MEMBER_EXECUTION_LIMIT")
    assert env.execute.await_count == env.provider.await_count == 0


@pytest.mark.parametrize("code,status", list(api.FAILURE_HTTP_STATUS.items()))
def test_fixed_service_error_http_translation(bridge, monkeypatch, code, status):
    result = {
        "source_evidence_verified": False,
        "blocking_reasons": [code],
        "failed_member_canonical_index": 1,
        "upstream_reason": "secret-token",
    }
    call = AsyncMock(return_value=result)
    monkeypatch.setattr(api, "assemble_response_cohort", call)
    obj = failed(post(bridge), status, code)
    assert obj["upstream_reason"] is None
    assert obj["failed_member_canonical_index"] == 1
    assert call.await_args.kwargs["verify_chronology"] is True


@pytest.mark.parametrize(
    "stage", ["owner", "credential", "assembly", "unknown_code", "corrupt_return"]
)
def test_dependency_failures_and_unknown_errors_never_echo_details(bridge, monkeypatch, stage):
    env, _ = bridge
    if stage == "owner":
        env.execute.side_effect = SQLAlchemyError("secret-token postgres://private/owner")
    elif stage == "credential":
        env.token.side_effect = InvalidToken("secret-token")
    elif stage == "assembly":
        monkeypatch.setattr(
            api, "assemble_response_cohort", AsyncMock(side_effect=RuntimeError("secret-token"))
        )
    elif stage == "unknown_code":
        monkeypatch.setattr(
            api,
            "assemble_response_cohort",
            AsyncMock(
                return_value={
                    "source_evidence_verified": False,
                    "blocking_reasons": ["secret-token"],
                }
            ),
        )
    else:
        monkeypatch.setattr(
            api,
            "assemble_response_cohort",
            AsyncMock(return_value={"source_evidence_verified": True, "status": "fake"}),
        )
    code = (
        "COHORT_API_INDEX_INTEGRITY_FAILED"
        if stage == "corrupt_return"
        else "COHORT_API_DEPENDENCY_FAILURE"
    )
    failed(post(bridge), 503, code)


def test_router_registration_and_openapi_manifest_contract():
    from app.api.router import api_router

    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")
    schema = app.openapi()
    operation = schema["paths"][URI]["post"]
    assert operation["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/ResponseCohortManifest"
    )
    assert (
        schema["components"]["schemas"]["ResponseCohortManifest"]["additionalProperties"] is False
    )
    param = next(p for p in operation["parameters"] if p["name"] == "include_index")
    assert param["schema"]["enum"] == ["true", "false"]
