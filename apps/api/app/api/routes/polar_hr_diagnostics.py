"""Read-only HR diagnostics for the connected owner's current Polar source."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.polar_tcx import _fetch_sample_session
from app.db.session import get_db
from app.services.heart_rate_signal_diagnostics import (
    DEFAULT_DETAIL_LIMIT,
    MAX_DETAIL_LIMIT,
    build_training_session_hr_signal_diagnostics,
)
from app.services.hr_acquisition_persistence import load_current_hr_acquisition_declarations
from app.services.hr_timebase_persistence import load_current_hr_timebase_snapshots

router = APIRouter(prefix="/integrations/polar", tags=["polar"])


@router.get("/sessions/{session_external_id}/hr-diagnostics")
async def inspect_training_session_hr_signal_diagnostics(
    session_external_id: Annotated[str, Path(min_length=1, max_length=200)],
    sample_date: Annotated[date, Query()],
    db: Annotated[AsyncSession, Depends(get_db)],
    detail_limit: Annotated[int, Query(ge=1, le=MAX_DETAIL_LIMIT)] = DEFAULT_DETAIL_LIMIT,
):
    user, sample, count = await _fetch_sample_session(db, session_external_id, sample_date)
    kwargs = {
        "athlete_id": str(user.id),
        "session_external_id": session_external_id,
        "sample_session_match_count": count,
    }
    clocks = await load_current_hr_timebase_snapshots(db, sample, **kwargs)
    declarations = await load_current_hr_acquisition_declarations(db, sample, **kwargs)
    return build_training_session_hr_signal_diagnostics(
        sample,
        hr_timebase_snapshots=clocks,
        hr_acquisition_declarations=declarations,
        detail_limit=detail_limit,
        **kwargs,
    )
