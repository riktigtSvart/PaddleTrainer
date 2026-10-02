import pytest

from app.services.route_motion import (
    build_route_motion_evidence,
)
from app.services.route_motion_summary import (
    build_route_motion_summary_evidence,
)


def test_summarizes_route_motion():
    motion = build_route_motion_evidence(
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
                        {
                            "waypoint_index": 2,
                            "exercise_elapsed_ms": 20000,
                            "latitude_deg": 0.0,
                            "longitude_deg": 0.002,
                        },
                    ],
                }
            ],
        }
    )

    result = (
        build_route_motion_summary_evidence(
            motion
        )
    )

    route = result["routes"][0]

    assert result["available"] is True

    assert route["segment_count"] == 2
    assert route["motion_segment_count"] == 2
    assert route["bearing_segment_count"] == 2
    assert (
        route["zero_distance_segment_count"]
        == 0
    )

    assert (
        route["total_surface_distance_m"]
        == pytest.approx(
            222.390,
            abs=0.02,
        )
    )

    assert (
        route["total_positive_interval_ms"]
        == 20000
    )

    assert (
        route[
            "distance_over_time_ground_speed_mps"
        ]
        == pytest.approx(
            11.1195,
            abs=0.01,
        )
    )


def test_stationary_segment_has_no_bearing():
    motion = build_route_motion_evidence(
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
                        {
                            "waypoint_index": 2,
                            "exercise_elapsed_ms": 2000,
                            "latitude_deg": 47.001,
                            "longitude_deg": 19.0,
                        },
                    ],
                }
            ],
        }
    )

    result = (
        build_route_motion_summary_evidence(
            motion
        )
    )

    route = result["routes"][0]

    assert route["motion_segment_count"] == 2
    assert route["bearing_segment_count"] == 1
    assert (
        route["zero_distance_segment_count"]
        == 1
    )


def test_unavailable_motion_does_not_invent_summary():
    motion = build_route_motion_evidence(
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

    result = (
        build_route_motion_summary_evidence(
            motion
        )
    )

    route = result["routes"][0]

    assert result["available"] is False
    assert route["motion_segment_count"] == 0
    assert (
        route["total_surface_distance_m"]
        is None
    )
    assert (
        route[
            "distance_over_time_ground_speed_mps"
        ]
        is None
    )