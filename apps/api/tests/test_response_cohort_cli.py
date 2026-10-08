import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from test_environment_replay_persistence import environment as _environment_fixture
from test_response_cohort_assembly import cohort as _cohort_fixture
from test_training_data_readiness_audit import sources as _sources_fixture

from app.services.environment_replay_snapshot import canonical_hash

environment = _environment_fixture
sources = _sources_fixture
cohort = _cohort_fixture
ROOT = Path(__file__).resolve().parents[3]
TOOL = ROOT / "tools/build_response_cohort_index.py"


@pytest.fixture
def cli():
    spec = importlib.util.spec_from_file_location("cohort_cli", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(*args):
    return subprocess.run(
        [sys.executable, str(TOOL), *map(str, args)],
        cwd=ROOT,
        env={
            **os.environ,
            "PYTHONPATH": str(ROOT / "apps/api"),
            "DATABASE_URL": "deliberately-unusable-offline-setting",
        },
        capture_output=True,
        text=True,
        check=False,
    )


def test_prepare_reads_actual_full_payloads_but_claims_only_expected_pins(cohort, tmp_path):
    paths = []
    for index, package in enumerate(cohort.packages):
        path = tmp_path / f"replay_{index}.json"
        path.write_text(json.dumps(package), encoding="utf-8-sig")
        paths.append(path)
    output = tmp_path / "manifest.json"
    result = run(
        "prepare",
        "--member",
        "2026-09-30",
        paths[0],
        "--member",
        "2026-09-30",
        paths[1],
        "--manifest-id",
        "sqlite-two-sessions",
        "--output",
        output,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    value = json.loads(result.stdout)
    assert value["member_count"] == 2 and value["source_evidence_verified"] is False
    assert value["claim_scope"] == "EXPECTED_PINS_FROM_LOCAL_FILES_ONLY"
    assert json.loads(output.read_text()) == cohort.manifest.canonical_payload()


def test_client_database_flag_does_not_prove_source_in_prepare(cohort, tmp_path):
    package = cohort.packages[0]
    package["input_provenance"]["database_environment_replay_verified"] = True
    package["replay_evidence"]["current_polar_source_verified"] = True
    package["package_hash"] = canonical_hash(
        {k: v for k, v in package.items() if k != "package_hash"}
    )
    payload = tmp_path / "client_claim.json"
    payload.write_text(json.dumps(package))
    output = tmp_path / "manifest.json"
    result = run(
        "prepare",
        "--member",
        "2026-09-30",
        payload,
        "--manifest-id",
        "client-only",
        "--output",
        output,
    )
    assert result.returncode == 0
    assert json.loads(result.stdout)["source_evidence_verified"] is False


def test_prepare_cannot_overwrite_previous_manifest_or_select_same_session_twice(
    cohort, cli, tmp_path, capsys
):
    payload = tmp_path / "replay.json"
    payload.write_text(json.dumps(cohort.packages[0]))
    output = tmp_path / "protected.json"
    output.write_bytes(b"previous user data")
    args = [
        "prepare",
        "--member",
        "2026-09-30",
        str(payload),
        "--manifest-id",
        "check",
        "--output",
        str(output),
    ]
    assert cli.main(args) == 1 and output.read_bytes() == b"previous user data"
    assert cli.main([*args, "--member", "2026-09-30", str(payload)]) == 1
    assert "previous user data" not in capsys.readouterr().out


@pytest.mark.parametrize(
    "text",
    [
        '{"schema_version":"0.1","schema_version":"0.1"}',
        '{"private":NaN}',
        '{"private":Infinity}',
        "[]",
        "{",
    ],
)
def test_invalid_files_never_reach_configured_db(cli, tmp_path, monkeypatch, text):
    target = tmp_path / "bad.json"
    target.write_text(text)
    dependency = AsyncMock(side_effect=AssertionError("Must remain offline"))
    monkeypatch.setattr(cli, "verify_configured_owner", dependency)
    assert cli.main(["verify", str(target)]) == 1
    dependency.assert_not_awaited()


def test_unknown_authority_values_are_not_echoed(cli, cohort, tmp_path, monkeypatch, capsys):
    data = cohort.manifest.canonical_payload()
    data["training_authorized"] = "private value must never be echoed"
    target = tmp_path / "claim.json"
    target.write_text(json.dumps(data))
    dependency = AsyncMock(side_effect=AssertionError("Must remain offline"))
    monkeypatch.setattr(cli, "verify_configured_owner", dependency)
    assert cli.main(["verify", str(target)]) == 1
    assert "private value" not in capsys.readouterr().out
    dependency.assert_not_awaited()


def test_verify_checks_existing_output_before_db_and_writes_new_index_only_on_success(
    cli,
    cohort,
    tmp_path,
    monkeypatch,
    capsys,
):
    from test_response_cohort_assembly import assemble

    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(cohort.manifest.canonical_payload()))
    output = tmp_path / "index.json"
    output.write_bytes(b"existing result")
    dependency = AsyncMock(return_value=assemble(cohort))
    monkeypatch.setattr(cli, "verify_configured_owner", dependency)
    assert cli.main(["verify", str(manifest), "--output", str(output)]) == 1
    dependency.assert_not_awaited()
    assert output.read_bytes() == b"existing result"
    output.unlink()
    assert cli.main(["verify", str(manifest), "--output", str(output)]) == 0
    value = json.loads(output.read_text())
    assert value["source_evidence_verified"] is True
    assert value["verified_member_count"] == 2
    assert "value_bpm" not in output.read_text()
    dependency.return_value = {"status": "WITHHELD", "source_evidence_verified": False}
    rejected = tmp_path / "not_saved.json"
    assert cli.main(["verify", str(manifest), "--output", str(rejected)]) == 1
    assert not rejected.exists()
    capsys.readouterr()


def test_missing_configured_user_is_never_created(cli, monkeypatch):
    import asyncio
    from types import SimpleNamespace

    from app.db import session

    db = AsyncMock()
    db.execute.return_value.scalar_one_or_none = lambda: None
    context = AsyncMock()
    context.__aenter__.return_value = db
    disposed = AsyncMock()
    monkeypatch.setattr(session, "SessionLocal", lambda: context)
    monkeypatch.setattr(session, "engine", SimpleNamespace(dispose=disposed))
    with pytest.raises(ValueError, match="existing demo user not found"):
        asyncio.run(cli.verify_configured_owner(None))
    db.add.assert_not_called()
    db.commit.assert_not_awaited()
    disposed.assert_awaited_once()


def test_file_limit_is_checked_before_json_parse(cli, tmp_path):
    path = tmp_path / "large.json"
    path.write_bytes(b"{}" * 10)
    with pytest.raises(ValueError, match="size limit"):
        cli.read_json(path, 10)
