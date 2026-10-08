from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from test_hr_timebase_readiness_audit import evidence_records
from test_response_dataset_split import manifest
from test_training_data_readiness_audit import sources as _sources_fixture

from app.services.environment_evidence_persistence import build_environment_persistence_plan
from app.services.environment_replay_snapshot import (
    build_environment_replay_snapshot,
    canonical_hash,
    replay_environment_dataset,
    verify_environment_replay_snapshot,
)
from app.services.hydrology_trust_decision_snapshot import build_hydrology_trust_decision_snapshot
from app.services.route_environment_evidence_record import build_route_environment_evidence_record
from app.services.route_response_dataset import verify_route_response_dataset
from app.services.route_water_environment_identity_snapshot import (
    bind_route_water_environment_identity_snapshot_to_evidence_record,
    build_route_water_environment_identity_snapshot,
)
from app.services.trusted_environment_context_snapshot import (
    build_trusted_route_environment_context_snapshot,
)
from app.services.trusted_route_environment_context import build_trusted_route_environment_context

sources = _sources_fixture
OWNER = UUID(int=101)
EVIDENCE_ID = UUID(int=202)


def capture_inputs(sources, *, owner=OWNER, evidence_id=EVIDENCE_ID, clocks=None):
    expected, route_session, sample_session = deepcopy(sources)
    clock_records = (
        evidence_records((expected, route_session, sample_session), owner=str(owner))
        if clocks is None
        else clocks
    )
    start = datetime(2026, 9, 30, 15, tzinfo=UTC)
    segments = []
    for row in expected["routes"][0]["segments"]:
        motion, order = row["external_workload"], row["order_index"]
        segments.append(
            {
                **motion,
                "order_index": order,
                "segment_index": order,
                "source_segment_index": order,
                "source_waypoint_contiguous": True,
                "start_waypoint_index": order,
                "end_waypoint_index": order + 1,
                "start_timestamp": (
                    start + timedelta(milliseconds=motion["start_exercise_elapsed_ms"])
                ).isoformat(),
                "end_timestamp": (
                    start + timedelta(milliseconds=motion["end_exercise_elapsed_ms"])
                ).isoformat(),
                "start_position": {"latitude_deg": 47.5, "longitude_deg": 19.04},
                "end_position": {"latitude_deg": 47.50001, "longitude_deg": 19.04},
                "surface_distance_m": 5.0,
                "movement_bearing_deg": 0.0,
            }
        )
    context = {
        "provider": "POLAR",
        "schema_version": "0.1",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "segments": segments,
                "time_context": {"absolute_timestamps_resolved": True},
            }
        ],
    }
    workload = {
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "observations": [
                    r["external_workload"] | {"order_index": r["order_index"]}
                    for r in expected["routes"][0]["segments"]
                ],
            }
        ]
    }
    weather_source = {
        "provider": "OPEN_METEO",
        "product": "HISTORICAL",
        "source_type": "MODELLED_HISTORICAL_WEATHER",
        "metadata": {"generationtime_ms": 12.34},
        "samples": [
            {
                "sample_id": "weather-1",
                "sample_timestamp": start.isoformat(),
                "source_provider": "OPEN_METEO",
                "source_product": "HISTORICAL",
                "source_type": "MODELLED_HISTORICAL_WEATHER",
                "latitude_deg": 47.5,
                "longitude_deg": 19.04,
                "air_temperature_c": 18.0,
                "wind_speed_mps": 1.25,
                "wind_direction_from_deg": 85.0,
                "wind_gust_mps": 4.8,
                "temporal_resolution_seconds": 3600,
                "spatial_support": "GRIDDED_POINT_ESTIMATE",
            }
        ],
    }
    weather_matches = {
        "schema_version": "0.1",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "matches": [
                    {
                        "order_index": s["order_index"],
                        "available": True,
                        "status": "MATCHED",
                        "matched_sample_id": "weather-1",
                        "absolute_time_delta_seconds": 1.0,
                        "surface_distance_to_sample_m": 100.0,
                    }
                    for s in segments
                ],
            }
        ],
    }
    wind = {
        "schema_version": "0.1",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "segments": [
                    {
                        "order_index": s["order_index"],
                        "available": True,
                        "status": "AVAILABLE",
                        "headwind_component_mps": 0.1,
                        "tailwind_component_mps": 0.0,
                        "crosswind_magnitude_mps": 1.1,
                        "relative_air_speed_mps": 2.6,
                    }
                    for s in segments
                ],
            }
        ],
    }
    water = {
        "schema_version": "0.1",
        "provider": "PADDLETRAINER",
        "available": True,
        "status": "RESOLVED",
        "route_count": 1,
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "environment_types": ["RIVER_INLAND"],
                "segments": [
                    {
                        "order_index": s["order_index"],
                        "environment_type": "RIVER_INLAND",
                        "resolution_status": "DIRECT_RESOLVED",
                        "resolved_river_inland_identity": {"waterbody_id": "TEST-RIVER"},
                    }
                    for s in segments
                ],
            }
        ],
    }
    hydrology_source = {
        "provider": "OVF_VRAQUERY",
        "source_type": "OPERATIONAL_HYDROLOGY_OBSERVATION",
        "measurements": [
            {
                "measurement_id": "level-1",
                "source_provider": "OVF_VRAQUERY",
                "observed_at": start.isoformat(),
                "metric_key": "WATER_LEVEL",
                "metric_code": 68,
                "value": 6.0,
                "unit": "cm",
                "data_type_code": 101,
            },
            {
                "measurement_id": "discharge-1",
                "source_provider": "OVF_VRAQUERY",
                "observed_at": start.isoformat(),
                "metric_key": "DISCHARGE",
                "metric_code": 87,
                "value": 714.4,
                "unit": "m3/s",
                "data_type_code": 101,
            },
        ],
    }
    hydrology_segments = []
    for segment in segments:
        item = {"order_index": segment["order_index"], "segment_index": segment["order_index"]}
        for name, measurement in zip(
            ("water_level", "discharge"), hydrology_source["measurements"], strict=True
        ):
            item[name] = {
                **measurement,
                "available": True,
                "status": "MATCHED",
                "absolute_time_delta_seconds": 1.0,
                "data_quality_code": None,
                "field_quality_code": None,
            }
        item["water_temperature"] = {"available": False, "status": "MEASUREMENT_UNAVAILABLE"}
        hydrology_segments.append(item)
    raw_hydrology = {
        "routes": [{"route_index": 0, "exercise_index": 0, "segments": hydrology_segments}]
    }
    trusted_hydrology = {
        "schema_version": "0.1",
        "status": "TRUSTED_WITH_LIMITATIONS",
        "route_count": 1,
        "trusted_with_limitations_route_count": 1,
        "policy": {"promotes_trust": False},
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "trust_status": "TRUSTED_WITH_LIMITATIONS",
                "source_context_available": True,
                "hydrology_context_included": True,
                "usable_for_downstream_environment_context": True,
                "usable_with_limitations": True,
                "trust_basis": ["SYNTHETIC_UPSTREAM_CONTEXT"],
                "representativeness_limitations": ["NO_FULL_REACH_CROSSWALK"],
                "trusted_context": {"segments": hydrology_segments},
            }
        ],
    }
    trusted = build_trusted_route_environment_context(
        context, water, weather_matches, wind, trusted_hydrology, weather_source=weather_source
    )
    for row, environment in zip(
        expected["routes"][0]["segments"], trusted["routes"][0]["segments"], strict=True
    ):
        row["environment_context"] = deepcopy(environment)
    identity = build_route_water_environment_identity_snapshot(water)
    record = build_route_environment_evidence_record(
        session_external_id="session-1",
        route_environment_context_input=context,
        route_external_workload_evidence=workload,
        route_weather_sample_matching=weather_matches,
        route_wind_context=wind,
        weather_source=weather_source,
        route_hydrology_context=raw_hydrology,
        hydrology_source=hydrology_source,
    )
    bind_route_water_environment_identity_snapshot_to_evidence_record(record, identity)
    plan = build_environment_persistence_plan(record)
    trust = build_hydrology_trust_decision_snapshot(
        environment_evidence_set_id=str(evidence_id),
        environment_evidence_hash=plan["evidence_hash"],
        route_hydrology_source_resolution_snapshot=None,
        route_hydrology_representativeness=None,
        trusted_route_hydrology_context=trusted_hydrology,
    )
    projection = build_trusted_route_environment_context_snapshot(
        environment_evidence_set_id=str(evidence_id),
        environment_evidence_hash=plan["evidence_hash"],
        route_water_environment_identity_snapshot=identity,
        hydrology_trust_decision_snapshot=trust,
        trusted_route_environment_context=trusted,
    )
    return {
        "athlete_id": str(owner),
        "session_external_id": "session-1",
        "evidence_set_id": str(evidence_id),
        "evidence_hash": plan["evidence_hash"],
        "evidence_record": record,
        "expected_response_input": expected,
        "trusted_environment": trusted,
        "provider_selection": {
            "weather_provider": "OPEN_METEO_HISTORICAL",
            "hydrology_provider": "OVF_VRAQUERY",
        },
        "weather_source": weather_source,
        "route_session": route_session,
        "sample_session": sample_session,
        "sample_session_match_count": 1,
        "hr_timebase_snapshots": clock_records,
        "hr_acquisition_declarations": [],
        "lineage": {
            "water_identity": identity,
            "hydrology_resolution": None,
            "hydrology_trust": trust,
            "hydrology_relation": None,
            "trusted_projection": projection,
        },
    }


@pytest.fixture
def inputs(sources):
    return capture_inputs(sources)


def replay(snapshot, inputs, **changes):
    args = {
        "snapshot_id": UUID(int=303),
        "athlete_id": inputs["athlete_id"],
        "session_external_id": "session-1",
        "route_session": inputs["route_session"],
        "sample_session": inputs["sample_session"],
        "clocks": inputs["hr_timebase_snapshots"],
        "declarations": inputs["hr_acquisition_declarations"],
    }
    return replay_environment_dataset(snapshot, **(args | changes))


def test_complete_capture_and_repeat_replay_preserve_source_and_exact_clock(inputs):
    before = deepcopy(inputs)
    snapshot = build_environment_replay_snapshot(**inputs)
    assert verify_environment_replay_snapshot(snapshot)
    assert snapshot == build_environment_replay_snapshot(**inputs)
    value = replay(snapshot, inputs)
    assert value == replay(snapshot, inputs) and verify_route_response_dataset(value)
    assert value["observation_count"] == value["preparation_candidate_count"] == 2
    assert value["hr_slot_count"] == 4 and value["hr_streams"][0]["sample_grid_origin_us"] == 500000
    assert value["input_provenance"]["database_environment_replay_verified"] is False
    assert value["replay_evidence"]["environmental_provider_calls"] == 0
    assert (
        value["observations"][0]["environment_features"]["water_temperature_c"]["status"]
        == "MISSING"
    )
    assert value["observations"][0]["environment_features"]["discharge_m3_s"]["value"] == 714.4
    assert (
        value["policy"]["fixed_hr_shift_applied"] is False
        and value["policy"]["physiological_lag_ms"] is None
    )
    assert value["training_authorized"] is False and inputs == before


@pytest.mark.parametrize(
    "change", ["owner", "session", "route", "samples", "proofs", "corrupt", "implementation"]
)
def test_changed_binding_cannot_replay(inputs, change):
    snapshot, kwargs = build_environment_replay_snapshot(**inputs), {}
    if change == "owner":
        kwargs["athlete_id"] = str(UUID(int=999))
    elif change == "session":
        kwargs["session_external_id"] = "other-session"
    elif change == "route":
        kwargs["route_session"] = inputs["route_session"] | {"modified": "changed"}
    elif change == "samples":
        kwargs["sample_session"] = inputs["sample_session"] | {"modified": "changed"}
    elif change == "proofs":
        kwargs["clocks"] = []
    elif change == "corrupt":
        snapshot["inputs"]["weather_source"]["metadata"]["generationtime_ms"] = 999
    else:
        snapshot["unassigned_dataset_package_hash"] = "0" * 64
        snapshot["snapshot_hash"] = canonical_hash(
            {k: v for k, v in snapshot.items() if k != "snapshot_hash"}
        )
    with pytest.raises(ValueError, match="REPLAY_"):
        replay(snapshot, inputs, **kwargs)


@pytest.mark.parametrize(
    "field", ["lineage", "evidence_hash", "sample_session_match_count", "trusted_environment"]
)
def test_capture_requires_full_consistent_lineage(inputs, field):
    if field == "lineage":
        inputs[field]["trusted_projection"] = None
    elif field == "evidence_hash":
        inputs[field] = "f" * 64
    elif field == "sample_session_match_count":
        inputs[field] = 2
    else:
        inputs[field]["routes"][0]["segments"][0]["weather"]["included"] = False
    with pytest.raises(ValueError, match="REPLAY_"):
        build_environment_replay_snapshot(**inputs)


@pytest.mark.parametrize("split", ["TRAIN", "VALIDATION", "TEST"])
def test_replay_whole_session_assignment_is_request_only(inputs, split):
    snapshot = build_environment_replay_snapshot(**inputs)
    value = replay(snapshot, inputs, split_manifest=manifest(split, owner=inputs["athlete_id"]))
    assert all(row["split"] == split for row in value["observations"])
    assert all(row["split"] == split for row in value["hr_streams"])
    assert (
        value["split_assignment"]["assignment_persisted"] is value["training_authorized"] is False
    )
    assert replay(snapshot, inputs)["split_assignment"]["status"] == "UNASSIGNED"


def test_runtime_metadata_is_pinned_even_when_legacy_evidence_hash_ignores_it(inputs):
    before = build_environment_replay_snapshot(**inputs)
    inputs["weather_source"]["metadata"]["generationtime_ms"] = 56.78
    after = build_environment_replay_snapshot(**inputs)
    assert before["evidence_hash"] == after["evidence_hash"]
    assert before["snapshot_hash"] != after["snapshot_hash"]
    assert replay(before, inputs)["package_hash"] != replay(after, inputs)["package_hash"]


@pytest.mark.parametrize(
    "bad", [None, {}, {"snapshot_schema_version": "0.2"}, {"bad": float("nan")}]
)
def test_incomplete_or_noncanonical_snapshots_are_invalid(bad):
    assert verify_environment_replay_snapshot(bad) is False
