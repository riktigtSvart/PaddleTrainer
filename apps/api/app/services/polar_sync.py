from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.polar.client import PolarClient
from app.models.entities import ExternalConnection, Sport, User, WorkoutSession
from app.services.polar_tokens import get_valid_access_token


POLAR_NAME_TO_SPORT = {
    "WATERSPORTS_KAYAKING": Sport.KAYAK,
    "RUNNING": Sport.RUNNING,
    "SWIMMING": Sport.SWIMMING,
    "STRENGTH_TRAINING": Sport.STRENGTH,
    "CYCLING": Sport.CYCLING,
}


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _extract_sports(sports_payload: Any) -> list[dict[str, Any]]:
    """Normalize Polar /sports/list response to a list of sport objects."""
    if isinstance(sports_payload, list):
        return sports_payload

    if isinstance(sports_payload, dict):
        sports = sports_payload.get("sports", [])
        if isinstance(sports, list):
            return sports

    return []


def _build_polar_sport_map(sports: list[dict[str, Any]]) -> dict[str, str]:
    """Build a lookup like: '95' -> 'WATERSPORTS_KAYAKING'."""
    result: dict[str, str] = {}

    for sport in sports:
        raw_id = sport.get("id")

        if isinstance(raw_id, dict):
            raw_id = raw_id.get("id")

        if raw_id is None:
            continue

        name = sport.get("name")
        if not name:
            continue

        result[str(raw_id)] = str(name)

    return result


def _sport_from_session(
    item: dict[str, Any],
    polar_sport_map: dict[str, str],
) -> Sport:
    """Resolve Polar sport id to our internal Sport enum."""
    sport_obj = item.get("sport") or {}

    if not isinstance(sport_obj, dict):
        return Sport.OTHER

    raw_id = sport_obj.get("id")
    if raw_id is None:
        return Sport.OTHER

    polar_name = polar_sport_map.get(str(raw_id))
    if not polar_name:
        return Sport.OTHER

    mapped = POLAR_NAME_TO_SPORT.get(polar_name)
    if mapped:
        return mapped

    upper_name = polar_name.upper()

    if "KAYAK" in upper_name or "CANOE" in upper_name:
        return Sport.KAYAK
    if "RUNNING" in upper_name or upper_name.startswith("RUN_"):
        return Sport.RUNNING
    if "SWIMMING" in upper_name or "SWIM" in upper_name:
        return Sport.SWIMMING
    if "STRENGTH" in upper_name or "GYM" in upper_name:
        return Sport.STRENGTH
    if "CYCLING" in upper_name or "BIKING" in upper_name or "BIKE" in upper_name:
        return Sport.CYCLING

    return Sport.OTHER


async def _enrich_training_load(
    db: AsyncSession,
    access_token: str,
    sessions: list[dict[str, Any]],
) -> int:
    session_dates = set()

    for item in sessions:
        start_time = item.get("startTime")
        if not start_time:
            continue

        session_date = datetime.fromisoformat(
            start_time.replace("Z", "+00:00")
        ).date()

        session_dates.add(session_date)

    updated = 0
    polar = PolarClient()

    for session_date in sorted(session_dates):
        next_day = session_date + timedelta(days=1)

        print("LOAD ENRICHMENT DAY:", session_date)

        payload = await polar.list_training_sessions(
            access_token,
            session_date,
            next_day,
            features=["training-load-report"],
        )

        for item in payload.get("trainingSessions", []):
            external_id = (item.get("identifier") or {}).get("id")
            if not external_id:
                continue

            load = item.get("trainingLoadReport") or {}

            if not load:
                print("NO TRAINING LOAD:", external_id)
                continue

            existing = await db.scalar(
                select(WorkoutSession).where(
                    WorkoutSession.external_provider == "POLAR",
                    WorkoutSession.external_id == external_id,
                )
            )

            if not existing:
                continue

            existing.cardio_load = load.get("cardioLoad")
            existing.perceived_load = load.get("perceivedLoad")

            # Keep the base Polar data and add the enrichment.
            existing.raw_data = {
                **(existing.raw_data or {}),
                "trainingLoadReport": load,
            }

            print(
                "TRAINING LOAD:",
                external_id,
                "cardio=",
                load.get("cardioLoad"),
                "perceived=",
                load.get("perceivedLoad"),
            )

            updated += 1

    await db.commit()

    print("TRAINING LOAD UPDATED:", updated)

    return updated


async def _enrich_statistics(
    db: AsyncSession,
    access_token: str,
    sessions: list[dict[str, Any]],
) -> int:
    session_dates = set()

    for item in sessions:
        start_time = item.get("startTime")
        if not start_time:
            continue

        session_date = datetime.fromisoformat(
            start_time.replace("Z", "+00:00")
        ).date()

        session_dates.add(session_date)

    updated = 0
    polar = PolarClient()

    for session_date in sorted(session_dates):
        next_day = session_date + timedelta(days=1)

        print("STATISTICS ENRICHMENT DAY:", session_date)

        payload = await polar.list_training_sessions(
            access_token,
            session_date,
            next_day,
            features=["statistics"],
        )

        for item in payload.get("trainingSessions", []):
            external_id = (item.get("identifier") or {}).get("id")
            if not external_id:
                continue

            existing = await db.scalar(
                select(WorkoutSession).where(
                    WorkoutSession.external_provider == "POLAR",
                    WorkoutSession.external_id == external_id,
                )
            )

            if not existing:
                continue

            exercises = item.get("exercises") or []

            # For now we only summarize sessions with one exercise.
            # Multi-exercise sessions will be handled separately later.
            if len(exercises) != 1:
                print(
                    "STATISTICS MULTI-EXERCISE SKIPPED:",
                    external_id,
                    "exercise_count=",
                    len(exercises),
                )
                continue

            exercise = exercises[0]

            statistics_container = exercise.get("statistics") or {}
            statistics = statistics_container.get("statistics") or []

            for stat in statistics:
                stat_type = stat.get("type")

                if stat_type == "STATISTICS_TYPE_HEART_RATE":
                    if stat.get("avg") is not None:
                        existing.avg_hr = stat.get("avg")

                    if stat.get("max") is not None:
                        existing.max_hr = stat.get("max")

                elif stat_type == "STATISTICS_TYPE_SPEED":
                    existing.avg_speed = stat.get("avg")
                    existing.max_speed = stat.get("max")

            # Preserve statistics in raw_data as well.
            existing.raw_data = {
                **(existing.raw_data or {}),
                "exerciseStatistics": exercises,
            }

            print(
                "STATISTICS UPDATED:",
                external_id,
                "avg_hr=",
                existing.avg_hr,
                "max_hr=",
                existing.max_hr,
                "avg_speed=",
                existing.avg_speed,
                "max_speed=",
                existing.max_speed,
            )

            updated += 1

    await db.commit()

    print("STATISTICS UPDATED COUNT:", updated)

    return updated


async def _enrich_samples(
    db: AsyncSession,
    access_token: str,
    sessions: list[dict[str, Any]],
) -> int:
    session_dates = set()

    for item in sessions:
        start_time = item.get("startTime")

        if not start_time:
            continue

        session_date = datetime.fromisoformat(
            start_time.replace(
                "Z",
                "+00:00",
            )
        ).date()

        session_dates.add(session_date)

    updated = 0
    polar = PolarClient()

    for session_date in sorted(
        session_dates
    ):
        next_day = (
            session_date
            + timedelta(days=1)
        )

        print(
            "SAMPLES ENRICHMENT DAY:",
            session_date,
        )

        payload = (
            await polar.list_training_sessions(
                access_token,
                session_date,
                next_day,
                features=["samples"],
            )
        )

        for item in payload.get(
            "trainingSessions",
            [],
        ):
            external_id = (
                item.get("identifier")
                or {}
            ).get("id")

            if not external_id:
                continue

            existing = await db.scalar(
                select(WorkoutSession).where(
                    WorkoutSession.external_provider
                    == "POLAR",
                    WorkoutSession.external_id
                    == external_id,
                )
            )

            if not existing:
                continue

            exercises = (
                item.get("exercises")
                or []
            )

            if not exercises:
                print(
                    "NO EXERCISE SAMPLES:",
                    external_id,
                )
                continue

            # Preserve the provider payload.
            #
            # Do not collapse the time series into
            # summary values here. Scientific
            # interpretation happens downstream.
            existing.raw_data = {
                **(existing.raw_data or {}),
                "exerciseSamples": exercises,
            }

            print(
                "SAMPLES UPDATED:",
                external_id,
                "exercise_count=",
                len(exercises),
            )

            updated += 1

    await db.commit()

    print(
        "SAMPLES UPDATED COUNT:",
        updated,
    )

    return updated


async def sync_recent_sessions(
    db: AsyncSession,
    user: User,
    days: int = 30,
) -> int:
    connection = await db.scalar(
        select(ExternalConnection).where(
            ExternalConnection.user_id == user.id,
            ExternalConnection.provider == "POLAR",
        )
    )

    if not connection:
        raise RuntimeError("Polar connection not found")

    access_token = await get_valid_access_token(db, connection)

    # 1) Resolve Polar sport ids.
    sports_payload = await PolarClient().list_sports(access_token)
    sports = _extract_sports(sports_payload)
    polar_sport_map = _build_polar_sport_map(sports)

    print("SPORTS COUNT:", len(sports))
    if "95" in polar_sport_map:
        print("SPORT 95:", polar_sport_map["95"])

    # 2) Load recent base sessions without optional feature enrichment.
    today = datetime.now(timezone.utc).date()
    start_date = today - timedelta(days=min(days, 89))

    payload = await PolarClient().list_training_sessions(
        access_token,
        start_date,
        today,
        features=None,
    )

    sessions = payload.get("trainingSessions", [])
    print("TRAINING SESSION COUNT:", len(sessions))

    imported = 0
    updated = 0

    # 3) Insert new sessions and refresh base fields on existing sessions.
    for item in sessions:
        external_id = (item.get("identifier") or {}).get("id")
        if not external_id:
            continue

        start = _parse_dt(item.get("startTime"))
        if not start:
            continue

        stop = _parse_dt(item.get("stopTime"))
        duration_ms = item.get("durationMillis")
        mapped_sport = _sport_from_session(item, polar_sport_map)

        existing = await db.scalar(
            select(WorkoutSession).where(
                WorkoutSession.external_provider == "POLAR",
                WorkoutSession.external_id == external_id,
            )
        )

        if existing:
            existing.sport = mapped_sport
            existing.name = item.get("name")
            existing.started_at = start
            existing.ended_at = stop
            existing.duration_sec = int(duration_ms / 1000) if duration_ms else None
            existing.distance_m = item.get("distanceMeters")
            existing.calories = item.get("calories")
            existing.avg_hr = item.get("hrAvg")
            existing.max_hr = item.get("hrMax")
            existing.cardio_load = item.get("trainingLoad")
            existing.raw_data = item

            updated += 1
            continue

        db.add(
            WorkoutSession(
                user_id=user.id,
                external_provider="POLAR",
                external_id=external_id,
                sport=mapped_sport,
                name=item.get("name"),
                started_at=start,
                ended_at=stop,
                duration_sec=int(duration_ms / 1000) if duration_ms else None,
                distance_m=item.get("distanceMeters"),
                calories=item.get("calories"),
                avg_hr=item.get("hrAvg"),
                max_hr=item.get("hrMax"),
                avg_speed=None,
                max_speed=None,
                avg_cadence=None,
                max_cadence=None,
                avg_power=None,
                max_power=None,
                cardio_load=item.get("trainingLoad"),
                perceived_load=None,
                raw_data=item,
            )
        )

        imported += 1

    await db.commit()

    print("IMPORTED SESSIONS:", imported)
    print("UPDATED SESSIONS:", updated)

    await _enrich_training_load(
        db,
        access_token,
        sessions,
    )

    await _enrich_statistics(
        db,
        access_token,
        sessions,
    )

    await _enrich_samples(
        db,
        access_token,
        sessions,
    )

    return imported
