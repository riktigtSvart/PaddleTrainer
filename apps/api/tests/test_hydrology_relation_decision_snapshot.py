from copy import deepcopy

from app.services.hydrology_relation_catalog import build_hydrology_relation_catalog
from app.services.hydrology_relation_decision_snapshot import (
    build_hydrology_relation_decision_snapshot,
    hydrology_relation_decision_snapshot_hash,
    verify_hydrology_relation_decision_snapshot,
)
from app.services.route_hydrology_relation_live_projection import (
    build_route_hydrology_relation_live_projection,
)


EVIDENCE_SET_ID = "7d68281a-ecb3-4a91-a726-2ceed5800beb"


def _catalog(*, water_level_allowed=True, product="RELATIONS_V1"):
    return build_hydrology_relation_catalog(
        provider="TEST_AUTH",
        product=product,
        source_documents=[
            {
                "document_id": "doc-b",
                "provider": "AUTH",
                "reference": "Document B",
            },
            {
                "document_id": "doc-a",
                "provider": "AUTH",
                "reference": "Document A",
            },
        ],
        relations=[
            {
                "relation_id": "rel-1",
                "relation_type": "UNCONTROLLED_HYDRAULIC_CONNECTION",
                "target": {"waterbody_names": ["Branch A"]},
                "source": {"station_registry_numbers": [1026]},
                "authority": {"provider": "AUTH", "reference": "DOC-1"},
                "metrics": [
                    {
                        "metric_key": "DISCHARGE",
                        "transfer_allowed": False,
                        "representativeness_ceiling": "INSUFFICIENT_EVIDENCE",
                    },
                    {
                        "metric_key": "WATER_LEVEL",
                        "transfer_allowed": water_level_allowed,
                        "representativeness_ceiling": (
                            "PARTIALLY_REPRESENTATIVE"
                            if water_level_allowed
                            else "INSUFFICIENT_EVIDENCE"
                        ),
                    },
                ],
            }
        ],
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
                        "segment_index": 0,
                        "start_timestamp": "2026-08-29T06:00:00+02:00",
                        "end_timestamp": "2026-08-29T06:01:00+02:00",
                    }
                ],
            }
        ],
    }


def _resolution():
    candidate = {
        "station_registry_number": "1026",
        "station_name": "Budapest",
        "watercourse": "Duna",
    }
    return {
        "schema_version": "0.1",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "status": "UNRESOLVED",
                "applicable": True,
                "trusted_river_inland_identities": [
                    {"waterbody_id": None, "identity_names": ["Branch A"]}
                ],
                "resolved_hydrology_source": None,
                "evaluated_candidates": [{"candidate_source": candidate}],
            }
        ],
    }


def _raw_context():
    return {
        "provider": "OVF_VRAQUERY",
        "schema_version": "0.1",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "segments": [
                    {
                        "segment_index": 0,
                        "water_level": {"value": 300, "unit": "cm"},
                        "discharge": {"value": 1000, "unit": "m3/s"},
                    }
                ],
            }
        ],
    }


def _direct_withheld():
    return {
        "schema_version": "0.1",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "trust_status": "WITHHELD",
                "hydrology_context_included": False,
                "trusted_context": None,
            }
        ],
    }


def _projection(catalog=None):
    return build_route_hydrology_relation_live_projection(
        route_environment_context_input=_route_input(),
        route_hydrology_source_resolution=_resolution(),
        route_hydrology_context=_raw_context(),
        trusted_route_hydrology_context=_direct_withheld(),
        relation_catalog=catalog or _catalog(),
    )


def _snapshot(catalog=None, projection=None):
    catalog = catalog or _catalog()
    projection = projection or _projection(catalog)
    return build_hydrology_relation_decision_snapshot(
        environment_evidence_set_id=EVIDENCE_SET_ID,
        environment_evidence_hash="e" * 64,
        route_hydrology_source_resolution_snapshot={"resolution_hash": "s" * 64},
        hydrology_relation_catalog=catalog,
        route_hydrology_relation_evidence=projection[
            "route_hydrology_relation_evidence"
        ],
        relation_aware_trusted_route_hydrology_context=projection[
            "relation_aware_trusted_route_hydrology_context"
        ],
    )


def test_relation_decision_snapshot_is_deterministic_and_verifiable():
    first = _snapshot()
    second = _snapshot()
    assert first == second
    assert verify_hydrology_relation_decision_snapshot(first)
    assert first["relation_decision_hash"] == hydrology_relation_decision_snapshot_hash(first)


def test_snapshot_is_compact_and_preserves_metric_authorization_commitment():
    snapshot = _snapshot()
    route = snapshot["routes"][0]
    assert route["trust_mode"] == "RELATION_DERIVED_METRIC_PROJECTION"
    assert route["authorized_metric_keys"] == ["WATER_LEVEL"]
    assert route["withheld_metric_keys"] == ["DISCHARGE"]
    assert [row["metric_key"] for row in route["metric_decisions"]] == [
        "DISCHARGE",
        "WATER_LEVEL",
    ]
    assert "trusted_context" not in route
    assert "segments" not in route
    assert snapshot["scope"]["stores_full_hydrology_measurements"] is False


def test_metric_transfer_change_creates_new_relation_decision_lineage():
    baseline = _snapshot()
    changed_catalog = _catalog(water_level_allowed=False)
    changed = _snapshot(
        catalog=changed_catalog,
        projection=_projection(changed_catalog),
    )
    assert changed["relation_catalog_hash"] != baseline["relation_catalog_hash"]
    assert changed["relation_decision_hash"] != baseline["relation_decision_hash"]
    assert changed["routes"][0]["authorized_metric_keys"] == []


def test_catalog_product_change_creates_new_relation_decision_lineage():
    baseline = _snapshot()
    changed_catalog = _catalog(product="RELATIONS_V2")
    changed = _snapshot(
        catalog=changed_catalog,
        projection=_projection(changed_catalog),
    )
    assert changed["relation_catalog_hash"] != baseline["relation_catalog_hash"]
    assert changed["relation_decision_hash"] != baseline["relation_decision_hash"]


def test_relation_policy_change_creates_new_relation_decision_lineage():
    catalog = _catalog()
    projection = _projection(catalog)
    baseline = _snapshot(catalog=catalog, projection=projection)
    changed_projection = deepcopy(projection)
    changed_projection["relation_aware_trusted_route_hydrology_context"]["policy"][
        "unknown_metric_payload_mapping"
    ] = "ERROR"
    changed = _snapshot(catalog=catalog, projection=changed_projection)
    assert changed["relation_policy_hash"] != baseline["relation_policy_hash"]
    assert changed["relation_decision_hash"] != baseline["relation_decision_hash"]


def test_catalog_document_and_scalar_list_order_do_not_change_hash():
    catalog = _catalog()
    projection = _projection(catalog)
    baseline = _snapshot(catalog=catalog, projection=projection)
    reordered = deepcopy(catalog)
    reordered["source_documents"].reverse()
    reordered["relations"][0]["target"]["waterbody_names"] = ["Branch A"]
    reordered["relations"][0]["metrics"].reverse()
    changed = _snapshot(catalog=reordered, projection=projection)
    assert changed["relation_catalog_hash"] == baseline["relation_catalog_hash"]
    assert changed["relation_decision_hash"] == baseline["relation_decision_hash"]


def test_missing_catalog_or_relation_projection_returns_none():
    projection = _projection()
    assert build_hydrology_relation_decision_snapshot(
        environment_evidence_set_id=EVIDENCE_SET_ID,
        environment_evidence_hash="e" * 64,
        route_hydrology_source_resolution_snapshot={"resolution_hash": "s" * 64},
        hydrology_relation_catalog=None,
        route_hydrology_relation_evidence=projection[
            "route_hydrology_relation_evidence"
        ],
        relation_aware_trusted_route_hydrology_context=projection[
            "relation_aware_trusted_route_hydrology_context"
        ],
    ) is None


def test_tampered_relation_decision_snapshot_fails_verification():
    snapshot = _snapshot()
    snapshot["routes"][0]["authorized_metric_keys"] = []
    assert not verify_hydrology_relation_decision_snapshot(snapshot)
