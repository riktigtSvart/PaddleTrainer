import pytest

from app.services.route_motion_speed_trajectory import (
    build_route_motion_speed_trajectories,
)


def _observation(
    segment_index,
    speed,
):
    return {
        "segment_index": segment_index,
        "start_exercise_elapsed_ms": (
            segment_index * 1000
        ),
        "end_exercise_elapsed_ms": (
            (segment_index + 1) * 1000
        ),
        "interval_ms": 1000,
        "gps_ground_speed_mps": speed,
        "polar_speed_sample_mean_mps": (
            speed - 0.1
        ),
        "gps_minus_polar_speed_mps": 0.1,
        "speed_residual_mps": 0.2,
        "absolute_speed_residual_mps": 0.2,
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
                "observations": observations,
            }
        ],
    }


def _ranking(
    start,
    end,
):
    return {
        "provider": "POLAR",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "speed_transition": [
                    {
                        "inspection_rank": 1,
                        "center_segment_index": (
                            (start + end) // 2
                        ),
                        "center_time_since_route_start_ms": (
                            ((start + end) // 2)
                            * 1000
                        ),
                        "window_start_segment_index": (
                            start
                        ),
                        "window_end_segment_index": (
                            end
                        ),
                        "gps_ground_speed_range_mps": (
                            5.0
                        ),
                    }
                ],
            }
        ],
    }


def test_trajectory_is_returned_in_segment_order():
    result = (
        build_route_motion_speed_trajectories(
            _anomaly(
                [
                    _observation(4, 4.0),
                    _observation(2, 1.0),
                    _observation(3, 2.5),
                ]
            ),
            _ranking(2, 4),
        )
    )

    trajectory = (
        result["routes"][0]
        ["trajectories"][0]
        ["trajectory"]
    )

    assert [
        item["segment_index"]
        for item in trajectory
    ] == [2, 3, 4]

    assert [
        item["gps_ground_speed_mps"]
        for item in trajectory
    ] == pytest.approx(
        [1.0, 2.5, 4.0]
    )


def test_speed_changes_are_calculated_from_ordered_speeds():
    result = (
        build_route_motion_speed_trajectories(
            _anomaly(
                [
                    _observation(0, 0.0),
                    _observation(1, 1.0),
                    _observation(2, 3.5),
                ]
            ),
            _ranking(0, 2),
        )
    )

    trajectory = (
        result["routes"][0]
        ["trajectories"][0]
        ["trajectory"]
    )

    assert (
        trajectory[0]
        ["gps_speed_change_from_previous_mps"]
        is None
    )

    assert (
        trajectory[1]
        ["gps_speed_change_from_previous_mps"]
        == pytest.approx(1.0)
    )

    assert (
        trajectory[2]
        ["gps_speed_change_from_previous_mps"]
        == pytest.approx(2.5)
    )


def test_missing_segments_are_reported_without_interpolation():
    result = (
        build_route_motion_speed_trajectories(
            _anomaly(
                [
                    _observation(10, 1.0),
                    _observation(12, 3.0),
                ]
            ),
            _ranking(10, 12),
        )
    )

    item = (
        result["routes"][0]
        ["trajectories"][0]
    )

    assert (
        item["expected_segment_count"]
        == 3
    )

    assert (
        item["trajectory_observation_count"]
        == 2
    )

    assert (
        item["missing_segment_indices"]
        == [11]
    )

    assert [
        entry["segment_index"]
        for entry in item["trajectory"]
    ] == [10, 12]


def test_summary_preserves_acceleration_shape_descriptively():
    result = (
        build_route_motion_speed_trajectories(
            _anomaly(
                [
                    _observation(0, 0.0),
                    _observation(1, 1.0),
                    _observation(2, 2.0),
                    _observation(3, 4.0),
                ]
            ),
            _ranking(0, 3),
        )
    )

    summary = (
        result["routes"][0]
        ["trajectories"][0]
        ["summary"]
    )

    assert (
        summary[
            "net_gps_ground_speed_change_mps"
        ]
        == pytest.approx(4.0)
    )

    assert (
        summary[
            "positive_speed_change_count"
        ]
        == 3
    )

    assert (
        summary[
            "negative_speed_change_count"
        ]
        == 0
    )

    assert (
        summary[
            "speed_change_sign_reversal_count"
        ]
        == 0
    )


def test_summary_preserves_spike_and_return_shape():
    result = (
        build_route_motion_speed_trajectories(
            _anomaly(
                [
                    _observation(0, 1.0),
                    _observation(1, 5.0),
                    _observation(2, 1.5),
                ]
            ),
            _ranking(0, 2),
        )
    )

    summary = (
        result["routes"][0]
        ["trajectories"][0]
        ["summary"]
    )

    assert (
        summary[
            "positive_speed_change_count"
        ]
        == 1
    )

    assert (
        summary[
            "negative_speed_change_count"
        ]
        == 1
    )

    assert (
        summary[
            "speed_change_sign_reversal_count"
        ]
        == 1
    )

    assert (
        summary[
            "largest_positive_speed_change_mps"
        ]
        == pytest.approx(4.0)
    )

    assert (
        summary[
            "largest_negative_speed_change_mps"
        ]
        == pytest.approx(-3.5)
    )


def test_no_anomaly_or_reconstruction_decision_is_added():
    result = (
        build_route_motion_speed_trajectories(
            _anomaly(
                [
                    _observation(0, 0.0),
                    _observation(1, 3.0),
                ]
            ),
            _ranking(0, 1),
        )
    )

    item = (
        result["routes"][0]
        ["trajectories"][0]
    )

    assert "score" not in item
    assert "classification" not in item
    assert "is_anomaly" not in item
    assert "reconstruction" not in item



def test_summary_adds_directionality_and_change_fractions():
    result = (
        build_route_motion_speed_trajectories(
            _anomaly(
                [
                    _observation(0, 0.0),
                    _observation(1, 1.0),
                    _observation(2, 3.0),
                    _observation(3, 4.0),
                ]
            ),
            _ranking(0, 3),
        )
    )

    summary = (
        result["routes"][0]
        ["trajectories"][0]
        ["summary"]
    )

    assert summary["speed_change_count"] == 3
    assert (
        summary["directionality_fraction"]
        == pytest.approx(1.0)
    )
    assert (
        summary["positive_speed_change_fraction"]
        == pytest.approx(1.0)
    )
    assert (
        summary["negative_speed_change_fraction"]
        == pytest.approx(0.0)
    )
    assert (
        summary["zero_speed_change_fraction"]
        == pytest.approx(0.0)
    )
    assert (
        summary["largest_absolute_speed_change_mps"]
        == pytest.approx(2.0)
    )
    assert (
        summary[
            "largest_absolute_speed_change_fraction_of_total"
        ]
        == pytest.approx(0.5)
    )


def test_zero_change_trajectory_has_undefined_ratio_metrics():
    result = (
        build_route_motion_speed_trajectories(
            _anomaly(
                [
                    _observation(0, 2.0),
                    _observation(1, 2.0),
                    _observation(2, 2.0),
                ]
            ),
            _ranking(0, 2),
        )
    )

    summary = (
        result["routes"][0]
        ["trajectories"][0]
        ["summary"]
    )

    assert summary["speed_change_count"] == 2
    assert (
        summary["total_absolute_speed_change_mps"]
        == pytest.approx(0.0)
    )
    assert summary["directionality_fraction"] is None
    assert (
        summary["positive_speed_change_fraction"]
        == pytest.approx(0.0)
    )
    assert (
        summary["negative_speed_change_fraction"]
        == pytest.approx(0.0)
    )
    assert (
        summary["zero_speed_change_fraction"]
        == pytest.approx(1.0)
    )
    assert (
        summary["largest_absolute_speed_change_mps"]
        == pytest.approx(0.0)
    )
    assert (
        summary[
            "largest_absolute_speed_change_fraction_of_total"
        ]
        is None
    )


def test_peak_metrics_for_monotonic_rise_peak_at_window_end():
    result = (
        build_route_motion_speed_trajectories(
            _anomaly(
                [
                    _observation(0, 0.0),
                    _observation(1, 0.5),
                    _observation(2, 3.0),
                    _observation(3, 4.0),
                    _observation(4, 4.5),
                ]
            ),
            _ranking(0, 4),
        )
    )

    summary = (
        result["routes"][0]
        ["trajectories"][0]
        ["summary"]
    )

    assert summary["minimum_speed_order_index"] == 0
    assert summary["maximum_speed_order_index"] == 4
    assert (
        summary["peak_to_last_speed_change_mps"]
        == pytest.approx(0.0)
    )
    assert (
        summary["peak_to_last_speed_drop_mps"]
        == pytest.approx(0.0)
    )
    assert (
        summary["post_peak_absolute_speed_change_mps"]
        == pytest.approx(0.0)
    )
    assert (
        summary[
            "peak_to_last_drop_fraction_of_speed_range"
        ]
        == pytest.approx(0.0)
    )


def test_peak_metrics_describe_middle_spike_and_return():
    result = (
        build_route_motion_speed_trajectories(
            _anomaly(
                [
                    _observation(0, 1.0),
                    _observation(1, 5.0),
                    _observation(2, 1.5),
                ]
            ),
            _ranking(0, 2),
        )
    )

    summary = (
        result["routes"][0]
        ["trajectories"][0]
        ["summary"]
    )

    assert summary["minimum_speed_order_index"] == 0
    assert summary["maximum_speed_order_index"] == 1
    assert (
        summary["peak_to_last_speed_change_mps"]
        == pytest.approx(-3.5)
    )
    assert (
        summary["peak_to_last_speed_drop_mps"]
        == pytest.approx(3.5)
    )
    assert (
        summary["post_peak_absolute_speed_change_mps"]
        == pytest.approx(3.5)
    )
    assert (
        summary[
            "peak_to_last_drop_fraction_of_speed_range"
        ]
        == pytest.approx(0.875)
    )


def test_peak_metrics_use_first_maximum_and_handle_zero_range():
    repeated_peak_result = (
        build_route_motion_speed_trajectories(
            _anomaly(
                [
                    _observation(0, 1.0),
                    _observation(1, 5.0),
                    _observation(2, 4.0),
                    _observation(3, 5.0),
                ]
            ),
            _ranking(0, 3),
        )
    )

    repeated_summary = (
        repeated_peak_result["routes"][0]
        ["trajectories"][0]
        ["summary"]
    )

    assert repeated_summary["maximum_speed_order_index"] == 1
    assert (
        repeated_summary["post_peak_absolute_speed_change_mps"]
        == pytest.approx(2.0)
    )
    assert (
        repeated_summary["peak_to_last_speed_change_mps"]
        == pytest.approx(0.0)
    )

    constant_result = (
        build_route_motion_speed_trajectories(
            _anomaly(
                [
                    _observation(0, 2.0),
                    _observation(1, 2.0),
                    _observation(2, 2.0),
                ]
            ),
            _ranking(0, 2),
        )
    )

    constant_summary = (
        constant_result["routes"][0]
        ["trajectories"][0]
        ["summary"]
    )

    assert constant_summary["minimum_speed_order_index"] == 0
    assert constant_summary["maximum_speed_order_index"] == 0
    assert (
        constant_summary["peak_to_last_speed_change_mps"]
        == pytest.approx(0.0)
    )
    assert (
        constant_summary["peak_to_last_speed_drop_mps"]
        == pytest.approx(0.0)
    )
    assert (
        constant_summary["post_peak_absolute_speed_change_mps"]
        == pytest.approx(0.0)
    )
    assert (
        constant_summary[
            "peak_to_last_drop_fraction_of_speed_range"
        ]
        is None
    )

