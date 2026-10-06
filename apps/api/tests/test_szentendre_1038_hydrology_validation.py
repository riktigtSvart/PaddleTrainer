from __future__ import annotations

from copy import deepcopy

from app.services.route_hydrology_representativeness import (
    build_route_hydrology_representativeness,
)
from app.services.route_hydrology_source_resolution import (
    build_route_hydrology_source_resolution,
)


def _szentendre_water_identity() -> dict:
    return {
        "provider": "PADDLETRAINER",
        "schema_version": "0.1",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "river_inland_segment_count": 3,
                "marine_segment_count": 0,
                "ambiguous_environment_segment_count": 0,
                "mixed_environment_route": False,
                "river_inland_identities": [
                    {
                        "source_provider": "EEA_WISE_WFD",
                        "source_product": (
                            "WFD2022_SURFACE_WATER_BODY_CENTRELINE"
                        ),
                        "waterbody_id": "HUAOC756",
                        "waterbody_type": "RIVER",
                        "waterbody_name": "Szentendrei-Duna",
                        "source_feature_ids": ["HU:HUAAB333_5"],
                        "source_feature_names": ["Szentendrei-Duna"],
                    }
                ],
            }
        ],
    }


def _station_source(
    *,
    registry_number: int,
    station_name: str,
    watercourse: str,
    river_km: float,
    measurements: list[dict] | None = None,
) -> dict:
    station = {
        "station_registry_number": registry_number,
        "station_name": station_name,
        "watercourse": watercourse,
        "municipality": station_name,
        "latitude_deg": 47.67,
        "longitude_deg": 19.08,
        "river_km": river_km,
    }
    result = {
        "provider": "OVF_VRAQUERY",
        "product": "VRA_SHORT_SERIES",
        "source_type": "OPERATIONAL_HYDROLOGY_OBSERVATION",
        "station": deepcopy(station),
        "measurements": [],
    }
    for measurement in measurements or []:
        item = deepcopy(measurement)
        item["station"] = deepcopy(station)
        result["measurements"].append(item)
    return result


def _route_environment_context_input() -> dict:
    return {
        "schema_version": "0.1",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "segments": [
                    {
                        "order_index": 0,
                        "midpoint_timestamp": "2026-08-29T12:00:00+02:00",
                        "start_position": {
                            "latitude_deg": 47.66,
                            "longitude_deg": 19.08,
                        },
                        "end_position": {
                            "latitude_deg": 47.661,
                            "longitude_deg": 19.081,
                        },
                    },
                    {
                        "order_index": 1,
                        "midpoint_timestamp": "2026-08-29T12:10:00+02:00",
                        "start_position": {
                            "latitude_deg": 47.661,
                            "longitude_deg": 19.081,
                        },
                        "end_position": {
                            "latitude_deg": 47.662,
                            "longitude_deg": 19.082,
                        },
                    },
                    {
                        "order_index": 2,
                        "midpoint_timestamp": "2026-08-29T12:20:00+02:00",
                        "start_position": {
                            "latitude_deg": 47.662,
                            "longitude_deg": 19.082,
                        },
                        "end_position": {
                            "latitude_deg": 47.663,
                            "longitude_deg": 19.083,
                        },
                    },
                ],
            }
        ],
    }


def test_szentendre_1038_exact_watercourse_identity_is_supported():
    source = _station_source(
        registry_number=1038,
        station_name="Szentendre",
        watercourse="Szentendrei-Duna",
        river_km=10.8,
    )

    result = build_route_hydrology_source_resolution(
        _szentendre_water_identity(),
        source,
    )

    assert result["status"] == "IDENTITY_SUPPORTED"
    route = result["routes"][0]
    assert route["status"] == "IDENTITY_SUPPORTED"
    assert route["resolved_hydrology_source"][
        "station_registry_number"
    ] == "1038"
    assert route["resolved_hydrology_source"][
        "watercourse"
    ] == "Szentendrei-Duna"
    assert (
        "SINGLE_HYDROLOGY_STATION_WATERCOURSE_IDENTITY_MATCH"
        in route["resolution_basis"]
    )
    assert (
        "NO_AUTHORITATIVE_WATERBODY_STATION_CROSSWALK_CLAIMED"
        in route["resolution_basis"]
    )


def test_szentendre_1038_water_level_only_supports_partial_representativeness():
    source = _station_source(
        registry_number=1038,
        station_name="Szentendre",
        watercourse="Szentendrei-Duna",
        river_km=10.8,
        measurements=[
            {
                "observed_at": "2026-08-29T12:00:00+02:00",
                "metric_key": "WATER_LEVEL",
                "value": -72.0,
                "unit": "cm",
            },
            {
                "observed_at": "2026-08-29T13:00:00+02:00",
                "metric_key": "WATER_LEVEL",
                "value": -72.0,
                "unit": "cm",
            },
        ],
    )
    resolution = build_route_hydrology_source_resolution(
        _szentendre_water_identity(),
        source,
    )

    result = build_route_hydrology_representativeness(
        _route_environment_context_input(),
        resolution,
        source,
    )

    assert result["status"] == "PARTIALLY_REPRESENTATIVE"
    route = result["routes"][0]
    assert route["status"] == "PARTIALLY_REPRESENTATIVE"
    assert route["station_identity_supported"] is True
    assert route["authoritative_reach_crosswalk_available"] is False
    assert route["temporal_evidence"]["matching_measurement_count"] == 2
    assert route["temporal_evidence"][
        "temporally_supported_segment_count"
    ] == 3
    assert route["temporal_evidence"][
        "temporally_supported_segment_fraction"
    ] == 1.0
    assert [
        row["metric_key"]
        for row in route["temporal_evidence"]["metric_coverage"]
    ] == ["WATER_LEVEL"]
    assert (
        "NO_AUTHORITATIVE_ROUTE_REACH_TO_STATION_CROSSWALK"
        in route["limitations"]
    )
    assert result["scope"]["infers_current_from_water_level"] is False
    assert result["scope"]["infers_current_from_discharge"] is False
    assert result["scope"]["estimates_local_current_velocity"] is False


def test_budapest_1026_remains_negative_control_for_szentendrei_duna():
    source = _station_source(
        registry_number=1026,
        station_name="Budapest",
        watercourse="Duna",
        river_km=1646.5,
    )

    result = build_route_hydrology_source_resolution(
        _szentendre_water_identity(),
        source,
    )

    assert result["status"] == "UNRESOLVED"
    route = result["routes"][0]
    assert route["status"] == "UNRESOLVED"
    assert route["resolved_hydrology_source"] is None
    assert route["evaluated_candidates"][0][
        "identity_compatibility"
    ] == "IDENTITY_CONFLICT"
    assert (
        "NO_HYDROLOGY_STATION_WATERCOURSE_IDENTITY_MATCH"
        in route["resolution_basis"]
    )
    assert (
        "NEAREST_STATION_NOT_ACCEPTED_AS_IDENTITY_PROOF"
        in route["resolution_basis"]
    )
