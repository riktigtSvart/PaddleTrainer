from __future__ import annotations

import asyncio

from app.services.eu_hydro_water_surface_source import (
    build_eu_hydro_route_water_surface_evidence,
    expand_lon_lat_bounds_m,
    route_environment_position_bounds,
)
from app.services.route_water_surface_evidence import (
    WaterSurfacePolygon,
    build_route_water_surface_evidence_from_environment_input,
    build_route_water_surface_evidence_summary,
)


def _context() -> dict:
    return {
        "provider": "POLAR",
        "schema_version": "0.1",
        "scope": {
            "domain": "ENVIRONMENTAL_ENRICHMENT_INPUT"
        },
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "segments": [
                    {
                        "order_index": 0,
                        "segment_index": 0,
                        "segment_index_scope": "VIEW_LOCAL",
                        "source_segment_index": 46,
                        "source_segment_index_scope": (
                            "NORMALIZED_ROUTE_SOURCE"
                        ),
                        "source_segment_index_status": "AVAILABLE",
                        "source_waypoint_contiguous": True,
                        "start_waypoint_index": 46,
                        "end_waypoint_index": 47,
                        "start_exercise_elapsed_ms": 129763,
                        "end_exercise_elapsed_ms": 130763,
                        "start_position": {
                            "waypoint_index": 46,
                            "latitude_deg": 47.50005,
                            "longitude_deg": 19.05000,
                        },
                        "end_position": {
                            "waypoint_index": 47,
                            "latitude_deg": 47.50010,
                            "longitude_deg": 19.05005,
                        },
                    }
                ],
            }
        ],
    }


def _polygon() -> WaterSurfacePolygon:
    return WaterSurfacePolygon(
        source_provider="EEA_EU_HYDRO",
        source_dataset="EU_HYDRO_RIVER_NETWORK_DATABASE",
        source_layer="RIVER_NET_POLYGON",
        source_feature_id="RIVER_NET_POLYGON:danube-test",
        rings_lon_lat=(
            (
                (19.049, 47.5000),
                (19.051, 47.5000),
                (19.051, 47.5010),
                (19.049, 47.5010),
                (19.049, 47.5000),
            ),
        ),
        source_attributes={"OBJECT_ID": "danube-test"},
    )


def test_environment_adapter_preserves_route_and_segment_provenance() -> None:
    evidence = build_route_water_surface_evidence_from_environment_input(
        _context(),
        surface_polygons=[_polygon()],
        boundary_near_m=10.0,
        source_query={"query_performed": True},
    )

    route = evidence["routes"][0]
    segment = route["segments"][0]

    assert evidence["provider"] == "POLAR"
    assert evidence["schema_version"] == "0.1"
    assert evidence["scope"]["identifies_waterbody"] is False
    assert route["route_index"] == 0
    assert route["exercise_index"] == 0
    assert segment["order_index"] == 0
    assert segment["source_segment_index"] == 46
    assert segment["start_exercise_elapsed_ms"] == 129763
    assert segment["start_surface_evidence"]["containment"] == "INSIDE"
    assert segment["start_surface_evidence"]["relation"] == "BOUNDARY_NEAR"


def test_summary_excludes_heavy_segment_and_polygon_catalog_payloads() -> None:
    evidence = build_route_water_surface_evidence_from_environment_input(
        _context(),
        surface_polygons=[_polygon()],
        boundary_near_m=10.0,
    )

    summary = build_route_water_surface_evidence_summary(evidence)

    assert "source_feature_catalog" not in summary
    assert summary["source_feature_catalog_included"] is False
    assert summary["source_feature_catalog_count"] == 1
    assert summary["routes"][0]["segments_included"] is False
    assert summary["routes"][0]["segment_payload_count"] == 1
    assert "segments" not in summary["routes"][0]


def test_route_bounds_use_both_segment_endpoints() -> None:
    bounds = route_environment_position_bounds(_context())
    assert bounds == (
        19.05,
        47.50005,
        19.05005,
        47.50010,
    )


def test_query_bounds_padding_expands_all_sides() -> None:
    raw = (19.05, 47.5, 19.06, 47.51)
    expanded = expand_lon_lat_bounds_m(raw, padding_m=50.0)
    assert expanded[0] < raw[0]
    assert expanded[1] < raw[1]
    assert expanded[2] > raw[2]
    assert expanded[3] > raw[3]


class _EUHydroClient:
    def __init__(self) -> None:
        self.river_kwargs = None
        self.inland_kwargs = None

    async def query_river_surface_polygons(self, **kwargs):
        self.river_kwargs = kwargs
        return {
            "features": [
                {
                    "attributes": {"OBJECT_ID": "danube-test"},
                    "geometry": {
                        "rings": [
                            [
                                [19.049, 47.5000],
                                [19.051, 47.5000],
                                [19.051, 47.5010],
                                [19.049, 47.5010],
                                [19.049, 47.5000],
                            ]
                        ]
                    },
                }
            ]
        }

    async def query_inland_water_polygons(self, **kwargs):
        self.inland_kwargs = kwargs
        return {"features": []}


def test_eu_hydro_route_builder_queries_padded_bounds_and_returns_evidence() -> None:
    client = _EUHydroClient()
    evidence = asyncio.run(
        build_eu_hydro_route_water_surface_evidence(
            _context(),
            boundary_near_m=25.0,
            query_padding_m=10.0,
            client=client,
        )
    )

    assert client.river_kwargs is not None
    assert client.inland_kwargs is not None
    source_query = evidence["source_query"]
    assert source_query["query_performed"] is True
    # Padding must never be smaller than the boundary-near band.
    assert source_query["effective_query_padding_m"] == 25.0
    assert evidence["source_feature_count"] == 1
    segment = evidence["routes"][0]["segments"][0]
    assert segment["start_surface_evidence"]["relation"] == "BOUNDARY_NEAR"
