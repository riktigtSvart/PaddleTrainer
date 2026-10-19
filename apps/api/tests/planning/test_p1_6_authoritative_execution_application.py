from datetime import datetime, timezone

import pytest

from app.planning.application.link_authoritative_execution import (
    AuthoritativeExecutionPlanNotFound,
    link_authoritative_execution_with_repository,
)
from app.planning.domain.execution_link import (
    AuthoritativeExecutionLinkNotEligible,
)
from app.planning.domain.plan_revision.persistence_contract import (
    AdoptionSourceRef,
    OccurrenceLineageKind,
    PlanHistoryClaim,
    PlanRevisionOrigin,
    RevisionOccurrence,
    finalize_authoritative_plan_identity,
    finalize_authoritative_plan_revision,
)
from app.planning.ports.execution_source import (
    LockedExecutionSourceCapture,
)


ATHLETE = "11111111-1111-4111-8111-111111111111"
SESSION = "22222222-2222-4222-8222-222222222222"
WORKOUT = "33333333-3333-4333-8333-333333333333"
LOGICAL = f"planned-workout:{WORKOUT}"
REVISION = "pt-plan-rev:baseline"
NOW = datetime(
    2026, 10, 19, 11, 30, tzinfo=timezone.utc
)


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
        authority_established_at=NOW,
        effective_from=NOW,
        created_at=NOW,
        contract_schema_version="0.1",
        contract_json='{"blocks":[],"plan":"baseline"}',
        occurrences=(
            RevisionOccurrence(
                occurrence_id="pt-occ:one",
                ordinal=0,
                lineage_kind=OccurrenceLineageKind.NEW,
                source_capture_occurrence_id="external-occ-1",
            ),
        ),
        adoption_source=AdoptionSourceRef(
            capture_id="capture-1",
            capture_content_hash="a" * 64,
            source_read_content_hash="b" * 64,
            source_content_sha256="c" * 64,
            external_contract_plan_id="external-plan-1",
            external_contract_plan_revision=1,
        ),
        decision_lineage=None,
    )


def identity(*, athlete_id=ATHLETE):
    return finalize_authoritative_plan_identity(
        logical_plan_id=LOGICAL,
        athlete_id=athlete_id,
        source_workout_id=WORKOUT,
        current_revision_id=REVISION,
        current_revision_number=1,
        authority_established_at=NOW,
    )


def locked_source(
    *,
    link_source=None,
    target_id="target-1",
):
    return LockedExecutionSourceCapture(
        session_snapshot={
            "id": SESSION,
            "user_id": ATHLETE,
            "planned_workout_id": WORKOUT,
            "planned_workout_link_source": link_source,
            "external_provider": "POLAR",
            "external_id": "polar-session-1",
            "sport": "RUNNING",
            "started_at": (
                "2026-10-19T18:47:00+00:00"
            ),
            "raw_data": {
                "trainingTarget": (
                    {}
                    if target_id is None
                    else {"id": target_id}
                )
            },
        },
        source_workout_snapshot={
            "id": WORKOUT,
            "user_id": ATHLETE,
            "sport": "RUNNING",
            "source": "POLAR",
            "polar_target_id": (
                None
                if target_id is None
                else "target-1"
            ),
        },
        source_workout_content_hash="d" * 64,
        session_source_content_hash="e" * 64,
    )


class FakeRevisionRepository:
    def __init__(
        self,
        *,
        plan=None,
        current_revision=None,
    ):
        self.plan = plan
        self.current_revision = current_revision
        self.lock_calls = 0

    async def get_plan_for_update(
        self,
        *,
        logical_plan_id,
    ):
        assert logical_plan_id == LOGICAL
        self.lock_calls += 1
        return self.plan

    async def get_revision(self, *, revision_id):
        assert revision_id == REVISION
        return self.current_revision


class FakeSource:
    def __init__(self, capture):
        self.capture = capture
        self.calls = []

    async def lock_and_capture(
        self,
        session,
        *,
        athlete_id,
        source_workout_id,
        workout_session_id,
    ):
        self.calls.append(
            (
                athlete_id,
                source_workout_id,
                workout_session_id,
            )
        )
        return self.capture


class FakeExecutionRepository:
    def __init__(self, *, error=None, existing=None):
        self.error = error
        self.existing = existing
        self.saved = []

    async def get_by_session(
        self,
        *,
        workout_session_id,
    ):
        return self.existing

    async def save(self, link):
        if self.error is not None:
            raise self.error
        self.saved.append(link)
        return link


class FakeSession:
    def __init__(self, *, commit_error=None):
        self.commits = 0
        self.rollbacks = 0
        self.commit_error = commit_error

    async def commit(self):
        self.commits += 1
        if self.commit_error is not None:
            raise self.commit_error

    async def rollback(self):
        self.rollbacks += 1


@pytest.mark.asyncio
async def test_exact_provider_execution_link_commits_once():
    revisions = FakeRevisionRepository(
        plan=identity(),
        current_revision=revision(),
    )
    source = FakeSource(locked_source())
    links = FakeExecutionRepository()
    session = FakeSession()

    result = (
        await link_authoritative_execution_with_repository(
            athlete_id=ATHLETE,
            logical_plan_id=LOGICAL,
            workout_session_id=SESSION,
            revision_repository=revisions,
            execution_link_repository=links,
            execution_source=source,
            session=session,
            created_at=NOW,
            id_factory=lambda: "test-link",
        )
    )

    assert result.link_id == "pt-exec-link:test-link"
    assert result.observed_revision_id == REVISION
    assert result.provider_target_id == "target-1"
    assert result.link_basis.value == "exact_provider_id"
    assert result.temporal_match_used is False
    assert (
        result.plan_content_at_execution_status
        == "unverified"
    )
    assert result.observed_revision_content_hash == (
        revision().content_hash
    )
    assert result.verify_content_hash()
    assert revisions.lock_calls == 1
    assert session.commits == 1
    assert session.rollbacks == 0


@pytest.mark.asyncio
async def test_manual_confirmed_execution_link_is_allowed():
    source = FakeSource(
        locked_source(
            link_source="MANUAL_CONFIRMED",
            target_id=None,
        )
    )
    links = FakeExecutionRepository()
    session = FakeSession()

    result = (
        await link_authoritative_execution_with_repository(
            athlete_id=ATHLETE,
            logical_plan_id=LOGICAL,
            workout_session_id=SESSION,
            revision_repository=FakeRevisionRepository(
                plan=identity(),
                current_revision=revision(),
            ),
            execution_link_repository=links,
            execution_source=source,
            session=session,
            created_at=NOW,
            id_factory=lambda: "manual",
        )
    )

    assert result.link_basis.value == "manual_confirmed"
    assert result.provider_target_id is None
    assert session.commits == 1
    assert session.rollbacks == 0


@pytest.mark.asyncio
async def test_candidate_only_link_fails_closed_and_rolls_back():
    source = FakeSource(
        locked_source(
            link_source="AUTO_MATCHED",
            target_id=None,
        )
    )
    links = FakeExecutionRepository()
    session = FakeSession()

    with pytest.raises(
        AuthoritativeExecutionLinkNotEligible
    ):
        await link_authoritative_execution_with_repository(
            athlete_id=ATHLETE,
            logical_plan_id=LOGICAL,
            workout_session_id=SESSION,
            revision_repository=FakeRevisionRepository(
                plan=identity(),
                current_revision=revision(),
            ),
            execution_link_repository=links,
            execution_source=source,
            session=session,
            created_at=NOW,
        )

    assert links.saved == []
    assert session.commits == 0
    assert session.rollbacks == 1


@pytest.mark.asyncio
async def test_cross_athlete_plan_is_not_disclosed():
    session = FakeSession()

    with pytest.raises(
        AuthoritativeExecutionPlanNotFound
    ):
        await link_authoritative_execution_with_repository(
            athlete_id=ATHLETE,
            logical_plan_id=LOGICAL,
            workout_session_id=SESSION,
            revision_repository=FakeRevisionRepository(
                plan=identity(
                    athlete_id=(
                        "99999999-9999-4999-8999-999999999999"
                    )
                ),
                current_revision=revision(),
            ),
            execution_link_repository=(
                FakeExecutionRepository()
            ),
            execution_source=FakeSource(
                locked_source()
            ),
            session=session,
        )

    assert session.commits == 0
    assert session.rollbacks == 1


@pytest.mark.asyncio
async def test_repository_failure_rolls_back():
    session = FakeSession()
    error = RuntimeError("persistence failed")

    with pytest.raises(RuntimeError, match="persistence failed"):
        await link_authoritative_execution_with_repository(
            athlete_id=ATHLETE,
            logical_plan_id=LOGICAL,
            workout_session_id=SESSION,
            revision_repository=FakeRevisionRepository(
                plan=identity(),
                current_revision=revision(),
            ),
            execution_link_repository=(
                FakeExecutionRepository(error=error)
            ),
            execution_source=FakeSource(
                locked_source()
            ),
            session=session,
            created_at=NOW,
        )

    assert session.commits == 0
    assert session.rollbacks == 1


@pytest.mark.asyncio
async def test_commit_failure_rolls_back():
    session = FakeSession(
        commit_error=RuntimeError("commit failed")
    )

    with pytest.raises(RuntimeError, match="commit failed"):
        await link_authoritative_execution_with_repository(
            athlete_id=ATHLETE,
            logical_plan_id=LOGICAL,
            workout_session_id=SESSION,
            revision_repository=FakeRevisionRepository(
                plan=identity(),
                current_revision=revision(),
            ),
            execution_link_repository=(
                FakeExecutionRepository()
            ),
            execution_source=FakeSource(
                locked_source()
            ),
            session=session,
            created_at=NOW,
        )

    assert session.commits == 1
    assert session.rollbacks == 1
