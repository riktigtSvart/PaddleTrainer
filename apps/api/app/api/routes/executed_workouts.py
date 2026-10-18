"""Owner-scoped, read-only ExecutedWorkout exports of already stored sessions."""
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.plan_contracts import _existing_owner_id
from app.db.session import get_db
from app.models.entities import WorkoutSession
from app.planning_contracts.execution_adapter import ADAPTER_VERSION, ExecutionAdapterError, canonical_bytes
from app.services.executed_workout_read import read_owned_execution

router = APIRouter(tags=["executed-workout-contracts"])
MAX_PAGE_BYTES = 12 * 1024 * 1024


def _queries(request, allowed):
    if set(request.query_params) - set(allowed):
        raise HTTPException(422, "EXECUTION_UNSUPPORTED_QUERY_FIELDS")


def _error(exc):
    return HTTPException(exc.status_code, {"code": exc.code, "database_writes": 0, "provider_calls": 0})


@router.get("/sessions/{session_id}/executed-workout")
async def get_executed_workout(
    session_id: UUID, response: Response, request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    response.headers["Cache-Control"] = "no-store"
    _queries(request, ())
    owner = await _existing_owner_id(db)
    if owner is None:
        raise HTTPException(404, "EXECUTION_CONFIGURED_OWNER_NOT_FOUND")
    with db.no_autoflush:
        row = await db.scalar(select(WorkoutSession).where(WorkoutSession.id == session_id, WorkoutSession.user_id == owner))
    if row is None:
        raise HTTPException(404, "EXECUTION_SESSION_NOT_FOUND")
    try:
        return await read_owned_execution(db, row, owner)
    except ExecutionAdapterError as exc:
        raise _error(exc) from None


@router.get("/planning/executed-workouts")
async def list_executed_workouts(
    response: Response, request: Request, db: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=10)] = 2,
    offset: Annotated[int, Query(ge=0, le=100000)] = 0,
):
    response.headers["Cache-Control"] = "no-store"
    _queries(request, ("limit", "offset"))
    owner = await _existing_owner_id(db)
    if owner is None:
        raise HTTPException(404, "EXECUTION_CONFIGURED_OWNER_NOT_FOUND")
    with db.no_autoflush:
        rows = list((await db.scalars(select(WorkoutSession).where(WorkoutSession.user_id == owner).order_by(
            WorkoutSession.started_at, WorkoutSession.id).offset(offset).limit(limit + 1))).unique())
    items, used = [], 0
    captured_at = datetime.now(timezone.utc).isoformat()
    for row in rows[:limit]:
        try:
            item = await read_owned_execution(db, row, owner, captured_at=captured_at)
        except ExecutionAdapterError as exc:
            item = {"status": "WITHHELD", "session_id": str(row.id), "blocking_reason": exc.code,
                    "numeric_output_authorized": False, "database_writes": 0, "provider_calls": 0}
        size = len(canonical_bytes(item))
        if used + size > MAX_PAGE_BYTES:
            if not items:
                raise HTTPException(413, "EXECUTION_PAGE_BYTE_LIMIT")
            break
        items.append(item)
        used += size
    has_more = len(rows) > len(items)
    return {"status": "STORED_EXECUTED_WORKOUT_PAGE", "adapter_version": ADAPTER_VERSION,
            "identity_scope": "APPLICATION_DEMO_USER", "items": items, "limit": limit, "offset": offset,
            "has_more": has_more, "next_offset": offset + len(items) if has_more else None,
            "returned_count": len(items), "converted_count": sum(i["status"] != "WITHHELD" for i in items),
            "withheld_count": sum(i["status"] == "WITHHELD" for i in items), "database_writes": 0,
            "provider_calls": 0, "numeric_output_authorized": False,
            "count_scope": "OWNED_CURRENT_STORED_SESSION_ROWS_NOT_COMPLETE_TRAINING_HISTORY"}
