from datetime import datetime
from datetime import timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.integrations.polar.client import PolarClient
from app.models.entities import (
    BlockType,
    ExternalConnection,
    PlannedWorkout,
    Sport,
    User,
    WorkoutBlock,
    WorkoutStatus,
)
from app.services.polar_tokens import get_valid_access_token

POLAR_TARGET_SPORT_MAP = {
    "95": Sport.KAYAK,
    "1": Sport.RUNNING,
}


def _block_type_from_name(
    name: str | None,
) -> BlockType:
    text = (name or "").strip().lower()

    if "warm up" in text or "warmup" in text:
        return BlockType.WARMUP

    if (
        "cool down" in text
        or "cooldown" in text
    ):
        return BlockType.COOLDOWN

    if (
        "recovery" in text
        or "rest" in text
    ):
        return BlockType.RECOVERY

    return BlockType.WORK


def _aware_planned_start(
    value: dict[str, Any] | None,
    timezone_name: str,
) -> datetime | None:
    naive = _polar_datetime(value)

    if naive is None:
        return None

    return naive.replace(
        tzinfo=ZoneInfo(timezone_name)
    )

def _polar_datetime(value: dict[str, Any] | None) -> datetime | None:
    if not value:
        return None

    return datetime(
        year=value["year"],
        month=value["month"],
        day=value["day"],
        hour=value.get("hour", 0),
        minute=value.get("min", 0),
        second=value.get("sec", 0),
    )


def _duration_ms_to_sec(value: int | None) -> int | None:
    if value is None:
        return None

    return int(value / 1000)

async def _replace_workout_blocks(
    db: AsyncSession,
    workout: PlannedWorkout,
    raw_target: dict,
) -> None:
    # Régi blokkok explicit async lekérése.
    # Így új workoutnál sem indul lazy loading.
    old_result = await db.scalars(
        select(WorkoutBlock).where(
            WorkoutBlock.workout_id
            == workout.id
        )
    )

    old_blocks = list(old_result)

    # Először bontjuk a parent-child
    # kapcsolatokat a self-FK miatt.
    for old_block in old_blocks:
        old_block.parent_block_id = None

    await db.flush()

    # Ezután törölhetők a régi blokkok.
    for old_block in old_blocks:
        await db.delete(old_block)

    await db.flush()

    exercises = (
        raw_target.get("exercise") or []
    )

    normalized_blocks = []

    for exercise_index, exercise in enumerate(
        exercises
    ):
        exercise_blocks = normalize_phase_tree(
            exercise.get("phaseOrRepeat")
            or []
        )

        prefix = f"e{exercise_index}:"

        for block in exercise_blocks:
            copied = dict(block)

            copied["key"] = (
                prefix + copied["key"]
            )

            if (
                copied["parent_key"]
                is not None
            ):
                copied["parent_key"] = (
                    prefix
                    + copied["parent_key"]
                )

            normalized_blocks.append(
                copied
            )

    block_ids: dict[str, object] = {}

    for flat_position, block_data in enumerate(
        normalized_blocks
    ):
        parent_id = None

        parent_key = block_data[
            "parent_key"
        ]

        if parent_key is not None:
            parent_id = block_ids.get(
                parent_key
            )

        block = WorkoutBlock(
            workout_id=workout.id,
            parent_block_id=parent_id,
            position=flat_position,
            block_type=BlockType(
                block_data["block_type"]
            ),
            name=block_data["name"],
            duration_sec=block_data[
                "duration_sec"
            ],
            distance_m=block_data[
                "distance_m"
            ],
            intensity_type=block_data[
                "intensity_type"
            ],
            intensity_min=block_data[
                "intensity_min"
            ],
            intensity_max=block_data[
                "intensity_max"
            ],
            repeat_count=block_data[
                "repeat_count"
            ],
        )

        db.add(block)

        # Az ID kellhet a következő
        # child blokk parent_id-jához.
        await db.flush()

        block_ids[
            block_data["key"]
        ] = block.id

def normalize_phase_tree(
    phases: list[dict],
    parent_key: str | None = None,
) -> list[dict]:
    result = []

    for index, phase in enumerate(phases):
        key = (
            f"{parent_key}.{index}"
            if parent_key is not None
            else str(index)
        )

        children = phase.get("phaseOrRepeat") or []
        repeat_count = phase.get("repeatCount")

        # Repeat container
        if children:
            result.append(
                {
                    "key": key,
                    "parent_key": parent_key,
                    "position": index,
                    "block_type": "REPEAT",
                    "name": phase.get("name") or None,
                    "duration_sec": None,
                    "distance_m": None,
                    "intensity_type": None,
                    "intensity_min": None,
                    "intensity_max": None,
                    "repeat_count": repeat_count or 1,
                }
            )

            result.extend(
                normalize_phase_tree(
                    children,
                    parent_key=key,
                )
            )

            continue

        goal = phase.get("goal") or {}
        intensity = phase.get("intensity") or {}

        goal_type = goal.get("type")

        duration_sec = None
        distance_m = None

        if goal_type == "DURATION":
            duration_ms = goal.get("duration")

            if duration_ms is not None:
                duration_sec = int(
                    duration_ms / 1000
                )

        elif goal_type == "DISTANCE":
            distance_m = goal.get("distance")

        name = phase.get("name") or ""

        result.append(
            {
                "key": key,
                "parent_key": parent_key,
                "position": index,
                "block_type": (
                    _block_type_from_name(name).value
                ),
                "name": name or None,
                "duration_sec": duration_sec,
                "distance_m": distance_m,
                "intensity_type": intensity.get("type"),
                "intensity_min": intensity.get(
                    "lowerZone"
                ),
                "intensity_max": intensity.get(
                    "upperZone"
                ),
                "repeat_count": 1,
            }
        )

    return result


def normalize_training_target(
    item: dict[str, Any],
) -> dict[str, Any]:
    session = item.get("session") or {}
    exercises = item.get("exercise") or []

    planned_start = _polar_datetime(
        session.get("startTime")
    )

    blocks = []

    for exercise in exercises:
        sport_id = str(exercise.get("sportId"))
        phases = exercise.get("phaseOrRepeat") or []

        for position, phase in enumerate(phases):
            goal = phase.get("goal") or {}
            intensity = phase.get("intensity") or {}

            block = {
                "position": position,
                "name": phase.get("name"),
                "block_type": "WORK",

                "duration_sec": (
                    _duration_ms_to_sec(
                        goal.get("duration")
                    )
                    if goal.get("type") == "DURATION"
                    else None
                ),

                "distance_m": (
                    goal.get("distance")
                    if goal.get("type") == "DISTANCE"
                    else None
                ),

                "intensity_type": intensity.get("type"),
                "intensity_min": intensity.get("lowerZone"),
                "intensity_max": intensity.get("upperZone"),

                "repeat_count": 1,
            }

            blocks.append(block)

    first_exercise = exercises[0] if exercises else {}

    sport_id = str(first_exercise.get("sportId"))

    return {
        "polar_target_id": str(session.get("id")),
        "date": (
            planned_start.date().isoformat()
            if planned_start
            else None
        ),
        "planned_start_time": (
            planned_start.isoformat()
            if planned_start
            else None
        ),
        "sport": POLAR_TARGET_SPORT_MAP.get(
            sport_id,
            Sport.OTHER,
        ).value,
        "title": session.get("name"),
        "description": session.get("description"),

        "duration_sec": _duration_ms_to_sec(
            first_exercise.get("duration")
        ),

        "distance_m": first_exercise.get("distance"),

        "status": (
            "COMPLETED"
            if session.get("done")
            else "PLANNED"
        ),

        "source": "POLAR",

        "blocks": blocks,
    }

async def sync_training_targets(
    db: AsyncSession,
    user: User,
    past_days: int = 35,
    future_days: int = 30,
) -> tuple[int, int]:
    connection = await db.scalar(
        select(ExternalConnection).where(
            ExternalConnection.user_id == user.id,
            ExternalConnection.provider == "POLAR",
        )
    )

    if not connection:
        raise RuntimeError("Polar connection not found")

    access_token = await get_valid_access_token(
        db,
        connection,
    )

    today = datetime.now(timezone.utc).date()

    from_date = today - timedelta(days=past_days)
    to_date = today + timedelta(days=future_days)

    payload = await PolarClient().list_training_targets(
        access_token,
        from_date,
        to_date,
    )

    imported = 0
    updated = 0

    for raw_item in payload:
        normalized = normalize_training_target(
            raw_item
        )

        polar_target_id = normalized.get(
            "polar_target_id"
        )

        if not polar_target_id:
            continue

        existing = await db.scalar(
            select(PlannedWorkout)
            .options(
                selectinload(
                    PlannedWorkout.blocks
                )
            )
            .where(
                PlannedWorkout.user_id
                == user.id,
                PlannedWorkout.polar_target_id
                == polar_target_id,
            )
        )

        session = raw_item.get("session") or {}
        exercises = raw_item.get("exercise") or []

        planned_start = _aware_planned_start(
            session.get("startTime"),
            user.timezone,
        )

        if planned_start is None:
            continue

        first_exercise = (
            exercises[0]
            if exercises
            else {}
        )

        sport_id = str(
            first_exercise.get("sportId")
        )

        sport = POLAR_TARGET_SPORT_MAP.get(
            sport_id,
            Sport.OTHER,
        )

        polar_status = (
            WorkoutStatus.COMPLETED
            if session.get("done")
            else WorkoutStatus.PLANNED
        )

        # ---------------------------------
        # Rekurzív block-fa feldolgozása
        # ---------------------------------

        all_blocks = []

        for exercise in exercises:
            all_blocks.extend(
                normalize_phase_tree(
                    exercise.get(
                        "phaseOrRepeat"
                    )
                    or []
                )
            )

        intensity_types = {
            block.get("intensity_type")
            for block in all_blocks
            if block.get("intensity_type")
            is not None
        }

        if len(intensity_types) == 1:
            intensity_type = next(
                iter(intensity_types)
            )
        elif len(intensity_types) > 1:
            intensity_type = "MIXED"
        else:
            intensity_type = None

        # ---------------------------------
        # Meglévő workout frissítése
        # ---------------------------------

        if existing:
            workout = existing

            workout.date = planned_start.date()
            workout.planned_start_time = (
                planned_start
            )
            workout.sport = sport

            workout.title = (
                normalized.get("title")
                or "Polar workout"
            )

            workout.description = (
                normalized.get(
                    "description"
                )
            )

            workout.duration_sec = (
                normalized.get(
                    "duration_sec"
                )
            )

            workout.distance_m = (
                normalized.get(
                    "distance_m"
                )
            )

            workout.intensity_type = (
                intensity_type
            )

            if (
                workout.status
                != WorkoutStatus.COMPLETED
            ):
                workout.status = (
                    polar_status
                )

            workout.source = "POLAR"
            workout.raw_data = raw_item

            workout.updated_at = (
                datetime.now(timezone.utc)
            )

            updated += 1

        # ---------------------------------
        # Új workout létrehozása
        # ---------------------------------

        else:
            workout = PlannedWorkout(
                user_id=user.id,
                date=planned_start.date(),
                planned_start_time=(
                    planned_start
                ),
                sport=sport,
                title=(
                    normalized.get("title")
                    or "Polar workout"
                ),
                description=(
                    normalized.get(
                        "description"
                    )
                ),
                duration_sec=(
                    normalized.get(
                        "duration_sec"
                    )
                ),
                distance_m=(
                    normalized.get(
                        "distance_m"
                    )
                ),
                intensity_type=(
                    intensity_type
                ),
                status=polar_status,
                source="POLAR",
                polar_target_id=(
                    polar_target_id
                ),
                raw_data=raw_item,
            )

            db.add(workout)

            # Kell az ID a WorkoutBlock-okhoz
            await db.flush()

            imported += 1

        # ---------------------------------
        # Block-fa teljes újraépítése
        # ---------------------------------

        await _replace_workout_blocks(
            db,
            workout,
            raw_item,
        )

    await db.commit()

    print(
        "TARGETS IMPORTED:",
        imported,
    )

    print(
        "TARGETS UPDATED:",
        updated,
    )

    return imported, updated