from copy import deepcopy

from app.services.route_hydrology_source_resolution_snapshot import (
    bind_route_hydrology_source_resolution_snapshot_to_evidence_record,
    build_route_hydrology_source_resolution_snapshot,
    route_hydrology_source_resolution_snapshot_hash,
    verify_route_hydrology_source_resolution_snapshot,
)


def _resolution(status="IDENTITY_SUPPORTED", station="1026"):
    resolved = None
    evaluated = []
    if status == "IDENTITY_SUPPORTED":
        resolved = {
            "source_provider": "OVF_VRAQUERY",
            "source_product": "VRAQUERY_OPENAPI",
            "source_type": "OPERATIONAL_HYDROLOGY_OBSERVATION",
            "station_registry_number": station,
            "station_name": "Budapest",
            "watercourse": "Duna",
            "river_km": 1646.5,
        }
        evaluated = [
            {
                "candidate_source": deepcopy(resolved),
                "identity_compatibility": "IDENTITY_MATCH",
                "candidate_watercourse_normalized": "duna",
                "trusted_waterbody_names_normalized": ["duna"],
                "resolution_basis": ["NORMALIZED_WATERCOURSE_NAME_EXACT_MATCH"],
            }
        ]
    return {
        "provider": "OVF_VRAQUERY",
        "schema_version": "0.1",
        "available": True,
        "status": status,
        "route_count": 1,
        "candidate_source_count": 1,
        "identity_supported_route_count": 1 if status == "IDENTITY_SUPPORTED" else 0,
        "direct_resolved_route_count": 0,
        "ambiguous_route_count": 0,
        "unresolved_route_count": 1 if status == "UNRESOLVED" else 0,
        "not_applicable_route_count": 1 if status == "NOT_APPLICABLE" else 0,
        "input_provenance": {
            "route_water_environment_identity_schema_version": "0.1",
            "hydrology_source_provider": "OVF_VRAQUERY",
            "hydrology_source_product": "VRAQUERY_OPENAPI",
        },
        "scope": {
            "domain": "ROUTE_HYDROLOGY_SOURCE_RESOLUTION",
            "uses_nearest_station_as_identity_proof": False,
            "estimates_local_current_velocity": False,
        },
        "candidate_sources": [
            resolved
            or {
                "source_provider": "OVF_VRAQUERY",
                "source_product": "VRAQUERY_OPENAPI",
                "source_type": "OPERATIONAL_HYDROLOGY_OBSERVATION",
                "station_registry_number": station,
                "station_name": "Budapest",
                "watercourse": "Duna",
                "river_km": 1646.5,
            }
        ],
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "available": True,
                "applicable": status != "NOT_APPLICABLE",
                "status": status,
                "trusted_river_inland_identity_count": 1 if status != "NOT_APPLICABLE" else 0,
                "trusted_river_inland_identities": (
                    [
                        {
                            "source_provider": "EEA_WISE_WFD",
                            "source_product": "WFD2022_SURFACE_WATER_BODY_CENTRELINE",
                            "waterbody_id": "HUAOC752",
                            "waterbody_type": "RIVER",
                            "identity_names": ["Duna"],
                            "source_feature_ids": ["HU:HUAAA626_31"],
                            "source_feature_names": ["Duna"],
                        }
                    ]
                    if status != "NOT_APPLICABLE"
                    else []
                ),
                "candidate_source_count": 1,
                "evaluated_candidate_count": len(evaluated),
                "evaluated_candidates": evaluated,
                "resolved_hydrology_source": resolved,
                "resolution_basis": [status],
            }
        ],
    }


def test_snapshot_is_deterministic_and_verifiable():
    first = build_route_hydrology_source_resolution_snapshot(_resolution())
    second = build_route_hydrology_source_resolution_snapshot(_resolution())
    assert first == second
    assert verify_route_hydrology_source_resolution_snapshot(first)
    assert first["resolution_hash"] == route_hydrology_source_resolution_snapshot_hash(first)


def test_resolution_change_changes_snapshot_hash():
    supported = build_route_hydrology_source_resolution_snapshot(_resolution())
    unresolved = build_route_hydrology_source_resolution_snapshot(
        _resolution(status="UNRESOLVED")
    )
    assert supported["resolution_hash"] != unresolved["resolution_hash"]


def test_changed_station_changes_snapshot_hash():
    first = build_route_hydrology_source_resolution_snapshot(_resolution(station="1026"))
    second = build_route_hydrology_source_resolution_snapshot(_resolution(station="9999"))
    assert first["resolution_hash"] != second["resolution_hash"]


def test_unresolved_and_not_applicable_are_persistable_snapshot_states():
    for status in ("UNRESOLVED", "NOT_APPLICABLE"):
        snapshot = build_route_hydrology_source_resolution_snapshot(
            _resolution(status=status)
        )
        assert snapshot["status"] == status
        assert verify_route_hydrology_source_resolution_snapshot(snapshot)


def test_binding_attaches_snapshot_without_owning_environment_hash():
    record = {"schema_version": "0.1", "evidence_hash": "legacy-value"}
    snapshot = build_route_hydrology_source_resolution_snapshot(_resolution())
    result = bind_route_hydrology_source_resolution_snapshot_to_evidence_record(
        record, snapshot
    )
    assert result["evidence_hash"] == "legacy-value"
    assert result["route_hydrology_source_resolution_snapshot"] == snapshot
    assert (
        result["hydrology_source_resolution_hash_binding"]
        ["route_hydrology_source_resolution_hash"]
        == snapshot["resolution_hash"]
    )
