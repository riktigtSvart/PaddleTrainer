from __future__ import annotations

from asyncio import to_thread
from collections.abc import Mapping, Sequence
from math import cos, degrees, isfinite, radians
from typing import Any

from app.integrations.eea_msfd.client import EEAMSFDClient
from app.services.eea_msfd_geometry_store import EEAMSFDGeometryStore
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


async def acquire_eea_msfd_marine_surface_polygons(
    *,
    client: EEAMSFDClient,
    geometry_store: EEAMSFDGeometryStore | None = None,
    xmin_lon: float,
    ymin_lat: float,
    xmax_lon: float,
    ymax_lat: float,
) -> tuple[tuple[WaterSurfacePolygon, ...], dict[str, object]]:
    """Acquire EEA MSFD structural geometry local-first.

    Fixed-cell discovery records which provider OBJECTIDs intersect an area,
    including explicit zero-result cells. Raw ArcGIS features are compressed
    and versioned by SHA-256 before normalization, keeping structural provider
    snapshots separate from route/session evidence.
    """
    if not _supports_local_geometry_acquisition(client):
        payload = await client.query_marine_region_polygons(
            xmin_lon=xmin_lon,
            ymin_lat=ymin_lat,
            xmax_lon=xmax_lon,
            ymax_lat=ymax_lat,
        )
        polygons = await to_thread(_normalize_msfd_polygon_payload, payload)
        return polygons, {
            "mode": "LEGACY_DIRECT_PROVIDER_QUERY",
            "local_geometry_store_used": False,
            "provider_discovery_performed": True,
            "provider_geometry_download_performed": True,
            "layers": [],
        }

    resolved_store = geometry_store or await to_thread(EEAMSFDGeometryStore)
    cells = await to_thread(
        resolved_store.coverage_cells_for_bounds,
        xmin_lon=xmin_lon,
        ymin_lat=ymin_lat,
        xmax_lon=xmax_lon,
        ymax_lat=ymax_lat,
    )

    object_ids: set[str] = set()
    cached_cell_count = 0
    discovered_cell_count = 0
    for cell in cells:
        cached_ids = await to_thread(
            resolved_store.get_cell_object_ids,
            cell=cell,
        )
        if cached_ids is None:
            discovered_ids = await client.query_marine_region_object_ids(
                xmin_lon=cell.xmin_lon,
                ymin_lat=cell.ymin_lat,
                xmax_lon=cell.xmax_lon,
                ymax_lat=cell.ymax_lat,
            )
            await to_thread(
                resolved_store.put_cell_object_ids,
                cell=cell,
                object_ids=discovered_ids,
            )
            cached_ids = tuple(str(value) for value in discovered_ids)
            discovered_cell_count += 1
        else:
            cached_cell_count += 1
        object_ids.update(cached_ids)

    ordered_ids = tuple(sorted(object_ids, key=_object_id_sort_key))
    cached_features = await to_thread(
        resolved_store.get_features,
        object_ids=ordered_ids,
    )
    cached_feature_count_before_download = len(cached_features)
    missing_ids = tuple(
        object_id for object_id in ordered_ids if object_id not in cached_features
    )

    downloaded_features: list[Mapping[str, Any]] = []
    if missing_ids:
        payload = await client.query_marine_region_features_by_object_ids(
            missing_ids
        )
        raw_features = payload.get("features")
        if isinstance(raw_features, Sequence) and not isinstance(
            raw_features, (str, bytes)
        ):
            downloaded_features = [
                feature
                for feature in raw_features
                if isinstance(feature, Mapping)
            ]
        await to_thread(
            resolved_store.put_features,
            features=downloaded_features,
        )
        cached_features = await to_thread(
            resolved_store.get_features,
            object_ids=ordered_ids,
        )

    raw_payload = {
        "features": [
            cached_features[object_id].raw_feature
            for object_id in ordered_ids
            if object_id in cached_features
        ]
    }
    snapshot_metadata_by_object_id = {
        object_id: {
            "snapshot_sha256": record.snapshot_sha256,
            "fetched_at": record.fetched_at,
        }
        for object_id, record in cached_features.items()
    }
    polygons = await to_thread(
        _normalize_msfd_polygon_payload,
        raw_payload,
        snapshot_metadata_by_object_id=snapshot_metadata_by_object_id,
    )

    any_discovery = discovered_cell_count > 0
    any_download = bool(downloaded_features)
    return polygons, {
        "mode": "LOCAL_FIRST_STRUCTURAL_GEOMETRY_STORE",
        "local_geometry_store_used": True,
        "coverage_cell_size_deg": resolved_store.cell_size_deg,
        "coverage_cell_count": len(cells),
        "provider_discovery_performed": any_discovery,
        "provider_geometry_download_performed": any_download,
        "layers": [
            {
                "source_layer": SOURCE_LAYER,
                "coverage_cell_count": len(cells),
                "cached_coverage_cell_count": cached_cell_count,
                "provider_discovered_cell_count": discovered_cell_count,
                "object_id_count": len(ordered_ids),
                "cached_feature_count_before_download": (
                    cached_feature_count_before_download
                ),
                "missing_feature_count_before_download": len(missing_ids),
                "downloaded_feature_count": len(downloaded_features),
                "available_feature_count": len(cached_features),
                "normalized_polygon_count": len(polygons),
            }
        ],
    }


def _supports_local_geometry_acquisition(client: object) -> bool:
    return all(
        callable(getattr(client, name, None))
        for name in (
            "query_marine_region_object_ids",
            "query_marine_region_features_by_object_ids",
        )
    )


def _object_id_sort_key(value: str) -> tuple[int, int | str]:
    try:
        return (0, int(value))
    except ValueError:
        return (1, value)


async def build_eea_msfd_route_marine_surface_evidence(
    route_environment_context_input: Mapping[str, Any],
    *,
    boundary_near_m: float = DEFAULT_BOUNDARY_NEAR_M,
    query_padding_m: float = DEFAULT_QUERY_PADDING_M,
    client: EEAMSFDClient | None = None,
    geometry_store: EEAMSFDGeometryStore | None = None,
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
    polygons, acquisition = await acquire_eea_msfd_marine_surface_polygons(
        client=resolved_client,
        geometry_store=geometry_store,
        xmin_lon=expanded[0],
        ymin_lat=expanded[1],
        xmax_lon=expanded[2],
        ymax_lat=expanded[3],
    )

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
            "geometry_acquisition": acquisition,
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
    *,
    snapshot_metadata_by_object_id: Mapping[
        str, Mapping[str, str]
    ] | None = None,
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
        object_id_text = str(object_id)
        snapshot_metadata = (
            snapshot_metadata_by_object_id.get(object_id_text)
            if snapshot_metadata_by_object_id is not None
            else None
        )

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
                source_feature_id=object_id_text,
                rings_lon_lat=rings,
                source_attributes=attributes,
                source_snapshot_sha256=(
                    snapshot_metadata.get("snapshot_sha256")
                    if snapshot_metadata is not None
                    else None
                ),
                source_snapshot_fetched_at=(
                    snapshot_metadata.get("fetched_at")
                    if snapshot_metadata is not None
                    else None
                ),
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
