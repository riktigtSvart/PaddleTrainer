import json
from copy import deepcopy
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.routes import polar
from app.services.heart_rate_sample_validation import (
    CONTRACT_ID,
    VALIDATION_VERSION,
    build_training_session_heart_rate_validation,
)


@pytest.fixture
def session():
    return {
        "identifier": {"id": "hr-session"},
        "product": {"modelName": "POLAR RECORDING DEVICE"},
        "exercises": [
            {
                "identifier": {"id": "exercise-1"},
                "startTime": "2026-09-30T17:00:00",
                "stopTime": "2026-09-30T17:00:04",
                "timezoneOffsetMinutes": 120,
                "durationMillis": 4000,
                "sport": {"id": "95"},
                "pauseTimes": [],
                "samples": {
                    "samples": [
                        {
                            "type": "HEART_RATE",
                            "intervalMillis": 1000,
                            "values": [110, 111, 112, 113],
                        }
                    ]
                },
            }
        ],
    }


def validate(session, **kwargs):
    return build_training_session_heart_rate_validation(
        session,
        expected_session_external_id=kwargs.pop("identity", "hr-session"),
        sample_session_match_count=kwargs.pop("count", 1),
        **kwargs,
    )


def hr_series(session):
    return session["exercises"][0]["samples"]["samples"][0]


def exercise_result(session):
    return validate(session)["exercises"][0]


def test_clean_values_and_matching_clocks_do_not_verify_time_origin_or_sensor(session):
    before = deepcopy(session)
    result = validate(session)
    assert session == before
    assert result["validation_version"] == VALIDATION_VERSION
    assert result["source_contract_id"] == CONTRACT_ID
    assert result["status"] == "CHECKED_WITH_LIMITATIONS"
    assert result["source_binding_verified"] is True
    assert result["technically_clean_exercise_count"] == 1
    assert result["training_authorized"] is False
    assert result["numeric_prediction_authorized"] is False
    assert result["verified_hr_label_count"] == 0
    exercise = result["exercises"][0]
    assert exercise["technical_status"] == "TECHNICALLY_CLEAN_WITH_LIMITATIONS"
    assert exercise["time_origin_verified"] is False
    assert exercise["acquisition_quality_verified"] is False
    timebase = exercise["timebase"]
    assert timebase["exercise_start_utc"] == "2026-09-30T15:00:00+00:00"
    assert timebase["wall_clock_duration_ms"] == 4000
    assert timebase["duration_clock_relation"] == "DECLARED_EQUALS_WALL_CLOCK"
    assert timebase["slot_count_minus_expected_half_open_grid"] == 0
    assert timebase["sample_grid_span_ms"] == 3000
    assert timebase["nominal_slot_occupancy_ms"] == 4000
    assert timebase["consistency_status"] == "CONSISTENT_WITH_REPORTED_METADATA"
    assert timebase["first_sample_timestamp_utc"] is None
    assert timebase["time_origin_status"] == "NOT_VERIFIED"
    assert exercise["acquisition"]["recording_product_model_name"] == "POLAR RECORDING DEVICE"
    assert exercise["acquisition"]["hr_sensor_identity"] is None
    assert len(result["input_provenance"]["source_hash"]) == 64
    assert len(result["decision_hash"]) == 64


def test_raw_invalid_categories_survive_normalization_boundary(session):
    hr_series(session)["values"] = [None, True, "110", float("inf"), 0, -10, 112]
    result = validate(session)
    assert result["status"] == "WITHHELD"
    quality = result["exercises"][0]["value_quality"]
    assert quality["positive_finite_sample_count"] == 1
    assert quality["invalid_or_missing_sample_count"] == 6
    assert quality["invalid_value_counts"] == {
        "MISSING": 1,
        "BOOLEAN": 1,
        "NON_NUMERIC": 1,
        "NON_FINITE": 1,
        "ZERO": 1,
        "NEGATIVE": 1,
    }
    assert "HR_SOURCE_NOT_CANONICAL_JSON" in result["blocking_reasons"]
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("values", [[0, -1, None], [True, "120", None], []])
def test_unusable_values_are_not_filled_or_promoted(session, values):
    hr_series(session)["values"] = values
    result = exercise_result(session)
    assert result["technical_status"] == "TECHNICAL_ISSUES"
    assert result["value_quality"]["positive_finite_sample_count"] == 0
    assert result["value_quality"]["observed_min_bpm"] is None
    assert result["verified_hr_label_count"] == 0


@pytest.mark.parametrize("values", [[111], [111, 111, 111, 111]])
def test_constant_run_is_descriptive_and_does_not_imply_sensor_failure(session, values):
    hr_series(session)["values"] = values
    result = exercise_result(session)
    quality = result["value_quality"]
    assert result["technical_status"] == "TECHNICALLY_CLEAN_WITH_LIMITATIONS"
    assert quality["longest_constant_run_slots"] == len(values)
    assert quality["longest_constant_run_span_ms"] == (len(values) - 1) * 1000
    assert quality["artifact_status"] == "NOT_ASSESSED"
    assert quality["physiological_plausibility_status"] == "NOT_ASSESSED"


def test_gaps_break_constant_runs_and_adjacent_change_calculation(session):
    hr_series(session)["values"] = [None, 110, 110, 110, None, 200, 204, 204, None, None]
    quality = exercise_result(session)["value_quality"]
    assert quality["longest_invalid_run_slots"] == 2
    assert quality["longest_invalid_run_nominal_ms"] == 2000
    assert quality["leading_invalid_slots"] == 1
    assert quality["trailing_invalid_slots"] == 2
    assert quality["longest_constant_run_slots"] == 3
    assert quality["adjacent_valid_pair_count"] == 4
    assert quality["largest_adjacent_change_bpm"] == 4
    assert quality["largest_adjacent_change_bpm_per_second"] == 4


def test_large_jump_is_reported_without_inventing_a_physiological_threshold(session):
    hr_series(session)["values"] = [110, 310, 111, 112]
    quality = exercise_result(session)["value_quality"]
    assert quality["observed_max_bpm"] == 310
    assert quality["largest_adjacent_change_bpm"] == 200
    assert quality["artifact_status"] == "NOT_ASSESSED"
    assert validate(session)["policy"]["physiological_outlier_threshold_configured"] is False


@pytest.mark.parametrize("interval", [True, None, 0, -1, 1000.0, "1000", 2**63])
def test_invalid_intervals_do_not_produce_an_assumed_time_grid(session, interval):
    hr_series(session)["intervalMillis"] = interval
    result = exercise_result(session)
    assert result["technical_status"] == "TECHNICAL_ISSUES"
    assert result["value_quality"]["interval_ms"] is None
    assert result["timebase"]["sample_grid_span_ms"] is None
    assert result["timebase"]["expected_half_open_grid_slot_count"] is None
    assert result["timebase"]["consistency_status"] == "REVIEW_REQUIRED"


def test_duplicate_hr_series_are_not_selected_or_combined(session):
    session["exercises"][0]["samples"]["samples"].append(deepcopy(hr_series(session)))
    result = exercise_result(session)
    assert result["technical_status"] == "WITHHELD"
    assert result["hr_series_count"] == 2
    assert result["value_quality"]["slot_count"] == 0


@pytest.mark.parametrize("value", ["bad", True, 120])
def test_non_list_value_containers_are_rejected(session, value):
    hr_series(session)["values"] = value
    assert (
        "HEART_RATE_VALUES_CONTAINER_INVALID"
        in exercise_result(session)["technical_blocking_reasons"]
    )


def test_optional_samples_absence_is_not_a_malformed_container(session):
    session["exercises"][0]["samples"] = {"rrSamples": []}
    result = exercise_result(session)
    assert result["technical_status"] == "UNAVAILABLE"
    assert "HR_SAMPLES_CONTAINER_INVALID" not in result["technical_blocking_reasons"]


def test_legacy_direct_list_is_explicit_and_transition_hr_is_not_merged(session):
    container = session["exercises"][0]["samples"]
    container["transitionSamples"] = [deepcopy(hr_series(session))]
    result = exercise_result(session)
    assert result["acquisition"]["transition_hr_series_count"] == 1
    assert result["value_quality"]["slot_count"] == 4
    session["exercises"][0]["samples"] = container["samples"]
    assert "NONSTANDARD_SAMPLES_CONTAINER" in exercise_result(session)["limitations"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("startTime", "not-a-date"),
        ("stopTime", None),
        ("timezoneOffsetMinutes", True),
        ("timezoneOffsetMinutes", 1440),
        ("durationMillis", True),
    ],
)
def test_unverifiable_exercise_time_is_separate_from_numeric_value_quality(session, field, value):
    session["exercises"][0][field] = value
    result = exercise_result(session)
    assert result["technical_status"] == "TECHNICALLY_CLEAN_WITH_LIMITATIONS"
    assert result["timebase"]["consistency_status"] == "REVIEW_REQUIRED"
    assert result["timebase"]["time_origin_status"] == "NOT_VERIFIED"


@pytest.mark.parametrize("stop", ["2026-09-30T17:00:00", "2026-09-30T16:59:59"])
def test_stop_before_or_at_start_requires_review(session, stop):
    session["exercises"][0]["stopTime"] = stop
    assert "EXERCISE_STOP_NOT_AFTER_START" in exercise_result(session)["timebase"]["review_reasons"]


def test_timezone_fallback_and_explicit_utc_are_supported(session):
    session["timezoneOffsetMinutes"] = 120
    session["exercises"][0].pop("timezoneOffsetMinutes")
    assert exercise_result(session)["timebase"]["exercise_start_utc"] == "2026-09-30T15:00:00+00:00"
    session["exercises"][0]["startTime"] = "2026-09-30T15:00:00Z"
    session["exercises"][0]["stopTime"] = "2026-09-30T15:00:04Z"
    session.pop("timezoneOffsetMinutes")
    assert (
        exercise_result(session)["timebase"]["consistency_status"]
        == "CONSISTENT_WITH_REPORTED_METADATA"
    )


def test_valid_pause_explains_duration_difference_without_proving_sample_pause_clock(session):
    e = session["exercises"][0]
    e["stopTime"] = "2026-09-30T17:00:06"
    e["pauseTimes"] = [{"startTime": "2026-09-30T17:00:02", "endTime": "2026-09-30T17:00:04"}]
    timebase = exercise_result(session)["timebase"]
    assert timebase["pause_inventory"]["union_duration_ms"] == 2000
    assert timebase["wall_clock_duration_ms"] == 6000
    assert timebase["reported_pause_adjusted_wall_duration_ms"] == 4000
    assert timebase["duration_clock_relation"] == "DECLARED_EQUALS_WALL_MINUS_REPORTED_PAUSES"
    assert timebase["time_origin_status"] == "NOT_VERIFIED"
    assert timebase["pause_clock_status"] == "NOT_VERIFIED"


@pytest.mark.parametrize(
    "pauses",
    [
        None,
        "bad",
        [{"startTime": "bad", "endTime": "bad"}],
        [{"startTime": "2026-09-30T16:59:59", "endTime": "2026-09-30T17:00:01"}],
    ],
)
def test_malformed_or_outside_pauses_are_not_used_to_prove_alignment(session, pauses):
    session["exercises"][0]["pauseTimes"] = pauses
    timebase = exercise_result(session)["timebase"]
    assert timebase["pause_inventory"]["status"] == "INVALID"
    assert timebase["reported_pause_adjusted_wall_duration_ms"] is None
    assert "PAUSE_METADATA_INVALID" in timebase["review_reasons"]


def test_overlapping_pauses_use_union_for_diagnostics_and_require_review(session):
    e = session["exercises"][0]
    e["pauseTimes"] = [
        {"startTime": "2026-09-30T17:00:00", "endTime": "2026-09-30T17:00:02"},
        {"startTime": "2026-09-30T17:00:01", "endTime": "2026-09-30T17:00:03"},
    ]
    inventory = exercise_result(session)["timebase"]["pause_inventory"]
    assert inventory["union_duration_ms"] == 3000
    assert inventory["overlap_detected"] is True
    assert inventory["status"] == "INVALID"


def test_missing_pause_records_are_not_invented(session):
    session["exercises"][0].pop("pauseTimes")
    assert exercise_result(session)["timebase"]["pause_inventory"]["status"] == "NOT_PROVIDED"


def test_truncated_or_endpoint_inclusive_series_is_a_count_diagnostic_only(session):
    hr_series(session)["values"] = [110, 111]
    assert exercise_result(session)["timebase"]["slot_count_minus_expected_half_open_grid"] == -2
    hr_series(session)["values"] = [110, 111, 112, 113, 114]
    result = exercise_result(session)
    assert result["timebase"]["slot_count_minus_expected_half_open_grid"] == 1
    assert result["technical_status"] == "TECHNICALLY_CLEAN_WITH_LIMITATIONS"
    assert result["time_origin_verified"] is False


def test_rr_offline_flags_and_recording_product_do_not_prove_sensor_or_hr_quality(session):
    session["exercises"][0]["samples"]["rrSamples"] = [
        {"durationMillis": 800, "offline": False},
        {"durationMillis": 810, "offline": True},
        {"durationMillis": True, "offline": "false"},
    ]
    acquisition = exercise_result(session)["acquisition"]
    assert acquisition["rr_inventory"]["sample_count"] == 3
    assert acquisition["rr_inventory"]["positive_duration_count"] == 2
    assert acquisition["rr_inventory"]["offline_count"] == 1
    assert acquisition["rr_inventory"]["invalid_offline_flag_count"] == 1
    assert acquisition["rr_inventory"]["hr_quality_verified"] is False
    assert acquisition["hr_sensor_identity"] is None
    assert acquisition["hr_sensor_modality"] is None
    assert acquisition["status"] == "NOT_ESTABLISHED"


def test_unrecognized_time_and_quality_fields_are_not_trusted(session):
    hr_series(session).update(startTime="2026-09-30T15:00:00Z", sensor="H10", quality=100)
    result = exercise_result(session)
    assert result["unrecognized_hr_series_fields"] == ["quality", "sensor", "startTime"]
    assert result["time_origin_verified"] is False
    assert result["acquisition_quality_verified"] is False
    assert "UNRECOGNIZED_HR_SERIES_FIELDS_REQUIRE_REVIEW" in result["limitations"]


@pytest.mark.parametrize("count", [0, 2, True])
def test_missing_or_duplicate_sessions_block_verification(session, count):
    result = validate(session, count=count)
    assert result["status"] == "WITHHELD"
    assert result["source_binding_verified"] is False
    assert result["exercises"][0]["technical_status"] == "WITHHELD"


def test_duplicate_exercise_ids_are_ambiguous_but_distinct_exercises_stay_separate(session):
    session["exercises"].append(deepcopy(session["exercises"][0]))
    result = validate(session)
    assert all(e["technical_status"] == "WITHHELD" for e in result["exercises"])
    session["exercises"][1]["identifier"]["id"] = "exercise-2"
    session["exercises"][1]["samples"]["samples"][0]["values"] = [120, 121]
    result = validate(session)
    assert result["exercise_count"] == 2
    assert result["exercises"][0]["value_quality"]["slot_count"] == 4
    assert result["exercises"][1]["value_quality"]["slot_count"] == 2


@pytest.mark.parametrize("identity", [None, True, "", "another-session"])
def test_session_identity_must_be_verifiable(session, identity):
    assert validate(session, identity=identity)["source_binding_verified"] is False


def test_no_session_and_non_mapping_exercise_are_safe(session):
    assert validate(None, count=0)["status"] == "WITHHELD"
    session["exercises"] = []
    assert validate(session)["status"] == "UNAVAILABLE"
    session["exercises"] = [None]
    assert "SAMPLE_EXERCISE_INVALID" in exercise_result(session)["technical_blocking_reasons"]


def test_source_and_decision_hashes_are_sensitive_and_output_contains_no_raw_series(session):
    first = validate(session)
    assert first == validate(session)
    assert "values" not in first["exercises"][0]
    assert "samples" not in first["exercises"][0]
    hr_series(session)["values"][0] += 1
    changed = validate(session)
    assert first["input_provenance"]["source_hash"] != changed["input_provenance"]["source_hash"]
    assert first["decision_hash"] != changed["decision_hash"]
    session["not_json"] = object()
    assert validate(session)["status"] == "WITHHELD"


@pytest.mark.parametrize("mode", ["ONE", "MISSING", "DUPLICATE", "NO_ROUTES"])
@pytest.mark.asyncio
async def test_inspection_wires_validation_independently_of_environment_without_writing(
    monkeypatch, session, mode
):
    db = SimpleNamespace(
        scalar=AsyncMock(return_value=SimpleNamespace(scopes=["training_sessions:read"]))
    )
    monkeypatch.setattr(
        polar, "get_or_create_demo_user", AsyncMock(return_value=SimpleNamespace(id="athlete"))
    )
    monkeypatch.setattr(polar, "get_valid_access_token", AsyncMock(return_value="token"))

    async def payload(*args, **kwargs):
        if kwargs["features"] == ["routes"]:
            return {"trainingSessions": [] if mode == "NO_ROUTES" else [deepcopy(session)]}
        return {
            "trainingSessions": []
            if mode == "MISSING"
            else [session, deepcopy(session)]
            if mode == "DUPLICATE"
            else [session]
        }

    monkeypatch.setattr(polar.PolarClient, "list_training_sessions", payload)
    monkeypatch.setattr(
        polar,
        "load_and_bind_athlete_state_scientific_views",
        AsyncMock(return_value={"status": "NOT_BOUND", "athlete_state_context": None}),
    )
    writes = AsyncMock(side_effect=AssertionError("inspection must remain read-only"))
    monkeypatch.setattr(polar, "persist_route_environment_evidence", writes)
    result = await polar._build_training_session_route_inspection(
        route_date=date(2026, 9, 30),
        artifact_policy_profile="BALANCED",
        wind_speed_mps=None,
        wind_direction_from_deg=None,
        weather_provider=None,
        hydrology_provider=None,
        hydrology_station_registry_number=None,
        hydrology_relation_provider=None,
        hydrology_relation_validation_mode=False,
        persist_environment_evidence=False,
        db=db,
    )
    if mode == "NO_ROUTES":
        assert result["route_sessions"] == []
    else:
        item = result["route_sessions"][0]
        validation = item["heart_rate_sample_validation"]
        assert validation["status"] == ("CHECKED_WITH_LIMITATIONS" if mode == "ONE" else "WITHHELD")
        assert validation["training_authorized"] is False
        assert validation["verified_hr_label_count"] == 0
        assert item["training_data_readiness_audit"]["training_authorized"] is False
        assert item["route_expected_response_model"]["response_available"] is False
    writes.assert_not_awaited()
