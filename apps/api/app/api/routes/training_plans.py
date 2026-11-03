"""A sample plan can only be applied through explicit, current review."""

from fastapi import APIRouter, Response
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.api.routes.planning_cycles import CycleRoute, Identity, error
from app.api.routes.planning_goals import DB, Owner, _fresh
from app.planning.application.create_cycle_program import CycleNotFound
from app.schemas.training_plans import AcceptInput, ChoiceInput, MissedInput, ReviewInput
from app.services import training_plans as service
from app.services.planning_inputs import PlanningInputError

router = APIRouter(
    prefix="/planning/cycles/programs/{identity}/training-plan",
    tags=["training-plan"],
    route_class=CycleRoute,
)


async def call(operation):
    try:
        return await operation
    except CycleNotFound:
        raise error(404, "CYCLE_PROGRAM_NOT_FOUND") from None
    except service.TrainingPlanError as exc:
        raise error(409, str(exc)) from None
    except PlanningInputError as exc:
        raise error(409, str(exc)) from None
    except IntegrityError:
        raise error(409, "TRAINING_PLAN_REQUEST_CONFLICT") from None
    except (SQLAlchemyError, ValueError, RuntimeError, LookupError, TypeError):
        raise error(503, "TRAINING_PLAN_SOURCE_UNAVAILABLE") from None


@router.get("")
async def status(identity: Identity, db: DB, owner: Owner):
    _fresh(db)
    return await call(service.status(session=db, owner=owner, program_id=identity))


@router.post("/review")
async def review(identity: Identity, payload: ReviewInput, db: DB, owner: Owner):
    _fresh(db)
    return await call(
        service.review(
            session=db,
            owner=owner,
            program_id=identity,
            first=payload.start_date,
            last=payload.end_date,
        )
    )


@router.post("/accept", status_code=201)
async def accept(
    identity: Identity, payload: AcceptInput, response: Response, db: DB, owner: Owner
):
    result = await call(
        service.accept(session=db, owner=owner, program_id=identity, proposal=payload.model_dump())
    )
    response.status_code = 200 if result["reused"] else 201
    return result


@router.post("/choose")
async def choose(identity: Identity, payload: ChoiceInput, db: DB, owner: Owner):
    _fresh(db)
    return await call(service.choose(session=db, owner=owner, program_id=identity, proposal=payload.model_dump()))


@router.post("/missed", status_code=201)
async def missed(
    identity: Identity, payload: MissedInput, response: Response, db: DB, owner: Owner
):
    result = await call(
        service.confirm_missed(
            session=db, owner=owner, program_id=identity, proposal=payload.model_dump()
        )
    )
    response.status_code = 200 if result["reused"] else 201
    return result
