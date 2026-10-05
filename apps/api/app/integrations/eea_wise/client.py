from __future__ import annotations

from typing import Any

import httpx


BASE_URL = (
    "https://water.discomap.eea.europa.eu"
    "/arcgis/rest/services/WISE_WFD/"
    "WFD2022_SurfaceWaterBodyCentreline_WM/"
    "MapServer/0/query"
)

OUT_FIELDS = ",".join(
    [
        "OBJECTID",
        "cYear",
        "continua",
        "geometry",
        "statusDate",
        "qcCheck",
        "countryCode",
        "thematicIdIdentifier",
        "thematicIdIdentifierScheme",
        "hydroIdLocalId",
        "hydroIdNamespace",
        "geographicalNameText",
        "geographicalNameLanguage",
        "specialisedZoneType",
        "id",
    ]
)


class EEAWiseAPIError(
    RuntimeError
):
    pass


class EEAWiseClient:
    async def query_surface_waterbody_centrelines(
        self,
        *,
        xmin_lon: float,
        ymin_lat: float,
        xmax_lon: float,
        ymax_lat: float,
    ) -> dict[str, Any]:
        params = {
            "where": "1=1",
            "geometry": (
                f"{xmin_lon},"
                f"{ymin_lat},"
                f"{xmax_lon},"
                f"{ymax_lat}"
            ),
            "geometryType": (
                "esriGeometryEnvelope"
            ),
            "inSR": "4326",
            "outSR": "4326",
            "spatialRel": (
                "esriSpatialRelIntersects"
            ),
            "outFields": OUT_FIELDS,
            "returnGeometry": "true",
            "f": "json",
        }

        async with httpx.AsyncClient(
            timeout=30.0
        ) as client:
            response = await client.get(
                BASE_URL,
                params=params,
                headers={
                    "Accept": (
                        "application/json"
                    )
                },
            )

        if not response.is_success:
            raise EEAWiseAPIError(
                "EEA WISE API "
                f"{response.status_code}: "
                f"{response.text}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise EEAWiseAPIError(
                "EEA WISE API returned "
                "invalid JSON"
            ) from exc

        if not isinstance(
            payload,
            dict,
        ):
            raise EEAWiseAPIError(
                "EEA WISE API returned "
                "an unexpected payload"
            )

        error = payload.get(
            "error"
        )

        if error is not None:
            raise EEAWiseAPIError(
                "EEA WISE ArcGIS query "
                f"error: {error}"
            )

        return payload
