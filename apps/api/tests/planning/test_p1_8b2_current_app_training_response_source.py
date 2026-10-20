from datetime import datetime, timezone
from enum import Enum
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.planning.domain.response_evidence import (
    TrainingResponseKind,
    TrainingResponseTiming,
)
from app.planning.infrastructure.adapters.current_app_training_response_source import (
    ATHLETE_RESPONSE_SOURCE_SCHEMA_V01,
    ATHLETE_RESPONSE_SOURCE_SYSTEM,
    CurrentAppLockedAthleteResponseSource,
    TrainingResponseSourceInvalid,
    TrainingResponseSourceNotFound,
    TrainingResponseSourceUnlinked,
)


UTC = timezone.utc

ATHLETE_ID = (
    "11111111-1111-4111-8111-111111111111"
)

SESSION_ID = (
    "22222222-2222-4222-8222-222222222222"
)

RESPONSE_ID = (
    "33333333-3333-4333-8333-333333333333"
)


class SourceTiming(str, Enum):
    IMMEDIATE = "IMMEDIATE"
    SAME_DAY = "SAME_DAY"
    NEXT_MORNING = "NEXT_MORNING"
    FOLLOW_UP = "FOLLOW_UP"


def dt(hour: int) -> datetime:
    return datetime(
        2026,
        10,
        20,
        hour,
        tzinfo=UTC,
    )


def response_row(**updates):
    values = dict(
        id=UUID(RESPONSE_ID),
        user_id=UUID(ATHLETE_ID),
        workout_session_id=UUID(SESSION_ID),
        response_timing=SourceTiming.SAME_DAY,
        recorded_at=dt(8),
        fatigue_score=6.0,
        soreness_score=None,
        recovery_score=7.0,
        energy_score=5.0,
        performance_metric="500m_time",
        performance_delta_percent=-1.5,
        extra_data={"note": "felt controlled"},
        created_at=dt(10),
    )
    values.update(updates)
    return SimpleNamespace(**values)


def workout_row(**updates):
    values = dict(
        id=UUID(SESSION_ID),
        user_id=UUID(ATHLETE_ID),
    )
    values.update(updates)
    return SimpleNamespace(**values)


class Result:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class FakeSession:
    def __init__(self, *values):
        self._values = list(values)
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)

        if not self._values:
            raise AssertionError(
                "Unexpected extra database query."
            )

        return Result(
            self._values.pop(0)
        )


@pytest.mark.asyncio
async def test_capture_uses_explicit_owned_session_identity_and_locks_both_rows():
    db = FakeSession(
        response_row(),
        workout_row(),
    )

    capture = await (
        CurrentAppLockedAthleteResponseSource()
        .lock_and_capture(
            db,
            athlete_id=ATHLETE_ID,
            response_source_id=RESPONSE_ID,
        )
    )

    assert capture.athlete_id == ATHLETE_ID
    assert capture.workout_session_id == SESSION_ID
    assert capture.response_source_id == RESPONSE_ID

    assert (
        capture.response_kind
        == TrainingResponseKind.SESSION_FEEDBACK
    )
    assert (
        capture.response_timing
        == TrainingResponseTiming.SAME_DAY
    )

    assert len(db.statements) == 2

    response_sql = str(db.statements[0])
    workout_sql = str(db.statements[1])

    assert "athlete_responses.id" in response_sql
    assert "athlete_responses.user_id" in response_sql

    assert "workout_sessions.id" in workout_sql
    assert "workout_sessions.user_id" in workout_sql


@pytest.mark.asyncio
async def test_capture_preserves_cutoff_semantics_for_late_database_creation():
    db = FakeSession(
        response_row(
            recorded_at=dt(8),
            created_at=dt(12),
        ),
        workout_row(),
    )

    capture = await (
        CurrentAppLockedAthleteResponseSource()
        .lock_and_capture(
            db,
            athlete_id=ATHLETE_ID,
            response_source_id=RESPONSE_ID,
        )
    )

    assert capture.observed_at == dt(8)
    assert capture.available_at == dt(12)


@pytest.mark.asyncio
async def test_capture_never_makes_availability_earlier_than_observation():
    db = FakeSession(
        response_row(
            recorded_at=dt(12),
            created_at=dt(8),
        ),
        workout_row(),
    )

    capture = await (
        CurrentAppLockedAthleteResponseSource()
        .lock_and_capture(
            db,
            athlete_id=ATHLETE_ID,
            response_source_id=RESPONSE_ID,
        )
    )

    assert capture.observed_at == dt(12)
    assert capture.available_at == dt(12)


@pytest.mark.asyncio
async def test_capture_promotes_only_whitelisted_self_report_scores():
    db = FakeSession(
        response_row(),
        workout_row(),
    )

    capture = await (
        CurrentAppLockedAthleteResponseSource()
        .lock_and_capture(
            db,
            athlete_id=ATHLETE_ID,
            response_source_id=RESPONSE_ID,
        )
    )

    values = {
        item.metric_key: item.value
        for item in capture.measurements
    }

    assert values == {
        "self_reported_energy_score": 5.0,
        "self_reported_fatigue_score": 6.0,
        "self_reported_recovery_score": 7.0,
    }

    assert "performance_metric" not in values
    assert "performance_delta_percent" not in values
    assert "soreness_score" not in values


@pytest.mark.asyncio
async def test_performance_and_extra_data_change_source_hash_without_becoming_response_measurements():
    first_db = FakeSession(
        response_row(
            performance_delta_percent=-1.5,
            extra_data={"note": "a"},
        ),
        workout_row(),
    )

    second_db = FakeSession(
        response_row(
            performance_delta_percent=-2.0,
            extra_data={"note": "b"},
        ),
        workout_row(),
    )

    adapter = CurrentAppLockedAthleteResponseSource()

    first = await adapter.lock_and_capture(
        first_db,
        athlete_id=ATHLETE_ID,
        response_source_id=RESPONSE_ID,
    )

    second = await adapter.lock_and_capture(
        second_db,
        athlete_id=ATHLETE_ID,
        response_source_id=RESPONSE_ID,
    )

    assert first.measurements == second.measurements
    assert first.source_content_hash != second.source_content_hash


@pytest.mark.asyncio
async def test_capture_rejects_response_without_explicit_session_fk():
    db = FakeSession(
        response_row(
            workout_session_id=None,
        ),
    )

    with pytest.raises(
        TrainingResponseSourceUnlinked,
        match="no explicit workout_session_id",
    ):
        await (
            CurrentAppLockedAthleteResponseSource()
            .lock_and_capture(
                db,
                athlete_id=ATHLETE_ID,
                response_source_id=RESPONSE_ID,
            )
        )

    assert len(db.statements) == 1


@pytest.mark.asyncio
async def test_capture_does_not_disclose_cross_athlete_or_missing_response():
    db = FakeSession(None)

    with pytest.raises(
        TrainingResponseSourceNotFound,
        match="Owned AthleteResponse not found",
    ):
        await (
            CurrentAppLockedAthleteResponseSource()
            .lock_and_capture(
                db,
                athlete_id=ATHLETE_ID,
                response_source_id=RESPONSE_ID,
            )
        )


@pytest.mark.asyncio
async def test_capture_requires_owned_referenced_workout_session():
    db = FakeSession(
        response_row(),
        None,
    )

    with pytest.raises(
        TrainingResponseSourceNotFound,
        match="Owned WorkoutSession",
    ):
        await (
            CurrentAppLockedAthleteResponseSource()
            .lock_and_capture(
                db,
                athlete_id=ATHLETE_ID,
                response_source_id=RESPONSE_ID,
            )
        )


@pytest.mark.asyncio
async def test_capture_rejects_no_promotable_self_report_measurement():
    db = FakeSession(
        response_row(
            fatigue_score=None,
            soreness_score=None,
            recovery_score=None,
            energy_score=None,
        ),
        workout_row(),
    )

    with pytest.raises(
        TrainingResponseSourceInvalid,
        match="no promotable",
    ):
        await (
            CurrentAppLockedAthleteResponseSource()
            .lock_and_capture(
                db,
                athlete_id=ATHLETE_ID,
                response_source_id=RESPONSE_ID,
            )
        )


@pytest.mark.asyncio
async def test_capture_rejects_unknown_response_timing():
    db = FakeSession(
        response_row(
            response_timing="SOME_FUTURE_TIMING",
        ),
        workout_row(),
    )

    with pytest.raises(
        TrainingResponseSourceInvalid,
        match="Unsupported AthleteResponse response_timing",
    ):
        await (
            CurrentAppLockedAthleteResponseSource()
            .lock_and_capture(
                db,
                athlete_id=ATHLETE_ID,
                response_source_id=RESPONSE_ID,
            )
        )


@pytest.mark.asyncio
async def test_capture_source_metadata_is_pinned():
    db = FakeSession(
        response_row(),
        workout_row(),
    )

    capture = await (
        CurrentAppLockedAthleteResponseSource()
        .lock_and_capture(
            db,
            athlete_id=ATHLETE_ID,
            response_source_id=RESPONSE_ID,
        )
    )

    assert (
        capture.source_system
        == ATHLETE_RESPONSE_SOURCE_SYSTEM
    )
    assert capture.source_record_id == RESPONSE_ID
    assert (
        capture.source_record_version
        == ATHLETE_RESPONSE_SOURCE_SCHEMA_V01
    )
    assert len(capture.source_content_hash) == 64
