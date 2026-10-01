from datetime import date, datetime, timezone
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.services.plan_context import (
    get_plan_context,
)


class FakeDb:
    def __init__(
        self,
        workouts,
        sessions,
        periods,
        objectives,
    ):
        self.results = [
            workouts,
            sessions,
            periods,
            objectives,
        ]

    async def scalars(self, statement):
        return self.results.pop(0)


@pytest.mark.asyncio
async def test_get_plan_context_returns_active_periods_and_current_week():
    period_id = UUID(
        "00000000-0000-0000-0000-000000000101"
    )

    workout_id = UUID(
        "00000000-0000-0000-0000-000000000301"
    )

    user = SimpleNamespace(
        id=UUID(
            "00000000-0000-0000-0000-000000000001"
        )
    )

    workout = SimpleNamespace(
        id=workout_id,
        training_period_id=period_id,
        date=date(2026, 9, 30),
        planned_start_time=datetime(
            2026,
            9,
            30,
            15,
            45,
            tzinfo=timezone.utc,
        ),
        sport=SimpleNamespace(
            value="KAYAK"
        ),
        title="8km kayaking",
        status=SimpleNamespace(
            value="PLANNED"
        ),
        duration_sec=None,
        distance_m=8000.0,
        intensity_type="HEART_RATE_ZONES",
    )

    period = SimpleNamespace(
        id=period_id,
        parent_id=None,
        period_type=SimpleNamespace(
            value="MESOCYCLE"
        ),
        title="Őszi alapozó ciklus 1",
        start_date=date(2026, 9, 28),
        end_date=date(2026, 10, 25),
        description=(
            "4 hetes alapozó ciklus, "
            "állóképességi fókusz."
        ),
        target_load=None,
        load_method=None,
        target_duration_sec=None,
        extra_data={},
    )

    objectives = [
        SimpleNamespace(
            id=UUID(
                "00000000-0000-0000-0000-000000000201"
            ),
            period_id=period_id,
            objective_type=SimpleNamespace(
                value="ENDURANCE"
            ),
            weight=0.6,
        ),
        SimpleNamespace(
            id=UUID(
                "00000000-0000-0000-0000-000000000202"
            ),
            period_id=period_id,
            objective_type=SimpleNamespace(
                value="STRENGTH"
            ),
            weight=0.2,
        ),
        SimpleNamespace(
            id=UUID(
                "00000000-0000-0000-0000-000000000203"
            ),
            period_id=period_id,
            objective_type=SimpleNamespace(
                value="TECHNIQUE"
            ),
            weight=0.2,
        ),
    ]

    db = FakeDb(
        workouts=[workout],
        sessions=[],
        periods=[period],
        objectives=objectives,
    )

    context = await get_plan_context(
        db=db,
        user=user,
        as_of_date=date(2026, 9, 30),
        timezone_name="Europe/Budapest",
    )

    assert context["as_of_date"] == date(
        2026,
        9,
        30,
    )

    assert len(
        context["active_periods"]
    ) == 1

    active_period = context[
        "active_periods"
    ][0]

    assert (
        active_period["period_type"]
        == "MESOCYCLE"
    )

    assert (
        active_period["title"]
        == "Őszi alapozó ciklus 1"
    )

    objective_weights = {
        item["objective_type"]: item["weight"]
        for item in active_period["objectives"]
    }

    assert objective_weights == {
        "ENDURANCE": 0.6,
        "STRENGTH": 0.2,
        "TECHNIQUE": 0.2,
    }

    current_week = context[
        "current_week"
    ]

    assert current_week[
        "week_start"
    ] == date(2026, 9, 28)

    assert current_week[
        "week_end"
    ] == date(2026, 10, 4)

    assert len(
        current_week["planned_workouts"]
    ) == 1

    planned_workout = current_week[
        "planned_workouts"
    ][0]

    assert planned_workout == {
        "id": str(workout_id),
        "training_period_id": str(
            period_id
        ),
        "date": date(2026, 9, 30),
        "planned_start_time": datetime(
            2026,
            9,
            30,
            15,
            45,
            tzinfo=timezone.utc,
        ),
        "sport": "KAYAK",
        "title": "8km kayaking",
        "status": "PLANNED",
        "duration_sec": None,
        "distance_m": 8000.0,
        "intensity_type": (
            "HEART_RATE_ZONES"
        ),
        "execution": {
            "has_actual": False,
            "actual_session_count": 0,
            "session_id": None,
            "link_source": None,
            "actual_started_at": None,
            "actual_duration_sec": None,
            "actual_distance_m": None,
            "actual_cardio_load": None,
        },
    }

@pytest.mark.asyncio
async def test_get_plan_context_keeps_weekly_workouts_without_active_period():
    workout_id = UUID(
        "00000000-0000-0000-0000-000000000401"
    )

    user = SimpleNamespace(
        id=UUID(
            "00000000-0000-0000-0000-000000000001"
        )
    )

    workout = SimpleNamespace(
        id=workout_id,
        training_period_id=None,
        date=date(2026, 9, 30),
        planned_start_time=datetime(
            2026,
            9,
            30,
            15,
            45,
            tzinfo=timezone.utc,
        ),
        sport=SimpleNamespace(
            value="KAYAK"
        ),
        title="Unscoped kayak session",
        status=SimpleNamespace(
            value="PLANNED"
        ),
        duration_sec=3600,
        distance_m=None,
        intensity_type="HEART_RATE_ZONES",
    )

    db = FakeDb(
        workouts=[workout],
        sessions=[],
        periods=[],
        objectives=[],
    )

    context = await get_plan_context(
        db=db,
        user=user,
        as_of_date=date(2026, 9, 30),
        timezone_name="Europe/Budapest",
    )

    assert context["active_periods"] == []

    assert context["current_week"][
               "week_start"
           ] == date(2026, 9, 28)

    assert context["current_week"][
               "week_end"
           ] == date(2026, 10, 4)

    planned_workouts = context[
        "current_week"
    ]["planned_workouts"]

    assert len(planned_workouts) == 1

    assert planned_workouts[0] == {
        "id": str(workout_id),
        "training_period_id": None,
        "date": date(2026, 9, 30),
        "planned_start_time": datetime(
            2026,
            9,
            30,
            15,
            45,
            tzinfo=timezone.utc,
        ),
        "sport": "KAYAK",
        "title": "Unscoped kayak session",
        "status": "PLANNED",
        "duration_sec": 3600,
        "distance_m": None,
        "intensity_type": (
            "HEART_RATE_ZONES"
        ),
        "execution": {
            "has_actual": False,
            "actual_session_count": 0,
            "session_id": None,
            "link_source": None,
            "actual_started_at": None,
            "actual_duration_sec": None,
            "actual_distance_m": None,
            "actual_cardio_load": None,
        },
    }

@pytest.mark.asyncio
async def test_get_plan_context_excludes_sessions_after_snapshot_date():
    workout_id = UUID(
        "00000000-0000-0000-0000-000000000501"
    )

    user = SimpleNamespace(
        id=UUID(
            "00000000-0000-0000-0000-000000000001"
        )
    )

    workout = SimpleNamespace(
        id=workout_id,
        training_period_id=None,
        date=date(2026, 9, 30),
        planned_start_time=datetime(
            2026,
            9,
            30,
            15,
            45,
            tzinfo=timezone.utc,
        ),
        sport=SimpleNamespace(
            value="KAYAK"
        ),
        title="Historical snapshot test",
        status=SimpleNamespace(
            value="PLANNED"
        ),
        duration_sec=3600,
        distance_m=None,
        intensity_type="HEART_RATE_ZONES",
    )

    same_day_session = SimpleNamespace(
        id=UUID(
            "00000000-0000-0000-0000-000000000601"
        ),
        planned_workout_id=workout_id,
        planned_workout_link_source=SimpleNamespace(
            value="MANUAL_CONFIRMED"
        ),
        started_at=datetime(
            2026,
            9,
            30,
            21,
            0,
            tzinfo=timezone.utc,
        ),
        duration_sec=3500,
        distance_m=7500.0,
        cardio_load=40.0,
    )

    future_session = SimpleNamespace(
        id=UUID(
            "00000000-0000-0000-0000-000000000602"
        ),
        planned_workout_id=workout_id,
        planned_workout_link_source=SimpleNamespace(
            value="MANUAL_CONFIRMED"
        ),
        started_at=datetime(
            2026,
            10,
            1,
            0,
            30,
            tzinfo=timezone.utc,
        ),
        duration_sec=4000,
        distance_m=8200.0,
        cardio_load=50.0,
    )

    db = FakeDb(
        workouts=[workout],
        sessions=[
            same_day_session,
            future_session,
        ],
        periods=[],
        objectives=[],
    )

    context = await get_plan_context(
        db=db,
        user=user,
        as_of_date=date(2026, 9, 30),
        timezone_name="Europe/Budapest",
    )

    execution = context[
        "current_week"
    ]["planned_workouts"][0]["execution"]

    assert execution["has_actual"] is True
    assert execution["actual_session_count"] == 1

    assert execution["session_id"] == str(
        same_day_session.id
    )

    assert (
        execution["actual_started_at"]
        == same_day_session.started_at
    )

    assert execution[
        "actual_cardio_load"
    ] == 40.0