from __future__ import annotations

from datetime import date
from typing import Any

import httpx


ARCHIVE_BASE = "https://archive-api.open-meteo.com/v1/archive"

HOURLY_VARIABLES = (
    "temperature_2m",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
)


class OpenMeteoAPIError(RuntimeError):
    pass


def build_historical_weather_params(
    *,
    latitude: float,
    longitude: float,
    start_date: date,
    end_date: date,
) -> dict[str, Any]:
    return {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "hourly": ",".join(
            HOURLY_VARIABLES
        ),
        "wind_speed_unit": "ms",
        "temperature_unit": "celsius",
        "timeformat": "unixtime",
        "timezone": "GMT",
        "cell_selection": "nearest",
    }


class OpenMeteoHistoricalWeatherClient:
    async def get_hourly_weather(
        self,
        *,
        latitude: float,
        longitude: float,
        start_date: date,
        end_date: date,
    ) -> dict[str, Any]:
        params = build_historical_weather_params(
            latitude=latitude,
            longitude=longitude,
            start_date=start_date,
            end_date=end_date,
        )

        async with httpx.AsyncClient(
            timeout=20.0
        ) as client:
            response = await client.get(
                ARCHIVE_BASE,
                params=params,
                headers={
                    "Accept": "application/json",
                },
            )

        return self._json_or_raise(
            response
        )

    @staticmethod
    def _json_or_raise(
        response: httpx.Response,
    ) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise OpenMeteoAPIError(
                "Open-Meteo returned non-JSON response "
                f"({response.status_code})"
            ) from exc

        if response.is_error:
            reason = None

            if isinstance(
                payload,
                dict,
            ):
                reason = payload.get(
                    "reason"
                )

            raise OpenMeteoAPIError(
                str(
                    reason
                    or (
                        "Open-Meteo request failed "
                        f"({response.status_code})"
                    )
                )
            )

        if not isinstance(
            payload,
            dict,
        ):
            raise OpenMeteoAPIError(
                "Open-Meteo returned unexpected JSON payload"
            )

        return payload
