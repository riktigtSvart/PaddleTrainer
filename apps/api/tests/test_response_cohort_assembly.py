import asyncio
import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import select
from test_environment_replay_persistence import (
    environment as _environment_fixture,
)
from test_environment_replay_persistence import (
    legacy_tables,
    save,
    scientific_state,
)
from test_training_data_readiness_audit import sources as _sources_fixture

from app.models import EnvironmentReplaySnapshot, HeartRateTimebaseSnapshot
from app.models.entities import RouteEnvironmentEvidenceSet, RouteEnvironmentSegment, WorkoutSession
from app.schemas.response_cohort import ResponseCohortManifest
from app.services import response_cohort_assembly as module
from app.services.environment_evidence_persistence import (
    build_environment_persistence_plan,
    persist_route_environment_evidence,
)
from app.services.environment_replay_snapshot import (
    LINEAGE,
    canonical_hash,
    replay_environment_dataset,
)
from app.services.hr_timebase_persistence import (
    load_current_hr_timebase_snapshots,
    persist_hr_timebase_snapshot,
)
from app.services.hr_timebase_snapshot import build_hr_timebase_snapshot
from app.services.hydrology_trust_decision_snapshot import hydrology_trust_decision_snapshot_hash
from app.services.response_dataset_integrity import check_response_dataset_integrity
from app.services.tcx_heart_rate_timebase import build_tcx_heart_rate_timebase
from app.services.trusted_environment_context_snapshot import (
    build_trusted_route_environment_context_snapshot,
)

environment = _environment_fixture
sources = _sources_fixture


async def second_session(env):
    """Independent stored group with a distinct session id; chronology is deliberately unverified."""
    inputs = deepcopy(env.inputs)
    inputs["session_external_id"] = "session-2"
    for key in ("route_session", "sample_session"):
        inputs[key]["identifier"]["id"] = "session-2"
    inputs["evidence_record"]["session_external_id"] = "session-2"
    workout = WorkoutSession(
        id=uuid4(),
        user_id=env.user.id,
        external_provider="POLAR",
        external_id="session-2",
        started_at=env.workout.started_at,
        created_at=env.workout.created_at,
    )
    env.db.session.add(workout)
    env.db.session.commit()
    persisted = await persist_route_environment_evidence(
        env.db, user=env.user, workout_session=workout, evidence_record=inputs["evidence_record"]
    )
    inputs["evidence_set_id"] = persisted["evidence_set_id"]
    inputs["evidence_hash"] = build_environment_persistence_plan(inputs["evidence_record"])[
        "evidence_hash"
    ]
    trust = inputs["lineage"]["hydrology_trust"]
    trust["environment_evidence_set_id"] = inputs["evidence_set_id"]
    trust["environment_evidence_hash"] = inputs["evidence_hash"]
    trust["decision_hash"] = hydrology_trust_decision_snapshot_hash(trust)
    inputs["lineage"]["trusted_projection"] = build_trusted_route_environment_context_snapshot(
        environment_evidence_set_id=inputs["evidence_set_id"],
        environment_evidence_hash=inputs["evidence_hash"],
        route_water_environment_identity_snapshot=inputs["lineage"]["water_identity"],
        hydrology_trust_decision_snapshot=trust,
        trusted_route_environment_context=inputs["trusted_environment"],
    )
    points = "".join(
        f"<Trackpoint><Time>2026-09-30T15:00:{i:02d}.500Z</Time>"
        f"<HeartRateBpm><Value>{110 + i}</Value></HeartRateBpm></Trackpoint>"
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
        inputs["sample_session"],
        expected_session_external_id="session-2",
        sample_session_match_count=1,
    )
    clock = build_hr_timebase_snapshot(
        verification,
        inputs["sample_session"],
        athlete_id=str(env.user.id),
        session_external_id="session-2",
        sample_session_match_count=1,
    )
    assert clock is not None
    await persist_hr_timebase_snapshot(
        env.db,
        verification,
        inputs["sample_session"],
        athlete_id=str(env.user.id),
        session_external_id="session-2",
        sample_session_match_count=1,
    )
    inputs["hr_timebase_snapshots"] = await load_current_hr_timebase_snapshots(
        env.db,
        inputs["sample_session"],
        athlete_id=str(env.user.id),
        session_external_id="session-2",
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


def full_replay(holder, saved):
    dataset = replay_environment_dataset(
        holder.db.session.get(EnvironmentReplaySnapshot, UUID(saved["snapshot_id"])).snapshot_json,
        snapshot_id=saved["snapshot_id"],
        athlete_id=holder.user.id,
        session_external_id=holder.inputs["session_external_id"],
        route_session=holder.inputs["route_session"],
        sample_session=holder.inputs["sample_session"],
        clocks=holder.inputs["hr_timebase_snapshots"],
        declarations=holder.inputs["hr_acquisition_declarations"],
    )
    dataset["input_provenance"].update(
        database_environment_replay_verified=True, scope=module.VERIFIED_REPLAY_SCOPE
    )
    dataset["package_hash"] = canonical_hash(
        {k: v for k, v in dataset.items() if k != "package_hash"}
    )
    return dataset


@pytest.fixture
def cohort(environment, monkeypatch):
    env = environment
    first = asyncio.run(save(env))
    second, saved = asyncio.run(second_session(env))
    env.holders = [env, second]
    env.saved = [first, saved]
    env.packages = [full_replay(h, s) for h, s in zip(env.holders, env.saved)]
    env.manifest = ResponseCohortManifest.model_validate(
        {
            "schema_version": "0.1",
            "manifest_id": "sqlite-two-sessions",
            "members": [
                {
                    "provider": "POLAR",
                    "athlete_id": str(env.user.id),
                    "session_external_id": holder.inputs["session_external_id"],
                    "route_date": "2026-09-30",
                    "replay_snapshot_id": item["snapshot_id"],
                    "expected_snapshot_hash": item["snapshot_hash"],
                    "expected_evidence_set_id": item["evidence_set_id"],
                    "expected_evidence_hash": item["evidence_hash"],
                    "expected_unassigned_replay_package_hash": package["package_hash"],
                }
                for holder, item, package in zip(env.holders, env.saved, env.packages)
            ],
        }
    )
    env.route_sources = [deepcopy(h.inputs["route_session"]) for h in env.holders]
    env.sample_sources = [deepcopy(h.inputs["sample_session"]) for h in env.holders]

    async def provider(*args, features):
        return {
            "trainingSessions": deepcopy(
                env.route_sources if features == ["routes"] else env.sample_sources
            )
        }

    env.provider = AsyncMock(side_effect=provider)
    env.token = AsyncMock(return_value="private-test-token")
    monkeypatch.setattr(module, "get_valid_access_token", env.token)
    monkeypatch.setattr(
        module, "PolarClient", lambda: SimpleNamespace(list_training_sessions=env.provider)
    )
    return env


def assemble(env, manifest=None, **kwargs):
    return asyncio.run(
        module.assemble_response_cohort(
            env.db, manifest or env.manifest, user_id=kwargs.get("user_id", env.user.id)
        )
    )


def withheld(value, reason=None):
    assert value["status"] == "WITHHELD"
    assert value["source_evidence_verified"] is False
    assert value["members"] == [] and value["totals"] is None
    assert value["verified_member_count"] == 0 and value["cohort_index_hash"] is None
    assert value["training_authorized"] is value["numeric_output_authorized"] is False
    if reason:
        assert value["blocking_reasons"] == [reason]


def test_two_actual_db_groups_repeat_deterministically_without_science_writes(cohort):
    before, commits = scientific_state(cohort), cohort.db.commit_count
    first, repeat = assemble(cohort), assemble(cohort)
    assert first["status"] == "SOURCE_VERIFIED_COHORT_INDEX_WITH_LIMITATIONS", first
    assert first == repeat and module.verify_cohort_index_integrity(first)
    assert first["source_evidence_verified"] is True
    assert first["verified_member_count"] == first["requested_member_count"] == 2
    assert first["totals"]["observation_count"] == 4 and first["totals"]["hr_slot_count"] == 8
    assert first["requested_split_counts"] == {"UNASSIGNED": 2}
    assert (
        first["chronological_cohort_order_verified"] is False
    )  # even identical times/reimport-like data
    assert scientific_state(cohort) == before and cohort.db.commit_count == commits
    assert len(cohort.db.session.scalars(select(EnvironmentReplaySnapshot)).all()) == 2
    assert [c.kwargs["features"] for c in cohort.provider.await_args_list] == [
        ["routes"],
        ["samples"],
    ] * 4
    encoded = json.dumps(first)
    assert all(
        name not in encoded
        for name in ('"value_bpm"', '"workload_observation"', "private-test-token")
    )
    for member, package in zip(first["members"], cohort.packages):
        assert member["unassigned_replay_package_hash"] == package["package_hash"]
        assert member["history_summary"]["sequence_count"] == 1
        assert member["history_summary"]["pre_observation_censored_sequence_count"] == 1


def test_member_order_is_canonical_and_request_split_never_changes_base_package_pins(cohort):
    original = assemble(cohort)
    data = cohort.manifest.canonical_payload()
    data["members"].reverse()
    assert assemble(cohort, data) == original
    data["split_manifest"] = {
        "schema_version": "0.1",
        "manifest_id": "request-only",
        "assignments": [
            {
                "provider": "POLAR",
                "athlete_id": str(cohort.user.id),
                "session_external_id": "session-2",
                "split": "TEST",
            }
        ],
    }
    assigned = assemble(cohort, data)
    assert assigned["source_evidence_verified"] is True, assigned
    assert assigned["requested_split_counts"] == {"TEST": 1, "UNASSIGNED": 1}
    assert assigned["cohort_index_hash"] != original["cohort_index_hash"]
    assert [m["unassigned_replay_package_hash"] for m in assigned["members"]] == [
        m["unassigned_replay_package_hash"] for m in original["members"]
    ]
    assert all(m["base_split_status"] == "UNASSIGNED" for m in assigned["members"])
    assert (
        assigned["split_assignment_persisted"]
        is assigned["chronological_cohort_order_verified"]
        is False
    )


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("expected_snapshot_hash", "a" * 64, "COHORT_SNAPSHOT_PIN_MISMATCH"),
        ("expected_evidence_hash", "b" * 64, "COHORT_ENVIRONMENT_PIN_MISMATCH"),
        ("expected_evidence_set_id", str(UUID(int=404)), "COHORT_ENVIRONMENT_PIN_MISMATCH"),
        ("replay_snapshot_id", str(UUID(int=405)), "COHORT_SNAPSHOT_NOT_FOUND_OR_NOT_OWNED"),
    ],
)
def test_all_member_metadata_pins_preflight_before_any_polar_calls(cohort, field, value, reason):
    data = cohort.manifest.canonical_payload()
    data["members"][1][field] = value
    before = scientific_state(cohort)
    result = assemble(cohort, data)
    withheld(result, reason)
    assert result["failed_member_canonical_index"] == 1
    cohort.provider.assert_not_awaited()
    cohort.token.assert_not_awaited()
    assert scientific_state(cohort) == before


@pytest.mark.parametrize(
    "case", ["trusted_owner", "manifest_owner", "other_row_owner", "connection", "scope"]
)
def test_owner_connection_and_scope_cannot_be_selected_by_client(cohort, case):
    data = cohort.manifest.canonical_payload()
    kwargs = {}
    if case == "trusted_owner":
        kwargs["user_id"] = UUID(int=909)
    elif case == "manifest_owner":
        for member in data["members"]:
            member["athlete_id"] = str(UUID(int=909))
    elif case == "other_row_owner":
        row = cohort.db.session.get(EnvironmentReplaySnapshot, UUID(cohort.saved[1]["snapshot_id"]))
        row.user_id = UUID(int=909)
        cohort.db.session.commit()
    elif case == "connection":
        cohort.db.session.delete(cohort.connection)
        cohort.db.session.commit()
    else:
        cohort.connection.scopes = []
        cohort.db.session.commit()
    withheld(assemble(cohort, data, **kwargs))
    cohort.provider.assert_not_awaited()
    cohort.token.assert_not_awaited()


@pytest.mark.parametrize(
    "case,upstream",
    [
        ("route_source", "REPLAY_CURRENT_POLAR_SOURCE_CHANGED"),
        ("sample_source", "REPLAY_CURRENT_POLAR_SOURCE_CHANGED"),
        ("clock", "REPLAY_HR_PROOF_STATE_CHANGED"),
        ("weather_link", "REPLAY_DATABASE_MEASUREMENT_LINK_MISMATCH"),
        ("lineage", "REPLAY_DATABASE_LINEAGE_MISSING_OR_CHANGED"),
    ],
)
def test_one_bad_member_withholds_whole_cohort_and_never_returns_successful_prefix(
    cohort, case, upstream
):
    if case == "route_source":
        cohort.route_sources[1]["revision"] = "changed"
    elif case == "sample_source":
        cohort.sample_sources[1]["revision"] = "changed"
    elif case == "clock":
        row = cohort.db.session.scalar(
            select(HeartRateTimebaseSnapshot).where(
                HeartRateTimebaseSnapshot.session_external_id == "session-2"
            )
        )
        cohort.db.session.delete(row)
        cohort.db.session.commit()
    elif case == "weather_link":
        row = cohort.db.session.scalar(
            select(RouteEnvironmentSegment).where(
                RouteEnvironmentSegment.evidence_set_id == UUID(cohort.saved[1]["evidence_set_id"])
            )
        )
        row.weather_sample_id = uuid4()
        cohort.db.session.commit()
    else:
        source = legacy_tables["trusted_projection"]
        cohort.db.session.execute(
            source.delete().where(
                source.c.evidence_set_id == UUID(cohort.saved[1]["evidence_set_id"])
            )
        )
        cohort.db.session.commit()
    before, commits = scientific_state(cohort), cohort.db.commit_count
    result = assemble(cohort)
    withheld(result, "COHORT_MEMBER_EVIDENCE_VERIFICATION_FAILED")
    assert result["upstream_reason"] == upstream
    assert result["failed_member_canonical_index"] == 1
    assert scientific_state(cohort) == before and cohort.db.commit_count == commits


def test_historical_pinned_evidence_remains_valid_without_current_fallback(cohort):
    rows = cohort.db.session.scalars(select(RouteEnvironmentEvidenceSet)).all()
    for row in rows:
        row.is_current = False
    cohort.db.session.commit()
    assert assemble(cohort)["source_evidence_verified"] is True


@pytest.mark.parametrize("source", ["route", "sample"])
@pytest.mark.parametrize("case", ["missing", "duplicate", "malformed"])
def test_current_session_must_be_unique_and_well_formed(cohort, source, case):
    items = cohort.route_sources if source == "route" else cohort.sample_sources
    if case == "missing":
        items.pop(1)
    elif case == "duplicate":
        items.append(deepcopy(items[1]))
    else:
        cohort.provider.side_effect = None
        cohort.provider.return_value = {"trainingSessions": {"secret": "private"}}
    withheld(assemble(cohort))


def test_wrong_replay_hash_does_not_substitute_capture_hash_or_skip_bad_member(cohort):
    data = cohort.manifest.canonical_payload()
    row = cohort.db.session.get(EnvironmentReplaySnapshot, UUID(cohort.saved[1]["snapshot_id"]))
    data["members"][1]["expected_unassigned_replay_package_hash"] = row.snapshot_json[
        "unassigned_dataset_package_hash"
    ]
    withheld(assemble(cohort, data), "COHORT_REPLAY_PACKAGE_PIN_MISMATCH")


def test_forged_manifest_authority_is_rejected_before_dependencies(cohort):
    data = cohort.manifest.canonical_payload()
    data["source_evidence_verified"] = True
    with pytest.raises(ValidationError):
        assemble(cohort, data)
    cohort.provider.assert_not_awaited()


@pytest.mark.parametrize(
    "error",
    [
        RuntimeError("private token / secret database URL"),
        httpx.ConnectError("private token / secret database URL"),
        ValueError("private token / secret database URL"),
    ],
)
def test_dependency_failures_never_echo_private_exception_text(cohort, error):
    cohort.provider.side_effect = error
    result = assemble(cohort)
    withheld(result)
    assert "private" not in json.dumps(result) and "secret" not in json.dumps(result)


@pytest.mark.parametrize("limit", ["members", "time", "source", "index"])
def test_execution_limits_fail_closed_without_truncation(cohort, monkeypatch, limit):
    names = {
        "members": "MAX_EXECUTION_MEMBERS",
        "time": "MAX_ASSEMBLY_SECONDS",
        "source": "MAX_CURRENT_SESSION_BYTES",
        "index": "MAX_INDEX_BYTES",
    }
    monkeypatch.setattr(module, names[limit], 1 if limit == "members" else 0)
    withheld(assemble(cohort))
    if limit in {"members", "time"}:
        cohort.provider.assert_not_awaited()


def test_index_integrity_check_is_only_a_local_hash_check(cohort):
    result = assemble(cohort)
    result["totals"]["hr_slot_count"] += 1
    assert module.verify_cohort_index_integrity(result) is False
    result["cohort_index_hash"] = canonical_hash(
        {k: v for k, v in result.items() if k != "cohort_index_hash"}
    )
    assert module.verify_cohort_index_integrity(result) is False


def test_payload_internal_references_are_verified_even_if_tampered_payload_is_rehashed(
    cohort, monkeypatch
):
    original = module.replay_environment_dataset

    def changed(*args, **kwargs):
        dataset = original(*args, **kwargs)
        dataset["observations"][1]["history_ref"]["completed_end_order_index"] = 1
        return dataset

    monkeypatch.setattr(module, "replay_environment_dataset", changed)
    result = assemble(cohort)
    withheld(result, "COHORT_MEMBER_EVIDENCE_VERIFICATION_FAILED")
    assert result["upstream_reason"] == "DATASET_INTERNAL_REFERENCES_INVALID"


def test_full_replayed_packages_have_verifiable_internal_grid_and_history(cohort):
    for package in cohort.packages:
        assert check_response_dataset_integrity(package)["internal_references_verified"] is True


def test_builder_uses_exact_same_unassigned_replay_hash_as_existing_v24_9_api(cohort, monkeypatch):
    from datetime import date

    from app.api.routes import polar, polar_environment_replay

    monkeypatch.setattr(
        polar_environment_replay, "_owner", AsyncMock(return_value=(cohort.user, cohort.connection))
    )
    monkeypatch.setattr(polar, "get_valid_access_token", cohort.token)
    monkeypatch.setattr(
        polar_environment_replay,
        "PolarClient",
        lambda: SimpleNamespace(list_training_sessions=cohort.provider),
    )
    dataset = asyncio.run(
        polar_environment_replay.inspect_saved_environment_response_dataset(
            session_external_id="session-1",
            route_date=date(2026, 9, 30),
            db=cohort.db,
            request=polar_environment_replay.EnvironmentReplayRequest(
                replay_snapshot_id=cohort.saved[0]["snapshot_id"], include_payload=True
            ),
        )
    )
    index = assemble(cohort)
    assert dataset["package_hash"] == index["members"][0]["unassigned_replay_package_hash"]
    assert dataset == cohort.packages[0]


def test_real_execution_member_limit_precedes_all_db_provider_calls(cohort):
    data = cohort.manifest.canonical_payload()
    template = data["members"][0]
    data["members"] = [
        {
            **template,
            "session_external_id": f"selected-{i}",
            "replay_snapshot_id": str(UUID(int=500 + i)),
        }
        for i in range(21)
    ]
    result = assemble(cohort, data)
    withheld(result, "COHORT_MEMBER_EXECUTION_LIMIT")
    cohort.provider.assert_not_awaited()
    cohort.token.assert_not_awaited()


def test_awaited_provider_timeout_cannot_leave_a_partial_index(cohort, monkeypatch):
    async def waiting(*args, **kwargs):
        await asyncio.Event().wait()

    cohort.provider.side_effect = waiting
    monkeypatch.setattr(module, "MAX_ASSEMBLY_SECONDS", 0.2)
    result = assemble(cohort)
    withheld(result, "COHORT_EXECUTION_TIME_LIMIT")
    assert cohort.provider.await_count == 1
