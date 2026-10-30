"""Read-only, owned workout details and bounded source sample projections.

Charts use each exercise's sample index multiplied by its declared interval.
Exercise clocks are never concatenated or aligned to a guessed session offset.
"""
from datetime import UTC, datetime
import hashlib
import json
import math
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.entities import PlannedWorkout, User, WorkoutSession
from app.planning.application.calendar_workspace import CalendarRuleError
from app.planning.infrastructure.adapters.athlete_history import aware
from app.services.session_chart_zones import heart_rate_zones, zone_limits
from app.services.session_sections import section_groups
from app.services.session_plan_timeline import plan_timeline
from app.services.session_sample_clock import sample_clock_issues
from app.services.session_route_projection import project_routes

SCHEMA = "session-analysis-v0.1"
MAX_EXERCISES = 64
MAX_SERIES = 128
MAX_SLOTS = 500_000
MAX_SERIES_SLOTS = 360_000
METRICS = {
    "HEART_RATE": ("heart_rate_bpm", "bpm"),
    "SPEED": ("speed_kmh", "km/h"),
    "DISTANCE": ("distance_m", "m"),
    "CADENCE": ("cadence_per_min", "1/perc"),
    "LEFT_CRANK_CURRENT_POWER": ("left_power_w", "W"),
    "RIGHT_CRANK_CURRENT_POWER": ("right_power_w", "W"),
    "ALTITUDE": ("altitude_m", "m"),
    "TEMPERATURE": ("temperature_c", "°C"),
}
SUMMARY_METRICS = (
    "duration_sec", "distance_m", "calories", "avg_hr", "max_hr", "avg_speed", "max_speed",
    "avg_cadence", "max_cadence", "avg_power", "max_power", "cardio_load", "perceived_load", "rpe",
)


def require(value, code):
    if not value:
        raise CalendarRuleError(code)


def numeric(value):
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        return None
    try:
        return value if math.isfinite(value) else None
    except (OverflowError, ValueError):
        return None


def samples(raw, provider):
    result = {"provider": provider, "time_basis": "exercise_sample_index_times_interval",
              "exercises": [], "series": [], "unsupported": [], "issues": [],
              "slot_count": 0, "valid_sample_count": 0, "routes": project_routes(raw, provider)}
    if provider != "POLAR":
        result["issues"].append("PROVIDER_SAMPLES_UNSUPPORTED")
        return result
    if not isinstance(raw, dict):
        result["issues"].append("SOURCE_OBJECT_MISSING")
        return result
    # Do not merge two native views: they may describe the same observations.
    key = "exerciseSamples" if isinstance(raw.get("exerciseSamples"), list) and raw["exerciseSamples"] else "exercises"
    exercises = raw.get(key)
    if not isinstance(exercises, list):
        result["issues"].append("SAMPLES_NOT_STORED")
        return result
    if key == "exerciseSamples" and raw.get("exercises"):
        result["issues"].append("PREFERRED_EXERCISE_SAMPLES_VIEW")
    require(len(exercises) <= MAX_EXERCISES, "CALENDAR_SESSION_SOURCE_TOO_LARGE")
    raw_slots = 0
    raw_series_count = 0
    for index, exercise in enumerate(exercises):
        if not isinstance(exercise, dict):
            result["issues"].append(f"EXERCISE_INVALID:{index}")
            continue
        start = exercise.get("startTime")
        result["exercises"].append({"index": index, "source_path": f"{key}[{index}]",
                                    "source_start": start[:100] if isinstance(start, str) else None,
                                    "clock_issues": sample_clock_issues(exercise, raw, index, key),
                                    "heart_rate_zones": heart_rate_zones(exercise, f"{key}[{index}]"),
                                    "speed_zones": zone_limits(exercise, f"{key}[{index}]", "ZONE_TYPE_SPEED", "km/h"),
                                    "power_zones": zone_limits(exercise, f"{key}[{index}]", "ZONE_TYPE_POWER", "W")})
        container = exercise.get("samples")
        if isinstance(container, dict) and any(container.get(k) for k in ("transitionSamples", "rrSamples", "transitionRrSamples", "swimmingPhases")):
            result["issues"].append(f"OTHER_SAMPLE_CONTAINERS_NOT_PLOTTED:{index}")
        direct = isinstance(container, list)
        series = container if direct else container.get("samples") if isinstance(container, dict) else None
        if not isinstance(series, list):
            result["issues"].append(f"SAMPLE_CONTAINER_MISSING:{index}")
            continue
        raw_series_count += len(series)
        require(raw_series_count <= MAX_SERIES, "CALENDAR_SESSION_SOURCE_TOO_LARGE")
        for position, source in enumerate(series):
            path = f"{key}[{index}].samples" + ("" if direct else ".samples") + f"[{position}]"
            if not isinstance(source, dict):
                result["issues"].append(f"SERIES_INVALID:{index}:{position}")
                continue
            kind = source.get("type")
            values = source.get("values")
            count = len(values) if isinstance(values, list) else 0
            raw_slots += count
            require(count <= MAX_SERIES_SLOTS and raw_slots <= MAX_SLOTS, "CALENDAR_SESSION_SOURCE_TOO_LARGE")
            if not isinstance(kind, str) or kind not in METRICS:
                result["unsupported"].append({"exercise_index": index, "source_path": path,
                    "source_type": kind[:120] if isinstance(kind, str) else "UNKNOWN", "slot_count": count})
                continue
            interval = source.get("intervalMillis")
            interval = interval if type(interval) is int and 0 < interval <= 86_400_000 else None
            issues = []
            if not isinstance(values, list):
                values = []
                issues.append("VALUES_CONTAINER_INVALID")
            normalized = []
            for value in values:
                n = numeric(value)
                if n is not None and n < 0 and kind not in ("ALTITUDE", "TEMPERATURE"):
                    n = None
                normalized.append(n)
            valid = sum(v is not None for v in normalized)
            if interval is None:
                issues.append("SAMPLE_INTERVAL_UNKNOWN")
            if valid < len(normalized):
                issues.append("MISSING_OR_INVALID_VALUES")
            metric, unit = METRICS[kind]
            result["series"].append({"id": f"e{index}-s{position}", "exercise_index": index,
                "source_path": path, "source_type": kind, "metric_key": metric, "unit": unit,
                "interval_ms": interval, "slot_count": len(normalized), "valid_sample_count": valid,
                "missing_sample_count": len(normalized) - valid, "values": normalized, "issues": issues})
            result["slot_count"] += len(normalized)
            result["valid_sample_count"] += valid
    if not result["series"]:
        result["issues"].append("NO_SUPPORTED_SAMPLES")
    return result


async def detail(*, owner, session_id, session):
    require(session.in_transaction() is False, "CALENDAR_FRESH_SESSION_REQUIRED")
    try:
        user = (await session.execute(select(User).where(User.id == UUID(owner)))).scalar_one_or_none()
        require(user is not None, "CALENDAR_SESSION_NOT_FOUND")
        ZoneInfo(user.timezone)  # Fail visibly if the saved zone is not valid.
        row = (await session.execute(select(WorkoutSession).where(
            WorkoutSession.id == UUID(session_id), WorkoutSession.user_id == UUID(owner)
        ))).scalar_one_or_none()
        require(row is not None, "CALENDAR_SESSION_NOT_FOUND")
        summary = {"id": str(row.id), "name": row.name, "sport": row.sport.value,
                   "external_provider": row.external_provider, "external_id": row.external_id,
                   "started_at": aware(row.started_at).isoformat(),
                   "ended_at": aware(row.ended_at).isoformat() if row.ended_at else None,
                   "planned_workout_id": str(row.planned_workout_id) if row.planned_workout_id else None,
                   "planned_workout_link_source": row.planned_workout_link_source.value if row.planned_workout_link_source else None,
                   **{name: numeric(getattr(row, name)) for name in SUMMARY_METRICS}}
        plan = None
        found = None
        if row.planned_workout_id:
            found = (await session.execute(select(PlannedWorkout).options(selectinload(PlannedWorkout.blocks)).where(
                PlannedWorkout.id == row.planned_workout_id, PlannedWorkout.user_id == UUID(owner)
            ))).scalar_one_or_none()
            if found is not None:
                require(len(found.blocks) <= 4000, "CALENDAR_SESSION_SOURCE_TOO_LARGE")
                plan = {"id": str(found.id), "date": found.date.isoformat(), "title": found.title,
                    "description": found.description, "sport": found.sport.value, "status": found.status.value,
                    "planned_start_time": aware(found.planned_start_time).isoformat() if found.planned_start_time else None,
                    "duration_sec": numeric(found.duration_sec), "distance_m": numeric(found.distance_m),
                    "blocks": [{"id": str(b.id), "position": b.position, "block_type": b.block_type.value,
                        "name": b.name, "duration_sec": numeric(b.duration_sec), "distance_m": numeric(b.distance_m),
                        "intensity_type": b.intensity_type, "intensity_min": numeric(b.intensity_min),
                        "intensity_max": numeric(b.intensity_max), "repeat_count": b.repeat_count,
                        "parent_block_id": str(b.parent_block_id) if b.parent_block_id else None} for b in found.blocks]}
        projection = samples(row.raw_data, row.external_provider)
        projection["route_content_hash"] = hashlib.sha256(json.dumps(projection["routes"], ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        # Preserve existing manual phase-reference keys when only GPS is enriched.
        clock_projection = {k: v for k, v in projection.items() if k not in ("routes", "route_content_hash")}
        projection["content_hash"] = hashlib.sha256(json.dumps(clock_projection, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return {"schema_version": SCHEMA, "athlete_id": owner, "timezone_name": user.timezone,
                "retrieved_at": datetime.now(UTC).isoformat(), "session": summary, "plan": plan,
                "link_state": "linked" if plan else "linked_plan_unavailable" if row.planned_workout_id else "unlinked",
                "samples": projection,
                "sections": section_groups(row.raw_data, row.external_provider),
                "plan_timeline": plan_timeline(found),
                "planning_authorized": False, "workouts_changed": False}
    finally:
        await session.rollback()
