import hashlib
import json
from copy import deepcopy

import pytest

from app.services.environment_evidence_persistence import (
    EVIDENCE_HASH_SEMANTICS_VERSION,
    build_environment_persistence_plan,
)


def _record():
    return {
        "schema_version": "0.1",
        "provider": "POLAR",
        "session_external_id": "session-1",
        "scope": {
            "domain": "ROUTE_ENVIRONMENT_EVIDENCE",
            "raw_data_mutated": False,
        },
        "source_catalog": {
            "weather_samples": [],
            "hydrology_measurements": [],
        },
        "routes": [],
    }


def _resolution_snapshot(resolution_hash="e" * 64):
    return {
        "snapshot_schema_version": "0.1",
        "resolution_schema_version": "0.1",
        "resolution_hash": resolution_hash,
        "status": "IDENTITY_SUPPORTED",
        "routes": [],
    }


def _legacy_minimal_hash():
    payload = {
        "hash_semantics_version": "2",
        "schema_version": "0.1",
        "provider": "POLAR",
        "session_external_id": "session-1",
        "scope": {
            "domain": "ROUTE_ENVIRONMENT_EVIDENCE",
            "raw_data_mutated": False,
        },
        "water_environment_identity_hash": None,
        "weather_samples": [],
        "hydrology_measurements": [],
        "routes": [],
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def test_no_resolution_snapshot_preserves_pre_v15_environment_hash_exactly():
    plan = build_environment_persistence_plan(_record())
    assert EVIDENCE_HASH_SEMANTICS_VERSION == "2"
    assert plan["evidence_hash"] == _legacy_minimal_hash()
    assert plan.get("hydrology_source_resolution_hash") is None


def test_resolution_snapshot_changes_environment_semantic_hash():
    baseline = build_environment_persistence_plan(_record())
    record = _record()
    record["route_hydrology_source_resolution_snapshot"] = _resolution_snapshot()
    with_resolution = build_environment_persistence_plan(record)

    assert baseline["evidence_hash"] != with_resolution["evidence_hash"]
    assert with_resolution["hydrology_source_resolution_hash"] == "e" * 64


def test_same_resolution_hash_is_environment_hash_idempotent():
    first = _record()
    first["route_hydrology_source_resolution_snapshot"] = _resolution_snapshot("a" * 64)
    second = deepcopy(first)
    second["route_hydrology_source_resolution_snapshot"] = {
        "routes": [],
        "status": "UNRESOLVED",
        "resolution_hash": "a" * 64,
        "resolution_schema_version": "0.1",
        "snapshot_schema_version": "0.1",
    }

    assert (
        build_environment_persistence_plan(first)["evidence_hash"]
        == build_environment_persistence_plan(second)["evidence_hash"]
    )


def test_different_resolution_hash_changes_environment_semantic_hash():
    first = _record()
    first["route_hydrology_source_resolution_snapshot"] = _resolution_snapshot("b" * 64)
    second = _record()
    second["route_hydrology_source_resolution_snapshot"] = _resolution_snapshot("c" * 64)

    assert (
        build_environment_persistence_plan(first)["evidence_hash"]
        != build_environment_persistence_plan(second)["evidence_hash"]
    )


def test_invalid_resolution_hash_is_rejected_before_persistence():
    record = _record()
    record["route_hydrology_source_resolution_snapshot"] = _resolution_snapshot(
        "not-a-hash"
    )
    with pytest.raises(ValueError, match="invalid resolution_hash"):
        build_environment_persistence_plan(record)
