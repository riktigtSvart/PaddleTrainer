from datetime import datetime, timezone

from app.services.open_meteo_weather import (
    SOURCE_TYPE,
    normalize_open_meteo_historical_weather,
)


def test_normalizes_hourly_open_meteo_to_provider_independent_samples():
    first_epoch = int(
        datetime(
            2026,
            9,
            30,
            15,
            0,
            tzinfo=timezone.utc,
        ).timestamp()
    )

    payload = {
        "latitude": 47.5,
        "longitude": 19.0,
        "elevation": 100.0,
        "timezone": "GMT",
        "timezone_abbreviation": "GMT",
        "utc_offset_seconds": 0,
        "hourly": {
            "time": [
                first_epoch,
                first_epoch
                + 3600,
            ],
            "temperature_2m": [
                17.2,
                16.8,
            ],
            "wind_speed_10m": [
                4.0,
                5.0,
            ],
            "wind_direction_10m": [
                350.0,
                370.0,
            ],
            "wind_gusts_10m": [
                6.0,
                7.0,
            ],
        },
    }

    result = (
        normalize_open_meteo_historical_weather(
            payload
        )
    )

    assert (
        result[
            "source_type"
        ]
        == SOURCE_TYPE
    )
    assert result["sample_count"] == 2

    first = result["samples"][0]
    second = result["samples"][1]

    assert (
        first[
            "sample_timestamp"
        ]
        == "2026-09-30T15:00:00+00:00"
    )
    assert (
        first[
            "wind_speed_mps"
        ]
        == 4.0
    )
    assert (
        second[
            "wind_direction_from_deg"
        ]
        == 10.0
    )
    assert (
        first[
            "source_type"
        ]
        == "MODELLED_HISTORICAL_WEATHER"
    )


def test_missing_hourly_values_are_preserved_as_unavailable_fields():
    epoch = int(
        datetime(
            2026,
            9,
            30,
            15,
            0,
            tzinfo=timezone.utc,
        ).timestamp()
    )

    result = (
        normalize_open_meteo_historical_weather(
            {
                "latitude": 47.5,
                "longitude": 19.0,
                "hourly": {
                    "time": [
                        epoch
                    ],
                    "wind_speed_10m": [
                        None
                    ],
                },
            }
        )
    )

    sample = result["samples"][0]

    assert (
        sample[
            "wind_speed_mps"
        ]
        is None
    )
    assert (
        sample[
            "wind_direction_from_deg"
        ]
        is None
    )
