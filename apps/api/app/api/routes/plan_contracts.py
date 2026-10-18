"""Read-only exports of the configured owner's already stored workout plans."""
from datetime import date, datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.db.session import get_db
from app.models.entities import PlannedWorkout, User
from app.services.plan_contract_read import (
    API_RULES_VERSION, CONTRACT_TYPES, PlanReadError, build_plan_read,
    canonical_bytes, schema_document, stored_workout_snapshot,
)

router = APIRouter(tags=["planning-contracts"])
MAX_PAGE_BYTES = 8 * 1024 * 1024


async def _existing_owner_id(db):
    with db.no_autoflush:
        return await db.scalar(select(User.id).where(User.email == get_settings().demo_user_email))


def _error(exc):
    return HTTPException(exc.status_code, {"code": exc.code, "database_writes": 0, "provider_calls": 0})


def _queries(request, allowed):
    if set(request.query_params) - set(allowed):
        raise HTTPException(422, "PLAN_CONTRACT_UNSUPPORTED_QUERY_FIELDS")


@router.get("/planning/contracts/capabilities")
async def capabilities():
    return {"api_rules_version": API_RULES_VERSION, "schema_version": "0.1", "contract_release": "DRAFT1",
            "identity_scope": "APPLICATION_DEMO_USER", "source_scope": "CURRENT_OWNED_STORED_PLANS",
            "supported_contract_schemas": list(CONTRACT_TYPES), "max_page_size": 25,
            "plan_path": "/api/v1/workouts/{workout_id}/plan-contract",
            "list_path": "/api/v1/planning/plan-contracts", "read_only": True,
            "snapshot_identity_scope": "SERVER_READ_CAPTURE; SOURCE_HASH_IDENTIFIES_EQUAL_STORED_CONTENT",
            "schema_checker_scope": "PINNED_SCHEMA_SUBSET_PLUS_DOMAIN_RULES_NOT_A_GENERAL_JSON_SCHEMA_ENGINE",
            "executed_workout_adapter_available": True,
            "executed_workout_adapter_version": "executed-workout-adapter-0.1-draft2",
            "executed_workout_repeat_policy": "STRUCTURAL_REPEATS_KEEP_LEAF_TRANSITION_RULES_CANDIDATE",
            "executed_workout_phase_clock_policy": "DECLARED_ROUTE_INDEX_TRANSFER_CANDIDATE_OR_EXPLICIT_NATIVE_INDEX_FALLBACK",
            "executed_workout_legacy_replay_versions": ["executed-workout-adapter-0.1-draft1"],
            "executed_workout_path": "/api/v1/sessions/{session_id}/executed-workout",
            "executed_workout_list_path": "/api/v1/planning/executed-workouts",
            "executed_workout_max_page_size": 10,
            "executed_workout_source_scope": "CURRENT_OWNED_STORED_SESSIONS_WITH_OPTIONAL_CANDIDATE_PHASES",
            "plan_execution_comparison_available": True,
            "plan_execution_comparison_api_version": "plan-execution-comparison-read-api-0.1",
            "plan_execution_comparison_path": "/api/v1/sessions/{session_id}/plan-execution-comparison",
            "plan_execution_comparison_list_path": "/api/v1/planning/plan-execution-comparisons",
            "plan_execution_comparison_max_page_size": 10,
            "plan_execution_comparison_source_scope": "CURRENT_OWNED_STORED_SESSION_AND_CURRENT_PLAN_CAPTURE",
            "plan_execution_comparison_optional_views": ["include_bundle", "include_source"],
            "numeric_output_authorized": False,
            "state_estimation_authorized": False, "database_writes": 0, "provider_calls": 0}


@router.get("/planning/contracts/schemas/{contract_type}")
async def get_contract_schema(contract_type: str):
    try:
        return schema_document(contract_type)
    except PlanReadError as exc:
        raise _error(exc) from None


@router.get("/workouts/{workout_id}/plan-contract")
async def get_plan_contract(
    workout_id: UUID, response: Response, request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    response.headers["Cache-Control"] = "no-store"
    _queries(request, ())
    owner_id = await _existing_owner_id(db)
    if owner_id is None:
        raise HTTPException(404, "PLAN_CONTRACT_CONFIGURED_OWNER_NOT_FOUND")
    with db.no_autoflush:
        row = await db.scalar(select(PlannedWorkout).options(selectinload(PlannedWorkout.blocks)).where(
            PlannedWorkout.id == workout_id, PlannedWorkout.user_id == owner_id))
    if row is None:
        raise HTTPException(404, "PLAN_CONTRACT_WORKOUT_NOT_FOUND")
    try:
        snapshot = stored_workout_snapshot(row, owner_id)
        return await run_in_threadpool(build_plan_read, snapshot)
    except PlanReadError as exc:
        raise _error(exc) from None


@router.get("/planning/plan-contracts")
async def list_plan_contracts(
    response: Response, request: Request, db: Annotated[AsyncSession, Depends(get_db)],
    date_from: date | None = None, date_to: date | None = None,
    limit: Annotated[int, Query(ge=1, le=25)] = 10,
    offset: Annotated[int, Query(ge=0, le=100000)] = 0,
):
    response.headers["Cache-Control"] = "no-store"
    _queries(request, ("date_from", "date_to", "limit", "offset"))
    if date_from is not None and date_to is not None and date_from > date_to:
        raise HTTPException(422, "PLAN_CONTRACT_DATE_RANGE_REVERSED")
    owner_id = await _existing_owner_id(db)
    if owner_id is None:
        raise HTTPException(404, "PLAN_CONTRACT_CONFIGURED_OWNER_NOT_FOUND")
    query = select(PlannedWorkout).options(selectinload(PlannedWorkout.blocks)).where(PlannedWorkout.user_id == owner_id)
    if date_from is not None:
        query = query.where(PlannedWorkout.date >= date_from)
    if date_to is not None:
        query = query.where(PlannedWorkout.date <= date_to)
    with db.no_autoflush:
        rows = list((await db.scalars(query.order_by(PlannedWorkout.date, PlannedWorkout.id).offset(offset).limit(limit + 1))).unique())
    captured_at = datetime.now(timezone.utc).isoformat()
    items, used = [], 0
    for row in rows[:limit]:
        try:
            snapshot = stored_workout_snapshot(row, owner_id)
            item = await run_in_threadpool(build_plan_read, snapshot, captured_at=captured_at)
        except PlanReadError as exc:
            item = {"status": "WITHHELD", "workout_id": str(row.id), "blocking_reason": exc.code,
                    "numeric_output_authorized": False, "database_writes": 0, "provider_calls": 0}
        size = len(canonical_bytes(item))
        if used + size > MAX_PAGE_BYTES:
            if not items:
                raise HTTPException(413, "PLAN_CONTRACT_PAGE_BYTE_LIMIT")
            break
        items.append(item)
        used += size
    has_more = len(rows) > len(items)
    return {"status": "STORED_PLAN_CONTRACT_PAGE", "api_rules_version": API_RULES_VERSION,
            "identity_scope": "APPLICATION_DEMO_USER", "items": items, "limit": limit, "offset": offset,
            "has_more": has_more, "next_offset": offset + len(items) if has_more else None,
            "returned_count": len(items), "converted_count": sum(i["status"] != "WITHHELD" for i in items),
            "withheld_count": sum(i["status"] == "WITHHELD" for i in items),
            "database_writes": 0, "provider_calls": 0, "numeric_output_authorized": False,
            "count_scope": "OWNED_STORED_PLANS_ON_THIS_PAGE_NOT_EXECUTED_WORKOUTS"}
