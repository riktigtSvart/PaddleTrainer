from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import User
from app.services.athlete_state import get_athlete_state
from app.services.athlete_state_scientific_view import (
    build_athlete_state_scientific_view,
)
from app.services.capacity_state import get_current_capacity_state
from app.services.coach_context import (
    build_coach_assessment,
    build_coach_context,
    build_coach_inputs,
    build_coach_state,
    build_descriptive_flags,
    build_interpretation_facts,
    build_interpretation_signals,
    build_readiness_coach_view,
)
from app.services.personal_readiness_reference import (
    compare_hrv_to_reference,
    compare_resting_hr_to_reference,
    compare_sleep_duration_to_reference,
    get_hrv_reference,
    get_hrv_trend_evidence,
    get_resting_hr_reference,
    get_sleep_duration_reference,
)
from app.services.scientific_assessment import build_scientific_assessment


SCHEMA_VERSION = "0.1"
SOURCE_POLICY = "PRIOR_LOCAL_DAY_CLOSED_WINDOW"


async def build_athlete_state_scientific_view_for_date(
    *,
    db: AsyncSession,
    user: User,
    as_of_date: date,
) -> dict[str, Any]:
    """Build the same scientific AthleteState view used by the coach API.

    This service-level orchestration mirrors the existing coach scientific-view
    route without calling one API route from another.  It preserves the current
    project semantics and does not synthesize any extra readiness/state fields.
    """
    athlete_state = await get_athlete_state(
        db=db,
        user=user,
        as_of_date=as_of_date,
        timezone_name=user.timezone,
    )

    coach_context = build_coach_context(
        athlete_state=athlete_state,
        as_of_date=as_of_date,
    )
    coach_inputs = build_coach_inputs(coach_context)
    interpretation_facts = build_interpretation_facts(coach_inputs)
    descriptive_flags = build_descriptive_flags(interpretation_facts)
    readiness_coach_view = build_readiness_coach_view(interpretation_facts)
    interpretation_signals = build_interpretation_signals(
        interpretation_facts=interpretation_facts,
        descriptive_flags=descriptive_flags,
        readiness_coach_view=readiness_coach_view,
    )
    coach_assessment = build_coach_assessment(interpretation_signals)
    coach_state = build_coach_state(
        coach_assessment=coach_assessment,
        readiness_coach_view=readiness_coach_view,
        interpretation_facts=interpretation_facts,
    )

    hrv_reference = await get_hrv_reference(
        db=db,
        user=user,
        as_of_date=as_of_date,
    )
    sleep_duration_reference = await get_sleep_duration_reference(
        db=db,
        user=user,
        as_of_date=as_of_date,
    )
    hrv_trend_evidence = await get_hrv_trend_evidence(
        db=db,
        user=user,
        as_of_date=as_of_date,
    )

    readiness_view = (
        (coach_state.get("readiness") or {}).get("view") or {}
    )
    readiness_values = readiness_view.get("values") or {}
    objective_values = readiness_values.get("objective") or {}

    hrv_reference_comparison = compare_hrv_to_reference(
        current_value=objective_values.get("hrv_rmssd_ms"),
        reference=hrv_reference,
    )
    sleep_duration_reference_comparison = compare_sleep_duration_to_reference(
        current_value=objective_values.get("sleep_duration_sec"),
        reference=sleep_duration_reference,
    )

    resting_hr_reference = await get_resting_hr_reference(
        db=db,
        user=user,
        as_of_date=as_of_date,
    )
    resting_hr_reference_comparison = compare_resting_hr_to_reference(
        current_value=objective_values.get("resting_hr_bpm"),
        reference=resting_hr_reference,
    )

    scientific_assessment = build_scientific_assessment(
        coach_state=coach_state,
        hrv_reference_comparison=hrv_reference_comparison,
        sleep_duration_reference_comparison=(
            sleep_duration_reference_comparison
        ),
        hrv_trend_evidence=hrv_trend_evidence,
        resting_hr_reference_comparison=(
            resting_hr_reference_comparison
        ),
    )

    capacity_state = await get_current_capacity_state(
        db=db,
        user=user,
        as_of_date=as_of_date,
    )

    return build_athlete_state_scientific_view(
        scientific_assessment,
        capacity_state=capacity_state,
    )


async def load_prior_local_day_closed_scientific_view(
    *,
    db: AsyncSession,
    user: User,
    target_timestamp: Any,
) -> dict[str, Any] | None:
    """Load one leakage-safe daily state wrapper for V22 temporal binding.

    The current scientific-state source is date-based, not timestamp-based.
    Some component queries (notably capacity) accept records throughout the
    requested local date.  Therefore a same-day view cannot prove that every
    component existed before an arbitrary exercise start time.

    V22.2 uses the *previous local calendar day* as a closed source window and
    gives that completed daily view an explicit effective timestamp at local
    midnight starting the target day.  V22 then applies its normal carry-forward
    policy from that instant to the exercise target timestamp.
    """
    target = _parse_aware_datetime(target_timestamp)
    if target is None:
        return None

    timezone_name = getattr(user, "timezone", None)
    if not isinstance(timezone_name, str) or not timezone_name.strip():
        raise ValueError("user.timezone must be a non-empty IANA timezone name")

    user_timezone = ZoneInfo(timezone_name)
    target_local = target.astimezone(user_timezone)
    target_local_date = target_local.date()
    source_as_of_date = target_local_date - timedelta(days=1)

    effective_local = datetime.combine(
        target_local_date,
        time.min,
        tzinfo=user_timezone,
    )
    effective_utc = effective_local.astimezone(timezone.utc)

    scientific_view = await build_athlete_state_scientific_view_for_date(
        db=db,
        user=user,
        as_of_date=source_as_of_date,
    )

    return {
        "scientific_view": scientific_view,
        "state_timestamp": effective_utc.isoformat(),
        "snapshot_id": (
            f"daily-scientific-view:{source_as_of_date.isoformat()}"
        ),
        "source_reference": {
            "schema_version": SCHEMA_VERSION,
            "source_policy": SOURCE_POLICY,
            "source_as_of_date": source_as_of_date.isoformat(),
            "target_local_date": target_local_date.isoformat(),
            "user_timezone": timezone_name,
            "effective_timestamp_local": effective_local.isoformat(),
            "effective_timestamp_utc": effective_utc.isoformat(),
            "same_day_state_used": False,
            "future_component_leakage_allowed": False,
            "component_specific_recency_established": False,
        },
    }


def extract_route_athlete_state_target_timestamp(
    route_environment_context_input: Mapping[str, Any] | None,
) -> str | None:
    """Return the earliest trustworthy route segment timestamp available.

    Environment-context segments already require positioned/timestamp-complete
    trusted route segments.  Prefer segment start time when present and fall back
    to midpoint time, which is already used elsewhere in the route pipeline.
    """
    if not isinstance(route_environment_context_input, Mapping):
        return None

    candidates: list[datetime] = []
    for route in route_environment_context_input.get("routes") or []:
        if not isinstance(route, Mapping):
            continue
        for segment in route.get("segments") or []:
            if not isinstance(segment, Mapping):
                continue
            value = (
                segment.get("start_timestamp")
                or segment.get("midpoint_timestamp")
            )
            parsed = _parse_aware_datetime(value)
            if parsed is not None:
                candidates.append(parsed)

    if not candidates:
        return None
    return min(candidates).astimezone(timezone.utc).isoformat()


def _parse_aware_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
    else:
        return None

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)
