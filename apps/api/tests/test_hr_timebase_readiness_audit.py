from copy import deepcopy
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from test_hr_timebase_snapshot import record
from test_training_data_readiness_audit import audit
from test_training_data_readiness_audit import sources as _sources_fixture

from app.api.routes import polar
from app.services.hr_timebase_snapshot import build_hr_timebase_snapshot
from app.services.tcx_heart_rate_timebase import build_tcx_heart_rate_timebase
from app.services.training_data_readiness_audit import (
    build_training_data_readiness_cohort_summary,
)

sources = _sources_fixture


def evidence_records(sources, *, offset_ms=500, owner="athlete-1"):
    source = sources[2]
    source["exercises"][0]["stopTime"] = "2026-09-30T17:00:04"
    points = "".join(
        "<Trackpoint>"
        f"<Time>2026-09-30T15:00:{i:02d}.{offset_ms:03d}Z</Time>"
        f"<HeartRateBpm><Value>{110 + i}</Value></HeartRateBpm>"
        "</Trackpoint>"
        for i in range(4)
    )
    xml = (
        '<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">'
        '<Activities><Activity Sport="Other"><Id>2026-09-30T15:00:00.250Z</Id>'
        '<Lap StartTime="2026-09-30T15:00:00.250Z"><TotalTimeSeconds>4</TotalTimeSeconds>'
        f"<Track>{points}</Track></Lap></Activity></Activities></TrainingCenterDatabase>"
    ).encode()
    verification = build_tcx_heart_rate_timebase(
        xml,
        source,
        expected_session_external_id="session-1",
        sample_session_match_count=1,
    )
    snapshot = build_hr_timebase_snapshot(
        verification,
        source,
        athlete_id=owner,
        session_external_id="session-1",
        sample_session_match_count=1,
    )
    return [record(snapshot)]


def test_verified_current_source_uses_export_origin_and_keeps_remaining_limits(sources):
    records = evidence_records(sources)
    before = deepcopy((sources, records))
    result = audit(sources, hr_timebase_snapshots=records)
    assert (sources, records) == before
    route = result["routes"][0]
    assert result["export_timebase_verified_route_count"] == 1
    assert route["hr_timebase"]["sample_grid_origin_us"] == 500000
    assert route["hr_timebase"]["snapshot_hash"] == records[0]["snapshot"]["snapshot_hash"]
    assert route["candidate_segment_count"] == 2
    assert "HR_SAMPLE_TIME_ORIGIN_NOT_VERIFIED" not in route["limitations"]
    assert "HR_ACQUISITION_QUALITY_NOT_ESTABLISHED" in route["limitations"]
    assert "HR_PAUSE_CLOCK_SEMANTICS_NOT_VERIFIED" in route["limitations"]
    assert result["training_authorized"] is result["numeric_output_authorized"] is False
    assert "sample_timestamps_utc" not in str(result)


@pytest.mark.parametrize(
    "start,end,expected",
    [
        (0, 500, 0),
        (500, 1000, 1),
        (501, 1500, 0),
        (1500, 1501, 1),
        (0, 1500, 1),
        (500, 1500, 1),
        (500, 1501, 2),
        (3500, 4000, 1),
    ],
)
def test_export_offset_respects_exact_half_open_segment_boundaries(sources, start, end, expected):
    records = evidence_records(sources)
    input_route = sources[0]["routes"][0]
    # This test isolates one coverage window. Sequence overlap/order is tested
    # separately by V24.7; the second fixture window must not overlap this one.
    input_route["segments"] = input_route["segments"][:1]
    for key in ("segment_count", "workload_segment_count", "aligned_usable_segment_count"):
        input_route[key] = 1
    segment = input_route["segments"][0]["external_workload"]
    segment.update(start_exercise_elapsed_ms=start, end_exercise_elapsed_ms=end)
    result = audit(sources, hr_timebase_snapshots=records)
    coverage = result["routes"][0]["segments"][0]
    assert coverage["expected_grid_slot_count"] == expected
    assert coverage["positive_finite_grid_sample_count"] == expected
    assert coverage["missing_or_invalid_grid_slot_count"] == 0
    assert coverage["candidate_for_data_preparation"] is bool(expected)


def test_absent_saved_proof_keeps_explicit_unverified_project_convention(sources):
    result = audit(sources)
    assert result["export_timebase_verified_route_count"] == 0
    assert result["hr_timebase_evidence"]["status"] == "NOT_PROVIDED"
    assert result["routes"][0]["hr_timebase"]["sample_grid_origin_us"] == 0
    assert "HR_SAMPLE_TIME_ORIGIN_NOT_VERIFIED" in result["limitations"]


def test_an_exercise_proof_does_not_become_a_session_wide_clock_offset(sources):
    for raw in sources[1:]:
        raw["exercises"][0]["stopTime"] = "2026-09-30T17:00:04"
        second = deepcopy(raw["exercises"][0])
        second["identifier"]["id"] = "exercise-2"
        if "samples" in second:
            second["samples"]["samples"][0]["values"] = [120, 121, 122, 123]
        raw["exercises"].append(second)
    second_route = deepcopy(sources[0]["routes"][0])
    second_route.update(route_index=1, exercise_index=1)
    sources[0]["routes"].append(second_route)
    records = evidence_records(sources)
    result = audit(sources, hr_timebase_snapshots=records)
    assert result["export_timebase_verified_route_count"] == 1
    assert [r["export_timebase_verified"] for r in result["routes"]] == [True, False]
    assert [r["hr_timebase"]["sample_grid_origin_us"] for r in result["routes"]] == [500000, 0]
    assert "HR_SAMPLE_TIME_ORIGIN_NOT_VERIFIED" in result["limitations"]


@pytest.mark.parametrize("failure", ["OWNER", "SOURCE", "COLUMN", "CONFLICT"])
def test_stale_wrong_owner_corrupt_and_conflicting_proofs_do_not_promote_candidates(
    sources, failure
):
    records = evidence_records(sources)
    if failure == "OWNER":
        records = evidence_records(sources, owner="another-athlete")
    elif failure == "SOURCE":
        sources[2]["modified"] = "2026-10-01T00:00:00Z"
    elif failure == "COLUMN":
        records[0]["column_identity"]["snapshot_hash"] = "0" * 64
    else:
        records += evidence_records(sources, offset_ms=501)
    result = audit(sources, hr_timebase_snapshots=records)
    assert result["export_timebase_verified_route_count"] == 0
    assert result["candidate_segment_count"] == 0
    assert "SAVED_HR_TIMEBASE_UNUSABLE" in result["routes"][0]["blocking_reasons"]
    assert "HR_SAMPLE_TIME_ORIGIN_NOT_VERIFIED" in result["limitations"]


@pytest.mark.parametrize("failure", ["NORMALIZED", "ROUTE_METADATA"])
def test_proof_cannot_bypass_normalization_or_route_exercise_matching(sources, failure):
    records = evidence_records(sources)
    kwargs = {}
    if failure == "NORMALIZED":
        from app.services.polar_training_samples import normalize_polar_training_samples

        normalized = normalize_polar_training_samples({"exerciseSamples": sources[2]["exercises"]})
        normalized["series"][0]["valid_sample_count"] = 999
        kwargs["normalized_samples"] = normalized
    else:
        sources[1]["exercises"][0]["durationMillis"] = 4001
    result = audit(sources, hr_timebase_snapshots=records, **kwargs)
    assert result["export_timebase_verified_route_count"] == 0
    assert result["candidate_segment_count"] == 0


def test_verified_clock_does_not_bypass_environment_or_model_boundary(sources):
    records = evidence_records(sources)
    sources[0]["routes"][0]["model_ready"] = False
    result = audit(sources, hr_timebase_snapshots=records)
    assert result["export_timebase_verified_route_count"] == 1
    assert result["candidate_segment_count"] == 0
    assert "UPSTREAM_MODEL_INPUT_NOT_READY" in result["routes"][0]["blocking_reasons"]


def test_cohort_uses_actual_limitations_and_does_not_assign_a_split(sources):
    verified = audit(sources, hr_timebase_snapshots=evidence_records(sources))
    cohort = build_training_data_readiness_cohort_summary([verified])
    assert "HR_SAMPLE_TIME_ORIGIN_NOT_VERIFIED" not in cohort["limitations"]
    assert cohort["split_status"] == "INSUFFICIENT_DISTINCT_SESSIONS"
    assert cohort["training_authorized"] is cohort["split_assigned"] is False
    mixed = build_training_data_readiness_cohort_summary([verified, audit(sources)])
    assert "HR_SAMPLE_TIME_ORIGIN_NOT_VERIFIED" in mixed["limitations"]


@pytest.mark.asyncio
async def test_existing_route_inspection_automatically_loads_saved_current_source_proof(
    monkeypatch, sources
):
    source, route, sample = sources
    records = evidence_records(sources)
    db = SimpleNamespace(
        scalar=AsyncMock(return_value=SimpleNamespace(scopes=["training_sessions:read"]))
    )
    monkeypatch.setattr(
        polar, "get_or_create_demo_user", AsyncMock(return_value=SimpleNamespace(id="athlete-1"))
    )
    monkeypatch.setattr(polar, "get_valid_access_token", AsyncMock(return_value="token"))

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
    loader = AsyncMock(return_value=records)
    monkeypatch.setattr(polar, "load_current_hr_timebase_snapshots", loader)
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
    audit_result = result["route_sessions"][0]["training_data_readiness_audit"]
    assert audit_result["export_timebase_verified_route_count"] == 1
    assert audit_result["routes"][0]["hr_timebase"]["sample_grid_origin_us"] == 500000
    assert "segments" not in audit_result["routes"][0]
    assert (
        result["route_sessions"][0]["route_expected_response_model"]["response_available"] is False
    )
