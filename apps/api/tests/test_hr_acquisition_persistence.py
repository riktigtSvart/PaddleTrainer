from copy import deepcopy
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from test_heart_rate_sample_validation import session as _session_fixture
from test_hr_acquisition_declarations import PAYLOAD
from test_hr_timebase_persistence import AsyncSQLiteBridge

from app.models.entities import User
from app.models.hr_acquisition_declaration import HRAcquisitionDeclaration
from app.services.hr_acquisition_declarations import (
    HRAcquisitionDeclarationError,
    resolve_hr_acquisition_declarations,
)
from app.services.hr_acquisition_persistence import (
    load_current_hr_acquisition_declarations,
    persist_hr_acquisition_declaration,
)

session = _session_fixture
OWNER = UUID("00000000-0000-0000-0000-000000000301")
OTHER = UUID("00000000-0000-0000-0000-000000000302")


@pytest.fixture
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    User.__table__.create(engine)
    HRAcquisitionDeclaration.__table__.create(engine)
    with Session(engine, expire_on_commit=False) as sync:
        sync.add_all(
            [
                User(id=owner, email=f"owner-{i}@example.test", created_at=datetime.now(UTC))
                for i, owner in enumerate((OWNER, OTHER))
            ]
        )
        sync.commit()
        yield AsyncSQLiteBridge(sync)
    engine.dispose()


async def save(db, source, *, owner=OWNER, **changes):
    return await persist_hr_acquisition_declaration(
        db,
        {**PAYLOAD, **changes},
        source,
        athlete_id=str(owner),
        session_external_id="hr-session",
        sample_session_match_count=1,
    )


async def load(db, source, *, owner=OWNER, identity="hr-session", count=1):
    return await load_current_hr_acquisition_declarations(
        db,
        source,
        athlete_id=str(owner),
        session_external_id=identity,
        sample_session_match_count=count,
    )


def context(source, records, *, owner=OWNER):
    return resolve_hr_acquisition_declarations(
        records,
        source,
        athlete_id=str(owner),
        session_external_id="hr-session",
        sample_session_match_count=1,
    )


@pytest.mark.asyncio
async def test_database_round_trip_is_durable_and_identical_repeat_has_one_row(db, session):
    first, second = await save(db, session), await save(db, session)
    assert first["status"] == "CREATED"
    assert second["status"] == "ALREADY_PRESENT"
    assert first["declaration_id"] == second["declaration_id"]
    assert first["round_trip_verified"] is first["declaration_active"] is True
    assert first["acquisition_quality_verified"] is first["sensor_identity_verified"] is False
    assert first["recorded_at_utc"].endswith("+00:00")
    assert db.commit_count == 1
    with Session(db.session.get_bind(), expire_on_commit=False) as fresh:
        entries = await load(AsyncSQLiteBridge(fresh), session)
        assert len(entries) == 1
        assert entries[0]["declaration_id"] == first["declaration_id"]
        assert context(session, entries)["declared_exercise_count"] == 1


@pytest.mark.asyncio
async def test_owner_session_and_full_api_source_scope_are_enforced(db, session):
    first = await save(db, session)
    assert await load(db, session, owner=OTHER) == []
    assert await load(db, session, identity="another-session") == []
    changed = deepcopy(session)
    changed["modified"] = "2025-03-01T00:00:00Z"
    assert await load(db, changed) == []
    assert await load(db, session, count=2) == []
    second = await save(db, session, owner=OTHER)
    assert first["declaration_id"] != second["declaration_id"]
    assert first["declaration_hash"] != second["declaration_hash"]


@pytest.mark.asyncio
async def test_explicit_correction_is_append_only_and_repeating_old_request_does_not_reactivate_it(
    db, session
):
    first = await save(db, session)
    correction = await save(
        db,
        session,
        sensor_model="Replacement Sensor",
        supersedes_declaration_ids=[first["declaration_id"]],
    )
    repeat = await save(db, session)
    assert repeat["status"] == "ALREADY_PRESENT"
    assert repeat["declaration_active"] is False
    assert correction["declaration_id"] != first["declaration_id"]
    entries = await load(db, session)
    assert len(entries) == 2
    original = next(
        entry for entry in entries if entry["declaration_id"] == first["declaration_id"]
    )
    assert original["declaration"]["statement"]["sensor_model"] == "Example Wearable"
    resolved = context(session, entries)
    assert resolved["exercises"][0]["declared_sensor"]["sensor_model"] == "Replacement Sensor"
    assert resolved["exercises"][0]["active_declaration_ids"] == [correction["declaration_id"]]


@pytest.mark.asyncio
async def test_conflicts_remain_visible_and_explicit_correction_can_resolve_all_heads(db, session):
    first = await save(db, session)
    second = await save(db, session, sensor_modality="ELECTRICAL", body_location="CHEST")
    assert context(session, await load(db, session))["status"] == "REVIEW_REQUIRED"
    with pytest.raises(HRAcquisitionDeclarationError, match="CORRECTION_TARGETS_NOT_CURRENT"):
        await save(
            db,
            session,
            sensor_model="Corrected Sensor",
            supersedes_declaration_ids=[first["declaration_id"]],
        )
    final = await save(
        db,
        session,
        sensor_model="Corrected Sensor",
        supersedes_declaration_ids=[second["declaration_id"], first["declaration_id"]],
    )
    result = context(session, await load(db, session))
    assert result["status"] == "USER_DECLARED_WITH_LIMITATIONS"
    assert result["provided_record_count"] == 3
    assert result["exercises"][0]["active_declaration_ids"] == [final["declaration_id"]]


@pytest.mark.asyncio
async def test_wrong_owner_source_and_nonexistent_predecessors_cannot_correct_a_record(db, session):
    first = await save(db, session)
    changed = deepcopy(session)
    changed["modified"] = "2025-03-01T00:00:00Z"
    for source, owner in ((session, OTHER), (changed, OWNER)):
        with pytest.raises(HRAcquisitionDeclarationError, match="CORRECTION_TARGETS_NOT_CURRENT"):
            await save(
                db, source, owner=owner, supersedes_declaration_ids=[first["declaration_id"]]
            )
    with pytest.raises(HRAcquisitionDeclarationError, match="CORRECTION_TARGETS_NOT_CURRENT"):
        await save(db, session, supersedes_declaration_ids=[str(UUID(int=99))])
    assert len(await load(db, session)) == 1
    assert db.commit_count == 1


@pytest.mark.asyncio
async def test_changed_source_keeps_prior_history_but_requires_new_statement(db, session):
    first = await save(db, session)
    changed = deepcopy(session)
    changed["modified"] = "2025-03-01T00:00:00Z"
    second = await save(db, changed)
    assert second["declaration_id"] != first["declaration_id"]
    assert len(await load(db, session)) == len(await load(db, changed)) == 1
    assert len(db.session.scalars(select(HRAcquisitionDeclaration)).all()) == 2


@pytest.mark.asyncio
async def test_database_corruption_is_not_returned_as_idempotent_success(db, session):
    await save(db, session)
    row = db.session.scalar(select(HRAcquisitionDeclaration))
    row.declaration_json = {**row.declaration_json, "source_kind": "PROVIDER_VERIFIED"}
    db.session.commit()
    with pytest.raises(HRAcquisitionDeclarationError, match="EXISTING_RECORDS_UNUSABLE"):
        await save(db, session)
    assert context(session, await load(db, session))["status"] == "WITHHELD"


@pytest.mark.asyncio
async def test_concurrent_identical_insert_recovers_exact_record(db, session, monkeypatch):
    first = await save(db, session)
    from app.services import hr_acquisition_persistence as module

    original = module.load_current_hr_acquisition_declarations
    calls = 0

    async def initial_miss(*args, **kwargs):
        nonlocal calls
        calls += 1
        return [] if calls == 1 else await original(*args, **kwargs)

    monkeypatch.setattr(module, "load_current_hr_acquisition_declarations", initial_miss)
    second = await save(db, session)
    assert second["status"] == "ALREADY_PRESENT"
    assert second["declaration_id"] == first["declaration_id"]
    assert len(await load(db, session)) == 1
