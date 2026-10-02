from app.services.polar_training_samples import (
    normalize_polar_training_samples,
)


def test_normalizes_heart_rate_series():
    result = normalize_polar_training_samples(
        {
            "exerciseSamples": [
                {
                    "samples": {
                        "samples": [
                            {
                                "type": (
                                    "HEART_RATE"
                                ),
                                "intervalMillis": (
                                    1000
                                ),
                                "values": [
                                    100,
                                    101,
                                    103,
                                ],
                            }
                        ]
                    }
                }
            ]
        }
    )

    assert result["provider"] == "POLAR"
    assert result["exercise_count"] == 1
    assert result["source_types"] == [
        "HEART_RATE"
    ]

    assert result["series"] == [
        {
            "exercise_index": 0,
            "metric_key": (
                "heart_rate_bpm"
            ),
            "unit": "bpm",
            "source_type": "HEART_RATE",
            "interval_ms": 1000,
            "slot_count": 3,
            "valid_sample_count": 3,
            "values": [
                100.0,
                101.0,
                103.0,
            ],
        }
    ]


def test_preserves_time_slots_for_invalid_values():
    result = normalize_polar_training_samples(
        {
            "exerciseSamples": [
                {
                    "samples": {
                        "samples": [
                            {
                                "type": (
                                    "HEART_RATE"
                                ),
                                "intervalMillis": (
                                    1000
                                ),
                                "values": [
                                    100,
                                    "NaN",
                                    102,
                                ],
                            }
                        ]
                    }
                }
            ]
        }
    )

    series = result["series"][0]

    assert series["slot_count"] == 3
    assert (
        series["valid_sample_count"]
        == 2
    )
    assert series["values"] == [
        100.0,
        None,
        102.0,
    ]


def test_reports_unmapped_source_types_without_interpreting_them():
    result = normalize_polar_training_samples(
        {
            "exerciseSamples": [
                {
                    "samples": {
                        "samples": [
                            {
                                "type": (
                                    "HEART_RATE"
                                ),
                                "intervalMillis": (
                                    1000
                                ),
                                "values": [100],
                            },
                            {
                                "type": (
                                    "LEFT_CRANK_"
                                    "CURRENT_POWER"
                                ),
                                "intervalMillis": (
                                    1000
                                ),
                                "values": [175],
                            },
                        ]
                    }
                }
            ]
        }
    )

    assert result["source_types"] == [
        "HEART_RATE",
        "LEFT_CRANK_CURRENT_POWER",
    ]

    assert len(result["series"]) == 1

    assert (
        result["series"][0][
            "metric_key"
        ]
        == "heart_rate_bpm"
    )


def test_normalizes_speed_and_distance_without_shifting_slots():
    raw_data = {
        "exerciseSamples": [
            {
                "samples": {
                    "samples": [
                        {
                            "type": "SPEED",
                            "intervalMillis": 1000,
                            "values": [
                                2.5,
                                "NaN",
                                3.25,
                            ],
                        },
                        {
                            "type": "DISTANCE",
                            "intervalMillis": 1000,
                            "values": [
                                0.0,
                                2.5,
                                5.75,
                            ],
                        },
                    ]
                }
            }
        ]
    }

    result = normalize_polar_training_samples(
        raw_data
    )

    assert result["provider"] == "POLAR"
    assert result["exercise_count"] == 1

    by_metric = {
        series["metric_key"]: series
        for series in result["series"]
    }

    speed = by_metric["speed_kmh"]

    assert speed["unit"] == "km/h"
    assert speed["source_type"] == "SPEED"
    assert speed["interval_ms"] == 1000
    assert speed["slot_count"] == 3
    assert speed["valid_sample_count"] == 2
    assert speed["values"] == [
        2.5,
        None,
        3.25,
    ]

    distance = by_metric["distance_m"]

    assert distance["unit"] == "m"
    assert distance["source_type"] == "DISTANCE"
    assert distance["interval_ms"] == 1000
    assert distance["slot_count"] == 3
    assert distance["valid_sample_count"] == 3
    assert distance["values"] == [
        0.0,
        2.5,
        5.75,
    ]