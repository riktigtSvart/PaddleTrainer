from __future__ import annotations

import asyncio

import app.integrations.eea_msfd.client as module
from app.integrations.eea_msfd.client import EEAMSFDAPIError, EEAMSFDClient


class _Response:
    def __init__(self, payload: object, *, success: bool = True) -> None:
        self._payload = payload
        self.is_success = success
        self.status_code = 200 if success else 500
        self.text = "boom" if not success else ""

    def json(self) -> object:
        return self._payload


class _AsyncClient:
    response = _Response({"features": []})
    last_url: str | None = None
    last_params: dict[str, str] | None = None

    def __init__(self, *, timeout: float) -> None:
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, url: str, *, params, headers):
        del headers
        type(self).last_url = url
        type(self).last_params = dict(params)
        return type(self).response


def test_query_uses_msfd_polygon_layer_and_wgs84(monkeypatch) -> None:
    monkeypatch.setattr(module.httpx, "AsyncClient", _AsyncClient)
    _AsyncClient.response = _Response({"features": []})

    result = asyncio.run(
        EEAMSFDClient().query_marine_region_polygons(
            xmin_lon=15.19,
            ymin_lat=44.24,
            xmax_lon=15.22,
            ymax_lat=44.28,
        )
    )

    assert result == {"features": []}
    assert _AsyncClient.last_url is not None
    assert _AsyncClient.last_url.endswith("/0/query")
    assert _AsyncClient.last_params["geometryType"] == "esriGeometryEnvelope"
    assert _AsyncClient.last_params["inSR"] == "4326"
    assert _AsyncClient.last_params["outSR"] == "4326"
    assert _AsyncClient.last_params["returnGeometry"] == "true"
    assert "subregionName" in _AsyncClient.last_params["outFields"]
    assert "regionName" in _AsyncClient.last_params["outFields"]


def test_arcgis_error_is_raised(monkeypatch) -> None:
    monkeypatch.setattr(module.httpx, "AsyncClient", _AsyncClient)
    _AsyncClient.response = _Response({"error": {"message": "bad"}})

    try:
        asyncio.run(
            EEAMSFDClient().query_marine_region_polygons(
                xmin_lon=15.19,
                ymin_lat=44.24,
                xmax_lon=15.22,
                ymax_lat=44.28,
            )
        )
    except EEAMSFDAPIError:
        pass
    else:
        raise AssertionError("EEAMSFDAPIError was not raised")


def test_object_id_discovery_uses_return_ids_only(monkeypatch) -> None:
    monkeypatch.setattr(module.httpx, "AsyncClient", _AsyncClient)
    _AsyncClient.response = _Response({"objectIds": [9, 7, 7]})

    result = asyncio.run(
        EEAMSFDClient().query_marine_region_object_ids(
            xmin_lon=15.19,
            ymin_lat=44.24,
            xmax_lon=15.22,
            ymax_lat=44.28,
        )
    )

    assert result == ("7", "9")
    assert _AsyncClient.last_params["returnIdsOnly"] == "true"
    assert _AsyncClient.last_params["geometryType"] == "esriGeometryEnvelope"
    assert "returnGeometry" not in _AsyncClient.last_params


def test_feature_download_queries_specific_object_ids(monkeypatch) -> None:
    monkeypatch.setattr(module.httpx, "AsyncClient", _AsyncClient)
    _AsyncClient.response = _Response(
        {
            "features": [
                {"attributes": {"OBJECTID": 7}, "geometry": {"rings": []}},
                {"attributes": {"OBJECTID": 9}, "geometry": {"rings": []}},
            ]
        }
    )

    result = asyncio.run(
        EEAMSFDClient().query_marine_region_features_by_object_ids([7, 9])
    )

    assert len(result["features"]) == 2
    assert _AsyncClient.last_params["objectIds"] == "7,9"
    assert _AsyncClient.last_params["returnGeometry"] == "true"
    assert "subregionName" in _AsyncClient.last_params["outFields"]
