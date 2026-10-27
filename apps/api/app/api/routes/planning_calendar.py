"""Bounded owned calendar reads and explicit immutable presentation-goal writes."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.api.routes.planning_goals import DB, GoalRoute, Owner, _fresh
from app.planning.application import calendar_workspace as service
from app.planning.application import calendar_constraints as constraints
from app.planning.domain import athlete_setup, calendar_constraints
from app.planning.domain.persistence.audit import AuditArtifactConflictError
from app.planning.infrastructure.repositories.postgres_planning_audit import SqlAlchemyPlanningAuditRepository
from app.schemas.planning_calendar import WorkoutGoalInput
from app.schemas.calendar_constraints import ScheduleInput, SchedulePreview


class CalendarRoute(GoalRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request):
            try:
                return await original(request)
            except RequestValidationError:
                return JSONResponse({"detail": {"code": "CALENDAR_INPUT_INVALID"}}, status_code=422, headers={"Cache-Control": "no-store"})

        return handler


router = APIRouter(prefix="/planning/calendar", tags=["planning-calendar"], route_class=CalendarRoute)
Day = Annotated[str, Query(pattern=r"^\d{4}-\d{2}-\d{2}$")]


def error(status, code):
    return HTTPException(status, {"code": code}, headers={"Cache-Control": "no-store"})


async def call(operation):
    try:
        return await operation
    except (service.CalendarRuleError, calendar_constraints.CalendarConstraintError, athlete_setup.SetupRuleError) as exc:
        code = str(exc)
        status = 404 if code.endswith("NOT_FOUND") else 503 if "STORAGE" in code else 409
        raise error(status, code) from None
    except (IntegrityError, AuditArtifactConflictError):
        raise error(409, "CALENDAR_REQUEST_IDENTITY_CONFLICT") from None
    except (SQLAlchemyError, ValueError, KeyError, TypeError, RuntimeError):
        raise error(503, "CALENDAR_SOURCE_UNAVAILABLE") from None


@router.get("/feed")
async def calendar_feed(db: DB, owner: Owner, start_date: Day | None = None, end_date: Day | None = None):
    _fresh(db)
    if (start_date is None) != (end_date is None):
        raise error(422, "CALENDAR_DATE_RANGE_INVALID")
    if start_date is not None:
        from app.api.routes.athlete_setup import valid_range
        valid_range(start_date, end_date)
    return await call(service.feed(owner=owner, start=start_date, end=end_date, repository=SqlAlchemyPlanningAuditRepository(db), session=db))


@router.post("/goals", status_code=201)
async def goal_tag(payload: WorkoutGoalInput, response: Response, db: DB, owner: Owner):
    _fresh(db)
    result = await call(service.save_goal(owner=owner, proposal=payload.model_dump(mode="json"), repository=SqlAlchemyPlanningAuditRepository(db), session=db))
    response.status_code = 200 if result["reused"] else 201
    return result


@router.get("/constraints")
async def constraint_context(db: DB, owner: Owner, start_date: Day | None = None, end_date: Day | None = None):
    _fresh(db)
    if (start_date is None) != (end_date is None):
        raise error(422, "CALENDAR_CONSTRAINT_RANGE_INVALID")
    return await call(constraints.projected(owner=owner, first=start_date, last=end_date,
        repository=SqlAlchemyPlanningAuditRepository(db), session=db))


@router.post("/constraints/preview")
async def constraint_preview(payload: SchedulePreview, db: DB, owner: Owner):
    _fresh(db)
    return await call(constraints.projected(owner=owner, first=payload.start_date, last=payload.end_date,
        proposal=payload.proposal.model_dump(mode="json"),
        availability_proposal=payload.availability_proposal.model_dump(mode="json") if payload.availability_proposal else None,
        repository=SqlAlchemyPlanningAuditRepository(db), session=db))


@router.post("/constraints", status_code=201)
async def constraint_save(payload: ScheduleInput, response: Response, db: DB, owner: Owner):
    _fresh(db)
    result = await call(constraints.save(owner=owner, proposal=payload.model_dump(mode="json"),
        repository=SqlAlchemyPlanningAuditRepository(db), session=db))
    response.status_code = 200 if result["reused"] else 201
    return result


from uuid import UUID
from app.planning.application import calendar_moves as moves
from app.schemas.calendar_moves import MoveProposal, MoveSave

@router.get("/moves/{plan_id}")
async def move_context(plan_id: UUID, db: DB, owner: Owner):
    _fresh(db)
    return await call(moves.context(owner=owner, plan_id=str(plan_id), repository=SqlAlchemyPlanningAuditRepository(db), session=db))

@router.post("/moves/preview")
async def move_preview(payload: MoveProposal, db: DB, owner: Owner):
    _fresh(db)
    return await call(moves.preview(owner=owner, proposal=payload.model_dump(mode="json"), repository=SqlAlchemyPlanningAuditRepository(db), session=db))

@router.post("/moves", status_code=201)
async def move_save(payload: MoveSave, response: Response, db: DB, owner: Owner):
    _fresh(db)
    result = await call(moves.save(owner=owner, proposal=payload.proposal.model_dump(mode="json"), review_hash=payload.review_hash, repository=SqlAlchemyPlanningAuditRepository(db), session=db))
    response.status_code = 200 if result["reused"] else 201
    return result
