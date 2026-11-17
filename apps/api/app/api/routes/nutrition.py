"""Closed, configured-owner menu and shopping endpoints; no provider calls."""
from fastapi import APIRouter, Request, Response
from app.api.routes.athlete_setup import SetupRoute, call
from app.api.routes.planning_goals import DB, Owner, _fresh
from app.planning.infrastructure.repositories.postgres_planning_audit import SqlAlchemyPlanningAuditRepository
from app.schemas.nutrition import NutritionWrite
from app.services import nutrition as service
from app.schemas.nutrition_journal import JournalWrite
from app.services import nutrition_journal as journal

router = APIRouter(prefix='/planning/nutrition', tags=['nutrition'], route_class=SetupRoute)


@router.get('')
async def read(db: DB, owner: Owner):
    _fresh(db)
    return await call(service.read(repository=SqlAlchemyPlanningAuditRepository(db), session=db, owner=owner))


@router.post('', status_code=201)
async def save(payload: NutritionWrite, request: Request, response: Response, db: DB, owner: Owner):
    _fresh(db)
    value = await call(service.save(repository=SqlAlchemyPlanningAuditRepository(db), session=db, owner=owner, proposal=payload.model_dump()))
    response.status_code = 200 if value['reused'] else 201
    return value


@router.get('/journal')
async def read_journal(db: DB, owner: Owner):
    _fresh(db)
    return await call(journal.read(repository=SqlAlchemyPlanningAuditRepository(db), session=db, owner=owner))


@router.post('/journal', status_code=201)
async def save_journal(payload: JournalWrite, response: Response, db: DB, owner: Owner):
    _fresh(db)
    value = await call(journal.save(repository=SqlAlchemyPlanningAuditRepository(db), session=db, owner=owner, proposal=payload.model_dump()))
    response.status_code = 200 if value['reused'] else 201
    return value
