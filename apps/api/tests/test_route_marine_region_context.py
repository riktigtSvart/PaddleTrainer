from __future__ import annotations

from app.services.route_marine_region_context import (
    build_route_marine_region_context,
    build_route_marine_region_context_summary,
)


def _feature(feature_id: str, subregion: str, subregion_name: str):
    return {
        "source_provider": "EEA_MSFD",
        "source_dataset": "MSFD_REGIONS_AND_SUBREGIONS_V1_SEP_2022",
        "source_layer": "MSFD_REGIONS_AND_SUBREGIONS",
        "source_feature_id": feature_id,
        "source_attributes": {
            "subregion": subregion,
            "subregionName": subregion_name,
            "region": "MED",
            "regionName": "Mediterranean Sea",
            "zoneType": "MSFD",
            "spZoneType": "subregion",
            "envDomain": "SEA",
        },
    }


def _point(*ids: str):
    return {
        "containment": "INSIDE" if ids else "OUTSIDE",
        "relation": "INSIDE" if ids else "OUTSIDE",
        "containing_source_feature_ids": list(ids),
    }


def test_same_msfd_polygon_directly_resolves_adriatic_region() -> None:
    evidence = {
        "provider": "POLAR",
        "schema_version": "0.1",
        "source_query": {"source_provider": "EEA_MSFD"},
        "source_feature_catalog": [_feature("7", "MAD", "Adriatic Sea")],
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "segments": [
                    {
                        "order_index": 0,
                        "segment_index": 0,
                        "start_surface_evidence": _point("7"),
                        "end_surface_evidence": _point("7"),
                    }
                ],
            }
        ],
    }

    result = build_route_marine_region_context(evidence)
    assert result["status"] == "DIRECT_RESOLVED"
    assert result["direct_resolved_segment_count"] == 1
    identity = result["routes"][0]["segments"][0][
        "resolved_marine_region_identity"
    ]
    assert identity["marine_subregion_name"] == "Adriatic Sea"
    assert identity["marine_region_name"] == "Mediterranean Sea"
    assert result["scope"]["claims_hydrographic_sea_identity"] is False


def test_outside_segment_stays_unresolved() -> None:
    evidence = {
        "provider": "POLAR",
        "schema_version": "0.1",
        "source_feature_catalog": [_feature("7", "MAD", "Adriatic Sea")],
        "routes": [
            {
                "route_index": 0,
                "segments": [
                    {
                        "order_index": 0,
                        "start_surface_evidence": _point(),
                        "end_surface_evidence": _point(),
                    }
                ],
            }
        ],
    }
    result = build_route_marine_region_context(evidence)
    assert result["status"] == "UNRESOLVED"
    assert result["unresolved_segment_count"] == 1


def test_crossing_between_two_regions_is_transition_candidate() -> None:
    evidence = {
        "provider": "POLAR",
        "schema_version": "0.1",
        "source_feature_catalog": [
            _feature("7", "MAD", "Adriatic Sea"),
            _feature("8", "MIC", "Ionian Sea and the Central Mediterranean Sea"),
        ],
        "routes": [
            {
                "route_index": 0,
                "segments": [
                    {
                        "order_index": 0,
                        "start_surface_evidence": _point("7"),
                        "end_surface_evidence": _point("8"),
                    }
                ],
            }
        ],
    }
    result = build_route_marine_region_context(evidence)
    assert result["status"] == "TRANSITION_CANDIDATE"
    assert result["transition_candidate_segment_count"] == 1


def test_summary_removes_segment_and_catalog_payloads() -> None:
    evidence = {
        "provider": "POLAR",
        "schema_version": "0.1",
        "source_feature_catalog": [_feature("7", "MAD", "Adriatic Sea")],
        "routes": [
            {
                "route_index": 0,
                "segments": [
                    {
                        "order_index": 0,
                        "start_surface_evidence": _point("7"),
                        "end_surface_evidence": _point("7"),
                    }
                ],
            }
        ],
    }
    summary = build_route_marine_region_context_summary(
        build_route_marine_region_context(evidence)
    )
    assert summary["marine_region_catalog_included"] is False
    assert summary["marine_region_catalog_count"] == 1
    assert summary["routes"][0]["segments_included"] is False
    assert summary["routes"][0]["segment_payload_count"] == 1
    assert "segments" not in summary["routes"][0]
