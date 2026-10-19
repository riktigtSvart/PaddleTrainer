from types import SimpleNamespace
from uuid import UUID

import pytest

from app.models.entities import WorkoutLinkSource
from app.services.polar_matching import (
    link_sessions_to_planned_workouts,
)


class _FakeDb:
    def __init__(self, session, planned):
        self.session = session
        self.planned = planned
        self.commit_count = 0

    async def scalars(self, statement):
        return [self.session]

    async def scalar(self, statement):
        return self.planned

    async def commit(self):
        self.commit_count += 1


@pytest.mark.asyncio
async def test_exact_polar_match_records_provider_exact_provenance():
    user_id = UUID(
        "11111111-1111-4111-8111-111111111111"
    )
    workout_id = UUID(
        "33333333-3333-4333-8333-333333333333"
    )

    session = SimpleNamespace(
        id=UUID(
            "22222222-2222-4222-8222-222222222222"
        ),
        user_id=user_id,
        external_provider="POLAR",
        raw_data={
            "trainingTarget": {
                "id": "polar-target-1",
            }
        },
        planned_workout_id=None,
        planned_workout_link_source=None,
    )
    planned = SimpleNamespace(
        id=workout_id,
        user_id=user_id,
        polar_target_id="polar-target-1",
    )
    db = _FakeDb(session, planned)

    result = await link_sessions_to_planned_workouts(
        db,
        SimpleNamespace(id=user_id),
    )

    assert result["linked"] == 1
    assert session.planned_workout_id == workout_id
    assert (
        session.planned_workout_link_source
        == WorkoutLinkSource.PROVIDER_EXACT
    )
    assert db.commit_count == 1
