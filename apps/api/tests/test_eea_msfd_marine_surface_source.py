from __future__ import annotations

import asyncio

from app.services.eea_msfd_marine_surface_source import (
    build_eea_msfd_route_marine_surface_evidence,
)


class _Client:
    async def query_marine_region_polygons(self, **kwargs):
        del kwargs
        return {
            "features": [
                {
                    "attributes": {
                        "OBJECTID": 7,
                        "subregion": "MAD",
                        "subregionName": "Adriatic Sea",
                        "region": "MED",
                        "regionName": "Mediterranean Sea",
                        "zoneType": "MSFD",
                        "spZoneType": "subregion",
                        "envDomain": "SEA",
                    },
                    "geometry": {
                        "rings": [
                            [
                                [15.0, 44.0],
                                [15.5, 44.0],
                                [15.5, 44.5],
                                [15.0, 44.5],
                                [15.0, 44.0],
                            ]
                        ]
                    },
                }
            ]
        }


def _environment_input():
    return {
        "provider": "POLAR",
        "schema_version": "0.1",
        "scope": {"domain": "ENVIRONMENTAL_ENRICHMENT_INPUT"},
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "segments": [
                    {
                        "order_index": 0,
                        "segment_index": 0,
                        "start_position": {
                            "latitude_deg": 44.2,
                            "longitude_deg": 15.2,
                        },
                        "end_position": {
                            "latitude_deg": 44.21,
                            "longitude_deg": 15.21,
                        },
                    }
                ],
            }
        ],
    }


def test_msfd_surface_evidence_preserves_provider_attributes() -> None:
    result = asyncio.run(
        build_eea_msfd_route_marine_surface_evidence(
            _environment_input(),
            client=_Client(),
        )
    )

    assert result["scope"]["domain"] == "ROUTE_MARINE_SURFACE_EVIDENCE"
    assert result["source_feature_count"] == 1
    feature = result["source_feature_catalog"][0]
    assert feature["source_attributes"]["subregionName"] == "Adriatic Sea"
    route = result["routes"][0]
    assert route["segments_with_surface_candidates"] == 1
    assert route["endpoint_containment_counts"]["INSIDE"] == 2


class _LocalFirstClient:
    def __init__(self) -> None:
        self.discovery_calls = 0
        self.download_calls = 0

    async def query_marine_region_object_ids(self, **kwargs):
        del kwargs
        self.discovery_calls += 1
        return ("7",)

    async def query_marine_region_features_by_object_ids(self, object_ids):
        assert tuple(object_ids) == ("7",)
        self.download_calls += 1
        return await _Client().query_marine_region_polygons()


def test_msfd_local_store_cold_then_warm_avoids_provider_calls(tmp_path) -> None:
    from app.services.eea_msfd_geometry_store import EEAMSFDGeometryStore

    store = EEAMSFDGeometryStore(
        tmp_path / "msfd.sqlite3",
        cell_size_deg=0.25,
    )
    client = _LocalFirstClient()

    cold = asyncio.run(
        build_eea_msfd_route_marine_surface_evidence(
            _environment_input(),
            client=client,
            geometry_store=store,
        )
    )
    cold_acquisition = cold["source_query"]["geometry_acquisition"]
    assert cold_acquisition["mode"] == "LOCAL_FIRST_STRUCTURAL_GEOMETRY_STORE"
    assert cold_acquisition["local_geometry_store_used"] is True
    assert cold_acquisition["provider_discovery_performed"] is True
    assert cold_acquisition["provider_geometry_download_performed"] is True
    assert cold["routes"][0]["segments_with_surface_candidates"] == 1
    assert client.discovery_calls >= 1
    assert client.download_calls == 1

    discovery_after_cold = client.discovery_calls
    warm = asyncio.run(
        build_eea_msfd_route_marine_surface_evidence(
            _environment_input(),
            client=client,
            geometry_store=store,
        )
    )
    warm_acquisition = warm["source_query"]["geometry_acquisition"]
    assert warm_acquisition["provider_discovery_performed"] is False
    assert warm_acquisition["provider_geometry_download_performed"] is False
    assert client.discovery_calls == discovery_after_cold
    assert client.download_calls == 1

    feature = warm["source_feature_catalog"][0]
    assert len(feature["source_snapshot_sha256"]) == 64
    assert feature["source_snapshot_fetched_at"] is not None
