from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Column, MetaData, Table, Uuid, create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.planning.domain.persistence.audit import (
    AuditArtifactConflictError,
    AuditArtifactKind,
    AuditArtifactRecord,
    AuditArtifactSaveStatus,
)
from app.planning.infrastructure.persistence.sqlalchemy_models import (
    PlanningAuditArtifactRow,
)
from app.planning.infrastructure.repositories.postgres_planning_audit import (
    SqlAlchemyPlanningAuditRepository,
)


UTC = timezone.utc


def dt(hour: int) -> datetime:
    return datetime(2026, 10, 19, hour, tzinfo=UTC)


class AsyncSQLiteBridge:
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


@pytest.fixture
def athlete_id():
    return str(uuid4())


@pytest.fixture
def db(athlete_id):
    metadata = Base.metadata

    if "users" not in metadata.tables:
        Table(
            "users",
            metadata,
            Column("id", Uuid(), primary_key=True),
        )

    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata.create_all(engine)

    with engine.begin() as connection:
        users = metadata.tables["users"]
        values = {"id": UUID(athlete_id)}

        if "email" in users.c:
            values["email"] = (
                f"p1-5e2a-{athlete_id}@example.invalid"
            )
        if "timezone" in users.c:
            values["timezone"] = "Europe/Budapest"
        if "created_at" in users.c:
            values["created_at"] = dt(8)

        connection.execute(users.insert().values(**values))

    with Session(
        engine,
        expire_on_commit=False,
    ) as sync:
        yield AsyncSQLiteBridge(sync)

    engine.dispose()


def record(
    *,
    athlete_id: str,
    artifact_id: str = "instruction-1",
    content_hash: str = "a" * 64,
    contract_json: str = '{"instruction":"one"}',
    created_at: datetime | None = None,
):
    return AuditArtifactRecord(
        artifact_kind=(
            AuditArtifactKind.PLAN_MUTATION_INSTRUCTION
        ),
        artifact_id=artifact_id,
        athlete_id=athlete_id,
        schema_version="plan_mutation_instruction_v0.1",
        created_at=created_at or dt(9),
        content_hash_algorithm="sha256",
        content_hash=content_hash,
        contract_json=contract_json,
    )


@pytest.mark.asyncio
async def test_save_and_get_round_trip_without_commit(
    db,
    athlete_id,
):
    repo = SqlAlchemyPlanningAuditRepository(db)
    item = record(athlete_id=athlete_id)

    saved = await repo.save(item)
    loaded = await repo.get(
        artifact_kind=item.artifact_kind,
        artifact_id=item.artifact_id,
    )

    assert saved.status == AuditArtifactSaveStatus.CREATED
    assert loaded == item
    assert db.commit_count == 0


@pytest.mark.asyncio
async def test_duplicate_identical_artifact_is_idempotent(
    db,
    athlete_id,
):
    repo = SqlAlchemyPlanningAuditRepository(db)
    item = record(athlete_id=athlete_id)

    first = await repo.save(item)
    second = await repo.save(item)

    assert first.status == AuditArtifactSaveStatus.CREATED
    assert (
        second.status
        == AuditArtifactSaveStatus.ALREADY_PRESENT
    )
    assert db.commit_count == 0


@pytest.mark.asyncio
async def test_duplicate_identity_with_different_content_conflicts(
    db,
    athlete_id,
):
    repo = SqlAlchemyPlanningAuditRepository(db)

    await repo.save(record(athlete_id=athlete_id))

    with pytest.raises(
        AuditArtifactConflictError,
        match="Immutable audit artifact identity",
    ):
        await repo.save(
            record(
                athlete_id=athlete_id,
                content_hash="b" * 64,
                contract_json='{"instruction":"changed"}',
            )
        )

    assert db.commit_count == 0


@pytest.mark.asyncio
async def test_list_for_athlete_filters_orders_and_limits(
    db,
    athlete_id,
):
    repo = SqlAlchemyPlanningAuditRepository(db)

    await repo.save(
        record(
            athlete_id=athlete_id,
            artifact_id="instruction-old",
            content_hash="1" * 64,
            contract_json='{"instruction":"old"}',
            created_at=dt(9),
        )
    )
    await repo.save(
        record(
            athlete_id=athlete_id,
            artifact_id="instruction-new",
            content_hash="2" * 64,
            contract_json='{"instruction":"new"}',
            created_at=dt(10),
        )
    )

    items = await repo.list_for_athlete(
        athlete_id=athlete_id,
        artifact_kind=(
            AuditArtifactKind.PLAN_MUTATION_INSTRUCTION
        ),
        limit=1,
    )

    assert len(items) == 1
    assert items[0].artifact_id == "instruction-new"
    assert db.commit_count == 0


def test_sqlalchemy_model_matches_planning_audit_contract():
    table = PlanningAuditArtifactRow.__table__

    assert table.name == "planning_audit_artifacts"
    assert set(table.primary_key.columns.keys()) == {
        "artifact_kind",
        "artifact_id",
    }

    assert {
        "artifact_kind",
        "artifact_id",
        "athlete_id",
        "schema_version",
        "created_at",
        "content_hash_algorithm",
        "content_hash",
        "contract_json",
    } <= set(table.columns.keys())
