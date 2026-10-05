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
