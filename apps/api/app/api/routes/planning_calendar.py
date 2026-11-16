"""Bounded owned calendar reads and explicit immutable presentation-goal writes."""

from typing import Annotated
from uuid import UUID
import logging
from time import perf_counter

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
from app.services.training_plans import TrainingPlanError
from app.schemas.training_plans import SavedChoiceInput
from app.schemas.manual_workouts import ManualSave

logger = logging.getLogger(__name__)


class CalendarRoute(GoalRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request):
            started = perf_counter()
            try:
                response = await original(request)
            except RequestValidationError as exc:
                detail = {"code": "CALENDAR_INPUT_INVALID"}
                if self.path.endswith('/manual-workouts'):
                    detail = {"code": "MANUAL_INPUT_INVALID", "issues": [
                        {"path": list(e['loc'][1:]), "message": e['msg'], "type": e['type']}
                        for e in exc.errors()[:30]]}
                response = JSONResponse({"detail": detail}, status_code=422, headers={"Cache-Control": "no-store"})
            if request.method == 'GET' and self.path.endswith(('/feed', '/cycles', '/constraints')):
                elapsed = (perf_counter() - started) * 1000
                response.headers['Server-Timing'] = f'calendar;dur={elapsed:.1f}'
                if elapsed >= 5000:
                    logger.warning('Slow calendar read: endpoint=%s duration_ms=%.1f status=%s',
                                   self.path, elapsed, response.status_code)
            return response

        return handler


router = APIRouter(prefix="/planning/calendar", tags=["planning-calendar"], route_class=CalendarRoute)
Day = Annotated[str, Query(pattern=r"^\d{4}-\d{2}-\d{2}$")]


@router.get('/manual-workouts/context')
async def manual_workout_context(db: DB, owner: Owner):
    from app.services import manual_workouts
    _fresh(db)
    return await call(manual_workouts.context(owner=owner, repository=SqlAlchemyPlanningAuditRepository(db), session=db))


@router.get('/manual-workouts/{workout_id}')
async def manual_workout_source(workout_id: UUID, db: DB, owner: Owner):
    from app.services import manual_workouts
    _fresh(db)
    return await call(manual_workouts.context(owner=owner, workout_id=str(workout_id),
        repository=SqlAlchemyPlanningAuditRepository(db), session=db))


@router.post('/manual-workouts')
async def manual_workout_save(body: ManualSave, db: DB, owner: Owner):
    from app.services import manual_workouts
    _fresh(db)
    return await call(manual_workouts.save(owner=owner, proposal=body.model_dump(mode='json'),
        repository=SqlAlchemyPlanningAuditRepository(db), session=db))


def error(status, code):
    return HTTPException(status, {"code": code}, headers={"Cache-Control": "no-store"})


async def call(operation):
    try:
        return await operation
    except (service.CalendarRuleError, calendar_constraints.CalendarConstraintError, athlete_setup.SetupRuleError, TrainingPlanError) as exc:
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


@router.get("/cycles")
async def cycle_context(db: DB, owner: Owner, start_date: Day, end_date: Day):
    from app.services import calendar_cycles
    from app.api.routes.athlete_setup import valid_range
    _fresh(db)
    valid_range(start_date, end_date)
    return await call(calendar_cycles.context(owner=owner, start=start_date, end=end_date,
        repository=SqlAlchemyPlanningAuditRepository(db), session=db))


@router.get('/workouts/{workout_id}/alternatives')
async def saved_alternatives(workout_id: UUID, db: DB, owner: Owner):
    from app.services import calendar_saved_options
    _fresh(db)
    return await call(calendar_saved_options.read(session=db, owner=owner, workout_id=str(workout_id)))


@router.post('/workouts/{workout_id}/alternatives/choose')
async def choose_saved_alternative(workout_id: UUID, payload: SavedChoiceInput, db: DB, owner: Owner):
    from app.services import calendar_saved_options
    _fresh(db)
    return await call(calendar_saved_options.choose(session=db, owner=owner, workout_id=str(workout_id), proposal=payload.model_dump(mode='json')))


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


from app.planning.application import calendar_moves as moves
from app.schemas.calendar_moves import MoveProposal, MoveSave
from app.services import session_analysis


@router.get("/sessions/{session_id}")
async def session_detail(session_id: UUID, db: DB, owner: Owner):
    _fresh(db)
    return await call(session_analysis.detail(owner=owner, session_id=str(session_id), session=db))

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


from app.schemas.session_feedback import FeedbackInput
from app.services import session_feedback

@router.get("/sessions/{session_id}/feedback")
async def feedback_context(session_id: UUID, db: DB, owner: Owner):
    _fresh(db)
    return await call(session_feedback.context(owner=owner, session_id=str(session_id),
        repository=SqlAlchemyPlanningAuditRepository(db), session=db))

@router.post("/sessions/{session_id}/feedback", status_code=201)
async def feedback_save(session_id: UUID, payload: FeedbackInput, response: Response, db: DB, owner: Owner):
    _fresh(db)
    result = await call(session_feedback.save(owner=owner, session_id=str(session_id),
        proposal=payload.model_dump(mode="json"), repository=SqlAlchemyPlanningAuditRepository(db), session=db))
    response.status_code = 200 if result["reused"] else 201
    # The feedback has already committed. Learning refresh failure must never
    # masquerade as a failed user save or discard its idempotent receipt.
    try:
        result["learning"] = await feedback_learning.refresh(owner=owner, session_id=str(session_id), session=db)
    except (SQLAlchemyError, ValueError, KeyError, TypeError, RuntimeError, LookupError):
        await db.rollback()
        result["learning"] = {"state":"retry_required"}
    return result


from datetime import datetime
from app.services import feedback_learning
from app.schemas.feedback_learning import FeedbackLearningRefresh

@router.get("/sessions/{session_id}/learning")
async def feedback_learning_context(session_id: UUID, db: DB, owner: Owner, information_cutoff_at: datetime | None = None):
    _fresh(db)
    return await call(feedback_learning.context(owner=owner, session_id=str(session_id), session=db, cutoff=information_cutoff_at))

@router.post("/sessions/{session_id}/learning")
async def feedback_learning_refresh(session_id: UUID, payload: FeedbackLearningRefresh, db: DB, owner: Owner):
    _fresh(db)
    return await call(feedback_learning.refresh(owner=owner, session_id=str(session_id), session=db))


@router.get("/learning-inputs")
async def personal_feedback_inputs(db: DB, owner: Owner, start_date: Day | None = None, end_date: Day | None = None):
    from datetime import UTC, time, timedelta
    from app.planning.application.feedback_personal_inputs import assemble_feedback_personal_inputs
    from app.planning.domain.common.serialization import to_contract_primitive
    from app.planning.domain.training_dynamics import PersonalAssociationPredictorKey
    from app.api.routes.athlete_setup import valid_range
    _fresh(db)
    now = feedback_learning._now()
    if (start_date is None) != (end_date is None):
        raise error(422,"CALENDAR_DATE_RANGE_INVALID")
    from zoneinfo import ZoneInfo
    from sqlalchemy import select
    from app.models.entities import User
    user = (await db.execute(select(User).where(User.id == UUID(owner)))).scalar_one()
    timezone_name = user.timezone
    zone = ZoneInfo(timezone_name)
    if start_date:
        valid_range(start_date,end_date)
        start = datetime.combine(datetime.fromisoformat(start_date).date(),time.min,tzinfo=zone).astimezone(UTC)
        end = min(now, datetime.combine(datetime.fromisoformat(end_date).date() + timedelta(days=1),time.min,tzinfo=zone).astimezone(UTC))
    else:
        start, end = now - timedelta(days=90), now
    if start > end:
        raise error(422,"CALENDAR_DATE_RANGE_INVALID")
    try:
        result = await call(assemble_feedback_personal_inputs(session=db,athlete_id=owner,
            history_id="pt-training-dynamics-history:c12:" + service.digest({"owner":owner,"start":start.isoformat(),"end":end.isoformat(),"cutoff":now.isoformat()}),
            window_start_at=start,as_of=now,information_cutoff_at=now,observation_end_at=end,
            predictor_keys=(PersonalAssociationPredictorKey(metric_key="duration_s",unit="s"),),created_at=now))
        return {"schema_version":"feedback-personal-inputs-v0.1","athlete_id":owner,
            "timezone_name":timezone_name,"response_window_end_at":end.isoformat(),
            "selection_scope":"response_observed_at",
            "information_cutoff_at":now.isoformat(),"window_start_at":start.isoformat(),"as_of":now.isoformat(),"assembly":to_contract_primitive(result),"planning_authorized":False,"model_updated":False}
    finally:
        await db.rollback()


from app.services import execution_connection
from app.schemas.execution_connection import ExecutionConnectionInput

@router.get("/sessions/{session_id}/execution-connection")
async def execution_connection_preview(session_id: UUID, db: DB, owner: Owner):
    _fresh(db)
    return await call(execution_connection.preview(owner=owner,session_id=str(session_id),session=db))

@router.post("/sessions/{session_id}/execution-connection", status_code=201)
async def execution_connection_save(session_id: UUID, payload: ExecutionConnectionInput, response: Response, db: DB, owner: Owner):
    _fresh(db)
    result = await call(execution_connection.connect(owner=owner,session_id=str(session_id),
        proposal=payload.model_dump(mode="json"),session=db))
    response.status_code = 200 if result["reused"] else 201
    try:
        result["learning"] = await feedback_learning.refresh(owner=owner,session_id=str(session_id),session=db)
    except (SQLAlchemyError, ValueError, KeyError, TypeError, RuntimeError, LookupError):
        await db.rollback()
        result["learning"] = {"state":"retry_required"}
    return result


from app.schemas.strength_workout import StrengthWorkoutInput
from app.services import strength_workout_log

@router.get("/sessions/{session_id}/strength-log")
async def strength_log_context(session_id: UUID, db: DB, owner: Owner):
    _fresh(db)
    return await call(strength_workout_log.context(owner=owner, session_id=str(session_id),
        repository=SqlAlchemyPlanningAuditRepository(db), session=db))

@router.post("/sessions/{session_id}/strength-log", status_code=201)
async def strength_log_save(session_id: UUID, payload: StrengthWorkoutInput, response: Response, db: DB, owner: Owner):
    _fresh(db)
    result = await call(strength_workout_log.save(owner=owner, session_id=str(session_id),
        proposal=payload.model_dump(mode="json"), repository=SqlAlchemyPlanningAuditRepository(db), session=db))
    if result['reused']:
        response.status_code = 200
    return result
