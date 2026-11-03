"""Training settings have explicit writes, configured-owner identity and closed queries."""

from fastapi import APIRouter, Response
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.api.routes.athlete_setup import DayQuery, SetupRoute, error
from app.api.routes.planning_goals import DB, Owner, _fresh
from app.planning.application.register_athlete_setup import SetupNotFound, SetupStorageError
from app.planning.domain.calendar_constraints import CalendarConstraintError
from app.schemas.training_options import OptionsInput
from app.services import training_options as service

router = APIRouter(prefix="/planning/training-options", tags=["training-options"], route_class=SetupRoute)


async def call(operation):
    try:
        return await operation
    except CalendarConstraintError as exc:
        raise error(409, str(exc)) from None
    except SetupNotFound:
        raise error(404, "TRAINING_OPTIONS_NOT_FOUND") from None
    except IntegrityError:
        raise error(409, "TRAINING_OPTIONS_REQUEST_CONFLICT") from None
    except (SQLAlchemyError, SetupStorageError, ValueError, KeyError, TypeError, RuntimeError):
        raise error(503, "TRAINING_OPTIONS_SOURCE_UNAVAILABLE") from None


@router.get("")
async def context(db: DB, owner: Owner, start_date: DayQuery | None = None, end_date: DayQuery | None = None):
    _fresh(db)
    if (start_date is None) != (end_date is None):
        raise error(422, "TRAINING_OPTIONS_RANGE_INVALID")
    return await call(service.context(session=db, owner=owner, first=start_date, last=end_date))


@router.post("", status_code=201)
async def save(payload: OptionsInput, response: Response, db: DB, owner: Owner):
    _fresh(db)
    value = await call(service.save(session=db, owner=owner, proposal=payload.model_dump(mode="json")))
    response.status_code = 200 if value["reused"] else 201
    return value
