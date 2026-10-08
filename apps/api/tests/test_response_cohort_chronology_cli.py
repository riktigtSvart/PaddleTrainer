import json
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest
from test_environment_replay_persistence import environment as _environment_fixture
from test_response_cohort_chronology import assemble
from test_response_cohort_chronology import chronological as _chronological_fixture
from test_response_cohort_chronology import sources as _sources_fixture
from test_response_cohort_cli import cli as _cli_fixture

environment = _environment_fixture
sources = _sources_fixture
chronological = _chronological_fixture
cli = _cli_fixture


@pytest.mark.parametrize("with_output", [False, True])
def test_cli_chronology_requests_fresh_owner_verification_and_preserves_distinct_claims(
    chronological,
    cli,
    tmp_path,
    monkeypatch,
    capsys,
    with_output,
):
    target = tmp_path / "request.json"
    target.write_text(json.dumps(chronological.request), encoding="utf-8-sig")
    index = assemble(chronological)
    verifier = AsyncMock(return_value=index)
    monkeypatch.setattr(cli, "verify_configured_owner", verifier)
    args = ["verify", str(target), "--chronology"]
    output = tmp_path / "index.json"
    if with_output:
        args += ["--output", str(output)]
    assert cli.main(args) == 0
    assert verifier.await_args.kwargs == {"verify_chronology": True}
    summary = json.loads(capsys.readouterr().out)
    assert summary["source_evidence_verified"] is summary["chronological_split_verified"] is True
    assert summary["training_authorized"] is False
    assert summary["temporal_audit"]["source_verification_performed"] is False
    if with_output:
        assert json.loads(output.read_text()) == index


def test_temporal_withheld_index_can_be_saved_without_claiming_evaluation(
    chronological,
    cli,
    tmp_path,
    monkeypatch,
    capsys,
):
    request = deepcopy(chronological.request)
    request["members"] = request["members"][:1]
    request["split_manifest"] = None
    value = assemble(chronological, request)
    verifier = AsyncMock(return_value=value)
    monkeypatch.setattr(cli, "verify_configured_owner", verifier)
    path, output = tmp_path / "request.json", tmp_path / "index.json"
    path.write_text(json.dumps(request))
    assert cli.main(["verify", str(path), "--chronology", "--output", str(output)]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["source_evidence_verified"] is True
    assert summary["chronological_split_verified"] is False
    assert summary["temporal_audit"]["status"] == "SINGLE_SESSION_TIME_BOUNDS_ONLY"
    assert output.exists()


def test_new_flag_does_not_allow_source_failure_to_write_an_index(
    chronological,
    cli,
    tmp_path,
    monkeypatch,
):
    request = deepcopy(chronological.request)
    request["members"][0]["expected_snapshot_hash"] = "a" * 64
    verifier = AsyncMock(return_value=assemble(chronological, request))
    monkeypatch.setattr(cli, "verify_configured_owner", verifier)
    path, output = tmp_path / "request.json", tmp_path / "index.json"
    path.write_text(json.dumps(request))
    assert cli.main(["verify", str(path), "--chronology", "--output", str(output)]) == 1
    assert not output.exists()


@pytest.mark.parametrize(
    "field", ["chronological_cohort_order_verified", "chronological_split_verified"]
)
def test_offline_claims_are_rejected_before_db_even_in_chronology_mode(
    chronological,
    cli,
    tmp_path,
    monkeypatch,
    capsys,
    field,
):
    request = deepcopy(chronological.request)
    request[field] = "private forbidden authority"
    path = tmp_path / "request.json"
    path.write_text(json.dumps(request))
    verifier = AsyncMock()
    monkeypatch.setattr(cli, "verify_configured_owner", verifier)
    assert cli.main(["verify", str(path), "--chronology"]) == 1
    verifier.assert_not_awaited()
    assert "private forbidden authority" not in capsys.readouterr().out


def test_cohort_index_is_never_accepted_as_a_request_source_proof(
    chronological,
    cli,
    tmp_path,
    monkeypatch,
):
    path = tmp_path / "forged_index.json"
    path.write_text(json.dumps(assemble(chronological)))
    verifier = AsyncMock()
    monkeypatch.setattr(cli, "verify_configured_owner", verifier)
    assert cli.main(["verify", str(path), "--chronology"]) == 1
    verifier.assert_not_awaited()
