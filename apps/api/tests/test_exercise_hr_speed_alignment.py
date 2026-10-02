from app.services.exercise_hr_speed_alignment import (
    build_exercise_hr_speed_alignment,
)


def test_aligns_hr_and_speed_on_same_grid():
    result = (
        build_exercise_hr_speed_alignment(
            {
                "provider": "POLAR",
                "series": [
                    {
                        "exercise_index": 0,
                        "metric_key": (
                            "heart_rate_bpm"
                        ),
                        "interval_ms": 1000,
                        "values": [
                            100.0,
                            110.0,
                            120.0,
                        ],
                    },
                    {
                        "exercise_index": 0,
                        "metric_key": (
                            "speed_kmh"
                        ),
                        "interval_ms": 1000,
                        "values": [
                            8.0,
                            9.0,
                            10.0,
                        ],
                    },
                ],
            }
        )
    )

    assert result["available"] is True

    evidence = result["exercises"][0]

    assert evidence["aligned"] is True
    assert evidence["interval_ms"] == 1000
    assert (
        evidence["aligned_slot_count"]
        == 3
    )
    assert (
        evidence["paired_sample_count"]
        == 3
    )
    assert (
        evidence["paired_fraction"]
        == 1.0
    )
    assert (
        evidence[
            "first_paired_elapsed_sec"
        ]
        == 0.0
    )
    assert (
        evidence[
            "last_paired_elapsed_sec"
        ]
        == 2.0
    )
    assert (
        evidence[
            "mean_hr_bpm_on_paired_slots"
        ]
        == 110.0
    )
    assert (
        evidence[
            "mean_speed_kmh_on_paired_slots"
        ]
        == 9.0
    )


def test_missing_speed_slots_preserve_time_alignment():
    result = (
        build_exercise_hr_speed_alignment(
            {
                "provider": "POLAR",
                "series": [
                    {
                        "exercise_index": 0,
                        "metric_key": (
                            "heart_rate_bpm"
                        ),
                        "interval_ms": 1000,
                        "values": [
                            100.0,
                            110.0,
                            120.0,
                            130.0,
                        ],
                    },
                    {
                        "exercise_index": 0,
                        "metric_key": (
                            "speed_kmh"
                        ),
                        "interval_ms": 1000,
                        "values": [
                            None,
                            None,
                            9.0,
                            10.0,
                        ],
                    },
                ],
            }
        )
    )

    evidence = result["exercises"][0]

    assert (
        evidence["paired_sample_count"]
        == 2
    )
    assert (
        evidence["paired_fraction"]
        == 0.5
    )
    assert (
        evidence[
            "first_paired_elapsed_sec"
        ]
        == 2.0
    )
    assert (
        evidence[
            "last_paired_elapsed_sec"
        ]
        == 3.0
    )


def test_interval_mismatch_is_not_resampled():
    result = (
        build_exercise_hr_speed_alignment(
            {
                "provider": "POLAR",
                "series": [
                    {
                        "exercise_index": 0,
                        "metric_key": (
                            "heart_rate_bpm"
                        ),
                        "interval_ms": 1000,
                        "values": [
                            100.0,
                            110.0,
                        ],
                    },
                    {
                        "exercise_index": 0,
                        "metric_key": (
                            "speed_kmh"
                        ),
                        "interval_ms": 5000,
                        "values": [
                            9.0,
                            10.0,
                        ],
                    },
                ],
            }
        )
    )

    assert result["available"] is False

    evidence = result["exercises"][0]

    assert evidence["aligned"] is False
    assert (
        evidence["reason"]
        == "INTERVAL_MISMATCH"
    )


def test_missing_speed_series_is_reported():
    result = (
        build_exercise_hr_speed_alignment(
            {
                "provider": "POLAR",
                "series": [
                    {
                        "exercise_index": 0,
                        "metric_key": (
                            "heart_rate_bpm"
                        ),
                        "interval_ms": 1000,
                        "values": [
                            100.0,
                            110.0,
                        ],
                    }
                ],
            }
        )
    )

    assert result["available"] is False

    evidence = result["exercises"][0]

    assert evidence["aligned"] is False
    assert (
        evidence["reason"]
        == "SPEED_SERIES_MISSING"
    )