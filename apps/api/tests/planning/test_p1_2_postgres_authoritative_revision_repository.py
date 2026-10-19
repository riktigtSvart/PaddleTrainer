from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Column, MetaData, Table, Uuid, create_engine, event, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.planning.application.apply_plan_revision import (
    apply_authoritative_plan_revision,
)
from app.planning.domain.plan_revision.models import (
    OccurrenceIdentityPolicy,
    PlanMutationOperation,
    create_workout_plan_contract_artifact,
    finalize_plan_mutation_instruction,
)
from app.planning.domain.plan_revision.persistence_contract import (
    AdoptionSourceRef,
    AuthoritativePlanConflictError,
    OccurrenceLineageKind,
    PlanHistoryClaim,
    PlanRevisionOrigin,
    RevisionDecisionLineage,
    RevisionOccurrence,
    finalize_authoritative_plan_revision,
    finalize_current_state_adoption_binding,
)
from app.planning.infrastructure.persistence.sqlalchemy_models import (
    PlanningLogicalPlanRow,
    PlanningPlanOccurrenceIdentityRow,
    PlanningPlanRevisionOccurrenceRow,
    PlanningPlanRevisionRow,
)
from app.planning.infrastructure.repositories.postgres_authoritative_plan_revision import (
    SqlAlchemyAuthoritativePlanRevisionRepository,
)


UTC = timezone.utc


def dt(hour: int) -> datetime:
    return datetime(2026, 10, 17, hour, tzinfo=UTC)


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


class StaticHashProvider:
    def __init__(self, value: str):
        self.value = value
        self.calls = []

    async def lock_and_hash(self, session, *, source_workout_id: str, athlete_id: str):
        self.calls.append((source_workout_id, athlete_id))
        return self.value


@pytest.fixture
def ids():
    return {
        "athlete": str(uuid4()),
        "source": str(uuid4()),
    }


@pytest.fixture
def db(ids):
    metadata = Base.metadata
    if "users" not in metadata.tables:
        Table("users", metadata, Column("id", Uuid(), primary_key=True))
    if "planned_workouts" not in metadata.tables:
        Table("planned_workouts", metadata, Column("id", Uuid(), primary_key=True))

    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _foreign_keys(dbapi_connection, _):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    metadata.create_all(engine)
    with engine.begin() as connection:
        users = metadata.tables["users"]
        user_values = {"id": UUID(ids["athlete"])}
        if "email" in users.c:
            user_values["email"] = f"p1-2-{ids['athlete']}@example.invalid"
        if "timezone" in users.c:
            user_values["timezone"] = "Europe/Budapest"
        if "created_at" in users.c:
            user_values["created_at"] = dt(8)
        connection.execute(users.insert().values(**user_values))

        planned_workouts = metadata.tables["planned_workouts"]
        workout_values = {"id": UUID(ids["source"])}
        if "user_id" in planned_workouts.c:
            workout_values["user_id"] = UUID(ids["athlete"])
        if "date" in planned_workouts.c:
            workout_values["date"] = date(2026, 10, 17)
        if "sport" in planned_workouts.c:
            workout_values["sport"] = "KAYAK"
        if "title" in planned_workouts.c:
            workout_values["title"] = "P1.2 repository fixture"
        if "status" in planned_workouts.c:
            workout_values["status"] = "PLANNED"
        if "source" in planned_workouts.c:
            workout_values["source"] = "TEST"
        if "created_at" in planned_workouts.c:
            workout_values["created_at"] = dt(8)
        if "updated_at" in planned_workouts.c:
            workout_values["updated_at"] = dt(8)
        connection.execute(planned_workouts.insert().values(**workout_values))

    with Session(engine, expire_on_commit=False) as sync:
        yield AsyncSQLiteBridge(sync)
    engine.dispose()


def source_ref() -> AdoptionSourceRef:
    return AdoptionSourceRef(
        capture_id="capture-1",
        capture_content_hash="a" * 64,
        source_read_content_hash="b" * 64,
        source_content_sha256="c" * 64,
        external_contract_plan_id="capture-plan-1",
        external_contract_plan_revision=1,
    )


def baseline(ids):
    logical = f"planned-workout:{ids['source']}"
    return finalize_authoritative_plan_revision(
        revision_id="pt-plan-rev:baseline",
        logical_plan_id=logical,
        athlete_id=ids["athlete"],
        revision_number=1,
        previous_revision_id=None,
        origin=PlanRevisionOrigin.ADOPTED_CURRENT_STATE,
        history_claim=PlanHistoryClaim.CURRENT_STATE_BASELINE_ONLY,
        authority_established_at=dt(9),
        effective_from=dt(10),
        created_at=dt(9),
        contract_schema_version="0.1",
        contract_json='{"blocks":[],"plan":"baseline"}',
        occurrences=(
            RevisionOccurrence(
                occurrence_id="pt-occ:one",
                ordinal=0,
                lineage_kind=OccurrenceLineageKind.NEW,
                source_capture_occurrence_id="capture-occ-one",
            ),
            RevisionOccurrence(
                occurrence_id="pt-occ:two",
                ordinal=1,
                lineage_kind=OccurrenceLineageKind.NEW,
                source_capture_occurrence_id="capture-occ-two",
            ),
        ),
        adoption_source=source_ref(),
        decision_lineage=None,
    )


def binding(ids):
    return finalize_current_state_adoption_binding(
        logical_plan_id=f"planned-workout:{ids['source']}",
        source_workout_id=ids["source"],
        expected_source_content_sha256="c" * 64,
        adopted_revision_id="pt-plan-rev:baseline",
        authority_established_at=dt(9),
    )


def second(ids):
    return finalize_authoritative_plan_revision(
        revision_id="pt-plan-rev:second",
        logical_plan_id=f"planned-workout:{ids['source']}",
        athlete_id=ids["athlete"],
        revision_number=2,
        previous_revision_id="pt-plan-rev:baseline",
        origin=PlanRevisionOrigin.PLANNER_CREATED,
        history_claim=PlanHistoryClaim.VERIFIED_FROM_AUTHORITY_START,
        authority_established_at=dt(9),
        effective_from=dt(12),
        created_at=dt(11),
        contract_schema_version="0.1",
        contract_json='{"blocks":[],"plan":"second"}',
        occurrences=(
            RevisionOccurrence(
                occurrence_id="pt-occ:one",
                ordinal=0,
                lineage_kind=OccurrenceLineageKind.PRESERVED,
            ),
            RevisionOccurrence(
                occurrence_id="pt-occ:three",
                ordinal=1,
                lineage_kind=OccurrenceLineageKind.NEW,
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


@pytest.mark.asyncio
async def test_adoption_round_trip_preserves_source_and_external_provenance(db, ids):
    provider = StaticHashProvider("c" * 64)
    repo = SqlAlchemyAuthoritativePlanRevisionRepository(
        db,
        source_hash_provider=provider,
    )
    revision = baseline(ids)
    identity = await repo.adopt_current_state(
        binding=binding(ids),
        revision=revision,
    )

    assert identity.current_revision_id == revision.revision_id
    assert identity.current_revision_number == 1
    assert provider.calls == [(ids["source"], ids["athlete"])]
    loaded = await repo.get_current_revision(logical_plan_id=revision.logical_plan_id)
    assert loaded == revision
    assert loaded.adoption_source.external_contract_plan_id == "capture-plan-1"
    assert loaded.adoption_source.external_contract_plan_revision == 1
    assert db.commit_count == 0


@pytest.mark.asyncio
async def test_adoption_fails_closed_when_locked_source_hash_drifted(db, ids):
    repo = SqlAlchemyAuthoritativePlanRevisionRepository(
        db,
        source_hash_provider=StaticHashProvider("9" * 64),
    )
    with pytest.raises(AuthoritativePlanConflictError, match="changed"):
        await repo.adopt_current_state(binding=binding(ids), revision=baseline(ids))

    rows = db.session.scalars(select(PlanningLogicalPlanRow)).all()
    assert rows == []


@pytest.mark.asyncio
async def test_append_uses_optimistic_pointer_and_preserves_old_revision(db, ids):
    repo = SqlAlchemyAuthoritativePlanRevisionRepository(
        db,
        source_hash_provider=StaticHashProvider("c" * 64),
    )
    first = baseline(ids)
    await repo.adopt_current_state(binding=binding(ids), revision=first)
    old_json = db.session.scalar(
        select(PlanningPlanRevisionRow.canonical_contract_json).where(
            PlanningPlanRevisionRow.revision_id == first.revision_id
        )
    )

    next_revision = second(ids)
    identity = await repo.append_revision(
        expected_current_revision_id=first.revision_id,
        revision=next_revision,
    )
    assert identity.current_revision_id == next_revision.revision_id
    assert identity.current_revision_number == 2
    assert await repo.get_revision(revision_id=first.revision_id) == first
    assert await repo.get_current_revision(logical_plan_id=first.logical_plan_id) == next_revision
    assert db.session.scalar(
        select(PlanningPlanRevisionRow.canonical_contract_json).where(
            PlanningPlanRevisionRow.revision_id == first.revision_id
        )
    ) == old_json

    identities = db.session.scalars(
        select(PlanningPlanOccurrenceIdentityRow).order_by(
            PlanningPlanOccurrenceIdentityRow.occurrence_id
        )
    ).all()
    assert [item.occurrence_id for item in identities] == [
        "pt-occ:one",
        "pt-occ:three",
        "pt-occ:two",
    ]


@pytest.mark.asyncio
async def test_append_rejects_stale_expected_current_revision(db, ids):
    repo = SqlAlchemyAuthoritativePlanRevisionRepository(
        db,
        source_hash_provider=StaticHashProvider("c" * 64),
    )
    await repo.adopt_current_state(binding=binding(ids), revision=baseline(ids))
    with pytest.raises(AuthoritativePlanConflictError, match="changed"):
        await repo.append_revision(
            expected_current_revision_id="pt-plan-rev:stale",
            revision=second(ids),
        )


@pytest.mark.asyncio
async def test_revision_membership_is_append_only_and_ordinals_are_stored(db, ids):
    repo = SqlAlchemyAuthoritativePlanRevisionRepository(
        db,
        source_hash_provider=StaticHashProvider("c" * 64),
    )
    await repo.adopt_current_state(binding=binding(ids), revision=baseline(ids))
    await repo.append_revision(
        expected_current_revision_id="pt-plan-rev:baseline",
        revision=second(ids),
    )

    rows = db.session.scalars(
        select(PlanningPlanRevisionOccurrenceRow).order_by(
            PlanningPlanRevisionOccurrenceRow.revision_id,
            PlanningPlanRevisionOccurrenceRow.ordinal,
        )
    ).all()
    assert len(rows) == 4
    assert [(row.revision_id, row.ordinal) for row in rows] == [
        ("pt-plan-rev:baseline", 0),
        ("pt-plan-rev:baseline", 1),
        ("pt-plan-rev:second", 0),
        ("pt-plan-rev:second", 1),
    ]

@pytest.mark.asyncio
async def test_p1_5_application_append_round_trips_lineage_and_preserves_baseline(
    db,
    ids,
):
    repo = SqlAlchemyAuthoritativePlanRevisionRepository(
        db,
        source_hash_provider=StaticHashProvider("c" * 64),
    )
    first = baseline(ids)
    await repo.adopt_current_state(
        binding=binding(ids),
        revision=first,
    )

    old_json = db.session.scalar(
        select(PlanningPlanRevisionRow.canonical_contract_json).where(
            PlanningPlanRevisionRow.revision_id == first.revision_id
        )
    )

    artifact = create_workout_plan_contract_artifact(
        plan_id=first.logical_plan_id,
        revision_id="artifact-p1-5-r2",
        contract_schema_version="0.1",
        contract_json='{"blocks":[],"plan":"p1.5-second"}',
        stable_occurrence_ids=(
            "pt-occ:one",
            "pt-occ:three",
        ),
    )
    instruction = finalize_plan_mutation_instruction(
        instruction_id="instruction-p1-5-r2",
        operation=PlanMutationOperation.MODIFY,
        decision_hash="d" * 64,
        rationale_hash="e" * 64,
        context_hash="f" * 64,
        selected_action_id="action-p1-5",
        plan_id=first.logical_plan_id,
        expected_current_revision_id=first.revision_id,
        new_plan_artifact=artifact,
        occurrence_identity_policy=(
            OccurrenceIdentityPolicy.PRESERVE_UNCHANGED
        ),
        effective_from=dt(12),
        created_at=dt(11),
    )

    applied = await apply_authoritative_plan_revision(
        current_revision=first,
        instruction=instruction,
        revision_id="pt-plan-rev:p1-5-second",
        repository=repo,
    )

    assert applied.identity.current_revision_id == applied.revision.revision_id
    assert applied.identity.current_revision_number == 2

    loaded = await repo.get_current_revision(
        logical_plan_id=first.logical_plan_id,
    )
    assert loaded == applied.revision
    assert loaded.previous_revision_id == first.revision_id

    assert loaded.decision_lineage is not None
    assert loaded.decision_lineage.context_hash == instruction.context_hash
    assert loaded.decision_lineage.decision_hash == instruction.decision_hash
    assert loaded.decision_lineage.rationale_hash == instruction.rationale_hash
    assert loaded.decision_lineage.instruction_hash == instruction.content_hash

    assert [
        (item.occurrence_id, item.lineage_kind)
        for item in loaded.occurrences
    ] == [
        ("pt-occ:one", OccurrenceLineageKind.PRESERVED),
        ("pt-occ:three", OccurrenceLineageKind.NEW),
    ]

    assert await repo.get_revision(revision_id=first.revision_id) == first
    assert db.session.scalar(
        select(PlanningPlanRevisionRow.canonical_contract_json).where(
            PlanningPlanRevisionRow.revision_id == first.revision_id
        )
    ) == old_json

    assert db.commit_count == 0


@pytest.mark.asyncio
async def test_p1_5_application_append_rejects_real_stale_current_pointer(
    db,
    ids,
):
    repo = SqlAlchemyAuthoritativePlanRevisionRepository(
        db,
        source_hash_provider=StaticHashProvider("c" * 64),
    )
    first = baseline(ids)
    await repo.adopt_current_state(
        binding=binding(ids),
        revision=first,
    )

    first_artifact = create_workout_plan_contract_artifact(
        plan_id=first.logical_plan_id,
        revision_id="artifact-p1-5-current",
        contract_schema_version="0.1",
        contract_json='{"blocks":[],"plan":"current-second"}',
        stable_occurrence_ids=(
            "pt-occ:one",
            "pt-occ:three",
        ),
    )
    first_instruction = finalize_plan_mutation_instruction(
        instruction_id="instruction-p1-5-current",
        operation=PlanMutationOperation.MODIFY,
        decision_hash="1" * 64,
        rationale_hash="2" * 64,
        context_hash="3" * 64,
        selected_action_id="action-current",
        plan_id=first.logical_plan_id,
        expected_current_revision_id=first.revision_id,
        new_plan_artifact=first_artifact,
        occurrence_identity_policy=(
            OccurrenceIdentityPolicy.PRESERVE_UNCHANGED
        ),
        effective_from=dt(12),
        created_at=dt(11),
    )

    current = await apply_authoritative_plan_revision(
        current_revision=first,
        instruction=first_instruction,
        revision_id="pt-plan-rev:p1-5-current",
        repository=repo,
    )

    stale_artifact = create_workout_plan_contract_artifact(
        plan_id=first.logical_plan_id,
        revision_id="artifact-p1-5-stale",
        contract_schema_version="0.1",
        contract_json='{"blocks":[],"plan":"stale-second"}',
        stable_occurrence_ids=(
            "pt-occ:one",
            "pt-occ:four",
        ),
    )
    stale_instruction = finalize_plan_mutation_instruction(
        instruction_id="instruction-p1-5-stale",
        operation=PlanMutationOperation.MODIFY,
        decision_hash="4" * 64,
        rationale_hash="5" * 64,
        context_hash="6" * 64,
        selected_action_id="action-stale",
        plan_id=first.logical_plan_id,
        expected_current_revision_id=first.revision_id,
        new_plan_artifact=stale_artifact,
        occurrence_identity_policy=(
            OccurrenceIdentityPolicy.PRESERVE_UNCHANGED
        ),
        effective_from=dt(13),
        created_at=dt(12),
    )

    with pytest.raises(
        AuthoritativePlanConflictError,
        match="Current revision changed before append",
    ):
        await apply_authoritative_plan_revision(
            current_revision=first,
            instruction=stale_instruction,
            revision_id="pt-plan-rev:p1-5-stale",
            repository=repo,
        )

    loaded = await repo.get_current_revision(
        logical_plan_id=first.logical_plan_id,
    )
    assert loaded == current.revision
    assert loaded.revision_number == 2
    assert db.commit_count == 0
