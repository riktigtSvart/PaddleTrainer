from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import (
    Column,
    Table,
    Uuid,
    create_engine,
    select,
)
from sqlalchemy.orm import Session

from app.db.base import Base
from app.planning.domain.common.enums import (
    KnowledgeStatus,
    ProvenanceKind,
)
from app.planning.domain.evidence.models import (
    EvidenceConflictError,
    EvidenceQuality,
    SourceRecordRef,
    create_evidence_item,
)
from app.planning.infrastructure.persistence.sqlalchemy_models import (
    PlanningEvidenceItemRow,
)
from app.planning.infrastructure.repositories.postgres_evidence import (
    SqlAlchemyEvidenceRepository,
)


UTC = timezone.utc
ATHLETE_ID = "11111111-1111-4111-8111-111111111111"


def dt(hour: int) -> datetime:
    return datetime(
        2026,
        10,
        19,
        hour,
        0,
        tzinfo=UTC,
    )


def item(
    evidence_id: str,
    *,
    observed: int = 10,
    available: int = 12,
    created: int = 20,
    duration_s: int | None = 3600,
):
    return create_evidence_item(
        evidence_id=evidence_id,
        athlete_id=ATHLETE_ID,
        evidence_type="EXECUTED_TRAINING_SESSION",
        observed_at=dt(observed),
        available_at=dt(available),
        created_at=dt(created),
        source_ref=SourceRecordRef(
            source_system=(
                "planning_authoritative_executed_training"
            ),
            source_record_id=(
                "pt-executed-training-evidence:example"
            ),
            source_version=(
                "authoritative-executed-training-evidence-v0.1"
            ),
            source_content_hash="a" * 64,
        ),
        provenance=ProvenanceKind.DERIVED,
        knowledge_status=KnowledgeStatus.KNOWN,
        quality=EvidenceQuality.HIGH,
        payload={
            "schema_version":
                "executed_training_session_evidence_v0.2",
            "session_id":
                "22222222-2222-4222-8222-222222222222",
            "modality_key": "RUNNING",
            "duration_status":
                "known" if duration_s is not None else "unknown",
            "duration_s": duration_s,
            "nested": {
                "flags": [False, False],
            },
        },
    )


class AsyncSQLiteBridge:
    def __init__(self, session: Session):
        self.session = session

    async def execute(self, statement):
        return self.session.execute(statement)

    def add(self, value):
        self.session.add(value)

    async def flush(self):
        self.session.flush()


@pytest.fixture
def repository():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:"
    )

    # The ORM mapper is bound to Base.metadata, so its FK targets
    # must exist in that same metadata. Do not clone the mapped table
    # into a separate MetaData object: the mapper would still resolve
    # ForeignKey("users.id") against Base.metadata during flush.
    metadata = Base.metadata

    if "users" not in metadata.tables:
        Table(
            "users",
            metadata,
            Column(
                "id",
                Uuid(),
                primary_key=True,
            ),
        )

    users = metadata.tables["users"]

    # Create only the two tables required by this repository contract.
    # Avoid Base.metadata.create_all(), because unrelated planning
    # tables have external FK targets outside this focused fixture.
    users.create(
        engine,
        checkfirst=True,
    )
    PlanningEvidenceItemRow.__table__.create(
        engine,
        checkfirst=True,
    )

    user_values = {
        "id": UUID(ATHLETE_ID),
    }

    if "email" in users.c:
        user_values["email"] = (
            "p1-7d-evidence@example.invalid"
        )
    if "name" in users.c:
        user_values["name"] = "P1.7D evidence fixture"
    if "timezone" in users.c:
        user_values["timezone"] = "Europe/Budapest"
    if "created_at" in users.c:
        user_values["created_at"] = dt(8)

    with engine.begin() as connection:
        connection.execute(
            users.insert().values(**user_values)
        )

    with Session(
        engine,
        expire_on_commit=False,
    ) as sync:
        bridge = AsyncSQLiteBridge(sync)
        repo = SqlAlchemyEvidenceRepository(bridge)
        yield repo, sync

    engine.dispose()


@pytest.mark.asyncio
async def test_round_trip_preserves_evidence_contract(
    repository,
):
    repo, _ = repository

    source = item("pt-evidence:test-round-trip")

    stored = await repo.save(source)

    assert stored == source

    rows = await repo.list_available(
        athlete_id=ATHLETE_ID,
        information_cutoff_at=dt(18),
    )

    assert len(rows) == 1

    restored = rows[0]

    assert restored.evidence_id == source.evidence_id
    assert restored.athlete_id == ATHLETE_ID
    assert restored.payload == source.payload
    assert restored.source_ref == source.source_ref
    assert restored.verify_content_hash() is True


@pytest.mark.asyncio
async def test_identical_retry_is_idempotent_and_preserves_first_created_at(
    repository,
):
    repo, sync = repository

    first = item(
        "pt-evidence:idempotent",
        created=20,
    )

    retry = item(
        "pt-evidence:idempotent",
        created=21,
    )

    assert first.content_hash == retry.content_hash

    saved_first = await repo.save(first)
    saved_retry = await repo.save(retry)

    assert saved_first.created_at == dt(20)
    assert saved_retry.created_at == dt(20)

    rows = sync.execute(
        select(PlanningEvidenceItemRow)
    ).scalars().all()

    assert len(rows) == 1


@pytest.mark.asyncio
async def test_same_identity_with_different_content_conflicts(
    repository,
):
    repo, _ = repository

    await repo.save(
        item(
            "pt-evidence:conflict",
            duration_s=3600,
        )
    )

    with pytest.raises(
        EvidenceConflictError,
        match="different content",
    ):
        await repo.save(
            item(
                "pt-evidence:conflict",
                duration_s=1800,
            )
        )


@pytest.mark.asyncio
async def test_cutoff_query_excludes_future_available_and_observed(
    repository,
):
    repo, _ = repository

    await repo.save(
        item(
            "pt-evidence:early",
            observed=10,
            available=12,
        )
    )

    await repo.save(
        item(
            "pt-evidence:late-available",
            observed=10,
            available=19,
        )
    )

    await repo.save(
        item(
            "pt-evidence:future-observed",
            observed=19,
            available=19,
        )
    )

    rows = await repo.list_available(
        athlete_id=ATHLETE_ID,
        information_cutoff_at=dt(18),
    )

    assert tuple(
        row.evidence_id
        for row in rows
    ) == (
        "pt-evidence:early",
    )


@pytest.mark.asyncio
async def test_cutoff_query_is_owner_scoped(
    repository,
):
    repo, _ = repository

    await repo.save(
        item("pt-evidence:owner")
    )

    other = str(uuid4())

    rows = await repo.list_available(
        athlete_id=other,
        information_cutoff_at=dt(18),
    )

    assert rows == ()


@pytest.mark.asyncio
async def test_persisted_hash_tampering_fails_round_trip(
    repository,
):
    repo, sync = repository

    await repo.save(
        item("pt-evidence:tamper")
    )

    row = sync.execute(
        select(PlanningEvidenceItemRow).where(
            PlanningEvidenceItemRow.evidence_id
            == "pt-evidence:tamper"
        )
    ).scalar_one()

    # SQLite contract test intentionally bypasses the PostgreSQL
    # immutability trigger so restoration integrity can be tested.
    row.content_hash = "f" * 64
    sync.flush()

    with pytest.raises(
        ValueError,
        match="does not round-trip",
    ):
        await repo.list_available(
            athlete_id=ATHLETE_ID,
            information_cutoff_at=dt(18),
        )
