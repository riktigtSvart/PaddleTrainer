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


def _snapshot(identity_hash="a" * 64):
    return {
        "snapshot_schema_version": "0.1",
        "identity_schema_version": "0.1",
        "identity_hash": identity_hash,
        "status": "DIRECT_RESOLVED",
        "routes": [],
    }


def test_hash_semantics_version_is_bumped_for_water_identity_binding():
    assert EVIDENCE_HASH_SEMANTICS_VERSION == "2"


def test_trusted_water_identity_changes_environment_semantic_hash():
    baseline = build_environment_persistence_plan(_record())

    with_identity = _record()
    with_identity["route_water_environment_identity_snapshot"] = _snapshot()
    identity_plan = build_environment_persistence_plan(with_identity)

    assert baseline["evidence_hash"] != identity_plan["evidence_hash"]
    assert baseline["water_environment_identity_hash"] is None
    assert identity_plan["water_environment_identity_hash"] == "a" * 64


def test_same_identity_hash_is_environment_hash_idempotent():
    first = _record()
    first["route_water_environment_identity_snapshot"] = _snapshot("b" * 64)

    second = deepcopy(first)
    second["route_water_environment_identity_snapshot"] = {
        "routes": [],
        "status": "DIRECT_RESOLVED",
        "identity_hash": "b" * 64,
        "identity_schema_version": "0.1",
        "snapshot_schema_version": "0.1",
    }

    first_plan = build_environment_persistence_plan(first)
    second_plan = build_environment_persistence_plan(second)

    assert first_plan["evidence_hash"] == second_plan["evidence_hash"]


def test_different_identity_hash_changes_environment_semantic_hash():
    first = _record()
    first["route_water_environment_identity_snapshot"] = _snapshot("c" * 64)
    second = _record()
    second["route_water_environment_identity_snapshot"] = _snapshot("d" * 64)

    assert (
        build_environment_persistence_plan(first)["evidence_hash"]
        != build_environment_persistence_plan(second)["evidence_hash"]
    )


def test_invalid_identity_hash_is_rejected_before_persistence():
    record = _record()
    record["route_water_environment_identity_snapshot"] = _snapshot("not-a-hash")

    with pytest.raises(ValueError, match="invalid identity_hash"):
        build_environment_persistence_plan(record)
