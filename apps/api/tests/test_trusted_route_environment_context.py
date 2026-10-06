from __future__ import annotations

from copy import deepcopy

from app.services.trusted_route_environment_context import (
    STATUS_NOT_APPLICABLE,
    STATUS_TRUSTED,
    STATUS_TRUSTED_WITH_LIMITATIONS,
    STATUS_UNAVAILABLE,
    STATUS_WITHHELD,
    build_trusted_route_environment_context,
    build_trusted_route_environment_context_summary,
)


def _route_input(n=3):
    return {
        "schema_version": "0.1",
        "routes": [{
            "route_index": 0,
            "exercise_index": 0,
            "segments": [
                {"order_index": i, "segment_index": i, "midpoint_timestamp": f"2026-09-30T10:00:0{i}+00:00"}
                for i in range(n)
            ],
        }],
    }


def _water(n=3, environment_type="RIVER_INLAND", resolution_status="DIRECT_RESOLVED"):
    return {
        "schema_version": "0.1",
        "routes": [{
            "route_index": 0,
            "exercise_index": 0,
            "environment_types": [environment_type],
            "mixed_environment_route": False,
            "segments": [
                {
                    "order_index": i,
                    "environment_type": environment_type,
                    "resolution_status": resolution_status,
                    "cross_domain_conflict": False,
                    "resolved_river_inland_identity": (
                        {"waterbody_id": "HUAOC752", "identity_names": ["Duna"]}
                        if environment_type == "RIVER_INLAND" else None
                    ),
                    "resolved_marine_region_identity": (
                        {"subregion_code": "MAD", "subregion_name": "Adriatic Sea"}
                        if environment_type == "MARINE" else None
                    ),
                }
                for i in range(n)
            ],
        }],
    }


def _weather(n=3, available=True):
    return {
        "schema_version": "0.1",
        "routes": [{
            "route_index": 0,
            "exercise_index": 0,
            "matches": [
                {
                    "order_index": i,
                    "available": available,
                    "status": "MATCHED" if available else "UNAVAILABLE",
                    "matched_sample_id": f"WX{i}" if available else None,
                    "absolute_time_delta_seconds": 120.0 if available else None,
                    "surface_distance_to_sample_m": 50.0 if available else None,
                }
                for i in range(n)
            ],
        }],
    }


def _weather_source(n=3, source_type="MODELLED_HISTORICAL_WEATHER"):
    return {
        "provider": "OPEN_METEO",
        "product": "HISTORICAL_WEATHER_API",
        "source_type": source_type,
        "samples": [
            {"sample_id": f"WX{i}", "temperature_2m_c": 18.0 + i, "wind_speed_mps": 3.0}
            for i in range(n)
        ],
    }


def _wind(n=3, available=True):
    return {
        "schema_version": "0.1",
        "routes": [{
            "route_index": 0,
            "exercise_index": 0,
            "segments": [
                {
                    "order_index": i,
                    "available": available,
                    "status": "AVAILABLE" if available else "BEARING_UNAVAILABLE",
                    "headwind_component_mps": 1.0 if available else None,
                    "tailwind_component_mps": 0.0 if available else None,
                    "crosswind_magnitude_mps": 2.0 if available else None,
                    "relative_air_speed_mps": 4.0 if available else None,
                }
                for i in range(n)
            ],
        }],
    }


def _hydrology(n=3, trust_status="TRUSTED_WITH_LIMITATIONS"):
    included = trust_status in {"TRUSTED", "TRUSTED_WITH_LIMITATIONS"}
    return {
        "schema_version": "0.1",
        "routes": [{
            "route_index": 0,
            "exercise_index": 0,
            "trust_status": trust_status,
            "representativeness_limitations": (
                ["NO_AUTHORITATIVE_ROUTE_REACH_TO_STATION_CROSSWALK"]
                if trust_status == "TRUSTED_WITH_LIMITATIONS" else []
            ),
            "trust_basis": [f"HYDROLOGY_{trust_status}"],
            "trusted_context": (
                {
                    "segments": [
                        {
                            "segment_index": i,
                            "water_level": {"available": True, "value": 300 + i, "unit": "cm"},
                            "discharge": {"available": True, "value": 1000 + i, "unit": "m3/s"},
                            "current_speed_estimate_mps": None,
                            "current_direction_deg": None,
                        }
                        for i in range(n)
                    ]
                }
                if included else None
            ),
        }],
    }


def _build(**overrides):
    inputs = {
        "route_environment_context_input": _route_input(),
        "route_water_environment_identity": _water(),
        "route_weather_sample_matching": _weather(),
        "route_wind_context": _wind(),
        "trusted_route_hydrology_context": _hydrology(),
        "weather_source": _weather_source(),
    }
    inputs.update(overrides)
    return build_trusted_route_environment_context(**inputs)


def test_duna_like_environment_is_trusted_with_limitations_not_promoted():
    result = _build()
    route = result["routes"][0]
    assert result["status"] == STATUS_TRUSTED_WITH_LIMITATIONS
    assert route["status"] == STATUS_TRUSTED_WITH_LIMITATIONS
    assert route["downstream_usable_segment_count"] == 3
    assert route["water_identity_usable_segment_count"] == 3
    assert route["weather_usable_segment_count"] == 3
    assert route["wind_usable_segment_count"] == 3
    assert route["hydrology_usable_segment_count"] == 3


def test_modelled_weather_is_limited_and_carries_sample_evidence():
    segment = _build()["routes"][0]["segments"][0]
    weather = segment["weather"]
    assert weather["status"] == STATUS_TRUSTED_WITH_LIMITATIONS
    assert weather["sample"]["sample_id"] == "WX0"
    assert "MODELLED_GRIDDED_WEATHER" in weather["limitations"]
    assert "WEATHER_REPRESENTATIVENESS_NOT_SEPARATELY_ESTABLISHED" in weather["limitations"]


def test_wind_is_limited_and_never_claims_boat_through_water_speed():
    wind = _build()["routes"][0]["segments"][0]["wind"]
    assert wind["status"] == STATUS_TRUSTED_WITH_LIMITATIONS
    assert wind["headwind_component_mps"] == 1.0
    assert "BOAT_THROUGH_WATER_SPEED_NOT_ESTABLISHED" in wind["limitations"]


def test_trusted_water_identity_is_not_downgraded_inside_component():
    water = _build()["routes"][0]["segments"][0]["water_identity"]
    assert water["status"] == STATUS_TRUSTED
    assert water["environment_type"] == "RIVER_INLAND"
    assert water["resolved_river_inland_identity"]["waterbody_id"] == "HUAOC752"


def test_ambiguous_water_identity_is_withheld_without_erasing_other_components():
    water = _water(resolution_status="AMBIGUOUS")
    result = _build(route_water_environment_identity=water)
    segment = result["routes"][0]["segments"][0]
    assert segment["water_identity"]["status"] == STATUS_WITHHELD
    assert segment["weather"]["included"] is True
    assert segment["status"] == STATUS_TRUSTED_WITH_LIMITATIONS


def test_withheld_hydrology_stays_withheld_while_weather_and_water_remain_usable():
    result = _build(trusted_route_hydrology_context=_hydrology(trust_status="WITHHELD"))
    route = result["routes"][0]
    segment = route["segments"][0]
    assert route["hydrology_usable_segment_count"] == 0
    assert segment["hydrology"]["status"] == STATUS_WITHHELD
    assert segment["status"] == STATUS_TRUSTED_WITH_LIMITATIONS


def test_not_applicable_hydrology_stays_not_applicable_for_marine_route():
    result = _build(
        route_water_environment_identity=_water(environment_type="MARINE"),
        trusted_route_hydrology_context=_hydrology(trust_status="NOT_APPLICABLE"),
    )
    segment = result["routes"][0]["segments"][0]
    assert segment["water_identity"]["status"] == STATUS_TRUSTED
    assert segment["hydrology"]["status"] == STATUS_NOT_APPLICABLE
    assert result["routes"][0]["status"] == STATUS_TRUSTED_WITH_LIMITATIONS


def test_missing_weather_and_wind_do_not_block_trusted_water_and_hydrology():
    result = _build(
        route_weather_sample_matching=_weather(available=False),
        route_wind_context=_wind(available=False),
        trusted_route_hydrology_context=_hydrology(trust_status="TRUSTED"),
    )
    segment = result["routes"][0]["segments"][0]
    assert segment["weather"]["status"] == STATUS_UNAVAILABLE
    assert segment["wind"]["status"] == STATUS_UNAVAILABLE
    assert segment["hydrology"]["status"] == STATUS_TRUSTED
    assert segment["status"] == STATUS_TRUSTED_WITH_LIMITATIONS


def test_only_fully_trusted_components_can_produce_segment_trusted_status():
    result = _build(
        route_weather_sample_matching={"schema_version": "0.1", "routes": []},
        route_wind_context={"schema_version": "0.1", "routes": []},
        trusted_route_hydrology_context=_hydrology(trust_status="TRUSTED"),
        weather_source=None,
    )
    # Unavailable components make the projection partial rather than silently full.
    assert result["routes"][0]["segments"][0]["status"] == STATUS_TRUSTED_WITH_LIMITATIONS


def test_no_usable_component_with_withheld_evidence_is_withheld():
    result = _build(
        route_water_environment_identity=_water(resolution_status="AMBIGUOUS"),
        route_weather_sample_matching=_weather(available=False),
        route_wind_context=_wind(available=False),
        trusted_route_hydrology_context=_hydrology(trust_status="WITHHELD"),
        weather_source=None,
    )
    assert result["routes"][0]["segments"][0]["status"] == STATUS_WITHHELD
    assert result["routes"][0]["status"] == STATUS_WITHHELD


def test_no_environment_evidence_is_unavailable_not_trusted():
    result = build_trusted_route_environment_context(
        _route_input(), None, None, None, None, weather_source=None
    )
    assert result["routes"][0]["status"] == STATUS_UNAVAILABLE
    assert result["routes"][0]["downstream_usable_segment_count"] == 0


def test_hydrology_missing_segment_is_withheld_not_promoted_from_route_status():
    hydro = _hydrology(trust_status="TRUSTED_WITH_LIMITATIONS")
    hydro["routes"][0]["trusted_context"]["segments"] = [
        hydro["routes"][0]["trusted_context"]["segments"][0]
    ]
    result = _build(trusted_route_hydrology_context=hydro)
    assert result["routes"][0]["segments"][1]["hydrology"]["status"] == STATUS_WITHHELD


def test_source_inputs_are_not_mutated_and_nested_payload_is_deep_copied():
    source = _weather_source()
    source_before = deepcopy(source)
    result = _build(weather_source=source)
    result["routes"][0]["segments"][0]["weather"]["sample"]["temperature_2m_c"] = -99
    assert source == source_before


def test_summary_omits_segments_but_preserves_counts_and_limitations():
    full = _build()
    summary = build_trusted_route_environment_context_summary(full)
    route = summary["routes"][0]
    assert route["segment_count"] == 3
    assert route["segments_included"] is False
    assert "segments" not in route
    assert "MODELLED_GRIDDED_WEATHER" in route["route_limitations"]


def test_scope_explicitly_forbids_current_and_physiology_inference():
    scope = _build()["scope"]
    assert scope["resolves_new_provider_evidence"] is False
    assert scope["promotes_component_trust"] is False
    assert scope["estimates_local_current_velocity"] is False
    assert scope["infers_current_from_water_level"] is False
    assert scope["infers_current_from_discharge"] is False
    assert scope["infers_physiological_response"] is False


def test_hydrology_current_fields_remain_none_in_projection():
    hydro = _build()["routes"][0]["segments"][0]["hydrology"]["context"]
    assert hydro["current_speed_estimate_mps"] is None
    assert hydro["current_direction_deg"] is None
