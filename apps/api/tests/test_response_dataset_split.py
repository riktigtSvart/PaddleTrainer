from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.schemas.response_dataset import ResponseDatasetRequest
from app.services.response_dataset_split import resolve_dataset_split, session_group_key


def manifest(split="TEST", owner="athlete-1", session="session-1"):
    return {
        "schema_version": "0.1",
        "manifest_id": "example-v1",
        "assignments": [
            {
                "provider": "POLAR",
                "athlete_id": owner,
                "session_external_id": session,
                "split": split,
            }
        ],
    }


def resolve(value):
    return resolve_dataset_split(value, athlete_id="athlete-1", session_external_id="session-1")


def test_unassigned_is_explicit_and_never_automatically_partitioned():
    value = resolve(None)
    assert value["status"] == "UNASSIGNED" and value["split"] is None
    assert value["blocking_reasons"] == ["DATASET_SPLIT_NOT_ASSIGNED"]
    assert value["session_group_key"] == session_group_key("athlete-1", "session-1")
    assert value["training_authorized"] is False


@pytest.mark.parametrize("split", ["TRAIN", "VALIDATION", "TEST"])
def test_explicit_whole_session_assignment_never_authorizes_training(split):
    source = manifest(split)
    original = deepcopy(source)
    value = resolve(source)
    assert source == original
    assert value["status"] == "ASSIGNED" and value["split"] == split
    assert value["blocking_reasons"] == []
    assert value["all_routes_exercises_history_and_labels_share_assignment"] is True
    assert value["assignment_persisted"] is value["training_authorized"] is False
    assert value["chronological_cohort_order_verified"] is False
    assert value["unseen_athlete_generalization_verified"] is False
    assert value["preprocessing_fit_scope_required"] == "TRAIN_ONLY"


def test_manifest_order_is_canonical_but_other_session_assignments_change_commitment():
    a = manifest()
    a["assignments"].extend(manifest("TRAIN", session="session-2")["assignments"])
    b = deepcopy(a)
    b["assignments"].reverse()
    assert resolve(a) == resolve(b)
    b["assignments"][0]["split"] = "VALIDATION"
    assert resolve(a)["manifest_hash"] != resolve(b)["manifest_hash"]


@pytest.mark.parametrize("owner,session", [("athlete-2", "session-1"), ("athlete-1", "session-2")])
def test_another_owner_or_session_assignment_does_not_apply(owner, session):
    value = resolve(manifest(owner=owner, session=session))
    assert value["status"] == "UNASSIGNED" and value["split"] is None
    assert value["manifest_hash"]
    assert "assignments" not in value


@pytest.mark.parametrize("other_split", ["TEST", "TRAIN"])
def test_duplicate_and_conflicting_groups_are_rejected(other_split):
    source = manifest()
    source["assignments"].extend(manifest(other_split)["assignments"])
    with pytest.raises(ValueError, match="Duplicate or conflicting"):
        resolve(source)
    with pytest.raises(ValidationError):
        ResponseDatasetRequest.model_validate({"split_manifest": source})


@pytest.mark.parametrize(
    "field,value",
    [
        ("route_index", 0),
        ("exercise_index", 0),
        ("order_index", 7),
        ("window_start_ms", 0),
        ("training_authorized", True),
        ("split", "AUTOMATIC"),
        ("provider", "OTHER"),
        ("athlete_id", " athlete-1"),
        ("session_external_id", ""),
    ],
)
def test_fragments_authority_claims_and_invalid_group_selectors_are_rejected(field, value):
    source = manifest()
    source["assignments"][0][field] = value
    with pytest.raises(ValueError):
        resolve(source)
    with pytest.raises(ValidationError):
        ResponseDatasetRequest.model_validate({"split_manifest": source})


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": "0.2"},
        {"manifest_id": ""},
        {"manifest_id": " padded "},
        {"assignments": []},
        {"assignments": {}},
        {"training_authorized": True},
    ],
)
def test_invalid_manifest_contract_is_rejected(change):
    with pytest.raises(ValueError):
        resolve(manifest() | change)
    with pytest.raises(ValidationError):
        ResponseDatasetRequest.model_validate({"split_manifest": manifest() | change})


@pytest.mark.parametrize(
    "body",
    [
        {"include_payload": "true"},
        {"include_payload": 1},
        {"athlete_id": "other"},
        {"training_authorized": True},
        {"physiological_lag_ms": 5000},
    ],
)
def test_request_cannot_override_identity_authority_or_temporal_policy(body):
    with pytest.raises(ValidationError):
        ResponseDatasetRequest.model_validate(body)
