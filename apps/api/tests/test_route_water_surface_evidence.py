from __future__ import annotations

from app.services.route_water_surface_evidence import (
    RouteSurfaceSegmentInput,
    WaterSurfaceContainment,
    WaterSurfacePolygon,
    WaterSurfaceRelation,
    build_route_water_surface_evidence,
)


def _rectangle(
    *,
    feature_id: str = "river-1",
    west: float = 19.0,
    south: float = 47.0,
    east: float = 19.01,
    north: float = 47.01,
) -> WaterSurfacePolygon:
    return WaterSurfacePolygon(
        source_provider="EU_HYDRO",
        source_dataset=(
            "EU_HYDRO_RIVER_NETWORK_DATABASE"
        ),
        source_layer="RIVER_NET_POLYGON",
        source_feature_id=feature_id,
        rings_lon_lat=(
            (
                (west, south),
                (east, south),
                (east, north),
                (west, north),
                (west, south),
            ),
        ),
    )


def _segment(
    *,
    start_lat: float | None,
    start_lon: float | None,
    end_lat: float | None = None,
    end_lon: float | None = None,
) -> RouteSurfaceSegmentInput:
    return RouteSurfaceSegmentInput(
        segment_index=7,
        source_segment_index=46,
        start_latitude_deg=start_lat,
        start_longitude_deg=start_lon,
        end_latitude_deg=(
            start_lat
            if end_lat is None
            else end_lat
        ),
        end_longitude_deg=(
            start_lon
            if end_lon is None
            else end_lon
        ),
        start_exercise_elapsed_ms=129_763,
        end_exercise_elapsed_ms=130_763,
    )


def test_inside_far_from_boundary_is_inside() -> None:
    result = build_route_water_surface_evidence(
        segments=[
            _segment(
                start_lat=47.005,
                start_lon=19.005,
            )
        ],
        surface_polygons=[
            _rectangle()
        ],
        boundary_near_m=25.0,
    )

    point = result.segments[0].start

    assert point.containment == (
        WaterSurfaceContainment.INSIDE
    )
    assert point.relation == (
        WaterSurfaceRelation.INSIDE
    )
    assert point.containing_source_feature_ids == (
        "river-1",
    )
    assert point.boundary_near_source_feature_ids == ()


def test_inside_near_bank_preserves_inside_side() -> None:
    # ~5.6 m north of the southern edge.
    result = build_route_water_surface_evidence(
        segments=[
            _segment(
                start_lat=47.00005,
                start_lon=19.005,
            )
        ],
        surface_polygons=[
            _rectangle()
        ],
        boundary_near_m=25.0,
    )

    point = result.segments[0].start

    assert point.containment == (
        WaterSurfaceContainment.INSIDE
    )
    assert point.relation == (
        WaterSurfaceRelation.BOUNDARY_NEAR
    )
    assert point.containing_source_feature_ids == (
        "river-1",
    )
    assert point.boundary_near_source_feature_ids == (
        "river-1",
    )


def test_outside_near_bank_is_boundary_near() -> None:
    # ~5.6 m south of the polygon edge.
    result = build_route_water_surface_evidence(
        segments=[
            _segment(
                start_lat=46.99995,
                start_lon=19.005,
            )
        ],
        surface_polygons=[
            _rectangle()
        ],
        boundary_near_m=25.0,
    )

    point = result.segments[0].start

    assert point.containment == (
        WaterSurfaceContainment.OUTSIDE
    )
    assert point.relation == (
        WaterSurfaceRelation.BOUNDARY_NEAR
    )
    assert point.containing_source_feature_ids == ()
    assert point.boundary_near_source_feature_ids == (
        "river-1",
    )
    assert point.candidate_source_feature_ids == (
        "river-1",
    )


def test_outside_far_from_surface_is_outside() -> None:
    result = build_route_water_surface_evidence(
        segments=[
            _segment(
                start_lat=46.99,
                start_lon=19.005,
            )
        ],
        surface_polygons=[
            _rectangle()
        ],
        boundary_near_m=25.0,
    )

    point = result.segments[0].start

    assert point.containment == (
        WaterSurfaceContainment.OUTSIDE
    )
    assert point.relation == (
        WaterSurfaceRelation.OUTSIDE
    )
    assert point.candidate_source_feature_ids == ()


def test_polygon_hole_uses_even_odd_containment() -> None:
    polygon = WaterSurfacePolygon(
        source_provider="TEST",
        source_dataset="TEST",
        source_layer="TEST",
        source_feature_id="with-hole",
        rings_lon_lat=(
            (
                (19.0, 47.0),
                (19.02, 47.0),
                (19.02, 47.02),
                (19.0, 47.02),
                (19.0, 47.0),
            ),
            (
                (19.008, 47.008),
                (19.012, 47.008),
                (19.012, 47.012),
                (19.008, 47.012),
                (19.008, 47.008),
            ),
        ),
    )

    result = build_route_water_surface_evidence(
        segments=[
            _segment(
                start_lat=47.01,
                start_lon=19.01,
            )
        ],
        surface_polygons=[
            polygon
        ],
        boundary_near_m=25.0,
    )

    point = result.segments[0].start

    assert point.containment == (
        WaterSurfaceContainment.OUTSIDE
    )


def test_overlapping_polygons_preserve_multiple_candidates() -> None:
    result = build_route_water_surface_evidence(
        segments=[
            _segment(
                start_lat=47.005,
                start_lon=19.005,
            )
        ],
        surface_polygons=[
            _rectangle(
                feature_id="a"
            ),
            _rectangle(
                feature_id="b",
                west=19.004,
                east=19.014,
            ),
        ],
        boundary_near_m=25.0,
    )

    point = result.segments[0].start

    assert point.containing_source_feature_ids == (
        "a",
        "b",
    )
    assert point.candidate_source_feature_ids == (
        "a",
        "b",
    )


def test_missing_position_is_unavailable() -> None:
    result = build_route_water_surface_evidence(
        segments=[
            _segment(
                start_lat=None,
                start_lon=None,
            )
        ],
        surface_polygons=[
            _rectangle()
        ],
        boundary_near_m=25.0,
    )

    point = result.segments[0].start

    assert point.containment == (
        WaterSurfaceContainment.UNAVAILABLE
    )
    assert point.relation == (
        WaterSurfaceRelation.UNAVAILABLE
    )
    assert point.evaluated_feature_count == 0


def test_segment_provenance_is_preserved() -> None:
    result = build_route_water_surface_evidence(
        segments=[
            _segment(
                start_lat=47.005,
                start_lon=19.005,
            )
        ],
        surface_polygons=[
            _rectangle()
        ],
        boundary_near_m=25.0,
    )

    segment = result.segments[0]

    assert result.schema_version == "0.1"
    assert segment.segment_index == 7
    assert segment.source_segment_index == 46
    assert segment.start_exercise_elapsed_ms == 129_763
    assert segment.end_exercise_elapsed_ms == 130_763
