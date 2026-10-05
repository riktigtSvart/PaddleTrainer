from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import cos, hypot, isfinite, radians
from typing import Iterable, Mapping, Sequence


SCHEMA_VERSION = "0.1"
EARTH_RADIUS_M = 6_371_008.8


class WaterSurfaceContainment(
    StrEnum
):
    INSIDE = "INSIDE"
    OUTSIDE = "OUTSIDE"
    UNAVAILABLE = "UNAVAILABLE"


class WaterSurfaceRelation(
    StrEnum
):
    INSIDE = "INSIDE"
    BOUNDARY_NEAR = "BOUNDARY_NEAR"
    OUTSIDE = "OUTSIDE"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(
    frozen=True,
    slots=True,
)
class RouteSurfaceSegmentInput:
    segment_index: int
    source_segment_index: int | None
    start_latitude_deg: float | None
    start_longitude_deg: float | None
    end_latitude_deg: float | None
    end_longitude_deg: float | None
    start_exercise_elapsed_ms: int | None = None
    end_exercise_elapsed_ms: int | None = None


@dataclass(
    frozen=True,
    slots=True,
)
class WaterSurfacePolygon:
    source_provider: str
    source_dataset: str
    source_layer: str
    source_feature_id: str
    rings_lon_lat: tuple[
        tuple[
            tuple[float, float],
            ...,
        ],
        ...,
    ]
    source_attributes: Mapping[
        str,
        object,
    ] | None = None
    source_snapshot_sha256: str | None = None
    source_snapshot_fetched_at: str | None = None


@dataclass(
    frozen=True,
    slots=True,
)
class WaterSurfacePointEvidence:
    latitude_deg: float | None
    longitude_deg: float | None
    containment: WaterSurfaceContainment
    relation: WaterSurfaceRelation
    nearest_boundary_distance_m: float | None
    nearest_source_feature_id: str | None
    containing_source_feature_ids: tuple[
        str,
        ...,
    ]
    boundary_near_source_feature_ids: tuple[
        str,
        ...,
    ]
    candidate_source_feature_ids: tuple[
        str,
        ...,
    ]
    evaluated_feature_count: int


@dataclass(
    frozen=True,
    slots=True,
)
class RouteWaterSurfaceSegmentEvidence:
    segment_index: int
    source_segment_index: int | None
    start_exercise_elapsed_ms: int | None
    end_exercise_elapsed_ms: int | None
    start: WaterSurfacePointEvidence
    end: WaterSurfacePointEvidence


@dataclass(
    frozen=True,
    slots=True,
)
class RouteWaterSurfaceEvidence:
    schema_version: str
    boundary_near_m: float
    source_feature_count: int
    segments: tuple[
        RouteWaterSurfaceSegmentEvidence,
        ...,
    ]


EDGE_CHUNK_SIZE = 64
SPATIAL_TREE_LEAF_CHUNKS = 8


@dataclass(
    frozen=True,
    slots=True,
)
class _PreparedEdgeChunk:
    xmin_lon: float
    ymin_lat: float
    xmax_lon: float
    ymax_lat: float
    edges: tuple[
        tuple[float, float, float, float],
        ...,
    ]


@dataclass(
    frozen=True,
    slots=True,
)
class _PreparedChunkSpatialNode:
    xmin_lon: float
    ymin_lat: float
    xmax_lon: float
    ymax_lat: float
    left: "_PreparedChunkSpatialNode | None"
    right: "_PreparedChunkSpatialNode | None"
    chunks: tuple[_PreparedEdgeChunk, ...]


@dataclass(
    frozen=True,
    slots=True,
)
class _PreparedRing:
    xmin_lon: float
    ymin_lat: float
    xmax_lon: float
    ymax_lat: float
    chunks: tuple[_PreparedEdgeChunk, ...]
    spatial_tree: _PreparedChunkSpatialNode | None


@dataclass(
    frozen=True,
    slots=True,
)
class _PreparedPolygon:
    polygon: WaterSurfacePolygon
    original_index: int
    xmin_lon: float | None
    ymin_lat: float | None
    xmax_lon: float | None
    ymax_lat: float | None
    rings: tuple[_PreparedRing, ...]
    chunks: tuple[_PreparedEdgeChunk, ...]
    spatial_tree: _PreparedChunkSpatialNode | None


def build_route_water_surface_evidence(
    *,
    segments: Iterable[
        RouteSurfaceSegmentInput
    ],
    surface_polygons: Sequence[
        WaterSurfacePolygon
    ],
    boundary_near_m: float,
) -> RouteWaterSurfaceEvidence:
    if boundary_near_m < 0.0:
        raise ValueError(
            "boundary_near_m must be >= 0"
        )

    polygons = tuple(surface_polygons)
    prepared_polygons = _prepare_polygons(
        polygons
    )
    point_cache: dict[
        tuple[float | None, float | None],
        WaterSurfacePointEvidence,
    ] = {}

    evidence_segments = tuple(
        _build_segment_evidence(
            segment=segment,
            polygons=polygons,
            prepared_polygons=(
                prepared_polygons
            ),
            point_cache=point_cache,
            boundary_near_m=(
                boundary_near_m
            ),
        )
        for segment in segments
    )

    return RouteWaterSurfaceEvidence(
        schema_version=SCHEMA_VERSION,
        boundary_near_m=boundary_near_m,
        source_feature_count=len(polygons),
        segments=evidence_segments,
    )


def _build_segment_evidence(
    *,
    segment: RouteSurfaceSegmentInput,
    polygons: Sequence[
        WaterSurfacePolygon
    ],
    boundary_near_m: float,
    prepared_polygons: Sequence[
        _PreparedPolygon
    ] | None = None,
    point_cache: dict[
        tuple[float | None, float | None],
        WaterSurfacePointEvidence,
    ] | None = None,
) -> RouteWaterSurfaceSegmentEvidence:
    resolved_prepared = (
        tuple(prepared_polygons)
        if prepared_polygons is not None
        else _prepare_polygons(polygons)
    )

    return RouteWaterSurfaceSegmentEvidence(
        segment_index=segment.segment_index,
        source_segment_index=(
            segment.source_segment_index
        ),
        start_exercise_elapsed_ms=(
            segment.start_exercise_elapsed_ms
        ),
        end_exercise_elapsed_ms=(
            segment.end_exercise_elapsed_ms
        ),
        start=_cached_point_evidence(
            latitude_deg=(
                segment.start_latitude_deg
            ),
            longitude_deg=(
                segment.start_longitude_deg
            ),
            prepared_polygons=(
                resolved_prepared
            ),
            polygon_count=len(polygons),
            boundary_near_m=(
                boundary_near_m
            ),
            point_cache=point_cache,
        ),
        end=_cached_point_evidence(
            latitude_deg=(
                segment.end_latitude_deg
            ),
            longitude_deg=(
                segment.end_longitude_deg
            ),
            prepared_polygons=(
                resolved_prepared
            ),
            polygon_count=len(polygons),
            boundary_near_m=(
                boundary_near_m
            ),
            point_cache=point_cache,
        ),
    )


def _cached_point_evidence(
    *,
    latitude_deg: float | None,
    longitude_deg: float | None,
    prepared_polygons: Sequence[
        _PreparedPolygon
    ],
    polygon_count: int,
    boundary_near_m: float,
    point_cache: dict[
        tuple[float | None, float | None],
        WaterSurfacePointEvidence,
    ] | None,
) -> WaterSurfacePointEvidence:
    key = (
        latitude_deg,
        longitude_deg,
    )

    if point_cache is not None:
        cached = point_cache.get(key)
        if cached is not None:
            return cached

    evidence = (
        _build_point_evidence_prepared(
            latitude_deg=latitude_deg,
            longitude_deg=longitude_deg,
            prepared_polygons=(
                prepared_polygons
            ),
            polygon_count=polygon_count,
            boundary_near_m=(
                boundary_near_m
            ),
        )
    )

    if point_cache is not None:
        point_cache[key] = evidence

    return evidence


def _build_point_evidence(
    *,
    latitude_deg: float | None,
    longitude_deg: float | None,
    polygons: Sequence[
        WaterSurfacePolygon
    ],
    boundary_near_m: float,
) -> WaterSurfacePointEvidence:
    polygons_tuple = tuple(polygons)
    return _build_point_evidence_prepared(
        latitude_deg=latitude_deg,
        longitude_deg=longitude_deg,
        prepared_polygons=(
            _prepare_polygons(
                polygons_tuple
            )
        ),
        polygon_count=len(polygons_tuple),
        boundary_near_m=boundary_near_m,
    )


def _build_point_evidence_prepared(
    *,
    latitude_deg: float | None,
    longitude_deg: float | None,
    prepared_polygons: Sequence[
        _PreparedPolygon
    ],
    polygon_count: int,
    boundary_near_m: float,
) -> WaterSurfacePointEvidence:
    if (
        latitude_deg is None
        or longitude_deg is None
        or not isfinite(latitude_deg)
        or not isfinite(longitude_deg)
    ):
        return WaterSurfacePointEvidence(
            latitude_deg=latitude_deg,
            longitude_deg=longitude_deg,
            containment=(
                WaterSurfaceContainment
                .UNAVAILABLE
            ),
            relation=(
                WaterSurfaceRelation
                .UNAVAILABLE
            ),
            nearest_boundary_distance_m=None,
            nearest_source_feature_id=None,
            containing_source_feature_ids=(),
            boundary_near_source_feature_ids=(),
            candidate_source_feature_ids=(),
            evaluated_feature_count=0,
        )

    ranked: list[
        tuple[float, int, _PreparedPolygon]
    ] = []

    for prepared in prepared_polygons:
        lower_bound_m = (
            _prepared_polygon_bbox_distance_m(
                longitude_deg=longitude_deg,
                latitude_deg=latitude_deg,
                prepared=prepared,
            )
        )
        ranked.append(
            (
                lower_bound_m,
                prepared.original_index,
                prepared,
            )
        )

    ranked.sort(
        key=lambda item: (
            item[0],
            item[1],
        )
    )

    containing_indexes: set[int] = set()
    boundary_near_indexes: set[int] = set()
    nearest_distance_m: float | None = None
    nearest_feature_id: str | None = None
    nearest_index: int | None = None

    for (
        bbox_distance_m,
        original_index,
        prepared,
    ) in ranked:
        if (
            nearest_distance_m is not None
            and bbox_distance_m
            > max(
                boundary_near_m,
                nearest_distance_m,
            )
        ):
            break

        inside = False
        if bbox_distance_m == 0.0:
            inside = (
                _point_in_prepared_polygon(
                    longitude_deg=(
                        longitude_deg
                    ),
                    latitude_deg=(
                        latitude_deg
                    ),
                    prepared=prepared,
                )
            )

        need_boundary_distance = (
            nearest_distance_m is None
            or bbox_distance_m
            <= nearest_distance_m
            or bbox_distance_m
            <= boundary_near_m
        )

        if need_boundary_distance:
            boundary_distance_m = (
                _distance_to_prepared_polygon_boundary_m(
                    longitude_deg=(
                        longitude_deg
                    ),
                    latitude_deg=(
                        latitude_deg
                    ),
                    prepared=prepared,
                )
            )
        else:
            boundary_distance_m = float("inf")

        if inside:
            containing_indexes.add(
                original_index
            )

        if (
            boundary_distance_m
            <= boundary_near_m
        ):
            boundary_near_indexes.add(
                original_index
            )

        if (
            nearest_distance_m is None
            or boundary_distance_m
            < nearest_distance_m
            or (
                boundary_distance_m
                == nearest_distance_m
                and (
                    nearest_index is None
                    or original_index
                    < nearest_index
                )
            )
        ):
            nearest_distance_m = (
                boundary_distance_m
            )
            nearest_feature_id = (
                prepared.polygon
                .source_feature_id
            )
            nearest_index = original_index

    containing = tuple(
        prepared.polygon.source_feature_id
        for prepared in prepared_polygons
        if prepared.original_index
        in containing_indexes
    )
    boundary_near = tuple(
        prepared.polygon.source_feature_id
        for prepared in prepared_polygons
        if prepared.original_index
        in boundary_near_indexes
    )
    candidates = _stable_unique(
        [
            *containing,
            *boundary_near,
        ]
    )

    containment = (
        WaterSurfaceContainment.INSIDE
        if containing
        else WaterSurfaceContainment.OUTSIDE
    )

    if boundary_near:
        relation = (
            WaterSurfaceRelation
            .BOUNDARY_NEAR
        )
    elif containing:
        relation = (
            WaterSurfaceRelation.INSIDE
        )
    else:
        relation = (
            WaterSurfaceRelation.OUTSIDE
        )

    return WaterSurfacePointEvidence(
        latitude_deg=latitude_deg,
        longitude_deg=longitude_deg,
        containment=containment,
        relation=relation,
        nearest_boundary_distance_m=(
            nearest_distance_m
        ),
        nearest_source_feature_id=(
            nearest_feature_id
        ),
        containing_source_feature_ids=(
            containing
        ),
        boundary_near_source_feature_ids=(
            boundary_near
        ),
        candidate_source_feature_ids=(
            candidates
        ),
        evaluated_feature_count=(
            polygon_count
        ),
    )


def _prepare_polygons(
    polygons: Sequence[
        WaterSurfacePolygon
    ],
) -> tuple[_PreparedPolygon, ...]:
    return tuple(
        _prepare_polygon(
            polygon=polygon,
            original_index=index,
        )
        for index, polygon in enumerate(
            polygons
        )
    )


def _prepare_polygon(
    *,
    polygon: WaterSurfacePolygon,
    original_index: int,
) -> _PreparedPolygon:
    prepared_rings: list[
        _PreparedRing
    ] = []
    polygon_chunks: list[
        _PreparedEdgeChunk
    ] = []
    all_longitudes: list[float] = []
    all_latitudes: list[float] = []

    for ring in polygon.rings_lon_lat:
        if len(ring) < 2:
            continue

        ring_longitudes = [
            point[0]
            for point in ring
        ]
        ring_latitudes = [
            point[1]
            for point in ring
        ]
        all_longitudes.extend(
            ring_longitudes
        )
        all_latitudes.extend(
            ring_latitudes
        )

        edges = tuple(
            (
                ring[index][0],
                ring[index][1],
                ring[
                    (index + 1)
                    % len(ring)
                ][0],
                ring[
                    (index + 1)
                    % len(ring)
                ][1],
            )
            for index in range(
                len(ring)
            )
        )

        chunks = tuple(
            _make_edge_chunk(
                edges[
                    offset:
                    offset + EDGE_CHUNK_SIZE
                ]
            )
            for offset in range(
                0,
                len(edges),
                EDGE_CHUNK_SIZE,
            )
        )
        polygon_chunks.extend(chunks)

        prepared_rings.append(
            _PreparedRing(
                xmin_lon=min(
                    ring_longitudes
                ),
                ymin_lat=min(
                    ring_latitudes
                ),
                xmax_lon=max(
                    ring_longitudes
                ),
                ymax_lat=max(
                    ring_latitudes
                ),
                chunks=chunks,
                spatial_tree=(
                    _build_chunk_spatial_tree(
                        chunks
                    )
                ),
            )
        )

    if not all_longitudes:
        return _PreparedPolygon(
            polygon=polygon,
            original_index=original_index,
            xmin_lon=None,
            ymin_lat=None,
            xmax_lon=None,
            ymax_lat=None,
            rings=(),
            chunks=(),
            spatial_tree=None,
        )

    return _PreparedPolygon(
        polygon=polygon,
        original_index=original_index,
        xmin_lon=min(all_longitudes),
        ymin_lat=min(all_latitudes),
        xmax_lon=max(all_longitudes),
        ymax_lat=max(all_latitudes),
        rings=tuple(prepared_rings),
        chunks=tuple(polygon_chunks),
        spatial_tree=(
            _build_chunk_spatial_tree(
                tuple(polygon_chunks)
            )
        ),
    )


def _make_edge_chunk(
    edges: Sequence[
        tuple[float, float, float, float]
    ],
) -> _PreparedEdgeChunk:
    longitudes = [
        coordinate
        for edge in edges
        for coordinate in (
            edge[0],
            edge[2],
        )
    ]
    latitudes = [
        coordinate
        for edge in edges
        for coordinate in (
            edge[1],
            edge[3],
        )
    ]

    return _PreparedEdgeChunk(
        xmin_lon=min(longitudes),
        ymin_lat=min(latitudes),
        xmax_lon=max(longitudes),
        ymax_lat=max(latitudes),
        edges=tuple(edges),
    )


def _build_chunk_spatial_tree(
    chunks: Sequence[_PreparedEdgeChunk],
) -> _PreparedChunkSpatialNode | None:
    if not chunks:
        return None

    chunks_tuple = tuple(chunks)
    xmin_lon = min(
        chunk.xmin_lon
        for chunk in chunks_tuple
    )
    ymin_lat = min(
        chunk.ymin_lat
        for chunk in chunks_tuple
    )
    xmax_lon = max(
        chunk.xmax_lon
        for chunk in chunks_tuple
    )
    ymax_lat = max(
        chunk.ymax_lat
        for chunk in chunks_tuple
    )

    if (
        len(chunks_tuple)
        <= SPATIAL_TREE_LEAF_CHUNKS
    ):
        return _PreparedChunkSpatialNode(
            xmin_lon=xmin_lon,
            ymin_lat=ymin_lat,
            xmax_lon=xmax_lon,
            ymax_lat=ymax_lat,
            left=None,
            right=None,
            chunks=chunks_tuple,
        )

    lon_span = xmax_lon - xmin_lon
    lat_span = ymax_lat - ymin_lat

    if lon_span >= lat_span:
        ordered = sorted(
            chunks_tuple,
            key=lambda chunk: (
                chunk.xmin_lon
                + chunk.xmax_lon,
                chunk.ymin_lat
                + chunk.ymax_lat,
            ),
        )
    else:
        ordered = sorted(
            chunks_tuple,
            key=lambda chunk: (
                chunk.ymin_lat
                + chunk.ymax_lat,
                chunk.xmin_lon
                + chunk.xmax_lon,
            ),
        )

    midpoint = len(ordered) // 2
    left = _build_chunk_spatial_tree(
        ordered[:midpoint]
    )
    right = _build_chunk_spatial_tree(
        ordered[midpoint:]
    )

    return _PreparedChunkSpatialNode(
        xmin_lon=xmin_lon,
        ymin_lat=ymin_lat,
        xmax_lon=xmax_lon,
        ymax_lat=ymax_lat,
        left=left,
        right=right,
        chunks=(),
    )


def _spatial_node_bbox_distance_m(
    *,
    longitude_deg: float,
    latitude_deg: float,
    node: _PreparedChunkSpatialNode,
) -> float:
    return _bbox_distance_m(
        longitude_deg=longitude_deg,
        latitude_deg=latitude_deg,
        xmin_lon=node.xmin_lon,
        ymin_lat=node.ymin_lat,
        xmax_lon=node.xmax_lon,
        ymax_lat=node.ymax_lat,
    )


def _prepared_polygon_bbox_distance_m(
    *,
    longitude_deg: float,
    latitude_deg: float,
    prepared: _PreparedPolygon,
) -> float:
    if (
        prepared.xmin_lon is None
        or prepared.ymin_lat is None
        or prepared.xmax_lon is None
        or prepared.ymax_lat is None
    ):
        return float("inf")

    return _bbox_distance_m(
        longitude_deg=longitude_deg,
        latitude_deg=latitude_deg,
        xmin_lon=prepared.xmin_lon,
        ymin_lat=prepared.ymin_lat,
        xmax_lon=prepared.xmax_lon,
        ymax_lat=prepared.ymax_lat,
    )


def _bbox_distance_m(
    *,
    longitude_deg: float,
    latitude_deg: float,
    xmin_lon: float,
    ymin_lat: float,
    xmax_lon: float,
    ymax_lat: float,
) -> float:
    if longitude_deg < xmin_lon:
        nearest_lon = xmin_lon
    elif longitude_deg > xmax_lon:
        nearest_lon = xmax_lon
    else:
        nearest_lon = longitude_deg

    if latitude_deg < ymin_lat:
        nearest_lat = ymin_lat
    elif latitude_deg > ymax_lat:
        nearest_lat = ymax_lat
    else:
        nearest_lat = latitude_deg

    x_m, y_m = _local_xy_m(
        longitude_deg=nearest_lon,
        latitude_deg=nearest_lat,
        origin_longitude_deg=(
            longitude_deg
        ),
        origin_latitude_deg=(
            latitude_deg
        ),
    )
    return hypot(x_m, y_m)


def _point_in_prepared_polygon(
    *,
    longitude_deg: float,
    latitude_deg: float,
    prepared: _PreparedPolygon,
) -> bool:
    inside = False

    for ring in prepared.rings:
        if not (
            ring.xmin_lon
            <= longitude_deg
            <= ring.xmax_lon
            and ring.ymin_lat
            <= latitude_deg
            <= ring.ymax_lat
        ):
            continue

        if _point_in_prepared_ring(
            longitude_deg=longitude_deg,
            latitude_deg=latitude_deg,
            ring=ring,
        ):
            inside = not inside

    return inside


def _point_in_prepared_ring(
    *,
    longitude_deg: float,
    latitude_deg: float,
    ring: _PreparedRing,
) -> bool:
    root = ring.spatial_tree
    if root is None:
        return False

    ring_inside = False
    stack = [root]

    while stack:
        node = stack.pop()
        if (
            latitude_deg < node.ymin_lat
            or latitude_deg > node.ymax_lat
            or node.xmax_lon
            <= longitude_deg
        ):
            continue

        if node.chunks:
            for chunk in node.chunks:
                if (
                    latitude_deg
                    < chunk.ymin_lat
                    or latitude_deg
                    > chunk.ymax_lat
                    or chunk.xmax_lon
                    <= longitude_deg
                ):
                    continue

                for (
                    start_lon,
                    start_lat,
                    end_lon,
                    end_lat,
                ) in chunk.edges:
                    crosses = (
                        (start_lat > latitude_deg)
                        != (end_lat > latitude_deg)
                    )
                    if not crosses:
                        continue

                    denominator = (
                        end_lat - start_lat
                    )
                    if denominator == 0.0:
                        continue

                    x_intersection = (
                        (end_lon - start_lon)
                        * (
                            latitude_deg
                            - start_lat
                        )
                        / denominator
                        + start_lon
                    )

                    if (
                        longitude_deg
                        < x_intersection
                    ):
                        ring_inside = (
                            not ring_inside
                        )
            continue

        if node.left is not None:
            stack.append(node.left)
        if node.right is not None:
            stack.append(node.right)

    return ring_inside


def _distance_to_prepared_polygon_boundary_m(
    *,
    longitude_deg: float,
    latitude_deg: float,
    prepared: _PreparedPolygon,
) -> float:
    root = prepared.spatial_tree
    if root is None:
        return float("inf")

    minimum_m = float("inf")
    stack: list[
        tuple[
            float,
            _PreparedChunkSpatialNode,
        ]
    ] = [
        (
            _spatial_node_bbox_distance_m(
                longitude_deg=longitude_deg,
                latitude_deg=latitude_deg,
                node=root,
            ),
            root,
        )
    ]

    while stack:
        lower_bound_m, node = stack.pop()
        if lower_bound_m > minimum_m:
            continue

        if node.chunks:
            ranked_leaf_chunks = []
            for chunk in node.chunks:
                chunk_lower_bound_m = (
                    _bbox_distance_m(
                        longitude_deg=(
                            longitude_deg
                        ),
                        latitude_deg=(
                            latitude_deg
                        ),
                        xmin_lon=(
                            chunk.xmin_lon
                        ),
                        ymin_lat=(
                            chunk.ymin_lat
                        ),
                        xmax_lon=(
                            chunk.xmax_lon
                        ),
                        ymax_lat=(
                            chunk.ymax_lat
                        ),
                    )
                )
                if (
                    chunk_lower_bound_m
                    <= minimum_m
                ):
                    ranked_leaf_chunks.append(
                        (
                            chunk_lower_bound_m,
                            chunk,
                        )
                    )

            ranked_leaf_chunks.sort(
                key=lambda item: item[0],
                reverse=True,
            )

            for (
                chunk_lower_bound_m,
                chunk,
            ) in reversed(
                ranked_leaf_chunks
            ):
                if (
                    chunk_lower_bound_m
                    > minimum_m
                ):
                    continue

                for (
                    start_lon,
                    start_lat,
                    end_lon,
                    end_lat,
                ) in chunk.edges:
                    distance_m = (
                        _distance_point_to_segment_m(
                            point_lon=(
                                longitude_deg
                            ),
                            point_lat=(
                                latitude_deg
                            ),
                            start_lon=start_lon,
                            start_lat=start_lat,
                            end_lon=end_lon,
                            end_lat=end_lat,
                        )
                    )
                    if distance_m < minimum_m:
                        minimum_m = distance_m
            continue

        child_candidates: list[
            tuple[
                float,
                _PreparedChunkSpatialNode,
            ]
        ] = []
        for child in (
            node.left,
            node.right,
        ):
            if child is None:
                continue
            child_lower_bound_m = (
                _spatial_node_bbox_distance_m(
                    longitude_deg=(
                        longitude_deg
                    ),
                    latitude_deg=(
                        latitude_deg
                    ),
                    node=child,
                )
            )
            if (
                child_lower_bound_m
                <= minimum_m
            ):
                child_candidates.append(
                    (
                        child_lower_bound_m,
                        child,
                    )
                )

        child_candidates.sort(
            key=lambda item: item[0],
            reverse=True,
        )
        stack.extend(child_candidates)

    return minimum_m


def _point_in_polygon(
    *,
    longitude_deg: float,
    latitude_deg: float,
    rings_lon_lat: Sequence[
        Sequence[
            tuple[float, float]
        ]
    ],
) -> bool:
    # ArcGIS polygons can contain multiple outer
    # rings and holes. Even/odd parity preserves
    # containment without depending on ring
    # orientation conventions.
    inside = False

    for ring in rings_lon_lat:
        if _point_in_ring(
            longitude_deg=longitude_deg,
            latitude_deg=latitude_deg,
            ring_lon_lat=ring,
        ):
            inside = not inside

    return inside


def _point_in_ring(
    *,
    longitude_deg: float,
    latitude_deg: float,
    ring_lon_lat: Sequence[
        tuple[float, float]
    ],
) -> bool:
    if len(ring_lon_lat) < 3:
        return False

    inside = False
    j = len(ring_lon_lat) - 1

    for i in range(
        len(ring_lon_lat)
    ):
        xi, yi = ring_lon_lat[i]
        xj, yj = ring_lon_lat[j]

        crosses = (
            (yi > latitude_deg)
            != (yj > latitude_deg)
        )

        if crosses:
            denominator = yj - yi

            if denominator != 0.0:
                x_intersection = (
                    (xj - xi)
                    * (
                        latitude_deg - yi
                    )
                    / denominator
                    + xi
                )

                if (
                    longitude_deg
                    < x_intersection
                ):
                    inside = not inside

        j = i

    return inside


def _distance_to_polygon_boundary_m(
    *,
    longitude_deg: float,
    latitude_deg: float,
    rings_lon_lat: Sequence[
        Sequence[
            tuple[float, float]
        ]
    ],
) -> float:
    minimum_m: float | None = None

    for ring in rings_lon_lat:
        if len(ring) < 2:
            continue

        for index in range(
            len(ring)
        ):
            start = ring[index]
            end = ring[
                (index + 1) % len(ring)
            ]

            distance_m = (
                _distance_point_to_segment_m(
                    point_lon=longitude_deg,
                    point_lat=latitude_deg,
                    start_lon=start[0],
                    start_lat=start[1],
                    end_lon=end[0],
                    end_lat=end[1],
                )
            )

            if (
                minimum_m is None
                or distance_m < minimum_m
            ):
                minimum_m = distance_m

    if minimum_m is None:
        return float("inf")

    return minimum_m


def _distance_point_to_segment_m(
    *,
    point_lon: float,
    point_lat: float,
    start_lon: float,
    start_lat: float,
    end_lon: float,
    end_lat: float,
) -> float:
    # Local equirectangular projection around the
    # evaluated point. This is intentionally a
    # geometric proximity calculation, not a
    # navigation or hydrology model.
    start_x, start_y = _local_xy_m(
        longitude_deg=start_lon,
        latitude_deg=start_lat,
        origin_longitude_deg=point_lon,
        origin_latitude_deg=point_lat,
    )
    end_x, end_y = _local_xy_m(
        longitude_deg=end_lon,
        latitude_deg=end_lat,
        origin_longitude_deg=point_lon,
        origin_latitude_deg=point_lat,
    )

    dx = end_x - start_x
    dy = end_y - start_y
    length_squared = dx * dx + dy * dy

    if length_squared == 0.0:
        return hypot(
            start_x,
            start_y,
        )

    t = -(
        start_x * dx
        + start_y * dy
    ) / length_squared
    t = max(
        0.0,
        min(
            1.0,
            t,
        ),
    )

    closest_x = start_x + t * dx
    closest_y = start_y + t * dy

    return hypot(
        closest_x,
        closest_y,
    )


def _local_xy_m(
    *,
    longitude_deg: float,
    latitude_deg: float,
    origin_longitude_deg: float,
    origin_latitude_deg: float,
) -> tuple[
    float,
    float,
]:
    latitude_rad = radians(
        origin_latitude_deg
    )
    delta_lon_rad = radians(
        longitude_deg
        - origin_longitude_deg
    )
    delta_lat_rad = radians(
        latitude_deg
        - origin_latitude_deg
    )

    x = (
        EARTH_RADIUS_M
        * delta_lon_rad
        * cos(latitude_rad)
    )
    y = (
        EARTH_RADIUS_M
        * delta_lat_rad
    )

    return x, y


def _stable_unique(
    values: Iterable[str],
) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            values
        )
    )


def build_route_water_surface_evidence_from_environment_input(
    route_environment_context_input: Mapping[str, object],
    *,
    surface_polygons: Sequence[WaterSurfacePolygon],
    boundary_near_m: float,
    source_query: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Evaluate trusted route endpoints against water-surface polygons.

    This is a provider-independent trajectory adapter. It preserves route /
    segment provenance from ``route_environment_context_input`` but does not
    resolve waterbody identity, bridge ambiguous regions, infer navigability,
    or mutate the trusted route.
    """
    if not isfinite(boundary_near_m) or boundary_near_m < 0.0:
        raise ValueError(
            "boundary_near_m must be a finite number >= 0"
        )

    polygons = tuple(surface_polygons)
    prepared_polygons = _prepare_polygons(polygons)
    point_cache: dict[
        tuple[float | None, float | None],
        WaterSurfacePointEvidence,
    ] = {}
    route_results: list[dict[str, object]] = []

    raw_routes = route_environment_context_input.get("routes")
    routes = (
        raw_routes
        if isinstance(raw_routes, Sequence)
        and not isinstance(raw_routes, (str, bytes))
        else []
    )

    for route_position, raw_route in enumerate(routes):
        if not isinstance(raw_route, Mapping):
            continue

        route_index = _integer_value(raw_route.get("route_index"))
        if route_index is None:
            route_index = route_position

        exercise_index = _integer_value(
            raw_route.get("exercise_index")
        )

        segment_results: list[dict[str, object]] = []
        relation_counts = {
            relation.value: 0
            for relation in WaterSurfaceRelation
        }
        containment_counts = {
            containment.value: 0
            for containment in WaterSurfaceContainment
        }
        relation_containment_counts = {
            relation.value: {
                containment.value: 0
                for containment in WaterSurfaceContainment
            }
            for relation in WaterSurfaceRelation
        }
        segments_with_candidates = 0

        raw_segments = raw_route.get("segments")
        segments = (
            raw_segments
            if isinstance(raw_segments, Sequence)
            and not isinstance(raw_segments, (str, bytes))
            else []
        )

        for order_position, raw_segment in enumerate(segments):
            if not isinstance(raw_segment, Mapping):
                continue

            order_index = _integer_value(
                raw_segment.get("order_index")
            )
            if order_index is None:
                order_index = order_position

            segment_index = _integer_value(
                raw_segment.get("segment_index")
            )
            if segment_index is None:
                segment_index = order_index

            start_latitude, start_longitude = _lat_lon_from_position(
                raw_segment.get("start_position")
            )
            end_latitude, end_longitude = _lat_lon_from_position(
                raw_segment.get("end_position")
            )

            core = _build_segment_evidence(
                segment=RouteSurfaceSegmentInput(
                    segment_index=segment_index,
                    source_segment_index=_integer_value(
                        raw_segment.get("source_segment_index")
                    ),
                    start_latitude_deg=start_latitude,
                    start_longitude_deg=start_longitude,
                    end_latitude_deg=end_latitude,
                    end_longitude_deg=end_longitude,
                    start_exercise_elapsed_ms=_integer_value(
                        raw_segment.get("start_exercise_elapsed_ms")
                    ),
                    end_exercise_elapsed_ms=_integer_value(
                        raw_segment.get("end_exercise_elapsed_ms")
                    ),
                ),
                polygons=polygons,
                prepared_polygons=prepared_polygons,
                point_cache=point_cache,
                boundary_near_m=boundary_near_m,
            )

            start = _point_evidence_to_dict(core.start)
            end = _point_evidence_to_dict(core.end)

            for point in (core.start, core.end):
                relation_counts[point.relation.value] += 1
                containment_counts[point.containment.value] += 1
                relation_containment_counts[
                    point.relation.value
                ][point.containment.value] += 1

            if (
                core.start.candidate_source_feature_ids
                or core.end.candidate_source_feature_ids
            ):
                segments_with_candidates += 1

            segment_results.append(
                {
                    "order_index": order_index,
                    "segment_index": segment_index,
                    "segment_index_scope": raw_segment.get(
                        "segment_index_scope"
                    ),
                    "source_segment_index": core.source_segment_index,
                    "source_segment_index_scope": raw_segment.get(
                        "source_segment_index_scope"
                    ),
                    "source_segment_index_status": raw_segment.get(
                        "source_segment_index_status"
                    ),
                    "source_waypoint_contiguous": (
                        raw_segment.get("source_waypoint_contiguous") is True
                    ),
                    "start_waypoint_index": _integer_value(
                        raw_segment.get("start_waypoint_index")
                    ),
                    "end_waypoint_index": _integer_value(
                        raw_segment.get("end_waypoint_index")
                    ),
                    "start_exercise_elapsed_ms": (
                        core.start_exercise_elapsed_ms
                    ),
                    "end_exercise_elapsed_ms": (
                        core.end_exercise_elapsed_ms
                    ),
                    "start_position": _copy_position(
                        raw_segment.get("start_position")
                    ),
                    "end_position": _copy_position(
                        raw_segment.get("end_position")
                    ),
                    "start_surface_evidence": start,
                    "end_surface_evidence": end,
                }
            )

        route_results.append(
            {
                "route_index": route_index,
                "exercise_index": exercise_index,
                "available": bool(segment_results),
                "segment_count": len(segment_results),
                "segments_with_surface_candidates": (
                    segments_with_candidates
                ),
                "segments_without_surface_candidates": (
                    len(segment_results) - segments_with_candidates
                ),
                "endpoint_relation_counts": relation_counts,
                "endpoint_containment_counts": containment_counts,
                "endpoint_relation_containment_counts": (
                    relation_containment_counts
                ),
                "segments": segment_results,
            }
        )

    feature_catalog = [
        {
            "source_provider": polygon.source_provider,
            "source_dataset": polygon.source_dataset,
            "source_layer": polygon.source_layer,
            "source_feature_id": polygon.source_feature_id,
            "source_attributes": (
                dict(polygon.source_attributes)
                if isinstance(polygon.source_attributes, Mapping)
                else {}
            ),
            "source_snapshot_sha256": polygon.source_snapshot_sha256,
            "source_snapshot_fetched_at": polygon.source_snapshot_fetched_at,
        }
        for polygon in polygons
    ]

    provider = route_environment_context_input.get("provider")

    return {
        "provider": provider,
        "schema_version": SCHEMA_VERSION,
        "available": bool(route_results),
        "boundary_near_m": float(boundary_near_m),
        "route_count": len(route_results),
        "source_feature_count": len(polygons),
        "source_feature_catalog": feature_catalog,
        "source_query": (
            dict(source_query)
            if isinstance(source_query, Mapping)
            else None
        ),
        "input_provenance": {
            "route_environment_context_schema_version": (
                route_environment_context_input.get("schema_version")
            ),
            "route_environment_context_scope": (
                route_environment_context_input.get("scope")
            ),
        },
        "scope": {
            "domain": "ROUTE_WATER_SURFACE_EVIDENCE",
            "evaluates_surface_geometry": True,
            "identifies_waterbody": False,
            "resolves_trajectory_continuity": False,
            "infers_navigability": False,
            "estimates_local_current_velocity": False,
            "interpolates_position": False,
            "raw_data_mutated": False,
        },
        "routes": route_results,
    }


def build_route_water_surface_evidence_summary(
    evidence: Mapping[str, object],
) -> dict[str, object]:
    raw_routes = evidence.get("routes")
    routes = (
        raw_routes
        if isinstance(raw_routes, Sequence)
        and not isinstance(raw_routes, (str, bytes))
        else []
    )

    summary_routes: list[dict[str, object]] = []
    for raw_route in routes:
        if not isinstance(raw_route, Mapping):
            continue

        summary_routes.append(
            {
                **{
                    key: value
                    for key, value in raw_route.items()
                    if key != "segments"
                },
                "segments_included": False,
                "segment_payload_count": len(
                    raw_route.get("segments") or []
                ),
            }
        )

    source_catalog = evidence.get("source_feature_catalog")
    source_catalog_count = (
        len(source_catalog)
        if isinstance(source_catalog, Sequence)
        and not isinstance(source_catalog, (str, bytes))
        else 0
    )

    return {
        **{
            key: value
            for key, value in evidence.items()
            if key not in {"routes", "source_feature_catalog"}
        },
        "source_feature_catalog_included": False,
        "source_feature_catalog_count": source_catalog_count,
        "routes": summary_routes,
    }


def _integer_value(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and isfinite(value) and value.is_integer():
        return int(value)
    return None


def _finite_value(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    numeric = float(value)
    return numeric if isfinite(numeric) else None


def _lat_lon_from_position(
    position: object,
) -> tuple[float | None, float | None]:
    if not isinstance(position, Mapping):
        return None, None
    return (
        _finite_value(position.get("latitude_deg")),
        _finite_value(position.get("longitude_deg")),
    )


def _copy_position(position: object) -> dict[str, object] | None:
    if not isinstance(position, Mapping):
        return None
    return dict(position)


def _point_evidence_to_dict(
    point: WaterSurfacePointEvidence,
) -> dict[str, object]:
    return {
        "latitude_deg": point.latitude_deg,
        "longitude_deg": point.longitude_deg,
        "containment": point.containment.value,
        "relation": point.relation.value,
        "nearest_boundary_distance_m": (
            point.nearest_boundary_distance_m
        ),
        "nearest_source_feature_id": (
            point.nearest_source_feature_id
        ),
        "containing_source_feature_ids": list(
            point.containing_source_feature_ids
        ),
        "boundary_near_source_feature_ids": list(
            point.boundary_near_source_feature_ids
        ),
        "candidate_source_feature_ids": list(
            point.candidate_source_feature_ids
        ),
        "evaluated_feature_count": point.evaluated_feature_count,
    }
