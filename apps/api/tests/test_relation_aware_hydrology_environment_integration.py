from app.services.relation_aware_trusted_route_hydrology_context import (
    build_relation_aware_trusted_route_hydrology_context,
)
from app.services.trusted_route_environment_context import (
    build_trusted_route_environment_context,
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
                        "order_index": 0,
                        "segment_index": 0,
                        "midpoint_timestamp": "2026-08-29T06:00:30+02:00",
                    }
                ],
            }
        ],
    }


def _water_identity():
    return {
        "schema_version": "0.1",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "environment_types": ["RIVER_INLAND"],
                "mixed_environment_route": False,
                "segments": [
                    {
                        "order_index": 0,
                        "environment_type": "RIVER_INLAND",
                        "resolution_status": "DIRECT_RESOLVED",
                        "cross_domain_conflict": False,
                        "resolved_river_inland_identity": {
                            "waterbody_id": "HU:BRANCH:1",
                            "identity_names": ["Branch"],
                        },
                        "resolved_marine_region_identity": None,
                    }
                ],
            }
        ],
    }


def _raw_hydrology(*, water_level_available=True):
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
                        "water_level": (
                            {"available": True, "value": 300, "unit": "cm"}
                            if water_level_available
                            else None
                        ),
                        "discharge": {
                            "available": True,
                            "value": 1000,
                            "unit": "m3/s",
                        },
                        "current_speed_estimate_mps": 4.2,
                        "current_direction_deg": 90.0,
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
                "trusted_context": None,
                "representativeness_limitations": ["IDENTITY_CONFLICT"],
                "trust_basis": ["HYDROLOGY_CONTEXT_WITHHELD_NOT_REPRESENTATIVE"],
            }
        ],
    }


def _water_level_relation():
    return {
        "schema_version": "0.1",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "status": "SUPPORTED_WITH_LIMITATIONS",
                "metric_relations": [
                    {
                        "metric_key": "WATER_LEVEL",
                        "decision": "TRANSFER_SUPPORTED",
                        "representativeness_ceiling": "PARTIALLY_REPRESENTATIVE",
                        "relation_type": "UNCONTROLLED_HYDRAULIC_CONNECTION",
                        "relation_id": "rel-water",
                        "source": {"station_registry_number": "1026"},
                        "limitations": ["CROSS_WATERBODY_WATER_LEVEL_PROXY"],
                    },
                    {
                        "metric_key": "DISCHARGE",
                        "decision": "TRANSFER_WITHHELD",
                        "representativeness_ceiling": "INSUFFICIENT_EVIDENCE",
                        "relation_type": "UNCONTROLLED_HYDRAULIC_CONNECTION",
                        "relation_id": "rel-water",
                        "source": {"station_registry_number": "1026"},
                        "limitations": ["DISCHARGE_TRANSFER_NOT_ESTABLISHED"],
                    },
                ],
            }
        ],
    }


def test_relation_authorized_water_level_reaches_downstream_without_discharge_leakage():
    hydrology = build_relation_aware_trusted_route_hydrology_context(
        _raw_hydrology(),
        _direct_withheld(),
        _water_level_relation(),
    )
    environment = build_trusted_route_environment_context(
        _route_input(),
        _water_identity(),
        None,
        None,
        hydrology,
        weather_source=None,
    )
    route = environment["routes"][0]
    component = route["segments"][0]["hydrology"]
    context = component["context"]

    assert route["hydrology_usable_segment_count"] == 1
    assert component["status"] == "TRUSTED_WITH_LIMITATIONS"
    assert context["water_level"]["value"] == 300
    assert "discharge" not in context
    assert "current_speed_estimate_mps" not in context
    assert "current_direction_deg" not in context


def test_missing_authorized_metric_payload_stays_withheld_downstream():
    hydrology = build_relation_aware_trusted_route_hydrology_context(
        _raw_hydrology(water_level_available=False),
        _direct_withheld(),
        _water_level_relation(),
    )
    environment = build_trusted_route_environment_context(
        _route_input(),
        _water_identity(),
        None,
        None,
        hydrology,
        weather_source=None,
    )
    route = environment["routes"][0]
    component = route["segments"][0]["hydrology"]

    assert hydrology["routes"][0]["trust_status"] == "WITHHELD"
    assert route["hydrology_usable_segment_count"] == 0
    assert component["status"] == "WITHHELD"
    assert component["context"] is None
