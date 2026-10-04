from app.services.route_environment_context_input import (
    STATUS_ENDPOINT_POSITIONS_AVAILABLE,
    build_route_environment_context_input,
    build_route_environment_context_input_summary,
)


def _trusted_normalized():
    return {
        "provider": "POLAR",
        "route_count": 1,
        "routes": [
            {
                "exercise_index": 0,
                "points": [
                    {
                        "waypoint_index": 46,
                        "exercise_elapsed_ms": 129_763,
                        "latitude_deg": 47.52,
                        "longitude_deg": 19.04,
                        "altitude_m": 92.0,
                    },
                    {
                        "waypoint_index": 47,
                        "exercise_elapsed_ms": 130_763,
                        "latitude_deg": 47.52001,
                        "longitude_deg": 19.04001,
                        "altitude_m": 92.5,
                    },
                    {
                        "waypoint_index": 48,
                        "exercise_elapsed_ms": 131_763,
                        "latitude_deg": 47.52002,
                        "longitude_deg": 19.04002,
                        "altitude_m": 93.0,
                    },
                ],
            }
        ],
    }


def _external():
    return {
        "provider": "POLAR",
        "evidence_version": "0.1",
        "available": True,
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "available": True,
                "reason": None,
                "usable_interval": {
                    "start_exercise_elapsed_ms": 129_763,
                    "end_exercise_elapsed_ms": 131_763,
                },
                "quality_provenance": {
                    "artifact_policy": {
                        "action": "EXCLUDE",
                    },
                },
                "observations": [
                    {
                        "order_index": 0,
                        "segment_index": 46,
                        "start_waypoint_index": 46,
                        "end_waypoint_index": 47,
                        "start_exercise_elapsed_ms": 129_763,
                        "segment_midpoint_exercise_elapsed_ms": 130_263.0,
                        "end_exercise_elapsed_ms": 130_763,
                        "gps_ground_speed_mps": 2.5,
                        "ground_speed_change_rate_mps2": None,
                        "initial_bearing_deg": 10.0,
                        "absolute_bearing_change_from_previous_deg": None,
                    },
                    {
                        "order_index": 1,
                        "segment_index": 47,
                        "start_waypoint_index": 47,
                        "end_waypoint_index": 48,
                        "start_exercise_elapsed_ms": 130_763,
                        "segment_midpoint_exercise_elapsed_ms": 131_263.0,
                        "end_exercise_elapsed_ms": 131_763,
                        "gps_ground_speed_mps": 2.8,
                        "ground_speed_change_rate_mps2": 0.3,
                        "initial_bearing_deg": 12.0,
                        "absolute_bearing_change_from_previous_deg": 2.0,
                    },
                ],
            }
        ],
    }


def test_joins_segment_endpoints_to_trusted_positions():
    result = build_route_environment_context_input(
        _trusted_normalized(),
        _external(),
        session_time_context={
            "exercise_start_time": (
                "2026-09-30T17:35:18"
            ),
            "timezone_offset_minutes": 120,
        },
    )

    route = result["routes"][0]
    first = route["segments"][0]

    assert route["position_complete_segment_count"] == 2
    assert (
        first["position_status"]
        == STATUS_ENDPOINT_POSITIONS_AVAILABLE
    )
    assert first["start_position"] == {
        "waypoint_index": 46,
        "exercise_elapsed_ms": 129_763,
        "latitude_deg": 47.52,
        "longitude_deg": 19.04,
        "altitude_m": 92.0,
    }
    assert (
        first["end_position"]["waypoint_index"]
        == 47
    )


def test_resolves_offset_aware_segment_timestamps_without_reinterpreting_elapsed_time():
    result = build_route_environment_context_input(
        _trusted_normalized(),
        _external(),
        session_time_context={
            "exercise_start_time": (
                "2026-09-30T17:35:18"
            ),
            "timezone_offset_minutes": 120,
        },
    )

    first = result["routes"][0]["segments"][0]

    assert (
        first["start_timestamp"]
        == "2026-09-30T17:37:27.763000+02:00"
    )
    assert (
        first["midpoint_timestamp"]
        == "2026-09-30T17:37:28.263000+02:00"
    )
    assert (
        first["end_timestamp"]
        == "2026-09-30T17:37:28.763000+02:00"
    )


def test_timezone_aware_input_start_time_takes_precedence_over_offset_hint():
    result = build_route_environment_context_input(
        _trusted_normalized(),
        _external(),
        session_time_context={
            "exercise_start_time": (
                "2026-09-30T17:35:18+01:00"
            ),
            "timezone_offset_minutes": 120,
        },
    )

    start = result["routes"][0][
        "time_context"
    ][
        "resolved_exercise_start_timestamp"
    ]

    assert (
        start
        == "2026-09-30T17:35:18+01:00"
    )


def test_naive_start_without_offset_does_not_invent_absolute_timestamps():
    result = build_route_environment_context_input(
        _trusted_normalized(),
        _external(),
        session_time_context={
            "exercise_start_time": (
                "2026-09-30T17:35:18"
            ),
        },
    )

    route = result["routes"][0]

    assert (
        route["time_context"][
            "absolute_timestamps_resolved"
        ]
        is False
    )
    assert (
        route["segments"][0][
            "start_timestamp"
        ]
        is None
    )


def test_scope_explicitly_contains_no_environmental_interpretation_yet():
    result = build_route_environment_context_input(
        _trusted_normalized(),
        _external(),
    )

    assert result["scope"] == {
        "domain": (
            "ENVIRONMENTAL_ENRICHMENT_INPUT"
        ),
        "contains_weather": False,
        "contains_hydrology": False,
        "contains_current_estimate": False,
        "contains_wind_adjustment": False,
        "contains_physiological_interpretation": False,
        "interpolates_position": False,
        "raw_data_mutated": False,
    }


def test_summary_strips_segment_payload():
    result = build_route_environment_context_input(
        _trusted_normalized(),
        _external(),
    )

    summary = (
        build_route_environment_context_input_summary(
            result
        )
    )

    route = summary["routes"][0]

    assert "segments" not in route
    assert route["segments_included"] is False
    assert route["segment_payload_count"] == 2



def test_fractional_millisecond_midpoint_resolves_timestamp():
    external = _external()

    external["routes"][0]["observations"][0][
        "segment_midpoint_exercise_elapsed_ms"
    ] = 130_263.5

    result = build_route_environment_context_input(
        _trusted_normalized(),
        external,
        session_time_context={
            "exercise_start_time": (
                "2026-09-30T17:35:18"
            ),
            "timezone_offset_minutes": 120,
        },
    )

    first = result["routes"][0]["segments"][0]

    assert (
        first["midpoint_timestamp"]
        == "2026-09-30T17:37:28.263500+02:00"
    )


def test_timestamp_completeness_counts_fractional_midpoints():
    external = _external()

    external["routes"][0]["observations"][0][
        "segment_midpoint_exercise_elapsed_ms"
    ] = 130_263.5

    result = build_route_environment_context_input(
        _trusted_normalized(),
        external,
        session_time_context={
            "exercise_start_time": (
                "2026-09-30T17:35:18"
            ),
            "timezone_offset_minutes": 120,
        },
    )

    route = result["routes"][0]

    assert route["segment_count"] == 2
    assert (
        route["timestamp_complete_segment_count"]
        == 2
    )
