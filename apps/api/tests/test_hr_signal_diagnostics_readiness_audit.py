from copy import deepcopy
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from test_hr_acquisition_readiness_audit import records as declarations
from test_hr_timebase_readiness_audit import evidence_records
from test_training_data_readiness_audit import audit
from test_training_data_readiness_audit import sources as _sources_fixture

from app.api.routes import polar
from app.services.heart_rate_sample_validation import build_training_session_heart_rate_validation
from app.services.heart_rate_signal_diagnostics import build_training_session_hr_signal_diagnostics
from app.services.training_data_readiness_audit import build_training_data_readiness_audit_summary

sources = _sources_fixture


def test_diagnostics_enrich_the_audit_without_promoting_preparation_or_training(sources):
    before = deepcopy(sources)
    result = audit(sources)
    assert result["audit_version"] == "0.5.0"
    assert result["candidate_segment_count"] == 2
    assert result["diagnostics_available_route_count"] == 1
    assert result["diagnostics_verified_clock_route_count"] == 0
    assert (
        result["routes"][0]["hr_signal_diagnostics"]["observation_counts"][
            "largest_adjacent_changes"
        ]
        == 3
    )
    for segment in result["routes"][0]["segments"]:
        assert segment["hr_signal_diagnostics"]["status"] == "TIMEBASE_NOT_VERIFIED"
        assert segment["hr_signal_diagnostics"]["expected_grid_slot_count"] is None
    assert result["training_authorized"] is result["numeric_output_authorized"] is False
    assert result["policy"]["signal_diagnostics_promote_eligibility"] is False
    assert "values" not in str(result)
    assert "sample_timestamps_utc" not in str(result)
    assert sources == before


def test_verified_clock_window_counts_agree_with_the_existing_audit_coverage(sources):
    clocks = evidence_records(sources)
    result = audit(sources, hr_timebase_snapshots=clocks)
    assert result["diagnostics_verified_clock_route_count"] == 1
    for segment in result["routes"][0]["segments"]:
        diagnostic = segment["hr_signal_diagnostics"]
        assert diagnostic["expected_grid_slot_count"] == segment["expected_grid_slot_count"] == 2
        assert (
            diagnostic["positive_finite_sample_count"]
            == segment["positive_finite_grid_sample_count"]
        )
        assert diagnostic["status"] == "COMPLETE_WITH_LIMITATIONS"
        assert diagnostic["adjacent_valid_pair_count"] == 1
        assert diagnostic["observed_nonzero_change_pair_count"] == 1
    standalone = build_training_session_hr_signal_diagnostics(
        sources[2],
        athlete_id="athlete-1",
        session_external_id="session-1",
        sample_session_match_count=1,
        hr_timebase_snapshots=clocks,
    )
    assert (
        result["input_provenance"]["hr_signal_diagnostics_decision_hash"]
        == standalone["decision_hash"]
    )


def test_user_reported_issue_stays_visible_and_retains_existing_withholding(sources):
    entries = declarations(sources, reported_issue_codes=["SIGNAL_DROPOUT"])
    result = audit(sources, hr_acquisition_declarations=entries)
    assert result["candidate_segment_count"] == 0
    context = result["routes"][0]["hr_signal_diagnostics"]["acquisition_context"]
    assert context["reported_issue_codes"] == ["SIGNAL_DROPOUT"]
    assert context["declaration_source"] == "USER_DECLARATION"
    assert context["acquisition_quality_verified"] is False


def test_constant_recordings_remain_observations_without_an_artifact_decision(sources):
    sources[2]["exercises"][0]["samples"]["samples"][0]["values"] = [110] * 4
    result = audit(sources)
    assert result["candidate_segment_count"] == 2
    route = result["routes"][0]["hr_signal_diagnostics"]
    assert route["observation_counts"]["constant_runs"] == 1
    assert route["artifact_status"] == "NOT_ASSESSED"
    assert route["acquisition_quality_verified"] is False


@pytest.mark.parametrize("failure", ["NORMALIZATION", "ROUTE_METADATA", "ROUTE_IDENTITY"])
def test_diagnostics_do_not_attach_to_an_unmatched_or_forged_route(sources, failure):
    kwargs = {}
    if failure == "NORMALIZATION":
        from app.services.polar_training_samples import normalize_polar_training_samples

        normalized = normalize_polar_training_samples({"exerciseSamples": sources[2]["exercises"]})
        normalized["series"][0]["values"][0] = 99
        kwargs["normalized_samples"] = normalized
    elif failure == "ROUTE_METADATA":
        sources[1]["exercises"][0]["durationMillis"] += 1
    else:
        sources[1]["identifier"]["id"] = "other-session"
    result = audit(sources, **kwargs)
    assert result["diagnostics_available_route_count"] == 0
    assert result["candidate_segment_count"] == 0
    assert result["routes"][0]["hr_signal_diagnostics"]["status"] == "NOT_APPLIED"
    assert (
        result["routes"][0]["segments"][0]["hr_signal_diagnostics"]["status"]
        == "SOURCE_NOT_APPLIED"
    )


def test_diagnostics_cannot_bypass_environment_or_model_input_gates(sources):
    clocks = evidence_records(sources)
    sources[0]["routes"][0]["model_ready"] = False
    result = audit(sources, hr_timebase_snapshots=clocks)
    assert result["diagnostics_verified_clock_route_count"] == 1
    assert result["candidate_segment_count"] == 0
    assert "UPSTREAM_MODEL_INPUT_NOT_READY" in result["routes"][0]["blocking_reasons"]


def test_reordered_exercises_use_provider_identity_instead_of_array_position(sources):
    other = deepcopy(sources[2]["exercises"][0])
    other["identifier"]["id"] = "other-exercise"
    other["samples"]["samples"][0]["values"] = [0] * 4
    sources[2]["exercises"].insert(0, other)
    result = audit(sources)
    route = result["routes"][0]
    assert route["sample_exercise_index"] == 1
    assert route["hr_signal_diagnostics"]["positive_finite_sample_count"] == 4
    assert route["hr_signal_diagnostics"]["invalid_or_missing_sample_count"] == 0


def test_summary_keeps_review_window_positions_but_bounds_them_explicitly(sources):
    sources[0]["routes"][0]["segments"] *= 20
    result = build_training_data_readiness_audit_summary(audit(sources))
    assert "segments" not in result["routes"][0]
    packet = result["routes"][0]["hr_signal_diagnostics"]["windows_requiring_coverage_review"]
    assert packet["total_count"] == 40
    assert packet["returned_count"] == 25
    assert packet["truncated"] is True
    assert packet["items"][0]["start_exercise_elapsed_ms"] == 0


def test_forged_diagnostic_claims_in_upstream_input_are_not_trusted(sources):
    sources[0]["hr_signal_diagnostics"] = {
        "training_authorized": True,
        "acquisition_quality_verified": True,
    }
    result = audit(sources)
    assert result["hr_signal_diagnostics_evidence"]["acquisition_quality_verified"] is False
    assert result["training_authorized"] is result["numeric_output_authorized"] is False


@pytest.mark.asyncio
async def test_route_inspection_exposes_diagnostics_and_keeps_the_old_hr_decision(
    monkeypatch, sources
):
    _source, route, sample = sources
    clocks = evidence_records(sources, owner="athlete-1")
    entries = declarations(sources)
    baseline = build_training_session_heart_rate_validation(
        sample, expected_session_external_id="session-1", sample_session_match_count=1
    )
    db = SimpleNamespace(
        scalar=AsyncMock(return_value=SimpleNamespace(scopes=["training_sessions:read"]))
    )
    monkeypatch.setattr(
        polar, "get_or_create_demo_user", AsyncMock(return_value=SimpleNamespace(id="athlete-1"))
    )
    monkeypatch.setattr(polar, "get_valid_access_token", AsyncMock(return_value="token"))
    client = SimpleNamespace(
        list_training_sessions=AsyncMock(
            side_effect=[{"trainingSessions": [route]}, {"trainingSessions": [sample]}]
        )
    )
    monkeypatch.setattr(polar, "PolarClient", lambda: client)
    clock_loader = AsyncMock(return_value=clocks)
    declaration_loader = AsyncMock(return_value=entries)
    monkeypatch.setattr(polar, "load_current_hr_timebase_snapshots", clock_loader)
    monkeypatch.setattr(polar, "load_current_hr_acquisition_declarations", declaration_loader)
    result = await polar.inspect_training_session_routes(
        route_date=date(2026, 9, 30),
        artifact_policy_profile="BALANCED",
        wind_speed_mps=None,
        wind_direction_from_deg=None,
        weather_provider=None,
        hydrology_provider=None,
        hydrology_station_registry_number=None,
        hydrology_relation_provider=None,
        hydrology_relation_validation_mode=False,
        waterbody_provider=None,
        waterbody_search_radius_m=1000.0,
        water_surface_provider=None,
        water_surface_boundary_near_m=25.0,
        water_surface_query_padding_m=1000.0,
        marine_surface_provider=None,
        marine_surface_boundary_near_m=25.0,
        marine_surface_query_padding_m=1000.0,
        db=db,
    )
    actual = result["route_sessions"][0]
    assert actual["heart_rate_sample_validation"] == baseline
    diagnostics = actual["heart_rate_signal_diagnostics"]
    assert diagnostics["verified_clock_exercise_count"] == 1
    assert (
        diagnostics["exercises"][0]["acquisition_context"]["declaration_source"]
        == "USER_DECLARATION"
    )
    assert (
        actual["training_data_readiness_audit"]["hr_signal_diagnostics_evidence"]["decision_hash"]
        == diagnostics["decision_hash"]
    )
    for loader in (clock_loader, declaration_loader):
        assert loader.await_args.kwargs["athlete_id"] == "athlete-1"
        assert loader.await_args.kwargs["session_external_id"] == "session-1"
