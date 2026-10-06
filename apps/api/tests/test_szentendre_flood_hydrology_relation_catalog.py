from copy import deepcopy

import pytest

from app.services.hydrology_relation_catalog import build_hydrology_relation_catalog
from app.services.hydrology_relation_catalog_source import (
    PRODUCTION_HYDROLOGY_RELATION_PROVIDERS,
    VALIDATION_HYDROLOGY_RELATION_PROVIDERS,
    load_hydrology_relation_catalog,
)
from app.services.hydrology_relation_decision_snapshot import (
    build_hydrology_relation_decision_snapshot,
)
from app.services.route_hydrology_relation_evidence import (
    STATUS_NOT_REQUIRED,
    STATUS_SUPPORTED_WITH_LIMITATIONS,
    STATUS_WITHHELD,
    build_route_hydrology_relation_evidence,
)
from app.services.route_hydrology_relation_live_projection import (
    build_route_hydrology_relation_live_projection,
)
from app.services.szentendre_flood_hydrology_relation_catalog import (
    DOCUMENTED_SOURCE_LEVEL_MAX_CM,
    DOCUMENTED_SOURCE_LEVEL_MIN_CM,
    DOCUMENTED_TARGET_OFFSET_MAX_CM,
    DOCUMENTED_TARGET_OFFSET_MIN_CM,
    PRODUCT,
    PROVIDER,
    SOURCE_STATION_REGISTRY_NUMBER,
    build_szentendre_flood_hydrology_relation_catalog,
)
from app.services.validation_hydrology_relation_catalog import (
    PROVIDER as VALIDATION_PROVIDER,
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


def _resolution(*, station=1020, status="UNRESOLVED", name="Szentendrei-Duna"):
    if station == 1020:
        station_name = "Nagymaros"
        watercourse = "Duna"
    elif station == 1038:
        station_name = "Szentendre"
        watercourse = "Szentendrei-Duna"
    else:
        station_name = "Other"
        watercourse = "Duna"
    candidate = {
        "source_provider": "OVF_VRAQUERY",
        "station_registry_number": str(station),
        "station_name": station_name,
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
                    {"waterbody_id": None, "identity_names": [name]}
                ],
                "resolved_hydrology_source": (
                    candidate if status == "IDENTITY_SUPPORTED" else None
                ),
                "evaluated_candidates": [{"candidate_source": candidate}],
            }
        ],
    }


def _raw_context(*values, unit="cm"):
    if not values:
        values = (690,)
    return {
        "provider": "OVF_VRAQUERY",
        "schema_version": "0.1",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "segments": [
                    {
                        "segment_index": index,
                        "start_timestamp": f"2026-08-29T06:{index:02d}:00+02:00",
                        "water_level": {"value": value, "unit": unit},
                        "discharge": {"value": 1000 + index, "unit": "m3/s"},
                        "water_temperature": {"value": 20 + index, "unit": "degC"},
                        "current_speed_estimate_mps": 1.2,
                    }
                    for index, value in enumerate(values)
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


def _projection(*values, unit="cm", catalog=None):
    catalog = catalog or build_szentendre_flood_hydrology_relation_catalog()
    return build_route_hydrology_relation_live_projection(
        route_environment_context_input=_route_input(),
        route_hydrology_source_resolution=_resolution(),
        route_hydrology_context=_raw_context(*values, unit=unit),
        trusted_route_hydrology_context=_direct_withheld(),
        relation_catalog=catalog,
    )


def _relation_route():
    return build_route_hydrology_relation_evidence(
        _route_input(),
        _resolution(),
        build_szentendre_flood_hydrology_relation_catalog(),
    )["routes"][0]


def test_catalog_is_real_production_evidence_not_validation_fixture():
    catalog = build_szentendre_flood_hydrology_relation_catalog()
    assert catalog["provider"] == PROVIDER
    assert catalog["product"] == PRODUCT
    assert catalog["metadata"]["validation_only"] is False
    assert catalog["metadata"]["synthetic"] is False
    assert PROVIDER in PRODUCTION_HYDROLOGY_RELATION_PROVIDERS
    assert PROVIDER not in VALIDATION_HYDROLOGY_RELATION_PROVIDERS


def test_catalog_documents_nagymaros_1020_and_interval_only_water_level_projection():
    relation = build_szentendre_flood_hydrology_relation_catalog()["relations"][0]
    assert relation["relation_type"] == "EMPIRICAL_PROXY"
    assert SOURCE_STATION_REGISTRY_NUMBER in relation["source"]["station_registry_numbers"]
    metric = next(row for row in relation["metrics"] if row["metric_key"] == "WATER_LEVEL")
    projection = metric["value_projection"]
    assert metric["transfer_allowed"] is True
    assert projection["projection_type"] == "ADDITIVE_INTERVAL"
    assert projection["source_value_min"] == DOCUMENTED_SOURCE_LEVEL_MIN_CM
    assert projection["source_value_max"] == DOCUMENTED_SOURCE_LEVEL_MAX_CM
    assert projection["offset_min"] == DOCUMENTED_TARGET_OFFSET_MIN_CM
    assert projection["offset_max"] == DOCUMENTED_TARGET_OFFSET_MAX_CM
    assert projection["scalar_value_established"] is False
    assert projection["extrapolation_allowed"] is False


def test_catalog_explicitly_withholds_discharge_and_temperature():
    relation = build_szentendre_flood_hydrology_relation_catalog()["relations"][0]
    decisions = {row["metric_key"]: row["transfer_allowed"] for row in relation["metrics"]}
    assert decisions == {
        "WATER_LEVEL": True,
        "DISCHARGE": False,
        "WATER_TEMPERATURE": False,
    }


def test_production_loader_returns_real_catalog_without_validation_opt_in():
    catalog = load_hydrology_relation_catalog(PROVIDER)
    assert catalog["provider"] == PROVIDER
    assert catalog["metadata"]["validation_only"] is False


def test_synthetic_validation_provider_still_requires_explicit_opt_in():
    with pytest.raises(ValueError, match="requires explicit validation mode"):
        load_hydrology_relation_catalog(VALIDATION_PROVIDER)


def test_wrong_source_station_does_not_match_real_relation():
    result = build_route_hydrology_relation_evidence(
        _route_input(),
        _resolution(station=1026),
        build_szentendre_flood_hydrology_relation_catalog(),
    )
    route = result["routes"][0]
    assert route["status"] == STATUS_WITHHELD
    assert route["metric_relations"] == []


def test_direct_szentendre_1038_still_bypasses_real_relation():
    result = build_route_hydrology_relation_evidence(
        _route_input(),
        _resolution(station=1038, status="IDENTITY_SUPPORTED"),
        build_szentendre_flood_hydrology_relation_catalog(),
    )
    assert result["routes"][0]["status"] == STATUS_NOT_REQUIRED


def test_relation_evidence_supports_water_level_and_preserves_projection_contract():
    route = _relation_route()
    assert route["status"] == STATUS_SUPPORTED_WITH_LIMITATIONS
    rows = {row["metric_key"]: row for row in route["metric_relations"]}
    assert rows["WATER_LEVEL"]["decision"] == "TRANSFER_SUPPORTED"
    assert rows["WATER_LEVEL"]["value_projection"]["projection_type"] == "ADDITIVE_INTERVAL"
    assert rows["DISCHARGE"]["decision"] == "TRANSFER_WITHHELD"
    assert rows["WATER_TEMPERATURE"]["decision"] == "TRANSFER_WITHHELD"


def test_643_cm_source_projects_to_conservative_interval_without_scalar_target():
    result = _projection(643)
    route = result["relation_aware_trusted_route_hydrology_context"]["routes"][0]
    payload = route["trusted_context"]["segments"][0]["water_level"]
    assert route["trust_status"] == "TRUSTED_WITH_LIMITATIONS"
    assert route["trust_mode"] == "RELATION_DERIVED_METRIC_PROJECTION"
    assert payload["representation"] == "INTERVAL"
    assert payload["lower_bound"] == 667
    assert payload["upper_bound"] == 681
    assert payload["scalar_value_available"] is False
    assert "value" not in payload
    assert payload["source_measurement"] == {"value": 643, "unit": "cm"}
    assert payload["lower_bound"] <= 670
    assert 680 <= payload["upper_bound"]


def test_704_cm_source_interval_contains_published_about_740_cm_example():
    payload = _projection(704)["relation_aware_trusted_route_hydrology_context"]["routes"][0]["trusted_context"]["segments"][0]["water_level"]
    assert payload["lower_bound"] == 728
    assert payload["upper_bound"] == 742
    assert payload["lower_bound"] <= 740 <= payload["upper_bound"]


def test_lower_documented_source_boundary_is_inclusive():
    route = _projection(532)["relation_aware_trusted_route_hydrology_context"]["routes"][0]
    payload = route["trusted_context"]["segments"][0]["water_level"]
    assert payload["lower_bound"] == 556
    assert payload["upper_bound"] == 570
    assert payload["lower_bound"] <= 560


def test_below_documented_flood_range_is_withheld_without_extrapolation():
    route = _projection(531)["relation_aware_trusted_route_hydrology_context"]["routes"][0]
    assert route["trust_status"] == "WITHHELD"
    assert route["trust_mode"] == "WITHHELD"
    assert route["trusted_context"] is None
    diagnostic = route["relation_metric_projection_diagnostics"][0]
    assert diagnostic["rejection_reasons"] == {
        "SOURCE_VALUE_OUTSIDE_DOCUMENTED_PROJECTION_RANGE": 1
    }
    assert "RELATION_SOURCE_VALUE_OUTSIDE_DOCUMENTED_RANGE" in route["representativeness_limitations"]


def test_above_documented_flood_range_is_withheld_without_extrapolation():
    route = _projection(717)["relation_aware_trusted_route_hydrology_context"]["routes"][0]
    assert route["trust_status"] == "WITHHELD"
    assert route["trusted_context"] is None
    assert route["relation_metric_projection_diagnostics"][0]["rejection_reasons"][
        "SOURCE_VALUE_OUTSIDE_DOCUMENTED_PROJECTION_RANGE"
    ] == 1


def test_source_unit_mismatch_is_withheld():
    route = _projection(643, unit="m")["relation_aware_trusted_route_hydrology_context"]["routes"][0]
    assert route["trust_status"] == "WITHHELD"
    assert route["relation_metric_projection_diagnostics"][0]["rejection_reasons"] == {
        "SOURCE_UNIT_MISMATCH": 1
    }


def test_nonnumeric_source_water_level_is_withheld():
    route = _projection("not-a-number")["relation_aware_trusted_route_hydrology_context"]["routes"][0]
    assert route["trust_status"] == "WITHHELD"
    assert route["relation_metric_projection_diagnostics"][0]["rejection_reasons"] == {
        "SOURCE_PAYLOAD_VALUE_NOT_NUMERIC": 1
    }


def test_real_relation_never_projects_discharge_temperature_or_current():
    route = _projection(643)["relation_aware_trusted_route_hydrology_context"]["routes"][0]
    segment = route["trusted_context"]["segments"][0]
    assert route["authorized_metric_keys"] == ["WATER_LEVEL"]
    assert set(route["withheld_metric_keys"]) == {"DISCHARGE", "WATER_TEMPERATURE"}
    assert "discharge" not in segment
    assert "water_temperature" not in segment
    assert "current_speed_estimate_mps" not in segment


def test_mixed_in_domain_and_out_of_domain_segments_are_filtered_with_diagnostics():
    route = _projection(643, 531)["relation_aware_trusted_route_hydrology_context"]["routes"][0]
    assert route["trust_status"] == "TRUSTED_WITH_LIMITATIONS"
    assert route["trusted_context_segment_count"] == 1
    assert route["withheld_context_segment_count"] == 1
    diagnostic = route["relation_metric_projection_diagnostics"][0]
    assert diagnostic["source_payload_count"] == 2
    assert diagnostic["projected_segment_count"] == 1
    assert diagnostic["rejected_segment_count"] == 1
    assert "SOME_SOURCE_SEGMENTS_REJECTED_BY_RELATION_VALUE_PROJECTION" in route["representativeness_limitations"]


def test_interval_projection_configuration_is_committed_by_relation_catalog_hash():
    catalog = build_szentendre_flood_hydrology_relation_catalog()
    projection = _projection(643, catalog=catalog)
    baseline = build_hydrology_relation_decision_snapshot(
        environment_evidence_set_id="00000000-0000-0000-0000-000000000001",
        environment_evidence_hash="e" * 64,
        route_hydrology_source_resolution_snapshot={"resolution_hash": "s" * 64},
        hydrology_relation_catalog=catalog,
        route_hydrology_relation_evidence=projection["route_hydrology_relation_evidence"],
        relation_aware_trusted_route_hydrology_context=projection[
            "relation_aware_trusted_route_hydrology_context"
        ],
    )
    changed_catalog = deepcopy(catalog)
    changed_catalog["relations"][0]["metrics"][0]["value_projection"]["offset_max"] = 61
    changed_projection = _projection(643, catalog=changed_catalog)
    changed = build_hydrology_relation_decision_snapshot(
        environment_evidence_set_id="00000000-0000-0000-0000-000000000001",
        environment_evidence_hash="e" * 64,
        route_hydrology_source_resolution_snapshot={"resolution_hash": "s" * 64},
        hydrology_relation_catalog=changed_catalog,
        route_hydrology_relation_evidence=changed_projection["route_hydrology_relation_evidence"],
        relation_aware_trusted_route_hydrology_context=changed_projection[
            "relation_aware_trusted_route_hydrology_context"
        ],
    )
    assert changed["relation_catalog_hash"] != baseline["relation_catalog_hash"]
    assert changed["relation_decision_hash"] != baseline["relation_decision_hash"]


def test_catalog_builder_rejects_interval_projection_that_allows_extrapolation():
    relation = deepcopy(build_szentendre_flood_hydrology_relation_catalog()["relations"][0])
    relation["metrics"][0]["value_projection"]["extrapolation_allowed"] = True
    with pytest.raises(ValueError, match="extrapolation_allowed must be false"):
        build_hydrology_relation_catalog(
            provider="TEST",
            product="TEST",
            relations=[relation],
        )


def test_real_catalog_is_not_mutated_by_live_projection():
    catalog = build_szentendre_flood_hydrology_relation_catalog()
    before = deepcopy(catalog)
    _projection(643, catalog=catalog)
    assert catalog == before
