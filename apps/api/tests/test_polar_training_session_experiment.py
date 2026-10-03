from datetime import date

import pytest

from app.services.polar_training_session_experiment import (
    build_discovery_ranges,
    build_training_session_experiment_sample,
)


def _session(
    external_id,
    day,
    *,
    sport_id=95,
    hour=8,
):
    return {
        "identifier": {
            "id": external_id,
        },
        "startTime": (
            f"{day}T{hour:02d}:00:00"
        ),
        "stopTime": (
            f"{day}T09:00:00"
        ),
        "durationMillis": 3600000,
        "distanceMeters": 10000.0,
        "sport": {
            "id": sport_id,
        },
        "name": "Training",
    }


def test_discovery_ranges_are_non_overlapping_and_max_90_days():
    ranges = build_discovery_ranges(
        date(
            2026,
            4,
            1,
        ),
        date(
            2026,
            10,
            1,
        ),
    )

    assert len(
        ranges
    ) == 3

    assert ranges[0][0] == date(
        2026,
        4,
        1,
    )

    assert ranges[-1][1] == date(
        2026,
        10,
        1,
    )

    assert all(
        (
            end - start
        ).days
        <= 90
        for start, end
        in ranges
    )

    assert all(
        ranges[index][1]
        == ranges[
            index + 1
        ][0]
        for index
        in range(
            len(ranges) - 1
        )
    )


def test_discovery_range_requires_positive_interval():
    with pytest.raises(
        ValueError,
        match=(
            "to_date must be after from_date"
        ),
    ):
        build_discovery_ranges(
            date(
                2026,
                4,
                1,
            ),
            date(
                2026,
                4,
                1,
            ),
        )


def test_sample_filters_sport_and_interval():
    payload = {
        "trainingSessions": [
            _session(
                "kayak-in",
                "2026-04-10",
            ),
            _session(
                "other-sport",
                "2026-04-11",
                sport_id=1,
            ),
            _session(
                "before",
                "2026-03-31",
            ),
            _session(
                "exclusive-end",
                "2026-05-01",
            ),
        ]
    }

    result = (
        build_training_session_experiment_sample(
            [
                payload
            ],
            from_date=date(
                2026,
                4,
                1,
            ),
            to_date=date(
                2026,
                5,
                1,
            ),
            sport_id=95,
        )
    )

    assert (
        result[
            "matching_session_count"
        ]
        == 1
    )

    assert (
        result[
            "selected_sessions"
        ][0][
            "external_id"
        ]
        == "kayak-in"
    )


def test_nine_sessions_select_third_and_sixth():
    payload = {
        "trainingSessions": [
            _session(
                f"s{index}",
                f"2026-05-{index:02d}",
            )
            for index
            in range(
                1,
                10,
            )
        ]
    }

    result = (
        build_training_session_experiment_sample(
            [
                payload
            ],
            from_date=date(
                2026,
                5,
                1,
            ),
            to_date=date(
                2026,
                6,
                1,
            ),
            sport_id=95,
        )
    )

    month = result[
        "months"
    ][0]

    assert (
        month[
            "selection_indices_zero_based"
        ]
        == [
            2,
            5,
        ]
    )

    assert [
        item[
            "external_id"
        ]
        for item
        in month[
            "selected"
        ]
    ] == [
        "s3",
        "s6",
    ]


def test_one_session_month_keeps_one_without_inventing_second():
    payload = {
        "trainingSessions": [
            _session(
                "only",
                "2026-06-15",
            )
        ]
    }

    result = (
        build_training_session_experiment_sample(
            [
                payload
            ],
            from_date=date(
                2026,
                6,
                1,
            ),
            to_date=date(
                2026,
                7,
                1,
            ),
            sport_id=95,
        )
    )

    month = result[
        "months"
    ][0]

    assert (
        month[
            "selected_count"
        ]
        == 1
    )

    assert (
        month[
            "selected"
        ][0][
            "external_id"
        ]
        == "only"
    )


def test_payload_boundaries_are_deduplicated_by_external_id():
    repeated = _session(
        "same-session",
        "2026-07-10",
    )

    result = (
        build_training_session_experiment_sample(
            [
                {
                    "trainingSessions": [
                        repeated
                    ]
                },
                {
                    "trainingSessions": [
                        repeated
                    ]
                },
            ],
            from_date=date(
                2026,
                7,
                1,
            ),
            to_date=date(
                2026,
                8,
                1,
            ),
            sport_id=95,
        )
    )

    assert (
        result[
            "matching_session_count"
        ]
        == 1
    )


def test_nested_sport_identifier_is_supported():
    nested = _session(
        "nested",
        "2026-08-10",
    )

    nested[
        "sport"
    ] = {
        "id": {
            "id": 95,
        }
    }

    result = (
        build_training_session_experiment_sample(
            [
                {
                    "trainingSessions": [
                        nested
                    ]
                }
            ],
            from_date=date(
                2026,
                8,
                1,
            ),
            to_date=date(
                2026,
                9,
                1,
            ),
            sport_id=95,
        )
    )

    assert (
        result[
            "matching_session_count"
        ]
        == 1
    )


def test_string_sport_identifier_is_supported():
    string_sport = _session(
        "string-sport",
        "2026-09-10",
    )

    string_sport[
        "sport"
    ] = {
        "id": "95",
    }

    result = (
        build_training_session_experiment_sample(
            [
                {
                    "trainingSessions": [
                        string_sport
                    ]
                }
            ],
            from_date=date(
                2026,
                9,
                1,
            ),
            to_date=date(
                2026,
                10,
                1,
            ),
            sport_id=95,
        )
    )

    assert (
        result[
            "matching_session_count"
        ]
        == 1
    )

    assert (
        result[
            "selected_sessions"
        ][0][
            "sport_id"
        ]
        == 95
    )
