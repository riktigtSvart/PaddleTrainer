import importlib.util
import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.schemas.response_cohort import MAX_COHORT_MEMBERS, ResponseCohortManifest

ROOT = Path(__file__).resolve().parents[3]
EXAMPLES = ROOT / "docs/examples"
TOOL_PATH = ROOT / "tools/check_response_cohort_manifest.py"
spec = importlib.util.spec_from_file_location("cohort_contract_checker", TOOL_PATH)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


@pytest.fixture
def unassigned():
    return json.loads((EXAMPLES / "response_cohort_unassigned.json").read_text())


@pytest.fixture
def assigned():
    return json.loads((EXAMPLES / "response_cohort_requested_split.json").read_text())


@pytest.mark.parametrize(
    "name,count,assignments",
    [("response_cohort_unassigned.json", 2, 0), ("response_cohort_requested_split.json", 3, 3)],
)
def test_published_synthetic_examples_prove_structure_only(name, count, assignments):
    path = EXAMPLES / name
    before = path.read_bytes()
    result = checker.check(path)
    assert path.read_bytes() == before
    assert result["status"] == "STRUCTURALLY_VALID_MANIFEST"
    assert result["member_count"] == count and result["requested_assignment_count"] == assignments
    assert result["claim_scope"] == "REQUEST_STRUCTURE_AND_COMMITMENT_ONLY"
    assert result["source_evidence_verified"] is False
    assert result["chronological_cohort_order_verified"] is False
    assert result["training_authorized"] is result["numeric_output_authorized"] is False
    assert result["split_assignment_persisted"] is False
    assert result["environmental_provider_calls"] == result["storage_writes"] == 0


def test_member_and_assignment_order_do_not_change_request_commitment(assigned):
    original = deepcopy(assigned)
    a = ResponseCohortManifest.model_validate(assigned)
    assigned["members"].reverse()
    assigned["split_manifest"]["assignments"].reverse()
    b = ResponseCohortManifest.model_validate(assigned)
    assert a.canonical_payload() == b.canonical_payload()
    assert a.request_manifest_hash() == b.request_manifest_hash()
    assert a.model_dump() == original


def test_defaults_and_explicit_null_share_a_commitment(unassigned):
    a = ResponseCohortManifest.model_validate(unassigned)
    del unassigned["task"], unassigned["split_manifest"]
    for member in unassigned["members"]:
        del member["expected_dataset_version"], member["expected_snapshot_schema_version"]
    b = ResponseCohortManifest.model_validate(unassigned)
    assert a.request_manifest_hash() == b.request_manifest_hash()


@pytest.mark.parametrize(
    "field,value",
    [
        ("expected_snapshot_hash", "a" * 64),
        ("expected_evidence_hash", "b" * 64),
        ("expected_unassigned_replay_package_hash", "c" * 64),
        ("replay_snapshot_id", str(UUID(int=500))),
        ("route_date", "2026-02-01"),
    ],
)
def test_changing_any_pinned_input_changes_request_commitment(unassigned, field, value):
    original_hash = ResponseCohortManifest.model_validate(unassigned).request_manifest_hash()
    unassigned["members"][0][field] = value
    assert (
        ResponseCohortManifest.model_validate(unassigned).request_manifest_hash() != original_hash
    )


@pytest.mark.parametrize("same_snapshot", [True, False])
def test_two_captures_cannot_double_count_one_session(unassigned, same_snapshot):
    duplicate = deepcopy(unassigned["members"][0])
    if not same_snapshot:
        duplicate["replay_snapshot_id"] = str(UUID(int=999))
    unassigned["members"].append(duplicate)
    with pytest.raises(ValidationError, match="Duplicate session group"):
        ResponseCohortManifest.model_validate(unassigned)


def test_snapshot_cannot_select_two_session_identifiers(unassigned):
    unassigned["members"][1]["replay_snapshot_id"] = unassigned["members"][0]["replay_snapshot_id"]
    with pytest.raises(ValidationError, match="different sessions"):
        ResponseCohortManifest.model_validate(unassigned)


def test_multiple_athletes_require_a_separate_future_contract(unassigned):
    unassigned["members"][1]["athlete_id"] = "another-athlete"
    with pytest.raises(ValidationError, match="one athlete"):
        ResponseCohortManifest.model_validate(unassigned)


@pytest.mark.parametrize("change", ["owner", "session", "fragment", "duplicate", "conflict"])
def test_requested_splits_cannot_escape_or_fragment_the_cohort(assigned, change):
    entries = assigned["split_manifest"]["assignments"]
    if change == "owner":
        entries[0]["athlete_id"] = "another-athlete"
    elif change == "session":
        entries[0]["session_external_id"] = "not-a-member"
    elif change == "fragment":
        entries[0]["route_index"] = 0
    else:
        duplicate = deepcopy(entries[0])
        if change == "conflict":
            duplicate["split"] = "TEST"
        entries.append(duplicate)
    with pytest.raises(ValidationError):
        ResponseCohortManifest.model_validate(assigned)


def test_partial_split_is_a_request_and_not_a_completed_evaluation(assigned, tmp_path):
    assigned["split_manifest"]["assignments"] = assigned["split_manifest"]["assignments"][:1]
    path = tmp_path / "partial.json"
    path.write_text(json.dumps(assigned))
    result = checker.check(path)
    assert result["requested_assignment_count"] == 1
    assert result["chronological_cohort_order_verified"] is result["training_authorized"] is False


def test_route_date_does_not_prove_actual_session_chronology(assigned, tmp_path):
    assigned["members"][0]["route_date"] = "2026-03-20"
    path = tmp_path / "request-only.json"
    path.write_text(json.dumps(assigned))
    assert checker.check(path)["chronological_cohort_order_verified"] is False


@pytest.mark.parametrize("location", ["root", "member", "split", "assignment"])
@pytest.mark.parametrize("value", [True, False])
def test_client_cannot_submit_training_authority_claims(assigned, location, value):
    target = {
        "root": assigned,
        "member": assigned["members"][0],
        "split": assigned["split_manifest"],
        "assignment": assigned["split_manifest"]["assignments"][0],
    }[location]
    target["training_authorized"] = value
    with pytest.raises(ValidationError):
        ResponseCohortManifest.model_validate(assigned)


@pytest.mark.parametrize(
    "field,value",
    [
        ("expected_snapshot_hash", "A" * 64),
        ("expected_evidence_hash", "a" * 63),
        ("expected_unassigned_replay_package_hash", 123),
        ("replay_snapshot_id", "not-a-uuid"),
        ("expected_evidence_set_id", "AB000000-0000-0000-0000-000000000001"),
        ("athlete_id", " athlete-example-1"),
        ("session_external_id", ""),
        ("provider", "OTHER"),
        ("route_date", "2026-02-30"),
        ("route_date", "9999-12-31"),
        ("route_date", "2026-1-1"),
        ("expected_dataset_version", "0.2.0"),
        ("expected_snapshot_schema_version", "0.2"),
        ("route_index", 0),
        ("physiological_lag_ms", 5000),
        ("source_evidence_verified", True),
        ("acquisition_quality_verified", True),
    ],
)
def test_invalid_pins_fragments_and_quality_claims_are_rejected(unassigned, field, value):
    unassigned["members"][0][field] = value
    with pytest.raises(ValidationError):
        ResponseCohortManifest.model_validate(unassigned)


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", "0.2"),
        ("manifest_id", " padded "),
        ("task", "PRE_EXERCISE_FORECAST"),
        ("members", []),
        ("members", {}),
        ("causal_prediction_authorized", True),
    ],
)
def test_unsupported_root_contracts_are_rejected(unassigned, field, value):
    unassigned[field] = value
    with pytest.raises(ValidationError):
        ResponseCohortManifest.model_validate(unassigned)


def test_membership_has_a_bounded_resource_contract(unassigned):
    prototype = unassigned["members"][0]
    unassigned["members"] = [
        prototype | {"session_external_id": str(i), "replay_snapshot_id": str(UUID(int=i + 1))}
        for i in range(MAX_COHORT_MEMBERS)
    ]
    assert len(ResponseCohortManifest.model_validate(unassigned).members) == MAX_COHORT_MEMBERS
    unassigned["members"].append(
        prototype | {"session_external_id": "overflow", "replay_snapshot_id": str(UUID(int=999))}
    )
    with pytest.raises(ValidationError):
        ResponseCohortManifest.model_validate(unassigned)


def test_published_json_schema_matches_the_python_contract():
    source = json.loads(
        (ROOT / "docs/contracts/response_cohort_manifest_v0_1.schema.json").read_text()
    )
    def semantic_schema(value):
        if isinstance(value, dict):
            return {
                key: semantic_schema(item)
                for key, item in value.items()
                if key not in {"$schema", "title", "description"}
            }
        if isinstance(value, list):
            return [semantic_schema(item) for item in value]
        return value

    assert semantic_schema(source) == semantic_schema(
        ResponseCohortManifest.model_json_schema(mode="validation")
    )


@pytest.mark.parametrize(
    "raw,reason",
    [(b'{"members":[],"members":[]}', "Duplicate JSON"), (b'{"x":NaN}', "Non-finite")],
)
def test_ambiguous_or_nonfinite_manifest_json_is_rejected(tmp_path, raw, reason):
    path = tmp_path / "invalid.json"
    path.write_bytes(raw)
    with pytest.raises(ValueError, match=reason):
        checker.check(path)


def test_checker_accepts_utf8_bom_and_preserves_original_bytes(unassigned, tmp_path):
    path = tmp_path / "windows.json"
    path.write_text(json.dumps(unassigned), encoding="utf-8-sig")
    before = path.read_bytes()
    assert checker.check(path)["member_count"] == 2 and path.read_bytes() == before


def test_checker_rejects_oversized_input_before_parsing(tmp_path):
    path = tmp_path / "too-large.json"
    path.write_bytes(b" " * (checker.MAX_MANIFEST_FILE_BYTES + 1))
    with pytest.raises(ValueError, match="1 MiB"):
        checker.check(path)


def test_cli_failure_returns_nonzero_and_does_not_echo_private_input(unassigned, tmp_path):
    path = tmp_path / "invalid-claim.json"
    unassigned["access_token"] = "private-example-token-must-not-be-echoed"
    path.write_text(json.dumps(unassigned))
    result = subprocess.run(
        [sys.executable, str(TOOL_PATH), str(path)],
        env=os.environ | {"PYTHONPATH": str(ROOT / "apps/api")},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert json.loads(result.stdout)["status"] == "REJECTED"
    assert unassigned["access_token"] not in result.stdout + result.stderr
