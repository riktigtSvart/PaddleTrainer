from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.planning.application.link_authoritative_occurrence_execution import (
    AuthoritativeOccurrenceExecutionPlanLinkNotFound,
    AuthoritativeOccurrenceExecutionStateError,
    link_authoritative_occurrence_execution_with_repository,
)
from app.planning.domain.occurrence_execution.models import (
    OccurrenceExecutionCandidateEvidence,
    OccurrenceExecutionConfirmation,
    OccurrenceExecutionConflictError,
    OccurrenceExecutionNotEligible,
    finalize_authoritative_occurrence_execution_link,
)


UTC = timezone.utc

ATHLETE_ID = "11111111-1111-4111-8111-111111111111"
SESSION_ID = "22222222-2222-4222-8222-222222222222"
LOGICAL_PLAN_ID = "planned-workout:33333333-3333-4333-8333-333333333333"
REVISION_ID = "pt-plan-rev:observed"
PLAN_EXECUTION_LINK_ID = "pt-exec-link:observed"
OCCURRENCE_ID = "pt-occ:1"
CAPTURE_OCCURRENCE_ID = "capture-occurrence-1"
ARTIFACT_ID = "phase_reconciliation_artifact_1"
HYPOTHESIS_ID = "phase_path_1"
STABLE_OCCURRENCE_ID = "phase-source-occurrence_1"

SESSION_HASH = "a" * 64
PLAN_HASH = "b" * 64
REVISION_HASH = "c" * 64

NOW = datetime(2026, 10, 19, 14, 0, tzinfo=UTC)


def plan_execution_link(*, valid_hash=True):
    return SimpleNamespace(
        link_id=PLAN_EXECUTION_LINK_ID,
        athlete_id=ATHLETE_ID,
        logical_plan_id=LOGICAL_PLAN_ID,
        observed_revision_id=REVISION_ID,
        observed_revision_content_hash=REVISION_HASH,
        workout_session_id=SESSION_ID,
        source_workout_content_hash=PLAN_HASH,
        session_source_content_hash=SESSION_HASH,
        plan_content_at_execution_status="unverified",
        temporal_match_used=False,
        verify_content_hash=lambda: valid_hash,
    )


def observed_revision():
    return SimpleNamespace(
        revision_id=REVISION_ID,
        logical_plan_id=LOGICAL_PLAN_ID,
        athlete_id=ATHLETE_ID,
        content_hash=REVISION_HASH,
        occurrences=(
            SimpleNamespace(
                occurrence_id=OCCURRENCE_ID,
                source_capture_occurrence_id=(
                    CAPTURE_OCCURRENCE_ID
                ),
            ),
        ),
        verify_content_hash=lambda: True,
        verify_contract_hash=lambda: True,
    )


def candidate():
    return OccurrenceExecutionCandidateEvidence(
        phase_reconciliation_artifact_id=ARTIFACT_ID,
        phase_reconciliation_rules_version=(
            "phase-reconciliation-0.1-draft2"
        ),
        session_source_content_hash=SESSION_HASH,
        plan_source_content_hash=PLAN_HASH,
        stable_source_occurrence_id=STABLE_OCCURRENCE_ID,
        captured_contract_occurrence_id=(
            CAPTURE_OCCURRENCE_ID
        ),
        hypothesis_id=HYPOTHESIS_ID,
        candidate_start_window_s=(10.0, 12.0),
        candidate_completion_window_s=(70.0, 72.0),
        clock_domain="NATIVE_INDEX_CANDIDATE",
    )


def existing_link():
    confirmation = OccurrenceExecutionConfirmation(
        confirmation_id="pt-occ-exec-confirmation:existing",
        athlete_id=ATHLETE_ID,
        workout_session_id=SESSION_ID,
        authoritative_occurrence_id=OCCURRENCE_ID,
        phase_reconciliation_artifact_id=ARTIFACT_ID,
        hypothesis_id=HYPOTHESIS_ID,
        stable_source_occurrence_id=STABLE_OCCURRENCE_ID,
        submitted_at=NOW,
        acknowledges_candidate_boundaries=True,
        acknowledges_not_provider_verified=True,
    )
    return finalize_authoritative_occurrence_execution_link(
        link_id="pt-occ-exec-link:existing",
        plan_execution_link=plan_execution_link(),
        observed_revision=observed_revision(),
        candidate=candidate(),
        confirmation=confirmation,
        created_at=NOW,
    )


class FakeExecutionLinkRepository:
    def __init__(self, value):
        self.value = value
        self.calls = []

    async def get_by_session(self, *, workout_session_id):
        self.calls.append(workout_session_id)
        return self.value


class FakeRevisionRepository:
    def __init__(self, value):
        self.value = value
        self.calls = []

    async def get_revision(self, *, revision_id):
        self.calls.append(revision_id)
        return self.value


class FakeOccurrenceRepository:
    def __init__(self, *, existing=None, save_error=None):
        self.existing = existing
        self.save_error = save_error
        self.lookups = []
        self.saved = []

    async def get_by_occurrence(
        self,
        *,
        plan_execution_link_id,
        authoritative_occurrence_id,
    ):
        self.lookups.append(
            (
                plan_execution_link_id,
                authoritative_occurrence_id,
            )
        )
        return self.existing

    async def save(self, link):
        if self.save_error is not None:
            raise self.save_error
        self.saved.append(link)
        return link


class FakeCandidateProvider:
    def __init__(self, value=None):
        self.value = value or candidate()
        self.calls = []

    async def __call__(
        self,
        *,
        hypothesis_id,
        stable_source_occurrence_id,
    ):
        self.calls.append(
            (
                hypothesis_id,
                stable_source_occurrence_id,
            )
        )
        return self.value


class ExplodingCandidateProvider:
    async def __call__(self, **kwargs):
        raise AssertionError(
            "Idempotent retry must not recapture candidate evidence."
        )


class FakeSession:
    def __init__(self):
        self.commit_count = 0
        self.rollback_count = 0

    async def commit(self):
        self.commit_count += 1

    async def rollback(self):
        self.rollback_count += 1


def ids():
    values = iter(("confirmation", "link"))
    return lambda: next(values)


@pytest.mark.asyncio
async def test_persists_explicit_candidate_occurrence_binding():
    execution_links = FakeExecutionLinkRepository(
        plan_execution_link()
    )
    revisions = FakeRevisionRepository(observed_revision())
    occurrence_links = FakeOccurrenceRepository()
    provider = FakeCandidateProvider()
    session = FakeSession()

    result = (
        await link_authoritative_occurrence_execution_with_repository(
            athlete_id=ATHLETE_ID,
            logical_plan_id=LOGICAL_PLAN_ID,
            workout_session_id=SESSION_ID,
            authoritative_occurrence_id=OCCURRENCE_ID,
            hypothesis_id=HYPOTHESIS_ID,
            stable_source_occurrence_id=STABLE_OCCURRENCE_ID,
            acknowledges_candidate_boundaries=True,
            acknowledges_not_provider_verified=True,
            execution_link_repository=execution_links,
            revision_repository=revisions,
            occurrence_execution_repository=occurrence_links,
            candidate_provider=provider,
            session=session,
            submitted_at=NOW,
            created_at=NOW,
            id_factory=ids(),
        )
    )

    assert revisions.calls == [REVISION_ID]
    assert provider.calls == [
        (HYPOTHESIS_ID, STABLE_OCCURRENCE_ID)
    ]
    assert occurrence_links.saved == [result]

    assert result.plan_execution_link_id == (
        PLAN_EXECUTION_LINK_ID
    )
    assert result.observed_revision_id == REVISION_ID
    assert result.authoritative_occurrence_id == OCCURRENCE_ID
    assert result.hypothesis_id == HYPOTHESIS_ID
    assert result.stable_source_occurrence_id == (
        STABLE_OCCURRENCE_ID
    )

    assert result.occurrence_alignment_status == (
        "user_confirmed_candidate_segment"
    )
    assert result.plan_content_at_execution_status == "unverified"
    assert result.provider_event_verified is False
    assert result.clock_alignment_verified is False
    assert result.actual_boundary_verified is False
    assert result.temporal_match_used is False

    assert session.commit_count == 1
    assert session.rollback_count == 0


@pytest.mark.asyncio
async def test_retry_returns_existing_without_candidate_recapture():
    existing = existing_link()
    occurrence_links = FakeOccurrenceRepository(
        existing=existing
    )
    revisions = FakeRevisionRepository(observed_revision())
    session = FakeSession()

    result = (
        await link_authoritative_occurrence_execution_with_repository(
            athlete_id=ATHLETE_ID,
            logical_plan_id=LOGICAL_PLAN_ID,
            workout_session_id=SESSION_ID,
            authoritative_occurrence_id=OCCURRENCE_ID,
            hypothesis_id=HYPOTHESIS_ID,
            stable_source_occurrence_id=STABLE_OCCURRENCE_ID,
            acknowledges_candidate_boundaries=True,
            acknowledges_not_provider_verified=True,
            execution_link_repository=(
                FakeExecutionLinkRepository(
                    plan_execution_link()
                )
            ),
            revision_repository=revisions,
            occurrence_execution_repository=occurrence_links,
            candidate_provider=ExplodingCandidateProvider(),
            session=session,
        )
    )

    assert result is existing
    assert revisions.calls == []
    assert session.commit_count == 1
    assert session.rollback_count == 0


@pytest.mark.asyncio
async def test_retry_with_different_candidate_identity_conflicts():
    existing = existing_link()
    session = FakeSession()

    with pytest.raises(OccurrenceExecutionConflictError):
        await link_authoritative_occurrence_execution_with_repository(
            athlete_id=ATHLETE_ID,
            logical_plan_id=LOGICAL_PLAN_ID,
            workout_session_id=SESSION_ID,
            authoritative_occurrence_id=OCCURRENCE_ID,
            hypothesis_id="phase_path_other",
            stable_source_occurrence_id=STABLE_OCCURRENCE_ID,
            acknowledges_candidate_boundaries=True,
            acknowledges_not_provider_verified=True,
            execution_link_repository=(
                FakeExecutionLinkRepository(
                    plan_execution_link()
                )
            ),
            revision_repository=(
                FakeRevisionRepository(observed_revision())
            ),
            occurrence_execution_repository=(
                FakeOccurrenceRepository(existing=existing)
            ),
            candidate_provider=ExplodingCandidateProvider(),
            session=session,
        )

    assert session.commit_count == 0
    assert session.rollback_count == 1


@pytest.mark.asyncio
async def test_missing_plan_execution_link_is_not_disclosed():
    session = FakeSession()

    with pytest.raises(
        AuthoritativeOccurrenceExecutionPlanLinkNotFound
    ):
        await link_authoritative_occurrence_execution_with_repository(
            athlete_id=ATHLETE_ID,
            logical_plan_id=LOGICAL_PLAN_ID,
            workout_session_id=SESSION_ID,
            authoritative_occurrence_id=OCCURRENCE_ID,
            hypothesis_id=HYPOTHESIS_ID,
            stable_source_occurrence_id=STABLE_OCCURRENCE_ID,
            acknowledges_candidate_boundaries=True,
            acknowledges_not_provider_verified=True,
            execution_link_repository=(
                FakeExecutionLinkRepository(None)
            ),
            revision_repository=(
                FakeRevisionRepository(observed_revision())
            ),
            occurrence_execution_repository=(
                FakeOccurrenceRepository()
            ),
            candidate_provider=ExplodingCandidateProvider(),
            session=session,
        )

    assert session.rollback_count == 1


@pytest.mark.asyncio
async def test_invalid_frozen_execution_link_hash_fails_closed():
    session = FakeSession()

    with pytest.raises(
        AuthoritativeOccurrenceExecutionStateError
    ):
        await link_authoritative_occurrence_execution_with_repository(
            athlete_id=ATHLETE_ID,
            logical_plan_id=LOGICAL_PLAN_ID,
            workout_session_id=SESSION_ID,
            authoritative_occurrence_id=OCCURRENCE_ID,
            hypothesis_id=HYPOTHESIS_ID,
            stable_source_occurrence_id=STABLE_OCCURRENCE_ID,
            acknowledges_candidate_boundaries=True,
            acknowledges_not_provider_verified=True,
            execution_link_repository=(
                FakeExecutionLinkRepository(
                    plan_execution_link(valid_hash=False)
                )
            ),
            revision_repository=(
                FakeRevisionRepository(observed_revision())
            ),
            occurrence_execution_repository=(
                FakeOccurrenceRepository()
            ),
            candidate_provider=ExplodingCandidateProvider(),
            session=session,
        )

    assert session.rollback_count == 1


@pytest.mark.asyncio
async def test_acknowledgements_are_required_even_for_retry():
    session = FakeSession()

    with pytest.raises(OccurrenceExecutionNotEligible):
        await link_authoritative_occurrence_execution_with_repository(
            athlete_id=ATHLETE_ID,
            logical_plan_id=LOGICAL_PLAN_ID,
            workout_session_id=SESSION_ID,
            authoritative_occurrence_id=OCCURRENCE_ID,
            hypothesis_id=HYPOTHESIS_ID,
            stable_source_occurrence_id=STABLE_OCCURRENCE_ID,
            acknowledges_candidate_boundaries=False,
            acknowledges_not_provider_verified=True,
            execution_link_repository=(
                FakeExecutionLinkRepository(
                    plan_execution_link()
                )
            ),
            revision_repository=(
                FakeRevisionRepository(observed_revision())
            ),
            occurrence_execution_repository=(
                FakeOccurrenceRepository(
                    existing=existing_link()
                )
            ),
            candidate_provider=ExplodingCandidateProvider(),
            session=session,
        )

    assert session.commit_count == 0
    assert session.rollback_count == 1


@pytest.mark.asyncio
async def test_repository_failure_rolls_back():
    session = FakeSession()
    error = RuntimeError("persistence failed")

    with pytest.raises(RuntimeError, match="persistence failed"):
        await link_authoritative_occurrence_execution_with_repository(
            athlete_id=ATHLETE_ID,
            logical_plan_id=LOGICAL_PLAN_ID,
            workout_session_id=SESSION_ID,
            authoritative_occurrence_id=OCCURRENCE_ID,
            hypothesis_id=HYPOTHESIS_ID,
            stable_source_occurrence_id=STABLE_OCCURRENCE_ID,
            acknowledges_candidate_boundaries=True,
            acknowledges_not_provider_verified=True,
            execution_link_repository=(
                FakeExecutionLinkRepository(
                    plan_execution_link()
                )
            ),
            revision_repository=(
                FakeRevisionRepository(observed_revision())
            ),
            occurrence_execution_repository=(
                FakeOccurrenceRepository(save_error=error)
            ),
            candidate_provider=FakeCandidateProvider(),
            session=session,
            submitted_at=NOW,
            created_at=NOW,
            id_factory=ids(),
        )

    assert session.commit_count == 0
    assert session.rollback_count == 1

@pytest.mark.asyncio
async def test_route_logical_plan_identity_must_match_frozen_link():
    session = FakeSession()

    with pytest.raises(
        AuthoritativeOccurrenceExecutionPlanLinkNotFound
    ):
        await link_authoritative_occurrence_execution_with_repository(
            athlete_id=ATHLETE_ID,
            logical_plan_id="planned-workout:other",
            workout_session_id=SESSION_ID,
            authoritative_occurrence_id=OCCURRENCE_ID,
            hypothesis_id=HYPOTHESIS_ID,
            stable_source_occurrence_id=STABLE_OCCURRENCE_ID,
            acknowledges_candidate_boundaries=True,
            acknowledges_not_provider_verified=True,
            execution_link_repository=(
                FakeExecutionLinkRepository(
                    plan_execution_link()
                )
            ),
            revision_repository=(
                FakeRevisionRepository(observed_revision())
            ),
            occurrence_execution_repository=(
                FakeOccurrenceRepository()
            ),
            candidate_provider=ExplodingCandidateProvider(),
            session=session,
        )

    assert session.commit_count == 0
    assert session.rollback_count == 1

