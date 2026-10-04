from app.services.route_environment_evidence_record import (
    build_route_environment_evidence_record,
    build_route_environment_evidence_record_summary,
)


def _environment():
    return {
        "provider": "POLAR",
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
                "segments": [
                    {
                        "order_index": 0,
                        "segment_index": 46,
                        "start_waypoint_index": 46,
                        "end_waypoint_index": 47,
                        "start_exercise_elapsed_ms": 129_763,
                        "segment_midpoint_exercise_elapsed_ms": 130_263.5,
                        "end_exercise_elapsed_ms": 130_764,
                        "start_timestamp": "2026-09-30T17:37:27.763000+02:00",
                        "midpoint_timestamp": "2026-09-30T17:37:28.263500+02:00",
                        "end_timestamp": "2026-09-30T17:37:28.764000+02:00",
                        "start_position": {
                            "waypoint_index": 46,
                            "latitude_deg": 47.52,
                            "longitude_deg": 19.04,
                        },
                        "end_position": {
                            "waypoint_index": 47,
                            "latitude_deg": 47.52001,
                            "longitude_deg": 19.04001,
                        },
                        "position_status": "ENDPOINT_POSITIONS_AVAILABLE",
                        "movement_bearing_deg": 10.0,
                        "gps_ground_speed_mps": 3.0,
                        "ground_speed_change_rate_mps2": 0.2,
                    }
                ],
            }
        ],
    }


def _external():
    return {
        "provider": "POLAR",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "observations": [
                    {
                        "order_index": 0,
                        "segment_index": 46,
                        "surface_distance_m": 3.0,
                        "cumulative_trusted_surface_distance_m": 3.0,
                    }
                ],
            }
        ],
    }


def _weather_source():
    sample = {
        "sample_id": "weather-1",
        "sample_timestamp": "2026-09-30T15:00:00+00:00",
        "wind_speed_mps": 1.2,
        "wind_direction_from_deg": 350.0,
        "source_provider": "OPEN_METEO",
    }

    return {
        "provider": "OPEN_METEO",
        "source_type": "MODELLED_HISTORICAL_WEATHER",
        "samples": [
            sample,
            dict(sample),
        ],
    }


def _weather_matching():
    return {
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "matches": [
                    {
                        "order_index": 0,
                        "segment_index": 46,
                        "available": True,
                        "status": "MATCHED",
                        "matched_sample_id": "weather-1",
                        "absolute_time_delta_seconds": 148.0,
                        "surface_distance_to_sample_m": 120.0,
                    }
                ],
            }
        ],
    }


def _wind():
    return {
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "segments": [
                    {
                        "order_index": 0,
                        "segment_index": 46,
                        "available": True,
                        "status": "AVAILABLE",
                        "headwind_component_mps": 0.4,
                        "tailwind_component_mps": 0.0,
                        "crosswind_magnitude_mps": 1.1,
                        "relative_air_velocity_along_course_mps": -3.4,
                        "relative_air_velocity_cross_course_mps": 1.1,
                        "relative_air_speed_mps": 3.57,
                    }
                ],
            }
        ],
    }


def _hydrology_source():
    measurement = {
        "measurement_id": "level-1",
        "observed_at": "2026-09-30T15:30:00+00:00",
        "metric_key": "WATER_LEVEL",
        "value": 14.0,
        "unit": "cm",
        "source_provider": "OVF_VRAQUERY",
    }

    return {
        "provider": "OVF_VRAQUERY",
        "station": {
            "station_registry_number": 1026,
            "station_name": "Budapest",
            "watercourse": "Duna",
        },
        "measurements": [
            measurement,
            dict(measurement),
            {
                "measurement_id": "q-1",
                "observed_at": "2026-09-30T15:30:00+00:00",
                "metric_key": "DISCHARGE",
                "value": 754.0,
                "unit": "m3/s",
            },
        ],
    }


def _hydrology():
    return {
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "segments": [
                    {
                        "order_index": 0,
                        "segment_index": 46,
                        "station_surface_distance_m": 2200.0,
                        "water_level": {
                            "available": True,
                            "status": "MATCHED",
                            "measurement_id": "level-1",
                            "observed_at": "2026-09-30T15:30:00+00:00",
                            "absolute_time_delta_seconds": 448.0,
                            "value": 14.0,
                            "unit": "cm",
                            "data_type_code": 101,
                        },
                        "discharge": {
                            "available": True,
                            "status": "MATCHED",
                            "measurement_id": "q-1",
                            "observed_at": "2026-09-30T15:30:00+00:00",
                            "absolute_time_delta_seconds": 448.0,
                            "value": 754.0,
                            "unit": "m3/s",
                            "data_type_code": 101,
                        },
                        "water_temperature": {
                            "available": False,
                            "status": "MEASUREMENT_UNAVAILABLE",
                        },
                        "current_speed_estimate_mps": None,
                        "current_direction_deg": None,
                    }
                ],
            }
        ],
    }


def _build():
    return build_route_environment_evidence_record(
        session_external_id="session-123",
        route_environment_context_input=_environment(),
        route_external_workload_evidence=_external(),
        route_weather_sample_matching=_weather_matching(),
        route_wind_context=_wind(),
        weather_source=_weather_source(),
        route_hydrology_context=_hydrology(),
        hydrology_source=_hydrology_source(),
    )


def test_preserves_actual_traversed_path_as_primary_evidence():
    result = _build()
    route = result["routes"][0]
    segment = route["segments"][0]

    assert (
        route["route_semantics"][
            "actual_traversed_path_is_primary_evidence"
        ]
        is True
    )
    assert (
        segment["source_locator"]["start_waypoint_index"]
        == 46
    )
    assert (
        segment["actual_path_evidence"]["start_position"]["latitude_deg"]
        == 47.52
    )
    assert (
        segment["actual_path_evidence"]["surface_distance_m"]
        == 3.0
    )


def test_does_not_assume_same_flow_line_or_use_half_speed_difference_as_current():
    route = _build()["routes"][0]

    semantics = route["route_semantics"]

    assert semantics["same_flow_line_across_traversals_assumed"] is False
    assert semantics["same_hydraulic_exposure_for_same_reach_assumed"] is False
    assert (
        semantics[
            "upstream_downstream_half_speed_difference_used_as_current_estimate"
        ]
        is False
    )
    assert semantics["route_choice_intent_inferred"] is False
    assert semantics["group_tactical_context_inferred"] is False


def test_waterbody_and_route_choice_identity_remain_explicitly_unresolved():
    segment = _build()["routes"][0]["segments"][0]

    assert segment["waterbody_identity"] == {
        "status": "UNRESOLVED",
        "waterbody_id": None,
        "river_reach_id": None,
        "flow_relation": None,
        "route_corridor_id": None,
    }
    assert segment["route_choice_context"]["status"] == "UNOBSERVED"
    assert segment["route_choice_context"]["route_choice_intent"] is None


def test_weather_and_hydrology_catalogs_are_deduplicated():
    result = _build()
    catalog = result["source_catalog"]

    assert len(catalog["weather_samples"]) == 1
    assert len(catalog["hydrology_measurements"]) == 2


def test_segment_references_environmental_evidence_without_current_inference():
    segment = _build()["routes"][0]["segments"][0]

    assert segment["weather"]["sample_id"] == "weather-1"
    assert segment["wind_physics"]["relative_air_speed_mps"] == 3.57
    assert segment["hydrology"]["water_level"]["measurement_id"] == "level-1"
    assert segment["hydrology"]["discharge"]["measurement_id"] == "q-1"
    assert segment["hydrology"]["current_speed_estimate_mps"] is None
    assert segment["hydrology"]["current_direction_deg"] is None


def test_record_id_uses_path_and_time_locator_not_only_segment_index():
    segment = _build()["routes"][0]["segments"][0]

    assert segment["record_id"] == (
        "session-123:r0:e0:"
        "wp46:wp47:t129763:t130764"
    )


def test_summary_strips_segment_and_catalog_payloads():
    summary = build_route_environment_evidence_record_summary(
        _build()
    )

    route = summary["routes"][0]
    catalog = summary["source_catalog"]

    assert "segments" not in route
    assert route["segments_included"] is False
    assert route["segment_payload_count"] == 1

    assert catalog["payloads_included"] is False
    assert catalog["weather_sample_count"] == 1
    assert catalog["hydrology_measurement_count"] == 2
    assert "weather_samples" not in catalog
    assert "hydrology_measurements" not in catalog
