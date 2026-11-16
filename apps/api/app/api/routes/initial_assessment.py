"""Configured-owner assessment reads and explicit writes through closed routes."""
from fastapi import APIRouter, Request, Response
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from uuid import UUID

from app.api.routes.athlete_setup import SetupRoute, error
from app.api.routes.planning_goals import DB, Owner, _fresh
from app.planning.application.create_cycle_program import CycleNotFound, CycleStorageError
from app.planning.application.register_athlete_setup import SetupNotFound, SetupStorageError
from app.planning.domain.calendar_constraints import CalendarConstraintError
from app.schemas.initial_assessment import AssessmentInput
from app.services import initial_assessment as service

router = APIRouter(prefix='/planning/initial-assessment', tags=['initial-assessment'], route_class=SetupRoute)


async def call(operation):
    try:
        return await operation
    except CalendarConstraintError as exc:
        raise error(404 if str(exc) == 'INITIAL_ASSESSMENT_NOT_FOUND' else 409, str(exc)) from None
    except (SetupNotFound, CycleNotFound):
        raise error(404, 'INITIAL_ASSESSMENT_NOT_FOUND') from None
    except IntegrityError:
        raise error(409, 'INITIAL_ASSESSMENT_REQUEST_CONFLICT') from None
    except (SQLAlchemyError, SetupStorageError, CycleStorageError, ValueError, KeyError, TypeError, RuntimeError):
        raise error(503, 'INITIAL_ASSESSMENT_SOURCE_UNAVAILABLE') from None


@router.get('')
async def context(request: Request, db: DB, owner: Owner):
    if request.url.query:
        raise error(422, 'INITIAL_ASSESSMENT_QUERY_INVALID')
    _fresh(db)
    return await call(service.context(session=db, owner=owner))


@router.post('', status_code=201)
async def save(payload: AssessmentInput, request: Request, response: Response, db: DB, owner: Owner):
    if request.url.query:
        raise error(422, 'INITIAL_ASSESSMENT_QUERY_INVALID')
    _fresh(db)
    value = await call(service.save(session=db, owner=owner, proposal=payload.model_dump(mode='json')))
    response.status_code = 200 if value['reused'] else 201
    return value


@router.get('/revisions/{token}')
async def revision(token: UUID, request: Request, db: DB, owner: Owner):
    if request.url.query:
        raise error(422, 'INITIAL_ASSESSMENT_QUERY_INVALID')
    _fresh(db)
    return await call(service.read_revision(session=db, owner=owner, token=str(token)))
