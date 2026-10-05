from __future__ import annotations

import asyncio
import math
import time

import app.services.eu_hydro_water_surface_source as eu_hydro_source
import app.services.route_water_surface_evidence as surface


def _polygon(
    *,
    feature_id: str,
    points: tuple[tuple[float, float], ...],
) -> surface.WaterSurfacePolygon:
    return surface.WaterSurfacePolygon(
        source_provider="TEST",
        source_dataset="TEST",
        source_layer="TEST",
        source_feature_id=feature_id,
        rings_lon_lat=(points,),
    )


def _segment(
    index: int,
    *,
    start: tuple[float, float],
    end: tuple[float, float],
) -> surface.RouteSurfaceSegmentInput:
    return surface.RouteSurfaceSegmentInput(
        segment_index=index,
        source_segment_index=index + 46,
        start_latitude_deg=start[0],
        start_longitude_deg=start[1],
        end_latitude_deg=end[0],
        end_longitude_deg=end[1],
    )


def test_contiguous_route_reuses_shared_waypoint_evidence(
    monkeypatch,
) -> None:
    original = surface._build_point_evidence_prepared
    call_count = 0

    def counted(**kwargs):
        nonlocal call_count
        call_count += 1
        return original(**kwargs)

    monkeypatch.setattr(
        surface,
        "_build_point_evidence_prepared",
        counted,
    )

    rectangle = _polygon(
        feature_id="river",
        points=(
            (19.0, 47.0),
            (19.02, 47.0),
            (19.02, 47.02),
            (19.0, 47.02),
            (19.0, 47.0),
        ),
    )

    waypoints = [
        (47.005, 19.001 + index * 0.0001)
        for index in range(11)
    ]
    segments = [
        _segment(
            index,
            start=waypoints[index],
            end=waypoints[index + 1],
        )
        for index in range(10)
    ]

    result = surface.build_route_water_surface_evidence(
        segments=segments,
        surface_polygons=[rectangle],
        boundary_near_m=25.0,
    )

    assert len(result.segments) == 10
    assert call_count == 11


def test_polygon_bbox_prunes_far_complex_geometry(
    monkeypatch,
) -> None:
    original = surface._distance_point_to_segment_m
    distance_call_count = 0

    def counted(**kwargs):
        nonlocal distance_call_count
        distance_call_count += 1
        return original(**kwargs)

    monkeypatch.setattr(
        surface,
        "_distance_point_to_segment_m",
        counted,
    )

    near = _polygon(
        feature_id="near",
        points=(
            (19.0, 47.0),
            (19.01, 47.0),
            (19.01, 47.01),
            (19.0, 47.01),
            (19.0, 47.0),
        ),
    )

    far_points = tuple(
        (
            20.0 + 0.02 * math.cos(index * 2 * math.pi / 4096),
            48.0 + 0.02 * math.sin(index * 2 * math.pi / 4096),
        )
        for index in range(4096)
    )
    far = _polygon(
        feature_id="far-complex",
        points=far_points,
    )

    result = surface.build_route_water_surface_evidence(
        segments=[
            _segment(
                0,
                start=(47.005, 19.005),
                end=(47.005, 19.005),
            )
        ],
        surface_polygons=[near, far],
        boundary_near_m=25.0,
    )

    point = result.segments[0].start
    assert point.containing_source_feature_ids == ("near",)
    assert point.nearest_source_feature_id == "near"
    assert distance_call_count <= 10


def test_eu_hydro_cpu_evaluation_is_offloaded_from_event_loop(
    monkeypatch,
) -> None:
    async def fake_query(**kwargs):
        return ()

    def deliberately_slow_builder(*args, **kwargs):
        time.sleep(0.08)
        return {"ok": True}

    monkeypatch.setattr(
        eu_hydro_source,
        "query_eu_hydro_water_surface_polygons",
        fake_query,
    )
    monkeypatch.setattr(
        eu_hydro_source,
        "build_route_water_surface_evidence_from_environment_input",
        deliberately_slow_builder,
    )

    environment_input = {
        "routes": [
            {
                "segments": [
                    {
                        "start_position": {
                            "latitude_deg": 47.5,
                            "longitude_deg": 19.0,
                        },
                        "end_position": {
                            "latitude_deg": 47.5001,
                            "longitude_deg": 19.0001,
                        },
                    }
                ]
            }
        ]
    }

    async def scenario() -> None:
        task = asyncio.create_task(
            eu_hydro_source.build_eu_hydro_route_water_surface_evidence(
                environment_input,
                client=object(),
            )
        )
        await asyncio.sleep(0.01)
        assert not task.done()
        assert await task == {"ok": True}

    asyncio.run(scenario())


def test_spatial_tree_matches_legacy_exact_geometry() -> None:
    points = tuple(
        (
            19.05
            + (0.02 + 0.003 * math.sin(index * 0.37))
            * math.cos(index * 2 * math.pi / 720),
            47.535
            + (0.03 + 0.002 * math.cos(index * 0.19))
            * math.sin(index * 2 * math.pi / 720),
        )
        for index in range(720)
    )
    polygon = _polygon(
        feature_id="complex",
        points=points,
    )
    prepared = surface._prepare_polygon(
        polygon=polygon,
        original_index=0,
    )

    probes = (
        (19.05, 47.535),
        (19.051, 47.56),
        (19.07, 47.535),
        (19.03, 47.535),
        (19.05, 47.505),
        (19.081, 47.535),
    )

    for longitude_deg, latitude_deg in probes:
        assert surface._point_in_prepared_polygon(
            longitude_deg=longitude_deg,
            latitude_deg=latitude_deg,
            prepared=prepared,
        ) == surface._point_in_polygon(
            longitude_deg=longitude_deg,
            latitude_deg=latitude_deg,
            rings_lon_lat=polygon.rings_lon_lat,
        )

        indexed_distance = (
            surface._distance_to_prepared_polygon_boundary_m(
                longitude_deg=longitude_deg,
                latitude_deg=latitude_deg,
                prepared=prepared,
            )
        )
        legacy_distance = surface._distance_to_polygon_boundary_m(
            longitude_deg=longitude_deg,
            latitude_deg=latitude_deg,
            rings_lon_lat=polygon.rings_lon_lat,
        )
        assert indexed_distance == legacy_distance


def test_spatial_tree_prunes_large_polygon_chunk_search(
    monkeypatch,
) -> None:
    point_count = 65_536
    points = tuple(
        (
            19.05 + 0.03 * math.cos(index * 2 * math.pi / point_count),
            47.535 + 0.05 * math.sin(index * 2 * math.pi / point_count),
        )
        for index in range(point_count)
    )
    polygon = _polygon(
        feature_id="large",
        points=points,
    )
    prepared = surface._prepare_polygon(
        polygon=polygon,
        original_index=0,
    )

    original = surface._bbox_distance_m
    bbox_call_count = 0

    def counted(**kwargs):
        nonlocal bbox_call_count
        bbox_call_count += 1
        return original(**kwargs)

    monkeypatch.setattr(
        surface,
        "_bbox_distance_m",
        counted,
    )

    distance = surface._distance_to_prepared_polygon_boundary_m(
        longitude_deg=19.05,
        latitude_deg=47.535,
        prepared=prepared,
    )

    assert distance > 0.0
    # 65,536 edges create ~1,024 old 64-edge chunks.
    # The spatial tree should not need to rank every chunk.
    assert bbox_call_count < 300
