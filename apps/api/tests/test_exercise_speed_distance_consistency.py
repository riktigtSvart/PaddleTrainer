from app.services.exercise_speed_distance_consistency import (
    build_exercise_speed_distance_consistency,
)


def test_speed_integration_matches_distance():
    result = (
        build_exercise_speed_distance_consistency(
            {
                "provider": "POLAR",
                "series": [
                    {
                        "exercise_index": 0,
                        "metric_key": "speed_kmh",
                        "interval_ms": 1000,
                        "values": [3.6] * 10,
                    },
                    {
                        "exercise_index": 0,
                        "metric_key": "distance_m",
                        "interval_ms": 1000,
                        "values": [
                            float(value)
                            for value in range(10)
                        ],
                    },
                ],
            }
        )
    )

    assert result["available"] is True

    exercise = result["exercises"][0]
    overall = exercise["overall"]

    assert (
        overall["candidate_interval_count"]
        == 9
    )
    assert (
        overall["paired_interval_count"]
        == 9
    )

    assert (
        overall[
            "observed_distance_m_on_"
            "paired_intervals"
        ]
        == 9.0
    )

    assert (
        overall[
            "trapezoidal_speed_distance_m_on_"
            "paired_intervals"
        ]
        == 9.0
    )

    assert (
        overall[
            "integrated_minus_observed_"
            "distance_m"
        ]
        == 0.0
    )


def test_missing_speed_preserves_interval_alignment():
    result = (
        build_exercise_speed_distance_consistency(
            {
                "provider": "POLAR",
                "series": [
                    {
                        "exercise_index": 0,
                        "metric_key": "speed_kmh",
                        "interval_ms": 1000,
                        "values": [
                            None,
                            None,
                            3.6,
                            3.6,
                            3.6,
                            3.6,
                            3.6,
                            3.6,
                            3.6,
                            3.6,
                        ],
                    },
                    {
                        "exercise_index": 0,
                        "metric_key": "distance_m",
                        "interval_ms": 1000,
                        "values": [
                            float(value)
                            for value in range(10)
                        ],
                    },
                ],
            }
        )
    )

    overall = (
        result["exercises"][0]["overall"]
    )

    assert (
        overall["candidate_interval_count"]
        == 9
    )

    assert (
        overall["paired_interval_count"]
        == 7
    )

    assert (
        overall[
            "observed_distance_m_on_"
            "paired_intervals"
        ]
        == 7.0
    )

    assert (
        overall[
            "trapezoidal_speed_distance_m_on_"
            "paired_intervals"
        ]
        == 7.0
    )


def test_interval_mismatch_is_unavailable():
    result = (
        build_exercise_speed_distance_consistency(
            {
                "provider": "POLAR",
                "series": [
                    {
                        "exercise_index": 0,
                        "metric_key": "speed_kmh",
                        "interval_ms": 1000,
                        "values": [3.6, 3.6],
                    },
                    {
                        "exercise_index": 0,
                        "metric_key": "distance_m",
                        "interval_ms": 5000,
                        "values": [0.0, 1.0],
                    },
                ],
            }
        )
    )

    assert result["available"] is False
    assert (
        result["exercises"][0]["reason"]
        == "INTERVAL_MISMATCH"
    )