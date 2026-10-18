"""Explicit persistent answers; old read and inspect endpoints stay stateless."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import ProgrammingError, OperationalError
from starlette.concurrency import run_in_threadpool

from app.api.routes.phase_reconciliations import owned_row, queries
from app.db.session import get_db
from app.models.phase_clarification import PhaseClarificationRevision as Revision
from app.planning_contracts.phase_reconciliation_input import strict_loads
from app.schemas.phase_clarification_storage import PhaseClarificationSaveRequest
from app.services.phase_reconciliation_read import PhaseReconciliationReadError
from app.services.phase_clarification_storage import (
    PhaseStorageError, STORAGE_VERSION, read_saved_state, save_revision,
    storage_capabilities, revision_metadata, verify_revision,
)

router = APIRouter(tags=['phase-clarification-storage'])
MAX_BODY_BYTES = 256*1024


def fail(exc):
    if isinstance(exc, (ProgrammingError, OperationalError)):
        code = getattr(getattr(exc, 'orig', None), 'sqlstate', None)
        missing = code == '42P01' or 'no such table: phase_clarification_revisions' in str(exc)
        if not missing:
            raise exc
        reason, status = 'PHASE_STORAGE_MIGRATION_REQUIRED', 503
    else:
        reason, status = exc.code, exc.status_code
    return HTTPException(status, {'status': 'WITHHELD', 'blocking_reason': reason,
        'storage_version': STORAGE_VERSION, 'actual_phase_alignment_verified': False,
        'numeric_prediction_authorized': False, 'provider_calls': 0}, headers={'Cache-Control':'no-store'})


@router.get('/planning/phase-reconciliation/storage-capabilities')
def capabilities(request: Request, response: Response):
    queries(request, ())
    response.headers['Cache-Control'] = 'no-store'
    return storage_capabilities()


@router.get('/sessions/{session_id}/phase-reconciliation/state')
async def state(session_id: UUID, request: Request, response: Response,
                db: Annotated[AsyncSession, Depends(get_db)], include_source: bool = False):
    queries(request, ('include_source',))
    response.headers['Cache-Control'] = 'no-store'
    owner, row = await owned_row(db, session_id)
    try:
        return await read_saved_state(db, row, owner, include_source=include_source)
    except (PhaseStorageError, ProgrammingError, OperationalError) as exc:
        raise fail(exc) from None


# The versioned Flow reference is a separate read view, not a clarification write.
from app.api.routes.flow_phase_time_evidence import router as flow_time_router
router.include_router(flow_time_router)


@router.post('/sessions/{session_id}/phase-reconciliation/clarifications')
async def save(session_id: UUID, body: PhaseClarificationSaveRequest, request: Request, response: Response,
               db: Annotated[AsyncSession, Depends(get_db)]):
    queries(request, ())
    response.headers['Cache-Control'] = 'no-store'
    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        raise HTTPException(413, 'PHASE_STORAGE_REQUEST_SIZE_LIMIT', headers={'Cache-Control':'no-store'})
    try:
        strict_loads(raw)
    except (ValueError, TypeError):
        raise HTTPException(422, 'PHASE_STORAGE_JSON_INVALID', headers={'Cache-Control':'no-store'}) from None
    owner, _ = await owned_row(db, session_id)
    try:
        return await save_revision(db, session_id, owner, body.model_dump(mode='json'))
    except (PhaseStorageError, PhaseReconciliationReadError, ProgrammingError, OperationalError) as exc:
        raise fail(exc) from None


@router.get('/sessions/{session_id}/phase-reconciliation/clarifications/history')
async def history(session_id: UUID, request: Request, response: Response,
                  db: Annotated[AsyncSession, Depends(get_db)],
                  limit: Annotated[int, Query(ge=1, le=25)] = 10,
                  offset: Annotated[int, Query(ge=0, le=100000)] = 0):
    queries(request, ('limit', 'offset'))
    response.headers['Cache-Control'] = 'no-store'
    owner, _ = await owned_row(db, session_id)
    try:
        with db.no_autoflush:
            rows = list((await db.scalars(select(Revision).where(Revision.user_id == owner, Revision.session_id == session_id)
                          .order_by(Revision.sequence.desc()).offset(offset).limit(limit+1))).all())
        records = await run_in_threadpool(lambda: [revision_metadata(row) for row in rows[:limit]])
        return {'status': 'PHASE_CLARIFICATION_HISTORY', 'storage_version': STORAGE_VERSION,
                'session_id': str(session_id), 'revisions': records, 'limit': limit, 'offset': offset,
                'has_more': len(rows)>limit, 'database_writes': 0, 'provider_calls': 0,
                'actual_phase_alignment_verified': False}
    except (PhaseStorageError, ProgrammingError, OperationalError) as exc:
        raise fail(exc) from None


@router.get('/sessions/{session_id}/phase-reconciliation/clarifications/{revision_id}')
async def revision(session_id: UUID, revision_id: UUID, request: Request, response: Response,
                   db: Annotated[AsyncSession, Depends(get_db)], include_source: bool = False):
    queries(request, ('include_source',))
    response.headers['Cache-Control'] = 'no-store'
    owner, _ = await owned_row(db, session_id)
    try:
        with db.no_autoflush:
            row = await db.scalar(select(Revision).where(Revision.user_id == owner, Revision.session_id == session_id,
                                                         Revision.id == revision_id))
        if row is None:
            raise HTTPException(404, 'PHASE_STORAGE_REVISION_NOT_FOUND', headers={'Cache-Control':'no-store'})
        evidence = await run_in_threadpool(verify_revision, row)
        metadata = await run_in_threadpool(revision_metadata, row)
        return {'status': 'PHASE_CLARIFICATION_ARCHIVED_REVISION', 'storage_version': STORAGE_VERSION,
                'revision': metadata, 'archived_reconciliation': evidence if include_source else None,
                'archived_evidence_is_current_source': False, 'database_writes': 0, 'provider_calls': 0,
                'actual_phase_alignment_verified': False}
    except (PhaseStorageError, ProgrammingError, OperationalError) as exc:
        raise fail(exc) from None
