"""Read candidate phases and inspect answers for the existing configured owner."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.plan_contracts import _existing_owner_id
from app.db.session import get_db
from app.models.entities import WorkoutSession
from app.planning_contracts.phase_reconciliation_input import strict_loads
from app.schemas.phase_reconciliation import PhaseClarificationInspectionRequest
from app.services.phase_reconciliation_read import (
    PhaseReconciliationReadError,capabilities,read_owned_phase_reconciliation,
)

router=APIRouter(tags=['phase-reconciliation'])
MAX_INSPECTION_BODY_BYTES=256*1024


def queries(request,allowed):
    keys=[key for key,_ in request.query_params.multi_items()]
    if set(keys)-set(allowed) or len(keys)!=len(set(keys)):
        raise HTTPException(422,'PHASE_RECONCILIATION_UNSUPPORTED_OR_DUPLICATE_QUERY_FIELDS',
                            headers={'Cache-Control':'no-store'})


def withheld(session_id,exc):
    value={'status':'WITHHELD','session_id':str(session_id),'blocking_reason':exc.code,
        'result':None,'source_comparison_read':None,'actual_phase_alignment_verified':False,
        'numeric_prediction_authorized':False,'training_authorized':False,
        'database_writes':0,'provider_calls':0,'clarifications_persisted':False,
        'speed_model_retrained':False,'new_independent_model_test':False}
    if exc.upstream_reason:
        value['upstream_reason']=exc.upstream_reason
    return value


async def owned_row(db,session_id):
    owner=await _existing_owner_id(db)
    if owner is None:
        raise HTTPException(404,'PHASE_RECONCILIATION_CONFIGURED_OWNER_NOT_FOUND',headers={'Cache-Control':'no-store'})
    with db.no_autoflush:
        row=await db.scalar(select(WorkoutSession).where(WorkoutSession.id==session_id,WorkoutSession.user_id==owner))
    if row is None:
        raise HTTPException(404,'PHASE_RECONCILIATION_SESSION_NOT_FOUND',headers={'Cache-Control':'no-store'})
    return owner,row


@router.get('/planning/phase-reconciliation/capabilities')
def get_capabilities(request:Request,response:Response):
    response.headers['Cache-Control']='no-store'
    queries(request,())
    return capabilities()


@router.get('/sessions/{session_id}/phase-reconciliation')
async def get_reconciliation(session_id:UUID,request:Request,response:Response,
    db:Annotated[AsyncSession,Depends(get_db)],include_source:bool=False):
    response.headers['Cache-Control']='no-store'
    queries(request,('include_source',))
    owner,row=await owned_row(db,session_id)
    try:
        return await read_owned_phase_reconciliation(db,row,owner,include_source=include_source)
    except PhaseReconciliationReadError as exc:
        raise HTTPException(exc.status_code,withheld(session_id,exc),headers={'Cache-Control':'no-store'}) from None


@router.post('/sessions/{session_id}/phase-reconciliation/clarifications/inspect')
async def inspect_clarifications(session_id:UUID,body:PhaseClarificationInspectionRequest,
    request:Request,response:Response,db:Annotated[AsyncSession,Depends(get_db)],include_source:bool=False):
    response.headers['Cache-Control']='no-store'
    queries(request,('include_source',))
    raw=await request.body()
    if len(raw)>MAX_INSPECTION_BODY_BYTES:
        raise HTTPException(413,'PHASE_RECONCILIATION_INSPECTION_BODY_LIMIT',headers={'Cache-Control':'no-store'})
    try:
        strict_loads(raw)
    except (ValueError,TypeError):
        raise HTTPException(422,'PHASE_RECONCILIATION_INSPECTION_JSON_INVALID',headers={'Cache-Control':'no-store'}) from None
    owner,row=await owned_row(db,session_id)
    try:
        return await read_owned_phase_reconciliation(db,row,owner,include_source=include_source,
                                                     clarifications=body.model_dump(mode='json'))
    except PhaseReconciliationReadError as exc:
        raise HTTPException(exc.status_code,withheld(session_id,exc),headers={'Cache-Control':'no-store'}) from None
