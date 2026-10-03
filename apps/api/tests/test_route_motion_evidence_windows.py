import pytest

from app.services.route_motion_evidence_windows import (
    build_route_motion_evidence_windows,
    build_route_motion_evidence_windows_summary,
)



def _evidence(
    observations,
):
    return {
        "provider": "POLAR",
        "routes": [
            {
                "exercise_index": 0,
                "observations": (
                    observations
                ),
            }
        ],
    }


def _observation(
    segment_index,
    *,
    speed=4.0,
    residual=None,
    interval_ms=1000,
):
    return {
        "segment_index": (
            segment_index
        ),
        "motion_available": True,
        "start_exercise_elapsed_ms": (
            segment_index * interval_ms
        ),
        "end_exercise_elapsed_ms": (
            (segment_index + 1)
            * interval_ms
        ),
        "interval_ms": interval_ms,
        "time_since_route_start_ms": (
            segment_index * interval_ms
        ),
        "gps_ground_speed_mps": (
            speed
        ),
        "speed_residual_mps": (
            residual
        ),
        "speed_residual_distance_m": (
            (
                residual
                * interval_ms
                / 1000.0
            )
            if residual is not None
            else None
        ),
    }


def test_builds_centered_five_segment_windows_with_shorter_edges():
    observations = [
        _observation(index)
        for index in range(5)
    ]

    result = (
        build_route_motion_evidence_windows(
            _evidence(
                observations
            )
        )
    )

    route = result["routes"][0]

    assert route["window_count"] == 5

    assert (
        route["windows"][0]
        ["segment_count"]
        == 3
    )

    assert (
        route["windows"][0]
        ["window_start_segment_index"]
        == 0
    )

    assert (
        route["windows"][0]
        ["window_end_segment_index"]
        == 2
    )

    assert (
        route["windows"][2]
        ["segment_count"]
        == 5
    )

    assert (
        route["windows"][2]
        ["window_start_segment_index"]
        == 0
    )

    assert (
        route["windows"][2]
        ["window_end_segment_index"]
        == 4
    )

    assert (
        route["windows"][4]
        ["segment_count"]
        == 3
    )


def test_geometry_pair_does_not_leak_outside_window():
    observations = [
        _observation(index)
        for index in range(4)
    ]

    observations[0]["forward_pair"] = {
        "first_segment_index": 0,
        "second_segment_index": 1,
        "middle_point_cross_track_deviation_m": 1.0,
        "heading_change_rate_deg_per_sec": 10.0,
    }

    observations[1]["forward_pair"] = {
        "first_segment_index": 1,
        "second_segment_index": 2,
        "middle_point_cross_track_deviation_m": 2.0,
        "heading_change_rate_deg_per_sec": 20.0,
    }

    observations[2]["forward_pair"] = {
        "first_segment_index": 2,
        "second_segment_index": 3,
        "middle_point_cross_track_deviation_m": 99.0,
        "heading_change_rate_deg_per_sec": 99.0,
    }

    result = (
        build_route_motion_evidence_windows(
            _evidence(
                observations
            ),
            window_radius_segments=1,
        )
    )

    center = (
        result["routes"][0]
        ["windows"][1]
    )

    assert (
        center["window_start_segment_index"]
        == 0
    )

    assert (
        center["window_end_segment_index"]
        == 2
    )

    assert (
        center["geometry_pair_count"]
        == 2
    )

    assert (
        center[
            "maximum_middle_point_"
            "cross_track_deviation_m"
        ]
        == pytest.approx(2.0)
    )

    assert (
        center[
            "maximum_heading_change_"
            "rate_deg_per_sec"
        ]
        == pytest.approx(20.0)
    )


def test_window_describes_residual_cancellation():
    observations = [
        _observation(
            0,
            residual=2.0,
        ),
        _observation(
            1,
            residual=-2.0,
        ),
        _observation(
            2,
            residual=0.5,
        ),
    ]

    result = (
        build_route_motion_evidence_windows(
            _evidence(
                observations
            ),
            window_radius_segments=1,
        )
    )

    center = (
        result["routes"][0]
        ["windows"][1]
    )

    assert (
        center[
            "signed_residual_distance_sum_m"
        ]
        == pytest.approx(0.5)
    )

    assert (
        center[
            "absolute_residual_distance_sum_m"
        ]
        == pytest.approx(4.5)
    )

    assert (
        center[
            "window_residual_"
            "cancellation_fraction"
        ]
        == pytest.approx(
            1.0 - (0.5 / 4.5)
        )
    )

    assert (
        center[
            "residual_sign_reversal_count"
        ]
        == 2
    )

    assert (
        center[
            "maximum_compensating_"
            "residual_distance_m"
        ]
        == pytest.approx(2.0)
    )

    assert (
        center[
            "maximum_adjacent_residual_"
            "cancellation_fraction"
        ]
        == pytest.approx(1.0)
    )


def test_window_describes_persistent_same_sign_residual():
    observations = [
        _observation(
            0,
            residual=1.0,
        ),
        _observation(
            1,
            residual=1.0,
        ),
        _observation(
            2,
            residual=1.0,
        ),
    ]

    result = (
        build_route_motion_evidence_windows(
            _evidence(
                observations
            ),
            window_radius_segments=1,
        )
    )

    center = (
        result["routes"][0]
        ["windows"][1]
    )

    assert (
        center[
            "window_residual_"
            "cancellation_fraction"
        ]
        == pytest.approx(0.0)
    )

    assert (
        center[
            "residual_sign_reversal_count"
        ]
        == 0
    )

    assert (
        center[
            "longest_same_sign_residual_"
            "run_segment_count"
        ]
        == 3
    )

    assert (
        center[
            "longest_same_sign_residual_"
            "run_duration_ms"
        ]
        == 3000
    )


def test_window_keeps_geometry_temporal_and_cross_source_separate():
    observations = [
        _observation(
            0,
            residual=1.0,
        ),
        _observation(
            1,
            residual=-1.0,
        ),
        _observation(
            2,
            residual=1.0,
        ),
    ]

    observations[0][
        "gps_minus_polar_speed_mps"
    ] = 0.2

    observations[0][
        "absolute_gps_polar_speed_difference_mps"
    ] = 0.2

    observations[1][
        "gps_minus_polar_speed_mps"
    ] = 2.0

    observations[1][
        "absolute_gps_polar_speed_difference_mps"
    ] = 2.0

    observations[1]["forward_pair"] = {
        "first_segment_index": 1,
        "second_segment_index": 2,
        "middle_point_cross_track_deviation_m": 0.03,
        "middle_point_along_track_fraction": 0.5,
        "heading_change_rate_deg_per_sec": 1.0,
        "implied_turn_radius_m": 200.0,
        "path_minus_net_displacement_m": 0.001,
        "net_displacement_fraction_of_path": 0.9999,
    }

    result = (
        build_route_motion_evidence_windows(
            _evidence(
                observations
            ),
            window_radius_segments=1,
        )
    )

    center = (
        result["routes"][0]
        ["windows"][1]
    )

    assert (
        center[
            "maximum_middle_point_"
            "cross_track_deviation_m"
        ]
        == pytest.approx(0.03)
    )

    assert (
        center[
            "residual_sign_reversal_count"
        ]
        == 2
    )

    assert (
        center[
            "maximum_absolute_gps_"
            "polar_speed_difference_mps"
        ]
        == pytest.approx(2.0)
    )

    # Deliberately no decision layer.
    assert "score" not in center
    assert "classification" not in center
    assert "is_anomaly" not in center
    assert "reconstruction" not in center


def test_summary_omits_full_window_list():
    observations = [
        _observation(
            index,
            residual=float(index - 2),
        )
        for index in range(5)
    ]

    windows = (
        build_route_motion_evidence_windows(
            _evidence(
                observations
            )
        )
    )

    summary = (
        build_route_motion_evidence_windows_summary(
            windows
        )
    )

    route = summary["routes"][0]

    assert route["window_count"] == 5
    assert "windows" not in route

    assert (
        "extremes"
        in route
    )


def test_summary_ranks_window_dimensions_independently():
    observations = [
        _observation(
            index,
            residual=0.0,
        )
        for index in range(5)
    ]

    windows = (
        build_route_motion_evidence_windows(
            _evidence(
                observations
            ),
            window_radius_segments=1,
        )
    )

    route_windows = (
        windows["routes"][0]
        ["windows"]
    )

    route_windows[1][
        "maximum_middle_point_"
        "cross_track_deviation_m"
    ] = 10.0

    route_windows[2][
        "maximum_absolute_speed_residual_mps"
    ] = 20.0

    summary = (
        build_route_motion_evidence_windows_summary(
            windows
        )
    )

    extremes = (
        summary["routes"][0]
        ["extremes"]
    )

    assert (
        extremes[
            "highest_window_"
            "cross_track_deviation"
        ][0]["center_segment_index"]
        == 1
    )

    assert (
        extremes[
            "highest_window_"
            "absolute_speed_residual"
        ][0]["center_segment_index"]
        == 2
    )

    assert "score" not in (
        extremes[
            "highest_window_"
            "cross_track_deviation"
        ][0]
    )