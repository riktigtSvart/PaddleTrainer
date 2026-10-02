from app.services.exercise_hr_response import (
    build_exercise_hr_response_evidence,
)
from app.services.polar_training_samples import (
    normalize_polar_training_samples,
)


def test_builds_hr_response_evidence():
    normalized = {
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
                    70.0,
                    80.0,
                    90.0,
                    90.0,
                    85.0,
                ],
            }
        ],
    }

    result = (
        build_exercise_hr_response_evidence(
            normalized
        )
    )

    assert result["available"] is True
    assert result["exercise_count"] == 1

    evidence = result["exercises"][0]

    assert evidence["slot_count"] == 5
    assert (
        evidence["valid_sample_count"]
        == 5
    )
    assert (
        evidence["missing_sample_count"]
        == 0
    )

    assert evidence["first_value"] == 70.0
    assert evidence["last_value"] == 85.0

    assert (
        evidence["minimum_value"]
        == 70.0
    )
    assert (
        evidence["maximum_value"]
        == 90.0
    )

    assert (
        evidence[
            "maximum_first_elapsed_sec"
        ]
        == 2.0
    )

    assert (
        evidence[
            "maximum_last_elapsed_sec"
        ]
        == 3.0
    )

    assert (
        evidence["maximum_sample_count"]
        == 2
    )

    assert (
        evidence["last_slot_elapsed_sec"]
        == 4.0
    )


def test_preserves_missing_slot_timing():
    normalized = {
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
                    70.0,
                    None,
                    90.0,
                ],
            }
        ],
    }

    result = (
        build_exercise_hr_response_evidence(
            normalized
        )
    )

    evidence = result["exercises"][0]

    assert evidence["slot_count"] == 3
    assert (
        evidence["valid_sample_count"]
        == 2
    )
    assert (
        evidence["missing_sample_count"]
        == 1
    )

    assert (
        evidence["coverage_fraction"]
        == 2 / 3
    )

    assert (
        evidence[
            "maximum_first_elapsed_sec"
        ]
        == 2.0
    )


def test_no_hr_series_is_unavailable():
    result = (
        build_exercise_hr_response_evidence(
            {
                "provider": "POLAR",
                "series": [],
            }
        )
    )

    assert result == {
        "metric_key": (
            "heart_rate_bpm"
        ),
        "provider": "POLAR",
        "available": False,
        "exercise_count": 0,
        "exercises": [],
    }


def test_polar_samples_feed_hr_response_evidence():
    raw_data = {
        "exerciseSamples": [
            {
                "samples": {
                    "samples": [
                        {
                            "type": "DISTANCE",
                            "intervalMillis": 1000,
                            "values": [
                                0.0,
                                1.0,
                                2.0,
                            ],
                        },
                        {
                            "type": "HEART_RATE",
                            "intervalMillis": 1000,
                            "values": [
                                70.0,
                                80.0,
                                90.0,
                            ],
                        },
                    ]
                }
            }
        ]
    }

    normalized = (
        normalize_polar_training_samples(
            raw_data
        )
    )

    result = (
        build_exercise_hr_response_evidence(
            normalized
        )
    )

    assert result["available"] is True
    assert result["provider"] == "POLAR"
    assert result["exercise_count"] == 1

    evidence = result["exercises"][0]

    assert evidence["metric_key"] == (
        "heart_rate_bpm"
    )
    assert evidence["slot_count"] == 3
    assert (
        evidence["valid_sample_count"]
        == 3
    )
    assert evidence["first_value"] == 70.0
    assert evidence["last_value"] == 90.0
    assert evidence["maximum_value"] == 90.0
    assert (
        evidence[
            "maximum_first_elapsed_sec"
        ]
        == 2.0
    )