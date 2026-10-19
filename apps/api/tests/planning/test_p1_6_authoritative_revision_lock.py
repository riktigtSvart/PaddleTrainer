from types import SimpleNamespace
from uuid import UUID

import pytest

from app.planning.infrastructure.repositories.postgres_authoritative_plan_revision import (
    SqlAlchemyAuthoritativePlanRevisionRepository,
)


ATHLETE = UUID(
    "11111111-1111-4111-8111-111111111111"
)
WORKOUT = UUID(
    "33333333-3333-4333-8333-333333333333"
)


class Result:
    def __init__(self, row):
        self.row = row

    def scalar_one_or_none(self):
        return self.row


class CaptureSession:
    def __init__(self, row):
        self.row = row
        self.statement = None

    async def execute(self, statement):
        self.statement = statement
        return Result(self.row)


@pytest.mark.asyncio
async def test_get_plan_for_update_requests_row_lock():
    row = SimpleNamespace(
        logical_plan_id=f"planned-workout:{WORKOUT}",
        athlete_id=ATHLETE,
        source_workout_id=WORKOUT,
        current_revision_id="pt-plan-rev:test",
        current_revision_number=1,
        authority_established_at=None,
    )

    session = CaptureSession(row)
    repo = SqlAlchemyAuthoritativePlanRevisionRepository(
        session
    )

    # authority_established_at is intentionally populated only
    # after statement inspection, because identity validation
    # requires it for an adopted plan.
    from datetime import datetime, timezone
    row.authority_established_at = datetime(
        2026, 10, 19, tzinfo=timezone.utc
    )

    loaded = await repo.get_plan_for_update(
        logical_plan_id=row.logical_plan_id
    )

    assert loaded.logical_plan_id == row.logical_plan_id
    assert session.statement._for_update_arg is not None
