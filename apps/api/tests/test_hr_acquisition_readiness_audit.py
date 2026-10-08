from copy import deepcopy
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from test_hr_acquisition_declarations import PAYLOAD, record
from test_hr_timebase_readiness_audit import evidence_records
from test_training_data_readiness_audit import audit
from test_training_data_readiness_audit import sources as _sources_fixture

from app.api.routes import polar
from app.services.heart_rate_sample_validation import build_training_session_heart_rate_validation
from app.services.hr_acquisition_declarations import build_hr_acquisition_declaration

sources = _sources_fixture


def records(sources, index=1, **changes):
    return [
        record(
            build_hr_acquisition_declaration(
                {**PAYLOAD, "exercise_external_id": "exercise-1", **changes},
                sources[2],
                athlete_id="athlete-1",
                session_external_id="session-1",
                sample_session_match_count=1,
            ),
            index,
        )
    ]


def test_declaration_informs_audit_without_certifying_labels_or_promoting_preparation(sources):
    before = deepcopy(sources)
    baseline = audit(sources)
    result = audit(sources, hr_acquisition_declarations=records(sources))
    assert sources == before
    assert result["audit_version"] == "0.5.0"
    assert result["user_declared_acquisition_route_count"] == 1
    assert result["candidate_segment_count"] == baseline["candidate_segment_count"] == 2
    assert result["routes"][0]["hr_acquisition"]["declaration_source"] == "USER_DECLARATION"
    assert (
        result["routes"][0]["hr_acquisition"]["declared_sensor"]["sensor_model"]
        == "Example Wearable"
    )
    assert result["routes"][0]["hr_acquisition"]["acquisition_quality_verified"] is False
    assert "HR_ACQUISITION_QUALITY_NOT_ESTABLISHED" in result["limitations"]
    assert "HR_SENSOR_DETAILS_USER_DECLARED_NOT_PROVIDER_VERIFIED" in result["limitations"]
    assert result["training_authorized"] is result["numeric_output_authorized"] is False


def test_sensor_statement_and_saved_export_proof_are_independent(sources):
    clocks = evidence_records(sources)
    result = audit(
        sources, hr_timebase_snapshots=clocks, hr_acquisition_declarations=records(sources)
    )
    assert result["export_timebase_verified_route_count"] == 1
    assert result["user_declared_acquisition_route_count"] == 1
    assert result["routes"][0]["hr_timebase"]["sample_grid_origin_us"] == 500000
    assert result["hr_acquisition_evidence"]["acquisition_quality_verified"] is False


def test_reported_acquisition_issue_withholds_preparation_without_altering_samples(sources):
    before = deepcopy(sources)
    entries = records(sources, reported_issue_codes=["SIGNAL_DROPOUT"])
    result = audit(sources, hr_acquisition_declarations=entries)
    route = result["routes"][0]
    assert route["fully_covered_grid_segment_count"] == 2
    assert route["status"] == "WITHHELD"
    assert result["candidate_segment_count"] == 0
    assert "HR_USER_REPORTED_ACQUISITION_ISSUES_REQUIRE_REVIEW" in route["blocking_reasons"]
    assert route["hr_acquisition"]["reported_issue_codes"] == ["SIGNAL_DROPOUT"]
    assert sources == before


def test_conflicting_statements_require_explicit_correction(sources):
    first = records(sources)
    second = records(sources, index=2, sensor_modality="ELECTRICAL", body_location="CHEST")
    conflicted = audit(sources, hr_acquisition_declarations=first + second)
    assert conflicted["candidate_segment_count"] == 0
    assert "HR_ACQUISITION_DECLARATION_UNUSABLE" in conflicted["routes"][0]["blocking_reasons"]
    correction = records(
        sources,
        index=3,
        supersedes_declaration_ids=[
            first[0]["declaration_id"],
            second[0]["declaration_id"],
        ],
    )
    result = audit(sources, hr_acquisition_declarations=first + second + correction)
    assert result["candidate_segment_count"] == 2
    assert result["training_authorized"] is False


def test_conflict_on_another_exercise_does_not_apply_to_this_route(sources):
    other = deepcopy(sources[2]["exercises"][0])
    other["identifier"]["id"] = "exercise-2"
    sources[2]["exercises"].append(other)
    entries = records(sources)
    entries += records(sources, index=2, exercise_external_id="exercise-2")
    entries += records(
        sources, index=3, exercise_external_id="exercise-2", sensor_model="Another Device"
    )
    result = audit(sources, hr_acquisition_declarations=entries)
    assert result["hr_acquisition_evidence"]["status"] == "REVIEW_REQUIRED"
    assert result["routes"][0]["hr_acquisition"]["status"] == "USER_DECLARED_WITH_LIMITATIONS"
    assert result["candidate_segment_count"] == 2


@pytest.mark.parametrize("failure", ["OWNER", "SOURCE", "COLUMN"])
def test_invalid_declaration_cannot_supply_sensor_metadata_or_preparation(sources, failure):
    entries = records(sources)
    if failure == "OWNER":
        entries[0]["declaration"]["athlete_id"] = "another-athlete"
    elif failure == "SOURCE":
        sources[2]["modified"] = "2025-03-01T00:00:00Z"
    else:
        entries[0]["column_identity"]["exercise_external_id"] = "another-exercise"
    result = audit(sources, hr_acquisition_declarations=entries)
    assert result["candidate_segment_count"] == 0
    assert result["routes"][0]["hr_acquisition"]["declared_sensor"] is None


def test_sensor_statement_cannot_bypass_environment_or_route_identity_boundary(sources):
    entries = records(sources)
    sources[0]["routes"][0]["model_ready"] = False
    result = audit(sources, hr_acquisition_declarations=entries)
    assert result["user_declared_acquisition_route_count"] == 1
    assert result["candidate_segment_count"] == 0
    assert "UPSTREAM_MODEL_INPUT_NOT_READY" in result["routes"][0]["blocking_reasons"]
    sources[1]["exercises"][0]["durationMillis"] = 4001
    result = audit(sources, hr_acquisition_declarations=entries)
    assert result["user_declared_acquisition_route_count"] == 0
    assert result["routes"][0]["hr_acquisition"]["declared_sensor"] is None


@pytest.mark.asyncio
async def test_route_inspection_loads_owned_declarations_and_keeps_raw_hr_validation_stable(
    monkeypatch, sources
):
    source, route, sample = sources
    entries = records(sources)
    baseline = build_training_session_heart_rate_validation(
        sample, expected_session_external_id="session-1", sample_session_match_count=1
    )
    db = SimpleNamespace(
        scalar=AsyncMock(return_value=SimpleNamespace(scopes=["training_sessions:read"]))
    )
    monkeypatch.setattr(
        polar, "get_or_create_demo_user", AsyncMock(return_value=SimpleNamespace(id="athlete-1"))
    )
    monkeypatch.setattr(polar, "get_valid_access_token", AsyncMock(return_value="test-token"))

    async def payload(*args, **kwargs):
        return {"trainingSessions": [route if kwargs["features"] == ["routes"] else sample]}

    monkeypatch.setattr(polar.PolarClient, "list_training_sessions", payload)
    monkeypatch.setattr(
        polar,
        "load_and_bind_athlete_state_scientific_views",
        AsyncMock(return_value={"status": "NOT_BOUND", "athlete_state_context": None}),
    )
    monkeypatch.setattr(
        polar, "build_route_expected_response_input", lambda *args, **kwargs: source
    )
    loader = AsyncMock(return_value=entries)
    monkeypatch.setattr(polar, "load_current_hr_acquisition_declarations", loader)
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
    loader.assert_awaited_once_with(
        db,
        sample,
        athlete_id="athlete-1",
        session_external_id="session-1",
        sample_session_match_count=1,
    )
    session_result = result["route_sessions"][0]
    assert session_result["heart_rate_acquisition_context"]["declared_exercise_count"] == 1
    assert (
        session_result["training_data_readiness_audit"]["user_declared_acquisition_route_count"]
        == 1
    )
    assert session_result["heart_rate_sample_validation"] == baseline
