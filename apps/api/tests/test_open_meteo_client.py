from datetime import date

from app.integrations.open_meteo.client import (
    HOURLY_VARIABLES,
    build_historical_weather_params,
)


def test_historical_weather_params_use_si_wind_and_utc_epoch_time():
    params = build_historical_weather_params(
        latitude=47.52,
        longitude=19.04,
        start_date=date(
            2026,
            9,
            30,
        ),
        end_date=date(
            2026,
            9,
            30,
        ),
    )

    assert params[
        "hourly"
    ] == ",".join(
        HOURLY_VARIABLES
    )
    assert (
        params[
            "wind_speed_unit"
        ]
        == "ms"
    )
    assert (
        params[
            "timeformat"
        ]
        == "unixtime"
    )
    assert (
        params[
            "timezone"
        ]
        == "GMT"
    )
    assert (
        params[
            "cell_selection"
        ]
        == "nearest"
    )
