"""Optional, read-only TCX/ZIP comparison against the connected Polar account."""

from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.integrations.polar.client import PolarAPIError, PolarClient
from app.models.entities import ExternalConnection
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
    return build_tcx_heart_rate_timebase(
        bytes(body),
        matched[0] if len(matched) == 1 else None,
        expected_session_external_id=session_external_id,
        sample_session_match_count=len(matched),
        expected_exercise_external_id=exercise_external_id,
    )
