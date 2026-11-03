"""Bounded, owner-scoped history shared by calendar rendering and conflict review."""

from datetime import UTC, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.models.entities import WorkoutSession, WorkoutStatus
from app.planning.domain import calendar_duration as domain
from app.planning.application import register_athlete_setup as setup
from app.planning.infrastructure.repositories.postgres_planning_audit import SqlAlchemyPlanningAuditRepository
from app.planning.infrastructure.adapters.athlete_history import aware

HISTORY_LIMIT = 4000


def reaches_view(plan, first, last, low, high, estimate):
    if first <= plan.date <= last:
        return True
    if plan.planned_start_time is None:
        return False
    start = aware(plan.planned_start_time)
    seconds = plan.duration_sec if plan.duration_sec is not None else estimate["upper_sec"] if estimate else None
    return start < high and (start >= low or domain.positive(seconds) and start + timedelta(seconds=seconds) > low)


def simple_distance_plan(plan):
    """Accept a continuous distance plan, including flat warmup/work/cooldown legs."""
    if plan.duration_sec is not None or not domain.positive(plan.distance_m) or plan.sport.value in ("OTHER", "STRENGTH"):
        return False
    if plan.status not in (WorkoutStatus.DRAFT, WorkoutStatus.PLANNED, WorkoutStatus.SCHEDULED):
        return False
    blocks = list(plan.blocks)
    if not blocks:
        return True
    if not all(block.parent_block_id is None and block.block_type.value in ("WARMUP", "WORK", "COOLDOWN")
        and block.duration_sec is None and block.repeat_count in (None, 1)
        and domain.positive(block.distance_m) for block in blocks):
        return False
    distance = sum(block.distance_m for block in blocks)
    return domain.positive(distance) and abs(distance - plan.distance_m) <= max(1, plan.distance_m * 0.01)


async def project(*, owner, plans, session, now, zone):
    eligible = [p for p in plans if simple_distance_plan(p)]
    if not eligible:
        return {}
    cutoffs = {str(p.id): min(now, aware(p.planned_start_time) if p.planned_start_time else
        datetime.combine(p.date, time.min, ZoneInfo(zone)).astimezone(UTC)) for p in eligible}
    low = min(cutoffs.values()) - timedelta(days=domain.LOOKBACK_DAYS)
    high = max(cutoffs.values())
    rows = list((await session.execute(select(WorkoutSession).where(
        WorkoutSession.user_id == UUID(owner), WorkoutSession.started_at >= low, WorkoutSession.started_at < high,
        WorkoutSession.sport.in_({p.sport for p in eligible}), WorkoutSession.distance_m > 0,
    ).order_by(WorkoutSession.started_at.desc(), WorkoutSession.id).limit(HISTORY_LIMIT + 1))).scalars())
    if len(rows) > HISTORY_LIMIT:
        return {}  # No inference from silently truncated history.
    observations = [{"id": str(s.id), "sport": s.sport.value, "started_at": aware(s.started_at).isoformat(),
        "ended_at": aware(s.ended_at).isoformat() if s.ended_at else None,
        "duration_sec": s.duration_sec, "distance_m": s.distance_m,
        "available_at": aware(s.created_at).isoformat()} for s in rows]
    profile = await setup.latest(SqlAlchemyPlanningAuditRepository(session), session, owner, "profile")
    result = {}
    for p in eligible:
        setting, coefficient_ref = domain.DEFAULT_SLOWDOWN_PCT, None
        if profile and aware(profile[1].persisted_at) <= cutoffs[str(p.id)]:
            value = profile[0]["proposal"]["data"].get("duration_doubling_slowdown_pct")
            if value is not None and domain.profile_matches_sport(profile[0]["proposal"]["data"]["target_sport"], p.sport.value):
                setting, coefficient_ref = value, setup.domain.reference(profile[0])
        item = domain.estimate(owner=owner, plan_id=str(p.id), sport=p.sport.value, distance_m=p.distance_m,
            cutoff=cutoffs[str(p.id)], observations=observations,
            doubling_slowdown_pct=setting, coefficient_profile_reference=coefficient_ref)
        if item:
            result[str(p.id)] = item
    return result
