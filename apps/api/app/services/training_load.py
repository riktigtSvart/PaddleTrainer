from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import User, WorkoutSession
from math import exp


def _week_start(value: date) -> date:
    return value - timedelta(
        days=value.weekday()
    )


def _percent_change(
    current: float,
    previous: float,
) -> float | None:
    if previous <= 0:
        return None

    return round(
        (
            (current - previous)
            / previous
        )
        * 100,
        1,
    )

def _normalized_ewma(
    daily_load_by_date: dict[date, float],
    start_date: date,
    end_date: date,
    time_constant_days: int,
) -> float:
    weighted_sum = 0.0
    weight_sum = 0.0

    cursor = start_date

    while cursor <= end_date:
        age_days = (
            end_date - cursor
        ).days

        weight = exp(
            -age_days
            / time_constant_days
        )

        daily_load = (
            daily_load_by_date.get(
                cursor,
                0.0,
            )
        )

        weighted_sum += (
            daily_load * weight
        )

        weight_sum += weight

        cursor += timedelta(days=1)

    if weight_sum <= 0:
        return 0.0

    return (
        weighted_sum
        / weight_sum
    )

def _normalized_ewma_series(
    daily_load_by_date: dict[date, float],
    start_date: date,
    end_date: date,
    time_constant_days: int,
) -> dict[date, float]:
    decay = exp(
        -1.0 / time_constant_days
    )

    weighted_sum = 0.0
    weight_sum = 0.0

    result: dict[date, float] = {}

    cursor = start_date

    while cursor <= end_date:
        daily_load = (
            daily_load_by_date.get(
                cursor,
                0.0,
            )
        )

        weighted_sum = (
            daily_load
            + decay * weighted_sum
        )

        weight_sum = (
            1.0
            + decay * weight_sum
        )

        result[cursor] = (
            weighted_sum / weight_sum
            if weight_sum > 0
            else 0.0
        )

        cursor += timedelta(days=1)

    return result

def _load_balance(
    acute_weekly: float,
    chronic_weekly: float,
) -> dict:
    absolute_difference = round(
        acute_weekly - chronic_weekly,
        2,
    )

    if chronic_weekly <= 0:
        return {
            "absolute_difference": (
                absolute_difference
            ),
            "ratio": None,
            "difference_percent": None,
        }

    ratio = round(
        acute_weekly / chronic_weekly,
        2,
    )

    difference_percent = round(
        (
            acute_weekly
            / chronic_weekly
            - 1
        )
        * 100,
        1,
    )

    return {
        "absolute_difference": (
            absolute_difference
        ),
        "ratio": ratio,
        "difference_percent": (
            difference_percent
        ),
    }

async def get_training_load_proxies(
    db: AsyncSession,
    user: User,
    as_of_date: date,
    timezone_name: str,
) -> dict:
    local_timezone = ZoneInfo(
        timezone_name
    )

    acute_start = (
        as_of_date
        - timedelta(days=6)
    )

    chronic_start = (
        as_of_date
        - timedelta(days=41)
    )

    # Hosszabb előtörténetet kérünk az EWMA
    # stabilizálásához. A jelenlegi Polar-history
    # kb. 90 nap, később ez tovább nőhet.
    history_start = (
        as_of_date
        - timedelta(days=125)
    )

    query_start = datetime.combine(
        history_start,
        time.min,
        tzinfo=local_timezone,
    )

    query_end = datetime.combine(
        as_of_date + timedelta(days=1),
        time.min,
        tzinfo=local_timezone,
    )

    session_result = await db.scalars(
        select(WorkoutSession)
        .where(
            WorkoutSession.user_id == user.id,
            WorkoutSession.started_at >= query_start,
            WorkoutSession.started_at < query_end,
        )
        .order_by(
            WorkoutSession.started_at.asc()
        )
    )

    sessions = list(session_result)

    acute_load = 0.0
    chronic_load_total = 0.0

    acute_session_count = 0
    chronic_session_count = 0

    daily_load_by_date: dict[date, float] = {}
    history_dates: list[date] = []

    history_cardio_load_session_count = 0

    for session in sessions:
        local_date = (
            session.started_at
            .astimezone(local_timezone)
            .date()
        )

        history_dates.append(local_date)

        if session.cardio_load is not None:
            daily_load_by_date[local_date] = (
                daily_load_by_date.get(
                    local_date,
                    0.0,
                )
                + session.cardio_load
            )

            history_cardio_load_session_count += 1

        if local_date >= chronic_start:
            chronic_session_count += 1

            if session.cardio_load is not None:
                chronic_load_total += (
                    session.cardio_load
                )

        if local_date >= acute_start:
            acute_session_count += 1

            if session.cardio_load is not None:
                acute_load += (
                    session.cardio_load
                )

    acute_load = round(
        acute_load,
        2,
    )

    chronic_load_total = round(
        chronic_load_total,
        2,
    )

    chronic_weekly_load = round(
        chronic_load_total / 6,
        2,
    )

    difference = round(
        acute_load - chronic_weekly_load,
        2,
    )

    difference_percent = (
        round(
            (
                acute_load
                / chronic_weekly_load
                - 1
            )
            * 100,
            1,
        )
        if chronic_weekly_load > 0
        else None
    )

    smoothed = None

    if history_dates:
        first_history_date = min(
            history_dates
        )

        history_days = (
            as_of_date
            - first_history_date
        ).days + 1

        acute_ewma = _normalized_ewma(
            daily_load_by_date=daily_load_by_date,
            start_date=first_history_date,
            end_date=as_of_date,
            time_constant_days=7,
        )

        chronic_ewma = _normalized_ewma(
            daily_load_by_date=daily_load_by_date,
            start_date=first_history_date,
            end_date=as_of_date,
            time_constant_days=42,
        )

        acute_weekly_equivalent = round(
            acute_ewma * 7,
            2,
        )

        chronic_weekly_equivalent = round(
            chronic_ewma * 7,
            2,
        )

        balance = _load_balance(
            acute_weekly=(
                acute_weekly_equivalent
            ),
            chronic_weekly=(
                chronic_weekly_equivalent
            ),
        )

        smoothed = {
            "method": "NORMALIZED_EWMA",
            "history_start_date": (
                first_history_date
            ),
            "history_days": history_days,
            "session_count": len(sessions),
            "cardio_load_session_count": (
                history_cardio_load_session_count
            ),
            "acute": {
                "time_constant_days": 7,
                "daily_load": round(
                    acute_ewma,
                    2,
                ),
                "weekly_equivalent": (
                    acute_weekly_equivalent
                ),
            },
            "chronic": {
                "time_constant_days": 42,
                "daily_load": round(
                    chronic_ewma,
                    2,
                ),
                "weekly_equivalent": (
                    chronic_weekly_equivalent
                ),
            },
            "balance": balance,
        }

    return {
        "as_of_date": as_of_date,
        "acute": {
            "days": 7,
            "start_date": acute_start,
            "end_date": as_of_date,
            "weekly_load": acute_load,
            "session_count": acute_session_count,
        },
        "chronic": {
            "days": 42,
            "start_date": chronic_start,
            "end_date": as_of_date,
            "total_load": chronic_load_total,
            "weekly_load": chronic_weekly_load,
            "session_count": chronic_session_count,
        },
        "comparison": {
            "absolute_difference": difference,
            "difference_percent": difference_percent,
        },
        "smoothed": smoothed,
    }


async def get_weekly_cardio_load_series(
    db: AsyncSession,
    user: User,
    start_date: date,
    end_date: date,
    timezone_name: str,
) -> list[dict]:
    local_timezone = ZoneInfo(
        timezone_name
    )

    first_week_start = _week_start(
        start_date
    )

    last_week_start = _week_start(
        end_date
    )

    # Kell az első megjelenített hetet
    # megelőző hét is a trendhez.
    query_start_week = (
        first_week_start
        - timedelta(days=7)
    )

    # Exclusive felső határ:
    # a legutolsó hét utáni hétfő.
    query_end = (
        last_week_start
        + timedelta(days=7)
    )

    query_start_datetime = datetime.combine(
        query_start_week,
        time.min,
        tzinfo=local_timezone,
    )

    query_end_datetime = datetime.combine(
        query_end,
        time.min,
        tzinfo=local_timezone,
    )

    session_result = await db.scalars(
        select(WorkoutSession)
        .where(
            WorkoutSession.user_id
            == user.id,
            WorkoutSession.started_at
            >= query_start_datetime,
            WorkoutSession.started_at
            < query_end_datetime,
        )
        .order_by(
            WorkoutSession.started_at.asc()
        )
    )

    sessions = list(session_result)

    buckets: dict[date, dict] = {}

    cursor = query_start_week

    while cursor <= last_week_start:
        buckets[cursor] = {
            "cardio_load": 0.0,
            "session_count": 0,
            "cardio_load_session_count": 0,
        }

        cursor += timedelta(days=7)

    for session in sessions:
        local_date = (
            session.started_at
            .astimezone(local_timezone)
            .date()
        )

        session_week_start = _week_start(
            local_date
        )

        if session_week_start not in buckets:
            continue

        bucket = buckets[
            session_week_start
        ]

        bucket["session_count"] += 1

        if session.cardio_load is not None:
            bucket["cardio_load"] += (
                session.cardio_load
            )

            bucket[
                "cardio_load_session_count"
            ] += 1

    today = datetime.now(
        local_timezone
    ).date()

    series: list[dict] = []

    cursor = first_week_start

    while cursor <= last_week_start:
        week_end = (
            cursor
            + timedelta(days=6)
        )

        current = buckets[cursor]

        previous_week_start = (
            cursor
            - timedelta(days=7)
        )

        previous = buckets.get(
            previous_week_start,
            {
                "cardio_load": 0.0,
                "session_count": 0,
                "cardio_load_session_count": 0,
            },
        )

        current_load = round(
            current["cardio_load"],
            2,
        )

        previous_load = round(
            previous["cardio_load"],
            2,
        )

        if week_end < today:
            phase = "PAST"
        elif cursor <= today <= week_end:
            phase = "CURRENT"
        else:
            phase = "FUTURE"

        # Csak lezárt hetet hasonlítunk
        # százalékosan teljes előző héthez.
        change_percent = (
            _percent_change(
                current_load,
                previous_load,
            )
            if phase == "PAST"
            else None
        )

        series.append(
            {
                "week_start": cursor,
                "week_end": week_end,
                "phase": phase,
                "cardio_load": current_load,
                "session_count": current[
                    "session_count"
                ],
                "cardio_load_session_count": (
                    current[
                        "cardio_load_session_count"
                    ]
                ),
                "previous_week_cardio_load": (
                    previous_load
                ),
                "change_percent": (
                    change_percent
                ),
            }
        )

        cursor += timedelta(days=7)

    return series

async def get_current_load_state(
    db: AsyncSession,
    user: User,
    as_of_date: date,
    timezone_name: str,
) -> dict:
    local_timezone = ZoneInfo(
        timezone_name
    )

    short_start = (
        as_of_date
        - timedelta(days=6)
    )

    baseline_end = (
        short_start
        - timedelta(days=1)
    )

    baseline_start = (
        baseline_end
        - timedelta(days=27)
    )

    query_start = datetime.combine(
        baseline_start,
        time.min,
        tzinfo=local_timezone,
    )

    query_end = datetime.combine(
        as_of_date + timedelta(days=1),
        time.min,
        tzinfo=local_timezone,
    )

    session_result = await db.scalars(
        select(WorkoutSession)
        .where(
            WorkoutSession.user_id
            == user.id,
            WorkoutSession.started_at
            >= query_start,
            WorkoutSession.started_at
            < query_end,
        )
        .order_by(
            WorkoutSession.started_at.asc()
        )
    )

    sessions = list(session_result)

    short_load = 0.0
    baseline_load = 0.0

    short_session_count = 0
    baseline_session_count = 0

    short_load_session_count = 0
    baseline_load_session_count = 0

    for session in sessions:
        local_date = (
            session.started_at
            .astimezone(
                local_timezone
            )
            .date()
        )

        if local_date >= short_start:
            short_session_count += 1

            if session.cardio_load is not None:
                short_load += (
                    session.cardio_load
                )

                short_load_session_count += 1

        else:
            baseline_session_count += 1

            if session.cardio_load is not None:
                baseline_load += (
                    session.cardio_load
                )

                baseline_load_session_count += 1

    short_load = round(
        short_load,
        2,
    )

    baseline_load = round(
        baseline_load,
        2,
    )

    baseline_weekly_average = round(
        baseline_load / 4,
        2,
    )

    short_vs_baseline_percent = (
        round(
            (
                short_load
                / baseline_weekly_average
                - 1
            )
            * 100,
            1,
        )
        if baseline_weekly_average > 0
        else None
    )

    return {
        "as_of_date": as_of_date,
        "short_term": {
            "start_date": short_start,
            "end_date": as_of_date,
            "days": 7,
            "cardio_load": short_load,
            "session_count": (
                short_session_count
            ),
            "cardio_load_session_count": (
                short_load_session_count
            ),
        },
        "baseline": {
            "start_date": baseline_start,
            "end_date": baseline_end,
            "days": 28,
            "cardio_load": baseline_load,
            "weekly_average_cardio_load": (
                baseline_weekly_average
            ),
            "session_count": (
                baseline_session_count
            ),
            "cardio_load_session_count": (
                baseline_load_session_count
            ),
            "weeks": 4,
            "average_sessions_per_week": round(
                baseline_session_count / 4,
                2,
            ),
        },
        "comparison": {
            "short_vs_baseline_percent": (
                short_vs_baseline_percent
            ),
            "absolute_difference": round(
                short_load
                - baseline_weekly_average,
                2,
            ),
        },
    }

async def get_training_load_series(
    db: AsyncSession,
    user: User,
    as_of_date: date,
    timezone_name: str,
    max_history_days: int = 126,
) -> dict:
    local_timezone = ZoneInfo(
        timezone_name
    )

    query_start_date = (
        as_of_date
        - timedelta(
            days=max_history_days - 1
        )
    )

    query_start = datetime.combine(
        query_start_date,
        time.min,
        tzinfo=local_timezone,
    )

    query_end = datetime.combine(
        as_of_date + timedelta(days=1),
        time.min,
        tzinfo=local_timezone,
    )

    session_result = await db.scalars(
        select(WorkoutSession)
        .where(
            WorkoutSession.user_id == user.id,
            WorkoutSession.started_at >= query_start,
            WorkoutSession.started_at < query_end,
        )
        .order_by(
            WorkoutSession.started_at.asc()
        )
    )

    sessions = list(session_result)

    if not sessions:
        return {
            "as_of_date": as_of_date,
            "history_start_date": None,
            "history_days": 0,
            "points": [],
        }

    daily_load_by_date: dict[
        date,
        float,
    ] = {}

    session_dates: list[date] = []

    cardio_load_session_count = 0

    for session in sessions:
        local_date = (
            session.started_at
            .astimezone(local_timezone)
            .date()
        )

        session_dates.append(
            local_date
        )

        if session.cardio_load is None:
            continue

        daily_load_by_date[
            local_date
        ] = (
            daily_load_by_date.get(
                local_date,
                0.0,
            )
            + session.cardio_load
        )

        cardio_load_session_count += 1

    first_history_date = min(
        session_dates
    )

    history_days = (
        as_of_date
        - first_history_date
    ).days + 1

    acute_series = (
        _normalized_ewma_series(
            daily_load_by_date=(
                daily_load_by_date
            ),
            start_date=(
                first_history_date
            ),
            end_date=as_of_date,
            time_constant_days=7,
        )
    )

    chronic_series = (
        _normalized_ewma_series(
            daily_load_by_date=(
                daily_load_by_date
            ),
            start_date=(
                first_history_date
            ),
            end_date=as_of_date,
            time_constant_days=42,
        )
    )

    points: list[dict] = []

    cursor = first_history_date

    while cursor <= as_of_date:
        available_history_days = (
            cursor
            - first_history_date
        ).days + 1

        acute_weekly = round(
            acute_series[cursor] * 7,
            2,
        )

        chronic_weekly = round(
            chronic_series[cursor] * 7,
            2,
        )

        balance = _load_balance(
            acute_weekly=acute_weekly,
            chronic_weekly=chronic_weekly,
        )

        points.append(
            {
                "date": cursor,
                "daily_cardio_load": round(
                    daily_load_by_date.get(
                        cursor,
                        0.0,
                    ),
                    2,
                ),
                "acute_weekly_equivalent": (
                    acute_weekly
                ),
                "chronic_weekly_equivalent": (
                    chronic_weekly
                ),
                "available_history_days": (
                    available_history_days
                ),
                "acute_mature": (
                    available_history_days
                    >= 7
                ),
                "chronic_mature": (
                    available_history_days
                    >= 42
                ),
                "balance": balance,
            }
        )

        cursor += timedelta(days=1)

    return {
        "as_of_date": as_of_date,
        "history_start_date": (
            first_history_date
        ),
        "history_days": history_days,
        "session_count": len(sessions),
        "cardio_load_session_count": (
            cardio_load_session_count
        ),
        "acute_time_constant_days": 7,
        "chronic_time_constant_days": 42,
        "points": points,
    }