import importlib.util
import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from test_response_cohort_storage_contract import chronological as _chronological
from test_response_cohort_storage_contract import completed as _completed
from test_response_cohort_storage_contract import environment as _environment
from test_response_cohort_storage_contract import sources as _sources

from app.services.response_cohort_storage_contract import build_cohort_record_payload

completed, chronological, environment, sources = _completed, _chronological, _environment, _sources
ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def cli():
    spec = importlib.util.spec_from_file_location(
        "cohort_storage_cli", ROOT / "tools/check_response_cohort_storage.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def local_files(completed, tmp_path):
    env, index = completed
    manifest, full = tmp_path / "request.json", tmp_path / "index.json"
    manifest.write_text(json.dumps(env.request), encoding="utf-8-sig")
    full.write_text(json.dumps(index), encoding="utf-8-sig")
    return env, index, manifest, full


def assert_local(result):
    assert result["source_evidence_verified"] is False
    assert result["owner_authorization_verified"] is False
    assert result["database_record_persisted"] is False
    assert result["training_authorized"] is False
    assert result["storage_writes"] == 0


@pytest.mark.parametrize("wrapped", [False, True])
def test_prepare_and_repeated_check_preserve_input_and_index(
    cli, local_files, tmp_path, capsys, wrapped
):
    env, index, manifest, full = local_files
    if wrapped:
        full.write_text(
            json.dumps(
                {
                    "schema_version": "0.1",
                    "representation": "FULL_INDEX",
                    "cohort_index_hash_scope": "COMPLETE_INDEX_EXCLUDING_OWN_HASH_NOT_API_SUMMARY",
                    "summary": {"cohort_index_hash": index["cohort_index_hash"]},
                    "cohort_index": index,
                }
            )
        )
    before = (manifest.read_bytes(), full.read_bytes())
    calls = env.provider.await_count
    output = tmp_path / "candidate.json"
    assert (
        cli.main(
            [
                "prepare",
                "--manifest",
                str(manifest),
                "--api-response" if wrapped else "--index",
                str(full),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    prepared = json.loads(capsys.readouterr().out)
    assert_local(prepared)
    assert prepared["local_candidate_written"] is True
    assert json.loads(output.read_text())["cohort_index"] == index
    assert cli.main(["check", str(output)]) == 0
    first = capsys.readouterr().out
    assert cli.main(["check", str(output)]) == 0
    assert capsys.readouterr().out == first
    assert_local(json.loads(first))
    assert (manifest.read_bytes(), full.read_bytes()) == before
    assert env.provider.await_count == calls


def test_offline_subprocess_has_no_database_engine_or_token_access(local_files, tmp_path):
    _, index, manifest, full = local_files
    env = {**os.environ, "PYTHONPATH": str(ROOT / "apps/api"), "DATABASE_URL": "not-a-database-url"}
    output = tmp_path / "candidate.json"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools/check_response_cohort_storage.py"),
            "prepare",
            "--manifest",
            str(manifest),
            "--index",
            str(full),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert_local(json.loads(result.stdout))
    assert json.loads(output.read_text())["cohort_index_hash"] == index["cohort_index_hash"]


@pytest.mark.parametrize(
    "case",
    [
        "summary",
        "withheld",
        "wrapped_without_option",
        "wrong_manifest",
        "tampered_record",
        "authority",
    ],
)
def test_rejected_inputs_never_publish_candidate_or_echo_private_values(
    cli, local_files, tmp_path, capsys, case
):
    env, index, manifest, full = local_files
    marker = "private-owner-and-token-value"
    args = [
        "prepare",
        "--manifest",
        str(manifest),
        "--index",
        str(full),
        "--output",
        str(tmp_path / "out.json"),
    ]
    if case == "summary":
        full.write_text(
            json.dumps(
                {
                    "schema_version": "0.1",
                    "representation": "SUMMARY",
                    "summary": {"cohort_index_hash": index["cohort_index_hash"]},
                    "cohort_index": None,
                }
            )
        )
        args[3] = "--api-response"
    elif case == "withheld":
        full.write_text(
            json.dumps({"status": "WITHHELD", "source_evidence_verified": False, "private": marker})
        )
    elif case == "wrapped_without_option":
        full.write_text(json.dumps({"representation": "FULL_INDEX", "cohort_index": index}))
    elif case == "wrong_manifest":
        request = deepcopy(env.request)
        request["manifest_id"] += "-other"
        manifest.write_text(json.dumps(request))
    else:
        payload = build_cohort_record_payload(env.request, index, owner_id=env.user.id)
        if case == "authority":
            payload[marker] = True
        else:
            payload["record_hash"] = "f" * 64
        full.write_text(json.dumps(payload))
        args = ["check", str(full)]
    assert cli.main(args) == 1
    raw = capsys.readouterr().out
    assert marker not in raw
    result = json.loads(raw)
    assert result["status"] == "REJECTED" and result["source_evidence_verified"] is False
    assert not (tmp_path / "out.json").exists()


def test_existing_output_is_never_overwritten(cli, local_files, tmp_path, capsys):
    _, _, manifest, full = local_files
    output = tmp_path / "existing.json"
    output.write_bytes(b"user-owned output")
    assert (
        cli.main(
            ["prepare", "--manifest", str(manifest), "--index", str(full), "--output", str(output)]
        )
        == 1
    )
    assert output.read_bytes() == b"user-owned output"
    assert json.loads(capsys.readouterr().out)["status"] == "REJECTED"


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"{",
        b'{"a":1,"a":2}',
        b'{"a":NaN}',
        b'{"a":1e999}',
        b"\xff",
        b"[" * 20000 + b"]" * 20000,
    ],
    # Pytest puts case IDs in PYTEST_CURRENT_TEST; keep them within Windows limits.
    ids=["empty", "truncated", "duplicate-keys", "nan", "overflow", "invalid-utf8", "deep-json"],
)
def test_bad_json_and_duplicate_keys_are_redacted(cli, tmp_path, capsys, raw):
    path = tmp_path / "bad.json"
    path.write_bytes(raw)
    assert cli.main(["check", str(path)]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["reason"] == "COHORT_RECORD_LOCAL_INPUT_OR_OUTPUT_INVALID"


def test_input_byte_limit_precedes_parsing(cli, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "MAX_RECORD_BYTES", 8)
    path = tmp_path / "large.json"
    path.write_bytes(b" " * 9)
    assert cli.main(["check", str(path)]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "REJECTED"
