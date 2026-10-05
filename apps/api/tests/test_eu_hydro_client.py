from __future__ import annotations

import asyncio

import app.integrations.eu_hydro.client as module
from app.integrations.eu_hydro.client import (
    EUHydroAPIError,
    EUHydroClient,
)


class _Response:
    def __init__(
        self,
        *,
        payload: object,
        is_success: bool = True,
        status_code: int = 200,
        text: str = "",
    ) -> None:
        self._payload = payload
        self.is_success = is_success
        self.status_code = status_code
        self.text = text

    def json(self) -> object:
        if isinstance(
            self._payload,
            Exception,
        ):
            raise self._payload

        return self._payload


class _AsyncClient:
    response = _Response(
        payload={
            "features": []
        }
    )
    last_url: str | None = None
    last_params: dict[
        str,
        str,
    ] | None = None

    def __init__(
        self,
        *,
        timeout: float,
    ) -> None:
        self.timeout = timeout

    async def __aenter__(
        self,
    ) -> "_AsyncClient":
        return self

    async def __aexit__(
        self,
        exc_type,
        exc,
        tb,
    ) -> None:
        return None

    async def get(
        self,
        url: str,
        *,
        params: dict[str, str],
        headers: dict[str, str],
    ) -> _Response:
        del headers
        type(self).last_url = url
        type(self).last_params = params
        return type(self).response


def test_river_surface_query_uses_polygon_layer(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        module.httpx,
        "AsyncClient",
        _AsyncClient,
    )
    _AsyncClient.response = _Response(
        payload={
            "features": []
        }
    )

    payload = asyncio.run(
        EUHydroClient()
        .query_river_surface_polygons(
            xmin_lon=19.0,
            ymin_lat=47.4,
            xmax_lon=19.2,
            ymax_lat=47.6,
        )
    )

    assert payload == {
        "features": []
    }
    assert _AsyncClient.last_url is not None
    assert _AsyncClient.last_url.endswith(
        "/19/query"
    )
    assert _AsyncClient.last_params is not None
    assert _AsyncClient.last_params[
        "geometryType"
    ] == "esriGeometryEnvelope"
    assert _AsyncClient.last_params[
        "inSR"
    ] == "4326"
    assert _AsyncClient.last_params[
        "outSR"
    ] == "4326"
    assert _AsyncClient.last_params[
        "returnGeometry"
    ] == "true"


def test_inland_water_query_uses_detailed_layer(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        module.httpx,
        "AsyncClient",
        _AsyncClient,
    )
    _AsyncClient.response = _Response(
        payload={
            "features": []
        }
    )

    asyncio.run(
        EUHydroClient()
        .query_inland_water_polygons(
            xmin_lon=19.0,
            ymin_lat=47.4,
            xmax_lon=19.2,
            ymax_lat=47.6,
        )
    )

    assert _AsyncClient.last_url is not None
    assert _AsyncClient.last_url.endswith(
        "/2/query"
    )


def test_arcgis_error_is_raised(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        module.httpx,
        "AsyncClient",
        _AsyncClient,
    )
    _AsyncClient.response = _Response(
        payload={
            "error": {
                "message": "boom"
            }
        }
    )

    try:
        asyncio.run(
            EUHydroClient()
            .query_river_surface_polygons(
                xmin_lon=19.0,
                ymin_lat=47.4,
                xmax_lon=19.2,
                ymax_lat=47.6,
            )
        )
    except EUHydroAPIError:
        pass
    else:
        raise AssertionError(
            "EUHydroAPIError was not raised"
        )


class _PagedAsyncClient(_AsyncClient):
    responses: list[_Response] = []
    seen_offsets: list[str] = []

    async def get(
        self,
        url: str,
        *,
        params: dict[str, str],
        headers: dict[str, str],
    ) -> _Response:
        del url, headers
        type(self).seen_offsets.append(
            params["resultOffset"]
        )
        return type(self).responses.pop(0)


def test_arcgis_transfer_limit_is_paginated(monkeypatch) -> None:
    monkeypatch.setattr(
        module.httpx,
        "AsyncClient",
        _PagedAsyncClient,
    )
    _PagedAsyncClient.seen_offsets = []
    _PagedAsyncClient.responses = [
        _Response(
            payload={
                "features": [{"attributes": {"OBJECTID": 1}}],
                "exceededTransferLimit": True,
            }
        ),
        _Response(
            payload={
                "features": [{"attributes": {"OBJECTID": 2}}],
                "exceededTransferLimit": False,
            }
        ),
    ]

    payload = asyncio.run(
        EUHydroClient().query_river_surface_polygons(
            xmin_lon=19.0,
            ymin_lat=47.4,
            xmax_lon=19.2,
            ymax_lat=47.6,
        )
    )

    assert _PagedAsyncClient.seen_offsets == ["0", "1"]
    assert [
        feature["attributes"]["OBJECTID"]
        for feature in payload["features"]
    ] == [1, 2]
    assert payload["exceededTransferLimit"] is False


def test_object_id_discovery_is_geometry_free(monkeypatch) -> None:
    monkeypatch.setattr(module.httpx, "AsyncClient", _AsyncClient)
    _AsyncClient.response = _Response(
        payload={"objectIdFieldName": "OBJECTID", "objectIds": [17, 9]}
    )

    object_ids = asyncio.run(
        EUHydroClient().query_river_surface_object_ids(
            xmin_lon=19.0,
            ymin_lat=47.4,
            xmax_lon=19.2,
            ymax_lat=47.6,
        )
    )

    assert object_ids == ("17", "9")
    assert _AsyncClient.last_params is not None
    assert _AsyncClient.last_params["returnIdsOnly"] == "true"
    assert "returnGeometry" not in _AsyncClient.last_params


def test_feature_lookup_fetches_only_requested_object_ids(monkeypatch) -> None:
    monkeypatch.setattr(module.httpx, "AsyncClient", _AsyncClient)
    _AsyncClient.response = _Response(
        payload={
            "features": [
                {"attributes": {"OBJECTID": 17}, "geometry": {"rings": []}}
            ]
        }
    )

    payload = asyncio.run(
        EUHydroClient().query_river_surface_features_by_object_ids([17])
    )

    assert len(payload["features"]) == 1
    assert _AsyncClient.last_params is not None
    assert _AsyncClient.last_params["objectIds"] == "17"
    assert _AsyncClient.last_params["returnGeometry"] == "true"
    assert "geometry" not in _AsyncClient.last_params
