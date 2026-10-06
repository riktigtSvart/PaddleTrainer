from copy import deepcopy

import pytest

from app.services.hydrology_relation_catalog_source import (
    PRODUCTION_HYDROLOGY_RELATION_PROVIDERS,
    SUPPORTED_HYDROLOGY_RELATION_PROVIDERS,
    VALIDATION_HYDROLOGY_RELATION_PROVIDERS,
    load_hydrology_relation_catalog,
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
from app.services.validation_hydrology_relation_catalog import (
    PRODUCT,
    PROVIDER,
    VALIDATION_ROUTE_DATE,
    build_validation_hydrology_relation_catalog,
)


def _route_input(*, timestamp="2026-08-29T06:00:00+02:00"):
    return {
        "schema_version": "0.1",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "segments": [
                    {
                        "segment_index": 0,
                        "start_timestamp": timestamp,
                        "end_timestamp": timestamp,
                    }
                ],
            }
        ],
    }


def _resolution(*, name="Szentendrei-Duna", station=1026, status="UNRESOLVED"):
    candidate = {
        "source_provider": "OVF_VRAQUERY",
        "station_registry_number": str(station),
        "station_name": "Budapest" if station == 1026 else "Szentendre",
        "watercourse": "Duna" if station == 1026 else "Szentendrei-Duna",
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
                        "start_timestamp": "2026-08-29T06:00:00+02:00",
                        "water_level": {"value": 310, "unit": "cm"},
                        "discharge": {"value": 1200, "unit": "m3/s"},
                        "water_temperature": {"value": 20.5, "unit": "degC"},
                        "current_speed_estimate_mps": 1.7,
                    },
                    {
                        "segment_index": 1,
                        "start_timestamp": "2026-08-29T06:01:00+02:00",
                        "water_level": {"value": 311, "unit": "cm"},
                        "discharge": {"value": 1210, "unit": "m3/s"},
                        "current_speed_estimate_mps": 1.8,
                    },
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


def test_validation_catalog_is_explicitly_synthetic_and_validation_only():
    catalog = build_validation_hydrology_relation_catalog()
    assert catalog["provider"] == PROVIDER
    assert catalog["product"] == PRODUCT
    assert catalog["source_mode"] == "SYNTHETIC_VALIDATION_FIXTURE"
    assert catalog["jurisdiction"] == "VALIDATION_ONLY"
    assert catalog["metadata"]["validation_only"] is True
    assert catalog["metadata"]["synthetic"] is True
    assert catalog["metadata"]["real_world_hydrology_claim"] is False
    assert catalog["metadata"]["allowed_route_date"] == VALIDATION_ROUTE_DATE


def test_validation_catalog_authorizes_only_water_level():
    relation = build_validation_hydrology_relation_catalog()["relations"][0]
    decisions = {
        row["metric_key"]: row["transfer_allowed"] for row in relation["metrics"]
    }
    assert decisions == {
        "WATER_LEVEL": True,
        "DISCHARGE": False,
        "WATER_TEMPERATURE": False,
    }
    assert relation["valid_from"].startswith(VALIDATION_ROUTE_DATE)
    assert relation["valid_to"].startswith(VALIDATION_ROUTE_DATE)


def test_validation_provider_is_separated_from_production_provider_set():
    assert PROVIDER in VALIDATION_HYDROLOGY_RELATION_PROVIDERS
    assert PROVIDER in SUPPORTED_HYDROLOGY_RELATION_PROVIDERS
    assert PROVIDER not in PRODUCTION_HYDROLOGY_RELATION_PROVIDERS


def test_validation_provider_loader_requires_explicit_opt_in():
    with pytest.raises(ValueError, match="requires explicit validation mode"):
        load_hydrology_relation_catalog(PROVIDER)


def test_validation_provider_loader_returns_fixture_only_when_enabled():
    catalog = load_hydrology_relation_catalog(
        PROVIDER,
        allow_validation_provider=True,
    )
    assert catalog["provider"] == PROVIDER
    assert catalog["metadata"]["validation_only"] is True


def test_szentendre_1026_positive_control_supports_only_water_level_relation():
    result = build_route_hydrology_relation_evidence(
        _route_input(),
        _resolution(),
        build_validation_hydrology_relation_catalog(),
    )
    route = result["routes"][0]
    assert route["status"] == STATUS_SUPPORTED_WITH_LIMITATIONS
    decisions = {row["metric_key"]: row["decision"] for row in route["metric_relations"]}
    assert decisions["WATER_LEVEL"] == "TRANSFER_SUPPORTED"
    assert decisions["DISCHARGE"] == "TRANSFER_WITHHELD"
    assert decisions["WATER_TEMPERATURE"] == "TRANSFER_WITHHELD"
    assert route["selected_source_by_metric"].keys() == {"WATER_LEVEL"}


def test_validation_relation_does_not_apply_outside_the_locked_route_date():
    result = build_route_hydrology_relation_evidence(
        _route_input(timestamp="2026-08-30T06:00:00+02:00"),
        _resolution(),
        build_validation_hydrology_relation_catalog(),
    )
    route = result["routes"][0]
    assert route["status"] == STATUS_WITHHELD
    assert route["metric_relations"] == []
    assert route["selected_source_by_metric"] == {}


def test_validation_relation_does_not_apply_to_other_waterbody():
    result = build_route_hydrology_relation_evidence(
        _route_input(),
        _resolution(name="Ráckevei (Soroksári)-Duna"),
        build_validation_hydrology_relation_catalog(),
    )
    route = result["routes"][0]
    assert route["status"] == STATUS_WITHHELD
    assert route["metric_relations"] == []


def test_direct_szentendre_1038_still_bypasses_validation_relation():
    result = build_route_hydrology_relation_evidence(
        _route_input(),
        _resolution(station=1038, status="IDENTITY_SUPPORTED"),
        build_validation_hydrology_relation_catalog(),
    )
    assert result["routes"][0]["status"] == STATUS_NOT_REQUIRED


def test_live_projection_copies_water_level_but_not_discharge_temperature_or_current():
    result = build_route_hydrology_relation_live_projection(
        route_environment_context_input=_route_input(),
        route_hydrology_source_resolution=_resolution(),
        route_hydrology_context=_raw_context(),
        trusted_route_hydrology_context=_direct_withheld(),
        relation_catalog=build_validation_hydrology_relation_catalog(),
    )
    assert result["relation_derived_hydrology_in_use"] is True
    relation_route = result["relation_aware_trusted_route_hydrology_context"]["routes"][0]
    assert relation_route["trust_mode"] == "RELATION_DERIVED_METRIC_PROJECTION"
    assert relation_route["trust_status"] == "TRUSTED_WITH_LIMITATIONS"
    assert relation_route["authorized_metric_keys"] == ["WATER_LEVEL"]
    assert set(relation_route["withheld_metric_keys"]) == {
        "DISCHARGE",
        "WATER_TEMPERATURE",
    }
    segments = relation_route["trusted_context"]["segments"]
    assert len(segments) == 2
    assert all("water_level" in segment for segment in segments)
    assert all("discharge" not in segment for segment in segments)
    assert all("water_temperature" not in segment for segment in segments)
    assert all("current_speed_estimate_mps" not in segment for segment in segments)


def test_validation_catalog_builder_output_is_not_mutated_by_projection():
    catalog = build_validation_hydrology_relation_catalog()
    before = deepcopy(catalog)
    build_route_hydrology_relation_live_projection(
        route_environment_context_input=_route_input(),
        route_hydrology_source_resolution=_resolution(),
        route_hydrology_context=_raw_context(),
        trusted_route_hydrology_context=_direct_withheld(),
        relation_catalog=catalog,
    )
    assert catalog == before
