import pytest

from app.services.route_motion import (
    build_route_motion_evidence,
)


def test_builds_distance_bearing_and_ground_speed():
    result = build_route_motion_evidence(
        {
            "provider": "POLAR",
            "routes": [
                {
                    "exercise_index": 0,
                    "points": [
                        {
                            "waypoint_index": 0,
                            "exercise_elapsed_ms": 0,
                            "latitude_deg": 0.0,
                            "longitude_deg": 0.0,
                        },
                        {
                            "waypoint_index": 1,
                            "exercise_elapsed_ms": 10000,
                            "latitude_deg": 0.0,
                            "longitude_deg": 0.001,
                        },
                    ],
                }
            ],
        }
    )

    assert result["available"] is True

    route = result["routes"][0]
    segment = route["segments"][0]

    assert route["segment_count"] == 1
    assert route["motion_segment_count"] == 1

    assert segment["interval_ms"] == 10000

    assert segment[
        "surface_distance_m"
    ] == pytest.approx(
        111.195,
        abs=0.01,
    )

    assert segment[
        "initial_bearing_deg"
    ] == pytest.approx(
        90.0,
        abs=0.001,
    )

    assert segment[
        "gps_ground_speed_mps"
    ] == pytest.approx(
        11.1195,
        abs=0.01,
    )


def test_stationary_points_have_zero_speed_and_no_bearing():
    result = build_route_motion_evidence(
        {
            "provider": "POLAR",
            "routes": [
                {
                    "exercise_index": 0,
                    "points": [
                        {
                            "waypoint_index": 0,
                            "exercise_elapsed_ms": 0,
                            "latitude_deg": 47.0,
                            "longitude_deg": 19.0,
                        },
                        {
                            "waypoint_index": 1,
                            "exercise_elapsed_ms": 1000,
                            "latitude_deg": 47.0,
                            "longitude_deg": 19.0,
                        },
                    ],
                }
            ],
        }
    )

    segment = (
        result["routes"][0]["segments"][0]
    )

    assert segment["motion_available"] is True
    assert segment["surface_distance_m"] == 0.0
    assert (
        segment["initial_bearing_deg"]
        is None
    )
    assert (
        segment["gps_ground_speed_mps"]
        == 0.0
    )


def test_non_positive_interval_is_preserved_but_not_motion_available():
    result = build_route_motion_evidence(
        {
            "provider": "POLAR",
            "routes": [
                {
                    "exercise_index": 0,
                    "points": [
                        {
                            "waypoint_index": 0,
                            "exercise_elapsed_ms": 1000,
                            "latitude_deg": 47.0,
                            "longitude_deg": 19.0,
                        },
                        {
                            "waypoint_index": 1,
                            "exercise_elapsed_ms": 1000,
                            "latitude_deg": 47.001,
                            "longitude_deg": 19.0,
                        },
                    ],
                }
            ],
        }
    )

    segment = (
        result["routes"][0]["segments"][0]
    )

    assert segment["interval_ms"] == 0
    assert (
        segment["surface_distance_m"]
        is not None
    )
    assert (
        segment["initial_bearing_deg"]
        == pytest.approx(0.0)
    )
    assert (
        segment["gps_ground_speed_mps"]
        is None
    )
    assert (
        segment["motion_available"]
        is False
    )
    assert (
        segment["reason"]
        == "NON_POSITIVE_INTERVAL"
    )


def test_missing_coordinate_is_reported_without_inventing_motion():
    result = build_route_motion_evidence(
        {
            "provider": "POLAR",
            "routes": [
                {
                    "exercise_index": 0,
                    "points": [
                        {
                            "waypoint_index": 0,
                            "exercise_elapsed_ms": 0,
                            "latitude_deg": 47.0,
                            "longitude_deg": None,
                        },
                        {
                            "waypoint_index": 1,
                            "exercise_elapsed_ms": 1000,
                            "latitude_deg": 47.1,
                            "longitude_deg": 19.1,
                        },
                    ],
                }
            ],
        }
    )

    segment = (
        result["routes"][0]["segments"][0]
    )

    assert (
        segment["surface_distance_m"]
        is None
    )
    assert (
        segment["initial_bearing_deg"]
        is None
    )
    assert (
        segment["gps_ground_speed_mps"]
        is None
    )
    assert (
        segment["motion_available"]
        is False
    )
    assert (
        segment["reason"]
        == "COORDINATES_UNAVAILABLE"
    )