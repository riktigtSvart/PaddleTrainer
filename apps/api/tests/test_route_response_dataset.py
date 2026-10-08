import json
from copy import deepcopy

import pytest
from test_hr_acquisition_readiness_audit import records as declarations
from test_hr_timebase_readiness_audit import evidence_records
from test_response_dataset_split import manifest
from test_route_input_diagnostics import environment
from test_training_data_readiness_audit import sources as _sources_fixture

from app.services.polar_training_samples import normalize_polar_training_samples
from app.services.route_response_dataset import (
    build_route_response_dataset,
    summarize_route_response_dataset,
    verify_route_response_dataset,
)
from app.services.training_data_readiness_audit import build_route_training_data_readiness_audit

sources = _sources_fixture


def package(sources, **kwargs):
    source, route, sample = sources
    env = (
        kwargs.pop("trusted_environment")
        if "trusted_environment" in kwargs
        else environment(sources)
    )
    return build_route_response_dataset(
        source,
        kwargs.pop(
            "normalized_samples",
            normalize_polar_training_samples({"exerciseSamples": sample["exercises"]}),
        ),
        session_external_id=kwargs.pop("session_external_id", "session-1"),
        athlete_id=kwargs.pop("athlete_id", "athlete-1"),
        route_session=route,
        sample_session=sample,
        sample_session_match_count=kwargs.pop("sample_session_match_count", 1),
        trusted_environment=env,
        **kwargs,
    )


def test_full_package_preserves_raw_slots_clock_history_and_separate_targets(sources):
    clocks = evidence_records(sources)
    entries = declarations(sources)
    before = deepcopy((sources, clocks, entries))
    value = package(sources, hr_timebase_snapshots=clocks, hr_acquisition_declarations=entries)
    assert value == package(
        sources, hr_timebase_snapshots=clocks, hr_acquisition_declarations=entries
    )
    assert (sources, clocks, entries) == before
    assert verify_route_response_dataset(value)
    assert verify_route_response_dataset(json.loads(json.dumps(value)))
    assert value["observation_count"] == value["preparation_candidate_count"] == 2
    assert value["hr_slot_count"] == 4
    assert value["split_assignment"]["status"] == "UNASSIGNED"
    stream = value["hr_streams"][0]
    assert [slot["value_bpm"] for slot in stream["samples"]] == [110, 111, 112, 113]
    assert [slot["exercise_elapsed_us"] for slot in stream["samples"]] == [
        500000,
        1500000,
        2500000,
        3500000,
    ]
    assert stream["samples"][0]["mapped_timestamp_utc"] == "2026-09-30T15:00:00.500000+00:00"
    assert stream["native_provider_per_sample_timestamps_present"] is False
    a, b = value["observations"]
    assert a["hr_label_ref"]["grid_start_index_inclusive"] == 0
    assert a["hr_label_ref"]["grid_stop_index_exclusive"] == 2
    assert b["history_ref"]["first_order_index"] == 0
    assert b["history_ref"]["completed_end_order_index"] == 0
    assert (
        b["temporal_context"]["current_workload_available_not_before_exercise_elapsed_ms"] == 4000
    )
    assert b["hr_label_ref"]["label_used_as_predictor"] is False
    assert value["routes"][0]["hr_acquisition"]["acquisition_quality_verified"] is False
    assert value["policy"]["physiological_lag_ms"] is None
    assert value["policy"]["fixed_hr_shift_applied"] is False
    assert value["training_authorized"] is value["causal_prediction_authorized"] is False


def test_unknown_clock_keeps_slots_but_never_invents_timestamps_or_label_mappings(sources):
    value = package(sources)
    assert value["existing_preparation_candidate_count"] == 2
    assert value["preparation_candidate_count"] == 0
    assert value["hr_slot_count"] == 4
    assert all(
        s["mapped_timestamp_utc"] is s["exercise_elapsed_us"] is None
        for s in value["hr_streams"][0]["samples"]
    )
    assert all(
        row["hr_label_ref"]["status"] == "TIME_MAPPING_UNAVAILABLE" for row in value["observations"]
    )
    assert all(
        "VERIFIED_EXPORT_CLOCK_REQUIRED_FOR_DATASET_LABELS" in row["exclusion_reasons"]
        for row in value["observations"]
    )


def test_invalid_or_missing_hr_does_not_remove_observed_workload_history(sources):
    sources[2]["exercises"][0]["samples"]["samples"][0]["values"][1] = None
    value = package(sources)
    a, b = value["observations"]
    assert value["observation_count"] == 2
    assert a["preparation_candidate"] is False
    assert a["workload_available"] is True
    assert b["history_ref"]["first_order_index"] == a["order_index"]
    assert b["history_ref"]["completed_end_order_index"] == a["order_index"]
    assert value["hr_streams"][0]["samples"][1]["value_bpm"] is None
    assert value["hr_streams"][0]["samples"][1]["positive_finite"] is False


@pytest.mark.parametrize(
    "start,end,first,stop",
    [
        (0, 500, 0, 0),
        (500, 1500, 0, 1),
        (501, 1500, 1, 1),
        (500, 1501, 0, 2),
        (1500, 1501, 1, 2),
        (3500, 4000, 3, 4),
    ],
)
def test_exact_export_clock_half_open_grid_references(sources, start, end, first, stop):
    clocks = evidence_records(sources)
    route = sources[0]["routes"][0]
    route["segments"] = route["segments"][:1]
    for name in ("segment_count", "workload_segment_count", "aligned_usable_segment_count"):
        route[name] = 1
    route["segments"][0]["external_workload"].update(
        start_exercise_elapsed_ms=start, end_exercise_elapsed_ms=end
    )
    label = package(sources, hr_timebase_snapshots=clocks)["observations"][0]["hr_label_ref"]
    assert (label["grid_start_index_inclusive"], label["grid_stop_index_exclusive"]) == (
        first,
        stop,
    )
    assert label["recorded_slot_count"] == stop - first


def test_unrecorded_terminal_slots_and_out_of_duration_window_are_explicit(sources):
    clocks = evidence_records(sources)
    for raw in sources[1:]:
        raw["exercises"][0]["durationMillis"] = 6000
    # A fresh export proof is needed for a changed duration; construct it against
    # the current fixture duration, retaining its four actual HR samples.
    from test_hr_timebase_snapshot import record

    from app.services.hr_timebase_snapshot import build_hr_timebase_snapshot
    from app.services.tcx_heart_rate_timebase import build_tcx_heart_rate_timebase

    xml = (
        '<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">'
        '<Activities><Activity Sport="Other"><Id>2026-09-30T15:00:00.250Z</Id>'
        '<Lap StartTime="2026-09-30T15:00:00.250Z"><TotalTimeSeconds>6</TotalTimeSeconds><Track>'
        + "".join(
            f"<Trackpoint><Time>2026-09-30T15:00:0{i}.500Z</Time>"
            f"<HeartRateBpm><Value>{110 + i}</Value></HeartRateBpm></Trackpoint>"
            for i in range(4)
        )
        + "</Track></Lap></Activity></Activities></TrainingCenterDatabase>"
    ).encode()
    sources[2]["exercises"][0]["stopTime"] = "2026-09-30T17:00:06"
    verification = build_tcx_heart_rate_timebase(
        xml, sources[2], expected_session_external_id="session-1", sample_session_match_count=1
    )
    clocks = [
        record(
            build_hr_timebase_snapshot(
                verification,
                sources[2],
                athlete_id="athlete-1",
                session_external_id="session-1",
                sample_session_match_count=1,
            )
        )
    ]
    route = sources[0]["routes"][0]
    for order in (2, 3):
        item = deepcopy(route["segments"][0])
        item["order_index"] = order
        item["environment_context"]["order_index"] = order
        item["external_workload"].update(
            start_exercise_elapsed_ms=order * 2000, end_exercise_elapsed_ms=(order + 1) * 2000
        )
        route["segments"].append(item)
    for name in ("segment_count", "workload_segment_count", "aligned_usable_segment_count"):
        route[name] = 4
    value = package(sources, hr_timebase_snapshots=clocks)
    assert value["hr_slot_count"] == 4 and value["observation_count"] == 4
    tail, invalid = value["observations"][2:]
    assert tail["hr_label_ref"]["status"] == "NO_SAMPLES"
    assert tail["hr_label_ref"]["unrecorded_grid_slot_count"] == 2
    assert tail["history_ref"]["completed_end_order_index"] == 1
    assert tail["temporal_context"]["status"] == "OBSERVED_WORKLOAD_SEQUENCE"
    assert invalid["hr_label_ref"]["status"] == "INVALID_WINDOW"
    assert invalid["history_ref"]["sequence_index"] is None
    assert value["routes"][0]["sequences"][0]["observation_count"] == 3


@pytest.mark.parametrize("mutation", ["DUPLICATE_ORDER", "REORDERED", "OVERLAP", "DUPLICATE_ROUTE"])
def test_ambiguous_chronology_cannot_produce_aliasing_history_or_payloads(sources, mutation):
    route = sources[0]["routes"][0]
    if mutation == "DUPLICATE_ORDER":
        route["segments"][1]["order_index"] = 0
    elif mutation == "REORDERED":
        route["segments"].reverse()
    elif mutation == "OVERLAP":
        route["segments"][1]["external_workload"]["start_exercise_elapsed_ms"] = 1000
    else:
        sources[0]["routes"].append(deepcopy(route))
    value = package(sources)
    assert value["status"] == "WITHHELD"
    assert value["observations"] == value["hr_streams"] == []
    assert value["preparation_candidate_count"] == 0


def test_observed_gap_starts_new_run_without_assuming_physiological_reset(sources):
    sources[0]["routes"][0]["segments"][0]["external_workload"]["end_exercise_elapsed_ms"] = 1000
    value = package(sources)
    assert len(value["routes"][0]["sequences"]) == 2
    a, b = value["observations"]
    assert b["history_ref"]["first_order_index"] == 1
    assert b["history_ref"]["completed_end_order_index"] is None
    assert a["temporal_context"]["physiological_state_reset_verified"] is False
    assert all(
        seq["initial_physiological_state"] == "UNKNOWN"
        and seq["pre_observation_history_censored"]
        and seq["post_observation_recovery_censored"]
        for seq in value["routes"][0]["sequences"]
    )


def test_environment_features_have_per_metric_missingness_and_preserve_limits(sources):
    for item in sources[0]["routes"][0]["segments"]:
        item["environment_context"].update(
            {
                "weather": {
                    "status": "TRUSTED_WITH_LIMITATIONS",
                    "available": True,
                    "usable_for_downstream_environment_context": True,
                    "limitations": ["MODELLED_GRIDDED_WEATHER"],
                    "sample": {
                        "air_temperature_c": 21.7,
                        "wind_speed_mps": 1.25,
                        "sample_timestamp": "2026-09-30T16:00:00+00:00",
                    },
                },
                "wind": {
                    "status": "UNAVAILABLE",
                    "available": False,
                    "usable_for_downstream_environment_context": False,
                    "source_status": "MOVEMENT_BEARING_UNAVAILABLE",
                },
                "hydrology": {
                    "status": "TRUSTED_WITH_LIMITATIONS",
                    "available": True,
                    "usable_for_downstream_environment_context": True,
                    "limitations": ["NO_AUTHORITATIVE_ROUTE_REACH_TO_STATION_CROSSWALK"],
                    "context": {
                        "water_level": {"available": True, "value": 6, "unit": "cm"},
                        "discharge": {"available": True, "value": 714.4, "unit": "m3/s"},
                        "water_temperature": {"available": False, "value": None},
                    },
                },
            }
        )
    value = package(sources)
    row = value["observations"][0]
    assert row["environment_features"]["air_temperature_c"]["value"] == 21.7
    assert row["environment_features"]["water_level_cm"]["value"] == 6
    assert row["environment_features"]["discharge_m3_s"]["value"] == 714.4
    assert row["environment_features"]["water_temperature_c"]["status"] == "MISSING"
    assert row["environment_features"]["headwind_component_mps"]["value"] is None
    assert value["feature_status_counts"]["water_temperature_c"] == {"MISSING": 2}
    assert row["environment_components"]["hydrology"]["limitations"] == [
        "NO_AUTHORITATIVE_ROUTE_REACH_TO_STATION_CROSSWALK"
    ]
    assert value["policy"]["current_velocity_estimated"] is False
    assert all(
        feature["pre_exercise_predictor_authorized"] is False
        for feature in row["environment_features"].values()
    )


@pytest.mark.parametrize(
    "status,usable,applicable,expected",
    [
        ("WITHHELD", False, True, "WITHHELD"),
        ("NOT_APPLICABLE", False, False, "NOT_APPLICABLE"),
        ("UNAVAILABLE", False, True, "MISSING"),
    ],
)
def test_unusable_component_value_is_never_promoted_or_filled(
    sources, status, usable, applicable, expected
):
    for item in sources[0]["routes"][0]["segments"]:
        item["environment_context"]["weather"] = {
            "status": status,
            "available": True,
            "applicable": applicable,
            "usable_for_downstream_environment_context": usable,
            "sample": {"air_temperature_c": 50},
        }
    feature = package(sources)["observations"][0]["environment_features"]["air_temperature_c"]
    assert feature["status"] == expected and feature["value"] is None


def test_target_and_future_hr_claims_cannot_enter_workload_conditioning(sources):
    sources[0]["routes"][0]["segments"][0]["external_workload"].update(
        target_hr=999, future_hr=888, physiological_lag_ms=5000
    )
    value = package(sources)
    row = value["observations"][0]
    assert "target_hr" not in row["workload_observation"]
    assert "future_hr" not in row["workload_observation"]
    assert row["history_ref"]["causal_predictor_history_selected"] is False
    assert value["policy"]["physiological_lag_ms"] is None


@pytest.mark.parametrize(
    "failure", ["OWNER", "SESSION", "AMBIGUOUS_SAMPLE", "NORMALIZATION", "ENVIRONMENT"]
)
def test_owner_source_and_component_binding_failures_withhold_payloads(sources, failure):
    options = {}
    if failure == "OWNER":
        options["athlete_id"] = None
    elif failure == "SESSION":
        options["session_external_id"] = "other"
    elif failure == "AMBIGUOUS_SAMPLE":
        options["sample_session_match_count"] = 2
    elif failure == "NORMALIZATION":
        normalized = normalize_polar_training_samples({"exerciseSamples": sources[2]["exercises"]})
        normalized["series"][0]["values"][0] = 999
        options["normalized_samples"] = normalized
    else:
        env = environment(sources)
        env["routes"][0]["segments"][0]["status"] = "TRUSTED"
        options["trusted_environment"] = env
    value = package(sources, **options)
    assert value["status"] == "WITHHELD"
    assert value["observations"] == value["hr_streams"] == []
    assert value["training_authorized"] is False


def test_wrong_owner_clock_is_not_mapped_and_source_revision_invalidates_saved_proof(sources):
    clocks = evidence_records(sources, owner="athlete-2")
    wrong = package(sources, hr_timebase_snapshots=clocks)
    assert wrong["preparation_candidate_count"] == 0
    assert wrong["hr_streams"][0]["time_mapping_verified"] is False
    clocks = evidence_records(sources)
    sources[2]["exercises"][0]["samples"]["samples"][0]["values"][0] = 120
    changed = package(sources, hr_timebase_snapshots=clocks)
    assert changed["preparation_candidate_count"] == 0
    assert changed["hr_streams"][0]["time_mapping_verified"] is False


def test_explicit_split_changes_package_commitment_not_source_or_audit(sources):
    clocks = evidence_records(sources)
    a = package(sources, hr_timebase_snapshots=clocks)
    b = package(sources, hr_timebase_snapshots=clocks, split_manifest=manifest("TEST"))
    assert a["input_provenance"]["audit_source_hash"] == b["input_provenance"]["audit_source_hash"]
    assert (
        a["input_provenance"]["audit_decision_hash"] == b["input_provenance"]["audit_decision_hash"]
    )
    assert a["package_hash"] != b["package_hash"]
    assert b["split_assignment"]["status"] == "ASSIGNED"
    assert all(
        row["split"] == "TEST" and row["session_group_key"] == b["session_group_key"]
        for row in b["observations"]
    )
    assert b["policy"]["split_assigned"] is True
    assert b["training_authorized"] is False


def test_summary_uses_full_commitment_without_exposing_all_labels_and_hash_detects_edits(sources):
    value = package(sources, hr_timebase_snapshots=evidence_records(sources))
    summary = summarize_route_response_dataset(value)
    assert summary["package_hash"] == value["package_hash"]
    assert summary["payload_included"] is False and "observations" not in summary
    assert "samples" not in summary["hr_streams"][0]
    assert verify_route_response_dataset(summary) is False
    assert verify_route_response_dataset(value)
    value["hr_streams"][0]["samples"][0]["value_bpm"] = 999
    assert verify_route_response_dataset(value) is False


def test_dataset_commitment_links_reproduced_existing_audit(sources):
    value = package(sources)
    audit = build_route_training_data_readiness_audit(
        sources[0],
        normalize_polar_training_samples({"exerciseSamples": sources[2]["exercises"]}),
        session_external_id="session-1",
        athlete_id="athlete-1",
        route_session=sources[1],
        sample_session=sources[2],
        sample_session_match_count=1,
        trusted_environment=environment(sources),
    )
    assert value["input_provenance"]["audit_decision_hash"] == audit["decision_hash"]
    assert value["session_group_key"] == audit["session_group_key"]


def test_withheld_environment_details_survive_when_upstream_usable_context_is_absent(sources):
    env = environment(sources)
    for segment in env["routes"][0]["segments"]:
        segment.update(
            status="WITHHELD",
            usable_for_downstream_environment_context=False,
            weather={
                "status": "WITHHELD",
                "available": True,
                "usable_for_downstream_environment_context": False,
                "limitations": ["SOURCE_NOT_REPRESENTATIVE"],
                "sample": {"air_temperature_c": 99},
            },
        )
    for segment in sources[0]["routes"][0]["segments"]:
        segment.update(
            environment_usable=False,
            aligned_for_expected_response_input=False,
            environment_context=None,
            environment_context_withheld=True,
            environment_status="WITHHELD",
        )
    route = sources[0]["routes"][0]
    route.update(
        model_ready=False,
        status="WITHHELD",
        environment_route_status="WITHHELD",
        environment_usable_segment_count=0,
        aligned_usable_segment_count=0,
    )
    value = package(sources, trusted_environment=env)
    assert value["observation_count"] == 2 and value["preparation_candidate_count"] == 0
    row = value["observations"][0]
    assert row["environment_components"]["weather"]["status"] == "WITHHELD"
    assert row["environment_components"]["weather"]["limitations"] == ["SOURCE_NOT_REPRESENTATIVE"]
    assert row["environment_features"]["air_temperature_c"]["status"] == "WITHHELD"
    assert row["environment_features"]["air_temperature_c"]["value"] is None


def test_multi_route_labels_deduplicate_streams_and_all_windows_keep_one_session_split(sources):
    clocks = evidence_records(sources)
    other = deepcopy(sources[0]["routes"][0])
    other["route_index"] = 1
    sources[0]["routes"].append(other)
    env = environment(sources)
    second = deepcopy(env["routes"][0])
    second["route_index"] = 1
    env["routes"].append(second)
    value = package(
        sources,
        hr_timebase_snapshots=clocks,
        trusted_environment=env,
        split_manifest=manifest("VALIDATION"),
    )
    assert value["observation_count"] == 4 and value["hr_slot_count"] == 4
    assert value["hr_stream_count"] == 1
    assert len({row["row_id"] for row in value["observations"]}) == 4
    assert all(row["split"] == "VALIDATION" for row in value["observations"])
    assert value["policy"]["cross_route_target_overlap_evaluated"] is False


def test_more_than_twenty_five_runs_are_preserved_in_full_contract(sources):
    for raw in sources[1:]:
        raw["exercises"][0]["durationMillis"] = 120000
    route = sources[0]["routes"][0]
    template = deepcopy(route["segments"][0])
    route["segments"] = []
    for order in range(30):
        item = deepcopy(template)
        item["order_index"] = order
        item["environment_context"]["order_index"] = order
        item["external_workload"].update(
            start_exercise_elapsed_ms=order * 4000, end_exercise_elapsed_ms=order * 4000 + 2000
        )
        route["segments"].append(item)
    for name in ("segment_count", "workload_segment_count", "aligned_usable_segment_count"):
        route[name] = 30
    value = package(sources)
    assert value["observation_count"] == 30
    assert len(value["routes"][0]["sequences"]) == 30
    summary = summarize_route_response_dataset(value)
    assert len(summary["observation_preview"]) == 4
    assert summary["routes"][0]["sequence_count"] == 30
    assert len(summary["routes"][0]["sequences"]) == 25
    assert summary["routes"][0]["sequences_truncated"] is True


def test_noncanonical_source_cannot_emit_nonfinite_data_or_verified_package_payload(sources):
    sources[2]["exercises"][0]["samples"]["samples"][0]["values"][0] = float("nan")
    value = package(sources)
    assert value["status"] == "WITHHELD" and value["observations"] == value["hr_streams"] == []
    assert "AUDIT_SOURCE_NOT_CANONICAL_JSON" in value["blocking_reasons"]
    json.dumps(value, allow_nan=False)
