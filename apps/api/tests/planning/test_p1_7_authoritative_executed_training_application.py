from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.planning.application.build_authoritative_executed_training import (
    AuthoritativeExecutedTrainingNotFound,
    AuthoritativeExecutedTrainingSourceDrift,
    AuthoritativeExecutedTrainingSourceInvalid,
    build_authoritative_executed_training_with_repository,
)


UTC = timezone.utc

ATHLETE_ID = "11111111-1111-4111-8111-111111111111"
SESSION_ID = "22222222-2222-4222-8222-222222222222"
SOURCE_ID = "33333333-3333-4333-8333-333333333333"
LOGICAL_ID = f"planned-workout:{SOURCE_ID}"

PLAN_HASH = "a" * 64
SESSION_HASH = "b" * 64
REVISION_HASH = "c" * 64
LINK_HASH = "d" * 64

OBSERVED_AT = datetime(
    2026, 10, 19, 12, 0, tzinfo=UTC
)
LINK_CREATED_AT = datetime(
    2026, 10, 19, 13, 0, tzinfo=UTC
)
CREATED_AT = datetime(
    2026, 10, 19, 13, 10, tzinfo=UTC
)


def plan_link(
    *,
    athlete_id=ATHLETE_ID,
    valid_hash=True,
):
    return SimpleNamespace(
        link_id="pt-exec-link:p1-7",
        athlete_id=athlete_id,
        logical_plan_id=LOGICAL_ID,
        observed_revision_id="pt-plan-rev:p1-7",
        workout_session_id=SESSION_ID,
        source_workout_id=SOURCE_ID,
        link_basis=SimpleNamespace(
            value="exact_provider_id"
        ),
        provider_target_id="target-1",
        source_workout_content_hash=PLAN_HASH,
        session_source_content_hash=SESSION_HASH,
        observed_revision_content_hash=REVISION_HASH,
        plan_content_at_execution_status="unverified",
        temporal_match_used=False,
        created_at=LINK_CREATED_AT,
        content_hash=LINK_HASH,
        verify_content_hash=lambda: valid_hash,
    )


def locked(
    *,
    plan_hash=PLAN_HASH,
    session_hash=SESSION_HASH,
    duration_sec=3600,
):
    return SimpleNamespace(
        session_snapshot={
            "id": SESSION_ID,
            "user_id": ATHLETE_ID,
            "sport": "RUNNING",
            "started_at": (
                "2026-10-19T12:00:00+00:00"
            ),
            "duration_sec": duration_sec,
        },
        source_workout_snapshot={
            "id": SOURCE_ID,
            "user_id": ATHLETE_ID,
            "sport": "RUNNING",
        },
        source_workout_content_hash=plan_hash,
        session_source_content_hash=session_hash,
    )


class FakeExecutionRepository:
    def __init__(self, value):
        self.value = value
        self.calls = []

    async def get_by_session(
        self,
        *,
        workout_session_id,
    ):
        self.calls.append(workout_session_id)
        return self.value


class FakeOccurrenceRepository:
    def __init__(self, values=()):
        self.values = tuple(values)
        self.calls = []

    async def list_by_plan_execution_link(
        self,
        *,
        plan_execution_link_id,
    ):
        self.calls.append(plan_execution_link_id)
        return self.values


class FakeExecutionSource:
    def __init__(self, value):
        self.value = value
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
        return self.value


class FakeSession:
    def __init__(self, *, commit_error=None):
        self.commit_count = 0
        self.rollback_count = 0
        self.commit_error = commit_error

    async def commit(self):
        self.commit_count += 1
        if self.commit_error is not None:
            raise self.commit_error

    async def rollback(self):
        self.rollback_count += 1


@pytest.mark.asyncio
async def test_builds_session_level_authoritative_evidence():
    execution_repository = FakeExecutionRepository(
        plan_link()
    )
    occurrence_repository = FakeOccurrenceRepository()
    source = FakeExecutionSource(locked())
    session = FakeSession()

    artifact = (
        await build_authoritative_executed_training_with_repository(
            athlete_id=ATHLETE_ID,
            workout_session_id=SESSION_ID,
            execution_link_repository=execution_repository,
            occurrence_execution_repository=(
                occurrence_repository
            ),
            execution_source=source,
            session=session,
            created_at=CREATED_AT,
            id_factory=lambda: "artifact",
        )
    )

    assert execution_repository.calls == [SESSION_ID]
    assert source.calls == [
        (
            ATHLETE_ID,
            SOURCE_ID,
            SESSION_ID,
        )
    ]
    assert occurrence_repository.calls == [
        "pt-exec-link:p1-7"
    ]

    assert artifact.athlete_id == ATHLETE_ID
    assert artifact.workout_session_id == SESSION_ID
    assert artifact.logical_plan_id == LOGICAL_ID
    assert artifact.observed_at == OBSERVED_AT
    assert artifact.modality_key == "RUNNING"
    assert artifact.duration_status.value == "known"
    assert artifact.duration_s == 3600

    assert artifact.occurrence_associations == ()
    assert artifact.occurrence_alignment_verified is False
    assert artifact.phase_alignment_verified is False
    assert artifact.verify_content_hash() is True

    assert session.commit_count == 1
    assert session.rollback_count == 0


@pytest.mark.asyncio
async def test_missing_duration_remains_unknown_not_zero():
    session = FakeSession()

    artifact = (
        await build_authoritative_executed_training_with_repository(
            athlete_id=ATHLETE_ID,
            workout_session_id=SESSION_ID,
            execution_link_repository=(
                FakeExecutionRepository(plan_link())
            ),
            occurrence_execution_repository=(
                FakeOccurrenceRepository()
            ),
            execution_source=(
                FakeExecutionSource(
                    locked(duration_sec=None)
                )
            ),
            session=session,
            created_at=CREATED_AT,
        )
    )

    assert artifact.duration_status.value == "unknown"
    assert artifact.duration_s is None
    assert session.commit_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("plan_hash", "session_hash", "message"),
    [
        (
            "9" * 64,
            SESSION_HASH,
            "Plan source changed",
        ),
        (
            PLAN_HASH,
            "8" * 64,
            "Workout session source changed",
        ),
    ],
)
async def test_current_source_drift_fails_closed(
    plan_hash,
    session_hash,
    message,
):
    session = FakeSession()

    with pytest.raises(
        AuthoritativeExecutedTrainingSourceDrift,
        match=message,
    ):
        await build_authoritative_executed_training_with_repository(
            athlete_id=ATHLETE_ID,
            workout_session_id=SESSION_ID,
            execution_link_repository=(
                FakeExecutionRepository(plan_link())
            ),
            occurrence_execution_repository=(
                FakeOccurrenceRepository()
            ),
            execution_source=(
                FakeExecutionSource(
                    locked(
                        plan_hash=plan_hash,
                        session_hash=session_hash,
                    )
                )
            ),
            session=session,
            created_at=CREATED_AT,
        )

    assert session.commit_count == 0
    assert session.rollback_count == 1


@pytest.mark.asyncio
async def test_cross_athlete_link_is_not_disclosed():
    session = FakeSession()

    with pytest.raises(
        AuthoritativeExecutedTrainingNotFound
    ):
        await build_authoritative_executed_training_with_repository(
            athlete_id=ATHLETE_ID,
            workout_session_id=SESSION_ID,
            execution_link_repository=(
                FakeExecutionRepository(
                    plan_link(
                        athlete_id=(
                            "99999999-9999-4999-8999-999999999999"
                        )
                    )
                )
            ),
            occurrence_execution_repository=(
                FakeOccurrenceRepository()
            ),
            execution_source=(
                FakeExecutionSource(locked())
            ),
            session=session,
            created_at=CREATED_AT,
        )

    assert session.commit_count == 0
    assert session.rollback_count == 1


@pytest.mark.asyncio
async def test_invalid_execution_link_hash_fails_closed():
    session = FakeSession()

    with pytest.raises(
        AuthoritativeExecutedTrainingSourceInvalid,
        match="hash does not verify",
    ):
        await build_authoritative_executed_training_with_repository(
            athlete_id=ATHLETE_ID,
            workout_session_id=SESSION_ID,
            execution_link_repository=(
                FakeExecutionRepository(
                    plan_link(valid_hash=False)
                )
            ),
            occurrence_execution_repository=(
                FakeOccurrenceRepository()
            ),
            execution_source=(
                FakeExecutionSource(locked())
            ),
            session=session,
            created_at=CREATED_AT,
        )

    assert session.rollback_count == 1


@pytest.mark.asyncio
async def test_invalid_duration_fails_closed():
    session = FakeSession()

    with pytest.raises(
        AuthoritativeExecutedTrainingSourceInvalid,
        match="duration_sec",
    ):
        await build_authoritative_executed_training_with_repository(
            athlete_id=ATHLETE_ID,
            workout_session_id=SESSION_ID,
            execution_link_repository=(
                FakeExecutionRepository(plan_link())
            ),
            occurrence_execution_repository=(
                FakeOccurrenceRepository()
            ),
            execution_source=(
                FakeExecutionSource(
                    locked(duration_sec=-1)
                )
            ),
            session=session,
            created_at=CREATED_AT,
        )

    assert session.rollback_count == 1


@pytest.mark.asyncio
async def test_naive_started_at_fails_closed():
    bad = locked()
    bad.session_snapshot["started_at"] = (
        "2026-10-19T12:00:00"
    )

    session = FakeSession()

    with pytest.raises(
        AuthoritativeExecutedTrainingSourceInvalid,
        match="offset-aware",
    ):
        await build_authoritative_executed_training_with_repository(
            athlete_id=ATHLETE_ID,
            workout_session_id=SESSION_ID,
            execution_link_repository=(
                FakeExecutionRepository(plan_link())
            ),
            occurrence_execution_repository=(
                FakeOccurrenceRepository()
            ),
            execution_source=FakeExecutionSource(bad),
            session=session,
            created_at=CREATED_AT,
        )

    assert session.rollback_count == 1


@pytest.mark.asyncio
async def test_commit_failure_rolls_back():
    error = RuntimeError("commit failed")
    session = FakeSession(commit_error=error)

    with pytest.raises(
        RuntimeError,
        match="commit failed",
    ):
        await build_authoritative_executed_training_with_repository(
            athlete_id=ATHLETE_ID,
            workout_session_id=SESSION_ID,
            execution_link_repository=(
                FakeExecutionRepository(plan_link())
            ),
            occurrence_execution_repository=(
                FakeOccurrenceRepository()
            ),
            execution_source=(
                FakeExecutionSource(locked())
            ),
            session=session,
            created_at=CREATED_AT,
        )

    assert session.commit_count == 1
    assert session.rollback_count == 1
