import asyncio
import json
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, delete, event, func, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from test_environment_replay_persistence import legacy_metadata, scientific_state
from test_polar_hr_acquisition_api import APIBridge
from test_response_cohort_chronology import chronological as _chronological
from test_response_cohort_chronology import environment as _environment
from test_response_cohort_chronology import sources as _sources

from app.db.base import Base
from app.models import EnvironmentReplaySnapshot, ResponseCohortMember, ResponseCohortRecord
from app.models.entities import (
    ExternalConnection,
    RouteEnvironmentEvidenceSet,
    RouteEnvironmentSegment,
    User,
    WorkoutSession,
)
from app.models.hr_timebase_snapshot import HeartRateTimebaseSnapshot
from app.services import response_cohort_persistence as persistence
from app.services.response_cohort_assembly import assemble_response_cohort
from app.services.response_cohort_storage_contract import build_cohort_record_payload

chronological, environment, sources = _chronological, _environment, _sources
OTHER = UUID(int=882)


class StorageBridge(APIBridge):
    @property
    def new(self):
        return self.session.new

    @property
    def dirty(self):
        return self.session.dirty

    @property
    def deleted(self):
        return self.session.deleted

    def in_transaction(self):
        return self.session.in_transaction()

    async def rollback(self):
        self.session.rollback()

    @asynccontextmanager
    async def begin(self):
        with self.session.begin():
            yield
        self.commit_count += 1


@pytest.fixture
def archived(chronological):
    """Real SQL transactions/FKs, actual assembler; only Polar/token sources are fixtures."""
    env, original_db = chronological, chronological.db
    original_user, original_workout = env.user, env.workout
    owner_id, workout_id = env.user.id, env.workout.id
    source_bind = original_db.session.get_bind()
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    legacy_metadata.create_all(engine)
    names = set(inspect(source_bind).get_table_names())
    with source_bind.connect() as source, engine.begin() as target:
        for table in [*Base.metadata.sorted_tables, *legacy_metadata.sorted_tables]:
            if table.name in names:
                rows = [dict(row) for row in source.execute(table.select()).mappings()]
                if rows:
                    target.execute(table.insert(), rows)
    with Session(engine, expire_on_commit=False) as sync:
        sync.add(
            User(id=OTHER, email="other-cohort-owner@example.test", created_at=datetime.now(UTC))
        )
        sync.commit()
        env.db = StorageBridge(sync)
        env.engine = engine
        env.user = SimpleNamespace(id=owner_id)
        env.workout = SimpleNamespace(id=workout_id)
        yield env
    env.db = original_db
    env.user, env.workout = original_user, original_workout
    engine.dispose()


def capture(env, request=None, owner=None):
    return asyncio.run(
        persistence.capture_response_cohort_record(
            env.db,
            request if request is not None else env.request,
            user_id=owner if owner is not None else env.user.id,
        )
    )


def read(env, record_id, owner=None):
    return asyncio.run(
        persistence.load_owned_response_cohort_record(
            env.db,
            record_id,
            user_id=owner if owner is not None else env.user.id,
        )
    )


def archive_state(env):
    state = {
        model.__tablename__: [
            {
                column.name: str(getattr(row, column.name))
                if isinstance(getattr(row, column.name), UUID)
                else getattr(row, column.name)
                for column in model.__table__.columns
            }
            for row in env.db.session.scalars(select(model)).all()
        ]
        for model in (ResponseCohortRecord, ResponseCohortMember)
    }
    env.db.session.rollback()
    return state


def counts(env):
    result = tuple(
        env.db.session.scalar(select(func.count()).select_from(model))
        for model in (ResponseCohortRecord, ResponseCohortMember)
    )
    env.db.session.rollback()
    return result


def no_proof(value, reason):
    assert value["status"] in {"WITHHELD", "REJECTED"}
    assert value["blocking_reasons"] == [reason], value
    assert value["record_id"] is value["record_hash"] is value["cohort_index_hash"] is None
    assert value["stored_member_count"] == 0
    for flag in (
        "round_trip_verified",
        "commit_acknowledged",
        "source_evidence_verified",
        "current_source_evidence_verified",
        "training_authorized",
        "numeric_output_authorized",
    ):
        assert value[flag] is False


@pytest.mark.parametrize("single", [False, True], ids=["three-session-split", "single-unassigned"])
def test_actual_capture_read_and_repeat_have_stable_identity_and_preserved_sources(
    archived, single
):
    env = archived
    if single:
        env.request = {**env.request, "members": env.request["members"][:1], "split_manifest": None}
    before = scientific_state(env)
    env.db.session.rollback()
    first, repeat = capture(env), capture(env)
    assert first["status"] == "CREATED" and repeat["status"] == "ALREADY_PRESENT", (first, repeat)
    assert (
        first["record_id"] == repeat["record_id"] and first["record_hash"] == repeat["record_hash"]
    )
    assert first["created_at"] == repeat["created_at"]
    members = len(env.request["members"])
    assert counts(env) == (1, members)
    assert first["cohort_storage_rows_written"] == 1 + members
    assert repeat["cohort_storage_rows_written"] == 0
    assert first["round_trip_verified"] is first["commit_acknowledged"] is True
    assert repeat["source_evidence_verified"] is repeat["current_source_evidence_verified"] is True
    assert first["split_request_archived"] is True
    assert first["dataset_split_assignment_persisted"] is first["training_authorized"] is False
    assert len(env.provider.await_args_list) == 4 * members
    calls = env.provider.await_count
    with Session(env.engine, expire_on_commit=False) as fresh:
        loaded = asyncio.run(
            persistence.load_owned_response_cohort_record(
                StorageBridge(fresh),
                first["record_id"],
                user_id=env.user.id,
            )
        )
        assert loaded["record_id"] == first["record_id"]
        payload = loaded["record_payload"]
        assert payload["record_hash"] == first["record_hash"]
        assert payload["cohort_index_hash"] == first["cohort_index_hash"]
        assert payload["cohort_index"]["split_assignment_persisted"] is False
        assert payload["cohort_index"]["source_evidence_verified"] is True
        assert payload["cohort_index"]["chronological_split_verified"] is not single
        assert (
            loaded["source_evidence_verified"]
            is loaded["current_source_evidence_verified"]
            is False
        )
        assert loaded["storage_writes"] == 0
        assert "secret-token" not in json.dumps(loaded)
    assert env.provider.await_count == calls
    assert scientific_state(env) == before


def test_request_order_reuses_original_record_but_explicit_label_change_creates_new_archive(
    archived,
):
    env = archived
    first = capture(env)
    original = archive_state(env)
    reordered = deepcopy(env.request)
    reordered["members"].reverse()
    reordered["split_manifest"]["assignments"].reverse()
    assert capture(env, reordered)["record_id"] == first["record_id"]
    changed = deepcopy(env.request)
    changed["split_manifest"]["manifest_id"] += "-explicit-new-request"
    second = capture(env, changed)
    assert second["status"] == "CREATED" and second["record_id"] != first["record_id"]
    assert second["record_hash"] != first["record_hash"]
    assert counts(env) == (2, 6)
    assert (
        archive_state(env)["response_cohort_records"][0] == original["response_cohort_records"][0]
    )


@pytest.mark.parametrize(
    "kind", ["candidate", "caller-authority", "bad-owner", "wrong-owner", "bad-pin"]
)
def test_caller_cannot_supply_local_proof_or_choose_another_owner(archived, kind):
    env = archived
    request = deepcopy(env.request)
    owner = env.user.id
    if kind == "candidate":
        index = asyncio.run(
            assemble_response_cohort(env.db, request, user_id=owner, verify_chronology=True)
        )
        request = build_cohort_record_payload(request, index, owner_id=owner)
        env.db.session.rollback()
    elif kind == "caller-authority":
        request["source_evidence_verified"] = True
    elif kind == "bad-owner":
        owner = "private-invalid-owner"
    elif kind == "wrong-owner":
        owner = OTHER
    else:
        request["members"][0]["expected_snapshot_hash"] = "f" * 64
    env.provider.reset_mock()
    result = capture(env, request, owner)
    reason = (
        "COHORT_STORAGE_REQUEST_INVALID"
        if kind in {"candidate", "caller-authority", "bad-owner"}
        else "COHORT_CURRENT_SOURCE_CHECK_FAILED"
    )
    no_proof(result, reason)
    assert counts(env) == (0, 0)
    assert env.provider.await_count == 0
    assert "private-invalid-owner" not in json.dumps(result)


@pytest.mark.parametrize("kind", ["route", "sample", "clock", "normalized", "scope", "connection"])
def test_repeat_rechecks_current_sources_and_never_falls_back_to_archive(archived, kind):
    env = archived
    first = capture(env)
    before = archive_state(env)
    if kind == "route":
        env.route_sources[0]["exercises"][0]["startTime"] = "2026-09-30T18:00:00.250"
    elif kind == "sample":
        env.sample_sources[0]["exercises"][0]["samples"]["samples"][0]["values"][0] += 9
    elif kind == "clock":
        env.db.session.execute(delete(HeartRateTimebaseSnapshot))
    elif kind == "normalized":
        env.db.session.scalar(select(RouteEnvironmentSegment)).headwind_component_mps = 999
    else:
        connection = env.db.session.scalar(
            select(ExternalConnection).where(ExternalConnection.user_id == env.user.id)
        )
        if kind == "scope":
            connection.scopes = []
        else:
            env.db.session.delete(connection)
    env.db.session.commit()
    result = capture(env)
    no_proof(result, "COHORT_CURRENT_SOURCE_CHECK_FAILED")
    assert archive_state(env) == before
    assert counts(env) == (1, 3)
    loaded = read(env, first["record_id"])
    assert loaded["source_evidence_verified"] is False


@pytest.mark.parametrize(
    "kind",
    [
        "workout-owner",
        "workout-external",
        "replay-owner",
        "evidence-owner",
        "snapshot-pin",
        "evidence-pin",
    ],
)
def test_storage_transaction_rechecks_actual_owned_links_after_assembly(
    archived, monkeypatch, kind
):
    env = archived
    actual_assembler = persistence.assemble_response_cohort

    async def changed_after_verified(*args, **kwargs):
        result = await actual_assembler(*args, **kwargs)
        if kind.startswith("workout"):
            row = env.db.session.get(WorkoutSession, env.workout.id)
            if kind == "workout-owner":
                row.user_id = OTHER
            else:
                row.external_id = "retargeted-session"
        elif kind.startswith("replay") or kind == "snapshot-pin":
            row = env.db.session.get(EnvironmentReplaySnapshot, UUID(env.saved[0]["snapshot_id"]))
            if kind == "replay-owner":
                row.user_id = OTHER
            else:
                row.snapshot_hash = "f" * 64
        else:
            row = env.db.session.get(
                RouteEnvironmentEvidenceSet, UUID(env.saved[0]["evidence_set_id"])
            )
            if kind == "evidence-owner":
                row.user_id = OTHER
            else:
                row.evidence_hash = "f" * 64
        env.db.session.commit()
        return result

    monkeypatch.setattr(persistence, "assemble_response_cohort", changed_after_verified)
    result = capture(env)
    no_proof(
        result,
        "COHORT_STORAGE_SOURCE_PIN_CHANGED"
        if kind.endswith("pin")
        else "COHORT_STORAGE_SOURCE_LINK_CHANGED",
    )
    assert counts(env) == (0, 0)


@pytest.mark.parametrize(
    "failure", ["after-record", "after-first-member", "after-all-members", "commit"]
)
def test_partial_writes_and_commit_failure_roll_back_complete_archive(
    archived, monkeypatch, failure
):
    env = archived
    before = scientific_state(env)
    env.db.session.rollback()
    original_flush = env.db.flush
    flush_count = 0

    async def failed_flush():
        nonlocal flush_count
        flush_count += 1
        if failure == "after-first-member" and flush_count == 2:
            row = next(row for row in env.db.new if isinstance(row, ResponseCohortMember))
            env.db.session.connection().execute(
                ResponseCohortMember.__table__.insert().values(
                    **{column.name: getattr(row, column.name) for column in row.__table__.columns},
                )
            )
            raise RuntimeError("private-database-url-and-token")
        await original_flush()
        if (failure == "after-record" and flush_count == 1) or (
            failure == "after-all-members" and flush_count == 2
        ):
            raise RuntimeError("private-database-url-and-token")

    monkeypatch.setattr(env.db, "flush", failed_flush)
    if failure == "commit":

        @asynccontextmanager
        async def failing_begin():
            with env.db.session.begin():
                yield
                raise RuntimeError("private-database-url-and-token")

        monkeypatch.setattr(env.db, "begin", failing_begin)
    result = capture(env)
    no_proof(result, "COHORT_STORAGE_DEPENDENCY_FAILURE")
    assert result["storage_attempted"] is True and result["database_record_persisted"] is None
    assert "private-database-url-and-token" not in json.dumps(result)
    assert counts(env) == (0, 0)
    assert scientific_state(env) == before


@pytest.mark.parametrize(
    "kind",
    [
        "record-hash",
        "hash-column",
        "index-hash",
        "schema",
        "task",
        "count",
        "payload",
        "missing-member",
        "retargeted-member",
    ],
)
def test_existing_corrupt_record_is_withheld_without_repair_or_replacement(archived, kind):
    env = archived
    first = capture(env)
    row = env.db.session.get(ResponseCohortRecord, UUID(first["record_id"]))
    if kind == "record-hash":
        # Keep lookup identity; corrupt the duplicated payload commitment instead.
        payload = deepcopy(row.record_json)
        payload["record_hash"] = "f" * 64
        row.record_json = payload
    elif kind == "hash-column":
        row.record_hash = "f" * 64
    elif kind == "index-hash":
        row.cohort_index_hash = "f" * 64
    elif kind == "schema":
        payload = deepcopy(row.record_json)
        payload["record_schema_version"] = "unknown"
        row.record_json = payload
    elif kind == "task":
        row.task = "invented-task"
    elif kind == "count":
        row.member_count = 2
    elif kind == "payload":
        payload = deepcopy(row.record_json)
        payload["training_authorized"] = True
        row.record_json = payload
    else:
        link = env.db.session.get(ResponseCohortMember, (row.id, 0))
        if kind == "missing-member":
            env.db.session.delete(link)
        else:
            link.session_external_id = "retargeted-session"
    env.db.session.commit()
    before = archive_state(env)
    result = capture(env)
    assert result["status"] == "WITHHELD", result
    assert result["blocking_reasons"][0].startswith("COHORT_STORED_")
    assert archive_state(env) == before
    with pytest.raises(persistence.CohortStorageError):
        read(env, first["record_id"])


def test_foreign_and_missing_read_and_delete_are_indistinguishable(archived):
    env = archived
    first = capture(env)
    assert read(env, first["record_id"], OTHER) is None
    assert read(env, uuid4()) is None
    env.db.session.rollback()
    for identity, owner in ((first["record_id"], OTHER), (uuid4(), env.user.id)):
        result = asyncio.run(
            persistence.delete_owned_response_cohort_record(env.db, identity, user_id=owner)
        )
        assert result == {"status": "NOT_FOUND", "database_record_deleted": False}
    assert counts(env) == (1, 3)


@pytest.mark.parametrize(
    "source",
    [WorkoutSession, EnvironmentReplaySnapshot, RouteEnvironmentEvidenceSet],
    ids=["workout", "replay", "evidence"],
)
def test_retained_archive_prevents_source_or_membership_orphaning(archived, source):
    env = archived
    capture(env)
    before = archive_state(env)
    with pytest.raises(IntegrityError):
        env.db.session.execute(delete(source).where(source.user_id == env.user.id))
        env.db.session.commit()
    env.db.session.rollback()
    assert archive_state(env) == before
    assert counts(env) == (1, 3)


def test_explicit_archive_deletion_cascades_members_retains_sources_and_releases_workout(archived):
    env = archived
    first = capture(env)
    before = scientific_state(env)
    env.db.session.rollback()
    assert asyncio.run(
        persistence.delete_owned_response_cohort_record(
            env.db,
            first["record_id"],
            user_id=env.user.id,
        )
    ) == {"status": "DELETED", "database_record_deleted": True}
    assert counts(env) == (0, 0)
    assert scientific_state(env) == before
    env.db.session.rollback()
    env.db.session.execute(delete(WorkoutSession).where(WorkoutSession.user_id == env.user.id))
    env.db.session.commit()


def test_explicit_owner_deletion_cascades_archives_and_sources_without_order_dependency(archived):
    env = archived
    capture(env)
    env.db.session.execute(delete(User).where(User.id == env.user.id))
    env.db.session.commit()
    assert counts(env) == (0, 0)
    assert env.db.session.get(User, OTHER) is not None
    for source in (WorkoutSession, EnvironmentReplaySnapshot, RouteEnvironmentEvidenceSet):
        assert env.db.session.scalar(select(func.count()).select_from(source)) == 0


@pytest.mark.parametrize("kind", ["read-transaction", "pending-orm", "core-write"])
def test_active_caller_work_is_rejected_without_commit_or_rollback(archived, kind):
    env = archived
    if kind == "read-transaction":
        env.db.session.execute(select(User))
    elif kind == "pending-orm":
        env.db.session.add(
            User(id=uuid4(), email="pending@example.test", created_at=datetime.now(UTC))
        )
    else:
        env.db.session.execute(
            User.__table__.insert().values(
                id=uuid4(), email="core@example.test", created_at=datetime.now(UTC)
            )
        )
    before_new = set(env.db.new)
    result = capture(env)
    no_proof(result, "COHORT_STORAGE_CLEAN_SESSION_REQUIRED")
    assert env.db.in_transaction() and set(env.db.new) == before_new
    assert env.provider.await_count == 0


@pytest.mark.parametrize("winner", ["complete", "incomplete", "none"])
def test_unique_race_can_only_resolve_to_complete_identical_committed_winner(
    archived, monkeypatch, winner
):
    env = archived
    index = asyncio.run(
        assemble_response_cohort(env.db, env.request, user_id=env.user.id, verify_chronology=True)
    )
    payload = build_cohort_record_payload(env.request, index, owner_id=env.user.id)
    env.db.session.rollback()
    winning_id = uuid4()
    actual_begin, actual_flush = env.db.begin, env.db.flush
    first_insert = True

    async def collide():
        nonlocal first_insert
        if first_insert:
            first_insert = False
            raise IntegrityError("insert", {}, RuntimeError("private-race-value"))
        await actual_flush()

    @asynccontextmanager
    async def competing_begin():
        try:
            async with actual_begin():
                yield
        except IntegrityError:
            if winner != "none":
                with Session(env.engine) as other:
                    other.add(
                        ResponseCohortRecord(
                            id=winning_id,
                            user_id=env.user.id,
                            member_count=3,
                            record_json=payload,
                            **{
                                field: payload[field]
                                for field in (
                                    "record_schema_version",
                                    "task",
                                    "request_manifest_hash",
                                    "cohort_index_hash",
                                    "record_hash",
                                )
                            },
                        )
                    )
                    other.flush()
                    for position, member in enumerate(payload["request_manifest"]["members"]):
                        if winner == "incomplete" and position == 2:
                            break
                        replay = other.get(
                            EnvironmentReplaySnapshot, UUID(member["replay_snapshot_id"])
                        )
                        other.add(
                            ResponseCohortMember(
                                record_id=winning_id,
                                canonical_index=position,
                                user_id=env.user.id,
                                workout_session_id=replay.workout_session_id,
                                replay_snapshot_id=replay.id,
                                evidence_set_id=replay.evidence_set_id,
                                provider=member["provider"],
                                session_external_id=member["session_external_id"],
                            )
                        )
                    other.commit()
            raise

    monkeypatch.setattr(env.db, "flush", collide)
    monkeypatch.setattr(env.db, "begin", competing_begin)
    result = capture(env)
    if winner == "complete":
        assert result["status"] == "ALREADY_PRESENT" and result["record_id"] == str(winning_id)
        assert result["cohort_storage_rows_written"] == 0
        assert counts(env) == (1, 3)
    else:
        no_proof(
            result,
            "COHORT_STORED_MEMBERSHIP_INVALID"
            if winner == "incomplete"
            else "COHORT_STORAGE_WRITE_CONFLICT",
        )
        assert counts(env) == ((1, 2) if winner == "incomplete" else (0, 0))
    assert "private-race-value" not in json.dumps(result)


def test_database_constraints_reject_duplicate_content_and_cross_owner_membership(archived):
    env = archived
    first = capture(env)
    row = env.db.session.get(ResponseCohortRecord, UUID(first["record_id"]))
    copied = {
        column.name: getattr(row, column.name)
        for column in row.__table__.columns
        if column.name != "id"
    }
    env.db.session.rollback()
    with pytest.raises(IntegrityError):
        env.db.session.add(ResponseCohortRecord(id=uuid4(), **copied))
        env.db.session.commit()
    env.db.session.rollback()
    link = env.db.session.get(ResponseCohortMember, (UUID(first["record_id"]), 0))
    link.user_id = OTHER
    with pytest.raises(IntegrityError):
        env.db.session.commit()
    env.db.session.rollback()
    assert counts(env) == (1, 3)


def test_serialized_database_readback_is_checked_before_commit(archived, monkeypatch):
    env = archived
    flush = env.db.flush
    calls = 0

    async def tampered_database():
        nonlocal calls
        await flush()
        calls += 1
        if calls == 1:
            row = env.db.session.scalar(select(ResponseCohortRecord))
            payload = deepcopy(row.record_json)
            payload["record_hash"] = "f" * 64
            env.db.session.execute(
                ResponseCohortRecord.__table__.update().values(record_json=payload)
            )

    monkeypatch.setattr(env.db, "flush", tampered_database)
    result = capture(env)
    no_proof(result, "COHORT_STORED_PAYLOAD_INVALID")
    assert counts(env) == (0, 0)


def test_capture_works_with_tables_created_by_actual_migration(archived, monkeypatch):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from test_response_cohort_migration import migration

    env = archived
    ResponseCohortMember.__table__.drop(env.engine)
    ResponseCohortRecord.__table__.drop(env.engine)
    module = migration()
    with env.engine.begin() as connection:
        monkeypatch.setattr(module, "op", Operations(MigrationContext.configure(connection)))
        module.upgrade()
    result = capture(env)
    assert result["status"] == "CREATED", result
    assert counts(env) == (1, 3)


@pytest.mark.parametrize("after_write", [False, True], ids=["lock-wait", "after-record-insert"])
def test_storage_timeout_rolls_back_and_never_issues_partial_proof(
    archived, monkeypatch, after_write
):
    env = archived
    monkeypatch.setattr(persistence, "MAX_STORAGE_SECONDS", 0.001)
    if after_write:
        original = env.db.flush

        async def slow_flush():
            await original()
            await asyncio.sleep(0.02)

        monkeypatch.setattr(env.db, "flush", slow_flush)
    else:
        original = env.db.execute

        async def slow_lock(statement):
            if str(statement).startswith("SELECT users.id"):
                await asyncio.sleep(0.02)
            return await original(statement)

        monkeypatch.setattr(env.db, "execute", slow_lock)
    result = capture(env)
    no_proof(result, "COHORT_STORAGE_TIME_LIMIT")
    assert result["storage_attempted"] is after_write
    assert counts(env) == (0, 0)


def test_cancellation_after_uncommitted_insert_leaves_no_archive(archived, monkeypatch):
    env = archived
    flush = env.db.flush

    async def cancelled_flush():
        await flush()
        raise asyncio.CancelledError

    monkeypatch.setattr(env.db, "flush", cancelled_flush)
    with pytest.raises(asyncio.CancelledError):
        capture(env)
    assert counts(env) == (0, 0)


def test_failure_of_later_source_member_does_not_archive_verified_prefix(archived):
    env = archived
    calls = 0

    async def later_member_failure(*args, features):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise RuntimeError("private-source-token-and-url")
        return {
            "trainingSessions": deepcopy(
                env.route_sources if features == ["routes"] else env.sample_sources
            )
        }

    env.provider.side_effect = later_member_failure
    result = capture(env)
    no_proof(result, "COHORT_CURRENT_SOURCE_CHECK_FAILED")
    assert result["failed_member_canonical_index"] == 1
    assert "private-source-token-and-url" not in json.dumps(result)
    assert counts(env) == (0, 0)


@pytest.mark.parametrize(
    "kind", ["index-negative", "index-too-large", "workout", "replay", "evidence", "record-owner"]
)
def test_database_rejects_invalid_positions_reused_sessions_and_owner_retargeting(archived, kind):
    env = archived
    result = capture(env)
    record_id = UUID(result["record_id"])
    if kind == "record-owner":
        env.db.session.get(ResponseCohortRecord, record_id).user_id = OTHER
    else:
        row = env.db.session.get(ResponseCohortMember, (record_id, 1))
        if kind.startswith("index"):
            row.canonical_index = -1 if kind == "index-negative" else 20
        else:
            first = env.db.session.get(ResponseCohortMember, (record_id, 0))
            field = {
                "workout": "workout_session_id",
                "replay": "replay_snapshot_id",
                "evidence": "evidence_set_id",
            }[kind]
            setattr(row, field, getattr(first, field))
    with pytest.raises(IntegrityError):
        env.db.session.commit()
    env.db.session.rollback()
    assert counts(env) == (1, 3)
