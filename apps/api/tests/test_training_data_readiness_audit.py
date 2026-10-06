from copy import deepcopy
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.routes import polar
from app.services.athlete_state_temporal_binding import build_athlete_state_temporal_binding
from app.services.polar_training_samples import normalize_polar_training_samples
from app.services.route_expected_response_input import build_route_expected_response_input
from app.services.training_data_readiness_audit import (
    build_route_training_data_readiness_audit,
    build_training_data_readiness_audit_summary,
    build_training_data_readiness_cohort_summary,
)


@pytest.fixture
def sources():
    context = {"as_of_date": date(2026, 9, 29), "training_load": {"available": True}}
    binding = build_athlete_state_temporal_binding(
        "2026-09-30T15:00:00+00:00",
        [
            {
                "state_timestamp": "2026-09-29T22:00:00+00:00",
                "snapshot_id": "state",
                "context": context,
                "source": {"source_policy": "PRIOR_LOCAL_DAY_CLOSED_WINDOW"},
            }
        ],
    )
    workload = {
        "schema_version": "0.1",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "observations": [
                    {
                        "order_index": i,
                        "gps_ground_speed_mps": 2.5,
                        "start_exercise_elapsed_ms": i * 2000,
                        "end_exercise_elapsed_ms": (i + 1) * 2000,
                    }
                    for i in range(2)
                ],
            }
        ],
    }
    environment = {
        "schema_version": "0.1",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "status": "TRUSTED_WITH_LIMITATIONS",
                "segments": [
                    {
                        "order_index": i,
                        "status": "TRUSTED_WITH_LIMITATIONS",
                        "usable_for_downstream_environment_context": True,
                    }
                    for i in range(2)
                ],
            }
        ],
    }
    source = build_route_expected_response_input(
        workload, environment, athlete_state_context=context, athlete_state_binding=binding
    )
    exercise = {
        "identifier": {"id": "exercise-1"},
        "startTime": "2026-09-30T17:00:00",
        "timezoneOffsetMinutes": 120,
        "durationMillis": 4000,
        "sport": {"id": "42"},
    }
    route = {"identifier": {"id": "session-1"}, "exercises": [exercise]}
    sample = deepcopy(route)
    sample["exercises"][0]["samples"] = {
        "samples": [
            {"type": "HEART_RATE", "intervalMillis": 1000, "values": [110, 111, 112, 113]},
        ]
    }
    return source, route, sample


def audit(sources, **kwargs):
    source, route, sample = sources
    return build_route_training_data_readiness_audit(
        source,
        kwargs.pop(
            "normalized_samples",
            normalize_polar_training_samples({"exerciseSamples": sample.get("exercises")}),
        ),
        session_external_id=kwargs.pop("session_external_id", "session-1"),
        athlete_id=kwargs.pop("athlete_id", "athlete-1"),
        route_session=route,
        sample_session=sample,
        sample_session_match_count=kwargs.pop("sample_session_match_count", 1),
        **kwargs,
    )


def test_positive_is_only_a_preparation_candidate_without_label_values(sources):
    before = deepcopy(sources)
    result = audit(sources)
    assert sources == before
    assert result["status"] == "CANDIDATE_WITH_LIMITATIONS"
    assert result["candidate_segment_count"] == 2
    assert result["training_authorized"] is False
    assert result["numeric_output_authorized"] is False
    route = result["routes"][0]
    assert route["exercise_start_utc"] == "2026-09-30T15:00:00+00:00"
    assert route["exercise_match_basis"] == "PROVIDER_EXERCISE_ID"
    assert route["hr_inventory"]["positive_finite_sample_count"] == 4
    assert all(s["expected_grid_slot_count"] == 2 for s in route["segments"])
    assert "HR_SAMPLE_TIME_ORIGIN_NOT_VERIFIED" in result["limitations"]
    assert result["policy"]["provider_time_origin_verified"] is False
    assert "values" not in str(result)
    assert len(result["input_provenance"]["source_hash"]) == 64
    assert len(result["decision_hash"]) == 64


def test_reordered_sample_exercises_match_by_identity(sources):
    sample = sources[2]
    other = deepcopy(sample["exercises"][0])
    other["identifier"]["id"] = "other"
    other["samples"]["samples"][0]["values"] = [0, 0, 0, 0]
    sample["exercises"].insert(0, other)
    result = audit(sources)
    assert result["candidate_segment_count"] == 2
    assert result["routes"][0]["sample_exercise_index"] == 1


def test_no_id_unique_temporal_sport_duration_key_is_explicit(sources):
    for session in sources[1:]:
        session["exercises"][0].pop("identifier")
    result = audit(sources)
    assert result["candidate_segment_count"] == 2
    assert result["routes"][0]["exercise_match_basis"] == "UNIQUE_START_SPORT_DURATION"


@pytest.mark.parametrize(
    "field,value",
    [
        ("startTime", "2026-09-30T17:00:01"),
        ("sport", {"id": "99"}),
        ("durationMillis", 5000),
        ("timezoneOffsetMinutes", 60),
    ],
)
def test_same_id_with_conflicting_metadata_is_blocked(sources, field, value):
    sources[2]["exercises"][0][field] = value
    result = audit(sources)
    assert result["status"] == "WITHHELD"
    assert "EXERCISE_METADATA_MISMATCH" in result["routes"][0]["blocking_reasons"]


@pytest.mark.parametrize("field", ["startTime", "sport", "durationMillis", "timezoneOffsetMinutes"])
def test_missing_required_metadata_is_unverifiable(sources, field):
    sources[2]["exercises"][0].pop(field)
    result = audit(sources)
    assert result["candidate_segment_count"] == 0
    assert "EXERCISE_TIME_SPORT_DURATION_UNVERIFIABLE" in result["routes"][0]["blocking_reasons"]


def test_exercise_timezone_precedes_session_offset_and_aware_time_is_accepted(sources):
    sources[2]["timezoneOffsetMinutes"] = -60
    assert audit(sources)["candidate_segment_count"] == 2
    sources[2]["exercises"][0]["startTime"] = "2026-09-30T15:00:00Z"
    sources[2]["exercises"][0].pop("timezoneOffsetMinutes")
    assert audit(sources)["candidate_segment_count"] == 2


def test_session_timezone_fallback(sources):
    sources[2]["timezoneOffsetMinutes"] = 120
    sources[2]["exercises"][0].pop("timezoneOffsetMinutes")
    assert audit(sources)["candidate_segment_count"] == 2


@pytest.mark.parametrize("side", [1, 2])
@pytest.mark.parametrize("use_id", [True, False])
def test_duplicate_exercise_identity_blocks_all_matches(sources, side, use_id):
    if not use_id:
        for session in sources[1:]:
            session["exercises"][0].pop("identifier")
    sources[side]["exercises"].append(deepcopy(sources[side]["exercises"][0]))
    result = audit(sources)
    assert result["candidate_segment_count"] == 0
    assert "EXERCISE_IDENTITY_MISSING_OR_AMBIGUOUS" in result["routes"][0]["blocking_reasons"]


def test_different_ids_do_not_fall_back_to_position_or_time(sources):
    sources[2]["exercises"][0]["identifier"]["id"] = "different"
    assert audit(sources)["candidate_segment_count"] == 0


@pytest.mark.parametrize("count", [0, 2, True, -1])
def test_sample_session_count_is_exactly_one(sources, count):
    result = audit(sources, sample_session_match_count=count)
    assert result["candidate_segment_count"] == 0
    assert "SAMPLE_SESSION_MISSING_OR_AMBIGUOUS" in result["blocking_reasons"]


@pytest.mark.parametrize("identity", [None, True, "", "different"])
def test_session_identity_is_required_and_consistent(sources, identity):
    result = audit(sources, session_external_id=identity)
    assert result["candidate_segment_count"] == 0


def test_athlete_and_sample_session_identity_are_required(sources):
    assert audit(sources, athlete_id=None)["candidate_segment_count"] == 0
    sources[2]["identifier"]["id"] = "different"
    assert "SAMPLE_SESSION_IDENTITY_MISMATCH" in audit(sources)["blocking_reasons"]


@pytest.mark.parametrize("invalid", [None, 0, -10, True, "112"])
def test_missing_and_invalid_hr_are_not_interpolated(sources, invalid):
    sources[2]["exercises"][0]["samples"]["samples"][0]["values"][2] = invalid
    result = audit(sources)
    assert result["candidate_segment_count"] == 1
    route = result["routes"][0]
    assert route["segments"][1]["grid_coverage_status"] == "PARTIAL"
    assert route["segments"][1]["candidate_for_data_preparation"] is False
    assert route["hr_inventory"]["invalid_or_missing_sample_count"] == 1
    assert "PARTIAL_HR_GRID_COVERAGE" in route["limitations"]


def test_truncated_series_counts_absent_slots(sources):
    sources[2]["exercises"][0]["samples"]["samples"][0]["values"] = [110]
    result = audit(sources)
    assert result["candidate_segment_count"] == 0
    assert result["routes"][0]["segments"][0]["missing_or_invalid_grid_slot_count"] == 1
    assert result["routes"][0]["segments"][1]["missing_or_invalid_grid_slot_count"] == 2


@pytest.mark.parametrize("values", [[], [0, 0, 0, 0], [None, None, None, None]])
def test_no_usable_hr_blocks_preparation(sources, values):
    sources[2]["exercises"][0]["samples"]["samples"][0]["values"] = values
    result = audit(sources)
    assert result["status"] == "WITHHELD"
    assert result["candidate_segment_count"] == 0
    assert "NO_FULLY_COVERED_HR_SEGMENT" in result["routes"][0]["blocking_reasons"]


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_nonfinite_raw_values_cannot_produce_a_canonical_candidate(sources, value):
    sources[2]["exercises"][0]["samples"]["samples"][0]["values"][0] = value
    result = audit(sources)
    assert result["candidate_segment_count"] == 0
    assert "AUDIT_SOURCE_NOT_CANONICAL_JSON" in result["blocking_reasons"]


@pytest.mark.parametrize("interval", [None, 0, -1, True, 1000.0])
def test_invalid_grid_interval_blocks_candidates(sources, interval):
    sources[2]["exercises"][0]["samples"]["samples"][0]["intervalMillis"] = interval
    assert audit(sources)["candidate_segment_count"] == 0


def test_multiple_hr_series_are_ambiguous(sources):
    collection = sources[2]["exercises"][0]["samples"]["samples"]
    collection.append(deepcopy(collection[0]))
    assert (
        "HEART_RATE_SERIES_MISSING_OR_AMBIGUOUS" in audit(sources)["routes"][0]["blocking_reasons"]
    )


@pytest.mark.parametrize(
    "start,end", [(True, 2000), (-1, 2000), (2000, 2000), (0, 5000), (0.0, 2000), (None, 2000)]
)
def test_invalid_windows_cannot_become_candidates(sources, start, end):
    workload = sources[0]["routes"][0]["segments"][0]["external_workload"]
    workload.update(start_exercise_elapsed_ms=start, end_exercise_elapsed_ms=end)
    result = audit(sources)
    assert result["candidate_segment_count"] == 1
    assert result["routes"][0]["segments"][0]["grid_coverage_status"] == "INVALID_WINDOW"


def test_half_open_windows_and_sub_interval_window(sources):
    workload = sources[0]["routes"][0]["segments"][0]["external_workload"]
    workload.update(start_exercise_elapsed_ms=1, end_exercise_elapsed_ms=1000)
    result = audit(sources)
    assert result["routes"][0]["segments"][0]["expected_grid_slot_count"] == 0
    workload.update(start_exercise_elapsed_ms=1000, end_exercise_elapsed_ms=2000)
    assert audit(sources)["routes"][0]["segments"][0]["expected_grid_slot_count"] == 1


def test_boundary_failures_are_not_promoted_by_hr_coverage(sources):
    sources[0]["routes"][0]["model_ready"] = False
    result = audit(sources)
    assert result["routes"][0]["fully_covered_grid_segment_count"] == 2
    assert result["candidate_segment_count"] == 0
    assert "UPSTREAM_MODEL_INPUT_NOT_READY" in result["routes"][0]["blocking_reasons"]


def test_declared_normalization_counts_cannot_be_forged(sources):
    normalized = normalize_polar_training_samples({"exerciseSamples": sources[2]["exercises"]})
    normalized["series"][0]["valid_sample_count"] = 999
    result = audit(sources, normalized_samples=normalized)
    assert "NORMALIZED_SAMPLES_SOURCE_MISMATCH" in result["blocking_reasons"]


def test_hashes_are_deterministic_sensitive_and_summary_preserves_commitment(sources):
    result = audit(sources)
    assert result == audit(sources)
    summary = build_training_data_readiness_audit_summary(result)
    assert summary["decision_hash"] == result["decision_hash"]
    assert summary["routes"][0]["segments_included"] is False
    assert "segments" not in summary["routes"][0]
    sources[2]["exercises"][0]["samples"]["samples"][0]["values"][0] += 1
    changed = audit(sources)
    assert changed["input_provenance"]["source_hash"] != result["input_provenance"]["source_hash"]
    assert changed["decision_hash"] != result["decision_hash"]


def test_noncanonical_source_is_blocked_and_empty_routes_are_unavailable(sources):
    sources[2]["created"] = object()
    assert "AUDIT_SOURCE_NOT_CANONICAL_JSON" in audit(sources)["blocking_reasons"]
    sources[0]["routes"] = []
    assert audit(sources)["status"] == "UNAVAILABLE"


def test_grouping_uses_workouts_not_segments_and_duplicates_are_excluded(sources):
    first = audit(sources)
    cohort = build_training_data_readiness_cohort_summary([first])
    assert cohort["candidate_distinct_session_count"] == 1
    assert cohort["candidate_segment_count"] == 2
    assert cohort["split_status"] == "INSUFFICIENT_DISTINCT_SESSIONS"
    duplicate = build_training_data_readiness_cohort_summary([first, first])
    assert duplicate["duplicate_session_group_count"] == 1
    assert duplicate["candidate_distinct_session_count"] == 0
    for session in sources[1:]:
        session["identifier"]["id"] = "session-2"
    second = audit(sources, session_external_id="session-2")
    cohort = build_training_data_readiness_cohort_summary([first, second])
    assert cohort["candidate_distinct_session_count"] == 2
    assert cohort["split_status"] == "SPLIT_REVIEW_REQUIRED"
    assert cohort["training_authorized"] is False
    assert cohort["candidate_utc_date_count"] == 1
    assert cohort["candidate_sport_ids"] == ["42"]
    assert cohort["audit_scope"] == "PROVIDED_SESSIONS_ONLY"
    assert build_training_data_readiness_cohort_summary([])["session_count"] == 0


def test_multiple_routes_still_form_one_session_group(sources):
    second_route = deepcopy(sources[0]["routes"][0])
    second_route["route_index"] = 1
    sources[0]["routes"].append(second_route)
    result = audit(sources)
    assert result["candidate_route_count"] == 2
    assert result["candidate_segment_count"] == 4
    cohort = build_training_data_readiness_cohort_summary([result])
    assert cohort["candidate_distinct_session_count"] == 1
    assert cohort["split_status"] == "INSUFFICIENT_DISTINCT_SESSIONS"


@pytest.mark.parametrize("mode", ["POSITIVE", "BLOCKED", "DUPLICATE_SAMPLES", "EMPTY"])
@pytest.mark.asyncio
async def test_real_inspection_wires_audit_without_writing(monkeypatch, sources, mode):
    source, route, sample = sources
    db = SimpleNamespace(
        scalar=AsyncMock(return_value=SimpleNamespace(scopes=["training_sessions:read"]))
    )
    monkeypatch.setattr(
        polar, "get_or_create_demo_user", AsyncMock(return_value=SimpleNamespace(id="athlete-1"))
    )
    monkeypatch.setattr(polar, "get_valid_access_token", AsyncMock(return_value="token"))

    async def payload(*args, **kwargs):
        if kwargs["features"] == ["routes"]:
            return {"trainingSessions": [route] if mode != "EMPTY" else []}
        return {
            "trainingSessions": [sample, deepcopy(sample)]
            if mode == "DUPLICATE_SAMPLES"
            else [sample]
        }

    monkeypatch.setattr(polar.PolarClient, "list_training_sessions", payload)
    monkeypatch.setattr(
        polar,
        "load_and_bind_athlete_state_scientific_views",
        AsyncMock(return_value={"status": "NOT_BOUND", "athlete_state_context": None}),
    )
    if mode == "BLOCKED":
        source["routes"][0]["model_ready"] = False
    monkeypatch.setattr(
        polar, "build_route_expected_response_input", lambda *args, **kwargs: source
    )
    writes = AsyncMock(side_effect=AssertionError("read-only inspection"))
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
    cohort = result["training_data_readiness_cohort"]
    assert cohort["candidate_distinct_session_count"] == (1 if mode == "POSITIVE" else 0)
    assert cohort["training_authorized"] is False
    if mode != "EMPTY":
        audit_result = result["route_sessions"][0]["training_data_readiness_audit"]
        assert audit_result["candidate_segment_count"] == (2 if mode == "POSITIVE" else 0)
        assert "segments" not in audit_result["routes"][0]
        assert (
            result["route_sessions"][0]["route_expected_response_model"]["response_available"]
            is False
        )
    writes.assert_not_awaited()
