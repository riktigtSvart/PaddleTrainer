from app.services.route_water_environment_identity import (
    build_route_water_environment_identity,
    build_route_water_environment_identity_summary,
)


def _river_segment(
    order_index: int,
    *,
    status: str = "DIRECT_RESOLVED",
    waterbody_id: str | None = "HUAOC752",
    source_direct_waterbody_id: str | None = None,
    withheld: bool = False,
):
    identity = (
        {
            "source_provider": "EEA_WISE_WFD",
            "source_product": "WFD2022_SURFACE_WATER_BODY_CENTRELINE",
            "waterbody_id": waterbody_id,
            "waterbody_name": None,
            "waterbody_type": "RIVER",
        }
        if waterbody_id is not None
        else None
    )
    source_identity = (
        {
            "source_provider": "EEA_WISE_WFD",
            "source_product": "WFD2022_SURFACE_WATER_BODY_CENTRELINE",
            "waterbody_id": source_direct_waterbody_id,
            "waterbody_name": None,
            "waterbody_type": "RIVER",
        }
        if source_direct_waterbody_id is not None
        else identity
    )
    return {
        "order_index": order_index,
        "segment_index": order_index,
        "source_segment_index": order_index,
        "start_exercise_elapsed_ms": order_index * 1000,
        "end_exercise_elapsed_ms": (order_index + 1) * 1000,
        "resolution_status": status,
        "resolved_waterbody_identity": identity,
        "direct_resolved_waterbody_identity": source_identity,
        "direct_resolution_withheld_by_surface": withheld,
        "resolution_basis": ["TEST_RIVER_BASIS"],
    }


def _marine_segment(
    order_index: int,
    *,
    status: str = "DIRECT_RESOLVED",
    subregion_id: str | None = "MAD",
):
    identity = (
        {
            "source_provider": "EEA_MSFD",
            "source_dataset": "MSFD_REGIONS_AND_SUBREGIONS_V1_SEP_2022",
            "source_layer": "MSFD_REGIONS_AND_SUBREGIONS",
            "source_feature_id": "1",
            "marine_subregion_id": subregion_id,
            "marine_subregion_name": "Adriatic Sea",
            "marine_region_id": "MED",
            "marine_region_name": "Mediterranean Sea",
            "zone_type": "marineRegion",
            "spatial_zone_type": "MSFDsubregion",
            "environment_domain": "water",
        }
        if subregion_id is not None
        else None
    )
    return {
        "order_index": order_index,
        "segment_index": order_index,
        "source_segment_index": order_index,
        "start_exercise_elapsed_ms": order_index * 1000,
        "end_exercise_elapsed_ms": (order_index + 1) * 1000,
        "resolution_status": status,
        "resolved_marine_region_identity": identity,
    }


def _river_context(segments):
    return {
        "provider": "POLAR",
        "schema_version": "0.4",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "segments": segments,
            }
        ],
    }


def _marine_context(segments):
    return {
        "provider": "POLAR",
        "schema_version": "0.1",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "segments": segments,
            }
        ],
    }


def test_river_direct_becomes_river_inland_environment():
    result = build_route_water_environment_identity(
        _river_context([_river_segment(0)]),
        _marine_context([_marine_segment(0, status="UNRESOLVED", subregion_id=None)]),
    )

    assert result["status"] == "DIRECT_RESOLVED"
    assert result["river_inland_segment_count"] == 1
    assert result["marine_segment_count"] == 0
    segment = result["routes"][0]["segments"][0]
    assert segment["environment_type"] == "RIVER_INLAND"
    assert segment["resolved_river_inland_identity"]["waterbody_id"] == "HUAOC752"
    assert segment["resolved_marine_region_identity"] is None


def test_river_continuity_status_is_preserved():
    result = build_route_water_environment_identity(
        _river_context(
            [
                _river_segment(
                    0,
                    status="CONTINUITY_SUPPORTED",
                    waterbody_id="HUAOC752",
                )
            ]
        ),
        None,
    )

    assert result["status"] == "CONTINUITY_SUPPORTED"
    assert result["continuity_supported_segment_count"] == 1
    assert result["routes"][0]["segments"][0]["environment_type"] == "RIVER_INLAND"


def test_marine_direct_becomes_marine_environment():
    result = build_route_water_environment_identity(
        None,
        _marine_context([_marine_segment(0)]),
    )

    assert result["status"] == "DIRECT_RESOLVED"
    assert result["marine_segment_count"] == 1
    segment = result["routes"][0]["segments"][0]
    assert segment["environment_type"] == "MARINE"
    assert segment["resolved_marine_region_identity"]["marine_subregion_name"] == "Adriatic Sea"


def test_surface_withheld_river_source_evidence_does_not_compete_with_trusted_marine():
    river = _river_segment(
        0,
        status="UNRESOLVED",
        waterbody_id=None,
        source_direct_waterbody_id="HRJKR00046_000000",
        withheld=True,
    )
    result = build_route_water_environment_identity(
        _river_context([river]),
        _marine_context([_marine_segment(0)]),
    )

    segment = result["routes"][0]["segments"][0]
    assert segment["environment_type"] == "MARINE"
    assert segment["cross_domain_conflict"] is False
    assert segment["river_inland_evidence"]["direct_resolution_withheld_by_surface"] is True
    assert (
        segment["river_inland_evidence"]["source_direct_waterbody_identity"]["waterbody_id"]
        == "HRJKR00046_000000"
    )
    assert segment["resolved_river_inland_identity"] is None


def test_same_segment_resolved_in_both_domains_is_retained_as_ambiguous():
    result = build_route_water_environment_identity(
        _river_context([_river_segment(0)]),
        _marine_context([_marine_segment(0)]),
    )

    assert result["status"] == "AMBIGUOUS"
    assert result["cross_domain_conflict_segment_count"] == 1
    segment = result["routes"][0]["segments"][0]
    assert segment["environment_type"] == "AMBIGUOUS"
    assert segment["resolution_status"] == "AMBIGUOUS"
    assert segment["resolved_river_inland_identity"] is not None
    assert segment["resolved_marine_region_identity"] is not None
    assert "CROSS_DOMAIN_CONFLICT_RETAINED_AS_AMBIGUOUS" in segment["resolution_basis"]


def test_unresolved_in_both_domains_stays_unresolved():
    result = build_route_water_environment_identity(
        _river_context([_river_segment(0, status="UNRESOLVED", waterbody_id=None)]),
        _marine_context([_marine_segment(0, status="UNRESOLVED", subregion_id=None)]),
    )

    assert result["status"] == "UNRESOLVED"
    assert result["unresolved_environment_segment_count"] == 1
    assert result["routes"][0]["segments"][0]["environment_type"] == "UNRESOLVED"


def test_domain_ambiguity_without_trusted_identity_stays_ambiguous():
    result = build_route_water_environment_identity(
        _river_context([_river_segment(0, status="AMBIGUOUS", waterbody_id=None)]),
        None,
    )

    segment = result["routes"][0]["segments"][0]
    assert segment["environment_type"] == "AMBIGUOUS"
    assert segment["resolution_status"] == "AMBIGUOUS"


def test_segments_align_by_order_index_not_input_position():
    result = build_route_water_environment_identity(
        _river_context([_river_segment(1), _river_segment(0)]),
        _marine_context(
            [
                _marine_segment(0, status="UNRESOLVED", subregion_id=None),
                _marine_segment(1, status="UNRESOLVED", subregion_id=None),
            ]
        ),
    )

    segments = result["routes"][0]["segments"]
    assert [segment["order_index"] for segment in segments] == [0, 1]
    assert all(segment["environment_type"] == "RIVER_INLAND" for segment in segments)


def test_route_can_contain_separate_river_and_marine_segments_without_conflict():
    result = build_route_water_environment_identity(
        _river_context(
            [
                _river_segment(0),
                _river_segment(1, status="UNRESOLVED", waterbody_id=None),
            ]
        ),
        _marine_context(
            [
                _marine_segment(0, status="UNRESOLVED", subregion_id=None),
                _marine_segment(1),
            ]
        ),
    )

    route = result["routes"][0]
    assert route["mixed_environment_route"] is True
    assert route["environment_types"] == ["MARINE", "RIVER_INLAND"]
    assert route["cross_domain_conflict_segment_count"] == 0
    assert [s["environment_type"] for s in route["segments"]] == [
        "RIVER_INLAND",
        "MARINE",
    ]


def test_summary_omits_segment_payload_but_keeps_route_identity_catalogs():
    result = build_route_water_environment_identity(
        _river_context([_river_segment(0)]),
        None,
    )
    summary = build_route_water_environment_identity_summary(result)

    route = summary["routes"][0]
    assert "segments" not in route
    assert route["segments_included"] is False
    assert route["segment_payload_count"] == 1
    assert route["river_inland_identity_count"] == 1
    assert route["river_inland_identities"][0]["waterbody_id"] == "HUAOC752"


def test_scope_explicitly_declares_aggregator_semantics():
    result = build_route_water_environment_identity(None, _marine_context([_marine_segment(0)]))
    scope = result["scope"]

    assert scope["aggregates_existing_trusted_domain_resolutions"] is True
    assert scope["resolves_new_provider_evidence"] is False
    assert scope["retains_cross_domain_conflict_as_ambiguous"] is True
    assert scope["claims_hydrographic_sea_identity"] is False
