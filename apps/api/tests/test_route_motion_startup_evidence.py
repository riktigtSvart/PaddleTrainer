import pytest

from app.services.route_motion_startup_evidence import (
    build_route_motion_startup_evidence,
)


def _normalized(
    waypoint_count=7,
):
    return {
        "provider": "POLAR",
        "routes": [
            {
                "exercise_index": 0,
                "route_start_offset_ms": 663.0,
                "points": [
                    {
                        "waypoint_index": index,
                        "source_elapsed_ms": (
                            73100
                            + index * 1000
                        ),
                        "exercise_elapsed_ms": (
                            73763.0
                            + index * 1000
                        ),
                    }
                    for index
                    in range(
                        waypoint_count
                    )
                ],
            }
        ],
    }


def _pair(
    first_segment_index,
    second_segment_index,
    *,
    cross_track=0.1,
    heading_rate=5.0,
    path_minus_net=0.01,
    net_path_fraction=0.99,
    along_track=0.5,
    turn_radius=20.0,
):
    return {
        "first_segment_index": (
            first_segment_index
        ),
        "second_segment_index": (
            second_segment_index
        ),
        "middle_point_cross_track_deviation_m": (
            cross_track
        ),
        "heading_change_rate_deg_per_sec": (
            heading_rate
        ),
        "path_minus_net_displacement_m": (
            path_minus_net
        ),
        "net_displacement_fraction_of_path": (
            net_path_fraction
        ),
        "middle_point_along_track_fraction": (
            along_track
        ),
        "implied_turn_radius_m": (
            turn_radius
        ),
    }


def _observation(
    segment_index,
    speed,
    *,
    polar_speed=None,
    residual=0.0,
    residual_distance=None,
    forward_pair=None,
    previous_pair=None,
    residual_sign_reversal=False,
    compensation=0.0,
    cancellation=0.0,
):
    if polar_speed is None:
        polar_speed = speed

    if residual_distance is None:
        residual_distance = residual

    difference = (
        speed - polar_speed
    )

    return {
        "segment_index": segment_index,
        "motion_available": True,
        "reason": None,
        "start_exercise_elapsed_ms": (
            73763
            + segment_index * 1000
        ),
        "end_exercise_elapsed_ms": (
            74763
            + segment_index * 1000
        ),
        "interval_ms": 1000,
        "gps_ground_speed_mps": speed,
        "initial_bearing_deg": 90.0,
        "previous_pair": previous_pair,
        "forward_pair": forward_pair,
        "polar_speed_sample_mean_mps": (
            polar_speed
        ),
        "gps_minus_polar_speed_mps": (
            difference
        ),
        "absolute_gps_polar_speed_difference_mps": (
            abs(
                difference
            )
        ),
        "speed_residual_mps": residual,
        "absolute_speed_residual_mps": (
            abs(
                residual
            )
        ),
        "speed_residual_distance_m": (
            residual_distance
        ),
        "residual_sign_reversal": (
            residual_sign_reversal
        ),
        "compensating_residual_distance_m": (
            compensation
        ),
        "residual_cancellation_fraction": (
            cancellation
        ),
    }


def _anomaly(
    observations,
):
    return {
        "provider": "POLAR",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "observations": (
                    observations
                ),
            }
        ],
    }


def test_startup_uses_fixed_first_five_segments():
    observations = [
        _observation(
            index,
            float(index),
        )
        for index in range(6)
    ]

    observations[5][
        "gps_ground_speed_mps"
    ] = 99.0

    result = (
        build_route_motion_startup_evidence(
            _normalized(),
            _anomaly(
                observations
            ),
        )
    )

    route = result[
        "routes"
    ][0]

    assert (
        route[
            "expected_segment_indices"
        ]
        == [0, 1, 2, 3, 4]
    )

    assert [
        item[
            "segment_index"
        ]
        for item in route[
            "trajectory"
        ]
    ] == [0, 1, 2, 3, 4]

    assert (
        route[
            "trajectory_summary"
        ][
            "maximum_gps_ground_speed_mps"
        ]
        == pytest.approx(4.0)
    )


def test_startup_trajectory_preserves_order_and_shape():
    observations = [
        _observation(
            4,
            4.5,
        ),
        _observation(
            0,
            0.0,
        ),
        _observation(
            2,
            3.0,
        ),
        _observation(
            1,
            0.5,
        ),
        _observation(
            3,
            4.0,
        ),
    ]

    result = (
        build_route_motion_startup_evidence(
            _normalized(),
            _anomaly(
                observations
            ),
        )
    )

    route = result[
        "routes"
    ][0]

    assert [
        item[
            "gps_ground_speed_mps"
        ]
        for item in route[
            "trajectory"
        ]
    ] == pytest.approx(
        [
            0.0,
            0.5,
            3.0,
            4.0,
            4.5,
        ]
    )

    summary = route[
        "trajectory_summary"
    ]

    assert (
        summary[
            "directionality_fraction"
        ]
        == pytest.approx(1.0)
    )

    assert (
        summary[
            "maximum_speed_order_index"
        ]
        == 4
    )

    assert (
        summary[
            "peak_to_last_speed_drop_mps"
        ]
        == pytest.approx(0.0)
    )


def test_geometry_uses_unique_pairs_inside_startup_window_only():
    pair_01 = _pair(
        0,
        1,
        cross_track=0.1,
        heading_rate=5.0,
        path_minus_net=0.01,
        net_path_fraction=0.99,
    )

    pair_12 = _pair(
        1,
        2,
        cross_track=0.2,
        heading_rate=7.0,
        path_minus_net=0.02,
        net_path_fraction=0.98,
    )

    pair_23 = _pair(
        2,
        3,
        cross_track=0.3,
        heading_rate=9.0,
        path_minus_net=0.03,
        net_path_fraction=0.97,
    )

    pair_34 = _pair(
        3,
        4,
        cross_track=0.4,
        heading_rate=11.0,
        path_minus_net=0.04,
        net_path_fraction=0.96,
    )

    pair_45_outside = _pair(
        4,
        5,
        cross_track=50.0,
        heading_rate=150.0,
        path_minus_net=20.0,
        net_path_fraction=0.2,
    )

    observations = [
        _observation(
            0,
            1.0,
            forward_pair=pair_01,
        ),
        _observation(
            1,
            2.0,
            previous_pair=pair_01,
            forward_pair=pair_12,
        ),
        _observation(
            2,
            3.0,
            previous_pair=pair_12,
            forward_pair=pair_23,
        ),
        _observation(
            3,
            4.0,
            previous_pair=pair_23,
            forward_pair=pair_34,
        ),
        _observation(
            4,
            5.0,
            previous_pair=pair_34,
            forward_pair=(
                pair_45_outside
            ),
        ),
    ]

    result = (
        build_route_motion_startup_evidence(
            _normalized(),
            _anomaly(
                observations
            ),
        )
    )

    geometry = result[
        "routes"
    ][0][
        "geometry"
    ]

    assert (
        geometry[
            "pair_count"
        ]
        == 4
    )

    assert (
        geometry[
            "maximum_middle_point_cross_track_deviation_m"
        ]
        == pytest.approx(0.4)
    )

    assert (
        geometry[
            "maximum_heading_change_rate_deg_per_sec"
        ]
        == pytest.approx(11.0)
    )

    assert (
        geometry[
            "path_minus_net_displacement_sum_m"
        ]
        == pytest.approx(0.10)
    )

    assert (
        geometry[
            "minimum_net_displacement_fraction_of_path"
        ]
        == pytest.approx(0.96)
    )


def test_cross_source_speed_summary_is_descriptive():
    observations = [
        _observation(
            0,
            1.0,
            polar_speed=0.5,
        ),
        _observation(
            1,
            2.0,
            polar_speed=1.0,
        ),
        _observation(
            2,
            3.0,
            polar_speed=3.5,
        ),
        _observation(
            3,
            4.0,
            polar_speed=4.0,
        ),
        _observation(
            4,
            5.0,
            polar_speed=4.0,
        ),
    ]

    result = (
        build_route_motion_startup_evidence(
            _normalized(),
            _anomaly(
                observations
            ),
        )
    )

    cross_source = result[
        "routes"
    ][0][
        "cross_source_speed"
    ]

    assert (
        cross_source[
            "comparison_count"
        ]
        == 5
    )

    assert (
        cross_source[
            "mean_gps_minus_polar_speed_mps"
        ]
        == pytest.approx(0.4)
    )

    assert (
        cross_source[
            "mean_absolute_gps_polar_speed_difference_mps"
        ]
        == pytest.approx(0.6)
    )

    assert (
        cross_source[
            "maximum_absolute_gps_polar_speed_difference_mps"
        ]
        == pytest.approx(1.0)
    )


def test_temporal_residual_summary_stays_inside_window():
    observations = [
        _observation(
            0,
            1.0,
            residual=-2.0,
            residual_distance=-2.0,
            residual_sign_reversal=True,
            compensation=1.0,
            cancellation=0.5,
        ),
        _observation(
            1,
            2.0,
            residual=1.0,
            residual_distance=1.0,
            residual_sign_reversal=True,
            compensation=0.5,
            cancellation=0.5,
        ),
        _observation(
            2,
            3.0,
            residual=-1.0,
            residual_distance=-1.0,
        ),
        _observation(
            3,
            4.0,
            residual=0.5,
            residual_distance=0.5,
        ),
        _observation(
            4,
            5.0,
            residual=-0.5,
            residual_distance=-0.5,
            residual_sign_reversal=True,
            compensation=99.0,
            cancellation=0.99,
        ),
    ]

    result = (
        build_route_motion_startup_evidence(
            _normalized(),
            _anomaly(
                observations
            ),
        )
    )

    temporal = result[
        "routes"
    ][0][
        "temporal_residual"
    ]

    assert (
        temporal[
            "maximum_absolute_speed_residual_mps"
        ]
        == pytest.approx(2.0)
    )

    assert (
        temporal[
            "signed_residual_distance_sum_m"
        ]
        == pytest.approx(-2.0)
    )

    assert (
        temporal[
            "absolute_residual_distance_sum_m"
        ]
        == pytest.approx(5.0)
    )

    assert (
        temporal[
            "window_residual_cancellation_fraction"
        ]
        == pytest.approx(0.6)
    )

    assert (
        temporal[
            "residual_sign_reversal_count"
        ]
        == 2
    )

    assert (
        temporal[
            "maximum_compensating_residual_distance_m"
        ]
        == pytest.approx(1.0)
    )


def test_timing_uses_route_metadata_and_first_waypoint():
    observations = [
        _observation(
            index,
            float(index),
        )
        for index in range(5)
    ]

    result = (
        build_route_motion_startup_evidence(
            _normalized(),
            _anomaly(
                observations
            ),
        )
    )

    route = result[
        "routes"
    ][0]

    assert (
        route[
            "route_start_offset_ms"
        ]
        == 663
    )

    assert (
        route[
            "first_route_waypoint_source_elapsed_ms"
        ]
        == 73100
    )

    assert (
        route[
            "first_route_waypoint_exercise_elapsed_ms"
        ]
        == 73763
    )

    assert (
        route[
            "trajectory"
        ][0][
            "time_since_first_route_waypoint_ms"
        ]
        == 0
    )

    assert (
        route[
            "startup_window_elapsed_ms"
        ]
        == 5000
    )


def test_missing_startup_observation_is_reported_without_interpolation():
    observations = [
        _observation(
            0,
            0.0,
        ),
        _observation(
            1,
            1.0,
        ),
        _observation(
            3,
            3.0,
        ),
        _observation(
            4,
            4.0,
        ),
    ]

    result = (
        build_route_motion_startup_evidence(
            _normalized(),
            _anomaly(
                observations
            ),
        )
    )

    route = result[
        "routes"
    ][0]

    assert (
        route[
            "missing_expected_segment_indices"
        ]
        == [2]
    )

    assert (
        route[
            "observed_startup_segment_count"
        ]
        == 4
    )

    assert (
        route[
            "target_segment_count_reached"
        ]
        is False
    )

    assert [
        item[
            "segment_index"
        ]
        for item in route[
            "trajectory"
        ]
    ] == [0, 1, 3, 4]


def test_short_route_does_not_invent_segments():
    result = (
        build_route_motion_startup_evidence(
            _normalized(
                waypoint_count=4
            ),
            _anomaly(
                [
                    _observation(
                        index,
                        float(index),
                    )
                    for index
                    in range(3)
                ]
            ),
        )
    )

    route = result[
        "routes"
    ][0]

    assert (
        route[
            "route_candidate_segment_count"
        ]
        == 3
    )

    assert (
        route[
            "expected_startup_segment_count"
        ]
        == 3
    )

    assert (
        route[
            "expected_segment_indices"
        ]
        == [0, 1, 2]
    )

    assert (
        route[
            "target_segment_count_reached"
        ]
        is False
    )


def test_startup_evidence_has_no_anomaly_decision():
    result = (
        build_route_motion_startup_evidence(
            _normalized(),
            _anomaly(
                [
                    _observation(
                        index,
                        float(index),
                    )
                    for index
                    in range(5)
                ]
            ),
        )
    )

    route = result[
        "routes"
    ][0]

    assert "score" not in route
    assert "classification" not in route
    assert "is_anomaly" not in route
    assert "startup_anomaly" not in route


def test_startup_segment_count_must_be_positive():
    with pytest.raises(
        ValueError,
        match=(
            "startup_segment_count must be >= 1"
        ),
    ):
        build_route_motion_startup_evidence(
            _normalized(),
            _anomaly([]),
            startup_segment_count=0,
        )
