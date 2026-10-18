"""Read complete stored WorkoutSession rows and optional owned plan captures."""
from __future__ import annotations

import copy
from datetime import date, datetime, timezone
from enum import Enum
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from starlette.concurrency import run_in_threadpool

from app.models.entities import PlannedWorkout, WorkoutSession
from app.planning_contracts.contract_checks import ContractError
from app.planning_contracts.execution_adapter import (
    ADAPTER_VERSION, ExecutionAdapterError, build_execution_read, provider_target_id,
)
from app.planning_contracts.legacy_plan_adapter import AdapterError
from app.services.plan_contract_read import PlanReadError, build_plan_read, stored_workout_snapshot

SESSION_FIELDS = (
    "id", "user_id", "planned_workout_id", "planned_workout_link_source", "external_provider",
    "external_id", "sport", "name", "started_at", "ended_at", "duration_sec", "distance_m", "calories",
    "avg_hr", "max_hr", "avg_speed", "max_speed", "avg_cadence", "max_cadence", "avg_power", "max_power",
    "cardio_load", "perceived_load", "rpe", "raw_data", "created_at",
)


def _value(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return copy.deepcopy(value)


def stored_session_snapshot(row, owner_id):
    if str(row.user_id) != str(owner_id):
        raise ExecutionAdapterError("EXECUTION_SESSION_NOT_FOUND", 404)
    if set(WorkoutSession.__table__.columns.keys()) != set(SESSION_FIELDS):
        raise ExecutionAdapterError("EXECUTION_SOURCE_SCHEMA_CHANGED")
    return {field: _value(getattr(row, field)) for field in SESSION_FIELDS}


async def read_owned_execution(db, row, owner_id, *, captured_at=None):
    captured_at = captured_at or datetime.now(timezone.utc).isoformat()
    snapshot = stored_session_snapshot(row, owner_id)
    selected = None
    selection = {"method": "NONE", "status": "NO_OWNED_PLAN_LINK"}
    if row.planned_workout_id is not None:
        with db.no_autoflush:
            selected = await db.scalar(select(PlannedWorkout).options(selectinload(PlannedWorkout.blocks)).where(
                PlannedWorkout.id == row.planned_workout_id, PlannedWorkout.user_id == owner_id))
        selection = {"method": "STORED_PLAN_LINK", "status": "OWNED_PLAN_AVAILABLE" if selected else "PLAN_NOT_AVAILABLE_FOR_OWNER"}
    else:
        raw = snapshot["raw_data"]
        target_id = provider_target_id(raw) if isinstance(raw, dict) and row.external_provider == "POLAR" else None
        if target_id:
            with db.no_autoflush:
                candidates = list((await db.scalars(select(PlannedWorkout).options(selectinload(PlannedWorkout.blocks)).where(
                    PlannedWorkout.user_id == owner_id, PlannedWorkout.source == "POLAR",
                    PlannedWorkout.polar_target_id == target_id).order_by(PlannedWorkout.id).limit(2))).unique())
            selected = candidates[0] if len(candidates) == 1 else None
            selection = {"method": "EXACT_SOURCE_TARGET_ID_LOOKUP", "candidate_count_up_to_two": len(candidates),
                         "status": "OWNED_PLAN_AVAILABLE" if selected else ("AMBIGUOUS_OWNED_TARGET_ID" if candidates else "NO_OWNED_TARGET_MATCH")}
    plan_read = None
    if selected is not None:
        try:
            plan_snapshot = stored_workout_snapshot(selected, owner_id)
            plan_read = await run_in_threadpool(build_plan_read, plan_snapshot, captured_at=captured_at)
        except PlanReadError as exc:
            selection = {**selection, "status": "PLAN_CAPTURE_WITHHELD", "blocking_reason": exc.code}
    try:
        return await run_in_threadpool(build_execution_read, snapshot, captured_at=captured_at,
                                      plan_read=plan_read, plan_selection=selection)
    except ExecutionAdapterError:
        raise
    except (ContractError, AdapterError, KeyError, TypeError, ValueError, OverflowError, RecursionError):
        raise ExecutionAdapterError("EXECUTION_SOURCE_CONVERSION_WITHHELD") from None
