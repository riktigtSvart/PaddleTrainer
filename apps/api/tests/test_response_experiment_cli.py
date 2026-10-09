import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from test_response_experiment_contract import (
    archive as _archive,
    chronological as _chronological,
    completed as _completed,
    envelope,
    environment as _environment,
    sources as _sources,
)

from app.services.response_experiment_contract import build_response_experiment_manifest

archive, completed, chronological, environment, sources = (
    _archive,
    _completed,
    _chronological,
    _environment,
    _sources,
)
ROOT = Path(__file__).resolve().parents[3]
TOOL = ROOT / "tools/check_response_experiment.py"


@pytest.fixture
def cli():
    spec = importlib.util.spec_from_file_location("experiment_cli", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def archive_file(archive, tmp_path):
    path = tmp_path / "archive.json"
    path.write_text(json.dumps(envelope(archive)), encoding="utf-8-sig")
    return path


def test_prepare_check_control_are_offline_deterministic_and_preserve_inputs(
    cli, archive_file, tmp_path, capsys, completed, monkeypatch
):
    env, _ = completed
    original, calls = archive_file.read_bytes(), env.provider.await_count
    candidate = tmp_path / "plan.json"
    assert (
        cli.main(
            [
                "prepare",
                "--archive",
                str(archive_file),
                "--experiment-id",
                "local",
                "--output",
                str(candidate),
            ]
        )
        == 0
    )
    prepared = json.loads(capsys.readouterr().out)
    assert prepared["local_contract_file_written"] is True
    for _ in range(2):
        assert cli.main(["check", str(candidate), "--archive", str(archive_file)]) == 0
        raw = capsys.readouterr().out
        if _ == 0:
            first = raw
        else:
            assert raw == first
    output = tmp_path / "control"
    valid_control_hashes = []
    real_rejection = cli._expect_rejection

    def checked_rejection(payload, archive):
        body = {k: v for k, v in payload.items() if k != "experiment_manifest_hash"}
        raw = json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        valid_control_hashes.append(
            hashlib.sha256(raw).hexdigest() == payload["experiment_manifest_hash"]
        )
        return real_rejection(payload, archive)

    monkeypatch.setattr(cli, "_expect_rejection", checked_rejection)
    assert (
        cli.main(
            [
                "control",
                "--archive",
                str(archive_file),
                "--experiment-id",
                "local",
                "--output-dir",
                str(output),
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["Status"] == "EXPERIMENT_CONTRACT_LOCAL_CONTROL_VERIFIED"
    assert valid_control_hashes[0] is False
    assert all(valid_control_hashes[1:])
    assert result["Members"] == 3
    assert result["OriginalArchiveSHA256"] == hashlib.sha256(original).hexdigest()
    for name, value in result.items():
        if name.endswith("Rejected"):
            assert value is True
    assert result["CurrentSourceEvidenceVerified"] is result["SourceEvidenceVerified"] is False
    assert result["ModelInputArraysChecked"] is result["ModelFitPerformed"] is False
    assert result["DatabaseStorageWrites"] == result["PolarProviderCalls"] == 0
    assert candidate.read_bytes() == (output / "experiment_contract.json").read_bytes()
    assert candidate.read_bytes() == (output / "experiment_contract_repeat.json").read_bytes()
    assert archive_file.read_bytes() == original and env.provider.await_count == calls
    assert len(list(output.iterdir())) == result["LocalFilesWritten"] == 4


def test_fresh_process_with_invalid_database_url_still_completes_control(archive_file, tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "control",
            "--archive",
            str(archive_file),
            "--experiment-id",
            "no-database",
            "--output-dir",
            str(tmp_path / "process"),
        ],
        cwd=ROOT,
        env={
            **os.environ,
            "PYTHONPATH": str(ROOT / "apps/api"),
            "DATABASE_URL": "not-a-database-url",
            "DEMO_USER_EMAIL": "unavailable@invalid",
        },
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    summary = json.loads(result.stdout)
    assert summary["DatabaseStorageWrites"] == summary["PolarProviderCalls"] == 0
    assert summary["CurrentSourceEvidenceVerified"] is False
    assert "not-a-database-url" not in result.stdout + result.stderr


@pytest.mark.parametrize(
    "raw",
    [
        b'{"record_payload": {}, "record_payload": {}}',
        b'{"private": NaN}',
        b'{"private": Infinity}',
        b'{"private": -Infinity}',
        b"\xff",
        b'{"broken"',
        b"[" * 2000 + b"]" * 2000,
    ],
)
def test_malformed_or_ambiguous_archive_rejected_without_output(cli, tmp_path, capsys, raw):
    archive = tmp_path / "bad.json"
    archive.write_bytes(raw)
    output = tmp_path / "plan.json"
    assert (
        cli.main(
            [
                "prepare",
                "--archive",
                str(archive),
                "--experiment-id",
                "bad",
                "--output",
                str(output),
            ]
        )
        == 1
    )
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "REJECTED"
    assert not output.exists() and archive.read_bytes() == raw


def test_wrong_user_supplied_archive_pin_creates_no_control_directory(
    cli, archive_file, tmp_path, capsys
):
    output = tmp_path / "wrong-pin"
    assert (
        cli.main(
            [
                "control",
                "--archive",
                str(archive_file),
                "--experiment-id",
                "wrong",
                "--output-dir",
                str(output),
                "--expected-record-hash",
                "f" * 64,
            ]
        )
        == 1
    )
    result = json.loads(capsys.readouterr().out)
    assert result["reason"] == "EXPERIMENT_EXPECTED_ARCHIVE_PIN_MISMATCH"
    assert not output.exists()


def test_existing_output_file_or_control_directory_is_preserved(
    cli, archive_file, tmp_path, capsys
):
    output = tmp_path / "keep.json"
    output.write_bytes(b"existing")
    assert (
        cli.main(
            [
                "prepare",
                "--archive",
                str(archive_file),
                "--experiment-id",
                "keep",
                "--output",
                str(output),
            ]
        )
        == 1
    )
    assert json.loads(capsys.readouterr().out)["reason"] == "EXPERIMENT_OUTPUT_ALREADY_EXISTS"
    assert output.read_bytes() == b"existing"
    assert (
        cli.main(
            [
                "control",
                "--archive",
                str(archive_file),
                "--experiment-id",
                "keep",
                "--output-dir",
                str(tmp_path),
            ]
        )
        == 1
    )
    assert json.loads(capsys.readouterr().out)["reason"] == "EXPERIMENT_OUTPUT_ALREADY_EXISTS"
    assert output.read_bytes() == b"existing"


def test_bounded_archive_and_manifest_reads(
    cli, archive_file, archive, tmp_path, capsys, monkeypatch
):
    monkeypatch.setattr(cli, "MAX_ARCHIVE_FILE_BYTES", 8)
    assert (
        cli.main(
            [
                "prepare",
                "--archive",
                str(archive_file),
                "--experiment-id",
                "size",
                "--output",
                str(tmp_path / "unused.json"),
            ]
        )
        == 1
    )
    assert json.loads(capsys.readouterr().out)["reason"] == "EXPERIMENT_INPUT_FILE_SIZE_LIMIT"
    monkeypatch.setattr(cli, "MAX_ARCHIVE_FILE_BYTES", 3 * 1024 * 1024)
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps(build_response_experiment_manifest(archive, experiment_id="size")))
    monkeypatch.setattr(cli, "MAX_EXPERIMENT_BYTES", 8)
    assert cli.main(["check", str(plan), "--archive", str(archive_file)]) == 1
    assert json.loads(capsys.readouterr().out)["reason"] == "EXPERIMENT_INPUT_FILE_SIZE_LIMIT"


def test_validation_error_does_not_echo_private_identifiers(
    cli, archive_file, archive, tmp_path, capsys
):
    payload = build_response_experiment_manifest(archive, experiment_id="redaction")
    payload["private-session-token"] = "private-secret-value"
    candidate = tmp_path / "bad-plan.json"
    candidate.write_text(json.dumps(payload))
    assert cli.main(["check", str(candidate), "--archive", str(archive_file)]) == 1
    output = capsys.readouterr().out
    assert "private-session-token" not in output and "private-secret-value" not in output
    assert json.loads(output)["reason"] == "EXPERIMENT_SCHEMA_REJECTED"
