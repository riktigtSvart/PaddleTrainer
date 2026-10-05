from __future__ import annotations

from app.services.route_waterbody_context import (
    STATUS_AMBIGUOUS,
    STATUS_RESOLVED,
    STATUS_UNRESOLVED,
    build_route_waterbody_candidate_evidence_summary,
    build_route_waterbody_context,
    build_route_waterbody_context_summary,
)


def _segment(
    order_index: int,
    *,
    position_available: bool = True,
):
    return {
        "order_index": order_index,
        "segment_index": order_index,
        "segment_index_scope": "VIEW_LOCAL",
        "source_segment_index": 46 + order_index,
        "source_segment_index_scope": "NORMALIZED_ROUTE_SOURCE",
        "source_segment_index_status": (
            "DIRECT_FROM_CONSECUTIVE_SOURCE_WAYPOINTS"
        ),
        "source_waypoint_contiguous": True,
        "start_waypoint_index": 46 + order_index,
        "end_waypoint_index": 47 + order_index,
        "start_exercise_elapsed_ms": 129763 + order_index * 1000,
        "end_exercise_elapsed_ms": 130763 + order_index * 1000,
        "start_position": {
            "latitude_deg": 47.52,
            "longitude_deg": 19.04,
        },
        "end_position": {
            "latitude_deg": 47.521,
            "longitude_deg": 19.041,
        },
        "position_status": (
            "ENDPOINT_POSITIONS_AVAILABLE"
            if position_available
            else "POSITION_ENDPOINT_UNAVAILABLE"
        ),
        "movement_bearing_deg": 25.0,
    }


def _context(
    *,
    segment_count: int = 2,
):
    return {
        "provider": "POLAR",
        "schema_version": "0.1",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "segments": [
                    _segment(index)
                    for index in range(
                        segment_count
                    )
                ],
            }
        ],
    }


def _candidate(
    feature_id: str,
    *,
    waterbody_id: str,
    name: str = "Duna",
    waterbody_type: str = "RIVER",
    reach_id: str | None = None,
    distance_m: float | None = 3.0,
):
    return {
        "source_feature_id": feature_id,
        "waterbody_id": waterbody_id,
        "waterbody_name": name,
        "waterbody_type": waterbody_type,
        "river_reach_id": reach_id,
        "geometry_relation": "ROUTE_SEGMENT_NEAR_FEATURE",
        "match_distance_m": distance_m,
    }


def test_no_candidate_source_remains_unresolved():
    result = build_route_waterbody_context(
        _context()
    )

    assert result["status"] == STATUS_UNRESOLVED
    assert result["resolved_segment_count"] == 0
    assert result["waterbody_count"] == 0

    route = result["routes"][0]

    assert route["status"] == STATUS_UNRESOLVED
    assert route["unresolved_segment_count"] == 2
    assert all(
        segment["match_status"]
        == "UNRESOLVED"
        for segment in route["segments"]
    )


def test_single_unique_candidate_resolves_segments():
    candidate_evidence = {
        "source_provider": "TEST_WATERBODY",
        "source_product": "TEST_FEATURES",
        "source_type": "VECTOR_WATERBODY_NETWORK",
        "segment_candidates": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "order_index": index,
                "candidates": [
                    _candidate(
                        "feature-1",
                        waterbody_id="waterbody-danube",
                        reach_id="reach-1646",
                    )
                ],
            }
            for index in range(2)
        ],
    }

    result = build_route_waterbody_context(
        _context(),
        waterbody_candidate_evidence=(
            candidate_evidence
        ),
    )

    assert result["status"] == STATUS_RESOLVED
    assert result["resolved_segment_count"] == 2
    assert result["waterbody_count"] == 1

    route = result["routes"][0]

    assert route["status"] == STATUS_RESOLVED
    assert route["waterbody_count"] == 1
    assert route["river_reach_count"] == 1
    assert all(
        segment["resolved_identity"]["waterbody_name"]
        == "Duna"
        for segment in route["segments"]
    )


def test_duplicate_same_candidate_is_not_ambiguous():
    candidate = _candidate(
        "feature-1",
        waterbody_id="waterbody-danube",
    )

    candidate_evidence = {
        "source_provider": "TEST_WATERBODY",
        "source_product": "TEST_FEATURES",
        "segment_candidates": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "order_index": 0,
                "candidates": [
                    candidate,
                    dict(candidate),
                ],
            }
        ],
    }

    result = build_route_waterbody_context(
        _context(
            segment_count=1
        ),
        waterbody_candidate_evidence=(
            candidate_evidence
        ),
    )

    segment = (
        result["routes"][0]["segments"][0]
    )

    assert segment["match_status"] == "RESOLVED"
    assert segment["candidate_count"] == 1


def test_multiple_distinct_candidates_remain_ambiguous_even_if_one_is_nearer():
    candidate_evidence = {
        "source_provider": "TEST_WATERBODY",
        "source_product": "TEST_FEATURES",
        "segment_candidates": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "order_index": 0,
                "candidates": [
                    _candidate(
                        "feature-near",
                        waterbody_id="river-a",
                        distance_m=1.0,
                    ),
                    _candidate(
                        "feature-far",
                        waterbody_id="river-b",
                        distance_m=30.0,
                    ),
                ],
            }
        ],
    }

    result = build_route_waterbody_context(
        _context(
            segment_count=1
        ),
        waterbody_candidate_evidence=(
            candidate_evidence
        ),
    )

    segment = (
        result["routes"][0]["segments"][0]
    )

    assert result["status"] == STATUS_AMBIGUOUS
    assert segment["match_status"] == "AMBIGUOUS"
    assert segment["resolved_identity"] is None
    assert segment["candidate_count"] == 2
    assert (
        result["scope"][
            "selects_nearest_candidate_when_ambiguous"
        ]
        is False
    )


def test_position_unavailable_is_not_silently_resolved():
    context = _context(
        segment_count=1
    )
    context["routes"][0]["segments"][0] = (
        _segment(
            0,
            position_available=False,
        )
    )

    candidate_evidence = {
        "source_provider": "TEST_WATERBODY",
        "source_product": "TEST_FEATURES",
        "segment_candidates": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "order_index": 0,
                "candidates": [
                    _candidate(
                        "feature-1",
                        waterbody_id="river-a",
                    )
                ],
            }
        ],
    }

    result = build_route_waterbody_context(
        context,
        waterbody_candidate_evidence=(
            candidate_evidence
        ),
    )

    segment = (
        result["routes"][0]["segments"][0]
    )

    assert (
        segment["match_status"]
        == "POSITION_UNAVAILABLE"
    )
    assert segment["resolved_identity"] is None


def test_multiple_resolved_reaches_are_preserved_not_collapsed():
    candidate_evidence = {
        "source_provider": "TEST_WATERBODY",
        "source_product": "TEST_FEATURES",
        "segment_candidates": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "order_index": 0,
                "candidates": [
                    _candidate(
                        "feature-1",
                        waterbody_id="waterbody-danube-a",
                        reach_id="reach-a",
                    )
                ],
            },
            {
                "route_index": 0,
                "exercise_index": 0,
                "order_index": 1,
                "candidates": [
                    _candidate(
                        "feature-2",
                        waterbody_id="waterbody-danube-b",
                        reach_id="reach-b",
                    )
                ],
            },
        ],
    }

    result = build_route_waterbody_context(
        _context(),
        waterbody_candidate_evidence=(
            candidate_evidence
        ),
    )

    route = result["routes"][0]

    assert route["status"] == STATUS_RESOLVED
    assert route["waterbody_count"] == 2
    assert route["river_reach_count"] == 2


def test_summary_removes_segment_payload_only():
    candidate_evidence = {
        "source_provider": "TEST_WATERBODY",
        "source_product": "TEST_FEATURES",
        "segment_candidates": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "order_index": 0,
                "candidates": [
                    _candidate(
                        "feature-1",
                        waterbody_id="waterbody-danube",
                    )
                ],
            }
        ],
    }

    result = build_route_waterbody_context(
        _context(
            segment_count=1
        ),
        waterbody_candidate_evidence=(
            candidate_evidence
        ),
    )

    summary = (
        build_route_waterbody_context_summary(
            result
        )
    )

    route = summary["routes"][0]

    assert "segments" not in route
    assert route["segments_included"] is False
    assert route["segment_payload_count"] == 1
    assert route["resolved_features_included"] is False
    assert route["resolved_feature_payload_count"] == 1
    assert summary["waterbody_count"] == 1


def test_same_waterbody_can_have_multiple_resolved_source_features():
    candidate_evidence = {
        "source_provider": "EEA_WISE_WFD",
        "source_product": "WFD2022_SURFACE_WATER_BODY_CENTRELINE",
        "segment_candidates": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "order_index": 0,
                "candidates": [
                    {
                        **_candidate(
                            "HU:HUAAA626_32",
                            waterbody_id="HUAOC752",
                        ),
                        "source_feature_name": "Duna",
                        "waterbody_name": None,
                    }
                ],
            },
            {
                "route_index": 0,
                "exercise_index": 0,
                "order_index": 1,
                "candidates": [
                    {
                        **_candidate(
                            "HU:HUADX429_1",
                            waterbody_id="HUAOC752",
                        ),
                        "source_feature_name": "Óbudai-mellékág",
                        "waterbody_name": None,
                    }
                ],
            },
        ],
    }

    result = build_route_waterbody_context(
        _context(),
        waterbody_candidate_evidence=candidate_evidence,
    )

    route = result["routes"][0]

    assert result["status"] == STATUS_RESOLVED
    assert route["source_feature_count"] == 2
    assert route["waterbody_count"] == 1
    assert result["source_feature_count"] == 2
    assert result["waterbody_count"] == 1

    waterbody = result["waterbody_catalog"][0]

    assert waterbody["waterbody_id"] == "HUAOC752"
    assert waterbody["source_feature_count"] == 2
    assert waterbody["source_feature_names"] == [
        "Duna",
        "Óbudai-mellékág",
    ]


def test_multiple_source_features_for_same_waterbody_resolve_waterbody_only():
    candidate_evidence = {
        "source_provider": "EEA_WISE_WFD",
        "source_product": "WFD2022_SURFACE_WATER_BODY_CENTRELINE",
        "segment_candidates": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "order_index": 0,
                "candidates": [
                    {
                        **_candidate(
                            "HU:HUAAA626_32",
                            waterbody_id="HUAOC752",
                            distance_m=15.0,
                        ),
                        "source_feature_name": "Duna",
                        "waterbody_name": None,
                    },
                    {
                        **_candidate(
                            "HU:HUADX429_1",
                            waterbody_id="HUAOC752",
                            distance_m=80.0,
                        ),
                        "source_feature_name": "Óbudai-mellékág",
                        "waterbody_name": None,
                    },
                ],
            }
        ],
    }

    result = build_route_waterbody_context(
        _context(
            segment_count=1
        ),
        waterbody_candidate_evidence=(
            candidate_evidence
        ),
    )

    segment = result["routes"][0]["segments"][0]

    assert result["status"] == STATUS_RESOLVED
    assert result["waterbody_resolved_segment_count"] == 1
    assert result["resolved_segment_count"] == 0
    assert result["waterbody_count"] == 1

    assert (
        segment["match_status"]
        == "WATERBODY_RESOLVED_FEATURE_AMBIGUOUS"
    )
    assert segment["waterbody_match_status"] == "RESOLVED"
    assert segment["source_feature_match_status"] == "AMBIGUOUS"
    assert segment["resolved_identity"] is None

    resolved_waterbody = segment["resolved_waterbody_identity"]

    assert resolved_waterbody["waterbody_id"] == "HUAOC752"
    assert resolved_waterbody["source_feature_ids"] == [
        "HU:HUAAA626_32",
        "HU:HUADX429_1",
    ]
    assert resolved_waterbody["source_feature_names"] == [
        "Duna",
        "Óbudai-mellékág",
    ]


def test_different_waterbody_candidates_remain_waterbody_ambiguous():
    candidate_evidence = {
        "source_provider": "EEA_WISE_WFD",
        "source_product": "WFD2022_SURFACE_WATER_BODY_CENTRELINE",
        "segment_candidates": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "order_index": 0,
                "candidates": [
                    {
                        **_candidate(
                            "HU:HUAAA626_32",
                            waterbody_id="HUAOC752",
                            distance_m=15.0,
                        ),
                        "source_feature_name": "Duna",
                    },
                    {
                        **_candidate(
                            "HU:HUAAA792_1",
                            waterbody_id="HUAOC845",
                            name="Rákos-patak",
                            distance_m=60.0,
                        ),
                        "source_feature_name": "Rákos-patak",
                    },
                ],
            }
        ],
    }

    result = build_route_waterbody_context(
        _context(
            segment_count=1
        ),
        waterbody_candidate_evidence=candidate_evidence,
    )

    segment = result["routes"][0]["segments"][0]

    assert result["status"] == STATUS_AMBIGUOUS
    assert result["waterbody_ambiguous_segment_count"] == 1
    assert segment["waterbody_match_status"] == "AMBIGUOUS"
    assert segment["resolved_waterbody_identity"] is None


def test_candidate_summary_reports_feature_distribution_without_segment_payload():
    candidate_evidence = {
        "schema_version": "0.2",
        "source_provider": "EEA_WISE_WFD",
        "source_product": "WFD2022_SURFACE_WATER_BODY_CENTRELINE",
        "source_type": "REPORTED_WFD_SURFACE_WATER_BODY_CENTRELINE",
        "spatial_match_method": "TEST",
        "search_radius_m": 300.0,
        "segment_candidates": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "order_index": 0,
                "candidates": [
                    {
                        **_candidate(
                            "HU:HUAAA626_32",
                            waterbody_id="HUAOC752",
                            distance_m=10.0,
                        ),
                        "source_feature_name": "Duna",
                    }
                ],
            },
            {
                "route_index": 0,
                "exercise_index": 0,
                "order_index": 1,
                "candidates": [
                    {
                        **_candidate(
                            "HU:HUAAA626_32",
                            waterbody_id="HUAOC752",
                            distance_m=12.0,
                        ),
                        "source_feature_name": "Duna",
                    },
                    {
                        **_candidate(
                            "HU:HUADX429_1",
                            waterbody_id="HUAOC752",
                            distance_m=90.0,
                        ),
                        "source_feature_name": "Óbudai-mellékág",
                    },
                ],
            },
        ],
    }

    summary = build_route_waterbody_candidate_evidence_summary(
        candidate_evidence
    )

    assert summary is not None
    assert summary["segment_candidate_record_count"] == 2
    assert summary["segments_with_candidates"] == 2
    assert summary["candidate_reference_count"] == 3
    assert summary["source_feature_count"] == 2
    assert summary["waterbody_count"] == 1
    assert summary["candidate_count_histogram"] == {
        "1": 1,
        "2": 1,
    }

    by_id = {
        item["source_feature_id"]: item
        for item in summary["source_features"]
    }

    assert (
        by_id["HU:HUAAA626_32"]["segment_candidate_count"]
        == 2
    )
    assert (
        by_id["HU:HUADX429_1"]["segment_candidate_count"]
        == 1
    )
