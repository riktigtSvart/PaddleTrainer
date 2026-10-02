import pytest

from app.services.exercise_speed_gps_consistency import (
    build_exercise_speed_gps_consistency,
)


def _motion_with_segments(
    segments,
):
    return {
        "provider": "POLAR",
        "routes": [
            {
                "exercise_index": 0,
                "segments": segments,
            }
        ],
    }


def test_pairs_speed_sample_inside_gps_segment():
    result = (
        build_exercise_speed_gps_consistency(
            {
                "provider": "POLAR",
                "series": [
                    {
                        "exercise_index": 0,
                        "metric_key": "speed_kmh",
                        "unit": "km/h",
                        "interval_ms": 1000,
                        "values": [
                            None,
                            3.6,
                            7.2,
                        ],
                    }
                ],
            },
            _motion_with_segments(
                [
                    {
                        "segment_index": 0,
                        "motion_available": True,
                        "start_exercise_elapsed_ms": 500,
                        "end_exercise_elapsed_ms": 1500,
                        "gps_ground_speed_mps": 1.2,
                    },
                    {
                        "segment_index": 1,
                        "motion_available": True,
                        "start_exercise_elapsed_ms": 1500,
                        "end_exercise_elapsed_ms": 2500,
                        "gps_ground_speed_mps": 2.2,
                    },
                ]
            ),
        )
    )

    exercise = result["exercises"][0]

    assert result["available"] is True
    assert (
        exercise["paired_segment_count"]
        == 2
    )

    first = exercise["comparisons"][0]

    assert (
        first[
            "first_polar_speed_slot_index"
        ]
        == 1
    )
    assert (
        first[
            "polar_speed_sample_mean_mps"
        ]
        == pytest.approx(1.0)
    )
    assert (
        first["difference_mps"]
        == pytest.approx(0.2)
    )


def test_uses_all_speed_samples_inside_longer_segment():
    result = (
        build_exercise_speed_gps_consistency(
            {
                "provider": "POLAR",
                "series": [
                    {
                        "exercise_index": 0,
                        "metric_key": "speed_kmh",
                        "unit": "km/h",
                        "interval_ms": 1000,
                        "values": [
                            0.0,
                            3.6,
                            7.2,
                            10.8,
                            14.4,
                        ],
                    }
                ],
            },
            _motion_with_segments(
                [
                    {
                        "segment_index": 0,
                        "motion_available": True,
                        "start_exercise_elapsed_ms": 500,
                        "end_exercise_elapsed_ms": 3500,
                        "gps_ground_speed_mps": 2.5,
                    }
                ]
            ),
        )
    )

    comparison = (
        result["exercises"][0][
            "comparisons"
        ][0]
    )

    assert (
        comparison[
            "polar_speed_sample_count"
        ]
        == 3
    )

    assert (
        comparison[
            "polar_speed_sample_mean_mps"
        ]
        == pytest.approx(2.0)
    )

    assert (
        comparison[
            "difference_mps"
        ]
        == pytest.approx(0.5)
    )


def test_missing_speed_values_remain_unpaired():
    result = (
        build_exercise_speed_gps_consistency(
            {
                "provider": "POLAR",
                "series": [
                    {
                        "exercise_index": 0,
                        "metric_key": "speed_kmh",
                        "unit": "km/h",
                        "interval_ms": 1000,
                        "values": [
                            None,
                            None,
                        ],
                    }
                ],
            },
            _motion_with_segments(
                [
                    {
                        "segment_index": 0,
                        "motion_available": True,
                        "start_exercise_elapsed_ms": 0,
                        "end_exercise_elapsed_ms": 1000,
                        "gps_ground_speed_mps": 1.0,
                    }
                ]
            ),
        )
    )

    exercise = result["exercises"][0]

    assert result["available"] is False
    assert (
        exercise["candidate_motion_segment_count"]
        == 1
    )
    assert (
        exercise["paired_segment_count"]
        == 0
    )
    assert (
        exercise["unpaired_segment_count"]
        == 1
    )
    assert (
        exercise["reason"]
        == "NO_PAIRED_OBSERVATIONS"
    )


def test_missing_speed_series_is_explicit():
    result = (
        build_exercise_speed_gps_consistency(
            {
                "provider": "POLAR",
                "series": [],
            },
            _motion_with_segments(
                [
                    {
                        "segment_index": 0,
                        "motion_available": True,
                        "start_exercise_elapsed_ms": 0,
                        "end_exercise_elapsed_ms": 1000,
                        "gps_ground_speed_mps": 1.0,
                    }
                ]
            ),
        )
    )

    exercise = result["exercises"][0]

    assert exercise["available"] is False
    assert (
        exercise["reason"]
        == "SPEED_SERIES_MISSING"
    )