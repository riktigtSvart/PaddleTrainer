import math

import pytest

from app.services.route_motion_anomaly_evidence import (
    build_route_motion_anomaly_evidence,
)


def _route(points):
    return {
        "provider": "POLAR",
        "routes": [
            {
                "exercise_index": 0,
                "points": points,
            }
        ],
    }


def _motion(segments):
    return {
        "provider": "POLAR",
        "routes": [
            {
                "exercise_index": 0,
                "segments": segments,
            }
        ],
    }


def test_describes_jump_and_return_geometry():
    normalized = _route(
        [
            {
                "waypoint_index": 0,
                "latitude_deg": 0.0,
                "longitude_deg": 0.0,
            },
            {
                "waypoint_index": 1,
                "latitude_deg": 0.0,
                "longitude_deg": 0.001,
            },
            {
                "waypoint_index": 2,
                "latitude_deg": 0.0,
                "longitude_deg": 0.0,
            },
        ]
    )

    motion = _motion(
        [
            {
                "segment_index": 0,
                "start_waypoint_index": 0,
                "end_waypoint_index": 1,
                "start_exercise_elapsed_ms": 1000,
                "end_exercise_elapsed_ms": 2000,
                "interval_ms": 1000,
                "surface_distance_m": 111.195,
                "initial_bearing_deg": 90.0,
                "gps_ground_speed_mps": 111.195,
                "motion_available": True,
                "reason": None,
            },
            {
                "segment_index": 1,
                "start_waypoint_index": 1,
                "end_waypoint_index": 2,
                "start_exercise_elapsed_ms": 2000,
                "end_exercise_elapsed_ms": 3000,
                "interval_ms": 1000,
                "surface_distance_m": 111.195,
                "initial_bearing_deg": 270.0,
                "gps_ground_speed_mps": 111.195,
                "motion_available": True,
                "reason": None,
            },
        ]
    )

    result = (
        build_route_motion_anomaly_evidence(
            normalized,
            motion,
        )
    )

    observation = (
        result["routes"][0]
        ["observations"][0]
    )

    pair = observation["forward_pair"]

    assert result["available"] is True

    assert (
        pair["path_distance_m"]
        == pytest.approx(
            222.39,
            rel=1e-4,
        )
    )

    assert (
        pair["net_displacement_m"]
        == pytest.approx(0.0)
    )

    assert (
        pair[
            "net_displacement_fraction_of_path"
        ]
        == pytest.approx(0.0)
    )

    assert (
        pair[
            "path_minus_net_displacement_m"
        ]
        == pytest.approx(
            222.39,
            rel=1e-4,
        )
    )

    assert (
        pair["bearing_separation_deg"]
        == pytest.approx(180.0)
    )


def test_preserves_local_speed_change_context():
    normalized = _route([])

    motion = _motion(
        [
            {
                "segment_index": 0,
                "gps_ground_speed_mps": 3.0,
                "interval_ms": 1000,
                "motion_available": True,
            },
            {
                "segment_index": 1,
                "gps_ground_speed_mps": 15.0,
                "interval_ms": 1000,
                "motion_available": True,
            },
            {
                "segment_index": 2,
                "gps_ground_speed_mps": 2.0,
                "interval_ms": 1000,
                "motion_available": True,
            },
        ]
    )

    result = (
        build_route_motion_anomaly_evidence(
            normalized,
            motion,
        )
    )

    observation = (
        result["routes"][0]
        ["observations"][1]
    )

    assert (
        observation[
            "previous_gps_ground_speed_mps"
        ]
        == 3.0
    )

    assert (
        observation[
            "gps_ground_speed_mps"
        ]
        == 15.0
    )

    assert (
        observation[
            "next_gps_ground_speed_mps"
        ]
        == 2.0
    )

    assert (
        observation[
            "speed_change_from_previous_mps"
        ]
        == 12.0
    )

    assert (
        observation[
            "speed_change_to_next_mps"
        ]
        == -13.0
    )


def test_attaches_polar_speed_comparison():
    normalized = _route([])

    motion = _motion(
        [
            {
                "segment_index": 7,
                "gps_ground_speed_mps": 15.0,
                "interval_ms": 1000,
                "motion_available": True,
            }
        ]
    )

    consistency = {
        "provider": "POLAR",
        "exercises": [
            {
                "exercise_index": 0,
                "comparisons": [
                    {
                        "segment_index": 7,
                        "polar_speed_sample_mean_mps": (
                            3.0
                        ),
                        "difference_mps": 12.0,
                        "absolute_difference_mps": (
                            12.0
                        ),
                    }
                ],
            }
        ],
    }

    result = (
        build_route_motion_anomaly_evidence(
            normalized,
            motion,
            consistency,
        )
    )

    observation = (
        result["routes"][0]
        ["observations"][0]
    )

    assert (
        observation[
            "polar_speed_sample_mean_mps"
        ]
        == 3.0
    )

    assert (
        observation[
            "gps_minus_polar_speed_mps"
        ]
        == 12.0
    )

    assert (
        observation[
            "absolute_gps_polar_speed_difference_mps"
        ]
        == 12.0
    )


def test_ranks_extremes_without_classifying_them():
    normalized = _route([])

    motion = _motion(
        [
            {
                "segment_index": 0,
                "gps_ground_speed_mps": 3.0,
                "motion_available": True,
            },
            {
                "segment_index": 1,
                "gps_ground_speed_mps": 15.0,
                "motion_available": True,
            },
            {
                "segment_index": 2,
                "gps_ground_speed_mps": 5.0,
                "motion_available": True,
            },
        ]
    )

    result = (
        build_route_motion_anomaly_evidence(
            normalized,
            motion,
            extreme_observation_limit=2,
        )
    )

    extremes = (
        result["routes"][0]
        ["extremes"]
        ["highest_gps_ground_speed"]
    )

    assert [
        item["segment_index"]
        for item in extremes
    ] == [1, 2]

    assert (
        "is_anomaly"
        not in extremes[0]
    )


def test_describes_middle_point_cross_track_deviation():
    normalized = _route(
        [
            {
                "waypoint_index": 0,
                "exercise_elapsed_ms": 0,
                "latitude_deg": 0.0,
                "longitude_deg": 0.0,
            },
            {
                "waypoint_index": 1,
                "exercise_elapsed_ms": 1000,
                "latitude_deg": 0.0001,
                "longitude_deg": 0.0005,
            },
            {
                "waypoint_index": 2,
                "exercise_elapsed_ms": 2000,
                "latitude_deg": 0.0,
                "longitude_deg": 0.001,
            },
        ]
    )

    motion = _motion(
        [
            {
                "segment_index": 0,
                "start_waypoint_index": 0,
                "end_waypoint_index": 1,
                "start_exercise_elapsed_ms": 0,
                "end_exercise_elapsed_ms": 1000,
                "interval_ms": 1000,
                "surface_distance_m": 56.7,
                "initial_bearing_deg": 78.7,
                "gps_ground_speed_mps": 5.0,
                "motion_available": True,
            },
            {
                "segment_index": 1,
                "start_waypoint_index": 1,
                "end_waypoint_index": 2,
                "start_exercise_elapsed_ms": 1000,
                "end_exercise_elapsed_ms": 2000,
                "interval_ms": 1000,
                "surface_distance_m": 56.7,
                "initial_bearing_deg": 101.3,
                "gps_ground_speed_mps": 5.0,
                "motion_available": True,
            },
        ]
    )

    result = build_route_motion_anomaly_evidence(
        normalized,
        motion,
    )

    pair = (
        result["routes"][0]
        ["observations"][0]
        ["forward_pair"]
    )

    assert (
        pair[
            "middle_point_cross_track_deviation_m"
        ]
        == pytest.approx(
            11.12,
            abs=0.1,
        )
    )

    assert (
        pair[
            "middle_point_along_track_fraction"
        ]
        == pytest.approx(
            0.5,
            abs=0.01,
        )
    )


def test_describes_heading_change_rate_and_implied_turn_radius():
    normalized = _route(
        [
            {
                "waypoint_index": 0,
                "latitude_deg": 0.0,
                "longitude_deg": 0.0,
            },
            {
                "waypoint_index": 1,
                "latitude_deg": 0.0,
                "longitude_deg": 0.0001,
            },
            {
                "waypoint_index": 2,
                "latitude_deg": 0.0001,
                "longitude_deg": 0.0001,
            },
        ]
    )

    motion = _motion(
        [
            {
                "segment_index": 0,
                "start_waypoint_index": 0,
                "end_waypoint_index": 1,
                "start_exercise_elapsed_ms": 0,
                "end_exercise_elapsed_ms": 1000,
                "interval_ms": 1000,
                "surface_distance_m": 5.0,
                "initial_bearing_deg": 90.0,
                "gps_ground_speed_mps": 5.0,
                "motion_available": True,
            },
            {
                "segment_index": 1,
                "start_waypoint_index": 1,
                "end_waypoint_index": 2,
                "start_exercise_elapsed_ms": 1000,
                "end_exercise_elapsed_ms": 2000,
                "interval_ms": 1000,
                "surface_distance_m": 5.0,
                "initial_bearing_deg": 0.0,
                "gps_ground_speed_mps": 5.0,
                "motion_available": True,
            },
        ]
    )

    result = build_route_motion_anomaly_evidence(
        normalized,
        motion,
    )

    pair = (
        result["routes"][0]
        ["observations"][0]
        ["forward_pair"]
    )

    assert (
        pair[
            "heading_change_rate_deg_per_sec"
        ]
        == pytest.approx(90.0)
    )

    assert (
        pair["implied_turn_radius_m"]
        == pytest.approx(
            5.0 / (math.pi / 2.0)
        )
    )


def test_time_since_route_start_is_distinct_from_exercise_start():
    normalized = _route(
        [
            {
                "waypoint_index": 0,
                "exercise_elapsed_ms": 73000,
            },
            {
                "waypoint_index": 1,
                "exercise_elapsed_ms": 74000,
            },
        ]
    )

    motion = _motion(
        [
            {
                "segment_index": 0,
                "start_exercise_elapsed_ms": 73000,
                "end_exercise_elapsed_ms": 74000,
                "interval_ms": 1000,
                "gps_ground_speed_mps": 3.0,
                "motion_available": True,
            }
        ]
    )

    result = build_route_motion_anomaly_evidence(
        normalized,
        motion,
    )

    route = result["routes"][0]
    observation = route["observations"][0]

    assert (
        route[
            "route_start_exercise_elapsed_ms"
        ]
        == 73000
    )

    assert (
        observation[
            "time_since_route_start_ms"
        ]
        == 0
    )


def test_linear_acceleration_has_near_zero_local_speed_residual():
    normalized = _route([])

    segments = []

    for index, speed in enumerate(
        [1.0, 2.0, 3.0, 4.0, 5.0]
    ):
        segments.append(
            {
                "segment_index": index,
                "start_exercise_elapsed_ms": (
                    index * 1000
                ),
                "end_exercise_elapsed_ms": (
                    (index + 1) * 1000
                ),
                "interval_ms": 1000,
                "gps_ground_speed_mps": speed,
                "motion_available": True,
            }
        )

    result = build_route_motion_anomaly_evidence(
        normalized,
        _motion(segments),
    )

    middle = (
        result["routes"][0]
        ["observations"][2]
    )

    assert (
        middle[
            "expected_gps_ground_speed_mps"
        ]
        == pytest.approx(3.0)
    )

    assert (
        middle["speed_residual_mps"]
        == pytest.approx(0.0)
    )


def test_spike_followed_by_deficit_has_compensation_evidence():
    normalized = _route([])

    speeds = [
        4.0,
        4.0,
        10.0,
        0.0,
        4.0,
    ]

    segments = [
        {
            "segment_index": index,
            "start_exercise_elapsed_ms": (
                index * 1000
            ),
            "end_exercise_elapsed_ms": (
                (index + 1) * 1000
            ),
            "interval_ms": 1000,
            "gps_ground_speed_mps": speed,
            "motion_available": True,
        }
        for index, speed
        in enumerate(speeds)
    ]

    result = build_route_motion_anomaly_evidence(
        normalized,
        _motion(segments),
    )

    spike = (
        result["routes"][0]
        ["observations"][2]
    )

    extremes = (
        result["routes"][0]
        ["extremes"]
        ["highest_residual_compensation_distance"]
    )


    assert (
        spike["speed_residual_mps"]
        > 0.0
    )

    assert (
        spike["next_speed_residual_mps"]
        < 0.0
    )

    assert (
        spike["residual_sign_reversal"]
        is True
    )

    assert (
        spike[
            "compensating_residual_distance_m"
        ]
        > 0.0
    )

    assert (
        spike[
            "residual_cancellation_fraction"
        ]
        > 0.0
    )

    assert extremes

    assert any(
        item["segment_index"] == 2
        for item in extremes
    )