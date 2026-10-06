from app.services.kdvvizig_hydrology_relation_catalog import (
    PRODUCT,
    PROVIDER,
    build_kdvvizig_hydrology_relation_catalog,
)
from app.services.route_hydrology_relation_evidence import (
    STATUS_NOT_REQUIRED,
    STATUS_WITHHELD,
    build_route_hydrology_relation_evidence,
)


def _route_input():
    return {
        "schema_version": "0.1",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "segments": [
                    {
                        "start_timestamp": "2026-08-29T06:00:00+02:00",
                        "end_timestamp": "2026-08-29T06:01:00+02:00",
                    }
                ],
            }
        ],
    }


def _resolution(*, name, station, watercourse, status="UNRESOLVED"):
    candidate = {
        "source_provider": "OVF_VRAQUERY",
        "station_registry_number": str(station),
        "station_name": "Budapest" if station == 1026 else "Szentendre",
        "watercourse": watercourse,
    }
    return {
        "schema_version": "0.1",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "available": True,
                "applicable": True,
                "status": status,
                "trusted_river_inland_identities": [
                    {
                        "waterbody_id": None,
                        "identity_names": [name],
                    }
                ],
                "resolved_hydrology_source": (
                    candidate if status == "IDENTITY_SUPPORTED" else None
                ),
                "evaluated_candidates": [
                    {
                        "candidate_source": candidate,
                        "identity_compatibility": (
                            "IDENTITY_SUPPORTED"
                            if status == "IDENTITY_SUPPORTED"
                            else "IDENTITY_CONFLICT"
                        ),
                    }
                ],
            }
        ],
    }


def test_kdvvizig_catalog_identifies_curated_official_product():
    catalog = build_kdvvizig_hydrology_relation_catalog()
    assert catalog["provider"] == PROVIDER
    assert catalog["product"] == PRODUCT
    assert catalog["source_mode"] == "CURATED_OFFICIAL_DOCUMENTS"
    assert catalog["source_document_count"] >= 3
    assert catalog["metadata"]["positive_metric_transfer_claims"] == 0


def test_rsd_relation_is_structure_controlled_and_does_not_claim_metric_transfer():
    relation = build_kdvvizig_hydrology_relation_catalog()["relations"][0]
    assert relation["relation_type"] == "STRUCTURE_CONTROLLED"
    assert 1026 in relation["source"]["station_registry_numbers"]
    assert "KVASSAY_VIZLEPCSO" in relation["control_structure_ids"]
    assert "TASSI_VIZLEPCSO" in relation["control_structure_ids"]
    assert relation["control_structure_state_required"] is True
    assert relation["control_state_evidence"]["available"] is False
    assert all(metric["transfer_allowed"] is False for metric in relation["metrics"])


def test_rsd_budapest_1026_relation_matches_but_is_withheld():
    result = build_route_hydrology_relation_evidence(
        _route_input(),
        _resolution(
            name="Ráckevei (Soroksári)-Duna",
            station=1026,
            watercourse="Duna",
        ),
        build_kdvvizig_hydrology_relation_catalog(),
    )
    route = result["routes"][0]
    assert route["status"] == STATUS_WITHHELD
    assert {row["metric_key"] for row in route["metric_relations"]} == {
        "WATER_LEVEL",
        "DISCHARGE",
        "WATER_TEMPERATURE",
    }
    assert all(row["decision"] == "TRANSFER_WITHHELD" for row in route["metric_relations"])


def test_szentendre_direct_1038_remains_not_required_by_relation_layer():
    result = build_route_hydrology_relation_evidence(
        _route_input(),
        _resolution(
            name="Szentendrei-Duna",
            station=1038,
            watercourse="Szentendrei-Duna",
            status="IDENTITY_SUPPORTED",
        ),
        build_kdvvizig_hydrology_relation_catalog(),
    )
    assert result["routes"][0]["status"] == STATUS_NOT_REQUIRED


def test_szentendre_with_budapest_station_does_not_accidentally_match_rsd_relation():
    result = build_route_hydrology_relation_evidence(
        _route_input(),
        _resolution(
            name="Szentendrei-Duna",
            station=1026,
            watercourse="Duna",
        ),
        build_kdvvizig_hydrology_relation_catalog(),
    )
    route = result["routes"][0]
    assert route["status"] == STATUS_WITHHELD
    assert route["metric_relations"] == []
    assert route["selected_source_by_metric"] == {}
