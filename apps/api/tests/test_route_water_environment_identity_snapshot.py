from copy import deepcopy

from app.services.route_water_environment_identity_snapshot import (
    bind_route_water_environment_identity_snapshot_to_evidence_record,
    build_route_water_environment_identity_snapshot,
    route_water_environment_identity_snapshot_hash,
    verify_route_water_environment_identity_snapshot,
)


def _identity():
    return {
        "provider": "POLAR",
        "schema_version": "0.1",
        "available": True,
        "status": "CONTINUITY_SUPPORTED",
        "route_count": 1,
        "river_inland_segment_count": 3,
        "marine_segment_count": 0,
        "ambiguous_environment_segment_count": 0,
        "unresolved_environment_segment_count": 0,
        "direct_resolved_segment_count": 2,
        "continuity_supported_segment_count": 1,
        "ambiguous_segment_count": 0,
        "transition_candidate_segment_count": 0,
        "unresolved_segment_count": 0,
        "cross_domain_conflict_segment_count": 0,
        "input_provenance": {
            "route_waterbody_trajectory_resolution_schema_version": "0.4",
            "route_marine_region_context_schema_version": "0.1",
        },
        "scope": {
            "domain": "ROUTE_WATER_ENVIRONMENT_IDENTITY",
            "aggregates_existing_trusted_domain_resolutions": True,
        },
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "available": True,
                "status": "CONTINUITY_SUPPORTED",
                "segment_count": 3,
                "environment_types": ["RIVER_INLAND"],
                "mixed_environment_route": False,
                "river_inland_segment_count": 3,
                "marine_segment_count": 0,
                "ambiguous_environment_segment_count": 0,
                "unresolved_environment_segment_count": 0,
                "direct_resolved_segment_count": 2,
                "continuity_supported_segment_count": 1,
                "ambiguous_segment_count": 0,
                "transition_candidate_segment_count": 0,
                "unresolved_segment_count": 0,
                "cross_domain_conflict_segment_count": 0,
                "river_inland_identity_count": 1,
                "river_inland_identities": [
                    {
                        "source_provider": "EEA_WISE_WFD",
                        "waterbody_id": "HUAOC752",
                        "waterbody_type": "RIVER",
                    }
                ],
                "marine_region_identity_count": 0,
                "marine_region_identities": [],
                "segments": [
                    {"order_index": 0, "resolution_status": "DIRECT_RESOLVED"},
                    {"order_index": 1, "resolution_status": "DIRECT_RESOLVED"},
                    {"order_index": 2, "resolution_status": "CONTINUITY_SUPPORTED"},
                ],
            }
        ],
    }


def test_snapshot_is_compact_and_preserves_identity_semantics():
    snapshot = build_route_water_environment_identity_snapshot(_identity())

    assert snapshot["snapshot_schema_version"] == "0.1"
    assert snapshot["identity_schema_version"] == "0.1"
    assert snapshot["status"] == "CONTINUITY_SUPPORTED"
    assert snapshot["river_inland_segment_count"] == 3
    assert snapshot["routes"][0]["environment_types"] == ["RIVER_INLAND"]
    assert snapshot["routes"][0]["river_inland_identities"][0]["waterbody_id"] == "HUAOC752"
    assert "segments" not in snapshot["routes"][0]
    assert len(snapshot["identity_hash"]) == 64


def test_snapshot_hash_is_stable_for_equivalent_key_order():
    snapshot = build_route_water_environment_identity_snapshot(_identity())
    reordered = {key: snapshot[key] for key in reversed(list(snapshot.keys()))}

    assert route_water_environment_identity_snapshot_hash(snapshot) == (
        route_water_environment_identity_snapshot_hash(reordered)
    )


def test_snapshot_hash_changes_when_identity_changes():
    first = build_route_water_environment_identity_snapshot(_identity())
    changed_identity = _identity()
    changed_identity["routes"][0]["river_inland_identities"][0]["waterbody_id"] = "OTHER"
    second = build_route_water_environment_identity_snapshot(changed_identity)

    assert first["identity_hash"] != second["identity_hash"]


def test_snapshot_verification_detects_tampering():
    snapshot = build_route_water_environment_identity_snapshot(_identity())
    tampered = deepcopy(snapshot)
    tampered["status"] = "UNRESOLVED"

    assert verify_route_water_environment_identity_snapshot(snapshot) is True
    assert verify_route_water_environment_identity_snapshot(tampered) is False


def test_snapshot_builder_returns_none_without_identity():
    assert build_route_water_environment_identity_snapshot(None) is None


def test_identity_binding_attaches_snapshot_without_owning_environment_hash():
    snapshot = build_route_water_environment_identity_snapshot(_identity())
    record = {"routes": []}

    returned = bind_route_water_environment_identity_snapshot_to_evidence_record(
        record, snapshot
    )

    assert returned is record
    assert record["route_water_environment_identity_snapshot"] == snapshot
    assert "evidence_hash" not in record
    assert record["water_environment_identity_hash_binding"] == {
        "binding_schema_version": "0.2",
        "hash_owner": "ENVIRONMENT_EVIDENCE_PERSISTENCE",
        "route_water_environment_identity_hash": snapshot["identity_hash"],
    }


def test_identity_binding_rejects_tampered_snapshot():
    snapshot = build_route_water_environment_identity_snapshot(_identity())
    snapshot["status"] = "UNRESOLVED"

    try:
        bind_route_water_environment_identity_snapshot_to_evidence_record(
            {}, snapshot
        )
    except ValueError as exc:
        assert "Invalid route water environment identity snapshot hash" in str(exc)
    else:
        raise AssertionError("Tampered identity snapshot must be rejected")


def test_no_identity_leaves_environment_evidence_record_unchanged():
    record = {"routes": []}
    returned = bind_route_water_environment_identity_snapshot_to_evidence_record(
        record, None
    )
    assert returned is record
    assert record == {"routes": []}
