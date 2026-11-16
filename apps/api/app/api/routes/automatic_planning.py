from fastapi import APIRouter, Request, Response
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from app.api.routes.athlete_setup import SetupRoute, error
from app.api.routes.planning_goals import DB, Owner, _fresh
from app.planning.application.create_cycle_program import CycleNotFound
from app.schemas.automatic_planning import AutomaticSettingInput, AutomaticRunInput
from app.services import automatic_planning as service

router = APIRouter(prefix='/planning/automation', tags=['automatic-planning'], route_class=SetupRoute)


async def call(operation):
    try:
        return await operation
    except service.AutomaticPlanningError as exc:
        raise error(409, str(exc)) from None
    except CycleNotFound:
        raise error(404, 'AUTOMATIC_PLANNING_PROGRAM_NOT_FOUND') from None
    except IntegrityError:
        raise error(409, 'AUTOMATIC_PLANNING_REQUEST_CONFLICT') from None
    except (SQLAlchemyError, ValueError, KeyError, TypeError, RuntimeError):
        raise error(503, 'AUTOMATIC_PLANNING_SOURCE_UNAVAILABLE') from None


def closed(request, db):
    if request.url.query:
        raise error(422, 'AUTOMATIC_PLANNING_QUERY_INVALID')
    _fresh(db)


@router.get('')
async def context(request: Request, db: DB, owner: Owner):
    closed(request, db)
    return await call(service.context(session=db, owner=owner))


@router.post('', status_code=201)
async def save(payload: AutomaticSettingInput, request: Request, response: Response, db: DB, owner: Owner):
    closed(request, db)
    result = await call(service.save(session=db, owner=owner, proposal=payload.model_dump(mode='json')))
    response.status_code = 200 if result['reused'] else 201
    return result


@router.post('/run')
async def run(payload: AutomaticRunInput, request: Request, db: DB, owner: Owner):
    closed(request, db)
    result = await call(service.run_once(db, owner))
    return {'run': result, 'context': await call(service.context(session=db, owner=owner))}
