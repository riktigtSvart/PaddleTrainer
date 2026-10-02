from app.services.exercise_hr_speed_windows import (
    build_exercise_hr_speed_windows,
)


def test_builds_fixed_windows():
    result = build_exercise_hr_speed_windows(
        {
            "provider": "POLAR",
            "series": [
                {
                    "exercise_index": 0,
                    "metric_key": "heart_rate_bpm",
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
                    "metric_key": "speed_kmh",
                    "interval_ms": 1000,
                    "values": [
                        8.0,
                        9.0,
                        10.0,
                        11.0,
                        12.0,
                    ],
                },
            ],
        },
        window_sec=2,
    )

    exercise = result["exercises"][0]

    assert result["available"] is True
    assert exercise["window_count"] == 3
    assert exercise["slots_per_window"] == 2

    first = exercise["windows"][0]

    assert first["start_slot"] == 0
    assert first["end_slot_exclusive"] == 2
    assert first["window_complete"] is True
    assert first["paired_sample_count"] == 2
    assert first["mean_hr_bpm"] == 105.0
    assert first["mean_speed_kmh"] == 8.5

    last = exercise["windows"][2]

    assert last["slot_count"] == 1
    assert last["window_complete"] is False
    assert last["mean_hr_bpm"] == 140.0
    assert last["mean_speed_kmh"] == 12.0


def test_missing_speed_values_preserve_window_time():
    result = build_exercise_hr_speed_windows(
        {
            "provider": "POLAR",
            "series": [
                {
                    "exercise_index": 0,
                    "metric_key": "heart_rate_bpm",
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
                    "metric_key": "speed_kmh",
                    "interval_ms": 1000,
                    "values": [
                        None,
                        None,
                        10.0,
                        11.0,
                    ],
                },
            ],
        },
        window_sec=2,
    )

    windows = (
        result["exercises"][0]["windows"]
    )

    assert (
        windows[0]["paired_sample_count"]
        == 0
    )
    assert windows[0]["paired_fraction"] == 0.0

    assert (
        windows[1]["paired_sample_count"]
        == 2
    )
    assert windows[1]["paired_fraction"] == 1.0
    assert (
        windows[1][
            "first_paired_elapsed_sec"
        ]
        == 2.0
    )


def test_interval_mismatch_is_unavailable():
    result = build_exercise_hr_speed_windows(
        {
            "provider": "POLAR",
            "series": [
                {
                    "exercise_index": 0,
                    "metric_key": "heart_rate_bpm",
                    "interval_ms": 1000,
                    "values": [100.0],
                },
                {
                    "exercise_index": 0,
                    "metric_key": "speed_kmh",
                    "interval_ms": 5000,
                    "values": [9.0],
                },
            ],
        }
    )

    assert result["available"] is False

    assert (
        result["exercises"][0]["reason"]
        == "INTERVAL_MISMATCH"
    )