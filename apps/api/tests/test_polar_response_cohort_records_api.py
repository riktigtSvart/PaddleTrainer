import asyncio
import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from test_environment_replay_persistence import scientific_state
from test_response_cohort_persistence import (
    archive_state,
    counts,
    archived as _archived,
    chronological as _chronological,
    environment as _environment,
    sources as _sources,
)

from app.api.routes import polar_response_cohort_records as api
from app.api.routes import polar_response_cohort as assemble_api
from app.models import ResponseCohortMember, ResponseCohortRecord
from app.models.entities import ExternalConnection, User
from app.services.response_cohort_assembly import verify_cohort_index_integrity
from app.services.response_cohort_storage_contract import check_cohort_record_payload

archived, chronological, environment, sources = _archived, _chronological, _environment, _sources
BASE = "/api/v1/integrations/polar/response-cohorts"


@pytest.fixture
def bridge(archived, monkeypatch):
    env = archived
    email = env.db.session.scalar(select(User.email).where(User.id == env.user.id))
    env.db.session.rollback()
    env.settings = SimpleNamespace(demo_user_email=email)
    monkeypatch.setattr(api, "get_settings", lambda: env.settings)
    monkeypatch.setattr(assemble_api, "get_settings", lambda: env.settings)
    env.execute = AsyncMock(wraps=env.db.execute)
    monkeypatch.setattr(env.db, "execute", env.execute)
    app = FastAPI()
    app.include_router(api.router, prefix="/api/v1")
    app.include_router(assemble_api.router, prefix="/api/v1")

    async def dependency():
        try:
            yield env.db
        finally:
            await env.db.rollback()

    app.dependency_overrides[api.get_db] = dependency
    with TestClient(app) as client:
        yield env, client


def capture(bridge, body=None):
    env, client = bridge
    return client.post(BASE + "/capture", json=env.request if body is None else body)


def saved_id(bridge):
    result = capture(bridge)
    assert result.status_code == 200, result.text
    return result.json()["record_id"]


def uri(record_id):
    return BASE + "/records/" + str(record_id)


def failure(response, status, code):
    assert response.status_code == status, response.text
    value = response.json()
    assert value["blocking_reasons"] == [code]
    assert value["record_id"] is value["record_hash"] is value["cohort_index_hash"] is None
    assert value["record_payload"] is value["cohort_index"] is None
    assert value["stored_member_count"] == 0
    for key in (
        "source_evidence_verified",
        "current_source_evidence_verified",
        "current_index_matches_archived_record",
        "training_authorized",
        "numeric_output_authorized",
        "round_trip_verified",
        "commit_acknowledged",
        "chronological_cohort_order_verified",
        "chronological_split_verified",
        "split_assignment_persisted",
        "dataset_split_assignment_persisted",
        "fixed_hr_shift_applied",
    ):
        assert value[key] is False
    assert value["physiological_lag_ms"] is None
    assert "private-credential" not in response.text and "secret-token" not in response.text
    assert response.headers["cache-control"] == "no-store"
    return value


@pytest.mark.parametrize("single", [False, True], ids=["three-session-split", "single-unassigned"])
def test_actual_api_capture_archived_read_repeat_and_current_revalidation(bridge, single):
    env, client = bridge
    if single:
        env.request = {**env.request, "members": env.request["members"][:1], "split_manifest": None}
    before = scientific_state(env)
    env.db.session.rollback()
    first, repeat = capture(bridge), capture(bridge)
    assert first.status_code == repeat.status_code == 200, (first.text, repeat.text)
    a, b = first.json(), repeat.json()
    assert a["status"] == "CREATED" and b["status"] == "ALREADY_PRESENT"
    assert a["record_id"] == b["record_id"] and a["created_at"] == b["created_at"]
    assert a["record_hash"] == b["record_hash"]
    n = len(env.request["members"])
    assert counts(env) == (1, n)
    assert a["cohort_storage_rows_written"] == 1 + n and b["cohort_storage_rows_written"] == 0
    assert a["current_source_evidence_verified"] is a["round_trip_verified"] is True
    assert a["commit_acknowledged"] is a["database_record_persisted"] is True
    assert env.provider.await_count == 4 * n  # Each repeat actually calls Polar.
    calls = env.provider.await_count
    default = client.get(uri(a["record_id"]))
    full = client.get(uri(a["record_id"]) + "?include_record=true")
    repeated = client.get(uri(a["record_id"]) + "?include_record=true")
    assert default.status_code == full.status_code == repeated.status_code == 200
    assert full.content == repeated.content
    assert (
        default.json()["representation"] == "SUMMARY" and default.json()["record_payload"] is None
    )
    loaded = full.json()
    assert loaded["representation"] == "FULL_RECORD"
    assert loaded["source_evidence_verified"] is loaded["current_source_evidence_verified"] is False
    assert loaded["owner_authorization_verified"] is loaded["member_links_verified"] is True
    payload = loaded["record_payload"]
    check_cohort_record_payload(payload)
    assert payload["record_hash"] == a["record_hash"]
    assert payload["cohort_index"]["source_evidence_verified"] is True
    assert payload["cohort_index"]["chronological_split_verified"] is not single
    assert env.provider.await_count == calls
    state = archive_state(env)
    verified = client.post(uri(a["record_id"]) + "/revalidate?include_index=true", json={})
    assert verified.status_code == 200, verified.text
    live = verified.json()
    assert (
        live["current_source_evidence_verified"]
        is live["current_index_matches_archived_record"]
        is True
    )
    assert live["cohort_index"] == payload["cohort_index"]
    assert verify_cohort_index_integrity(live["cohort_index"])
    assert live["storage_writes"] == live["scientific_evidence_writes"] == 0
    assert live["chronological_split_verified"] is not single
    assert live["training_authorized"] is live["numeric_output_authorized"] is False
    assert live["fixed_hr_shift_applied"] is False and live["physiological_lag_ms"] is None
    assert env.provider.await_count == calls + 2 * n
    assert archive_state(env) == state and scientific_state(env) == before
    assert all(
        r.headers["cache-control"] == "no-store" for r in (first, repeat, default, full, verified)
    )


def test_revalidation_default_summary_and_forbidden_request_do_not_mutate_archive(bridge):
    env, client = bridge
    record_id = saved_id(bridge)
    before = archive_state(env)
    result = client.post(uri(record_id) + "/revalidate", json={})
    assert result.status_code == 200, result.text
    assert result.json()["representation"] == "SUMMARY" and result.json()["cohort_index"] is None
    calls, executions = env.provider.await_count, env.execute.await_count
    rejected = client.post(uri(record_id) + "/revalidate", json={"source_evidence_verified": True})
    failure(rejected, 422, "COHORT_REQUEST_INVALID")
    assert env.provider.await_count == calls and env.execute.await_count == executions
    assert archive_state(env) == before


def test_wrong_pin_and_wrong_owner_preserve_prior_record_without_partial_capture(bridge):
    env, client = bridge
    record_id = saved_id(bridge)
    before = archive_state(env)
    for kind, status, upstream in (
        ("pin", 409, "COHORT_SNAPSHOT_PIN_MISMATCH"),
        ("owner", 403, "COHORT_OWNER_MISMATCH"),
    ):
        wrong = deepcopy(env.request)
        if kind == "pin":
            wrong["members"][0]["expected_snapshot_hash"] = "f" * 64
        else:
            wrong["split_manifest"] = None
            for member in wrong["members"]:
                member["athlete_id"] = str(UUID(int=882))
        env.provider.reset_mock()
        result = failure(capture(bridge, wrong), status, "COHORT_CURRENT_SOURCE_CHECK_FAILED")
        assert result["upstream_reason"] == upstream
        assert result["storage_attempted"] is False and result["cohort_storage_rows_written"] == 0
        assert env.provider.await_count == 0
        assert archive_state(env) == before
    assert client.get(uri(record_id)).status_code == 200


@pytest.mark.parametrize("operation", ["read", "revalidate"])
def test_missing_and_foreign_record_ids_are_indistinguishable(bridge, operation):
    env, client = bridge
    record_id = saved_id(bridge)
    env.settings.demo_user_email = "other-cohort-owner@example.test"
    env.provider.reset_mock()

    def call(value):
        return (
            client.get(uri(value))
            if operation == "read"
            else client.post(uri(value) + "/revalidate", json={})
        )

    foreign, missing = call(record_id), call(uuid4())
    failure(foreign, 404, "COHORT_RECORD_NOT_FOUND_OR_NOT_OWNED")
    assert missing.status_code == foreign.status_code and missing.content == foreign.content
    assert env.provider.await_count == 0 and counts(env) == (1, 3)


def test_changed_current_source_is_not_hidden_by_historical_readback(bridge):
    env, client = bridge
    record_id = saved_id(bridge)
    before = archive_state(env)
    env.route_sources[-1]["exercises"][0]["durationMillis"] += 1
    calls = env.provider.await_count
    read = client.get(uri(record_id) + "?include_record=true")
    assert read.status_code == 200 and read.json()["current_source_evidence_verified"] is False
    assert read.json()["record_payload"]["cohort_index"]["source_evidence_verified"] is True
    assert env.provider.await_count == calls
    live = failure(
        client.post(uri(record_id) + "/revalidate", json={}),
        409,
        "COHORT_CURRENT_SOURCE_CHECK_FAILED",
    )
    assert live["upstream_reason"] == "COHORT_MEMBER_EVIDENCE_VERIFICATION_FAILED"
    failure(capture(bridge), 409, "COHORT_CURRENT_SOURCE_CHECK_FAILED")
    assert archive_state(env) == before and counts(env) == (1, 3)


def test_archive_read_does_not_need_current_polar_connection(bridge):
    env, client = bridge
    record_id = saved_id(bridge)
    env.db.session.execute(delete(ExternalConnection))
    env.db.session.commit()
    env.provider.reset_mock()
    assert client.get(uri(record_id) + "?include_record=true").status_code == 200
    live = failure(
        client.post(uri(record_id) + "/revalidate", json={}),
        404,
        "COHORT_CURRENT_SOURCE_CHECK_FAILED",
    )
    assert live["upstream_reason"] == "COHORT_POLAR_CONNECTION_REQUIRED"
    assert env.provider.await_count == 0 and counts(env) == (1, 3)


@pytest.mark.parametrize("kind", ["payload", "column", "missing-member", "retarget-member"])
@pytest.mark.parametrize("operation", ["read", "revalidate"])
def test_corrupt_archive_is_withheld_without_repair_or_provider_call(bridge, kind, operation):
    env, client = bridge
    record_id = saved_id(bridge)
    row = env.db.session.get(ResponseCohortRecord, UUID(record_id))
    if kind == "payload":
        obj = deepcopy(row.record_json)
        obj["record_hash"] = "f" * 64
        row.record_json = obj
        code = "COHORT_STORED_PAYLOAD_INVALID"
    elif kind == "column":
        row.cohort_index_hash = "f" * 64
        code = "COHORT_STORED_ROW_BINDING_INVALID"
    else:
        member = env.db.session.get(ResponseCohortMember, (UUID(record_id), 0))
        if kind == "missing-member":
            env.db.session.delete(member)
        else:
            member.session_external_id = "wrong-retarget"
        code = "COHORT_STORED_MEMBERSHIP_INVALID"
    env.db.session.commit()
    before = archive_state(env)
    calls = env.provider.await_count
    result = (
        client.get(uri(record_id))
        if operation == "read"
        else client.post(uri(record_id) + "/revalidate", json={})
    )
    failure(result, 409, code)
    assert archive_state(env) == before and env.provider.await_count == calls


@pytest.mark.parametrize(
    "case", ["authority", "owner-selector", "candidate", "member-extra", "date"]
)
def test_invalid_capture_is_redacted_before_any_db_or_provider(bridge, case):
    env, _ = bridge
    body = deepcopy(env.request)
    if case == "authority":
        body["training_authorized"] = "private-credential"
    elif case == "owner-selector":
        body["private-credential"] = str(uuid4())
    elif case == "candidate":
        body = {"record_schema_version": "0.1", "record_payload": "private-credential"}
    elif case == "member-extra":
        body["members"][0]["private-credential"] = "private-credential"
    else:
        body["members"][0]["route_date"] = "2026-02-30"
    failure(capture(bridge, body), 422, "COHORT_REQUEST_INVALID")
    assert env.execute.await_count == env.provider.await_count == 0


@pytest.mark.parametrize(
    "raw,status",
    [
        (b"", 400),
        (b"{", 400),
        (b"[]", 422),
        (b"null", 422),
        (b'{"a":1,"a":2}', 400),
        (b'{"a":NaN}', 400),
        (b'{"a":1e999}', 400),
        (b"\xff", 400),
        (b"[" * 20000 + b"]" * 20000, 400),
    ],
    ids=[
        "empty",
        "incomplete",
        "array",
        "null",
        "duplicate",
        "nan",
        "overflow",
        "encoding",
        "deep",
    ],
)
def test_json_is_bounded_and_strict_before_dependencies(bridge, raw, status):
    env, client = bridge
    code = "COHORT_REQUEST_INVALID" if status == 422 else "COHORT_JSON_INVALID"
    failure(
        client.post(BASE + "/capture", content=raw, headers={"Content-Type": "application/json"}),
        status,
        code,
    )
    assert env.execute.await_count == env.provider.await_count == 0


@pytest.mark.parametrize("chunked", [False, True])
def test_capture_stream_limit_without_content_length(bridge, chunked):
    env, client = bridge
    raw = b" " * (api.MAX_REQUEST_BYTES + 1)
    content = iter([raw[:100], raw[100:]]) if chunked else raw
    failure(
        client.post(
            BASE + "/capture", content=content, headers={"Content-Type": "application/json"}
        ),
        413,
        "COHORT_REQUEST_SIZE_LIMIT",
    )
    assert env.execute.await_count == env.provider.await_count == 0


@pytest.mark.parametrize(
    "path,method,query",
    [
        ("/capture", "post", "?include_record=true"),
        ("/records/{id}", "get", "?user_id=private-credential"),
        ("/records/{id}", "get", "?include_record=yes"),
        ("/records/{id}", "get", "?include_record=true&include_record=false"),
        ("/records/{id}/revalidate", "post", "?include_record=true"),
        ("/records/{id}/revalidate", "post", "?include_index=1"),
    ],
    ids=[
        "capture-query",
        "owner-query",
        "read-bool",
        "duplicate-query",
        "revalidate-query",
        "revalidate-bool",
    ],
)
def test_unknown_query_and_nonliteral_flags_rejected_before_db(bridge, path, method, query):
    env, client = bridge
    url = BASE + path.replace("{id}", str(uuid4())) + query
    response = (
        client.get(url)
        if method == "get"
        else client.post(url, json=env.request if path == "/capture" else {})
    )
    assert response.status_code == 422
    assert "private-credential" not in response.text
    assert env.execute.await_count == env.provider.await_count == 0


def test_missing_owner_invalid_path_media_type_and_read_body(bridge):
    env, client = bridge
    failure(client.get(uri("private-credential")), 422, "COHORT_REQUEST_INVALID")
    failure(client.request("GET", uri(uuid4()), content=b"{}"), 422, "COHORT_READ_BODY_FORBIDDEN")
    failure(client.post(BASE + "/capture", content=b"{}"), 415, "COHORT_JSON_CONTENT_TYPE_REQUIRED")
    assert env.execute.await_count == 0
    env.settings.demo_user_email = "missing-owner@example.test"
    failure(capture(bridge), 404, "COHORT_CONFIGURED_OWNER_REQUIRED")
    assert env.provider.await_count == 0 and counts(env) == (0, 0)


def test_windows_bom_request_and_execution_limit(bridge):
    env, client = bridge
    body = deepcopy(env.request)
    body["split_manifest"] = None
    body["members"] = [
        dict(
            body["members"][0], session_external_id=f"session-{i}", replay_snapshot_id=str(uuid4())
        )
        for i in range(21)
    ]
    failure(capture(bridge, body), 422, "COHORT_MEMBER_EXECUTION_LIMIT")
    assert env.execute.await_count == 0
    result = client.post(
        BASE + "/capture",
        content=b"\xef\xbb\xbf" + json.dumps(env.request).encode(),
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    assert result.status_code == 200, result.text


def test_provider_failure_withholds_capture_without_partial_rows(bridge):
    env, _ = bridge
    env.provider.side_effect = httpx.ConnectError("secret-token https://private-credential")
    value = failure(capture(bridge), 502, "COHORT_CURRENT_SOURCE_CHECK_FAILED")
    assert value["upstream_reason"] == "COHORT_POLAR_SOURCE_REQUEST_FAILED"
    assert value["storage_outcome"] == "NOT_ATTEMPTED" and counts(env) == (0, 0)


def test_actual_partial_write_rollback_and_unknown_storage_outcome(bridge, monkeypatch):
    env, _ = bridge
    original = env.db.flush

    async def failed_flush():
        await original()
        if env.db.session.scalar(select(ResponseCohortMember.record_id).limit(1)) is not None:
            raise SQLAlchemyError("secret-token postgres://private-credential")

    monkeypatch.setattr(env.db, "flush", failed_flush)
    value = failure(capture(bridge), 503, "COHORT_STORAGE_DEPENDENCY_FAILURE")
    assert value["storage_attempted"] is True and value["storage_outcome"] == "NOT_CONFIRMED"
    assert value["database_record_persisted"] is value["cohort_storage_rows_written"] is None
    assert counts(env) == (0, 0)


def test_active_caller_transaction_is_not_committed_or_rolled_back_by_capture(bridge):
    env, client = bridge
    env.db.session.execute(select(User.id))
    call = asyncio.run(
        api.capture_cohort_record(api.ResponseCohortManifest.model_validate(env.request), env.db)
    )
    failure(
        httpx.Response(call.status_code, content=call.body, headers=call.headers),
        422,
        "COHORT_STORAGE_CLEAN_SESSION_REQUIRED",
    )
    assert env.db.in_transaction()
    env.db.session.rollback()


def test_new_route_registration_and_openapi_contracts():
    from app.api.router import api_router

    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")
    schema = app.openapi()
    capture_op = schema["paths"][BASE + "/capture"]["post"]
    assert capture_op["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/ResponseCohortManifest"
    )
    revalidate_op = schema["paths"][BASE + "/records/{record_id}/revalidate"]["post"]
    ref = revalidate_op["requestBody"]["content"]["application/json"]["schema"]["$ref"].split("/")[
        -1
    ]
    assert schema["components"]["schemas"][ref]["additionalProperties"] is False
    assert schema["components"]["schemas"][ref]["properties"] == {}
    read_op = schema["paths"][BASE + "/records/{record_id}"]["get"]
    flag = next(p for p in read_op["parameters"] if p["name"] == "include_record")
    assert flag["schema"]["enum"] == ["true", "false"]
    assert "delete" not in schema["paths"][BASE + "/records/{record_id}"]


@pytest.mark.parametrize(
    "kind", ["valid-different-index", "corrupt-current-index", "deleted-archive"]
)
def test_revalidation_never_promotes_changed_current_index_or_changed_archive(
    bridge, monkeypatch, kind
):
    from app.services.environment_replay_snapshot import canonical_hash

    env, client = bridge
    record_id = saved_id(bridge)
    before = archive_state(env)
    actual = api.assemble_response_cohort

    async def changed(*args, **kwargs):
        index = await actual(*args, **kwargs)
        assert index["source_evidence_verified"] is True
        if kind == "valid-different-index":
            index["manifest_id"] += "-new-assembly-result"
            index["cohort_index_hash"] = canonical_hash(
                {k: v for k, v in index.items() if k != "cohort_index_hash"}
            )
            assert verify_cohort_index_integrity(index)
        elif kind == "corrupt-current-index":
            index["cohort_index_hash"] = "f" * 64
        else:
            env.db.session.execute(
                delete(ResponseCohortRecord).where(ResponseCohortRecord.id == UUID(record_id))
            )
            env.db.session.commit()
        return index

    monkeypatch.setattr(api, "assemble_response_cohort", changed)
    code, status = {
        "valid-different-index": ("COHORT_ARCHIVE_CURRENT_INDEX_CHANGED", 409),
        "corrupt-current-index": ("COHORT_API_INDEX_INTEGRITY_FAILED", 503),
        "deleted-archive": ("COHORT_ARCHIVE_CHANGED_DURING_REVALIDATION", 409),
    }[kind]
    failure(client.post(uri(record_id) + "/revalidate", json={}), status, code)
    if kind == "deleted-archive":
        assert counts(env) == (0, 0)
    else:
        assert archive_state(env) == before
