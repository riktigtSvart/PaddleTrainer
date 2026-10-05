from __future__ import annotations

from asyncio import to_thread
from collections.abc import Mapping, Sequence
from math import cos, degrees, isfinite, radians
from typing import Any

from app.integrations.eea_msfd.client import EEAMSFDClient
from app.services.route_water_surface_evidence import (
    WaterSurfacePolygon,
    build_route_water_surface_evidence_from_environment_input,
)


SOURCE_PROVIDER = "EEA_MSFD"
SOURCE_DATASET = "MSFD_REGIONS_AND_SUBREGIONS_V1_SEP_2022"
SOURCE_LAYER = "MSFD_REGIONS_AND_SUBREGIONS"
DEFAULT_BOUNDARY_NEAR_M = 25.0
DEFAULT_QUERY_PADDING_M = 50.0
EARTH_RADIUS_M = 6_371_008.8


async def build_eea_msfd_route_marine_surface_evidence(
    route_environment_context_input: Mapping[str, Any],
    *,
    boundary_near_m: float = DEFAULT_BOUNDARY_NEAR_M,
    query_padding_m: float = DEFAULT_QUERY_PADDING_M,
    client: EEAMSFDClient | None = None,
) -> dict[str, object]:
    """Evaluate trusted route geometry against EEA MSFD marine polygons.

    This is structural marine-surface evidence. The MSFD attributes are kept
    as source provenance, but marine-region identity is resolved in the next
    layer rather than inside the geometric evaluator.
    """
    if not isfinite(boundary_near_m) or boundary_near_m < 0.0:
        raise ValueError("boundary_near_m must be a finite number >= 0")
    if not isfinite(query_padding_m) or query_padding_m < 0.0:
        raise ValueError("query_padding_m must be a finite number >= 0")

    raw_bounds = _route_environment_position_bounds(
        route_environment_context_input
    )
    if raw_bounds is None:
        evidence = build_route_water_surface_evidence_from_environment_input(
            route_environment_context_input,
            surface_polygons=(),
            boundary_near_m=boundary_near_m,
            source_query={
                "source_provider": SOURCE_PROVIDER,
                "source_dataset": SOURCE_DATASET,
                "source_layer": SOURCE_LAYER,
                "query_performed": False,
                "reason": "ROUTE_POSITION_BOUNDS_UNAVAILABLE",
                "query_padding_m": float(query_padding_m),
            },
        )
        return _as_marine_surface_evidence(evidence)

    effective_padding_m = max(float(query_padding_m), float(boundary_near_m))
    expanded = _expand_lon_lat_bounds_m(
        raw_bounds,
        padding_m=effective_padding_m,
    )

    resolved_client = client or EEAMSFDClient()
    payload = await resolved_client.query_marine_region_polygons(
        xmin_lon=expanded[0],
        ymin_lat=expanded[1],
        xmax_lon=expanded[2],
        ymax_lat=expanded[3],
    )
    polygons = await to_thread(_normalize_msfd_polygon_payload, payload)

    evidence = await to_thread(
        build_route_water_surface_evidence_from_environment_input,
        route_environment_context_input,
        surface_polygons=polygons,
        boundary_near_m=boundary_near_m,
        source_query={
            "source_provider": SOURCE_PROVIDER,
            "source_dataset": SOURCE_DATASET,
            "source_layer": SOURCE_LAYER,
            "query_performed": True,
            "boundary_near_m": float(boundary_near_m),
            "requested_query_padding_m": float(query_padding_m),
            "effective_query_padding_m": effective_padding_m,
            "raw_route_bounds_wgs84": {
                "xmin_lon": raw_bounds[0],
                "ymin_lat": raw_bounds[1],
                "xmax_lon": raw_bounds[2],
                "ymax_lat": raw_bounds[3],
            },
            "query_bounds_wgs84": {
                "xmin_lon": expanded[0],
                "ymin_lat": expanded[1],
                "xmax_lon": expanded[2],
                "ymax_lat": expanded[3],
            },
            "normalized_source_feature_count": len(polygons),
            "geometry_acquisition": {
                "mode": "DIRECT_EEA_ARCGIS_QUERY",
                "local_geometry_store_used": False,
            },
        },
    )
    return _as_marine_surface_evidence(evidence)


def _as_marine_surface_evidence(
    evidence: Mapping[str, object],
) -> dict[str, object]:
    result = dict(evidence)
    scope = dict(result.get("scope") or {})
    scope.update(
        {
            "domain": "ROUTE_MARINE_SURFACE_EVIDENCE",
            "marine_region_identity_resolved_here": False,
            "hydrographic_sea_identity_resolved_here": False,
            "coastline_truth_inferred": False,
        }
    )
    result["scope"] = scope
    return result


def _normalize_msfd_polygon_payload(
    payload: Mapping[str, Any],
) -> tuple[WaterSurfacePolygon, ...]:
    raw_features = payload.get("features")
    if not isinstance(raw_features, Sequence) or isinstance(
        raw_features, (str, bytes)
    ):
        return ()

    polygons: list[WaterSurfacePolygon] = []
    for raw_feature in raw_features:
        if not isinstance(raw_feature, Mapping):
            continue
        attributes_raw = raw_feature.get("attributes")
        geometry = raw_feature.get("geometry")
        if not isinstance(attributes_raw, Mapping) or not isinstance(
            geometry, Mapping
        ):
            continue

        rings = _normalize_rings(geometry.get("rings"))
        if not rings:
            continue

        object_id = attributes_raw.get("OBJECTID")
        if object_id is None:
            continue

        attributes = {
            key: attributes_raw.get(key)
            for key in (
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
            )
        }
        polygons.append(
            WaterSurfacePolygon(
                source_provider=SOURCE_PROVIDER,
                source_dataset=SOURCE_DATASET,
                source_layer=SOURCE_LAYER,
                source_feature_id=str(object_id),
                rings_lon_lat=rings,
                source_attributes=attributes,
            )
        )

    return tuple(polygons)


def _normalize_rings(
    rings_raw: object,
) -> tuple[tuple[tuple[float, float], ...], ...]:
    if not isinstance(rings_raw, Sequence) or isinstance(
        rings_raw, (str, bytes)
    ):
        return ()

    rings: list[tuple[tuple[float, float], ...]] = []
    for raw_ring in rings_raw:
        if not isinstance(raw_ring, Sequence) or isinstance(
            raw_ring, (str, bytes)
        ):
            continue
        points: list[tuple[float, float]] = []
        for raw_point in raw_ring:
            if not isinstance(raw_point, Sequence) or isinstance(
                raw_point, (str, bytes)
            ) or len(raw_point) < 2:
                continue
            try:
                lon = float(raw_point[0])
                lat = float(raw_point[1])
            except (TypeError, ValueError):
                continue
            if isfinite(lon) and isfinite(lat):
                points.append((lon, lat))
        if len(points) >= 3:
            rings.append(tuple(points))
    return tuple(rings)


def _route_environment_position_bounds(
    route_environment_context_input: Mapping[str, Any],
) -> tuple[float, float, float, float] | None:
    longitudes: list[float] = []
    latitudes: list[float] = []
    routes = route_environment_context_input.get("routes")
    if not isinstance(routes, Sequence) or isinstance(routes, (str, bytes)):
        return None

    for route in routes:
        if not isinstance(route, Mapping):
            continue
        segments = route.get("segments")
        if not isinstance(segments, Sequence) or isinstance(
            segments, (str, bytes)
        ):
            continue
        for segment in segments:
            if not isinstance(segment, Mapping):
                continue
            for position_key in ("start_position", "end_position"):
                position = segment.get(position_key)
                if not isinstance(position, Mapping):
                    continue
                lat = _finite_number(position.get("latitude_deg"))
                lon = _finite_number(position.get("longitude_deg"))
                if lat is None or lon is None:
                    continue
                latitudes.append(lat)
                longitudes.append(lon)

    if not latitudes or not longitudes:
        return None
    return (min(longitudes), min(latitudes), max(longitudes), max(latitudes))


def _expand_lon_lat_bounds_m(
    bounds: tuple[float, float, float, float],
    *,
    padding_m: float,
) -> tuple[float, float, float, float]:
    xmin_lon, ymin_lat, xmax_lon, ymax_lat = bounds
    center_lat = (ymin_lat + ymax_lat) / 2.0
    lat_padding = degrees(padding_m / EARTH_RADIUS_M)
    cosine = cos(radians(center_lat))
    lon_padding = (
        180.0
        if abs(cosine) < 1e-12
        else degrees(padding_m / (EARTH_RADIUS_M * abs(cosine)))
    )
    return (
        max(-180.0, xmin_lon - lon_padding),
        max(-90.0, ymin_lat - lat_padding),
        min(180.0, xmax_lon + lon_padding),
        min(90.0, ymax_lat + lat_padding),
    )


def _finite_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    numeric = float(value)
    return numeric if isfinite(numeric) else None
