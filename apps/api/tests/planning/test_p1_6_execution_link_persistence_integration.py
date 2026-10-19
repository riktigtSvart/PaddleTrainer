from datetime import date, datetime, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.entities import (
    PlannedWorkout,
    Sport,
    User,
    WorkoutLinkSource,
    WorkoutSession,
    WorkoutStatus,
)
from app.planning.application.link_authoritative_execution import (
    link_authoritative_execution_with_repository,
)
from app.planning.domain.execution_link import (
    AuthoritativeExecutionLinkConflictError,
    ExecutionLinkBasis,
    finalize_authoritative_plan_execution_link,
)
from app.planning.domain.plan_revision.persistence_contract import (
    AdoptionSourceRef,
    OccurrenceLineageKind,
    PlanHistoryClaim,
    PlanRevisionOrigin,
    RevisionDecisionLineage,
    RevisionOccurrence,
    finalize_authoritative_plan_revision,
    finalize_current_state_adoption_binding,
)
from app.planning.infrastructure.adapters.locked_execution_source import (
    CurrentAppLockedExecutionSource,
)
from app.planning.infrastructure.persistence.sqlalchemy_models import (
    PlanningPlanExecutionLinkRow,
)
from app.planning.infrastructure.repositories.postgres_authoritative_plan_execution import (
    SqlAlchemyAuthoritativePlanExecutionLinkRepository,
)
from app.planning.infrastructure.repositories.postgres_authoritative_plan_revision import (
    SqlAlchemyAuthoritativePlanRevisionRepository,
)


UTC = timezone.utc


def dt(hour: int) -> datetime:
    return datetime(2026, 10, 19, hour, tzinfo=UTC)


class AsyncSQLiteBridge:
    def __init__(self, session):
        self.session = session
        self.commit_count = 0
        self.rollback_count = 0

    async def execute(self, statement):
        return self.session.execute(statement)

    def add(self, row):
        self.session.add(row)

    async def flush(self):
        self.session.flush()

    async def commit(self):
        self.session.commit()
        self.commit_count += 1

    async def rollback(self):
        self.session.rollback()
        self.rollback_count += 1


class StaticHashProvider:
    def __init__(self, value: str):
        self.value = value

    async def lock_and_hash(
        self,
        session,
        *,
        source_workout_id: str,
        athlete_id: str,
    ):
        return self.value


class ExplodingExecutionSource:
    async def lock_and_capture(self, *args, **kwargs):
        raise AssertionError(
            "Idempotent retry must not recapture mutable source."
        )


@pytest.fixture
def ids():
    return {
        "athlete": str(uuid4()),
        "source": str(uuid4()),
        "session": str(uuid4()),
    }


@pytest.fixture
def db(ids):
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _foreign_keys(dbapi_connection, _):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)

    with Session(engine, expire_on_commit=False) as sync:
        sync.add(
            User(
                id=UUID(ids["athlete"]),
                email=(
                    f"p1-6-{ids['athlete']}@example.invalid"
                ),
                name="P1.6 test athlete",
                timezone="Europe/Budapest",
                created_at=dt(7),
            )
        )
        # Persist the FK parent explicitly. These mappers have no
        # ORM relationship that guarantees unit-of-work ordering
        # for this synthetic fixture.
        sync.flush()

        sync.add(
            PlannedWorkout(
                id=UUID(ids["source"]),
                user_id=UUID(ids["athlete"]),
                date=date(2026, 10, 19),
                planned_start_time=dt(6),
                sport=Sport.RUNNING,
                title="P1.6 exact provider plan",
                description=None,
                duration_sec=3600,
                distance_m=None,
                intensity_type=None,
                status=WorkoutStatus.PLANNED,
                source="POLAR",
                polar_target_id="target-1",
                raw_data={"provider_fixture": True},
                created_at=dt(5),
                updated_at=dt(5),
            )
        )
        # WorkoutSession references this planned workout.
        sync.flush()

        # The actual start is intentionally many hours away from
        # planned_start_time. Temporal proximity must not contribute.
        sync.add(
            WorkoutSession(
                id=UUID(ids["session"]),
                user_id=UUID(ids["athlete"]),
                planned_workout_id=UUID(ids["source"]),
                planned_workout_link_source=(
                    WorkoutLinkSource.PROVIDER_EXACT
                ),
                external_provider="POLAR",
                external_id="polar-session-p1-6",
                sport=Sport.RUNNING,
                name="P1.6 executed session",
                started_at=dt(18),
                ended_at=dt(19),
                duration_sec=3600,
                raw_data={
                    "trainingTarget": {
                        "id": "target-1",
                    }
                },
                created_at=dt(19),
            )
        )
        # Make fixture setup failures local and explicit.
        sync.flush()

        sync.commit()

        bridge = AsyncSQLiteBridge(sync)
        yield bridge

    engine.dispose()


def source_ref():
    return AdoptionSourceRef(
        capture_id="capture-p1-6",
        capture_content_hash="a" * 64,
        source_read_content_hash="b" * 64,
        source_content_sha256="c" * 64,
        external_contract_plan_id="polar-plan-p1-6",
        external_contract_plan_revision=1,
    )


def baseline(ids):
    return finalize_authoritative_plan_revision(
        revision_id="pt-plan-rev:p1-6-baseline",
        logical_plan_id=(
            f"planned-workout:{ids['source']}"
        ),
        athlete_id=ids["athlete"],
        revision_number=1,
        previous_revision_id=None,
        origin=PlanRevisionOrigin.ADOPTED_CURRENT_STATE,
        history_claim=(
            PlanHistoryClaim.CURRENT_STATE_BASELINE_ONLY
        ),
        authority_established_at=dt(8),
        effective_from=dt(8),
        created_at=dt(8),
        contract_schema_version="0.1",
        contract_json=(
            '{"blocks":[],"plan":"p1-6-baseline"}'
        ),
        occurrences=(
            RevisionOccurrence(
                occurrence_id="pt-occ:p1-6-one",
                ordinal=0,
                lineage_kind=OccurrenceLineageKind.NEW,
                source_capture_occurrence_id=(
                    "capture-occ-p1-6-one"
                ),
            ),
        ),
        adoption_source=source_ref(),
        decision_lineage=None,
    )


def second_revision(ids):
    return finalize_authoritative_plan_revision(
        revision_id="pt-plan-rev:p1-6-second",
        logical_plan_id=(
            f"planned-workout:{ids['source']}"
        ),
        athlete_id=ids["athlete"],
        revision_number=2,
        previous_revision_id="pt-plan-rev:p1-6-baseline",
        origin=PlanRevisionOrigin.PLANNER_CREATED,
        history_claim=(
            PlanHistoryClaim.VERIFIED_FROM_AUTHORITY_START
        ),
        authority_established_at=dt(8),
        effective_from=dt(12),
        created_at=dt(11),
        contract_schema_version="0.1",
        contract_json=(
            '{"blocks":[],"plan":"p1-6-second"}'
        ),
        occurrences=(
            RevisionOccurrence(
                occurrence_id="pt-occ:p1-6-one",
                ordinal=0,
                lineage_kind=OccurrenceLineageKind.PRESERVED,
            ),
        ),
        adoption_source=None,
        decision_lineage=RevisionDecisionLineage(
            context_hash="d" * 64,
            decision_hash="e" * 64,
            rationale_hash="f" * 64,
            instruction_hash="1" * 64,
        ),
    )


async def establish_authority(db, ids):
    repo = SqlAlchemyAuthoritativePlanRevisionRepository(
        db,
        source_hash_provider=StaticHashProvider("c" * 64),
    )
    first = baseline(ids)

    await repo.adopt_current_state(
        binding=finalize_current_state_adoption_binding(
            logical_plan_id=first.logical_plan_id,
            source_workout_id=ids["source"],
            expected_source_content_sha256="c" * 64,
            adopted_revision_id=first.revision_id,
            authority_established_at=dt(8),
        ),
        revision=first,
    )
    await db.commit()

    return repo, first


@pytest.mark.asyncio
async def test_real_sqlalchemy_execution_link_round_trip(
    db,
    ids,
):
    revision_repo, first = await establish_authority(
        db,
        ids,
    )

    # Ignore setup commit; assertions below cover application boundary.
    db.commit_count = 0
    db.rollback_count = 0

    link_repo = (
        SqlAlchemyAuthoritativePlanExecutionLinkRepository(
            db
        )
    )

    result = (
        await link_authoritative_execution_with_repository(
            athlete_id=ids["athlete"],
            logical_plan_id=first.logical_plan_id,
            workout_session_id=ids["session"],
            revision_repository=revision_repo,
            execution_link_repository=link_repo,
            execution_source=CurrentAppLockedExecutionSource(),
            session=db,
            created_at=dt(20),
            id_factory=lambda: "real-round-trip",
        )
    )

    loaded = await link_repo.get_by_session(
        workout_session_id=ids["session"]
    )

    assert loaded == result
    assert result.verify_content_hash()
    assert (
        result.link_basis
        == ExecutionLinkBasis.EXACT_PROVIDER_ID
    )
    assert result.provider_target_id == "target-1"
    assert result.observed_revision_id == first.revision_id
    assert (
        result.observed_revision_content_hash
        == first.content_hash
    )
    assert result.source_workout_content_hash != "c" * 64
    assert len(result.source_workout_content_hash) == 64
    assert len(result.session_source_content_hash) == 64
    assert result.temporal_match_used is False
    assert (
        result.plan_content_at_execution_status
        == "unverified"
    )

    rows = db.session.scalars(
        select(PlanningPlanExecutionLinkRow)
    ).all()
    assert len(rows) == 1

    assert db.commit_count == 1
    assert db.rollback_count == 0


@pytest.mark.asyncio
async def test_retry_after_new_plan_revision_returns_original_link(
    db,
    ids,
):
    revision_repo, first = await establish_authority(
        db,
        ids,
    )
    link_repo = (
        SqlAlchemyAuthoritativePlanExecutionLinkRepository(
            db
        )
    )

    original = (
        await link_authoritative_execution_with_repository(
            athlete_id=ids["athlete"],
            logical_plan_id=first.logical_plan_id,
            workout_session_id=ids["session"],
            revision_repository=revision_repo,
            execution_link_repository=link_repo,
            execution_source=CurrentAppLockedExecutionSource(),
            session=db,
            created_at=dt(20),
            id_factory=lambda: "original",
        )
    )

    second = second_revision(ids)
    await revision_repo.append_revision(
        expected_current_revision_id=first.revision_id,
        revision=second,
    )
    await db.commit()

    commits_before_retry = db.commit_count
    rollbacks_before_retry = db.rollback_count

    retried = (
        await link_authoritative_execution_with_repository(
            athlete_id=ids["athlete"],
            logical_plan_id=first.logical_plan_id,
            workout_session_id=ids["session"],
            revision_repository=revision_repo,
            execution_link_repository=link_repo,
            execution_source=ExplodingExecutionSource(),
            session=db,
            created_at=dt(21),
            id_factory=lambda: "must-not-be-used",
        )
    )

    assert retried == original
    assert (
        retried.observed_revision_id
        == "pt-plan-rev:p1-6-baseline"
    )
    assert retried.observed_revision_id != second.revision_id

    rows = db.session.scalars(
        select(PlanningPlanExecutionLinkRow)
    ).all()
    assert len(rows) == 1

    assert db.commit_count == commits_before_retry + 1
    assert db.rollback_count == rollbacks_before_retry


@pytest.mark.asyncio
async def test_repository_rejects_rebinding_existing_session(
    db,
    ids,
):
    revision_repo, first = await establish_authority(
        db,
        ids,
    )
    link_repo = (
        SqlAlchemyAuthoritativePlanExecutionLinkRepository(
            db
        )
    )

    original = (
        await link_authoritative_execution_with_repository(
            athlete_id=ids["athlete"],
            logical_plan_id=first.logical_plan_id,
            workout_session_id=ids["session"],
            revision_repository=revision_repo,
            execution_link_repository=link_repo,
            execution_source=CurrentAppLockedExecutionSource(),
            session=db,
            created_at=dt(20),
            id_factory=lambda: "immutable-original",
        )
    )

    second = second_revision(ids)
    await revision_repo.append_revision(
        expected_current_revision_id=first.revision_id,
        revision=second,
    )
    await db.commit()

    competing = finalize_authoritative_plan_execution_link(
        link_id="pt-exec-link:competing",
        athlete_id=ids["athlete"],
        logical_plan_id=first.logical_plan_id,
        observed_revision_id=second.revision_id,
        workout_session_id=ids["session"],
        source_workout_id=ids["source"],
        link_basis=ExecutionLinkBasis.EXACT_PROVIDER_ID,
        provider_target_id="target-1",
        source_workout_content_hash=(
            original.source_workout_content_hash
        ),
        session_source_content_hash=(
            original.session_source_content_hash
        ),
        observed_revision_content_hash=second.content_hash,
        created_at=dt(21),
    )

    with pytest.raises(
        AuthoritativeExecutionLinkConflictError
    ):
        await link_repo.save(competing)

    await db.rollback()

    persisted = await link_repo.get_by_session(
        workout_session_id=ids["session"]
    )
    assert persisted == original

    rows = db.session.scalars(
        select(PlanningPlanExecutionLinkRow)
    ).all()
    assert len(rows) == 1
