import pytest

from app.services.route_wind_context import (
    STATUS_AVAILABLE,
    STATUS_MOVEMENT_BEARING_UNAVAILABLE,
    build_route_wind_context,
    build_route_wind_context_summary,
)


def _environment(
    *,
    bearing=0.0,
    speed=3.0,
):
    return {
        "provider": "POLAR",
        "schema_version": "0.1",
        "available": True,
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "available": True,
                "usable_interval": {
                    "start_exercise_elapsed_ms": 1000,
                    "end_exercise_elapsed_ms": 2000,
                },
                "segments": [
                    {
                        "order_index": 0,
                        "segment_index": 10,
                        "start_exercise_elapsed_ms": 1000,
                        "segment_midpoint_exercise_elapsed_ms": 1500.0,
                        "end_exercise_elapsed_ms": 2000,
                        "midpoint_timestamp": (
                            "2026-09-30T17:35:19.500000+02:00"
                        ),
                        "start_position": {
                            "latitude_deg": 47.5,
                            "longitude_deg": 19.0,
                        },
                        "end_position": {
                            "latitude_deg": 47.5001,
                            "longitude_deg": 19.0,
                        },
                        "movement_bearing_deg": bearing,
                        "gps_ground_speed_mps": speed,
                    }
                ],
            }
        ],
    }


def _wind(
    speed,
    direction_from,
):
    return {
        "wind_speed_mps": speed,
        "wind_direction_from_deg": direction_from,
        "source": "TEST",
    }


def test_headwind_north_course_north_wind():
    result = build_route_wind_context(
        _environment(
            bearing=0.0,
            speed=3.0,
        ),
        default_weather_sample=(
            _wind(
                5.0,
                0.0,
            )
        ),
    )

    segment = result["routes"][0][
        "segments"
    ][0]

    assert segment["status"] == STATUS_AVAILABLE
    assert (
        segment[
            "wind_along_course_mps"
        ]
        == pytest.approx(
            -5.0
        )
    )
    assert (
        segment[
            "headwind_component_mps"
        ]
        == pytest.approx(
            5.0
        )
    )
    assert (
        segment[
            "relative_air_velocity_along_course_mps"
        ]
        == pytest.approx(
            -8.0
        )
    )
    assert (
        segment[
            "relative_air_speed_mps"
        ]
        == pytest.approx(
            8.0
        )
    )


def test_tailwind_can_reduce_or_reverse_relative_airflow():
    result = build_route_wind_context(
        _environment(
            bearing=0.0,
            speed=3.0,
        ),
        default_weather_sample=(
            _wind(
                5.0,
                180.0,
            )
        ),
    )

    segment = result["routes"][0][
        "segments"
    ][0]

    assert (
        segment[
            "wind_along_course_mps"
        ]
        == pytest.approx(
            5.0
        )
    )
    assert (
        segment[
            "tailwind_component_mps"
        ]
        == pytest.approx(
            5.0
        )
    )
    assert (
        segment[
            "relative_air_velocity_along_course_mps"
        ]
        == pytest.approx(
            2.0
        )
    )
    assert (
        segment[
            "relative_air_speed_mps"
        ]
        == pytest.approx(
            2.0
        )
    )


def test_crosswind_right_of_north_course():
    result = build_route_wind_context(
        _environment(
            bearing=0.0,
            speed=3.0,
        ),
        default_weather_sample=(
            _wind(
                4.0,
                270.0,
            )
        ),
    )

    segment = result["routes"][0][
        "segments"
    ][0]

    assert (
        segment[
            "wind_along_course_mps"
        ]
        == pytest.approx(
            0.0,
            abs=1e-12,
        )
    )
    assert (
        segment[
            "wind_cross_course_mps"
        ]
        == pytest.approx(
            4.0
        )
    )
    assert (
        segment[
            "relative_air_speed_mps"
        ]
        == pytest.approx(
            5.0
        )
    )


def test_missing_movement_bearing_is_explicit():
    result = build_route_wind_context(
        _environment(
            bearing=None,
            speed=3.0,
        ),
        default_weather_sample=(
            _wind(
                4.0,
                270.0,
            )
        ),
    )

    segment = result["routes"][0][
        "segments"
    ][0]

    assert segment["available"] is False
    assert (
        segment["status"]
        == STATUS_MOVEMENT_BEARING_UNAVAILABLE
    )


def test_segment_specific_wind_overrides_default():
    result = build_route_wind_context(
        _environment(
            bearing=0.0,
            speed=3.0,
        ),
        default_weather_sample=(
            _wind(
                1.0,
                0.0,
            )
        ),
        wind_by_segment_index={
            10: _wind(
                6.0,
                0.0,
            )
        },
    )

    segment = result["routes"][0][
        "segments"
    ][0]

    assert (
        segment[
            "weather_sample"
        ][
            "wind_speed_mps"
        ]
        == 6.0
    )


def test_scope_keeps_physics_separate_from_physiology_and_hydrology():
    result = build_route_wind_context(
        _environment(),
        default_weather_sample=(
            _wind(
                2.0,
                90.0,
            )
        ),
    )

    assert (
        result["scope"][
            "estimates_relative_air_velocity"
        ]
        is True
    )
    assert (
        result["scope"][
            "estimates_boat_through_water_speed"
        ]
        is False
    )
    assert (
        result["scope"][
            "contains_hydrology"
        ]
        is False
    )
    assert (
        result["scope"][
            "estimates_physiological_load"
        ]
        is False
    )


def test_summary_strips_segments():
    context = build_route_wind_context(
        _environment(),
        default_weather_sample=(
            _wind(
                2.0,
                90.0,
            )
        ),
    )

    summary = (
        build_route_wind_context_summary(
            context
        )
    )

    route = summary["routes"][0]

    assert "segments" not in route
    assert route["segments_included"] is False
    assert route["segment_payload_count"] == 1



def test_matched_weather_sample_takes_precedence():
    matching = {
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "matches": [
                    {
                        "segment_index": 10,
                        "matched_sample": {
                            "wind_speed_mps": 7.0,
                            "wind_direction_from_deg": 0.0,
                            "source": "MATCHED_WEATHER_SAMPLE",
                        },
                    }
                ],
            }
        ],
    }

    result = build_route_wind_context(
        _environment(
            bearing=0.0,
            speed=3.0,
        ),
        default_weather_sample=(
            _wind(
                1.0,
                180.0,
            )
        ),
        weather_sample_matching=(
            matching
        ),
    )

    segment = result["routes"][0]["segments"][0]

    assert segment["weather_sample"]["wind_speed_mps"] == 7.0
    assert segment["weather_sample"]["source"] == "MATCHED_WEATHER_SAMPLE"
