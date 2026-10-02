from app.services.exercise_hr_trajectory import (
    build_exercise_hr_trajectory_evidence,
)


def test_builds_fixed_windows_and_quintiles():
    values = [
        float(value)
        for value in range(120)
    ]

    result = (
        build_exercise_hr_trajectory_evidence(
            {
                "provider": "POLAR",
                "series": [
                    {
                        "exercise_index": 0,
                        "metric_key": (
                            "heart_rate_bpm"
                        ),
                        "unit": "bpm",
                        "source_type": (
                            "HEART_RATE"
                        ),
                        "interval_ms": 1000,
                        "values": values,
                    }
                ],
            }
        )
    )

    assert result["available"] is True
    assert result["exercise_count"] == 1

    evidence = result["exercises"][0]

    first_60 = (
        evidence["windows"][
            "first_60_sec"
        ]
    )

    last_60 = (
        evidence["windows"][
            "last_60_sec"
        ]
    )

    assert first_60["slot_count"] == 60
    assert first_60["mean_bpm"] == 29.5

    assert last_60["slot_count"] == 60
    assert last_60["mean_bpm"] == 89.5

    assert (
        evidence[
            "last_60_minus_"
            "first_60_mean_bpm"
        ]
        == 60.0
    )

    assert len(evidence["quintiles"]) == 5


def test_missing_values_do_not_shift_timing():
    values = [
        70.0,
        None,
        80.0,
        90.0,
    ]

    result = (
        build_exercise_hr_trajectory_evidence(
            {
                "provider": "POLAR",
                "series": [
                    {
                        "exercise_index": 0,
                        "metric_key": (
                            "heart_rate_bpm"
                        ),
                        "unit": "bpm",
                        "source_type": (
                            "HEART_RATE"
                        ),
                        "interval_ms": 1000,
                        "values": values,
                    }
                ],
            }
        )
    )

    evidence = result["exercises"][0]

    assert evidence["slot_count"] == 4

    first = evidence[
        "windows"
    ]["first_60_sec"]

    assert first["slot_count"] == 4
    assert first["valid_sample_count"] == 3
    assert first["mean_bpm"] == 80.0


def test_no_hr_series_is_unavailable():
    result = (
        build_exercise_hr_trajectory_evidence(
            {
                "provider": "POLAR",
                "series": [],
            }
        )
    )

    assert result["available"] is False
    assert result["exercise_count"] == 0
    assert result["exercises"] == []


def test_all_missing_hr_values_are_unavailable():
    result = (
        build_exercise_hr_trajectory_evidence(
            {
                "provider": "POLAR",
                "series": [
                    {
                        "exercise_index": 0,
                        "metric_key": (
                            "heart_rate_bpm"
                        ),
                        "unit": "bpm",
                        "source_type": (
                            "HEART_RATE"
                        ),
                        "interval_ms": 1000,
                        "values": [
                            None,
                            None,
                            None,
                        ],
                    }
                ],
            }
        )
    )

    assert result["available"] is False
    assert result["exercise_count"] == 1

    assert (
        result["exercises"][0][
            "observations_available"
        ]
        is False
    )