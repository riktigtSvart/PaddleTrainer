import asyncio
import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from test_environment_replay_persistence import environment as _environment_fixture
from test_environment_replay_persistence import legacy_tables, save, scientific_state
from test_environment_replay_snapshot import capture_inputs
from test_hr_timebase_snapshot import record
from test_response_cohort_assembly import full_replay, withheld
from test_training_data_readiness_audit import sources as _sources_fixture

from app.models.entities import WorkoutSession
from app.services import response_cohort_assembly as module
from app.services import response_cohort_temporal as temporal
from app.services.environment_evidence_persistence import persist_route_environment_evidence
from app.services.environment_replay_snapshot import LINEAGE, canonical_hash
from app.services.hr_timebase_persistence import (
    load_current_hr_timebase_snapshots,
    persist_hr_timebase_snapshot,
)
from app.services.hr_timebase_snapshot import build_hr_timebase_snapshot
from app.services.tcx_heart_rate_timebase import build_tcx_heart_rate_timebase

environment = _environment_fixture


@pytest.fixture
def sources():
    expected, route, sample = _sources_fixture.__wrapped__()
    for obj in (route, sample):
        obj.update(
            startTime="2026-09-30T17:00:00",
            stopTime="2026-09-30T17:00:05",
            timezoneOffsetMinutes=120,
            durationMillis=4000,
        )
        obj["exercises"][0]["stopTime"] = "2026-09-30T17:00:04"
    return expected, route, sample


async def add_session(env, template, index, start):
    session_id = f"session-{index}"
    expected, route, sample = deepcopy(template)
    values = [110 + 10 * index + i for i in range(4)]
    local = start + timedelta(hours=2)
    for obj in (route, sample):
        obj["identifier"]["id"] = session_id
        obj["startTime"] = local.replace(tzinfo=None).isoformat()
        obj["stopTime"] = (local + timedelta(seconds=5)).replace(tzinfo=None).isoformat()
        exercise = obj["exercises"][0]
        exercise["identifier"]["id"] = f"exercise-{index}"
        exercise["startTime"] = obj["startTime"]
        exercise["stopTime"] = (local + timedelta(seconds=4)).replace(tzinfo=None).isoformat()
    sample["exercises"][0]["samples"]["samples"][0]["values"] = values
    points = "".join(
        f"<Trackpoint><Time>{(start + timedelta(seconds=i, milliseconds=500)).isoformat()}</Time>"
        f"<HeartRateBpm><Value>{value}</Value></HeartRateBpm></Trackpoint>"
        for i, value in enumerate(values)
    )
    xml = (
        '<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">'
        f'<Activities><Activity Sport="Other"><Id>{start.isoformat()}</Id>'
        f'<Lap StartTime="{start.isoformat()}"><TotalTimeSeconds>4</TotalTimeSeconds>'
        f"<Track>{points}</Track></Lap></Activity></Activities></TrainingCenterDatabase>"
    ).encode()
    verification = build_tcx_heart_rate_timebase(
        xml,
        sample,
        expected_session_external_id=session_id,
        sample_session_match_count=1,
    )
    clock = build_hr_timebase_snapshot(
        verification,
        sample,
        athlete_id=str(env.user.id),
        session_external_id=session_id,
        sample_session_match_count=1,
    )
    assert clock is not None, verification
    workout = WorkoutSession(
        id=uuid4(),
        user_id=env.user.id,
        external_provider="POLAR",
        external_id=session_id,
        started_at=start,
        created_at=datetime.now(UTC),
    )
    env.db.session.add(workout)
    env.db.session.commit()
    args = {
        "owner": env.user.id,
        "clocks": [record(clock)],
        "start": start,
        "session_external_id": session_id,
    }
    inputs = capture_inputs((expected, route, sample), **args)
    persisted = await persist_route_environment_evidence(
        env.db,
        user=env.user,
        workout_session=workout,
        evidence_record=inputs["evidence_record"],
    )
    inputs = capture_inputs(
        (expected, route, sample),
        evidence_id=UUID(persisted["evidence_set_id"]),
        **args,
    )
    await persist_hr_timebase_snapshot(
        env.db,
        verification,
        sample,
        athlete_id=str(env.user.id),
        session_external_id=session_id,
        sample_session_match_count=1,
    )
    inputs["hr_timebase_snapshots"] = await load_current_hr_timebase_snapshots(
        env.db,
        sample,
        athlete_id=str(env.user.id),
        session_external_id=session_id,
        sample_session_match_count=1,
    )
    for name, value in inputs["lineage"].items():
        if value is not None:
            env.db.session.execute(
                legacy_tables[name]
                .insert()
                .values(
                    id=uuid4(),
                    evidence_set_id=UUID(inputs["evidence_set_id"]),
                    **{LINEAGE[name][0]: value[LINEAGE[name][0]], "snapshot_json": value},
                )
            )
    env.db.session.commit()
    holder = SimpleNamespace(db=env.db, user=env.user, workout=workout, inputs=inputs)
    return holder, await save(holder)


def member_pins(holder, saved, package):
    return {
        "provider": "POLAR",
        "athlete_id": str(holder.user.id),
        "session_external_id": holder.inputs["session_external_id"],
        "route_date": holder.inputs["route_session"]["startTime"][:10],
        "replay_snapshot_id": saved["snapshot_id"],
        "expected_snapshot_hash": saved["snapshot_hash"],
        "expected_evidence_set_id": saved["evidence_set_id"],
        "expected_evidence_hash": saved["evidence_hash"],
        "expected_unassigned_replay_package_hash": package["package_hash"],
    }


@pytest.fixture
def chronological(environment, sources, monkeypatch):
    env = environment
    first = asyncio.run(save(env))
    # Identity order intentionally differs from chronological order: 1,3,2.
    second, two = asyncio.run(add_session(env, sources, 2, datetime(2026, 10, 2, 15, tzinfo=UTC)))
    third, three = asyncio.run(add_session(env, sources, 3, datetime(2026, 10, 1, 15, tzinfo=UTC)))
    env.holders, env.saved = [env, second, third], [first, two, three]
    env.packages = [full_replay(h, s) for h, s in zip(env.holders, env.saved)]
    env.request = {
        "schema_version": "0.1",
        "manifest_id": "source-bound-three-sessions",
        "members": [member_pins(h, s, p) for h, s, p in zip(env.holders, env.saved, env.packages)],
        "split_manifest": {
            "schema_version": "0.1",
            "manifest_id": "whole-session-splits",
            "assignments": [
                {
                    "provider": "POLAR",
                    "athlete_id": str(env.user.id),
                    "session_external_id": sid,
                    "split": split,
                }
                for sid, split in (
                    ("session-1", "TRAIN"),
                    ("session-3", "VALIDATION"),
                    ("session-2", "TEST"),
                )
            ],
        },
    }
    env.route_sources = [deepcopy(h.inputs["route_session"]) for h in env.holders]
    env.sample_sources = [deepcopy(h.inputs["sample_session"]) for h in env.holders]

    async def provider(*args, features):
        return {
            "trainingSessions": deepcopy(
                env.route_sources if features == ["routes"] else env.sample_sources
            )
        }

    env.provider, env.token = (
        AsyncMock(side_effect=provider),
        AsyncMock(return_value="secret-token"),
    )
    monkeypatch.setattr(module, "get_valid_access_token", env.token)
    monkeypatch.setattr(
        module, "PolarClient", lambda: SimpleNamespace(list_training_sessions=env.provider)
    )
    return env


def assemble(env, request=None):
    return asyncio.run(
        module.assemble_response_cohort(
            env.db,
            request or env.request,
            user_id=env.user.id,
            verify_chronology=True,
        )
    )


def refresh_header_snapshot(env, position):
    """Store a new legitimate source commitment, not a forged verifier flag."""
    holder = env.holders[position]
    holder.inputs["route_session"] = deepcopy(env.route_sources[position])
    holder.inputs["sample_session"] = deepcopy(env.sample_sources[position])
    sample = holder.inputs["sample_session"]
    exercise = sample["exercises"][0]
    start = temporal.declared_utc(exercise["startTime"], exercise["timezoneOffsetMinutes"])
    points = "".join(
        f"<Trackpoint><Time>{(start + timedelta(seconds=i, milliseconds=500)).isoformat()}</Time>"
        f"<HeartRateBpm><Value>{v}</Value></HeartRateBpm></Trackpoint>"
        for i, v in enumerate(exercise["samples"]["samples"][0]["values"])
    )
    xml = (
        '<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">'
        f'<Activities><Activity Sport="Other"><Id>{start.isoformat()}</Id>'
        f'<Lap StartTime="{start.isoformat()}"><TotalTimeSeconds>4</TotalTimeSeconds>'
        f"<Track>{points}</Track></Lap></Activity></Activities></TrainingCenterDatabase>"
    ).encode()
    verification = build_tcx_heart_rate_timebase(
        xml,
        sample,
        expected_session_external_id=holder.inputs["session_external_id"],
        sample_session_match_count=1,
    )
    asyncio.run(
        persist_hr_timebase_snapshot(
            env.db,
            verification,
            sample,
            athlete_id=str(env.user.id),
            session_external_id=holder.inputs["session_external_id"],
            sample_session_match_count=1,
        )
    )
    holder.inputs["hr_timebase_snapshots"] = asyncio.run(
        load_current_hr_timebase_snapshots(
            env.db,
            sample,
            athlete_id=str(env.user.id),
            session_external_id=holder.inputs["session_external_id"],
            sample_session_match_count=1,
        )
    )
    saved = asyncio.run(save(holder))
    package = full_replay(holder, saved)
    env.request["members"][position] = member_pins(holder, saved, package)


def test_actual_three_session_db_checks_bind_interval_order_and_complete_requested_split(
    chronological,
):
    before, commits = scientific_state(chronological), chronological.db.commit_count
    value, repeat = assemble(chronological), assemble(chronological)
    assert value["source_evidence_verified"] is True, value
    assert value == repeat and module.verify_cohort_index_integrity(value)
    assert value["chronological_cohort_order_verified"] is True
    assert value["chronological_split_verified"] is True
    assert value["temporal_audit"]["ordered_member_canonical_indices"] == [0, 2, 1]
    assert [m["session_external_id"] for m in value["members"]] == [
        "session-1",
        "session-2",
        "session-3",
    ]
    assert value["assembly_version"] == "0.2.0"
    assert value["split_assignment_persisted"] is False
    assert value["independence_between_sessions_verified"] is False
    assert value["training_authorized"] is value["numeric_output_authorized"] is False
    assert scientific_state(chronological) == before and chronological.db.commit_count == commits
    assert chronological.provider.await_count == 12
    assert value["environmental_provider_calls"] == value["science_storage_writes"] == 0
    for member in value["members"]:
        evidence = member["temporal_evidence"]
        assert evidence["temporal_evidence_hash"] == canonical_hash(
            {k: v for k, v in evidence.items() if k != "temporal_evidence_hash"}
        )
        assert evidence["binding_scope"].startswith("ACTUALLY_VERIFIED_CURRENT_POLAR")
    assert "secret-token" not in json.dumps(value)


def test_b_default_unchanged_and_c_does_not_change_unassigned_replay_or_requested_splits(
    chronological,
):
    original = asyncio.run(
        module.assemble_response_cohort(
            chronological.db,
            chronological.request,
            user_id=chronological.user.id,
        )
    )
    explicit_b = asyncio.run(
        module.assemble_response_cohort(
            chronological.db,
            chronological.request,
            user_id=chronological.user.id,
            verify_chronology=False,
        )
    )
    value = assemble(chronological)
    assert original == explicit_b and original["assembly_version"] == "0.1.0"
    assert "temporal_audit" not in original and "chronological_split_verified" not in original
    assert original["chronological_cohort_order_verified"] is False
    for first, new in zip(original["members"], value["members"]):
        assert first["unassigned_replay_package_hash"] == new["unassigned_replay_package_hash"]
        assert first["base_split_status"] == new["base_split_status"] == "UNASSIGNED"
        assert first["requested_split"] == new["requested_split"]


@pytest.mark.parametrize("case", ["unassigned", "partial", "empty", "reversed"])
def test_actual_source_proof_survives_incomplete_or_incorrect_request_split(chronological, case):
    request = deepcopy(chronological.request)
    if case == "unassigned":
        request["split_manifest"] = None
    elif case == "partial":
        request["split_manifest"]["assignments"].pop()
    elif case == "empty":
        request["split_manifest"]["assignments"][1]["split"] = "TRAIN"
    else:
        assignments = request["split_manifest"]["assignments"]
        assignments[0]["split"], assignments[-1]["split"] = (
            assignments[-1]["split"],
            assignments[0]["split"],
        )
    value = assemble(chronological, request)
    assert value["source_evidence_verified"] is value["chronological_cohort_order_verified"] is True
    assert value["chronological_split_verified"] is False
    assert value["temporal_audit"]["split_blocking_reasons"]


@pytest.mark.parametrize("case", ["missing", "disagreement"])
def test_committed_uncertain_headers_withhold_chronology_but_keep_complete_source_proof(
    chronological, case
):
    if case == "missing":
        chronological.route_sources[1].pop("stopTime")
    else:
        chronological.route_sources[1]["stopTime"] = "2026-10-02T17:00:06"
    refresh_header_snapshot(chronological, 1)
    value = assemble(chronological)
    assert value["source_evidence_verified"] is True, value
    assert value["verified_member_count"] == 3
    assert (
        value["chronological_cohort_order_verified"]
        is value["chronological_split_verified"]
        is False
    )
    assert value["temporal_audit"]["unsupported_member_canonical_indices"] == [1]
    assert value["members"][1]["temporal_evidence"]["session_interval_status"] == "WITHHELD"


def test_whole_header_overlap_cannot_hide_behind_short_routes(chronological):
    for source in (chronological.route_sources[0], chronological.sample_sources[0]):
        source["stopTime"] = "2026-10-01T17:00:03"
    refresh_header_snapshot(chronological, 0)
    value = assemble(chronological)
    assert value["source_evidence_verified"] is True, value
    assert value["chronological_cohort_order_verified"] is False
    assert value["temporal_audit"]["interval_conflicts"][0]["member_canonical_indices"] == [0, 2]
    assert (
        "COHORT_TRAIN_NOT_STRICTLY_BEFORE_VALIDATION"
        in value["temporal_audit"]["split_blocking_reasons"]
    )


@pytest.mark.parametrize("case", ["hr_copy", "reused_exercise_id"])
def test_actual_verified_reimport_like_sources_withhold_chronology_without_removing_member(
    chronological,
    case,
):
    if case == "hr_copy":
        chronological.sample_sources[1]["exercises"][0]["samples"] = deepcopy(
            chronological.sample_sources[0]["exercises"][0]["samples"]
        )
    else:
        for source in (chronological.route_sources[1], chronological.sample_sources[1]):
            source["exercises"][0]["identifier"]["id"] = "exercise-1"
    refresh_header_snapshot(chronological, 1)
    value = assemble(chronological)
    assert value["source_evidence_verified"] is True, value
    assert value["verified_member_count"] == 3
    assert value["chronological_cohort_order_verified"] is False
    assert value["chronological_split_verified"] is False
    assert value["temporal_audit"]["possible_duplicate_pairs"][0]["member_canonical_indices"] == [
        0,
        1,
    ]


def test_actual_single_session_bounds_are_supported_but_no_relative_order_or_split(chronological):
    request = deepcopy(chronological.request)
    request["members"] = request["members"][:1]
    request["split_manifest"] = None
    value = assemble(chronological, request)
    assert value["source_evidence_verified"] is True
    assert value["members"][0]["temporal_evidence"]["start_utc"] == "2026-09-30T15:00:00.000000Z"
    assert value["members"][0]["temporal_evidence"]["stop_utc"] == "2026-09-30T15:00:05.000000Z"
    assert value["temporal_audit"]["status"] == "SINGLE_SESSION_TIME_BOUNDS_ONLY"
    assert (
        value["chronological_cohort_order_verified"]
        is value["chronological_split_verified"]
        is False
    )


@pytest.mark.parametrize(
    "field", ["source_evidence_verified", "chronological_split_verified", "verify_chronology"]
)
def test_manifest_authority_cannot_select_trusted_verification(chronological, field):
    request = deepcopy(chronological.request)
    request[field] = True
    with pytest.raises(ValidationError):
        assemble(chronological, request)
    chronological.provider.assert_not_awaited()


def test_query_dates_cannot_supply_chronology_and_changed_header_must_match_snapshot(chronological):
    request = deepcopy(chronological.request)
    for member in request["members"]:
        member["route_date"] = "2000-01-01"
    result = assemble(chronological, request)  # mock responds; actual source timestamps prevail
    assert result["chronological_cohort_order_verified"] is True
    assert result["temporal_audit"]["ordered_member_canonical_indices"] == [0, 2, 1]
    chronological.route_sources[0]["stopTime"] = "2026-10-01T17:00:03"
    result = assemble(chronological)
    withheld(result, "COHORT_MEMBER_EVIDENCE_VERIFICATION_FAILED")
    assert result["upstream_reason"] == "REPLAY_CURRENT_POLAR_SOURCE_CHANGED"
    assert result["temporal_audit"] is None


def test_wrong_pin_still_preflights_and_does_not_emit_temporal_partial_proof(chronological):
    request = deepcopy(chronological.request)
    request["members"][-1]["expected_snapshot_hash"] = "f" * 64
    result = assemble(chronological, request)
    withheld(result, "COHORT_SNAPSHOT_PIN_MISMATCH")
    assert result["temporal_audit"] is None
    chronological.provider.assert_not_awaited()
    chronological.token.assert_not_awaited()


def test_exercise_limit_withholds_only_temporal_claim_and_preserves_source(
    chronological, monkeypatch
):
    monkeypatch.setattr(temporal, "MAX_TEMPORAL_EXERCISES", 0)
    result = assemble(chronological)
    assert result["source_evidence_verified"] is True
    assert result["chronological_cohort_order_verified"] is False
    assert result["temporal_audit"]["unsupported_member_canonical_indices"] == [0, 1, 2]


def test_c_index_and_time_budget_limits_withhold_all_source_proof(chronological, monkeypatch):
    monkeypatch.setattr(module, "MAX_INDEX_BYTES", 1)
    withheld(assemble(chronological), "COHORT_INDEX_SIZE_LIMIT")
    monkeypatch.setattr(module, "MAX_ASSEMBLY_SECONDS", 0)
    withheld(assemble(chronological), "COHORT_EXECUTION_TIME_LIMIT")


def test_unrouted_late_exercise_is_part_of_actual_source_bound_interval(chronological):
    for source in (chronological.route_sources[0], chronological.sample_sources[0]):
        source["stopTime"] = "2026-10-01T17:00:03"
        source["exercises"].append(
            {
                "identifier": {"id": "unrouted-late"},
                "startTime": "2026-10-01T16:55:00",
                "stopTime": "2026-10-01T17:00:03",
                "timezoneOffsetMinutes": 120,
                "sport": {"id": "99"},
                "durationMillis": 303000,
            }
        )
    refresh_header_snapshot(chronological, 0)
    value = assemble(chronological)
    assert value["source_evidence_verified"] is True, value
    assert value["members"][0]["counts"]["route_count"] == 1
    assert value["members"][0]["temporal_evidence"]["published_exercise_count"] == 2
    assert value["chronological_cohort_order_verified"] is False
    assert value["temporal_audit"]["interval_conflicts"][0]["member_canonical_indices"] == [0, 2]
