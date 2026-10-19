from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base

# Register the core ORM tables referenced by planning foreign keys
# before Base.metadata.create_all() is called.
from app.models import entities as _entities  # noqa: F401

from app.planning.domain.execution_link import (
    ExecutionLinkBasis,
    finalize_authoritative_plan_execution_link,
)
from app.planning.domain.occurrence_execution import (
    OccurrenceExecutionCandidateEvidence,
    OccurrenceExecutionConfirmation,
    OccurrenceExecutionConflictError,
    finalize_authoritative_occurrence_execution_link,
)
from app.planning.domain.plan_revision.persistence_contract import (
    AdoptionSourceRef,
    OccurrenceLineageKind,
    PlanHistoryClaim,
    PlanRevisionOrigin,
    RevisionOccurrence,
    finalize_authoritative_plan_revision,
)
from app.planning.infrastructure.repositories.postgres_authoritative_occurrence_execution import (
    SqlAlchemyAuthoritativeOccurrenceExecutionLinkRepository,
)


UTC = timezone.utc
ATHLETE = str(uuid4())
SESSION = str(uuid4())
SOURCE = str(uuid4())
LOGICAL = f"planned-workout:{SOURCE}"
REVISION = "pt-plan-rev:p1-6c-persistence"
OCCURRENCE = "pt-occ:p1-6c-persistence"
CAPTURED = "occ_capture_p1_6c_persistence"


def dt(hour):
    return datetime(2026, 10, 19, hour, tzinfo=UTC)


class AsyncBridge:
    def __init__(self, session):
        self.session = session

    async def execute(self, statement):
        return self.session.execute(statement)

    def add(self, row):
        self.session.add(row)

    async def flush(self):
        self.session.flush()


def revision():
    return finalize_authoritative_plan_revision(
        revision_id=REVISION,
        logical_plan_id=LOGICAL,
        athlete_id=ATHLETE,
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
        contract_json="{}",
        occurrences=(
            RevisionOccurrence(
                occurrence_id=OCCURRENCE,
                ordinal=0,
                lineage_kind=OccurrenceLineageKind.NEW,
                source_capture_occurrence_id=CAPTURED,
            ),
        ),
        adoption_source=AdoptionSourceRef(
            capture_id="capture-p1-6c-persistence",
            capture_content_hash="1" * 64,
            source_read_content_hash="2" * 64,
            source_content_sha256="3" * 64,
            external_contract_plan_id=(
                "polar-plan-p1-6c-persistence"
            ),
            external_contract_plan_revision=1,
        ),
        decision_lineage=None,
    )


def occurrence_link(
    *,
    link_id="pt-occ-exec-link:persistence",
    hypothesis_suffix="1",
    created_hour=14,
):
    observed = revision()

    plan_execution = (
        finalize_authoritative_plan_execution_link(
            link_id="pt-exec-link:p1-6c-persistence",
            athlete_id=ATHLETE,
            logical_plan_id=LOGICAL,
            observed_revision_id=REVISION,
            workout_session_id=SESSION,
            source_workout_id=SOURCE,
            link_basis=ExecutionLinkBasis.EXACT_PROVIDER_ID,
            provider_target_id="target-p1-6c",
            source_workout_content_hash="a" * 64,
            session_source_content_hash="b" * 64,
            observed_revision_content_hash=(
                observed.content_hash
            ),
            created_at=dt(12),
        )
    )

    candidate = OccurrenceExecutionCandidateEvidence(
        phase_reconciliation_artifact_id=(
            "phase_reconciliation_" + "c" * 64
        ),
        phase_reconciliation_rules_version=(
            "phase-reconciliation-0.1-draft2"
        ),
        session_source_content_hash="b" * 64,
        plan_source_content_hash="a" * 64,
        stable_source_occurrence_id=(
            "phase-source-occurrence_" + "d" * 64
        ),
        captured_contract_occurrence_id=CAPTURED,
        hypothesis_id=(
            "phase_path_" + hypothesis_suffix * 64
        ),
        candidate_start_window_s=(10.0, 12.0),
        candidate_completion_window_s=(70.0, 72.0),
        clock_domain="NATIVE_INDEX_CANDIDATE",
    )

    confirmation = OccurrenceExecutionConfirmation(
        confirmation_id=(
            "pt-occ-exec-confirmation:persistence"
        ),
        athlete_id=ATHLETE,
        workout_session_id=SESSION,
        authoritative_occurrence_id=OCCURRENCE,
        phase_reconciliation_artifact_id=(
            candidate.phase_reconciliation_artifact_id
        ),
        hypothesis_id=candidate.hypothesis_id,
        stable_source_occurrence_id=(
            candidate.stable_source_occurrence_id
        ),
        submitted_at=dt(13),
        acknowledges_candidate_boundaries=True,
        acknowledges_not_provider_verified=True,
    )

    return finalize_authoritative_occurrence_execution_link(
        link_id=link_id,
        plan_execution_link=plan_execution,
        observed_revision=observed,
        candidate=candidate,
        confirmation=confirmation,
        created_at=dt(created_hour),
    )


@pytest.fixture
def repository():
    engine = create_engine("sqlite+pysqlite:///:memory:")

    Base.metadata.create_all(engine)

    # Foreign-key enforcement is intentionally not enabled in this
    # repository serialization test. FK declarations are verified
    # independently by the schema contract.
    with Session(engine, expire_on_commit=False) as sync:
        bridge = AsyncBridge(sync)

        yield (
            SqlAlchemyAuthoritativeOccurrenceExecutionLinkRepository(
                bridge
            ),
            sync,
        )

    engine.dispose()


@pytest.mark.asyncio
async def test_repository_round_trip(repository):
    repo, sync = repository
    original = occurrence_link()

    saved = await repo.save(original)
    sync.commit()

    loaded = await repo.get_by_occurrence(
        plan_execution_link_id=(
            original.plan_execution_link_id
        ),
        authoritative_occurrence_id=(
            original.authoritative_occurrence_id
        ),
    )

    assert saved == original
    assert loaded == original
    assert loaded.verify_content_hash()


@pytest.mark.asyncio
async def test_repository_idempotent_retry_returns_original(
    repository,
):
    repo, sync = repository

    original = occurrence_link()
    await repo.save(original)
    sync.commit()

    retry = occurrence_link(
        link_id="pt-occ-exec-link:retry-id-differs",
        created_hour=15,
    )

    returned = await repo.save(retry)

    assert returned == original


@pytest.mark.asyncio
async def test_repository_rejects_divergent_occurrence_binding(
    repository,
):
    repo, sync = repository

    original = occurrence_link()
    await repo.save(original)
    sync.commit()

    competing = occurrence_link(
        link_id="pt-occ-exec-link:competing",
        hypothesis_suffix="f",
        created_hour=15,
    )

    with pytest.raises(
        OccurrenceExecutionConflictError
    ):
        await repo.save(competing)
