import json
from copy import deepcopy
from datetime import UTC, datetime

import pytest
from test_heart_rate_sample_validation import session as _session_fixture
from test_hr_acquisition_declarations import PAYLOAD
from test_hr_acquisition_declarations import record as declaration_record
from test_hr_timebase_readiness_audit import evidence_records
from test_hr_timebase_snapshot import record as clock_record
from test_tcx_heart_rate_timebase import xml_bytes
from test_training_data_readiness_audit import sources as _sources_fixture

from app.services import heart_rate_signal_diagnostics as module
from app.services.heart_rate_sample_validation import build_training_session_heart_rate_validation
from app.services.hr_acquisition_declarations import build_hr_acquisition_declaration
from app.services.hr_timebase_snapshot import (
    build_hr_timebase_snapshot,
    resolve_hr_timebase_snapshots,
)
from app.services.tcx_heart_rate_timebase import build_tcx_heart_rate_timebase

session = _session_fixture
sources = _sources_fixture


def diagnose(session, **kwargs):
    return module.build_training_session_hr_signal_diagnostics(
        session,
        athlete_id=kwargs.pop("athlete_id", "athlete-1"),
        session_external_id=kwargs.pop("session_external_id", "hr-session"),
        sample_session_match_count=kwargs.pop("sample_session_match_count", 1),
        **kwargs,
    )


def hr(session):
    return session["exercises"][0]["samples"]["samples"][0]


def sample_observations(session):
    return diagnose(session)["exercises"][0]["observations"]


def test_raw_diagnostics_preserve_source_and_validator_without_inventing_utc(session):
    before = deepcopy(session)
    validation = build_training_session_heart_rate_validation(
        session, expected_session_external_id="hr-session", sample_session_match_count=1
    )
    first, second = diagnose(session), diagnose(session)
    assert first == second and session == before
    assert first["input_provenance"]["raw_validation_decision_hash"] == validation["decision_hash"]
    assert (
        first["input_provenance"]["api_source_hash"]
        == validation["input_provenance"]["source_hash"]
    )
    assert first["verified_clock_exercise_count"] == 0
    entry = first["exercises"][0]
    assert entry["timebase"]["status"] == "NOMINAL_SAMPLE_GRID_ONLY"
    assert entry["timebase"]["first_sample_timestamp_utc"] is None
    for item in entry["observations"]["largest_adjacent_changes"]["items"]:
        assert item["first_sample_timestamp_utc"] is None
        assert item["first_sample_offset_from_exercise_start_us"] is None
        assert item["nominal_first_sample_offset_ms"] >= 0
    assert entry["acquisition_context"]["declared_sensor"] is None
    assert first["training_authorized"] is first["numeric_prediction_authorized"] is False
    assert first["acquisition_quality_verified"] is first["artifact_detector_validated"] is False
    json.dumps(first, allow_nan=False)


def test_diagnostic_decision_includes_owner_even_without_saved_evidence(session):
    first = diagnose(session, athlete_id="athlete-1")
    other = diagnose(session, athlete_id="athlete-2")
    assert first["input_provenance"]["source_provider"] == "POLAR"
    assert first["input_provenance"]["athlete_id"] == "athlete-1"
    assert other["input_provenance"]["athlete_id"] == "athlete-2"
    assert (
        first["input_provenance"]["api_source_hash"] == other["input_provenance"]["api_source_hash"]
    )
    assert first["decision_hash"] != other["decision_hash"]


def test_invalid_runs_and_patterns_are_localized_without_changes_across_gaps(session):
    hr(session)["values"] = [100, 100, 105, None, 0, -1, True, "bad", 110, 110, 110, 115, 110]
    before = deepcopy(session)
    result = diagnose(session)
    entry = result["exercises"][0]
    assert entry["status"] == "DIAGNOSTICS_WITH_TECHNICAL_ISSUES"
    assert entry["positive_finite_sample_count"] == 8
    assert entry["invalid_or_missing_sample_count"] == 5
    assert entry["adjacent_valid_pair_count"] == 6
    assert entry["observed_nonzero_change_pair_count"] == 3
    invalid = entry["observations"]["invalid_runs"]["items"]
    assert [(p["start_sample_index"], p["end_sample_index_exclusive"]) for p in invalid] == [(3, 8)]
    assert invalid[0]["category_counts"] == {
        "MISSING": 1,
        "ZERO": 1,
        "NEGATIVE": 1,
        "BOOLEAN": 1,
        "NON_NUMERIC": 1,
    }
    constants = entry["observations"]["constant_runs"]["items"]
    assert [(p["start_sample_index"], p["end_sample_index_exclusive"]) for p in constants] == [
        (8, 11),
        (0, 2),
    ]
    assert constants[0]["sample_span_ms"] == 2000
    assert constants[0]["nominal_slot_occupancy_ms"] == 3000
    changes = entry["observations"]["largest_adjacent_changes"]["items"]
    assert [p["end_sample_index_exclusive"] - 1 for p in changes] == [2, 11, 12]
    assert [p["signed_change_bpm"] for p in changes] == [5, 5, -5]
    assert session == before


@pytest.mark.parametrize(
    "recorded,expected",
    [
        ([None, None], [(0, 2)]),
        ([None, 100, None], [(0, 1), (2, 3)]),
        ([100], []),
        ([0, 0, 100, -1], [(0, 2), (3, 4)]),
    ],
)
def test_invalid_run_edge_positions(session, recorded, expected):
    hr(session)["values"] = recorded
    items = sample_observations(session)["invalid_runs"]["items"]
    assert [(p["start_sample_index"], p["end_sample_index_exclusive"]) for p in items] == expected


@pytest.mark.parametrize(
    "recorded,expected",
    [
        ([100, 100, 100], [(0, 3)]),
        ([100, 100, None, 100, 100], [(0, 2), (3, 5)]),
        ([100, 101], []),
        ([0, 0, 100], []),
        ([100, 100.0], [(0, 2)]),
        ([None, None], []),
    ],
)
def test_constant_patterns_require_two_adjacent_valid_equal_recordings(session, recorded, expected):
    hr(session)["values"] = recorded
    items = sample_observations(session)["constant_runs"]["items"]
    assert [(p["start_sample_index"], p["end_sample_index_exclusive"]) for p in items] == expected


def test_change_ranking_has_no_physiological_threshold_and_keeps_signed_direction(session):
    hr(session)["values"] = [100, 101, 120, 100, None, 160]
    result = diagnose(session, detail_limit=2)
    packet = result["exercises"][0]["observations"]["largest_adjacent_changes"]
    assert packet["total_count"] == 3 and packet["returned_count"] == 2
    assert packet["truncated"] is True
    assert [p["signed_change_bpm"] for p in packet["items"]] == [-20, 19]
    assert result["policy"]["change_threshold_configured"] is False
    assert result["policy"]["physiological_threshold_configured"] is False


def test_detail_limit_changes_only_presentation_and_its_decision_hash(session):
    hr(session)["values"] = [100, 100, 101, 101, None, 105, 105, None, 106]
    small, large = diagnose(session, detail_limit=1), diagnose(session, detail_limit=100)
    assert small["input_provenance"] == large["input_provenance"]
    assert small["decision_hash"] != large["decision_hash"]
    for kind in ("invalid_runs", "constant_runs", "largest_adjacent_changes"):
        a, b = [r["exercises"][0]["observations"][kind] for r in (small, large)]
        assert a["total_count"] == b["total_count"]
        assert a["returned_count"] == 1
        assert b["returned_count"] == b["total_count"]
    assert (
        small["exercises"][0]["positive_finite_sample_count"]
        == large["exercises"][0]["positive_finite_sample_count"]
    )


@pytest.mark.parametrize("limit", [0, -1, 101, True, 1.5, None, "25"])
def test_invalid_detail_limits_are_not_silently_used(session, limit):
    with pytest.raises(ValueError, match="limit"):
        diagnose(session, detail_limit=limit)


@pytest.mark.parametrize("interval", [0, -1, True, 1.5, None, 2**63])
def test_invalid_interval_keeps_indices_but_does_not_supply_time_or_change_rate(session, interval):
    hr(session)["intervalMillis"] = interval
    entry = diagnose(session)["exercises"][0]
    assert entry["interval_ms"] is None
    assert entry["technical_status"] == "TECHNICAL_ISSUES"
    for item in entry["observations"]["largest_adjacent_changes"]["items"]:
        assert item["nominal_first_sample_offset_ms"] is None
        assert item["absolute_change_bpm_per_nominal_second"] is None
        assert item["first_sample_timestamp_utc"] is None


@pytest.mark.parametrize("mode", ["WRONG_SESSION", "AMBIGUOUS", "MISSING_OWNER", "NON_CANONICAL"])
def test_unverifiable_sources_have_no_exercise_details(session, mode):
    kwargs = {}
    if mode == "WRONG_SESSION":
        kwargs["session_external_id"] = "other"
    elif mode == "AMBIGUOUS":
        kwargs["sample_session_match_count"] = 2
    elif mode == "MISSING_OWNER":
        kwargs["athlete_id"] = None
    else:
        hr(session)["values"][0] = float("nan")
    result = diagnose(session, **kwargs)
    assert result["status"] == "WITHHELD"
    assert result["source_binding_verified"] is result["available"] is False
    assert result["exercises"] == []
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("mode", ["NO_HR", "MULTIPLE_HR", "EMPTY", "MISSING_ID", "DUPLICATE_ID"])
def test_missing_ambiguous_or_empty_series_does_not_invent_observations(session, mode):
    if mode == "NO_HR":
        hr(session)["type"] = "SPEED"
    elif mode == "MULTIPLE_HR":
        session["exercises"][0]["samples"]["samples"].append(deepcopy(hr(session)))
    elif mode == "EMPTY":
        hr(session)["values"] = []
    elif mode == "MISSING_ID":
        session["exercises"][0].pop("identifier")
    else:
        session["exercises"].append(deepcopy(session["exercises"][0]))
    result = diagnose(session)
    assert result["available"] is False
    for entry in result["exercises"]:
        assert entry["timebase"]["time_mapping_available"] is False
        assert all(
            p["items"] == [] and p["assessed"] is False for p in entry["observations"].values()
        )


def test_unrecognized_series_metadata_retains_raw_validator_limitations(session):
    hr(session)["confidence"] = 0.99
    entry = diagnose(session)["exercises"][0]
    assert "UNRECOGNIZED_HR_SERIES_FIELDS_REQUIRE_REVIEW" in entry["technical_limitations"]
    assert entry["acquisition_quality_verified"] is False


@pytest.mark.parametrize("kind", ["SLOTS", "EXERCISES"])
def test_source_limits_are_checked_before_the_raw_validator(monkeypatch, session, kind):
    def fail(*args, **kwargs):
        raise AssertionError("oversized input reached the validator")

    monkeypatch.setattr(module, "build_training_session_heart_rate_validation", fail)
    if kind == "SLOTS":
        hr(session)["values"] = [100] * (module.MAX_DIAGNOSTIC_SLOTS + 1)
    else:
        session["exercises"] *= module.MAX_DIAGNOSTIC_EXERCISES + 1
    result = diagnose(session)
    assert result["blocking_reasons"] == ["HR_DIAGNOSTICS_SOURCE_LIMIT_EXCEEDED"]


def test_large_numeric_recordings_are_not_rounded_to_false_equal_pairs(session):
    base = 10**300
    hr(session)["values"] = [base, base + 1]
    entry = diagnose(session)["exercises"][0]
    assert entry["observations"]["constant_runs"]["total_count"] == 0
    assert entry["observations"]["largest_adjacent_changes"]["items"][0]["absolute_change_bpm"] == 1


def test_unrepresentable_change_rate_is_json_safe_without_a_plausibility_claim(session):
    hr(session).update(intervalMillis=1, values=[1, 1e308])
    result = diagnose(session)
    item = result["exercises"][0]["observations"]["largest_adjacent_changes"]["items"][0]
    assert item["absolute_change_bpm_per_nominal_second"] is None
    assert result["exercises"][0]["physiological_plausibility_status"] == "NOT_ASSESSED"
    json.dumps(result, allow_nan=False)


def test_verified_export_supplies_the_actual_sample_timestamps_and_scoped_offset(sources):
    clocks = evidence_records(sources, offset_ms=537)
    original = deepcopy((sources, clocks))
    result = diagnose(sources[2], session_external_id="session-1", hr_timebase_snapshots=clocks)
    entry = result["exercises"][0]
    assert result["verified_clock_exercise_count"] == 1
    assert entry["timebase"]["snapshot_id"] == clocks[0]["snapshot_id"]
    assert entry["timebase"]["first_sample_offset_from_api_exercise_start_us"] == 537000
    item = entry["observations"]["largest_adjacent_changes"]["items"][0]
    assert item["first_sample_timestamp_utc"] == "2026-09-30T15:00:00.537000+00:00"
    assert item["last_sample_offset_from_exercise_start_us"] == 1537000
    assert entry["timebase"]["native_clock_semantics_verified"] is False
    assert (sources, clocks) == original


@pytest.mark.parametrize("failure", ["OWNER", "SOURCE", "COLUMN", "CONFLICT"])
def test_wrong_owner_stale_corrupt_or_conflicting_clock_does_not_stamp_observations(
    sources, failure
):
    clocks = evidence_records(sources)
    if failure == "OWNER":
        clocks = evidence_records(sources, owner="other-athlete")
    elif failure == "SOURCE":
        sources[2]["modified"] = "changed"
    elif failure == "COLUMN":
        clocks[0]["column_identity"]["snapshot_hash"] = "0" * 64
    else:
        clocks += evidence_records(sources, offset_ms=501)
    result = diagnose(sources[2], session_external_id="session-1", hr_timebase_snapshots=clocks)
    assert result["verified_clock_exercise_count"] == 0
    for item in result["exercises"][0]["observations"]["largest_adjacent_changes"]["items"]:
        assert item["time_mapping_available"] is False
        assert item["first_sample_timestamp_utc"] is None


def test_a_clock_does_not_propagate_to_another_exercise(sources):
    other = deepcopy(sources[2]["exercises"][0])
    other["identifier"]["id"] = "another-exercise"
    other["samples"]["samples"][0]["values"] = [120, 125, 130, 135]
    sources[2]["exercises"].append(other)
    clocks = evidence_records(sources)
    result = diagnose(sources[2], session_external_id="session-1", hr_timebase_snapshots=clocks)
    assert [e["timebase"]["time_mapping_available"] for e in result["exercises"]] == [True, False]


def test_sensor_context_is_user_declared_and_cannot_supply_a_clock_or_quality(session):
    declaration = build_hr_acquisition_declaration(
        {**PAYLOAD, "reported_issue_codes": ["LOOSE_CONTACT"]},
        session,
        athlete_id="athlete-1",
        session_external_id="hr-session",
        sample_session_match_count=1,
    )
    result = diagnose(session, hr_acquisition_declarations=[declaration_record(declaration)])
    context = result["exercises"][0]["acquisition_context"]
    assert context["declaration_source"] == "USER_DECLARATION"
    assert context["reported_issue_codes"] == ["LOOSE_CONTACT"]
    assert context["acquisition_quality_verified"] is context["sensor_identity_verified"] is False
    assert result["verified_clock_exercise_count"] == 0


def windows(*pairs):
    return [
        {"order_index": i, "start_exercise_elapsed_ms": a, "end_exercise_elapsed_ms": b}
        for i, (a, b) in enumerate(pairs)
    ]


def segment_diagnostics(sources, clocks, requested):
    report = diagnose(sources[2], session_external_id="session-1", hr_timebase_snapshots=clocks)
    resolved = resolve_hr_timebase_snapshots(
        clocks,
        sources[2],
        athlete_id="athlete-1",
        session_external_id="session-1",
        sample_session_match_count=1,
    )
    return module.build_hr_segment_diagnostics(
        sources[2]["exercises"][0],
        report["exercises"][0],
        saved_clock=resolved["by_exercise"].get("exercise-1", {}),
        windows=requested,
    )


@pytest.mark.parametrize(
    "start,end,expected",
    [
        (0, 500, 0),
        (500, 1000, 1),
        (501, 1500, 0),
        (1500, 1501, 1),
        (0, 1500, 1),
        (500, 1501, 2),
        (3500, 4000, 1),
    ],
)
def test_window_mapping_obeys_exact_half_open_export_grid_boundaries(sources, start, end, expected):
    clocks = evidence_records(sources)
    result = segment_diagnostics(sources, clocks, windows((start, end)))[0]
    assert result["expected_grid_slot_count"] == result["positive_finite_sample_count"] == expected
    assert result["adjacent_valid_pair_count"] == max(0, expected - 1)
    assert result["observed_nonzero_change_pair_count"] == max(0, expected - 1)
    assert result["unrecorded_grid_slot_count"] == 0
    assert result["acquisition_quality_verified"] is False


@pytest.mark.parametrize(
    "pair", [(-1, 1000), (0, 4001), (1, 1), (1000, 0), (True, 1000), (0, 1000.5)]
)
def test_invalid_windows_are_not_mapped(sources, pair):
    clocks = evidence_records(sources)
    entry = segment_diagnostics(sources, clocks, windows(pair))[0]
    assert entry["status"] == "INVALID_WINDOW"
    assert entry["first_recorded_timestamp_utc"] is None
    assert entry["positive_finite_sample_count"] is None


def test_windows_without_proof_have_no_assumed_exercise_zero_positions(sources):
    entry = segment_diagnostics(sources, [], windows((0, 2000)))[0]
    assert entry["status"] == "TIMEBASE_NOT_VERIFIED"
    assert entry["expected_grid_slot_count"] is entry["first_grid_slot_index"] is None


def test_window_outside_the_recorded_grid_reports_unrecorded_slots(sources):
    sources[1]["exercises"][0]["durationMillis"] = 10000
    sources[2]["exercises"][0].update(durationMillis=10000, stopTime="2026-09-30T17:00:10")
    # Use the source's matching metadata and a short observed grid in a longer exercise.
    source = sources[2]
    export = build_tcx_heart_rate_timebase(
        xml_bytes(
            values=[110, 111, 112, 113], start=datetime(2026, 9, 30, 15, 0, 0, 250000, tzinfo=UTC)
        ),
        source,
        expected_session_external_id="session-1",
        sample_session_match_count=1,
    )
    snapshot = build_hr_timebase_snapshot(
        export,
        source,
        athlete_id="athlete-1",
        session_external_id="session-1",
        sample_session_match_count=1,
    )
    entries = segment_diagnostics(
        sources, [clock_record(snapshot)], windows((4000, 8000), (8000, 10000))
    )
    assert entries[0]["status"] == "PARTIAL_WITH_LIMITATIONS"
    assert entries[0]["positive_finite_sample_count"] == 2
    assert entries[0]["unrecorded_grid_slot_count"] == 2
    assert entries[1]["status"] == "NO_POSITIVE_FINITE_SAMPLES"


def export_records(sources, recorded, fraction_us):
    source = sources[2]
    source["exercises"][0].update(durationMillis=10000, stopTime="2026-09-30T17:00:10")
    source["exercises"][0]["samples"]["samples"][0]["values"] = recorded
    export = build_tcx_heart_rate_timebase(
        xml_bytes(values=recorded, start=datetime(2026, 9, 30, 15, 0, 0, fraction_us, tzinfo=UTC)),
        source,
        expected_session_external_id="session-1",
        sample_session_match_count=1,
    )
    snapshot = build_hr_timebase_snapshot(
        export,
        source,
        athlete_id="athlete-1",
        session_external_id="session-1",
        sample_session_match_count=1,
    )
    return [clock_record(snapshot)]


def test_submillisecond_export_origin_is_not_rounded_at_window_boundaries(sources):
    clocks = export_records(sources, [110, 111, 112, 113], 537123)
    report = diagnose(sources[2], session_external_id="session-1", hr_timebase_snapshots=clocks)
    entry = report["exercises"][0]
    assert entry["timebase"]["first_sample_offset_from_api_exercise_start_us"] == 2_537_123
    assert entry["timebase"]["first_sample_timestamp_utc"] == "2026-09-30T15:00:02.537123+00:00"
    entries = segment_diagnostics(
        sources, clocks, windows((0, 2537), (2537, 2538), (2538, 3537), (3537, 3538))
    )
    assert [entry["expected_grid_slot_count"] for entry in entries] == [0, 1, 0, 1]
    assert entries[1]["first_recorded_timestamp_utc"] == "2026-09-30T15:00:02.537123+00:00"


def test_window_pattern_counts_exclude_neighbor_pairs_crossing_window_boundaries(sources):
    clocks = export_records(sources, [110, 110, 112, 112], 250000)
    entries = segment_diagnostics(
        sources, clocks, windows((2250, 4250), (4250, 6250), (3250, 4250))
    )
    assert [entry["observed_constant_pair_count"] for entry in entries] == [1, 1, 0]
    assert [entry["observed_nonzero_change_pair_count"] for entry in entries] == [0, 0, 0]
    assert [entry["adjacent_valid_pair_count"] for entry in entries] == [1, 1, 0]
    assert [entry["positive_finite_sample_count"] for entry in entries] == [2, 2, 1]


def test_source_or_grid_changed_after_diagnosis_cannot_be_used_for_window_mapping(sources):
    clocks = evidence_records(sources)
    report = diagnose(sources[2], session_external_id="session-1", hr_timebase_snapshots=clocks)
    resolved = resolve_hr_timebase_snapshots(
        clocks,
        sources[2],
        athlete_id="athlete-1",
        session_external_id="session-1",
        sample_session_match_count=1,
    )
    changed = deepcopy(sources[2]["exercises"][0])
    changed["samples"]["samples"][0]["values"][0] = 90
    results = module.build_hr_segment_diagnostics(
        changed,
        report["exercises"][0],
        saved_clock=resolved["by_exercise"]["exercise-1"],
        windows=windows((0, 2000)),
    )
    assert results[0]["status"] == "SOURCE_NOT_APPLIED"
    bad_clock = deepcopy(resolved["by_exercise"]["exercise-1"])
    bad_clock["timebase"]["first_sample_offset_from_api_exercise_start_us"] += 1
    results = module.build_hr_segment_diagnostics(
        sources[2]["exercises"][0],
        report["exercises"][0],
        saved_clock=bad_clock,
        windows=windows((0, 2000)),
    )
    assert results[0]["status"] == "TIMEBASE_NOT_VERIFIED"
