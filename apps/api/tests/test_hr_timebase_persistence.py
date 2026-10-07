from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_tcx_heart_rate_timebase import session as _session_fixture
from test_tcx_heart_rate_timebase import verify

from app.models.entities import User
from app.models.hr_timebase_snapshot import HeartRateTimebaseSnapshot
from app.services import hr_timebase_persistence as persistence

session = _session_fixture

OWNER = UUID("00000000-0000-0000-0000-000000000101")
OTHER = UUID("00000000-0000-0000-0000-000000000102")


class AsyncSQLiteBridge:
    """Use real ORM SQL, JSON serialization and constraints without a remote DB."""

    def __init__(self, session):
        self.session = session
        self.commit_count = 0

    async def execute(self, statement):
        return self.session.execute(statement)

    def add(self, row):
        self.session.add(row)

    async def flush(self):
        self.session.flush()

    async def commit(self):
        self.session.commit()
        self.commit_count += 1

    @asynccontextmanager
    async def begin_nested(self):
        with self.session.begin_nested():
            yield


@pytest.fixture
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    User.__table__.create(engine)
    HeartRateTimebaseSnapshot.__table__.create(engine)
    with Session(engine, expire_on_commit=False) as sync:
        sync.add_all(
            [
                User(id=OWNER, email="first@example.test", created_at=datetime.now(UTC)),
                User(id=OTHER, email="second@example.test", created_at=datetime.now(UTC)),
            ]
        )
        sync.commit()
        yield AsyncSQLiteBridge(sync)
    engine.dispose()


async def save(db, source, *, owner=OWNER):
    return await persistence.persist_hr_timebase_snapshot(
        db,
        verify(source),
        source,
        athlete_id=str(owner),
        session_external_id="synthetic-session",
        sample_session_match_count=1,
    )


async def load(db, source, *, owner=OWNER, identity="synthetic-session", count=1):
    return await persistence.load_current_hr_timebase_snapshots(
        db,
        source,
        athlete_id=str(owner),
        session_external_id=identity,
        sample_session_match_count=count,
    )


@pytest.mark.asyncio
async def test_real_database_round_trip_is_immutable_and_idempotent(db, session):
    first = await save(db, session)
    second = await save(db, session)
    assert first["status"] == "CREATED"
    assert second["status"] == "ALREADY_PRESENT"
    assert first["snapshot_id"] == second["snapshot_id"]
    assert first["round_trip_verified"] is True
    assert db.commit_count == 1
    records = await load(db, session)
    assert len(records) == 1
    assert records[0]["snapshot"]["verification"]["timebase"]["sample_count"] == 4
    assert first["training_authorized"] is False


@pytest.mark.asyncio
async def test_lookup_is_scoped_to_owner_session_and_current_api_source(db, session):
    await save(db, session)
    assert await load(db, session, owner=OTHER) == []
    assert await load(db, session, identity="another-session") == []
    modified = deepcopy(session)
    modified["modified"] = "2025-01-11T00:00:00Z"
    assert await load(db, modified) == []
    assert await load(db, session, count=2) == []
    assert len(await load(db, session)) == 1


@pytest.mark.asyncio
async def test_same_export_can_be_stored_separately_for_different_owners(db, session):
    first = await save(db, session)
    second = await save(db, session, owner=OTHER)
    assert first["snapshot_id"] != second["snapshot_id"]
    assert first["snapshot_hash"] != second["snapshot_hash"]
    assert len(await load(db, session, owner=OTHER)) == 1


@pytest.mark.asyncio
async def test_changed_source_creates_new_lineage_without_overwriting_old(db, session):
    first = await save(db, session)
    changed = deepcopy(session)
    changed["exercises"][0]["durationMillis"] = 14999
    second = await save(db, changed)
    assert first["snapshot_id"] != second["snapshot_id"]
    assert first["snapshot_hash"] != second["snapshot_hash"]
    rows = db.session.scalars(select(HeartRateTimebaseSnapshot)).all()
    assert len(rows) == 2
    assert len(await load(db, session)) == len(await load(db, changed)) == 1


@pytest.mark.asyncio
async def test_bad_import_and_wrong_owner_format_do_not_write(db, session):
    with pytest.raises(ValueError):
        await persistence.persist_hr_timebase_snapshot(
            db,
            {"export_timebase_verified": True},
            session,
            athlete_id=str(OWNER),
            session_external_id="synthetic-session",
            sample_session_match_count=1,
        )
    with pytest.raises(ValueError):
        await save(db, session, owner="invalid-uuid")
    assert db.commit_count == 0
    assert db.session.scalars(select(HeartRateTimebaseSnapshot)).all() == []


@pytest.mark.asyncio
async def test_stored_corruption_is_not_reported_as_idempotent_success(db, session):
    await save(db, session)
    row = db.session.scalar(select(HeartRateTimebaseSnapshot))
    row.snapshot_json = {**row.snapshot_json, "athlete_id": str(OTHER)}
    db.session.commit()
    with pytest.raises(ValueError, match="round-trip"):
        await save(db, session)


@pytest.mark.asyncio
async def test_proof_is_durable_in_a_new_database_session_without_export(db, session):
    first = await save(db, session)
    with Session(db.session.get_bind(), expire_on_commit=False) as new_session:
        records = await load(AsyncSQLiteBridge(new_session), session)
        assert records[0]["snapshot_id"] == first["snapshot_id"]
        assert records[0]["snapshot"]["snapshot_hash"] == first["snapshot_hash"]
        assert len(records[0]["snapshot"]["verification"]["timebase"]["sample_timestamps_utc"]) == 4


@pytest.mark.asyncio
async def test_concurrent_identical_insert_recovers_only_exact_existing_row(db, session):
    first = await save(db, session)

    class ConcurrentInsert(AsyncSQLiteBridge):
        lookup_count = 0

        async def execute(self, statement):
            self.lookup_count += 1
            # Simulate another request committing between the initial lookup
            # and insert. The database still enforces the actual unique key.
            if self.lookup_count == 1:
                statement = statement.where(False)
            return await super().execute(statement)

    second = await save(ConcurrentInsert(db.session), session)
    assert second["status"] == "ALREADY_PRESENT"
    assert second["snapshot_id"] == first["snapshot_id"]
    assert len(db.session.scalars(select(HeartRateTimebaseSnapshot)).all()) == 1


@pytest.mark.asyncio
async def test_unrelated_integrity_error_is_not_disguised_as_success(db, session):
    class FailedInsert(AsyncSQLiteBridge):
        async def flush(self):
            raise IntegrityError("synthetic insert", {}, ValueError("unrelated constraint"))

    with pytest.raises(IntegrityError):
        await save(FailedInsert(db.session), session)
    assert db.session.scalars(select(HeartRateTimebaseSnapshot)).all() == []


@pytest.mark.asyncio
async def test_corrupt_indexed_identity_is_detected_after_database_read(db, session):
    await save(db, session)
    row = db.session.scalar(select(HeartRateTimebaseSnapshot))
    row.exercise_external_id = "different-exercise"
    db.session.commit()
    records = await load(db, session)
    result = persistence.resolve_hr_timebase_snapshots(
        records,
        session,
        athlete_id=str(OWNER),
        session_external_id="synthetic-session",
        sample_session_match_count=1,
    )
    assert result["status"] == "WITHHELD"
    assert result["verified_exercise_count"] == 0
