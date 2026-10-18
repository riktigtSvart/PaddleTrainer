"""Read source-bound displayed execution time evidence without changing answers."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import ProgrammingError, OperationalError

from app.api.routes.phase_reconciliations import owned_row, queries
from app.db.session import get_db
from app.planning_contracts.flow_phase_time_evidence import FlowEvidenceError
from app.services.phase_reconciliation_read import PhaseReconciliationReadError
from app.services.phase_clarification_storage import PhaseStorageError
from app.services import flow_phase_time_evidence_read as service

router = APIRouter(tags=['flow-phase-time-evidence'])


@router.get('/planning/phase-reconciliation/execution-time-evidence-capabilities')
def capabilities(request: Request, response: Response):
    queries(request, ())
    response.headers['Cache-Control'] = 'no-store'
    return service.capabilities()


@router.get('/sessions/{session_id}/phase-reconciliation/execution-time-evidence')
async def evidence(session_id: UUID, request: Request, response: Response,
                   db: Annotated[AsyncSession, Depends(get_db)], include_source: bool = False):
    queries(request, ('include_source',))
    response.headers['Cache-Control'] = 'no-store'
    owner, row = await owned_row(db, session_id)
    try:
        return await service.read_owned_evidence(db, row, owner, include_source=include_source)
    except (FlowEvidenceError, PhaseStorageError, PhaseReconciliationReadError) as exc:
        raise HTTPException(exc.status_code, {'status': 'WITHHELD', 'blocking_reason': exc.code,
            'database_writes': 0, 'provider_calls': 0, 'actual_phase_alignment_verified': False,
            'numeric_prediction_authorized': False}, headers={'Cache-Control': 'no-store'}) from None
    except (ProgrammingError, OperationalError) as exc:
        from app.api.routes.phase_clarification_storage import fail
        raise fail(exc) from None
