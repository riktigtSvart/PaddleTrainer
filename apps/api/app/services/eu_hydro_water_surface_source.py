from __future__ import annotations

from asyncio import to_thread
from collections.abc import Mapping, Sequence
from math import cos, degrees, isfinite, radians
from typing import Any

from app.integrations.eu_hydro.client import (
    EUHydroClient,
)
from app.services.eu_hydro_geometry_store import (
    EUHydroGeometryStore,
)
from app.services.route_water_surface_evidence import (
    WaterSurfacePolygon,
    build_route_water_surface_evidence_from_environment_input,
)


SOURCE_PROVIDER = "EEA_EU_HYDRO"
SOURCE_DATASET = (
    "EU_HYDRO_RIVER_NETWORK_DATABASE"
)
RIVER_SOURCE_LAYER = "RIVER_NET_POLYGON"
INLAND_WATER_SOURCE_LAYER = "INLAND_WATER"
EARTH_RADIUS_M = 6_371_008.8
DEFAULT_BOUNDARY_NEAR_M = 25.0
DEFAULT_QUERY_PADDING_M = 50.0


async def acquire_eu_hydro_water_surface_polygons(
    *,
    client: EUHydroClient,
    geometry_store: EUHydroGeometryStore | None = None,
    xmin_lon: float,
    ymin_lat: float,
    xmax_lon: float,
    ymax_lat: float,
    include_inland_water: bool = True,
) -> tuple[tuple[WaterSurfacePolygon, ...], dict[str, object]]:
    """Acquire EU-Hydro reference geometry local-first.

    Coverage discovery is cached by fixed spatial cells. Raw ArcGIS features
    are stored compressed before normalization/evaluation, so repeated routes
    on the same water reuse the exact provider snapshot without downloading
    the large geometry again.
    """
    if not _supports_local_geometry_acquisition(client):
        polygons = await query_eu_hydro_water_surface_polygons(
            client=client,
            xmin_lon=xmin_lon,
            ymin_lat=ymin_lat,
            xmax_lon=xmax_lon,
            ymax_lat=ymax_lat,
            include_inland_water=include_inland_water,
        )
        return polygons, {
            "mode": "LEGACY_DIRECT_PROVIDER_QUERY",
            "local_geometry_store_used": False,
            "provider_discovery_performed": True,
            "provider_geometry_download_performed": True,
            "layers": [],
        }

    resolved_store = geometry_store or await to_thread(EUHydroGeometryStore)

    layers: list[tuple[str, str, str]] = [
        (
            RIVER_SOURCE_LAYER,
            "query_river_surface_object_ids",
            "query_river_surface_features_by_object_ids",
        )
    ]
    if include_inland_water:
        layers.append(
            (
                INLAND_WATER_SOURCE_LAYER,
                "query_inland_water_object_ids",
                "query_inland_water_features_by_object_ids",
            )
        )

    all_polygons: list[WaterSurfacePolygon] = []
    layer_metadata: list[dict[str, object]] = []
    any_discovery = False
    any_download = False

    cells = await to_thread(
        resolved_store.coverage_cells_for_bounds,
        xmin_lon=xmin_lon,
        ymin_lat=ymin_lat,
        xmax_lon=xmax_lon,
        ymax_lat=ymax_lat,
    )

    for source_layer, discovery_name, feature_name in layers:
        discovery_method = getattr(client, discovery_name)
        feature_method = getattr(client, feature_name)
        object_ids: set[str] = set()
        cached_cell_count = 0
        discovered_cell_count = 0

        for cell in cells:
            cached_ids = await to_thread(
                resolved_store.get_cell_object_ids,
                source_layer=source_layer,
                cell=cell,
            )
            if cached_ids is None:
                discovered_ids = await discovery_method(
                    xmin_lon=cell.xmin_lon,
                    ymin_lat=cell.ymin_lat,
                    xmax_lon=cell.xmax_lon,
                    ymax_lat=cell.ymax_lat,
                )
                await to_thread(
                    resolved_store.put_cell_object_ids,
                    source_layer=source_layer,
                    cell=cell,
                    object_ids=discovered_ids,
                )
                cached_ids = tuple(str(value) for value in discovered_ids)
                discovered_cell_count += 1
                any_discovery = True
            else:
                cached_cell_count += 1
            object_ids.update(cached_ids)

        ordered_ids = tuple(sorted(object_ids, key=_object_id_sort_key))
        cached_features = await to_thread(
            resolved_store.get_features,
            source_layer=source_layer,
            object_ids=ordered_ids,
        )
        missing_ids = tuple(
            object_id
            for object_id in ordered_ids
            if object_id not in cached_features
        )

        downloaded_features: list[Mapping[str, Any]] = []
        if missing_ids:
            payload = await feature_method(missing_ids)
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
                source_layer=source_layer,
                features=downloaded_features,
            )
            any_download = True
            cached_features = await to_thread(
                resolved_store.get_features,
                source_layer=source_layer,
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
        normalized = await to_thread(
            normalize_eu_hydro_polygon_payload,
            payload=raw_payload,
            source_layer=source_layer,
            snapshot_metadata_by_object_id=snapshot_metadata_by_object_id,
        )
        all_polygons.extend(normalized)

        layer_metadata.append(
            {
                "source_layer": source_layer,
                "coverage_cell_count": len(cells),
                "cached_coverage_cell_count": cached_cell_count,
                "provider_discovered_cell_count": discovered_cell_count,
                "object_id_count": len(ordered_ids),
                "cached_feature_count_before_download": len(cached_features)
                if not missing_ids
                else len(ordered_ids) - len(missing_ids),
                "missing_feature_count_before_download": len(missing_ids),
                "downloaded_feature_count": len(downloaded_features),
                "available_feature_count": len(cached_features),
                "normalized_polygon_count": len(normalized),
            }
        )

    return tuple(all_polygons), {
        "mode": "LOCAL_FIRST_STRUCTURAL_GEOMETRY_STORE",
        "local_geometry_store_used": True,
        "coverage_cell_size_deg": resolved_store.cell_size_deg,
        "coverage_cell_count": len(cells),
        "provider_discovery_performed": any_discovery,
        "provider_geometry_download_performed": any_download,
        "layers": layer_metadata,
    }


def _supports_local_geometry_acquisition(client: object) -> bool:
    return all(
        callable(getattr(client, name, None))
        for name in (
            "query_river_surface_object_ids",
            "query_river_surface_features_by_object_ids",
            "query_inland_water_object_ids",
            "query_inland_water_features_by_object_ids",
        )
    )


def _object_id_sort_key(value: str) -> tuple[int, int | str]:
    try:
        return (0, int(value))
    except ValueError:
        return (1, value)


async def query_eu_hydro_water_surface_polygons(
    *,
    client: EUHydroClient,
    xmin_lon: float,
    ymin_lat: float,
    xmax_lon: float,
    ymax_lat: float,
    include_inland_water: bool = True,
) -> tuple[
    WaterSurfacePolygon,
    ...,
]:
    river_payload = (
        await client.query_river_surface_polygons(
            xmin_lon=xmin_lon,
            ymin_lat=ymin_lat,
            xmax_lon=xmax_lon,
            ymax_lat=ymax_lat,
        )
    )

    polygons = list(
        await to_thread(
            normalize_eu_hydro_polygon_payload,
            payload=river_payload,
            source_layer=(
                RIVER_SOURCE_LAYER
            ),
        )
    )

    if include_inland_water:
        inland_payload = (
            await client.query_inland_water_polygons(
                xmin_lon=xmin_lon,
                ymin_lat=ymin_lat,
                xmax_lon=xmax_lon,
                ymax_lat=ymax_lat,
            )
        )
        polygons.extend(
            await to_thread(
                normalize_eu_hydro_polygon_payload,
                payload=inland_payload,
                source_layer=(
                    INLAND_WATER_SOURCE_LAYER
                ),
            )
        )

    return tuple(
        polygons
    )


def normalize_eu_hydro_polygon_payload(
    *,
    payload: Mapping[str, Any],
    source_layer: str,
    snapshot_metadata_by_object_id: Mapping[str, Mapping[str, str]] | None = None,
) -> tuple[
    WaterSurfacePolygon,
    ...,
]:
    features = payload.get(
        "features"
    )

    if not isinstance(
        features,
        Sequence,
    ) or isinstance(
        features,
        (str, bytes),
    ):
        return ()

    polygons: list[
        WaterSurfacePolygon
    ] = []

    for feature in features:
        polygon = _normalize_feature(
            feature=feature,
            source_layer=source_layer,
            snapshot_metadata_by_object_id=snapshot_metadata_by_object_id,
        )

        if polygon is not None:
            polygons.append(
                polygon
            )

    return tuple(
        polygons
    )


def _normalize_feature(
    *,
    feature: object,
    source_layer: str,
    snapshot_metadata_by_object_id: Mapping[str, Mapping[str, str]] | None = None,
) -> WaterSurfacePolygon | None:
    if not isinstance(
        feature,
        Mapping,
    ):
        return None

    attributes = feature.get(
        "attributes"
    )
    geometry = feature.get(
        "geometry"
    )

    if not isinstance(
        attributes,
        Mapping,
    ):
        attributes = {}

    if not isinstance(
        geometry,
        Mapping,
    ):
        return None

    rings_raw = geometry.get(
        "rings"
    )

    rings = _normalize_rings(
        rings_raw
    )

    if not rings:
        return None

    raw_feature_id = (
        _first_non_empty(
            attributes,
            (
                "OBJECT_ID",
                "INSPIRE_ID",
                "OBJECTID",
                "WCOURSE_ID",
                "WSO_ID",
            ),
        )
    )

    if raw_feature_id is None:
        return None

    source_feature_id = (
        f"{source_layer}:"
        f"{raw_feature_id}"
    )

    object_id = attributes.get("OBJECTID")
    snapshot_metadata = (
        snapshot_metadata_by_object_id.get(str(object_id))
        if snapshot_metadata_by_object_id is not None and object_id is not None
        else None
    )

    return WaterSurfacePolygon(
        source_provider=SOURCE_PROVIDER,
        source_dataset=SOURCE_DATASET,
        source_layer=source_layer,
        source_feature_id=(
            source_feature_id
        ),
        rings_lon_lat=rings,
        source_attributes=dict(
            attributes
        ),
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


def _normalize_rings(
    rings_raw: object,
) -> tuple[
    tuple[
        tuple[float, float],
        ...,
    ],
    ...,
]:
    if not isinstance(
        rings_raw,
        Sequence,
    ) or isinstance(
        rings_raw,
        (str, bytes),
    ):
        return ()

    rings: list[
        tuple[
            tuple[float, float],
            ...,
        ]
    ] = []

    for ring_raw in rings_raw:
        if not isinstance(
            ring_raw,
            Sequence,
        ) or isinstance(
            ring_raw,
            (str, bytes),
        ):
            continue

        points: list[
            tuple[float, float]
        ] = []

        for point_raw in ring_raw:
            if not isinstance(
                point_raw,
                Sequence,
            ) or isinstance(
                point_raw,
                (str, bytes),
            ):
                continue

            if len(point_raw) < 2:
                continue

            try:
                longitude_deg = float(
                    point_raw[0]
                )
                latitude_deg = float(
                    point_raw[1]
                )
            except (
                TypeError,
                ValueError,
            ):
                continue

            points.append(
                (
                    longitude_deg,
                    latitude_deg,
                )
            )

        if len(points) >= 3:
            rings.append(
                tuple(
                    points
                )
            )

    return tuple(
        rings
    )


def _first_non_empty(
    attributes: Mapping[str, Any],
    keys: Sequence[str],
) -> str | None:
    for key in keys:
        value = attributes.get(
            key
        )

        if value is None:
            continue

        text = str(
            value
        ).strip()

        if text:
            return text

    return None


async def build_eu_hydro_route_water_surface_evidence(
    route_environment_context_input: Mapping[str, Any],
    *,
    boundary_near_m: float = DEFAULT_BOUNDARY_NEAR_M,
    query_padding_m: float = DEFAULT_QUERY_PADDING_M,
    include_inland_water: bool = True,
    client: EUHydroClient | None = None,
    geometry_store: EUHydroGeometryStore | None = None,
) -> dict[str, object]:
    """Fetch EU-Hydro polygons around the trusted route and evaluate endpoints.

    The result is geometric water-surface evidence only. It deliberately does
    not resolve WFD waterbody identity or perform trajectory continuity
    bridging. Those remain later interpretation layers.
    """
    if not isfinite(boundary_near_m) or boundary_near_m < 0.0:
        raise ValueError(
            "boundary_near_m must be a finite number >= 0"
        )
    if not isfinite(query_padding_m) or query_padding_m < 0.0:
        raise ValueError(
            "query_padding_m must be a finite number >= 0"
        )

    raw_bounds = route_environment_position_bounds(
        route_environment_context_input
    )

    if raw_bounds is None:
        return build_route_water_surface_evidence_from_environment_input(
            route_environment_context_input,
            surface_polygons=(),
            boundary_near_m=boundary_near_m,
            source_query={
                "source_provider": SOURCE_PROVIDER,
                "source_dataset": SOURCE_DATASET,
                "query_performed": False,
                "reason": "ROUTE_POSITION_BOUNDS_UNAVAILABLE",
                "include_inland_water": include_inland_water,
                "query_padding_m": float(query_padding_m),
            },
        )

    effective_padding_m = max(
        float(query_padding_m),
        float(boundary_near_m),
    )
    expanded = expand_lon_lat_bounds_m(
        raw_bounds,
        padding_m=effective_padding_m,
    )

    resolved_client = client or EUHydroClient()
    polygons, acquisition = await acquire_eu_hydro_water_surface_polygons(
        client=resolved_client,
        geometry_store=geometry_store,
        xmin_lon=expanded[0],
        ymin_lat=expanded[1],
        xmax_lon=expanded[2],
        ymax_lat=expanded[3],
        include_inland_water=include_inland_water,
    )

    return await to_thread(
        build_route_water_surface_evidence_from_environment_input,
        route_environment_context_input,
        surface_polygons=polygons,
        boundary_near_m=boundary_near_m,
        source_query={
            "source_provider": SOURCE_PROVIDER,
            "source_dataset": SOURCE_DATASET,
            "query_performed": True,
            "include_inland_water": include_inland_water,
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


def route_environment_position_bounds(
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
            for key in ("start_position", "end_position"):
                position = segment.get(key)
                if not isinstance(position, Mapping):
                    continue
                latitude = _finite_number(position.get("latitude_deg"))
                longitude = _finite_number(position.get("longitude_deg"))
                if latitude is None or longitude is None:
                    continue
                latitudes.append(latitude)
                longitudes.append(longitude)

    if not latitudes or not longitudes:
        return None

    return (
        min(longitudes),
        min(latitudes),
        max(longitudes),
        max(latitudes),
    )


def expand_lon_lat_bounds_m(
    bounds: tuple[float, float, float, float],
    *,
    padding_m: float,
) -> tuple[float, float, float, float]:
    if not isfinite(padding_m) or padding_m < 0.0:
        raise ValueError(
            "padding_m must be a finite number >= 0"
        )

    xmin_lon, ymin_lat, xmax_lon, ymax_lat = bounds
    center_lat = (ymin_lat + ymax_lat) / 2.0
    latitude_padding_deg = degrees(
        padding_m / EARTH_RADIUS_M
    )

    cosine = cos(radians(center_lat))
    if abs(cosine) < 1e-12:
        longitude_padding_deg = 180.0
    else:
        longitude_padding_deg = degrees(
            padding_m / (EARTH_RADIUS_M * abs(cosine))
        )

    return (
        max(-180.0, xmin_lon - longitude_padding_deg),
        max(-90.0, ymin_lat - latitude_padding_deg),
        min(180.0, xmax_lon + longitude_padding_deg),
        min(90.0, ymax_lat + latitude_padding_deg),
    )


def _finite_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    numeric = float(value)
    return numeric if isfinite(numeric) else None
