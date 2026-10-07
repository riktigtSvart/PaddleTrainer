"""TCX/ZIP verification and immutable evidence for the connected Polar account."""

from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.integrations.polar.client import PolarAPIError, PolarClient
from app.models.entities import ExternalConnection
from app.services.hr_timebase_persistence import (
    load_current_hr_timebase_snapshots,
    persist_hr_timebase_snapshot,
)
from app.services.hr_timebase_snapshot import current_hr_source_hash, resolve_hr_timebase_snapshots
from app.services.polar_tokens import get_valid_access_token
from app.services.tcx_heart_rate_timebase import (
    MAX_IMPORT_BYTES,
    build_tcx_heart_rate_timebase,
)
from app.services.users import get_or_create_demo_user

router = APIRouter(prefix="/integrations/polar", tags=["polar"])


@router.post(
    "/sessions/{session_external_id}/hr-timebase/verify-tcx",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                kind: {"schema": {"type": "string", "format": "binary"}}
                for kind in ("application/xml", "application/zip", "application/octet-stream")
            },
        }
    },
)
async def verify_training_session_tcx_timebase(
    session_external_id: str,
    request: Request,
    sample_date: Annotated[date, Query()],
    db: Annotated[AsyncSession, Depends(get_db)],
    exercise_external_id: Annotated[str | None, Query()] = None,
):
    """Send a TCX or ZIP as the raw request body; no database evidence is saved."""
    if sample_date == date.max:
        raise HTTPException(422, "Sample date cannot be the last representable date.")
    body = await _read_tcx_body(request)
    _, sample_session, match_count = await _fetch_sample_session(
        db, session_external_id, sample_date
    )
    return build_tcx_heart_rate_timebase(
        body,
        sample_session,
        expected_session_external_id=session_external_id,
        sample_session_match_count=match_count,
        expected_exercise_external_id=exercise_external_id,
    )


@router.post(
    "/sessions/{session_external_id}/hr-timebase/persist-tcx",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                kind: {"schema": {"type": "string", "format": "binary"}}
                for kind in ("application/xml", "application/zip", "application/octet-stream")
            },
        }
    },
)
async def persist_training_session_tcx_timebase(
    session_external_id: str,
    request: Request,
    sample_date: Annotated[date, Query()],
    db: Annotated[AsyncSession, Depends(get_db)],
    exercise_external_id: Annotated[str | None, Query()] = None,
):
    """Persist only a freshly verified, immutable export-timebase snapshot."""
    if sample_date == date.max:
        raise HTTPException(422, "Sample date cannot be the last representable date.")
    body = await _read_tcx_body(request)
    user, sample_session, match_count = await _fetch_sample_session(
        db, session_external_id, sample_date
    )
    verification = build_tcx_heart_rate_timebase(
        body,
        sample_session,
        expected_session_external_id=session_external_id,
        sample_session_match_count=match_count,
        expected_exercise_external_id=exercise_external_id,
    )
    persistence = {"status": "NOT_STORED", "persists_timebase_evidence": False}
    if verification["export_timebase_verified"]:
        try:
            persistence = await persist_hr_timebase_snapshot(
                db,
                verification,
                sample_session,
                athlete_id=str(user.id),
                session_external_id=session_external_id,
                sample_session_match_count=match_count,
            )
        except ValueError:
            raise HTTPException(
                409, "HR timebase snapshot source or round-trip verification failed."
            ) from None
    return {"verification": verification, "persistence": persistence}


@router.get("/sessions/{session_external_id}/hr-timebase/saved")
async def inspect_saved_training_session_hr_timebase(
    session_external_id: str,
    sample_date: Annotated[date, Query()],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Revalidate saved proof against current source data; no TCX is required."""
    user, sample_session, match_count = await _fetch_sample_session(
        db, session_external_id, sample_date
    )
    records = await load_current_hr_timebase_snapshots(
        db,
        sample_session,
        athlete_id=str(user.id),
        session_external_id=session_external_id,
        sample_session_match_count=match_count,
    )
    resolved = resolve_hr_timebase_snapshots(
        records,
        sample_session,
        athlete_id=str(user.id),
        session_external_id=session_external_id,
        sample_session_match_count=match_count,
    )
    source_hash = current_hr_source_hash(
        sample_session,
        session_external_id=session_external_id,
        sample_session_match_count=match_count,
    )
    return {
        "session_external_id": session_external_id,
        "source_binding_verified": source_hash is not None,
        "current_api_source_hash": source_hash,
        "stored_current_source_snapshot_count": len(records),
        "saved_timebase": resolved,
        "training_authorized": False,
        "numeric_prediction_authorized": False,
    }


async def _read_tcx_body(request):
    media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type not in (
        "application/xml",
        "text/xml",
        "application/zip",
        "application/octet-stream",
    ):
        raise HTTPException(415, "Send TCX XML or ZIP bytes as the raw request body.")
    if request.headers.get("content-encoding", "identity").lower() != "identity":
        raise HTTPException(415, "Compressed HTTP request encoding is not supported.")
    declared_length = request.headers.get("content-length")
    if declared_length is not None:
        try:
            length = int(declared_length)
        except ValueError:
            raise HTTPException(400, "Invalid Content-Length.") from None
        if length < 0:
            raise HTTPException(400, "Invalid Content-Length.")
        if length > MAX_IMPORT_BYTES:
            raise HTTPException(413, "TCX/ZIP upload exceeds the 16 MiB limit.")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_IMPORT_BYTES:
            raise HTTPException(413, "TCX/ZIP upload exceeds the 16 MiB limit.")
        body.extend(chunk)
    return bytes(body)


async def _fetch_sample_session(db, session_external_id, sample_date):
    if sample_date == date.max:
        raise HTTPException(422, "Sample date cannot be the last representable date.")
    user = await get_or_create_demo_user(db)
    connection = await db.scalar(
        select(ExternalConnection).where(
            ExternalConnection.user_id == user.id,
            ExternalConnection.provider == "POLAR",
        )
    )
    if connection is None:
        raise HTTPException(404, "Polar connection not found")
    if "training_sessions:read" not in (connection.scopes or []):
        raise HTTPException(403, "Polar training_sessions:read scope not authorized")
    token = await get_valid_access_token(db, connection)
    try:
        payload = await PolarClient().list_training_sessions(
            token, sample_date, sample_date + timedelta(days=1), features=["samples"]
        )
    except PolarAPIError:
        raise HTTPException(502, "Polar training sample request failed.") from None
    sessions = payload.get("trainingSessions") if isinstance(payload, dict) else None
    if not isinstance(sessions, list):
        raise HTTPException(502, "Polar returned an invalid training sample payload.")
    matched = [
        s
        for s in sessions
        if isinstance(s, dict)
        and isinstance(s.get("identifier"), dict)
        and str(s["identifier"].get("id")) == session_external_id
    ]
    return user, matched[0] if len(matched) == 1 else None, len(matched)
