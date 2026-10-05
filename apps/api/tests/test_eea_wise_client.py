from __future__ import annotations

import json

import httpx
import pytest

from app.integrations.eea_wise import client as wise_client


@pytest.mark.asyncio
async def test_client_uses_arcgis_envelope_query(monkeypatch):
    captured = {}

    class FakeResponse:
        is_success = True
        status_code = 200
        text = ""

        def json(self):
            return {
                "features": []
            }

    class FakeAsyncClient:
        def __init__(
            self,
            *args,
            **kwargs,
        ):
            captured["init"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(
            self,
            exc_type,
            exc,
            tb,
        ):
            return False

        async def get(
            self,
            url,
            *,
            params,
            headers,
        ):
            captured["url"] = url
            captured["params"] = params
            captured["headers"] = headers
            return FakeResponse()

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        FakeAsyncClient,
    )

    client = wise_client.EEAWiseClient()

    payload = (
        await client
        .query_surface_waterbody_centrelines(
            xmin_lon=19.0,
            ymin_lat=47.0,
            xmax_lon=19.1,
            ymax_lat=47.1,
        )
    )

    assert payload == {
        "features": []
    }

    params = captured["params"]

    assert (
        params["geometryType"]
        == "esriGeometryEnvelope"
    )
    assert params["inSR"] == "4326"
    assert params["outSR"] == "4326"
    assert params["returnGeometry"] == "true"
    assert params["f"] == "json"
    assert (
        params["geometry"]
        == "19.0,47.0,19.1,47.1"
    )
    assert (
        "thematicIdIdentifier"
        in params["outFields"]
    )


@pytest.mark.asyncio
async def test_client_surfaces_arcgis_error_payload(monkeypatch):
    class FakeResponse:
        is_success = True
        status_code = 200
        text = ""

        def json(self):
            return {
                "error": {
                    "code": 400,
                    "message": "bad query",
                }
            }

    class FakeAsyncClient:
        def __init__(
            self,
            *args,
            **kwargs,
        ):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(
            self,
            exc_type,
            exc,
            tb,
        ):
            return False

        async def get(
            self,
            url,
            *,
            params,
            headers,
        ):
            return FakeResponse()

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        FakeAsyncClient,
    )

    client = wise_client.EEAWiseClient()

    with pytest.raises(
        wise_client.EEAWiseAPIError
    ):
        await client.query_surface_waterbody_centrelines(
            xmin_lon=19.0,
            ymin_lat=47.0,
            xmax_lon=19.1,
            ymax_lat=47.1,
        )
