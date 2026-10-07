import hashlib
import json
from copy import deepcopy
from uuid import UUID

import pytest
from pydantic import ValidationError
from test_heart_rate_sample_validation import session as _session_fixture

from app.schemas.hr_acquisition import HRAcquisitionDeclarationCreate
from app.services.heart_rate_sample_validation import build_training_session_heart_rate_validation
from app.services.hr_acquisition_declarations import (
    MAX_DECLARATIONS,
    HRAcquisitionDeclarationError,
    build_hr_acquisition_declaration,
    resolve_hr_acquisition_declarations,
)

session = _session_fixture
PAYLOAD = {
    "exercise_external_id": "exercise-1",
    "sensor_modality": "OPTICAL_PPG",
    "body_location": "WRIST",
    "sensor_manufacturer": "Example Maker",
    "sensor_model": "Example Wearable",
}


def declaration(source, *, owner="athlete-1", **changes):
    return build_hr_acquisition_declaration(
        {**PAYLOAD, **changes},
        source,
        athlete_id=owner,
        session_external_id="hr-session",
        sample_session_match_count=1,
    )


def record(value, index=1):
    return {
        "declaration_id": str(UUID(int=index)),
        "recorded_at_utc": "2025-01-01T00:00:00+00:00",
        "column_identity": {
            key: value[key]
            for key in (
                "athlete_id",
                "source_provider",
                "session_external_id",
                "exercise_external_id",
                "api_source_hash",
                "declaration_hash",
            )
        },
        "declaration": value,
    }


def resolve(source, records=None, **changes):
    return resolve_hr_acquisition_declarations(
        records,
        source,
        athlete_id=changes.get("owner", "athlete-1"),
        session_external_id=changes.get("identity", "hr-session"),
        sample_session_match_count=changes.get("count", 1),
    )


def rehash(value):
    value.pop("declaration_hash", None)
    value["declaration_hash"] = hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def test_recording_product_without_statement_does_not_infer_sensor(session):
    result = resolve(session)
    assert result["status"] == "NOT_DECLARED"
    assert result["recording_product_model_name"] == "POLAR RECORDING DEVICE"
    assert result["exercises"][0]["declared_sensor"] is None
    assert result["declared_exercise_count"] == 0
    assert result["sensor_identity_verified"] is result["acquisition_quality_verified"] is False


@pytest.mark.parametrize(
    "modality,location",
    [
        ("OPTICAL_PPG", "WRIST"),
        ("ELECTRICAL", "CHEST"),
        ("OPTICAL_PPG", "UPPER_ARM"),
        ("OTHER", "OTHER"),
        ("UNKNOWN", "UNKNOWN"),
    ],
)
def test_generic_sensor_statements_preserve_source_and_raw_validation(session, modality, location):
    before = deepcopy(session)
    baseline = build_training_session_heart_rate_validation(
        session, expected_session_external_id="hr-session", sample_session_match_count=1
    )
    value = declaration(session, sensor_modality=modality, body_location=location)
    result = resolve(session, [record(value)])
    assert result["status"] == "USER_DECLARED_WITH_LIMITATIONS"
    exercise = result["exercises"][0]
    assert exercise["declared_sensor"]["sensor_modality"] == modality
    assert exercise["declaration_source"] == "USER_DECLARATION"
    assert exercise["source_binding_verified"] is True
    assert exercise["acquisition_quality_verified"] is exercise["sensor_identity_verified"] is False
    assert result["training_authorized"] is result["numeric_prediction_authorized"] is False
    assert session == before
    assert (
        build_training_session_heart_rate_validation(
            session, expected_session_external_id="hr-session", sample_session_match_count=1
        )
        == baseline
    )


@pytest.mark.parametrize(
    "change",
    [
        {"sensor_identity_verified": True},
        {"source_kind": "PROVIDER_VERIFIED"},
        {"acquisition_quality_verified": True},
        {"training_authorized": True},
        {"numeric_prediction_authorized": True},
        {"athlete_id": "another-athlete"},
        {"source_provider": "OTHER"},
        {"exercise_external_id": "missing"},
        {"declaration_version": "future"},
        {"unexpected": "field"},
    ],
)
def test_even_rehashed_forged_claims_do_not_become_accepted_statements(session, change):
    value = declaration(session)
    value.update(change)
    rehash(value)
    result = resolve(session, [record(value)])
    assert result["status"] == "WITHHELD"
    assert result["declared_exercise_count"] == 0
    assert result["rejected_record_count"] == 1
    assert result["acquisition_quality_verified"] is False


@pytest.mark.parametrize("failure", ["SOURCE", "OWNER", "COLUMN", "DUPLICATE_ID", "HASH"])
def test_stale_wrong_owner_or_corrupt_records_are_not_applied(session, failure):
    entries = [record(declaration(session))]
    kwargs = {}
    if failure == "SOURCE":
        session["modified"] = "2025-02-01T00:00:00Z"
    elif failure == "OWNER":
        kwargs["owner"] = "another-athlete"
    elif failure == "COLUMN":
        entries[0]["column_identity"]["exercise_external_id"] = "other"
    elif failure == "DUPLICATE_ID":
        entries *= 2
    else:
        entries[0]["declaration"]["statement"]["body_location"] = "CHEST"
    result = resolve(session, entries, **kwargs)
    assert result["status"] == "WITHHELD"
    assert result["exercises"][0]["declared_sensor"] is None


def test_conflicts_do_not_choose_latest_and_explicit_correction_preserves_history(session):
    first = record(declaration(session), 1)
    other = record(declaration(session, sensor_modality="ELECTRICAL", body_location="CHEST"), 2)
    other["recorded_at_utc"] = "2030-01-01T00:00:00+00:00"
    conflict = resolve(session, [first, other])
    assert conflict["status"] == "REVIEW_REQUIRED"
    assert conflict["exercises"][0]["declared_sensor"] is None
    assert len(conflict["exercises"][0]["active_declaration_ids"]) == 2
    correction = record(
        declaration(
            session, supersedes_declaration_ids=[first["declaration_id"], other["declaration_id"]]
        ),
        3,
    )
    entries = [first, other, correction]
    before = deepcopy(entries)
    resolved = resolve(session, entries)
    assert resolved["status"] == "USER_DECLARED_WITH_LIMITATIONS"
    assert resolved["provided_record_count"] == 3
    assert resolved["exercises"][0]["active_declaration_ids"] == [correction["declaration_id"]]
    assert resolve(session, entries[::-1]) == resolved
    assert entries == before


@pytest.mark.parametrize("failure", ["MISSING_PARENT", "SELF_CYCLE", "TWO_NODE_CYCLE"])
def test_invalid_correction_lineage_cannot_retire_a_statement(session, failure):
    first_id, second_id = str(UUID(int=1)), str(UUID(int=2))
    predecessors = [first_id] if failure == "SELF_CYCLE" else [second_id]
    entries = [record(declaration(session, supersedes_declaration_ids=predecessors), 1)]
    if failure == "TWO_NODE_CYCLE":
        entries.append(record(declaration(session, supersedes_declaration_ids=[first_id]), 2))
    result = resolve(session, entries)
    assert result["status"] == "REVIEW_REQUIRED"
    assert "HR_ACQUISITION_CORRECTION_LINEAGE_INVALID" in result["exercises"][0]["blocking_reasons"]


def test_concurrent_corrections_with_different_details_remain_a_conflict(session):
    parent = record(declaration(session), 1)
    left = record(
        declaration(
            session, sensor_model="Device A", supersedes_declaration_ids=[parent["declaration_id"]]
        ),
        2,
    )
    right = record(
        declaration(
            session, sensor_model="Device B", supersedes_declaration_ids=[parent["declaration_id"]]
        ),
        3,
    )
    result = resolve(session, [parent, left, right])
    assert result["status"] == "REVIEW_REQUIRED"
    assert result["exercises"][0]["active_declaration_ids"] == [
        left["declaration_id"],
        right["declaration_id"],
    ]
    assert result["exercises"][0]["declared_sensor"] is None


def test_reported_issues_require_review_without_claiming_artifact_detection(session):
    result = resolve(
        session, [record(declaration(session, reported_issue_codes=["SIGNAL_DROPOUT"]))]
    )
    assert result["status"] == "REVIEW_REQUIRED"
    assert result["declared_exercise_count"] == 1
    assert result["review_required_exercise_count"] == 1
    assert (
        "HR_USER_REPORTED_ACQUISITION_ISSUES_REQUIRE_REVIEW"
        in result["exercises"][0]["blocking_reasons"]
    )
    assert result["exercises"][0]["acquisition_quality_verified"] is False


@pytest.mark.parametrize("records", [{}, "records", [None], [None] * (MAX_DECLARATIONS + 1)])
def test_record_shape_and_limits_are_controlled(session, records):
    assert resolve(session, records)["status"] == "WITHHELD"


@pytest.mark.parametrize("source", [None, {}, {"exercises": None}, {"exercises": {}}])
def test_absent_or_malformed_api_source_is_controlled(source):
    assert resolve(source)["status"] == "WITHHELD"


@pytest.mark.parametrize(
    "changes",
    [
        {"athlete_id": "client-owner"},
        {"source_kind": "PROVIDER"},
        {"acquisition_quality_verified": True},
        {"training_authorized": True},
        {"sensor_modality": "invented"},
        {"sensor_model": 123},
        {"sensor_model": " "},
        {"sensor_model": "X" * 101},
        {"sensor_model": "bad\nlabel"},
        {"reported_issue_codes": ["invented"]},
        {"supersedes_declaration_ids": ["not-a-uuid"]},
    ],
)
def test_api_schema_rejects_claims_and_malformed_details(changes):
    with pytest.raises(ValidationError):
        HRAcquisitionDeclarationCreate.model_validate({**PAYLOAD, **changes})


def test_statement_normalization_is_idempotent_and_no_report_is_not_quality_proof(session):
    first = declaration(
        session,
        sensor_model=" Example Wearable ",
        reported_issue_codes=["SIGNAL_DROPOUT", "LOOSE_CONTACT", "SIGNAL_DROPOUT"],
    )
    second = declaration(session, reported_issue_codes=["LOOSE_CONTACT", "SIGNAL_DROPOUT"])
    assert first == second
    clean = resolve(session, [record(declaration(session))])
    assert clean["exercises"][0]["reported_issue_codes"] == []
    assert clean["acquisition_quality_verified"] is False


def test_ambiguous_exercise_cannot_receive_a_declaration(session):
    session["exercises"].append(deepcopy(session["exercises"][0]))
    with pytest.raises(HRAcquisitionDeclarationError, match="EXERCISE_MISSING_OR_AMBIGUOUS"):
        declaration(session)


def test_full_supported_correction_chain_is_resolved_without_recursive_stack_overflow(session):
    entries = []
    for i in range(1, MAX_DECLARATIONS + 1):
        predecessors = [entries[-1]["declaration_id"]] if entries else []
        entries.append(
            record(
                declaration(
                    session, sensor_model=f"Revision {i}", supersedes_declaration_ids=predecessors
                ),
                i,
            )
        )
    result = resolve(session, entries)
    assert result["status"] == "USER_DECLARED_WITH_LIMITATIONS"
    assert result["exercises"][0]["active_declaration_ids"] == [entries[-1]["declaration_id"]]
    assert (
        result["exercises"][0]["declared_sensor"]["sensor_model"] == f"Revision {MAX_DECLARATIONS}"
    )
