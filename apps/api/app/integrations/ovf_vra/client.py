from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx


BASE_URL = "https://vmservice.vizugy.hu/vraquery"
TOKEN_URL = "https://data.vizugy.hu/AuthApi/auth/token"

SURFACE_STATIONS_PATH = "Vra/InternetVmo/11/true"
SHORT_SERIES_PATH = "TS/TsShortList"

METRIC_WATER_LEVEL = 68
METRIC_DISCHARGE = 87
METRIC_WATER_TEMPERATURE = 85

DATA_TYPE_OPERATIONAL = 101


class OVFVRAAPIError(RuntimeError):
    pass


def build_short_series_body(
    *,
    station_registry_number: int,
    metric_code: int,
    data_type_code: int,
    start: datetime,
    end: datetime,
) -> dict[str, Any]:
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError(
            "start and end must be timezone-aware"
        )

    return {
        "TorzsszamList": [
            int(
                station_registry_number
            )
        ],
        "AdatFajtaKod": int(
            metric_code
        ),
        "AdatTipusKod": int(
            data_type_code
        ),
        "StartTime": (
            start.astimezone(
                timezone.utc
            ).isoformat()
        ),
        "EndTime": (
            end.astimezone(
                timezone.utc
            ).isoformat()
        ),
    }


class OVFVRAClient:
    def __init__(
        self,
        *,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.timeout_seconds = (
            timeout_seconds
        )
        self._token: str | None = None

    async def _get_token(
        self,
    ) -> str:
        if self._token is not None:
            return self._token

        async with httpx.AsyncClient(
            timeout=self.timeout_seconds
        ) as client:
            response = await client.get(
                TOKEN_URL,
                headers={
                    "Origin": (
                        "https://data.vizugy.hu"
                    ),
                    "Referer": (
                        "https://data.vizugy.hu/"
                    ),
                    "Accept": (
                        "application/json"
                    ),
                },
            )

        payload = self._json_or_raise(
            response,
            operation="token",
        )

        token = (
            payload.get(
                "access_token"
            )
            if isinstance(
                payload,
                dict,
            )
            else None
        )

        if not isinstance(
            token,
            str,
        ) or not token:
            raise OVFVRAAPIError(
                "OVF VRA token response "
                "did not contain access_token"
            )

        self._token = token
        return token

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> Any:
        token = await self._get_token()

        async with httpx.AsyncClient(
            timeout=self.timeout_seconds
        ) as client:
            response = await client.request(
                method,
                (
                    f"{BASE_URL}/"
                    f"{path.lstrip('/')}"
                ),
                headers={
                    "Authorization": (
                        f"Bearer {token}"
                    ),
                    "Accept": (
                        "application/json"
                    ),
                },
                **kwargs,
            )

            if response.status_code == 401:
                self._token = None
                token = await self._get_token()

                response = await client.request(
                    method,
                    (
                        f"{BASE_URL}/"
                        f"{path.lstrip('/')}"
                    ),
                    headers={
                        "Authorization": (
                            f"Bearer {token}"
                        ),
                        "Accept": (
                            "application/json"
                        ),
                    },
                    **kwargs,
                )

        return self._json_or_raise(
            response,
            operation=path,
        )

    async def get_surface_station(
        self,
        station_registry_number: int,
    ) -> dict[str, Any]:
        payload = await self._request(
            "GET",
            SURFACE_STATIONS_PATH,
        )

        if not isinstance(
            payload,
            list,
        ):
            raise OVFVRAAPIError(
                "OVF surface-station response "
                "was not a list"
            )

        matching = [
            item
            for item in payload
            if isinstance(
                item,
                dict,
            )
            and item.get(
                "Tsz"
            )
            == station_registry_number
        ]

        if len(
            matching
        ) != 1:
            raise OVFVRAAPIError(
                "OVF surface station not found "
                f"or ambiguous: "
                f"{station_registry_number}"
            )

        return matching[0]

    async def get_short_series(
        self,
        *,
        station_registry_number: int,
        metric_code: int,
        data_type_code: int,
        start: datetime,
        end: datetime,
    ) -> dict[str, Any]:
        body = build_short_series_body(
            station_registry_number=(
                station_registry_number
            ),
            metric_code=metric_code,
            data_type_code=(
                data_type_code
            ),
            start=start,
            end=end,
        )

        payload = await self._request(
            "POST",
            SHORT_SERIES_PATH,
            json=body,
        )

        if not isinstance(
            payload,
            list,
        ):
            raise OVFVRAAPIError(
                "OVF short-series response "
                "was not a list"
            )

        first = (
            payload[0]
            if payload
            and isinstance(
                payload[0],
                dict,
            )
            else {}
        )

        items = (
            first.get(
                "TsItemList"
            )
            if isinstance(
                first.get(
                    "TsItemList"
                ),
                list,
            )
            else []
        )

        return {
            "station_registry_number": (
                station_registry_number
            ),
            "metric_code": (
                metric_code
            ),
            "data_type_code": (
                data_type_code
            ),
            "source_operation": (
                f"{BASE_URL}/"
                f"{SHORT_SERIES_PATH}"
            ),
            "requested_start": (
                body[
                    "StartTime"
                ]
            ),
            "requested_end": (
                body[
                    "EndTime"
                ]
            ),
            "item_count": (
                len(
                    items
                )
            ),
            "items": (
                items
            ),
        }

    @staticmethod
    def _json_or_raise(
        response: httpx.Response,
        *,
        operation: str,
    ) -> Any:
        try:
            payload = response.json()
        except ValueError as exc:
            raise OVFVRAAPIError(
                "OVF VRA returned non-JSON "
                f"response for {operation} "
                f"({response.status_code})"
            ) from exc

        if response.is_error:
            raise OVFVRAAPIError(
                "OVF VRA request failed for "
                f"{operation} "
                f"({response.status_code})"
            )

        return payload
