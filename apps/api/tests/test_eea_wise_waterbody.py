from __future__ import annotations

import pytest

from app.services.eea_wise_waterbody import (
    build_eea_wise_candidate_evidence_from_features,
    build_eea_wise_waterbody_candidate_evidence,
    normalize_eea_wise_features,
)


def _context():
    return {
        "provider": "POLAR",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "segments": [
                    {
                        "order_index": 0,
                        "start_position": {
                            "latitude_deg": 47.50000,
                            "longitude_deg": 19.00000,
                        },
                        "end_position": {
                            "latitude_deg": 47.50010,
                            "longitude_deg": 19.00000,
                        },
                    },
                    {
                        "order_index": 1,
                        "start_position": {
                            "latitude_deg": 47.50010,
                            "longitude_deg": 19.00000,
                        },
                        "end_position": {
                            "latitude_deg": 47.50020,
                            "longitude_deg": 19.00000,
                        },
                    },
                ],
            }
        ],
    }


def _payload():
    return {
        "features": [
            {
                "attributes": {
                    "OBJECTID": 12,
                    "countryCode": "HU",
                    "thematicIdIdentifier": "HU_RW_001",
                    "hydroIdLocalId": "DUNA001",
                    "hydroIdNamespace": "HU.WISE",
                    "geographicalNameText": "Duna",
                    "geographicalNameLanguage": "hun",
                    "specialisedZoneType": "river water body",
                    "cYear": "2022",
                },
                "geometry": {
                    "paths": [
                        [
                            [19.00005, 47.49990],
                            [19.00005, 47.50030],
                        ]
                    ]
                },
            }
        ]
    }


def test_normalizes_wise_waterbody_without_claiming_river_reach():
    features = normalize_eea_wise_features(
        _payload()
    )

    assert len(features) == 1

    feature = features[0]

    assert feature["waterbody_id"] == "HU_RW_001"
    assert feature["source_feature_name"] == "Duna"
    assert feature["waterbody_name"] is None
    assert feature["waterbody_type"] == "RIVER"
    assert feature["river_reach_id"] is None
    assert feature["source_feature_id"] == "HU.WISE:DUNA001"


def test_builds_segment_candidates_with_measured_local_distance():
    features = normalize_eea_wise_features(
        _payload()
    )

    result = (
        build_eea_wise_candidate_evidence_from_features(
            _context(),
            normalized_features=features,
            search_radius_m=100.0,
        )
    )

    assert result["source_provider"] == "EEA_WISE_WFD"
    assert (
        result["river_reach_semantics"]
        == "NOT_PROVIDED_BY_WFD_WATERBODY_CENTRELINE"
    )

    segment_candidates = result["segment_candidates"]

    assert len(segment_candidates) == 2

    for item in segment_candidates:
        assert len(item["candidates"]) == 1
        candidate = item["candidates"][0]
        assert candidate["waterbody_id"] == "HU_RW_001"
        assert candidate["river_reach_id"] is None
        assert 0.0 < candidate["match_distance_m"] < 10.0


def test_far_feature_is_not_emitted_as_candidate():
    payload = _payload()

    payload["features"][0]["geometry"] = {
        "paths": [
            [
                [19.10000, 47.50000],
                [19.10000, 47.50030],
            ]
        ]
    }

    features = normalize_eea_wise_features(
        payload
    )

    result = (
        build_eea_wise_candidate_evidence_from_features(
            _context(),
            normalized_features=features,
            search_radius_m=100.0,
        )
    )

    assert all(
        item["candidates"] == []
        for item in result["segment_candidates"]
    )


@pytest.mark.asyncio
async def test_live_builder_queries_once_per_route_and_reuses_features():
    class FakeClient:
        def __init__(self):
            self.calls = []

        async def query_surface_waterbody_centrelines(
            self,
            **kwargs,
        ):
            self.calls.append(
                kwargs
            )
            return _payload()

    client = FakeClient()

    result = (
        await build_eea_wise_waterbody_candidate_evidence(
            _context(),
            client=client,
            search_radius_m=100.0,
        )
    )

    assert len(client.calls) == 1
    assert result["source_feature_count"] == 1
    assert len(result["segment_candidates"]) == 2


@pytest.mark.asyncio
async def test_invalid_search_radius_is_rejected_before_api_call():
    class FakeClient:
        async def query_surface_waterbody_centrelines(
            self,
            **kwargs,
        ):
            raise AssertionError(
                "API must not be called"
            )

    with pytest.raises(
        ValueError
    ):
        await build_eea_wise_waterbody_candidate_evidence(
            _context(),
            client=FakeClient(),
            search_radius_m=0.0,
        )


def test_same_wfd_waterbody_code_preserves_distinct_reported_features():
    payload = {
        "features": [
            {
                "attributes": {
                    "OBJECTID": 1207342,
                    "id": 2727463,
                    "countryCode": "HU",
                    "thematicIdIdentifier": "HUAOC752",
                    "thematicIdIdentifierScheme": "euSurfaceWaterBodyCode",
                    "hydroIdLocalId": "HUAAA626_32",
                    "hydroIdNamespace": "HU",
                    "geographicalNameText": "Duna",
                    "specialisedZoneType": "riverWaterBody",
                },
                "geometry": {
                    "paths": [
                        [
                            [19.05, 47.52],
                            [19.05, 47.53],
                        ]
                    ]
                },
            },
            {
                "attributes": {
                    "OBJECTID": 1207350,
                    "id": 2727471,
                    "countryCode": "HU",
                    "thematicIdIdentifier": "HUAOC752",
                    "thematicIdIdentifierScheme": "euSurfaceWaterBodyCode",
                    "hydroIdLocalId": "HUADX429_1",
                    "hydroIdNamespace": "HU",
                    "geographicalNameText": "Óbudai-mellékág",
                    "specialisedZoneType": "riverWaterBody",
                },
                "geometry": {
                    "paths": [
                        [
                            [19.06, 47.52],
                            [19.06, 47.53],
                        ]
                    ]
                },
            },
        ]
    }

    features = normalize_eea_wise_features(
        payload
    )

    assert len(features) == 2
    assert {
        item["waterbody_id"]
        for item in features
    } == {"HUAOC752"}
    assert {
        item["source_feature_id"]
        for item in features
    } == {
        "HU:HUAAA626_32",
        "HU:HUADX429_1",
    }
    assert {
        item["source_feature_name"]
        for item in features
    } == {
        "Duna",
        "Óbudai-mellékág",
    }
