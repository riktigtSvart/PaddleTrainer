from __future__ import annotations

import asyncio

from app.services.eu_hydro_water_surface_source import (
    INLAND_WATER_SOURCE_LAYER,
    RIVER_SOURCE_LAYER,
    normalize_eu_hydro_polygon_payload,
    query_eu_hydro_water_surface_polygons,
)


def test_normalizes_arcgis_rings_and_provenance() -> None:
    payload = {
        "features": [
            {
                "attributes": {
                    "OBJECT_ID": "river-object-7",
                    "WCOURSE_ID": 42,
                },
                "geometry": {
                    "rings": [
                        [
                            [19.0, 47.0],
                            [19.01, 47.0],
                            [19.01, 47.01],
                            [19.0, 47.01],
                            [19.0, 47.0],
                        ]
                    ]
                },
            }
        ]
    }

    polygons = normalize_eu_hydro_polygon_payload(
        payload=payload,
        source_layer=RIVER_SOURCE_LAYER,
    )

    assert len(polygons) == 1
    polygon = polygons[0]

    assert polygon.source_provider == (
        "EEA_EU_HYDRO"
    )
    assert polygon.source_layer == (
        "RIVER_NET_POLYGON"
    )
    assert polygon.source_feature_id == (
        "RIVER_NET_POLYGON:river-object-7"
    )
    assert polygon.rings_lon_lat[0][0] == (
        19.0,
        47.0,
    )
    assert polygon.source_attributes is not None
    assert polygon.source_attributes[
        "WCOURSE_ID"
    ] == 42


def test_malformed_features_are_not_invented() -> None:
    payload = {
        "features": [
            {
                "attributes": {
                    "OBJECT_ID": "no-geometry"
                }
            },
            {
                "geometry": {
                    "rings": []
                },
                "attributes": {
                    "OBJECT_ID": "empty"
                },
            },
            {
                "geometry": {
                    "rings": [
                        [
                            [19.0, 47.0],
                            [19.01, 47.0],
                            [19.0, 47.01],
                        ]
                    ]
                },
                "attributes": {},
            },
        ]
    }

    polygons = normalize_eu_hydro_polygon_payload(
        payload=payload,
        source_layer=RIVER_SOURCE_LAYER,
    )

    assert polygons == ()


class _Client:
    async def query_river_surface_polygons(
        self,
        **kwargs,
    ):
        del kwargs
        return {
            "features": [
                {
                    "attributes": {
                        "OBJECTID": 1
                    },
                    "geometry": {
                        "rings": [
                            [
                                [19.0, 47.0],
                                [19.01, 47.0],
                                [19.0, 47.01],
                            ]
                        ]
                    },
                }
            ]
        }

    async def query_inland_water_polygons(
        self,
        **kwargs,
    ):
        del kwargs
        return {
            "features": [
                {
                    "attributes": {
                        "OBJECTID": 2
                    },
                    "geometry": {
                        "rings": [
                            [
                                [19.1, 47.1],
                                [19.11, 47.1],
                                [19.1, 47.11],
                            ]
                        ]
                    },
                }
            ]
        }


def test_combines_river_and_inland_water_sources() -> None:
    polygons = asyncio.run(
        query_eu_hydro_water_surface_polygons(
            client=_Client(),
            xmin_lon=19.0,
            ymin_lat=47.0,
            xmax_lon=19.2,
            ymax_lat=47.2,
        )
    )

    assert len(polygons) == 2
    assert polygons[0].source_layer == (
        RIVER_SOURCE_LAYER
    )
    assert polygons[1].source_layer == (
        INLAND_WATER_SOURCE_LAYER
    )


class _CachedClient:
    def __init__(self) -> None:
        self.discovery_calls = 0
        self.geometry_calls = 0

    async def query_river_surface_object_ids(self, **kwargs):
        del kwargs
        self.discovery_calls += 1
        return ("11",)

    async def query_inland_water_object_ids(self, **kwargs):
        del kwargs
        self.discovery_calls += 1
        return ()

    async def query_river_surface_features_by_object_ids(self, object_ids):
        self.geometry_calls += 1
        assert tuple(object_ids) == ("11",)
        return {
            "features": [
                {
                    "attributes": {
                        "OBJECTID": 11,
                        "OBJECT_ID": "danube-cached",
                    },
                    "geometry": {
                        "rings": [
                            [
                                [19.0, 47.0],
                                [19.1, 47.0],
                                [19.1, 47.1],
                                [19.0, 47.0],
                            ]
                        ]
                    },
                }
            ]
        }

    async def query_inland_water_features_by_object_ids(self, object_ids):
        self.geometry_calls += 1
        assert not object_ids
        return {"features": []}



def test_local_geometry_store_downloads_feature_only_once(tmp_path) -> None:
    from app.services.eu_hydro_geometry_store import EUHydroGeometryStore
    from app.services.eu_hydro_water_surface_source import (
        acquire_eu_hydro_water_surface_polygons,
    )

    store = EUHydroGeometryStore(
        tmp_path / "eu_hydro.sqlite3",
        cell_size_deg=0.05,
    )
    client = _CachedClient()

    first_polygons, first_meta = asyncio.run(
        acquire_eu_hydro_water_surface_polygons(
            client=client,
            geometry_store=store,
            xmin_lon=19.046,
            ymin_lat=47.519,
            xmax_lon=19.062,
            ymax_lat=47.554,
        )
    )
    first_discovery_calls = client.discovery_calls
    first_geometry_calls = client.geometry_calls

    second_polygons, second_meta = asyncio.run(
        acquire_eu_hydro_water_surface_polygons(
            client=client,
            geometry_store=store,
            xmin_lon=19.047,
            ymin_lat=47.520,
            xmax_lon=19.061,
            ymax_lat=47.553,
        )
    )

    assert len(first_polygons) == 1
    assert len(second_polygons) == 1
    assert first_meta["provider_geometry_download_performed"] is True
    assert second_meta["provider_geometry_download_performed"] is False
    assert second_meta["provider_discovery_performed"] is False
    assert client.discovery_calls == first_discovery_calls
    assert client.geometry_calls == first_geometry_calls == 1


def test_snapshot_metadata_is_attached_to_normalized_polygon() -> None:
    payload = {
        "features": [
            {
                "attributes": {"OBJECTID": 99, "OBJECT_ID": "raw-99"},
                "geometry": {
                    "rings": [
                        [
                            [19.0, 47.0],
                            [19.1, 47.0],
                            [19.0, 47.1],
                        ]
                    ]
                },
            }
        ]
    }
    polygons = normalize_eu_hydro_polygon_payload(
        payload=payload,
        source_layer=RIVER_SOURCE_LAYER,
        snapshot_metadata_by_object_id={
            "99": {
                "snapshot_sha256": "abc123",
                "fetched_at": "2026-10-05T10:00:00+00:00",
            }
        },
    )

    assert polygons[0].source_snapshot_sha256 == "abc123"
    assert polygons[0].source_snapshot_fetched_at == (
        "2026-10-05T10:00:00+00:00"
    )
