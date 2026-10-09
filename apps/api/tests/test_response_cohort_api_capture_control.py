import asyncio
import importlib.util
import json
from contextlib import asynccontextmanager
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy import text
from test_polar_response_cohort_records_api import (
    bridge as _bridge,
    archived as _archived,
    chronological as _chronological,
    environment as _environment,
    sources as _sources,
)
from test_response_cohort_persistence import archive_state, counts

from app.services.response_cohort_assembly import assemble_response_cohort

spec = importlib.util.spec_from_file_location(
    "cohort_capture_control",
    Path(__file__).resolve().parents[3] / "tools/check_response_cohort_api_capture.py",
)
control = importlib.util.module_from_spec(spec)
spec.loader.exec_module(control)

bridge, archived, chronological, environment, sources = (
    _bridge,
    _archived,
    _chronological,
    _environment,
    _sources,
)


@pytest.fixture
def live(bridge, tmp_path, monkeypatch):
    env, client = bridge
    index = asyncio.run(
        assemble_response_cohort(env.db, env.request, user_id=env.user.id, verify_chronology=True)
    )
    env.db.session.rollback()
    request, reference = tmp_path / "request.json", tmp_path / "index.json"
    request.write_text(json.dumps(env.request), encoding="utf-8")
    reference.write_text(json.dumps(index), encoding="utf-8")
    with env.engine.begin() as db:
        db.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        db.execute(text("INSERT INTO alembic_version VALUES ('e4f7a92c1836')"))

    class Connection:
        async def execute(self, statement):
            return connection.execute(statement)

    class Engine:
        @asynccontextmanager
        async def connect(self):
            nonlocal connection
            with env.engine.connect() as connection:
                yield Connection()

        async def dispose(self):
            pass

    connection = None
    monkeypatch.setattr(control, "get_settings", lambda: SimpleNamespace(database_url="fixture"))
    monkeypatch.setattr(control, "create_async_engine", lambda *args, **kwargs: Engine())

    def actual_http(url, payload=None, *, method="POST"):
        response = client.request(method, url, json=payload if method == "POST" else None)
        return response.status_code, response.content, response.json()

    monkeypatch.setattr(control, "request_json", actual_http)
    return SimpleNamespace(
        env=env,
        request=request,
        reference=reference,
        index=index,
        output=tmp_path / "control",
        base="http://127.0.0.1:8000/api/v1/integrations/polar",
    )


def test_entire_control_uses_actual_api_and_sql_counts_and_can_repeat_without_new_rows(live):
    state = archive_state(live.env)
    first = control.run(live.request, live.reference, live.output, live.base)
    assert first["FirstSave"] == "CREATED" and first["RepeatSave"] == "ALREADY_PRESENT"
    assert first["RecordCountsBefore"] == 0 and first["RecordCountsAfter"] == 1
    assert first["MemberCountsBefore"] == 0 and first["MemberCountsAfter"] == 3
    assert first["PriorHRProofRowsPreserved"] is first["PriorScienceTableCountsPreserved"] is True
    assert first["ArchivedReadCurrentSourceProof"] is False
    assert first["ExplicitRevalidationCurrentSourceProof"] is True
    assert first["LiveForeignRecordOwnershipTestPerformed"] is False
    # The chronological split is verified, while model authority remains false.
    assert first["TrainingAuthorized"] is False and first["ChronologicalSplitVerified"] is True
    assert counts(live.env) == (1, 3)
    second = control.run(live.request, live.reference, live.output.with_name("repeat"), live.base)
    assert second["FirstSave"] == "ALREADY_PRESENT" and second["RecordId"] == first["RecordId"]
    assert second["RecordCountsBefore"] == second["RecordCountsAfter"] == 1
    assert counts(live.env) == (1, 3)
    assert archive_state(live.env) != state
    saved = json.loads((live.output / "live_summary.json").read_text())
    assert saved == first


@pytest.mark.parametrize("kind", ["capture-commitment", "revalidation-writes"])
def test_failed_postcapture_control_retains_archive_and_never_publishes_false_success(
    live, monkeypatch, kind
):
    actual = control.request_json

    def changed(url, payload=None, *, method="POST"):
        status, raw, value = actual(url, payload, method=method)
        if kind == "capture-commitment" and url.endswith("/capture"):
            value["cohort_index_hash"] = "f" * 64
        elif kind == "revalidation-writes" and "/revalidate?" in url:
            value["scientific_evidence_writes"] = 1
        return status, json.dumps(value).encode(), value

    monkeypatch.setattr(control, "request_json", changed)
    reason = (
        "CAPTURE_COMMITMENTS_OR_MEMBER_COUNT_FAILED"
        if kind == "capture-commitment"
        else "REVALIDATION_SCIENTIFIC_BOUNDARY_CHANGED"
    )
    with pytest.raises(control.CaptureControlError, match=reason):
        control.run(live.request, live.reference, live.output, live.base)
    assert counts(live.env) == (1, 3)
    assert not (live.output / "live_summary.json").exists()


def test_current_index_difference_stops_before_any_capture_without_updating_pins(live):
    live.env.route_sources[-1]["exercises"][0]["durationMillis"] += 1
    with pytest.raises(control.CaptureControlError, match="PREFLIGHT_CURRENT_INDEX_HTTP_409"):
        control.run(live.request, live.reference, live.output, live.base)
    assert counts(live.env) == (0, 0)
    assert not (live.output / "capture_first.json").exists()


@pytest.mark.parametrize(
    "case", ["bad-index", "bad-binding", "duplicate-json", "foreign-url", "existing-output"]
)
def test_invalid_local_inputs_reject_before_any_api_capture_or_db_write(live, monkeypatch, case):
    call = Mock(wraps=control.request_json)
    monkeypatch.setattr(control, "request_json", call)
    base = live.base
    if case == "bad-index":
        obj = deepcopy(live.index)
        obj["cohort_index_hash"] = "f" * 64
        live.reference.write_text(json.dumps(obj))
    elif case == "bad-binding":
        obj = json.loads(live.request.read_text())
        obj["manifest_id"] += "-different"
        live.request.write_text(json.dumps(obj))
    elif case == "duplicate-json":
        live.request.write_text('{"schema_version":"0.1","schema_version":"0.1"}')
    elif case == "foreign-url":
        base = "https://private-credential.example.test/api"
    else:
        live.output.mkdir()
    with pytest.raises((ValueError, OSError)):
        control.run(live.request, live.reference, live.output, base)
    assert call.call_count == 0 and counts(live.env) == (0, 0)


def test_storage_head_mismatch_stops_before_api_calls(live, monkeypatch):
    with live.env.engine.begin() as db:
        db.execute(text("UPDATE alembic_version SET version_num='d83b9c61f204'"))
    call = Mock(wraps=control.request_json)
    monkeypatch.setattr(control, "request_json", call)
    with pytest.raises(control.CaptureControlError, match="E2_DATABASE_HEAD_REQUIRED"):
        control.run(live.request, live.reference, live.output, live.base)
    assert call.call_count == 0 and counts(live.env) == (0, 0)


def test_full_d_response_is_supported_without_altering_local_bytes(live):
    # This is the exact D wrapper used in the user's earlier live control.
    value = {
        "schema_version": "0.1",
        "representation": "FULL_INDEX",
        "cohort_index_hash_scope": "COMPLETE_INDEX_EXCLUDING_OWN_HASH_NOT_API_SUMMARY",
        "summary": {"cohort_index_hash": live.index["cohort_index_hash"]},
        "cohort_index": live.index,
    }
    raw = b"\xef\xbb\xbf" + json.dumps(value).encode()
    live.reference.write_bytes(raw)
    result = control.run(live.request, live.reference, live.output, live.base)
    assert result["OriginalInputBytesPreserved"] is True
    assert live.reference.read_bytes() == raw


def test_control_cli_redacts_dependency_failure_and_does_not_remove_archives(
    live, monkeypatch, capsys
):
    monkeypatch.setattr(
        control,
        "storage_state",
        Mock(side_effect=RuntimeError("secret-token postgres://private-credential")),
    )
    result = control.main(
        [
            "--request",
            str(live.request),
            "--c-index",
            str(live.reference),
            "--output-dir",
            str(live.output),
        ]
    )
    assert result == 1
    value = json.loads(capsys.readouterr().err)
    assert value["Reason"] == "DEPENDENCY_OR_INPUT_FAILURE"
    assert value["AutomaticArchiveRemovalPerformed"] is False
    assert "secret-token" not in json.dumps(value)
    assert counts(live.env) == (0, 0)
