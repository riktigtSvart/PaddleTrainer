from __future__ import annotations

from typing import Any

import httpx


BASE_URL = (
    "https://water.discomap.eea.europa.eu"
    "/arcgis/rest/services/Marine/"
    "MSFD_regions_and_subregions/MapServer"
)
MARINE_REGION_LAYER_ID = 0
OUT_FIELDS = ",".join(
    [
        "OBJECTID",
        "subregion",
        "subregionName",
        "region",
        "regionName",
        "zoneType",
        "spZoneType",
        "envDomain",
        "sizeValue",
        "sizeUom",
    ]
)


class EEAMSFDAPIError(RuntimeError):
    pass


class EEAMSFDClient:
    """Small ArcGIS client for EEA MSFD marine region/subregion polygons."""

    async def query_marine_region_polygons(
        self,
        *,
        xmin_lon: float,
        ymin_lat: float,
        xmax_lon: float,
        ymax_lat: float,
    ) -> dict[str, Any]:
        _validate_bounds(xmin_lon, ymin_lat, xmax_lon, ymax_lat)

        base_params = {
            "where": "1=1",
            "geometry": f"{xmin_lon},{ymin_lat},{xmax_lon},{ymax_lat}",
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "outSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": OUT_FIELDS,
            "returnGeometry": "true",
            "returnZ": "false",
            "returnM": "false",
            "orderByFields": "OBJECTID",
            "resultRecordCount": "1000",
            "f": "json",
        }

        offset = 0
        combined_features: list[Any] = []
        first_payload: dict[str, Any] | None = None

        while True:
            payload = await self._request_json(
                params={**base_params, "resultOffset": str(offset)}
            )
            if first_payload is None:
                first_payload = dict(payload)

            features = payload.get("features")
            if not isinstance(features, list):
                return payload

            combined_features.extend(features)
            exceeded = payload.get("exceededTransferLimit") is True
            if not exceeded or not features:
                if offset == 0:
                    return payload
                break
            offset += len(features)

        result = dict(first_payload or {})
        result["features"] = combined_features
        result["exceededTransferLimit"] = False
        return result

    async def _request_json(
        self,
        *,
        params: dict[str, str],
    ) -> dict[str, Any]:
        url = f"{BASE_URL}/{MARINE_REGION_LAYER_ID}/query"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                url,
                params=params,
                headers={"Accept": "application/json"},
            )

        if not response.is_success:
            raise EEAMSFDAPIError(
                f"EEA MSFD API {response.status_code}: {response.text}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise EEAMSFDAPIError(
                "EEA MSFD API returned invalid JSON"
            ) from exc

        if not isinstance(payload, dict):
            raise EEAMSFDAPIError(
                "EEA MSFD API returned an unexpected payload"
            )

        error = payload.get("error")
        if error is not None:
            raise EEAMSFDAPIError(
                f"EEA MSFD ArcGIS query error: {error}"
            )

        return payload


def _validate_bounds(
    xmin_lon: float,
    ymin_lat: float,
    xmax_lon: float,
    ymax_lat: float,
) -> None:
    if xmin_lon > xmax_lon:
        raise ValueError("xmin_lon must be <= xmax_lon")
    if ymin_lat > ymax_lat:
        raise ValueError("ymin_lat must be <= ymax_lat")
