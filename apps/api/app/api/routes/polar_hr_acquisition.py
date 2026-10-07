"""Explicit HR sensor statements for the current user's Polar exercise."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.polar_tcx import _fetch_sample_session
from app.db.session import get_db
from app.schemas.hr_acquisition import HRAcquisitionDeclarationCreate
from app.services.hr_acquisition_declarations import (
    MAX_DECLARATIONS,
    HRAcquisitionDeclarationError,
    acquisition_declaration_history,
    resolve_hr_acquisition_declarations,
)
from app.services.hr_acquisition_persistence import (
    load_current_hr_acquisition_declarations,
    persist_hr_acquisition_declaration,
)

router = APIRouter(prefix="/integrations/polar", tags=["polar"])
SessionId = Annotated[str, Path(min_length=1, max_length=200)]


@router.post("/sessions/{session_external_id}/hr-acquisition/declarations")
async def create_hr_acquisition_declaration(
    session_external_id: SessionId,
    payload: HRAcquisitionDeclarationCreate,
    sample_date: Annotated[date, Query()],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    user, sample, count = await _fetch_sample_session(db, session_external_id, sample_date)
    kwargs = {
        "athlete_id": str(user.id),
        "session_external_id": session_external_id,
        "sample_session_match_count": count,
    }
    try:
        persistence = await persist_hr_acquisition_declaration(
            db, payload.model_dump(mode="json"), sample, **kwargs
        )
    except HRAcquisitionDeclarationError as exc:
        raise HTTPException(409, str(exc)) from None
    records = await load_current_hr_acquisition_declarations(db, sample, **kwargs)
    context = resolve_hr_acquisition_declarations(records, sample, **kwargs)
    return {"persistence": persistence, "acquisition_context": context}


@router.get("/sessions/{session_external_id}/hr-acquisition")
async def inspect_hr_acquisition_declarations(
    session_external_id: SessionId,
    sample_date: Annotated[date, Query()],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    user, sample, count = await _fetch_sample_session(db, session_external_id, sample_date)
    kwargs = {
        "athlete_id": str(user.id),
        "session_external_id": session_external_id,
        "sample_session_match_count": count,
    }
    records = await load_current_hr_acquisition_declarations(db, sample, **kwargs)
    context = resolve_hr_acquisition_declarations(records, sample, **kwargs)
    history_available = not context["rejected_record_count"] and len(records) <= MAX_DECLARATIONS
    return {
        "session_external_id": session_external_id,
        "source_binding_verified": context["source_binding_verified"],
        "stored_current_source_declaration_count": len(records),
        "history_scope": "CURRENT_API_SOURCE",
        "history_available": history_available,
        "declaration_history": acquisition_declaration_history(records)
        if history_available
        else [],
        "acquisition_context": context,
        "training_authorized": False,
        "numeric_prediction_authorized": False,
    }
