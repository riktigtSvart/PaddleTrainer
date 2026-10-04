from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any


SOURCE_PROVIDER = "OPEN_METEO"
SOURCE_PRODUCT = "HISTORICAL_WEATHER_API"
SOURCE_TYPE = "MODELLED_HISTORICAL_WEATHER"
SPATIAL_SUPPORT = "GRIDDED_POINT_ESTIMATE"
TEMPORAL_RESOLUTION_SECONDS = 3600


def _finite_number(
    value: Any,
) -> float | None:
    if isinstance(
        value,
        bool,
    ):
        return None

    if not isinstance(
        value,
        (int, float),
    ):
        return None

    result = float(
        value
    )

    return (
        result
        if math.isfinite(
            result
        )
        else None
    )


def _timestamp_from_unix(
    value: Any,
) -> str | None:
    numeric = _finite_number(
        value
    )

    if numeric is None:
        return None

    return datetime.fromtimestamp(
        numeric,
        tz=timezone.utc,
    ).isoformat()


def _at(
    values: Any,
    index: int,
) -> Any:
    if not isinstance(
        values,
        list,
    ):
        return None

    if (
        index < 0
        or index >= len(
            values
        )
    ):
        return None

    return values[
        index
    ]


def normalize_open_meteo_historical_weather(
    payload: dict[str, Any],
) -> dict[str, Any]:
    hourly = (
        payload.get(
            "hourly"
        )
        if isinstance(
            payload.get(
                "hourly"
            ),
            dict,
        )
        else {}
    )

    times = (
        hourly.get(
            "time"
        )
        if isinstance(
            hourly.get(
                "time"
            ),
            list,
        )
        else []
    )

    latitude = _finite_number(
        payload.get(
            "latitude"
        )
    )
    longitude = _finite_number(
        payload.get(
            "longitude"
        )
    )
    elevation_m = _finite_number(
        payload.get(
            "elevation"
        )
    )

    samples = []

    for index, time_value in enumerate(
        times
    ):
        timestamp = (
            _timestamp_from_unix(
                time_value
            )
        )

        if (
            timestamp is None
            or latitude is None
            or longitude is None
        ):
            continue

        wind_direction = _finite_number(
            _at(
                hourly.get(
                    "wind_direction_10m"
                ),
                index,
            )
        )

        samples.append(
            {
                "sample_id": (
                    "open_meteo:"
                    f"{index}:"
                    f"{timestamp}"
                ),
                "sample_timestamp": (
                    timestamp
                ),
                "latitude_deg": (
                    latitude
                ),
                "longitude_deg": (
                    longitude
                ),
                "elevation_m": (
                    elevation_m
                ),
                "wind_speed_mps": (
                    _finite_number(
                        _at(
                            hourly.get(
                                "wind_speed_10m"
                            ),
                            index,
                        )
                    )
                ),
                "wind_direction_from_deg": (
                    wind_direction
                    % 360.0
                    if wind_direction
                    is not None
                    else None
                ),
                "wind_gust_mps": (
                    _finite_number(
                        _at(
                            hourly.get(
                                "wind_gusts_10m"
                            ),
                            index,
                        )
                    )
                ),
                "air_temperature_c": (
                    _finite_number(
                        _at(
                            hourly.get(
                                "temperature_2m"
                            ),
                            index,
                        )
                    )
                ),
                "source_provider": (
                    SOURCE_PROVIDER
                ),
                "source_product": (
                    SOURCE_PRODUCT
                ),
                "source_type": (
                    SOURCE_TYPE
                ),
                "spatial_support": (
                    SPATIAL_SUPPORT
                ),
                "temporal_resolution_seconds": (
                    TEMPORAL_RESOLUTION_SECONDS
                ),
                "source_reference": None,
            }
        )

    return {
        "provider": (
            SOURCE_PROVIDER
        ),
        "product": (
            SOURCE_PRODUCT
        ),
        "source_type": (
            SOURCE_TYPE
        ),
        "available": bool(
            samples
        ),
        "sample_count": (
            len(
                samples
            )
        ),
        "requested_location": {
            "latitude_deg": (
                latitude
            ),
            "longitude_deg": (
                longitude
            ),
            "elevation_m": (
                elevation_m
            ),
        },
        "provider_metadata": {
            "timezone": (
                payload.get(
                    "timezone"
                )
            ),
            "timezone_abbreviation": (
                payload.get(
                    "timezone_abbreviation"
                )
            ),
            "utc_offset_seconds": (
                payload.get(
                    "utc_offset_seconds"
                )
            ),
            "generationtime_ms": (
                payload.get(
                    "generationtime_ms"
                )
            ),
        },
        "samples": (
            samples
        ),
    }
