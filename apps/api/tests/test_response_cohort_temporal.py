import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from app.services import response_cohort_temporal as module
from app.services.response_cohort_temporal import (
    SUPPORTED_INTERVAL,
    TemporalMetadataError,
    audit_cohort_temporal_metadata,
    build_session_temporal_evidence,
    declared_utc,
)


def source_pair(day=1, *, identifier=None):
    base = datetime(2026, 10, day, 17, tzinfo=UTC).replace(
        tzinfo=None
    )  # explicit provider local clock fixture
    start, stop = base.isoformat(), (base + timedelta(hours=1)).isoformat()
    exercise = {
        "identifier": {"id": identifier or f"exercise-{day}"},
        "startTime": start,
        "stopTime": stop,
        "timezoneOffsetMinutes": 120,
        "durationMillis": 3600000,
        "sport": {"id": "42"},
    }
    route = {
        "identifier": {"id": f"session-{day}"},
        "startTime": start,
        "stopTime": stop,
        "timezoneOffsetMinutes": 120,
        "durationMillis": 3600000,
        "exercises": [deepcopy(exercise)],
    }
    sample = deepcopy(route)
    route["exercises"][0]["routes"] = {"waypoints": [{"elapsed": 0, "lat": day}]}
    sample["exercises"][0]["samples"] = {
        "samples": [{"type": "HEART_RATE", "intervalMillis": 1000, "values": [110 + day, 115]}]
    }
    return route, sample


def member(day, split=None):
    return {
        "temporal_evidence": build_session_temporal_evidence(*source_pair(day)),
        "requested_split": {"split": split},
    }


@pytest.mark.parametrize(
    "value,offset,expected",
    [
        ("2026-10-01T00:00:00", 120, "2026-09-30T22:00:00+00:00"),
        ("2026-10-01T00:00:00", -300, "2026-10-01T05:00:00+00:00"),
        ("2026-10-01T00:00:00.123456+02:00", 120, "2026-09-30T22:00:00.123456+00:00"),
        ("2026-10-01T00:00:00Z", 0, "2026-10-01T00:00:00+00:00"),
        ("2026-10-01T00:00:00+14:00", 840, "2026-09-30T10:00:00+00:00"),
        ("2026-10-01T00:00:00-14:00", -840, "2026-10-01T14:00:00+00:00"),
    ],
)
def test_declared_utc_is_explicit_and_exact(value, offset, expected):
    assert declared_utc(value, offset).isoformat() == expected


@pytest.mark.parametrize(
    "value",
    [
        "2026-10-01",
        "2026-10-01 10:00:00",
        "2026-W40-4T10:00:00Z",
        "2026-10-01T10:00",
        "2026-10-01T10:00:00.1234567Z",
        "2026-10-01T10:00:00+00:00:30",
        "2026-02-30T10:00:00Z",
        "2026-10-01T24:00:00Z",
        "2026-10-01T10:00:00+14:01",
        "2026-10-01T10:00:00+00:60",
        "2026-10-01T10:00:00-00:00",
        "0001-01-01T00:00:00+14:00",
        None,
        True,
    ],
)
def test_ambiguous_or_invalid_calendar_times_never_use_host_clock(value):
    with pytest.raises(TemporalMetadataError):
        declared_utc(value)


@pytest.mark.parametrize("offset", [True, False, None, "120", 120.0, 841, -841])
def test_offset_requires_bounded_integer_even_with_aware_timestamp(offset):
    with pytest.raises(TemporalMetadataError):
        declared_utc("2026-10-01T10:00:00Z", offset)


def test_explicit_offset_conflict_is_not_silently_ignored():
    with pytest.raises(TemporalMetadataError, match="OFFSET_CONFLICT"):
        declared_utc("2026-10-01T10:00:00Z", 120)
    with pytest.raises(TemporalMetadataError, match="UNRESOLVED"):
        declared_utc("2026-10-01T10:00:00")
    assert declared_utc("2026-10-01T10:00:00", fallback=120).hour == 8


def test_equivalent_utc_representation_and_parent_fallback_match_without_mutation():
    route, sample = source_pair()
    before = deepcopy(route)
    for obj in (sample, sample["exercises"][0]):
        for field in ("startTime", "stopTime"):
            obj[field] = declared_utc(obj[field], 120).isoformat()
        obj["timezoneOffsetMinutes"] = 0
    route["exercises"][0].pop("timezoneOffsetMinutes")
    value = build_session_temporal_evidence(route, sample)
    assert value["session_interval_status"] == SUPPORTED_INTERVAL
    assert value["start_utc"] == "2026-10-01T15:00:00.000000Z"
    assert before["exercises"][0]["timezoneOffsetMinutes"] == 120
    assert route["startTime"] == before["startTime"]


def test_header_bounds_include_unrouted_exercise_and_duration_does_not_shorten_them():
    route, sample = source_pair()
    for obj in (route, sample):
        late = {
            "identifier": {"id": "unrouted"},
            "sport": {"id": "99"},
            "startTime": "2026-10-01T18:05:00",
            "stopTime": "2026-10-01T18:30:00",
        }
        obj["exercises"].append(late)
        obj["stopTime"] = "2026-10-01T18:35:00"
    value = build_session_temporal_evidence(route, sample)
    assert value["session_interval_status"] == SUPPORTED_INTERVAL
    assert value["published_exercise_count"] == 2
    assert value["stop_utc"] == "2026-10-01T16:35:00.000000Z"
    assert value["session_wall_clock_minus_duration_us"]["routes"] == 2100000000
    assert value["stop_inferred_from_duration"] is False


@pytest.mark.parametrize(
    "target", ["route_header", "sample_header", "route_exercise", "sample_exercise"]
)
@pytest.mark.parametrize("field", ["startTime", "stopTime"])
def test_missing_explicit_boundary_is_withheld_even_with_duration(target, field):
    route, sample = source_pair()
    obj = route if target.startswith("route") else sample
    if target.endswith("exercise"):
        obj = obj["exercises"][0]
    obj.pop(field)
    result = build_session_temporal_evidence(route, sample)
    assert result["session_interval_status"] == "WITHHELD"
    assert result["exercises"] == [] and result["stop_utc"] is None
    assert result["blocking_reasons"] == ["COHORT_EXPLICIT_START_OR_STOP_MISSING"]


@pytest.mark.parametrize(
    "case,reason",
    [
        ("header_disagree", "COHORT_SESSION_TIME_METADATA_MISMATCH"),
        ("exercise_disagree", "COHORT_EXERCISE_TIME_METADATA_MISMATCH"),
        ("outside", "COHORT_EXERCISE_OUTSIDE_SESSION_INTERVAL"),
        ("zero", "COHORT_INTERVAL_NOT_POSITIVE"),
        ("negative", "COHORT_INTERVAL_NOT_POSITIVE"),
        ("membership", "COHORT_PUBLISHED_EXERCISE_SET_MISMATCH"),
        ("duplicate", "COHORT_EXERCISE_IDENTITY_AMBIGUOUS"),
        ("identity_type", "COHORT_EXERCISE_IDENTITY_INVALID"),
        ("empty", "COHORT_PUBLISHED_EXERCISE_SET_MISSING_OR_LIMIT"),
    ],
)
def test_disagreement_missing_membership_and_ambiguous_identity_fail_closed(case, reason):
    route, sample = source_pair()
    exercise = sample["exercises"][0]
    if case == "header_disagree":
        sample["stopTime"] = "2026-10-01T18:01:00"
    elif case == "exercise_disagree":
        exercise["stopTime"] = "2026-10-01T17:59:00"
    elif case == "outside":
        exercise["stopTime"] = "2026-10-01T18:01:00"
    elif case in {"zero", "negative"}:
        exercise["stopTime"] = "2026-10-01T17:00:00" if case == "zero" else "2026-10-01T16:00:00"
    elif case == "membership":
        exercise["identifier"]["id"] = "other"
    elif case == "duplicate":
        sample["exercises"].append(deepcopy(exercise))
    elif case == "identity_type":
        exercise["identifier"]["id"] = True
    else:
        sample["exercises"] = []
    result = build_session_temporal_evidence(route, sample)
    assert result["blocking_reasons"] == [reason]


def test_anonymous_identity_matches_reordered_full_exercise_sets():
    route, sample = source_pair()
    for obj in (route, sample):
        obj["exercises"][0].pop("identifier")
        other = deepcopy(obj["exercises"][0])
        other["sport"] = {"id": "99"}
        obj["exercises"].append(other)
    sample["exercises"].reverse()
    result = build_session_temporal_evidence(route, sample)
    assert result["session_interval_status"] == SUPPORTED_INTERVAL
    assert all(e["identity_basis"] == "METADATA" for e in result["exercises"])
    assert {e["sample_source_exercise_index"] for e in result["exercises"]} == {0, 1}


def test_unrouted_missing_stop_and_short_header_cannot_use_route_only_bounds():
    route, sample = source_pair()
    for obj in (route, sample):
        obj["exercises"].append({"startTime": "2026-10-01T18:00:00", "durationMillis": 10000})
    assert build_session_temporal_evidence(route, sample)["metadata_consistent"] is False
    for obj in (route, sample):
        obj["exercises"][-1]["stopTime"] = "2026-10-01T18:10:00"
    assert build_session_temporal_evidence(route, sample)["blocking_reasons"] == [
        "COHORT_EXERCISE_OUTSIDE_SESSION_INTERVAL"
    ]


def test_all_pairs_not_just_neighboring_starts_are_checked():
    members = [member(i) for i in (1, 2, 3)]
    members[0]["temporal_evidence"]["stop_utc"] = "2026-10-04T00:00:00.000000Z"
    result = audit_cohort_temporal_metadata(members)
    assert result["compared_interval_pair_count"] == 3
    assert [c["member_canonical_indices"] for c in result["interval_conflicts"]] == [[0, 1], [0, 2]]
    assert result["chronological_order_supported"] is False


@pytest.mark.parametrize("split", [None, "TRAIN", "TEST"])
@pytest.mark.parametrize("touch", [False, True])
def test_touching_and_overlapping_whole_sessions_fail_even_in_same_split(split, touch):
    members = [member(1, split), member(2, split)]
    members[1]["temporal_evidence"]["start_utc"] = (
        "2026-10-01T16:00:00.000000Z" if touch else "2026-10-01T15:30:00.000000Z"
    )
    result = audit_cohort_temporal_metadata(members)
    reason = "COHORT_SESSION_BOUNDARIES_TOUCH" if touch else "COHORT_SESSION_INTERVALS_OVERLAP"
    assert result["interval_conflicts"][0]["reason"] == reason
    assert result["chronological_split_supported"] is False


@pytest.mark.parametrize(
    "splits",
    [
        (None, None, None),
        ("TRAIN", None, "TEST"),
        ("TRAIN", "TRAIN", "TEST"),
        ("TEST", "VALIDATION", "TRAIN"),
        ("TRAIN", "TEST", "VALIDATION"),
    ],
)
def test_incomplete_empty_or_reversed_partitions_remain_evaluation_withheld(splits):
    result = audit_cohort_temporal_metadata([member(i, split) for i, split in enumerate(splits, 1)])
    assert result["chronological_order_supported"] is True
    assert result["chronological_split_supported"] is False
    assert result["split_blocking_reasons"]


def test_complete_split_keeps_identity_order_and_separate_time_refs():
    result = audit_cohort_temporal_metadata(
        [
            member(3, "TEST"),
            member(1, "TRAIN"),
            member(2, "VALIDATION"),
        ]
    )
    assert result["chronological_order_supported"] is True
    assert result["chronological_split_supported"] is True
    assert result["ordered_member_canonical_indices"] == [1, 2, 0]
    assert result["source_verification_performed"] is False
    assert result["policy"]["statistical_independence_established"] is False
    assert result["policy"]["training_authorized"] is False
    assert result["policy"]["preprocessing_fit_scope_required"] == "TRAIN_ONLY"


def test_partition_check_uses_last_train_end_not_last_train_start():
    members = [member(1, "TRAIN"), member(2, "TRAIN"), member(3, "VALIDATION"), member(4, "TEST")]
    members[0]["temporal_evidence"]["stop_utc"] = "2026-10-03T16:30:00.000000Z"
    result = audit_cohort_temporal_metadata(members)
    assert "COHORT_TRAIN_NOT_STRICTLY_BEFORE_VALIDATION" in result["split_blocking_reasons"]


def test_single_session_and_unknown_interval_do_not_prove_relative_order():
    result = audit_cohort_temporal_metadata([member(1)])
    assert result["status"] == "SINGLE_SESSION_TIME_BOUNDS_ONLY"
    assert result["supported_interval_count"] == 1 and not result["chronological_order_supported"]
    members = [member(1), member(2)]
    members[1]["temporal_evidence"] = build_session_temporal_evidence({}, {})
    result = audit_cohort_temporal_metadata(members)
    assert result["status"] == "WITHHELD"
    assert result["unsupported_member_canonical_indices"] == [1]
    assert result["ordered_member_canonical_indices"] == []
    assert result["duplicate_check_complete_for_supported_members"] is False


@pytest.mark.parametrize(
    "case,reason",
    [
        ("identifier", "COHORT_PROVIDER_EXERCISE_ID_REUSED"),
        ("features", "COHORT_EXACT_FEATURE_CONTENT_REUSED"),
        ("hr_only", "COHORT_EXACT_HR_SEQUENCE_REUSED"),
    ],
)
def test_shifted_or_renamed_reimports_flag_possible_copy_without_deleting(case, reason):
    first_route, first_sample = source_pair(1)
    route, sample = source_pair(2)
    if case == "identifier":
        for obj in (route, sample):
            obj["exercises"][0]["identifier"] = first_route["exercises"][0]["identifier"]
    else:
        sample["exercises"][0]["samples"] = deepcopy(first_sample["exercises"][0]["samples"])
        if case == "features":
            route["exercises"][0]["routes"] = deepcopy(first_route["exercises"][0]["routes"])
    members = [
        {
            "temporal_evidence": build_session_temporal_evidence(*pair),
            "requested_split": {"split": None},
        }
        for pair in ((first_route, first_sample), (route, sample))
    ]
    result = audit_cohort_temporal_metadata(members)
    assert reason in result["possible_duplicate_pairs"][0]["reasons"]
    assert result["chronological_order_supported"] is False
    assert len(members) == 2
    assert result["all_possible_duplicates_ruled_out"] is False
    assert "values" not in json.dumps(result)


def test_repeated_route_with_distinct_hr_is_not_exact_copy_and_empty_hr_is_not_copy():
    pairs = [source_pair(i) for i in (1, 2)]
    pairs[1][0]["exercises"][0]["routes"] = deepcopy(pairs[0][0]["exercises"][0]["routes"])
    members = [
        {
            "temporal_evidence": build_session_temporal_evidence(*p),
            "requested_split": {"split": None},
        }
        for p in pairs
    ]
    assert audit_cohort_temporal_metadata(members)["possible_duplicate_pairs"] == []
    for _, sample in pairs:
        sample["exercises"][0]["samples"]["samples"][0]["values"] = [0, None, -1]
    members = [
        {
            "temporal_evidence": build_session_temporal_evidence(*p),
            "requested_split": {"split": None},
        }
        for p in pairs
    ]
    assert not members[0]["temporal_evidence"]["exercises"][0]["hr_sequence_hashes"]


def test_metadata_and_authority_claims_do_not_create_source_verification():
    route, sample = source_pair()
    for obj in (route, sample):
        obj.update(source_evidence_verified=True, training_authorized=True, route_date="2000-01-01")
    evidence = build_session_temporal_evidence(route, sample)
    assert "source_evidence_verified" not in evidence and "training_authorized" not in evidence
    assert evidence["claim_scope"] == "DECLARED_WALL_CLOCK_METADATA_CONSISTENCY_ONLY"
    assert evidence["route_date_used_as_chronological_evidence"] is False


def test_temporal_limits_never_truncate_exercise_or_member_sets(monkeypatch):
    route, sample = source_pair()
    monkeypatch.setattr(module, "MAX_TEMPORAL_EXERCISES", 0)
    assert build_session_temporal_evidence(route, sample)["session_interval_status"] == "WITHHELD"
    monkeypatch.setattr(module, "MAX_TEMPORAL_EXERCISES", 256)
    with pytest.raises(TemporalMetadataError, match="MEMBER_LIMIT"):
        audit_cohort_temporal_metadata([member(1)] * 21)


def test_maximum_duplicate_pair_diagnostics_are_bounded_and_deterministic():
    members = [member(1) for _ in range(20)]
    result = audit_cohort_temporal_metadata(members)
    assert len(result["possible_duplicate_pairs"]) == len(result["interval_conflicts"]) == 190
    assert result == audit_cohort_temporal_metadata(members)
    assert len(json.dumps(result).encode()) < 100000


@pytest.mark.parametrize("field", ["sport", "durationMillis"])
def test_anonymous_membership_requires_complete_disambiguating_metadata(field):
    route, sample = source_pair()
    for obj in (route, sample):
        obj["exercises"][0].pop("identifier")
        obj["exercises"][0].pop(field)
    result = build_session_temporal_evidence(route, sample)
    assert result["blocking_reasons"] == ["COHORT_ANONYMOUS_EXERCISE_METADATA_INCOMPLETE"]


def test_pure_audit_rejects_unknown_split_even_if_all_three_known_splits_are_present():
    members = [member(1, "TRAIN"), member(2, "VALIDATION"), member(3, "TEST"), member(4, "BOGUS")]
    with pytest.raises(TemporalMetadataError, match="REQUESTED_SPLIT_INVALID"):
        audit_cohort_temporal_metadata(members)


@pytest.mark.parametrize("duration", [True, 3600000.0])
def test_metadata_agreement_does_not_use_python_boolean_or_float_integer_equality(duration):
    route, sample = source_pair()
    if duration is True:
        route["exercises"][0]["durationMillis"] = 1
    sample["exercises"][0]["durationMillis"] = duration
    result = build_session_temporal_evidence(route, sample)
    assert result["blocking_reasons"] == ["COHORT_EXERCISE_TIME_METADATA_MISMATCH"]
