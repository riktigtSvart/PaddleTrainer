"""Closed configured-owner interface for the actual reference occasion."""
from fastapi import APIRouter, Request, Response
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.api.routes.athlete_setup import SetupRoute, error
from app.api.routes.planning_goals import DB, Owner, _fresh
from app.schemas.guided_strength import GuidedCommand
from app.schemas.strength_calibration import CalibrationCommand
from uuid import UUID
from app.services import guided_strength as service

router = APIRouter(prefix='/planning/guided-strength', tags=['guided-strength'], route_class=SetupRoute)


async def call(operation):
    try:
        return await operation
    except service.GuidedError as exc:
        raise error(409, str(exc)) from None
    except IntegrityError:
        raise error(409, 'GUIDED_REQUEST_CONFLICT') from None
    except (SQLAlchemyError, ValueError, KeyError, TypeError, RuntimeError):
        raise error(503, 'GUIDED_SOURCE_UNAVAILABLE') from None


@router.get('')
async def context(request: Request, db: DB, owner: Owner):
    if request.url.query:
        raise error(422, 'GUIDED_QUERY_INVALID')
    _fresh(db)
    return await call(service.context(session=db, owner=owner))


@router.post('', status_code=201)
async def command(payload: CalibrationCommand | GuidedCommand, request: Request, response: Response, db: DB, owner: Owner):
    if request.url.query:
        raise error(422, 'GUIDED_QUERY_INVALID')
    _fresh(db)
    value = await call(service.command(session=db, owner=owner, proposal=payload.model_dump(mode='json')))
    response.status_code = 200 if value['reused'] else 201
    return value


@router.get('/revisions/{token}')
async def revision(token: UUID, request: Request, db: DB, owner: Owner):
    if request.url.query:
        raise error(422, 'GUIDED_QUERY_INVALID')
    _fresh(db)
    return await call(service.read_revision(session=db, owner=owner, token=str(token)))
