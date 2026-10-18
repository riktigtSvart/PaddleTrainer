"""Read-only session comparison exports using the configured existing owner."""
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.plan_contracts import _existing_owner_id
from app.db.session import get_db
from app.models.entities import WorkoutSession
from app.planning_contracts.execution_adapter import canonical_bytes
from app.services.plan_execution_comparison_read import API_RULES_VERSION, ComparisonReadError, read_owned_comparison

router = APIRouter(tags=["plan-execution-comparisons"])
MAX_PAGE_BYTES = 12 * 1024 * 1024


def _queries(request, allowed):
    keys = [key for key, _ in request.query_params.multi_items()]
    if set(keys) - set(allowed) or len(keys) != len(set(keys)):
        raise HTTPException(422, "COMPARISON_UNSUPPORTED_OR_DUPLICATE_QUERY_FIELDS")


def withheld(session_id, exc):
    result = {"status": "WITHHELD", "session_id": str(session_id), "blocking_reason": exc.code,
              "comparison": None, "integration_bundle": None,
              "actual_phase_alignment_verified": False, "historical_plan_content_verified": False,
              "numeric_output_authorized": False, "state_estimation_authorized": False,
              "training_authorized": False, "capability_update_performed": False,
              "database_writes": 0, "provider_calls": 0,
              "speed_model_retrained": False, "state_model_trained": False, "new_independent_test": False}
    if exc.upstream_reason:
        result["upstream_reason"] = exc.upstream_reason
    return result


@router.get("/sessions/{session_id}/plan-execution-comparison")
async def get_plan_execution_comparison(
    session_id: UUID, response: Response, request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    include_bundle: bool = False, include_source: bool = False,
):
    response.headers["Cache-Control"] = "no-store"
    _queries(request, ("include_bundle", "include_source"))
    owner = await _existing_owner_id(db)
    if owner is None:
        raise HTTPException(404, "COMPARISON_CONFIGURED_OWNER_NOT_FOUND", headers={"Cache-Control": "no-store"})
    with db.no_autoflush:
        row = await db.scalar(select(WorkoutSession).where(WorkoutSession.id == session_id, WorkoutSession.user_id == owner))
    if row is None:
        raise HTTPException(404, "COMPARISON_SESSION_NOT_FOUND", headers={"Cache-Control": "no-store"})
    try:
        return await read_owned_comparison(db, row, owner, include_bundle=include_bundle, include_source=include_source)
    except ComparisonReadError as exc:
        raise HTTPException(exc.status_code, withheld(session_id, exc), headers={"Cache-Control": "no-store"}) from None


def page(items, rows, limit, offset):
    more = len(rows) > len(items)
    return {"status": "STORED_PLAN_EXECUTION_COMPARISON_PAGE", "api_rules_version": API_RULES_VERSION,
            "identity_scope": "APPLICATION_DEMO_USER", "items": items, "limit": limit, "offset": offset,
            "has_more": more, "next_offset": offset + len(items) if more else None,
            "returned_count": len(items), "converted_count": sum(i["status"] != "WITHHELD" for i in items),
            "withheld_count": sum(i["status"] == "WITHHELD" for i in items),
            "database_writes": 0, "provider_calls": 0, "numeric_output_authorized": False,
            "state_estimation_authorized": False, "capability_update_performed": False,
            "speed_model_retrained": False, "state_model_trained": False, "new_independent_test": False,
            "count_scope": "OWNED_CURRENT_STORED_SESSION_ROWS_NOT_COMPLETE_TRAINING_HISTORY",
            "coverage_scope": "ROW_COVERAGE_NOT_VERIFIED_ALIGNMENT_OR_PRESCRIPTION_COMPLETION"}


@router.get("/planning/plan-execution-comparisons")
async def list_plan_execution_comparisons(
    response: Response, request: Request, db: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=10)] = 2,
    offset: Annotated[int, Query(ge=0, le=100000)] = 0,
    include_bundle: bool = False, include_source: bool = False,
):
    response.headers["Cache-Control"] = "no-store"
    _queries(request, ("limit", "offset", "include_bundle", "include_source"))
    owner = await _existing_owner_id(db)
    if owner is None:
        raise HTTPException(404, "COMPARISON_CONFIGURED_OWNER_NOT_FOUND", headers={"Cache-Control": "no-store"})
    with db.no_autoflush:
        rows = list((await db.scalars(select(WorkoutSession).where(WorkoutSession.user_id == owner).order_by(
            WorkoutSession.started_at, WorkoutSession.id).offset(offset).limit(limit + 1))).unique())
    items = []
    captured_at = datetime.now(timezone.utc).isoformat()
    for row in rows[:limit]:
        try:
            item = await read_owned_comparison(db, row, owner, captured_at=captured_at,
                                               include_bundle=include_bundle, include_source=include_source)
        except ComparisonReadError as exc:
            item = withheld(row.id, exc)
        candidate = page(items + [item], rows, limit, offset)
        if len(canonical_bytes(candidate)) > MAX_PAGE_BYTES:
            if not items:
                raise HTTPException(413, "COMPARISON_PAGE_BYTE_LIMIT", headers={"Cache-Control": "no-store"})
            break
        items.append(item)
    result = page(items, rows, limit, offset)
    if len(canonical_bytes(result)) > MAX_PAGE_BYTES:
        raise HTTPException(413, "COMPARISON_PAGE_BYTE_LIMIT", headers={"Cache-Control": "no-store"})
    return result
