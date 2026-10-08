from copy import deepcopy
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from test_hr_acquisition_readiness_audit import records as declarations
from test_hr_timebase_readiness_audit import evidence_records
from test_route_input_diagnostics import environment
from test_training_data_readiness_audit import audit
from test_training_data_readiness_audit import sources as _sources_fixture

from app.api.routes import polar
from app.services.heart_rate_sample_validation import build_training_session_heart_rate_validation
from app.services.training_data_readiness_audit import build_training_data_readiness_audit_summary

sources = _sources_fixture


@pytest.mark.parametrize("failure", ["DUPLICATE", "REORDERED", "OVERLAP"])
def test_temporal_ambiguity_blocks_existing_preparation_candidate(sources, failure):
    segments = sources[0]["routes"][0]["segments"]
    if failure == "DUPLICATE":
        segments[1]["order_index"] = 0
    elif failure == "REORDERED":
        segments.reverse()
    else:
        segments[1]["external_workload"]["start_exercise_elapsed_ms"] = 1000
    result = audit(sources)
    route = result["routes"][0]
    assert route["temporal_context"]["status"] == "WITHHELD"
    assert result["candidate_segment_count"] == 0
    assert any(r.startswith("TEMPORAL_") for r in route["blocking_reasons"])
    assert result["training_authorized"] is False


def test_current_environment_detail_mismatch_blocks_preparation_without_altering_proofs(sources):
    clocks, entries = evidence_records(sources), declarations(sources)
    before = deepcopy((sources, clocks, entries))
    env = environment(sources)
    env["routes"][0]["segments"][1]["status"] = "TRUSTED"
    result = audit(
        sources,
        hr_timebase_snapshots=clocks,
        hr_acquisition_declarations=entries,
        trusted_environment=env,
    )
    assert result["candidate_segment_count"] == 0
    assert result["export_timebase_verified_route_count"] == 1
    route = result["routes"][0]
    assert "ENVIRONMENT_SEGMENT_SOURCE_MISMATCH" in route["blocking_reasons"]
    assert route["input_diagnostics"]["environment_detail_binding_verified"] is False
    assert all(
        s["existing_preparation_candidate"] is False
        for s in route["input_diagnostics"]["segment_details"]["items"]
    )
    assert (sources, clocks, entries) == before


def test_summary_keeps_bounded_causes_and_run_context_without_label_arrays(sources):
    result = audit(sources, trusted_environment=environment(sources))
    summary = build_training_data_readiness_audit_summary(result)
    route = summary["routes"][0]
    assert "segments" not in route
    assert route["input_diagnostics"]["environment_detail_binding_verified"] is True
    assert route["temporal_context"]["sequence_count"] == 1
    assert route["temporal_context"]["sequences"]["items"][0]["segment_count"] == 2
    assert summary["session_group_key"] == result["session_group_key"]
    assert summary["decision_hash"] == result["decision_hash"]
    assert "values" not in str(summary)
    assert (
        summary["hr_response_temporal_policy"]["history_and_target_windows_must_share_split"]
        is True
    )


@pytest.mark.asyncio
async def test_inspection_passes_full_environment_and_source_selection_without_writes(
    monkeypatch, sources
):
    source, route, sample = sources
    db = SimpleNamespace(
        scalar=AsyncMock(return_value=SimpleNamespace(scopes=["training_sessions:read"]))
    )
    monkeypatch.setattr(
        polar, "get_or_create_demo_user", AsyncMock(return_value=SimpleNamespace(id="athlete-1"))
    )
    monkeypatch.setattr(polar, "get_valid_access_token", AsyncMock(return_value="token"))
    client = SimpleNamespace(
        list_training_sessions=AsyncMock(
            side_effect=[
                {"trainingSessions": [route]},
                {"trainingSessions": [sample]},
            ]
        )
    )
    monkeypatch.setattr(polar, "PolarClient", lambda: client)
    clocks = evidence_records(sources)
    entries = declarations(sources)
    monkeypatch.setattr(polar, "load_current_hr_timebase_snapshots", AsyncMock(return_value=clocks))
    monkeypatch.setattr(
        polar, "load_current_hr_acquisition_declarations", AsyncMock(return_value=entries)
    )
    env = environment(sources)
    monkeypatch.setattr(
        polar, "build_trusted_route_environment_context", lambda *args, **kwargs: env
    )
    monkeypatch.setattr(
        polar, "build_route_expected_response_input", lambda *args, **kwargs: source
    )
    monkeypatch.setattr(
        polar,
        "load_and_bind_athlete_state_scientific_views",
        AsyncMock(
            return_value={
                "status": "NOT_BOUND",
                "athlete_state_context": None,
            }
        ),
    )
    writes = AsyncMock(side_effect=AssertionError("Inspection must remain read-only"))
    monkeypatch.setattr(polar, "persist_route_environment_evidence", writes)
    original = deepcopy((sources, clocks, entries, env))
    old_hr = build_training_session_heart_rate_validation(
        sample, expected_session_external_id="session-1", sample_session_match_count=1
    )
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
    session = result["route_sessions"][0]
    actual = session["training_data_readiness_audit"]
    assert actual["audit_version"] == "0.5.0"
    assert actual["routes"][0]["input_diagnostics"]["environment_detail_binding_verified"] is True
    assert set(actual["routes"][0]["input_diagnostics"]["component_source_selection"].values()) == {
        "NOT_SELECTED"
    }
    assert actual["routes"][0]["temporal_context"]["sequence_count"] == 1
    assert actual["export_timebase_verified_route_count"] == 1
    assert session["heart_rate_sample_validation"] == old_hr
    assert (
        actual["routes"][0]["input_diagnostics"]["owner_bound_audit_source_hash"]
        == actual["input_provenance"]["source_hash"]
    )
    assert actual["training_authorized"] is actual["numeric_output_authorized"] is False
    assert (sources, clocks, entries, env) == original
    writes.assert_not_awaited()
    assert not hasattr(db, "commit")
