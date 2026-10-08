"""Pure immutable record contract: payload binding is never current source proof."""

import re
from collections import Counter
from copy import deepcopy
from uuid import UUID

from app.schemas.response_cohort import ResponseCohortManifest
from app.services.environment_replay_snapshot import canonical_hash
from app.services.response_cohort_assembly import (
    MAX_EXECUTION_MEMBERS,
    MAX_INDEX_BYTES,
    verify_cohort_index_integrity,
)
from app.services.response_cohort_temporal import audit_cohort_temporal_metadata
from app.services.response_dataset_integrity import require_json_size
from app.services.response_dataset_split import resolve_dataset_split, session_group_key

RECORD_SCHEMA_VERSION = "0.1"
MAX_RECORD_BYTES = 2 * 1024 * 1024
RECORD_SCOPE = "ARCHIVED_REQUEST_AND_ASSEMBLER_INDEX_ONLY"
CHECK_SCOPE = "LOCAL_PAYLOAD_INTEGRITY_AND_REQUEST_INDEX_BINDING_ONLY"
INDEX_FIELDS = frozenset(
    {
        "schema_version",
        "assembly_version",
        "task",
        "manifest_id",
        "request_manifest_hash",
        "requested_member_count",
        "verified_member_count",
        "status",
        "claim_scope",
        "source_evidence_verified",
        "member_order",
        "members",
        "totals",
        "requested_split_counts",
        "blocking_reasons",
        "training_blocking_reasons",
        "temporal_audit",
        "chronology_claim_scope",
        "chronological_cohort_order_verified",
        "chronological_split_verified",
        "split_assignment_persisted",
        "independence_between_sessions_verified",
        "training_authorized",
        "numeric_output_authorized",
        "pre_exercise_prediction_authorized",
        "causal_prediction_authorized",
        "environmental_provider_calls",
        "science_storage_writes",
        "policy",
        "execution_limits",
        "cohort_index_hash",
    }
)
MEMBER_FIELDS = frozenset(
    {
        "status",
        "provider",
        "athlete_id",
        "session_external_id",
        "session_group_key",
        "replay_snapshot_id",
        "snapshot_hash",
        "snapshot_schema_version",
        "evidence_set_id",
        "evidence_hash",
        "dataset_version",
        "unassigned_replay_package_hash",
        "source_commitments",
        "source_evidence_verified",
        "database_environment_evidence_verified",
        "current_polar_source_verified",
        "pinned_hr_proof_state_verified",
        "payload_integrity_verified",
        "internal_references_verified",
        "full_member_payload_in_index",
        "base_split_status",
        "requested_split",
        "counts",
        "feature_status_counts",
        "hr_window_status_counts",
        "history_summary",
        "temporal_evidence",
        "training_blocking_reasons",
    }
)
RECORD_FIELDS = frozenset(
    {
        "record_schema_version",
        "owner_id",
        "task",
        "claim_scope",
        "request_manifest_hash",
        "cohort_index_hash",
        "request_manifest",
        "cohort_index",
        "record_hash",
    }
)
FALSE_FLAGS = (
    "split_assignment_persisted",
    "independence_between_sessions_verified",
    "training_authorized",
    "numeric_output_authorized",
    "pre_exercise_prediction_authorized",
    "causal_prediction_authorized",
)
MEMBER_TRUE_FLAGS = (
    "source_evidence_verified",
    "database_environment_evidence_verified",
    "current_polar_source_verified",
    "pinned_hr_proof_state_verified",
    "payload_integrity_verified",
    "internal_references_verified",
)
COUNT_FIELDS = frozenset(
    {
        "observation_count",
        "source_observation_count",
        "route_count",
        "hr_stream_count",
        "hr_slot_count",
        "complete_hr_window_count",
        "preparation_candidate_count",
        "excluded_observation_count",
    }
)
PIN_FIELDS = {
    "provider": "provider",
    "athlete_id": "athlete_id",
    "session_external_id": "session_external_id",
    "replay_snapshot_id": "replay_snapshot_id",
    "snapshot_hash": "expected_snapshot_hash",
    "evidence_set_id": "expected_evidence_set_id",
    "evidence_hash": "expected_evidence_hash",
    "dataset_version": "expected_dataset_version",
    "snapshot_schema_version": "expected_snapshot_schema_version",
    "unassigned_replay_package_hash": "expected_unassigned_replay_package_hash",
}


def _require(condition, code):
    if not condition:
        raise ValueError(code)


def _equal(a, b):
    # JSON distinctions such as true versus 1 must not disappear in Python equality.
    return canonical_hash(a) == canonical_hash(b)


def _owner(value):
    try:
        parsed = UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise ValueError("COHORT_RECORD_OWNER_INVALID") from None
    _require(type(value) is str and str(parsed) == value, "COHORT_RECORD_OWNER_INVALID")
    return value


def _validate_binding(manifest, index, owner_id):
    _require(len(manifest.members) <= MAX_EXECUTION_MEMBERS, "COHORT_RECORD_MEMBER_LIMIT")
    _require(
        all(m.athlete_id == owner_id for m in manifest.members), "COHORT_RECORD_OWNER_MISMATCH"
    )
    require_json_size(index, MAX_INDEX_BYTES, "COHORT_RECORD_INDEX_SIZE_LIMIT")
    _require(
        isinstance(index, dict) and set(index) == INDEX_FIELDS,
        "COHORT_RECORD_COMPLETE_C_INDEX_REQUIRED",
    )
    _require(verify_cohort_index_integrity(index), "COHORT_RECORD_INDEX_INTEGRITY_FAILED")
    _require(
        index["schema_version"] == "0.1"
        and index["assembly_version"] == "0.2.0"
        and index["source_evidence_verified"] is True
        and index["claim_scope"] == "SELECTED_MEMBER_SOURCE_BINDING_AND_PAYLOAD_INTEGRITY_ONLY"
        and index["chronology_claim_scope"]
        == "ACTUALLY_SOURCE_BOUND_DECLARED_WALL_CLOCK_METADATA_ONLY",
        "COHORT_RECORD_COMPLETE_C_INDEX_REQUIRED",
    )
    _require(
        index["request_manifest_hash"] == manifest.request_manifest_hash()
        and index["manifest_id"] == manifest.manifest_id
        and index["task"] == manifest.task,
        "COHORT_RECORD_REQUEST_INDEX_MISMATCH",
    )
    _require(
        all(index[flag] is False for flag in FALSE_FLAGS)
        and all(
            type(index[key]) is int and index[key] == 0
            for key in ("science_storage_writes", "environmental_provider_calls")
        )
        and index["policy"]["fixed_hr_shift_applied"] is False
        and index["policy"]["physiological_lag_ms"] is None
        and index["policy"]["feature_fit_performed"] is False
        and index["policy"]["feature_missing_values_imputed"] is False
        and index["policy"]["sensor_identity_or_acquisition_quality_promoted"] is False,
        "COHORT_RECORD_UNEXPECTED_AUTHORIZATION_OR_TRANSFORMATION",
    )
    _require(
        all(
            type(index[key]) is int and index[key] == len(manifest.members)
            for key in ("requested_member_count", "verified_member_count")
        )
        and index["member_order"] == "CANONICAL_SESSION_IDENTITY_NOT_CHRONOLOGICAL"
        and index["blocking_reasons"] == [],
        "COHORT_RECORD_MEMBERSHIP_MISMATCH",
    )
    requested = manifest.canonical_payload()
    for pin, member in zip(requested["members"], index["members"]):
        _require(
            isinstance(member, dict) and set(member) == MEMBER_FIELDS,
            "COHORT_RECORD_MEMBER_FIELDS_INVALID",
        )
        _require(
            all(member[field] == pin[request_field] for field, request_field in PIN_FIELDS.items())
            and member["status"] == "SOURCE_VERIFIED_WITH_LIMITATIONS"
            and all(member[flag] is True for flag in MEMBER_TRUE_FLAGS)
            and member["full_member_payload_in_index"] is False
            and member["base_split_status"] == "UNASSIGNED"
            and member["session_group_key"]
            == session_group_key(owner_id, pin["session_external_id"]),
            "COHORT_RECORD_MEMBER_PIN_OR_IDENTITY_MISMATCH",
        )
        _require(
            set(member["counts"]) == COUNT_FIELDS
            and all(type(v) is int and v >= 0 for v in member["counts"].values()),
            "COHORT_RECORD_COUNTS_INVALID",
        )
        _require(
            set(member["source_commitments"])
            == {"route_source_hash", "sample_source_hash", "hr_proof_state_hash"}
            and all(
                isinstance(v, str) and re.fullmatch(r"[0-9a-f]{64}", v)
                for v in member["source_commitments"].values()
            ),
            "COHORT_RECORD_SOURCE_COMMITMENTS_INVALID",
        )
        split = resolve_dataset_split(
            requested["split_manifest"],
            athlete_id=owner_id,
            session_external_id=pin["session_external_id"],
        )
        _require(_equal(split, member["requested_split"]), "COHORT_RECORD_SPLIT_BINDING_MISMATCH")
        evidence = member["temporal_evidence"]
        _require(
            evidence["temporal_evidence_hash"]
            == canonical_hash({k: v for k, v in evidence.items() if k != "temporal_evidence_hash"})
            and evidence["binding_scope"]
            == "ACTUALLY_VERIFIED_CURRENT_POLAR_SOURCES_AND_PINNED_UNASSIGNED_REPLAY",
            "COHORT_RECORD_TEMPORAL_COMMITMENT_INVALID",
        )
    _require(
        set(index["totals"]) == COUNT_FIELDS
        and all(type(v) is int and v >= 0 for v in index["totals"].values())
        and _equal(
            index["requested_split_counts"],
            dict(
                sorted(
                    Counter(
                        m["requested_split"]["split"] or "UNASSIGNED" for m in index["members"]
                    ).items()
                )
            ),
        ),
        "COHORT_RECORD_TOTALS_OR_SPLIT_COUNTS_INVALID",
    )
    temporal = audit_cohort_temporal_metadata(index["members"])
    _require(
        _equal(temporal, index["temporal_audit"])
        and index["chronological_cohort_order_verified"]
        is temporal["chronological_order_supported"]
        and index["chronological_split_verified"] is temporal["chronological_split_supported"],
        "COHORT_RECORD_TEMPORAL_AUDIT_MISMATCH",
    )
    _require(
        index["training_blocking_reasons"]
        == list(
            dict.fromkeys(
                temporal["split_blocking_reasons"]
                + ["HR_ACQUISITION_QUALITY_NOT_ESTABLISHED", "RESPONSE_MODEL_NOT_CONFIGURED"]
            )
        ),
        "COHORT_RECORD_TRAINING_LIMITATIONS_MISMATCH",
    )


def build_cohort_record_payload(manifest, index, *, owner_id):
    """Prepare a stable commitment. Inputs/owner context are not authenticated here.

    Future server persistence must supply its configured/authenticated owner and
    an index returned by its own fresh actual assembler, never uploaded JSON.
    This pure helper can also process local fixtures; it issues no source proof.
    """
    manifest = ResponseCohortManifest.model_validate(
        manifest.model_dump(mode="json")
        if isinstance(manifest, ResponseCohortManifest)
        else manifest
    )
    owner_id = _owner(str(owner_id) if isinstance(owner_id, UUID) else owner_id)
    _validate_binding(manifest, index, owner_id)
    result = {
        "record_schema_version": RECORD_SCHEMA_VERSION,
        "owner_id": owner_id,
        "task": manifest.task,
        "claim_scope": RECORD_SCOPE,
        "request_manifest_hash": manifest.request_manifest_hash(),
        "cohort_index_hash": index["cohort_index_hash"],
        "request_manifest": manifest.canonical_payload(),
        "cohort_index": deepcopy(index),
    }
    result["record_hash"] = canonical_hash(result)
    require_json_size(result, MAX_RECORD_BYTES, "COHORT_RECORD_PAYLOAD_SIZE_LIMIT")
    return result


def check_cohort_record_payload(payload):
    """Local hash/binding checks only, even if the embedded index claims source proof."""
    _require(
        isinstance(payload, dict) and set(payload) == RECORD_FIELDS, "COHORT_RECORD_FIELDS_INVALID"
    )
    require_json_size(payload, MAX_RECORD_BYTES, "COHORT_RECORD_PAYLOAD_SIZE_LIMIT")
    _require(
        payload["record_schema_version"] == RECORD_SCHEMA_VERSION,
        "COHORT_RECORD_VERSION_UNSUPPORTED",
    )
    expected = build_cohort_record_payload(
        payload["request_manifest"], payload["cohort_index"], owner_id=payload["owner_id"]
    )
    _require(_equal(expected, payload), "COHORT_RECORD_PAYLOAD_HASH_OR_BINDING_MISMATCH")
    return {
        "status": "LOCALLY_VALID_COHORT_RECORD_PAYLOAD",
        "record_schema_version": RECORD_SCHEMA_VERSION,
        "record_hash": payload["record_hash"],
        "request_manifest_hash": payload["request_manifest_hash"],
        "cohort_index_hash": payload["cohort_index_hash"],
        "member_count": len(payload["request_manifest"]["members"]),
        "claim_scope": CHECK_SCOPE,
        "payload_integrity_verified": True,
        "request_index_binding_verified": True,
        "owner_authorization_verified": False,
        "source_evidence_verified": False,
        "current_source_evidence_verified": False,
        "chronological_cohort_order_verified": False,
        "chronological_split_verified": False,
        "database_record_persisted": False,
        "split_assignment_persisted": False,
        "training_authorized": False,
        "numeric_output_authorized": False,
        "environmental_provider_calls": 0,
        "storage_writes": 0,
    }
