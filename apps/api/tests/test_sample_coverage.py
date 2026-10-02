from app.services.sample_coverage import (
    build_sample_coverage_evidence,
)


def test_complete_series_coverage():
    result = build_sample_coverage_evidence(
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
                        70.0,
                        80.0,
                        90.0,
                        100.0,
                        110.0,
                    ],
                }
            ],
        },
        session_duration_sec=5,
    )

    assert result["provider"] == "POLAR"
    assert result["series_count"] == 1

    coverage = result["series"][0]

    assert coverage["slot_count"] == 5
    assert (
        coverage["valid_sample_count"]
        == 5
    )
    assert (
        coverage["missing_sample_count"]
        == 0
    )

    assert (
        coverage[
            "value_completeness_fraction"
        ]
        == 1.0
    )

    assert (
        coverage["last_slot_elapsed_sec"]
        == 4.0
    )
    assert (
        coverage["sample_grid_span_sec"]
        == 4.0
    )

    assert (
        coverage[
            "session_end_minus_last_slot_sec"
        ]
        == 1.0
    )

    assert (
        coverage[
            "maximum_consecutive_missing_slots"
        ]
        == 0
    )


def test_internal_missing_samples_are_preserved():
    result = build_sample_coverage_evidence(
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
                        70.0,
                        None,
                        None,
                        100.0,
                        None,
                    ],
                }
            ],
        },
        session_duration_sec=8,
    )

    coverage = result["series"][0]

    assert coverage["slot_count"] == 5
    assert (
        coverage["valid_sample_count"]
        == 2
    )
    assert (
        coverage["missing_sample_count"]
        == 3
    )

    assert (
        coverage[
            "value_completeness_fraction"
        ]
        == 0.4
    )

    assert (
        coverage["leading_missing_slots"]
        == 0
    )
    assert (
        coverage["trailing_missing_slots"]
        == 1
    )

    assert (
        coverage[
            "maximum_consecutive_missing_slots"
        ]
        == 2
    )
    assert (
        coverage[
            "maximum_consecutive_missing_sec"
        ]
        == 2.0
    )

    assert (
        coverage[
            "first_valid_elapsed_sec"
        ]
        == 0.0
    )
    assert (
        coverage[
            "last_valid_elapsed_sec"
        ]
        == 3.0
    )


def test_no_interval_does_not_invent_timing():
    result = build_sample_coverage_evidence(
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
                    "interval_ms": None,
                    "values": [
                        70.0,
                        80.0,
                    ],
                }
            ],
        },
        session_duration_sec=10,
    )

    coverage = result["series"][0]

    assert (
        coverage["last_slot_elapsed_sec"]
        is None
    )
    assert (
        coverage["sample_grid_span_sec"]
        is None
    )
    assert (
        coverage[
            "session_end_minus_last_slot_sec"
        ]
        is None
    )