from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import httpx


BASE_URL = (
    "https://image.discomap.eea.europa.eu"
    "/arcgis/rest/services/EUHydro/"
    "EUHydro_RiverNetworkDatabase/MapServer"
)

RIVER_SURFACE_LAYER_ID = 19
INLAND_WATER_LAYER_ID = 2

RIVER_SURFACE_OUT_FIELDS = ",".join(
    [
        "OBJECTID",
        "WCOURSE_ID",
        "OBJECT_ID",
        "INSPIRE_ID",
        "AREA_GEO",
    ]
)

INLAND_WATER_OUT_FIELDS = ",".join(
    [
        "OBJECTID",
        "NAM",
        "WSO_ID",
        "OBJECT_ID",
        "INSPIRE_ID",
        "AREA_GEO",
        "thematicId",
    ]
)


class EUHydroAPIError(RuntimeError):
    pass


class EUHydroClient:
    async def query_river_surface_polygons(
        self,
        *,
        xmin_lon: float,
        ymin_lat: float,
        xmax_lon: float,
        ymax_lat: float,
    ) -> dict[str, Any]:
        return await self._query_polygon_layer(
            layer_id=RIVER_SURFACE_LAYER_ID,
            out_fields=RIVER_SURFACE_OUT_FIELDS,
            xmin_lon=xmin_lon,
            ymin_lat=ymin_lat,
            xmax_lon=xmax_lon,
            ymax_lat=ymax_lat,
        )

    async def query_inland_water_polygons(
        self,
        *,
        xmin_lon: float,
        ymin_lat: float,
        xmax_lon: float,
        ymax_lat: float,
    ) -> dict[str, Any]:
        return await self._query_polygon_layer(
            layer_id=INLAND_WATER_LAYER_ID,
            out_fields=INLAND_WATER_OUT_FIELDS,
            xmin_lon=xmin_lon,
            ymin_lat=ymin_lat,
            xmax_lon=xmax_lon,
            ymax_lat=ymax_lat,
        )

    async def query_river_surface_object_ids(
        self,
        *,
        xmin_lon: float,
        ymin_lat: float,
        xmax_lon: float,
        ymax_lat: float,
    ) -> tuple[str, ...]:
        return await self._query_object_ids(
            layer_id=RIVER_SURFACE_LAYER_ID,
            xmin_lon=xmin_lon,
            ymin_lat=ymin_lat,
            xmax_lon=xmax_lon,
            ymax_lat=ymax_lat,
        )

    async def query_inland_water_object_ids(
        self,
        *,
        xmin_lon: float,
        ymin_lat: float,
        xmax_lon: float,
        ymax_lat: float,
    ) -> tuple[str, ...]:
        return await self._query_object_ids(
            layer_id=INLAND_WATER_LAYER_ID,
            xmin_lon=xmin_lon,
            ymin_lat=ymin_lat,
            xmax_lon=xmax_lon,
            ymax_lat=ymax_lat,
        )

    async def query_river_surface_features_by_object_ids(
        self,
        object_ids: Sequence[str | int],
    ) -> dict[str, Any]:
        return await self._query_features_by_object_ids(
            layer_id=RIVER_SURFACE_LAYER_ID,
            out_fields=RIVER_SURFACE_OUT_FIELDS,
            object_ids=object_ids,
        )

    async def query_inland_water_features_by_object_ids(
        self,
        object_ids: Sequence[str | int],
    ) -> dict[str, Any]:
        return await self._query_features_by_object_ids(
            layer_id=INLAND_WATER_LAYER_ID,
            out_fields=INLAND_WATER_OUT_FIELDS,
            object_ids=object_ids,
        )

    async def _query_object_ids(
        self,
        *,
        layer_id: int,
        xmin_lon: float,
        ymin_lat: float,
        xmax_lon: float,
        ymax_lat: float,
    ) -> tuple[str, ...]:
        _validate_bounds(xmin_lon, ymin_lat, xmax_lon, ymax_lat)
        payload = await self._request_json(
            layer_id=layer_id,
            params={
                "where": "1=1",
                "geometry": f"{xmin_lon},{ymin_lat},{xmax_lon},{ymax_lat}",
                "geometryType": "esriGeometryEnvelope",
                "inSR": "4326",
                "spatialRel": "esriSpatialRelIntersects",
                "returnIdsOnly": "true",
                "f": "json",
            },
        )
        raw_ids = payload.get("objectIds")
        if not isinstance(raw_ids, list):
            return ()
        return tuple(str(value) for value in raw_ids if value is not None)

    async def _query_features_by_object_ids(
        self,
        *,
        layer_id: int,
        out_fields: str,
        object_ids: Sequence[str | int],
    ) -> dict[str, Any]:
        normalized = tuple(dict.fromkeys(str(value) for value in object_ids))
        if not normalized:
            return {"features": []}

        combined: list[Any] = []
        first_payload: dict[str, Any] | None = None
        # Large individual geometries make small batches safer for ArcGIS and
        # keep retries bounded to a limited set of provider features.
        for offset in range(0, len(normalized), 50):
            batch = normalized[offset : offset + 50]
            payload = await self._request_json(
                layer_id=layer_id,
                params={
                    "objectIds": ",".join(batch),
                    "outFields": out_fields,
                    "returnGeometry": "true",
                    "returnZ": "false",
                    "returnM": "false",
                    "outSR": "4326",
                    "orderByFields": "OBJECTID",
                    "f": "json",
                },
            )
            if first_payload is None:
                first_payload = dict(payload)
            features = payload.get("features")
            if isinstance(features, list):
                combined.extend(features)

        result = dict(first_payload or {})
        result["features"] = combined
        return result

    async def _query_polygon_layer(
        self,
        *,
        layer_id: int,
        out_fields: str,
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
            "outFields": out_fields,
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
                layer_id=layer_id,
                params={**base_params, "resultOffset": str(offset)},
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
        result["page_count"] = (offset // 1000) + 1 if combined_features else 1
        return result

    async def _request_json(
        self,
        *,
        layer_id: int,
        params: dict[str, str],
    ) -> dict[str, Any]:
        url = f"{BASE_URL}/{layer_id}/query"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                url,
                params=params,
                headers={"Accept": "application/json"},
            )
        if not response.is_success:
            raise EUHydroAPIError(
                f"EU-Hydro API {response.status_code}: {response.text}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise EUHydroAPIError("EU-Hydro API returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise EUHydroAPIError("EU-Hydro API returned an unexpected payload")
        error = payload.get("error")
        if error is not None:
            raise EUHydroAPIError(f"EU-Hydro ArcGIS query error: {error}")
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
