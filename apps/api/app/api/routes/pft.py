"""PFT measurement ingestion, versioned retrieval and descriptive comparisons."""
from datetime import datetime
from typing import Annotated
from uuid import UUID
import json

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Request
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool
from app.pft_engine.archive.comparison import (
    PftComparisonIncompatible, compare_pft_documents,
)
from dataclasses import asdict
from app.db.session import get_db
from app.schemas.pft import PftComparisonRequest, PftMeasurementContext
from app.services.users import get_or_create_demo_user
from app.services.pft_processing import (
    MAX_PFT_IMPORT_BYTES, PftInputError, PftIntegrityError, comparable_context,
    process_recording, sample_payload,
)
from app.services.pft_persistence import (
    get_measurement, get_recording, list_measurements, response_document,
    save_measurement, utc, verify_measurement, verify_recording,
)

router = APIRouter(prefix="/pft", tags=["pft"])


async def pft_owner(db: Annotated[AsyncSession, Depends(get_db)]):
    # This application has a demo-user identity model. Never accept a client
    # athlete_id, and keep owner selection replaceable by future authentication.
    return await get_or_create_demo_user(db)


async def _read_body(request):
    size = 0
    parts = []
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_PFT_IMPORT_BYTES:
            raise HTTPException(413, "PFT_IMPORT_SIZE_LIMIT")
        parts.append(chunk)
    return b"".join(parts)


def _context(text):
    try:
        return PftMeasurementContext.model_validate_json(text)
    except ValidationError:
        raise HTTPException(422, "PFT_CONTEXT_INVALID_OR_UNSUPPORTED_FIELDS") from None


async def _owned(db, owner, identity):
    row = await get_measurement(db, owner.id, identity)
    if row is None:
        raise HTTPException(404, "PFT_MEASUREMENT_NOT_FOUND")
    return row


def _integrity_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except (PftIntegrityError, PftInputError, KeyError, TypeError, ValueError):
        raise HTTPException(409, "PFT_STORED_EVIDENCE_INVALID") from None


@router.get("/capabilities")
async def capabilities():
    return {
        "protocol": "PFT-RUN", "protocol_version": "0.1", "engine_version": "0.2.0",
        "supported_sources": ["TCX_UPLOAD"],
        "native_polar_capture": "HR_POWER_CLOCK_ORIGIN_VERIFICATION_REQUIRED",
        "identity_scope": "APPLICATION_DEMO_USER",
        "state_estimation_authorized": False, "training_plan_modification_authorized": False,
    }


@router.post("/measurements/tcx", openapi_extra={"requestBody": {
    "required": True, "content": {"application/xml": {"schema": {
        "type": "string", "format": "binary"
    }}}
}})
async def import_tcx(
    request: Request,
    context_json: Annotated[str, Header(alias="X-PFT-Context", min_length=2, max_length=6000)],
    db: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[object, Depends(pft_owner)],
    filename: Annotated[str, Query(min_length=1, max_length=200)] = "pft.tcx",
):
    context = _context(context_json)
    raw = await _read_body(request)
    try:
        whole, selected, manifest, document = await run_in_threadpool(process_recording, raw, context)
        row, source, status = await save_measurement(
            db, owner_id=owner.id, filename=filename, raw=raw, whole=whole, selected=selected,
            manifest=manifest, document=document,
        )
        return _integrity_call(response_document, row, source, status=status)
    except PftInputError as exc:
        raise HTTPException(422, str(exc)) from None
    except PftIntegrityError:
        raise HTTPException(409, "PFT_STORED_EVIDENCE_INVALID") from None


@router.get("/measurements")
async def list_pft(
    db: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[object, Depends(pft_owner)],
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0, le=100000)] = 0,
):
    rows = await list_measurements(db, owner.id, limit, offset)
    measurements = []
    for row in rows:
        document = _integrity_call(verify_measurement, row)
        output = document["processing_output"]
        measurements.append({
            "measurement_id": str(row.id), "recording_id": str(row.recording_id),
            "started_at_utc": utc(row.started_at).isoformat(),
            "available_at_utc": utc(row.created_at).isoformat(),
            "quality_grade": output["session_quality_grade"],
            "algorithm_lineage": output["algorithm_lineage"],
            "profile_id": document["declared_context"]["profile_id"],
        })
    return {"measurements": measurements, "limit": limit, "offset": offset,
            "count_scope": "PROCESSING_VERSIONS", "state_estimation_authorized": False}


@router.get("/measurements/{measurement_id}")
async def get_pft(
    measurement_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[object, Depends(pft_owner)],
    include_samples: bool = False,
):
    row = await _owned(db, owner, measurement_id)
    source = await get_recording(db, owner.id, row.recording_id)
    if source is None:
        raise HTTPException(409, "PFT_RECORDING_MISSING")
    result = _integrity_call(response_document, row, source)
    if include_samples:
        session = _integrity_call(verify_recording, source)
        result["recording_samples"] = sample_payload(session)
    return result


@router.post("/measurements/{measurement_id}/reprocess")
async def reprocess_pft(
    measurement_id: UUID,
    context: PftMeasurementContext,
    db: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[object, Depends(pft_owner)],
):
    old = await _owned(db, owner, measurement_id)
    _integrity_call(verify_measurement, old)
    source = await get_recording(db, owner.id, old.recording_id)
    if source is None:
        raise HTTPException(409, "PFT_RECORDING_MISSING")
    _integrity_call(verify_recording, source)
    try:
        whole, selected, manifest, document = await run_in_threadpool(process_recording, source.raw_tcx, context)
        row, source, status = await save_measurement(
            db, owner_id=owner.id, filename=source.source_filename, raw=source.raw_tcx,
            whole=whole, selected=selected, manifest=manifest, document=document,
        )
        return _integrity_call(response_document, row, source, status=status)
    except PftInputError as exc:
        raise HTTPException(422, str(exc)) from None


@router.post("/measurements/{measurement_id}/compare")
async def compare_pft(
    measurement_id: UUID, payload: PftComparisonRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[object, Depends(pft_owner)],
):
    try:
        reference_id = UUID(payload.reference_measurement_id)
    except ValueError:
        raise HTTPException(422, "PFT_REFERENCE_ID_INVALID") from None
    current = await _owned(db, owner, measurement_id)
    reference = await _owned(db, owner, reference_id)
    verified = []
    for row in (current, reference):
        source = await get_recording(db, owner.id, row.recording_id)
        if source is None:
            raise HTTPException(409, "PFT_RECORDING_MISSING")
        verified.append(_integrity_call(response_document, row, source))
    current_doc, reference_doc = verified
    for field in ("adapter", "engine_version", "engine_source_hash", "processing_rules"):
        if current.processing_manifest[field] != reference.processing_manifest[field]:
            raise HTTPException(409, "PFT_PROCESSING_LINEAGE_DIFFERS")
    if comparable_context(current_doc["declared_context"]) != comparable_context(reference_doc["declared_context"]):
        raise HTTPException(409, "PFT_DECLARED_REFERENCE_CONTEXT_DIFFERS")
    if utc(reference.started_at) > utc(current.started_at):
        raise HTTPException(409, "PFT_REFERENCE_STARTS_AFTER_CURRENT_MEASUREMENT")
    try:
        comparison = compare_pft_documents(
            reference=reference_doc["processing_output"], current=current_doc["processing_output"]
        )
    except PftComparisonIncompatible:
        raise HTTPException(409, "PFT_PROCESSING_LINEAGE_DIFFERS") from None
    distinct = current.recording_id != reference.recording_id
    available_before = (utc(reference.ended_at) <= utc(current.started_at)
                        and utc(reference.created_at) <= utc(current.started_at))
    return {
        "status": "DESCRIPTIVE_PFT_COMPARISON_WITH_LIMITATIONS",
        "comparison": asdict(comparison),
        "independent_recordings": distinct,
        "reference_available_before_current_start": available_before,
        "scope": "RETROSPECTIVE_OBSERVATIONS",
        "limitations": ["MEASURED_LOAD_EQUIVALENCE_NOT_ESTABLISHED",
                       "DECLARATIONS_NOT_INDEPENDENTLY_VERIFIED",
                       "PERSONAL_STATE_MODEL_NOT_VALIDATED"],
        "state_estimation_authorized": False, "training_plan_modification_authorized": False,
        "pre_exercise_prediction_authorized": False, "causal_prediction_authorized": False,
    }
