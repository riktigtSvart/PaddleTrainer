import asyncio
from copy import deepcopy
from uuid import uuid4

import pytest
from test_environment_replay_persistence import scientific_state
from test_response_cohort_chronology import chronological as _chronological
from test_response_cohort_chronology import environment as _environment
from test_response_cohort_chronology import sources as _sources

from app.schemas.response_cohort import ResponseCohortManifest
from app.services import response_cohort_storage_contract as storage
from app.services.environment_replay_snapshot import canonical_hash
from app.services.response_cohort_assembly import assemble_response_cohort

chronological, environment, sources = _chronological, _environment, _sources


@pytest.fixture
def completed(chronological):
    env = chronological
    index = asyncio.run(
        assemble_response_cohort(env.db, env.request, user_id=env.user.id, verify_chronology=True)
    )
    assert index["source_evidence_verified"] is True
    return env, index


def rehash(index):
    index["cohort_index_hash"] = canonical_hash(
        {k: v for k, v in index.items() if k != "cohort_index_hash"}
    )
    return index


def make(env, index, manifest=None):
    return storage.build_cohort_record_payload(manifest or env.request, index, owner_id=env.user.id)


def test_actual_complete_index_and_request_preserved_without_science_writes(completed):
    env, index = completed
    before, commits, calls = scientific_state(env), env.db.commit_count, env.provider.await_count
    request_before, index_before = deepcopy(env.request), deepcopy(index)
    payload = make(env, index)
    result = storage.check_cohort_record_payload(payload)
    assert (
        payload["cohort_index"] == index
        and payload["cohort_index_hash"] == index["cohort_index_hash"]
    )
    assert (
        payload["request_manifest"]
        == ResponseCohortManifest.model_validate(env.request).canonical_payload()
    )
    assert (
        payload["record_hash"] != payload["cohort_index_hash"] != payload["request_manifest_hash"]
    )
    assert result["payload_integrity_verified"] is result["request_index_binding_verified"] is True
    for flag in (
        "source_evidence_verified",
        "current_source_evidence_verified",
        "owner_authorization_verified",
        "chronological_cohort_order_verified",
        "chronological_split_verified",
        "database_record_persisted",
        "split_assignment_persisted",
        "training_authorized",
        "numeric_output_authorized",
    ):
        assert result[flag] is False
    assert result["claim_scope"] == storage.CHECK_SCOPE
    assert index["chronological_split_verified"] is True
    assert result["storage_writes"] == result["environmental_provider_calls"] == 0
    assert env.request == request_before and index == index_before
    assert scientific_state(env) == before and env.db.commit_count == commits
    assert env.provider.await_count == calls


def test_reordering_request_is_deterministic_and_candidate_is_detached(completed):
    env, index = completed
    first = make(env, index)
    manifest = deepcopy(env.request)
    manifest["members"].reverse()
    manifest["split_manifest"]["assignments"].reverse()
    assert make(env, index, manifest) == first
    first["cohort_index"]["members"][0]["counts"]["observation_count"] += 1
    assert first["cohort_index"] != index


def test_single_session_with_limitations_is_valid_candidate(chronological):
    env = chronological
    manifest = deepcopy(env.request)
    manifest["members"] = manifest["members"][:1]
    manifest["split_manifest"] = None
    index = asyncio.run(
        assemble_response_cohort(env.db, manifest, user_id=env.user.id, verify_chronology=True)
    )
    payload = make(env, index, manifest)
    result = storage.check_cohort_record_payload(payload)
    assert result["member_count"] == 1
    assert payload["cohort_index"]["temporal_audit"]["status"] == "SINGLE_SESSION_TIME_BOUNDS_ONLY"
    assert payload["cohort_index"]["chronological_split_verified"] is False


@pytest.mark.parametrize(
    "case", ["id", "date", "snapshot", "evidence", "replay", "split", "missing_member"]
)
def test_request_index_binding_cannot_be_substituted_even_with_new_request_hash(completed, case):
    env, original = completed
    manifest, index = deepcopy(env.request), deepcopy(original)
    if case == "id":
        manifest["manifest_id"] += "-different"
    elif case == "date":
        manifest["members"][0]["route_date"] = "2026-10-05"
    elif case == "snapshot":
        manifest["members"][0]["expected_snapshot_hash"] = "f" * 64
    elif case == "evidence":
        manifest["members"][0]["expected_evidence_hash"] = "f" * 64
    elif case == "replay":
        manifest["members"][0]["expected_unassigned_replay_package_hash"] = "f" * 64
    elif case == "split":
        manifest["split_manifest"]["assignments"][0]["split"] = "TEST"
    else:
        manifest["members"].pop()
        manifest["split_manifest"] = None
    with pytest.raises(ValueError):
        make(env, index, manifest)
    if case in ("snapshot", "evidence", "replay", "split", "missing_member"):
        index["request_manifest_hash"] = ResponseCohortManifest.model_validate(
            manifest
        ).request_manifest_hash()
        with pytest.raises(ValueError):
            make(env, rehash(index), manifest)


@pytest.mark.parametrize(
    "owner", [None, True, "invalid", "00000000-0000-0000-0000-000000000ABC", str(uuid4())]
)
def test_owner_binding_requires_canonical_database_uuid(completed, owner):
    env, index = completed
    with pytest.raises(ValueError):
        storage.build_cohort_record_payload(env.request, index, owner_id=owner)


@pytest.mark.parametrize(
    "case",
    [
        "summary",
        "api_wrapper",
        "b_index",
        "withheld",
        "extra_root",
        "extra_member",
        "order",
        "proof_flag",
        "count_bool",
        "member_group",
        "source_hash",
        "temporal_hash",
        "temporal_audit",
        "promoted_chronology",
        "promoted_split",
        "removed_limitations",
        "split_recorded",
    ],
)
def test_recomputed_index_hash_cannot_hide_bad_structural_binding(completed, case):
    env, index = completed
    index = deepcopy(index)
    member = index["members"][0]
    if case == "summary":
        index.pop("members")
    elif case == "api_wrapper":
        index = {"representation": "FULL_INDEX", "cohort_index": index}
    elif case == "b_index":
        index["assembly_version"] = "0.1.0"
    elif case == "withheld":
        index["status"] = "WITHHELD"
    elif case == "extra_root":
        index["private_training_authority"] = True
    elif case == "extra_member":
        member["raw_hr"] = [123]
    elif case == "order":
        index["members"].reverse()
    elif case == "proof_flag":
        member["current_polar_source_verified"] = 1
    elif case == "count_bool":
        member["counts"]["route_count"] = True
    elif case == "member_group":
        member["session_group_key"] = "f" * 64
    elif case == "source_hash":
        member["source_commitments"]["hr_proof_state_hash"] = "not-a-hash"
    elif case == "temporal_hash":
        member["temporal_evidence"]["temporal_evidence_hash"] = "f" * 64
    elif case == "temporal_audit":
        index["temporal_audit"]["split_boundaries_utc"] = {}
    elif case == "promoted_chronology":
        index["chronological_cohort_order_verified"] = 1
    elif case == "promoted_split":
        index["chronological_split_verified"] = 1
    elif case == "removed_limitations":
        index["training_blocking_reasons"] = []
    else:
        member["requested_split"]["assignment_persisted"] = True
    with pytest.raises(ValueError):
        make(env, rehash(index))


@pytest.mark.parametrize(
    "path,value",
    [
        (("training_authorized",), True),
        (("numeric_output_authorized",), 0),
        (("split_assignment_persisted",), True),
        (("science_storage_writes",), False),
        (("policy", "fixed_hr_shift_applied"), True),
        (("policy", "physiological_lag_ms"), 1663),
        (("policy", "feature_fit_performed"), True),
        (("policy", "feature_missing_values_imputed"), True),
        (("policy", "sensor_identity_or_acquisition_quality_promoted"), True),
    ],
)
def test_record_does_not_promote_authority_or_transform_hr(completed, path, value):
    env, index = completed
    index = deepcopy(index)
    target = index
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError):
        make(env, rehash(index))


@pytest.mark.parametrize(
    "field",
    [
        "record_hash",
        "cohort_index_hash",
        "request_manifest_hash",
        "owner_id",
        "claim_scope",
        "task",
        "record_schema_version",
        "record_id",
        "created_at",
        "training_authorized",
    ],
)
def test_payload_tampering_and_row_metadata_rejected(completed, field):
    env, index = completed
    payload = make(env, index)
    payload[field] = "changed"
    with pytest.raises(ValueError):
        storage.check_cohort_record_payload(payload)


def test_bounded_payload_is_checked_before_local_hash_work(completed, monkeypatch):
    env, index = completed
    monkeypatch.setattr(storage, "MAX_INDEX_BYTES", 64)
    with pytest.raises(ValueError, match="INDEX_SIZE_LIMIT"):
        make(env, index)
    monkeypatch.setattr(storage, "MAX_INDEX_BYTES", 1024 * 1024)
    payload = make(env, index)
    monkeypatch.setattr(storage, "MAX_RECORD_BYTES", 64)
    with pytest.raises(ValueError, match="PAYLOAD_SIZE_LIMIT"):
        storage.check_cohort_record_payload(payload)
