import copy
import uuid

import pytest

from app.db.base import Base
from app.models.entities import (
    RouteEnvironmentEvidenceSet,
    RouteEnvironmentHydrologyMeasurement,
    RouteEnvironmentRoute,
    RouteEnvironmentSegment,
    RouteEnvironmentWeatherSample,
)
from app.services.environment_evidence_persistence import (
    build_environment_persistence_plan,
)


def _evidence_record():
    return {
        "schema_version": "0.1",
        "session_external_id": "session-123",
        "provider": "POLAR",
        "available": True,
        "scope": {
            "estimates_local_current_velocity": False,
        },
        "source_catalog": {
            "weather_source": {
                "provider": "OPEN_METEO",
                "source_type": (
                    "MODELLED_HISTORICAL_WEATHER"
                ),
            },
            "weather_samples": [
                {
                    "sample_id": "weather-1",
                    "sample_timestamp": (
                        "2026-09-30T15:00:00+00:00"
                    ),
                    "latitude_deg": 47.52,
                    "longitude_deg": 19.04,
                    "elevation_m": 100.0,
                    "air_temperature_c": 18.0,
                    "wind_speed_mps": 1.25,
                    "wind_direction_from_deg": 350.0,
                    "wind_gust_mps": 2.0,
                    "source_provider": "OPEN_METEO",
                    "source_product": (
                        "HISTORICAL_WEATHER_API"
                    ),
                    "source_type": (
                        "MODELLED_HISTORICAL_WEATHER"
                    ),
                    "spatial_support": (
                        "GRIDDED_POINT_ESTIMATE"
                    ),
                    "temporal_resolution_seconds": 3600,
                    "source_reference": None,
                },
                {
                    "sample_id": "weather-1",
                    "sample_timestamp": (
                        "2026-09-30T15:00:00+00:00"
                    ),
                    "source_provider": "OPEN_METEO",
                },
            ],
            "hydrology_source": {
                "provider": "OVF_VRAQUERY",
                "source_type": (
                    "OPERATIONAL_HYDROLOGY_OBSERVATION"
                ),
            },
            "hydrology_measurements": [
                {
                    "measurement_id": "level-1",
                    "observed_at": (
                        "2026-09-30T15:30:00+00:00"
                    ),
                    "metric_code": 68,
                    "metric_key": "WATER_LEVEL",
                    "value": 14.0,
                    "unit": "cm",
                    "data_type_code": 101,
                    "source_provider": "OVF_VRAQUERY",
                    "source_product": "VRAQUERY_OPENAPI",
                    "source_type": (
                        "OPERATIONAL_HYDROLOGY_OBSERVATION"
                    ),
                    "station": {
                        "station_registry_number": 1026,
                        "station_name": "Budapest",
                        "watercourse": "Duna",
                        "municipality": "Budapest",
                        "latitude_deg": 47.5,
                        "longitude_deg": 19.04,
                        "river_km": 1646.5,
                    },
                },
                {
                    "measurement_id": "q-1",
                    "observed_at": (
                        "2026-09-30T15:30:00+00:00"
                    ),
                    "metric_code": 87,
                    "metric_key": "DISCHARGE",
                    "value": 754.0,
                    "unit": "m3/s",
                    "data_type_code": 101,
                    "source_provider": "OVF_VRAQUERY",
                    "station": {
                        "station_registry_number": 1026,
                        "station_name": "Budapest",
                        "watercourse": "Duna",
                    },
                },
            ],
        },
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "quality_provenance": {
                    "artifact_policy": {
                        "action": "EXCLUDE",
                    },
                },
                "time_context": {
                    "absolute_timestamps_resolved": True,
                },
                "route_semantics": {
                    "actual_traversed_path_is_primary_evidence": True,
                    "same_flow_line_across_traversals_assumed": False,
                },
                "segments": [
                    {
                        "record_id": (
                            "session-123:r0:e0:"
                            "wp46:wp47:t129763:t130763"
                        ),
                        "order_index": 0,
                        "source_locator": {
                            "view_segment_index": 0,
                            "segment_index_scope": "VIEW_LOCAL",
                            "source_segment_index": 46,
                            "source_segment_index_scope": (
                                "NORMALIZED_ROUTE_SOURCE"
                            ),
                            "source_segment_index_status": (
                                "DIRECT_FROM_CONSECUTIVE_"
                                "SOURCE_WAYPOINTS"
                            ),
                            "source_waypoint_contiguous": True,
                            "start_waypoint_index": 46,
                            "end_waypoint_index": 47,
                            "start_exercise_elapsed_ms": 129763,
                            "end_exercise_elapsed_ms": 130763,
                            "start_timestamp": (
                                "2026-09-30T17:37:27.763+02:00"
                            ),
                            "midpoint_timestamp": (
                                "2026-09-30T17:37:28.263+02:00"
                            ),
                            "end_timestamp": (
                                "2026-09-30T17:37:28.763+02:00"
                            ),
                        },
                        "actual_path_evidence": {
                            "start_position": {
                                "latitude_deg": 47.52,
                                "longitude_deg": 19.04,
                            },
                            "end_position": {
                                "latitude_deg": 47.52001,
                                "longitude_deg": 19.04001,
                            },
                            "surface_distance_m": 2.8,
                            "movement_bearing_deg": 10.0,
                            "position_status": (
                                "ENDPOINT_POSITIONS_AVAILABLE"
                            ),
                        },
                        "external_motion": {
                            "gps_ground_speed_mps": 2.8,
                            "ground_speed_change_rate_mps2": 0.1,
                            "cumulative_trusted_surface_distance_m": 2.8,
                        },
                        "weather": {
                            "match_available": True,
                            "match_status": "MATCHED",
                            "sample_id": "weather-1",
                            "absolute_time_delta_seconds": 2248.263,
                            "surface_distance_to_sample_m": 100.0,
                        },
                        "wind_physics": {
                            "available": True,
                            "status": "AVAILABLE",
                            "headwind_component_mps": 1.0,
                            "tailwind_component_mps": 0.0,
                            "crosswind_magnitude_mps": 0.5,
                            "relative_air_velocity_along_course_mps": -3.8,
                            "relative_air_velocity_cross_course_mps": 0.5,
                            "relative_air_speed_mps": 3.83,
                        },
                        "hydrology": {
                            "station_surface_distance_m": 2200.0,
                            "water_level": {
                                "available": True,
                                "status": "MATCHED",
                                "measurement_id": "level-1",
                                "absolute_time_delta_seconds": 448.263,
                            },
                            "discharge": {
                                "available": True,
                                "status": "MATCHED",
                                "measurement_id": "q-1",
                                "absolute_time_delta_seconds": 448.263,
                            },
                            "water_temperature": {
                                "available": False,
                                "status": "MEASUREMENT_UNAVAILABLE",
                                "measurement_id": None,
                            },
                            "current_speed_estimate_mps": None,
                            "current_direction_deg": None,
                        },
                        "waterbody_identity": {
                            "status": "UNRESOLVED",
                            "waterbody_id": None,
                            "river_reach_id": None,
                            "flow_relation": None,
                            "route_corridor_id": None,
                        },
                        "route_choice_context": {
                            "status": "UNOBSERVED",
                            "route_choice_intent": None,
                            "group_tactical_context": None,
                            "preferred_flow_line": None,
                        },
                    }
                ],
            }
        ],
    }


def test_environment_tables_are_registered_in_metadata():
    expected = {
        "route_environment_evidence_sets",
        "route_environment_routes",
        "route_environment_weather_samples",
        "route_environment_hydrology_measurements",
        "route_environment_segments",
    }

    assert expected.issubset(
        Base.metadata.tables
    )

    assert (
        RouteEnvironmentEvidenceSet.__table__.name
        == "route_environment_evidence_sets"
    )
    assert (
        RouteEnvironmentRoute.__table__.name
        == "route_environment_routes"
    )
    assert (
        RouteEnvironmentWeatherSample.__table__.name
        == "route_environment_weather_samples"
    )
    assert (
        RouteEnvironmentHydrologyMeasurement.__table__.name
        == "route_environment_hydrology_measurements"
    )
    assert (
        RouteEnvironmentSegment.__table__.name
        == "route_environment_segments"
    )


def test_plan_deduplicates_source_catalog_but_keeps_segment_reference():
    plan = build_environment_persistence_plan(
        _evidence_record()
    )

    assert len(
        plan[
            "weather_samples"
        ]
    ) == 1

    assert len(
        plan[
            "hydrology_measurements"
        ]
    ) == 2

    segment = plan[
        "routes"
    ][0][
        "segments"
    ][0]

    assert (
        segment[
            "weather_sample_key"
        ]
        == "weather-1"
    )
    assert (
        segment[
            "water_level_measurement_key"
        ]
        == "level-1"
    )
    assert (
        segment[
            "discharge_measurement_key"
        ]
        == "q-1"
    )


def test_plan_preserves_source_and_view_segment_identity():
    plan = build_environment_persistence_plan(
        _evidence_record()
    )

    segment = plan[
        "routes"
    ][0][
        "segments"
    ][0]

    assert segment["view_segment_index"] == 0
    assert segment["segment_index_scope"] == "VIEW_LOCAL"
    assert segment["source_segment_index"] == 46
    assert (
        segment[
            "source_segment_index_scope"
        ]
        == "NORMALIZED_ROUTE_SOURCE"
    )
    assert segment["source_waypoint_contiguous"] is True


def test_plan_keeps_segment_specific_wind_but_not_duplicate_weather_payload():
    plan = build_environment_persistence_plan(
        _evidence_record()
    )

    segment = plan[
        "routes"
    ][0][
        "segments"
    ][0]

    assert segment["headwind_component_mps"] == 1.0
    assert segment["relative_air_speed_mps"] == 3.83

    assert "wind_speed_mps" not in segment
    assert "air_temperature_c" not in segment


def test_plan_hash_is_stable_for_equivalent_dict_order():
    record = _evidence_record()
    reordered = copy.deepcopy(
        record
    )

    reordered["scope"] = {
        key: reordered[
            "scope"
        ][key]
        for key in reversed(
            list(
                reordered[
                    "scope"
                ]
            )
        )
    }

    first = build_environment_persistence_plan(
        record
    )[
        "evidence_hash"
    ]

    second = build_environment_persistence_plan(
        reordered
    )[
        "evidence_hash"
    ]

    assert first == second
    assert len(first) == 64


def test_plan_rejects_segment_reference_missing_from_weather_catalog():
    record = _evidence_record()
    record[
        "source_catalog"
    ][
        "weather_samples"
    ] = []

    with pytest.raises(
        ValueError,
        match="not present in source catalog",
    ):
        build_environment_persistence_plan(
            record
        )


def test_plan_preserves_hydrology_station_and_provider_codes_as_strings():
    plan = build_environment_persistence_plan(
        _evidence_record()
    )

    level = next(
        item
        for item in plan[
            "hydrology_measurements"
        ]
        if item[
            "metric_key"
        ]
        == "WATER_LEVEL"
    )

    assert level["station_registry_id"] == "1026"
    assert level["watercourse"] == "Duna"
    assert level["metric_code"] == "68"
    assert level["provider_data_type"] == "101"


def test_model_unique_constraints_cover_snapshot_and_source_deduplication():
    evidence_constraints = {
        constraint.name
        for constraint
        in RouteEnvironmentEvidenceSet.__table__.constraints
        if constraint.name
    }

    weather_constraints = {
        constraint.name
        for constraint
        in RouteEnvironmentWeatherSample.__table__.constraints
        if constraint.name
    }

    hydrology_constraints = {
        constraint.name
        for constraint
        in RouteEnvironmentHydrologyMeasurement.__table__.constraints
        if constraint.name
    }

    segment_constraints = {
        constraint.name
        for constraint
        in RouteEnvironmentSegment.__table__.constraints
        if constraint.name
    }

    assert (
        "uq_route_environment_session_hash"
        in evidence_constraints
    )
    assert (
        "uq_route_environment_weather_source"
        in weather_constraints
    )
    assert (
        "uq_route_environment_hydrology_source"
        in hydrology_constraints
    )
    assert (
        "uq_route_environment_segment_record"
        in segment_constraints
    )



def test_hash_ignores_volatile_provider_runtime_metadata():
    first_record = _evidence_record()
    second_record = copy.deepcopy(
        first_record
    )

    first_record[
        "source_catalog"
    ][
        "weather_source"
    ][
        "provider_metadata"
    ] = {
        "generationtime_ms": 0.421,
        "timezone": "GMT",
    }

    second_record[
        "source_catalog"
    ][
        "weather_source"
    ][
        "provider_metadata"
    ] = {
        "generationtime_ms": 8.917,
        "timezone": "GMT",
    }

    first = build_environment_persistence_plan(
        first_record
    )
    second = build_environment_persistence_plan(
        second_record
    )

    assert first["evidence_hash"] == second["evidence_hash"]
    assert (
        first[
            "source_summary"
        ][
            "weather_source"
        ][
            "provider_metadata"
        ][
            "generationtime_ms"
        ]
        != second[
            "source_summary"
        ][
            "weather_source"
        ][
            "provider_metadata"
        ][
            "generationtime_ms"
        ]
    )
    assert first["hash_semantics_version"] == "1"


def test_hash_changes_when_actual_weather_evidence_changes():
    first_record = _evidence_record()
    second_record = copy.deepcopy(
        first_record
    )

    # The fixture intentionally contains a duplicate sample_id;
    # persistence keeps the last normalized row for that id.
    second_record[
        "source_catalog"
    ][
        "weather_samples"
    ][-1][
        "wind_speed_mps"
    ] = 1.75

    first_hash = (
        build_environment_persistence_plan(
            first_record
        )[
            "evidence_hash"
        ]
    )
    second_hash = (
        build_environment_persistence_plan(
            second_record
        )[
            "evidence_hash"
        ]
    )

    assert first_hash != second_hash


def test_hash_changes_when_actual_hydrology_evidence_changes():
    first_record = _evidence_record()
    second_record = copy.deepcopy(
        first_record
    )

    second_record[
        "source_catalog"
    ][
        "hydrology_measurements"
    ][0][
        "value"
    ] = 15.0

    first_hash = (
        build_environment_persistence_plan(
            first_record
        )[
            "evidence_hash"
        ]
    )
    second_hash = (
        build_environment_persistence_plan(
            second_record
        )[
            "evidence_hash"
        ]
    )

    assert first_hash != second_hash
