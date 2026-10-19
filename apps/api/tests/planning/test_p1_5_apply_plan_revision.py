from datetime import datetime, timezone

import pytest

from app.planning.application.apply_plan_revision import (
    AuthoritativePlanRevisionNoChange,
    AuthoritativePlanRevisionStaleCurrent,
    apply_authoritative_plan_revision,
    apply_authoritative_plan_revision_with_repository,
    prepare_authoritative_plan_revision,
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
    RevisionOccurrence,
    finalize_authoritative_plan_identity,
    finalize_authoritative_plan_revision,
)


UTC = timezone.utc


def dt(hour: int) -> datetime:
    return datetime(2026, 10, 19, hour, 0, tzinfo=UTC)


def baseline():
    return finalize_authoritative_plan_revision(
        revision_id="pt-plan-rev:r1",
        logical_plan_id="planned-workout:w1",
        athlete_id="athlete-1",
        revision_number=1,
        previous_revision_id=None,
        origin=PlanRevisionOrigin.ADOPTED_CURRENT_STATE,
        history_claim=PlanHistoryClaim.CURRENT_STATE_BASELINE_ONLY,
        authority_established_at=dt(9),
        effective_from=dt(9),
        created_at=dt(9),
        contract_schema_version="0.1",
        contract_json='{"blocks":[],"plan":"baseline"}',
        occurrences=(
            RevisionOccurrence(
                occurrence_id="pt-occ:o1",
                ordinal=0,
                lineage_kind=OccurrenceLineageKind.NEW,
                source_capture_occurrence_id="capture-o1",
            ),
            RevisionOccurrence(
                occurrence_id="pt-occ:o2",
                ordinal=1,
                lineage_kind=OccurrenceLineageKind.NEW,
                source_capture_occurrence_id="capture-o2",
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


def artifact(
    *,
    contract_json='{"blocks":[],"plan":"updated"}',
    occurrence_ids=("pt-occ:o1", "pt-occ:o3"),
):
    return create_workout_plan_contract_artifact(
        plan_id="planned-workout:w1",
        revision_id="artifact-r2",
        contract_schema_version="0.1",
        contract_json=contract_json,
        stable_occurrence_ids=occurrence_ids,
    )


def instruction(
    *,
    expected_current_revision_id="pt-plan-rev:r1",
    new_artifact=None,
    operation=PlanMutationOperation.MODIFY,
    occurrence_identity_policy=OccurrenceIdentityPolicy.PRESERVE_UNCHANGED,
):
    return finalize_plan_mutation_instruction(
        instruction_id="instruction-1",
        operation=operation,
        decision_hash="d" * 64,
        rationale_hash="e" * 64,
        context_hash="f" * 64,
        selected_action_id="action-1",
        plan_id="planned-workout:w1",
        expected_current_revision_id=expected_current_revision_id,
        new_plan_artifact=new_artifact,
        occurrence_identity_policy=occurrence_identity_policy,
        effective_from=dt(12),
        created_at=dt(11),
    )


def test_prepare_builds_planner_owned_revision_with_lineage():
    current = baseline()
    mutation = instruction(new_artifact=artifact())

    candidate = prepare_authoritative_plan_revision(
        current_revision=current,
        instruction=mutation,
        revision_id="pt-plan-rev:r2",
    )

    assert candidate.revision_number == 2
    assert candidate.previous_revision_id == current.revision_id
    assert candidate.origin == PlanRevisionOrigin.PLANNER_CREATED
    assert (
        candidate.history_claim
        == PlanHistoryClaim.VERIFIED_FROM_AUTHORITY_START
    )
    assert candidate.authority_established_at == current.authority_established_at
    assert candidate.adoption_source is None

    assert candidate.decision_lineage.context_hash == mutation.context_hash
    assert candidate.decision_lineage.decision_hash == mutation.decision_hash
    assert candidate.decision_lineage.rationale_hash == mutation.rationale_hash
    assert candidate.decision_lineage.instruction_hash == mutation.content_hash

    assert [
        (item.occurrence_id, item.lineage_kind)
        for item in candidate.occurrences
    ] == [
        ("pt-occ:o1", OccurrenceLineageKind.PRESERVED),
        ("pt-occ:o3", OccurrenceLineageKind.NEW),
    ]
    assert all(
        item.source_capture_occurrence_id is None
        for item in candidate.occurrences
    )


def test_prepare_rejects_stale_expected_current_revision():
    with pytest.raises(AuthoritativePlanRevisionStaleCurrent):
        prepare_authoritative_plan_revision(
            current_revision=baseline(),
            instruction=instruction(
                expected_current_revision_id="pt-plan-rev:stale",
                new_artifact=artifact(),
            ),
            revision_id="pt-plan-rev:r2",
        )


def test_prepare_rejects_identical_contract_as_no_change():
    current = baseline()
    same = artifact(
        contract_json=current.canonical_contract_json,
        occurrence_ids=("pt-occ:o1", "pt-occ:o2"),
    )

    with pytest.raises(AuthoritativePlanRevisionNoChange):
        prepare_authoritative_plan_revision(
            current_revision=current,
            instruction=instruction(new_artifact=same),
            revision_id="pt-plan-rev:r2",
        )


def test_prepare_rejects_explicit_no_change_instruction():
    with pytest.raises(AuthoritativePlanRevisionNoChange):
        prepare_authoritative_plan_revision(
            current_revision=baseline(),
            instruction=instruction(
                new_artifact=None,
                operation=PlanMutationOperation.NO_CHANGE,
            ),
            revision_id="pt-plan-rev:r2",
        )

class RecordingRepository:
    def __init__(self):
        self.expected_current_revision_id = None
        self.revision = None

    async def append_revision(
        self,
        *,
        expected_current_revision_id,
        revision,
    ):
        self.expected_current_revision_id = expected_current_revision_id
        self.revision = revision
        return finalize_authoritative_plan_identity(
            logical_plan_id=revision.logical_plan_id,
            athlete_id=revision.athlete_id,
            source_workout_id="w1",
            current_revision_id=revision.revision_id,
            current_revision_number=revision.revision_number,
            authority_established_at=revision.authority_established_at,
        )


class ConcurrentStaleRepository:
    async def append_revision(
        self,
        *,
        expected_current_revision_id,
        revision,
    ):
        raise AuthoritativePlanConflictError(
            "Current revision changed before append."
        )


@pytest.mark.asyncio
async def test_apply_appends_prepared_revision_using_current_pointer():
    current = baseline()
    mutation = instruction(new_artifact=artifact())
    repository = RecordingRepository()

    applied = await apply_authoritative_plan_revision(
        current_revision=current,
        instruction=mutation,
        revision_id="pt-plan-rev:r2",
        repository=repository,
    )

    assert (
        repository.expected_current_revision_id
        == current.revision_id
    )
    assert repository.revision == applied.revision
    assert applied.revision.revision_number == 2
    assert (
        applied.identity.current_revision_id
        == applied.revision.revision_id
    )
    assert applied.identity.current_revision_number == 2


@pytest.mark.asyncio
async def test_apply_propagates_concurrent_stale_pointer_conflict():
    with pytest.raises(
        AuthoritativePlanConflictError,
        match="Current revision changed before append",
    ):
        await apply_authoritative_plan_revision(
            current_revision=baseline(),
            instruction=instruction(new_artifact=artifact()),
            revision_id="pt-plan-rev:r2",
            repository=ConcurrentStaleRepository(),
        )

def test_prepare_rejects_unsupported_occurrence_identity_policy():
    with pytest.raises(
        ValueError,
        match="only supports PRESERVE_UNCHANGED",
    ):
        prepare_authoritative_plan_revision(
            current_revision=baseline(),
            instruction=instruction(
                new_artifact=artifact(),
                occurrence_identity_policy=(
                    OccurrenceIdentityPolicy.NEW_FOR_NEW_OCCURRENCES
                ),
            ),
            revision_id="pt-plan-rev:r2",
        )

class RecordingTransactionSession:
    def __init__(self, *, fail_commit=False):
        self.commit_count = 0
        self.rollback_count = 0
        self.fail_commit = fail_commit

    async def commit(self):
        self.commit_count += 1
        if self.fail_commit:
            raise RuntimeError("commit failed")

    async def rollback(self):
        self.rollback_count += 1


class TransactionRepository(RecordingRepository):
    def __init__(self, current_revision, *, fail_append=False):
        super().__init__()
        self.current_revision = current_revision
        self.fail_append = fail_append
        self.get_current_calls = []

    async def get_current_revision(self, *, logical_plan_id):
        self.get_current_calls.append(logical_plan_id)
        return self.current_revision

    async def append_revision(
        self,
        *,
        expected_current_revision_id,
        revision,
    ):
        if self.fail_append:
            raise AuthoritativePlanConflictError(
                "Current revision changed before append."
            )
        return await super().append_revision(
            expected_current_revision_id=expected_current_revision_id,
            revision=revision,
        )


@pytest.mark.asyncio
async def test_transactional_apply_commits_once_after_successful_append():
    current = baseline()
    repository = TransactionRepository(current)
    session = RecordingTransactionSession()

    applied = await apply_authoritative_plan_revision_with_repository(
        instruction=instruction(new_artifact=artifact()),
        revision_id="pt-plan-rev:r2",
        repository=repository,
        session=session,
    )

    assert repository.get_current_calls == [current.logical_plan_id]
    assert repository.expected_current_revision_id == current.revision_id
    assert applied.identity.current_revision_id == "pt-plan-rev:r2"
    assert session.commit_count == 1
    assert session.rollback_count == 0


@pytest.mark.asyncio
async def test_transactional_apply_rolls_back_when_append_conflicts():
    current = baseline()
    repository = TransactionRepository(
        current,
        fail_append=True,
    )
    session = RecordingTransactionSession()

    with pytest.raises(
        AuthoritativePlanConflictError,
        match="Current revision changed before append",
    ):
        await apply_authoritative_plan_revision_with_repository(
            instruction=instruction(new_artifact=artifact()),
            revision_id="pt-plan-rev:r2",
            repository=repository,
            session=session,
        )

    assert session.commit_count == 0
    assert session.rollback_count == 1


@pytest.mark.asyncio
async def test_transactional_apply_rolls_back_when_commit_fails():
    current = baseline()
    repository = TransactionRepository(current)
    session = RecordingTransactionSession(fail_commit=True)

    with pytest.raises(RuntimeError, match="commit failed"):
        await apply_authoritative_plan_revision_with_repository(
            instruction=instruction(new_artifact=artifact()),
            revision_id="pt-plan-rev:r2",
            repository=repository,
            session=session,
        )

    assert session.commit_count == 1
    assert session.rollback_count == 1

