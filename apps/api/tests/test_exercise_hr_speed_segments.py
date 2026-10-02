from app.services.exercise_hr_speed_segments import (
    build_exercise_hr_speed_segments,
)


def test_builds_five_time_segments():
    result = (
        build_exercise_hr_speed_segments(
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
                            140.0,
                            150.0,
                            160.0,
                            170.0,
                            180.0,
                            190.0,
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
                            8.0,
                            9.0,
                            9.0,
                            10.0,
                            10.0,
                            11.0,
                            11.0,
                            12.0,
                            12.0,
                        ],
                    },
                ],
            }
        )
    )

    assert result["available"] is True
    assert result["exercise_count"] == 1

    exercise = result["exercises"][0]

    assert exercise["segment_count"] == 5
    assert exercise["aligned_slot_count"] == 10

    first = exercise["segments"][0]

    assert first["start_slot"] == 0
    assert first["end_slot_exclusive"] == 2
    assert first["paired_sample_count"] == 2
    assert first["paired_fraction"] == 1.0
    assert first["mean_hr_bpm"] == 105.0
    assert first["mean_speed_kmh"] == 8.0


def test_missing_speed_slots_do_not_shift_time():
    result = (
        build_exercise_hr_speed_segments(
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
                            140.0,
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
                            9.0,
                            10.0,
                            11.0,
                            12.0,
                        ],
                    },
                ],
            }
        )
    )

    exercise = result["exercises"][0]

    first = exercise["segments"][0]

    assert first["start_elapsed_sec"] == 0.0
    assert (
        first["end_elapsed_sec_exclusive"]
        == 1.0
    )
    assert first["paired_sample_count"] == 0


def test_interval_mismatch_is_unavailable():
    result = (
        build_exercise_hr_speed_segments(
            {
                "provider": "POLAR",
                "series": [
                    {
                        "exercise_index": 0,
                        "metric_key": (
                            "heart_rate_bpm"
                        ),
                        "interval_ms": 1000,
                        "values": [100.0],
                    },
                    {
                        "exercise_index": 0,
                        "metric_key": (
                            "speed_kmh"
                        ),
                        "interval_ms": 5000,
                        "values": [9.0],
                    },
                ],
            }
        )
    )

    assert result["available"] is False
    assert result["exercise_count"] == 0