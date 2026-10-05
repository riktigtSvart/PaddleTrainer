from __future__ import annotations

from app.services.route_hydrology_source_resolution import (
    CANDIDATE_IDENTITY_CONFLICT,
    CANDIDATE_IDENTITY_MATCH,
    STATUS_AMBIGUOUS,
    STATUS_IDENTITY_SUPPORTED,
    STATUS_NOT_APPLICABLE,
    STATUS_UNRESOLVED,
    build_hydrology_source_candidates,
    build_route_hydrology_source_resolution,
)


def _river_identity(name: str = "Duna", waterbody_id: str = "HUAOC752"):
    return {
        "provider": "POLAR",
        "schema_version": "0.1",
        "available": True,
        "status": "CONTINUITY_SUPPORTED",
        "route_count": 1,
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "available": True,
                "status": "CONTINUITY_SUPPORTED",
                "segment_count": 2913,
                "environment_types": ["RIVER_INLAND"],
                "mixed_environment_route": False,
                "river_inland_segment_count": 2913,
                "marine_segment_count": 0,
                "ambiguous_environment_segment_count": 0,
                "unresolved_environment_segment_count": 0,
                "river_inland_identity_count": 1,
                "river_inland_identities": [
                    {
                        "source_provider": "EEA_WISE_WFD",
                        "source_product": "WFD2022_SURFACE_WATER_BODY_CENTRELINE",
                        "waterbody_id": waterbody_id,
                        "waterbody_type": "RIVER",
                        "source_feature_ids": ["HU:HUAAA626_31"],
                        "source_feature_names": [name],
                    }
                ],
                "marine_region_identity_count": 0,
                "marine_region_identities": [],
            }
        ],
    }


def _marine_identity():
    return {
        "provider": "POLAR",
        "schema_version": "0.1",
        "available": True,
        "status": "DIRECT_RESOLVED",
        "route_count": 1,
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "available": True,
                "status": "DIRECT_RESOLVED",
                "segment_count": 2986,
                "environment_types": ["MARINE"],
                "mixed_environment_route": False,
                "river_inland_segment_count": 0,
                "marine_segment_count": 2986,
                "ambiguous_environment_segment_count": 0,
                "unresolved_environment_segment_count": 0,
                "river_inland_identity_count": 0,
                "river_inland_identities": [],
                "marine_region_identity_count": 1,
                "marine_region_identities": [
                    {
                        "marine_subregion_id": "MAD",
                        "marine_subregion_name": "Adriatic Sea",
                    }
                ],
            }
        ],
    }


def _hydrology_source(
    *,
    station_registry_number: int = 1026,
    station_name: str = "Budapest",
    watercourse: str = "Duna",
):
    station = {
        "station_registry_number": station_registry_number,
        "station_name": station_name,
        "watercourse": watercourse,
        "municipality": "Budapest",
        "latitude_deg": 47.498,
        "longitude_deg": 19.046,
        "river_km": 1646.5,
    }
    return {
        "provider": "OVF_VRAQUERY",
        "product": "VRAQUERY_SURFACE_WATER",
        "source_type": "OBSERVED_HYDROLOGY",
        "measurements": [
            {
                "measurement_id": "wl-1",
                "metric_key": "WATER_LEVEL",
                "source_provider": "OVF_VRAQUERY",
                "source_product": "VRAQUERY_SURFACE_WATER",
                "source_type": "OBSERVED_HYDROLOGY",
                "station": station,
            },
            {
                "measurement_id": "q-1",
                "metric_key": "DISCHARGE",
                "source_provider": "OVF_VRAQUERY",
                "source_product": "VRAQUERY_SURFACE_WATER",
                "source_type": "OBSERVED_HYDROLOGY",
                "station": dict(station),
            },
        ],
    }


def test_extracts_unique_station_candidate_from_measurements():
    candidates = build_hydrology_source_candidates(_hydrology_source())
    assert len(candidates) == 1
    assert candidates[0]["station_registry_number"] == "1026"
    assert candidates[0]["station_name"] == "Budapest"
    assert candidates[0]["watercourse"] == "Duna"
    assert candidates[0]["river_km"] == 1646.5


def test_danube_budapest_station_is_identity_supported_not_direct_resolved():
    result = build_route_hydrology_source_resolution(
        _river_identity(),
        _hydrology_source(),
    )
    route = result["routes"][0]
    assert result["status"] == STATUS_IDENTITY_SUPPORTED
    assert route["status"] == STATUS_IDENTITY_SUPPORTED
    assert route["resolved_hydrology_source"]["station_registry_number"] == "1026"
    assert route["evaluated_candidates"][0]["identity_compatibility"] == (
        CANDIDATE_IDENTITY_MATCH
    )
    assert "NO_AUTHORITATIVE_WATERBODY_STATION_CROSSWALK_CLAIMED" in (
        route["resolution_basis"]
    )


def test_name_normalization_is_case_accent_and_punctuation_stable():
    result = build_route_hydrology_source_resolution(
        _river_identity(name="Sárvíz-Malomcsatorna"),
        _hydrology_source(watercourse="sárvíz malomcsatorna"),
    )
    assert result["routes"][0]["status"] == STATUS_IDENTITY_SUPPORTED


def test_szentendrei_duna_does_not_silently_accept_budapest_duna_station():
    result = build_route_hydrology_source_resolution(
        _river_identity(name="Szentendrei-Duna", waterbody_id="HUAOC756"),
        _hydrology_source(watercourse="Duna"),
    )
    route = result["routes"][0]
    assert route["status"] == STATUS_UNRESOLVED
    assert route["resolved_hydrology_source"] is None
    assert route["evaluated_candidates"][0]["identity_compatibility"] == (
        CANDIDATE_IDENTITY_CONFLICT
    )
    assert "NEAREST_STATION_NOT_ACCEPTED_AS_IDENTITY_PROOF" in (
        route["resolution_basis"]
    )


def test_marine_route_is_not_applicable_even_if_river_station_candidate_exists():
    result = build_route_hydrology_source_resolution(
        _marine_identity(),
        _hydrology_source(),
    )
    route = result["routes"][0]
    assert route["status"] == STATUS_NOT_APPLICABLE
    assert route["applicable"] is False
    assert route["resolved_hydrology_source"] is None


def test_missing_hydrology_candidate_keeps_river_route_unresolved():
    result = build_route_hydrology_source_resolution(
        _river_identity(),
        None,
    )
    route = result["routes"][0]
    assert route["status"] == STATUS_UNRESOLVED
    assert route["candidate_source_count"] == 0


def test_multiple_matching_stations_are_ambiguous_not_nearest_selected():
    source = _hydrology_source()
    second = dict(source["measurements"][0])
    second["measurement_id"] = "wl-2"
    second["station"] = {
        **source["measurements"][0]["station"],
        "station_registry_number": 9999,
        "station_name": "Other Danube gauge",
        "latitude_deg": 47.2,
    }
    source["measurements"].append(second)

    result = build_route_hydrology_source_resolution(_river_identity(), source)
    route = result["routes"][0]
    assert route["status"] == STATUS_AMBIGUOUS
    assert route["resolved_hydrology_source"] is None
    assert route["candidate_source_count"] == 2
    assert "NEAREST_STATION_NOT_USED_AS_TIE_BREAKER" in route["resolution_basis"]


def test_multiple_trusted_waterbodies_are_ambiguous_before_station_selection():
    identity = _river_identity()
    identity["routes"][0]["river_inland_identities"].append(
        {
            "source_provider": "EEA_WISE_WFD",
            "source_product": "WFD2022_SURFACE_WATER_BODY_CENTRELINE",
            "waterbody_id": "OTHER",
            "waterbody_type": "RIVER",
            "source_feature_names": ["Other river"],
        }
    )
    identity["routes"][0]["river_inland_identity_count"] = 2

    result = build_route_hydrology_source_resolution(
        identity,
        _hydrology_source(),
    )
    assert result["routes"][0]["status"] == STATUS_AMBIGUOUS


def test_scope_explicitly_prohibits_current_inference_and_nearest_identity():
    result = build_route_hydrology_source_resolution(
        _river_identity(),
        _hydrology_source(),
    )
    scope = result["scope"]
    assert scope["uses_nearest_station_as_identity_proof"] is False
    assert scope["estimates_local_current_velocity"] is False
    assert scope["infers_current_from_water_level"] is False
    assert scope["infers_current_from_discharge"] is False
    assert scope["controls_hydrology_context_inclusion"] is False
