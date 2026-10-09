"""Configured-owner cohort capture, archived readback and explicit revalidation."""

import json
from typing import Annotated, Literal
from uuid import UUID

from cryptography.fernet import InvalidToken
from fastapi import APIRouter, Depends, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.polar_response_cohort import (
    FAILURE_HTTP_STATUS,
    HEADERS,
    MAX_REQUEST_BYTES,
    VALIDATION_FIELDS,
    _finite_float,
    _nonfinite,
    _object,
    _summary,
)
from app.core.config import get_settings
from app.db.session import get_db
from app.models.entities import User
from app.schemas.response_cohort import ResponseCohortManifest
from app.services.response_cohort_assembly import (
    MAX_EXECUTION_MEMBERS,
    assemble_response_cohort,
    verify_cohort_index_integrity,
)
from app.services.response_cohort_persistence import (
    ASSEMBLY_DIAGNOSTICS,
    CohortStorageError,
    capture_response_cohort_record,
    load_owned_response_cohort_record,
)

STORED_CONFLICTS = frozenset(
    {
        "COHORT_STORAGE_SOURCE_LINK_CHANGED",
        "COHORT_STORAGE_SOURCE_PIN_CHANGED",
        "COHORT_STORED_PAYLOAD_INVALID",
        "COHORT_STORED_ROW_BINDING_INVALID",
        "COHORT_STORED_ROUND_TRIP_FAILED",
        "COHORT_STORED_MEMBERSHIP_INVALID",
        "COHORT_STORED_IDENTITY_AMBIGUOUS",
        "COHORT_STORAGE_WRITE_CONFLICT",
    }
)
STORAGE_HTTP_STATUS = {
    **dict.fromkeys(STORED_CONFLICTS, 409),
    "COHORT_STORAGE_OWNER_MISSING": 404,
    "COHORT_STORAGE_CLEAN_SESSION_REQUIRED": 422,
    "COHORT_STORAGE_REQUEST_INVALID": 422,
    "COHORT_CAPTURE_PAYLOAD_INVALID": 503,
    "COHORT_STORAGE_TIME_LIMIT": 504,
    "COHORT_STORAGE_DEPENDENCY_FAILURE": 503,
    "COHORT_STORAGE_CLEANUP_FAILED": 503,
}
DEPENDENCY_ERRORS = (
    SQLAlchemyError,
    InvalidToken,
    RuntimeError,
    OSError,
    ValueError,
    KeyError,
    TypeError,
    AttributeError,
    RecursionError,
)


def _failure(code, http_status, *, attempted=False, upstream=None, failed_member=None):
    """No record/hash/prefix or private validation value on a failed operation."""
    return JSONResponse(
        status_code=http_status,
        headers=HEADERS,
        content={
            "status": "REJECTED" if http_status in {400, 415, 422} else "WITHHELD",
            "blocking_reasons": [code],
            "upstream_reason": upstream if upstream in ASSEMBLY_DIAGNOSTICS else None,
            "failed_member_canonical_index": failed_member
            if type(failed_member) is int and 0 <= failed_member < MAX_EXECUTION_MEMBERS
            else None,
            "claim_scope": "NO_COHORT_CAPTURE_OR_CURRENT_SOURCE_PROOF_ISSUED",
            "record_id": None,
            "record_hash": None,
            "cohort_index_hash": None,
            "record_payload": None,
            "cohort_index": None,
            "stored_member_count": 0,
            "source_evidence_verified": False,
            "current_source_evidence_verified": False,
            "current_index_matches_archived_record": False,
            "round_trip_verified": False,
            "commit_acknowledged": False,
            "storage_attempted": attempted,
            "storage_outcome": "NOT_CONFIRMED" if attempted else "NOT_ATTEMPTED",
            "database_record_persisted": None if attempted else False,
            "cohort_storage_rows_written": None if attempted else 0,
            "environmental_provider_calls": 0,
            "scientific_evidence_writes": 0,
            "chronological_cohort_order_verified": False,
            "chronological_split_verified": False,
            "split_assignment_persisted": False,
            "dataset_split_assignment_persisted": False,
            "training_authorized": False,
            "numeric_output_authorized": False,
            "fixed_hr_shift_applied": False,
            "physiological_lag_ms": None,
        },
    )


class CohortRecordRoute(APIRoute):
    """Bound body and redact input errors before owner/provider dependencies."""

    def get_route_handler(self):
        original = super().get_route_handler()
        query_name = {
            "read_cohort_record": "include_record",
            "revalidate_cohort_record": "include_index",
        }.get(self.name)

        async def bounded(request: Request):
            allowed = {query_name} if query_name else set()
            if set(request.query_params) - allowed or (
                query_name and len(request.query_params.getlist(query_name)) > 1
            ):
                return _failure("COHORT_QUERY_INVALID", 422)
            if request.method == "POST" and (
                request.headers.get("content-type", "").split(";")[0].strip().lower()
                != "application/json"
            ):
                return _failure("COHORT_JSON_CONTENT_TYPE_REQUIRED", 415)
            raw = bytearray()
            async for chunk in request.stream():
                if len(raw) + len(chunk) > MAX_REQUEST_BYTES:
                    return _failure("COHORT_REQUEST_SIZE_LIMIT", 413)
                raw.extend(chunk)
            if request.method == "GET" and raw:
                return _failure("COHORT_READ_BODY_FORBIDDEN", 422)
            if request.method == "POST":
                try:
                    json.loads(
                        raw.decode("utf-8-sig"),
                        object_pairs_hook=_object,
                        parse_constant=_nonfinite,
                        parse_float=_finite_float,
                    )
                except (ValueError, UnicodeError, RecursionError):
                    return _failure("COHORT_JSON_INVALID", 400)
            delivered = False

            async def receive():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": bytes(raw), "more_body": False}
                return await request.receive()

            try:
                return await original(Request(request.scope, receive=receive))
            except RequestValidationError as exc:
                response = _failure("COHORT_REQUEST_INVALID", 422)
                payload = json.loads(response.body)
                fields = VALIDATION_FIELDS | {"path", "record_id", "include_record"}
                payload["errors"] = [
                    {
                        "loc": [
                            part if isinstance(part, int) or part in fields else "field"
                            for part in error["loc"]
                        ],
                        "type": error["type"],
                    }
                    for error in exc.errors()[:20]
                ]
                return JSONResponse(payload, status_code=422, headers=HEADERS)

        return bounded


router = APIRouter(
    prefix="/integrations/polar/response-cohorts",
    tags=["polar"],
    route_class=CohortRecordRoute,
    responses={
        400: {"description": "Malformed, duplicate or nonfinite JSON."},
        403: {"description": "Owner pin mismatch or missing Polar read scope."},
        404: {"description": "Configured owner, owned record or required source absent."},
        409: {"description": "Pinned source, archive integrity or revalidation conflict."},
        413: {"description": "Request or verification payload size limit."},
        415: {"description": "POST requires application/json."},
        422: {"description": "Strict body/query/path or member limit rejected."},
        502: {"description": "Current Polar source request failed or response malformed."},
        503: {"description": "Storage or internal verification dependency failed."},
        504: {"description": "Assembly or storage time limit."},
    },
)


class CohortRevalidationRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


async def _owner_id(db):
    # Existing configured local-demo owner, never a caller-supplied identity.
    return (
        await db.execute(select(User.id).where(User.email == get_settings().demo_user_email))
    ).scalar_one_or_none()


def _source_failure(value):
    upstream = value.get("upstream_reason")
    status = FAILURE_HTTP_STATUS.get(upstream, 503)
    return _failure(
        "COHORT_CURRENT_SOURCE_CHECK_FAILED",
        status,
        upstream=upstream,
        failed_member=value.get("failed_member_canonical_index"),
    )


def _stored_failure(error):
    code = str(error)
    if code not in STORAGE_HTTP_STATUS:
        code = "COHORT_STORAGE_DEPENDENCY_FAILURE"
    return _failure(code, STORAGE_HTTP_STATUS[code])


@router.post("/capture")
async def capture_cohort_record(
    manifest: ResponseCohortManifest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Fresh current-source capture; E/2 owns the archive transaction.

    Configured-owner demo API, not authentication of a remote caller. A local
    candidate/index and authority flags are not request inputs.
    """
    if len(manifest.members) > MAX_EXECUTION_MEMBERS:
        return _failure("COHORT_MEMBER_EXECUTION_LIMIT", 422)
    if db.in_transaction() or db.new or db.dirty or db.deleted:
        return _failure("COHORT_STORAGE_CLEAN_SESSION_REQUIRED", 422)
    started = False
    try:
        owner = await _owner_id(db)
        # End only this endpoint's owner lookup, before E/2's clean-session check.
        await db.rollback()
        if owner is None:
            return _failure("COHORT_CONFIGURED_OWNER_REQUIRED", 404)
        started = True
        receipt = await capture_response_cohort_record(db, manifest, user_id=owner)
        if receipt.get("status") not in {"CREATED", "ALREADY_PRESENT"}:
            code = next(iter(receipt.get("blocking_reasons", [])), None)
            if code == "COHORT_CURRENT_SOURCE_CHECK_FAILED":
                return _source_failure(receipt)
            if code not in STORAGE_HTTP_STATUS:
                code = "COHORT_STORAGE_DEPENDENCY_FAILURE"
            return _failure(
                code,
                STORAGE_HTTP_STATUS[code],
                attempted=receipt.get("storage_attempted") is True,
            )
        # The trusted E/2 service validates payload/columns and membership before
        # acknowledged commit. Publish its receipt, without another fallible read.
        return JSONResponse(receipt, headers=HEADERS)
    except DEPENDENCY_ERRORS:
        return _failure("COHORT_STORAGE_DEPENDENCY_FAILURE", 503, attempted=started)


@router.get("/records/{record_id}")
async def read_cohort_record(
    record_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    include_record: Literal["true", "false"] = "false",
):
    """Owned archive only; nested historical claims are never current source proof."""
    try:
        owner = await _owner_id(db)
        if owner is None:
            return _failure("COHORT_CONFIGURED_OWNER_REQUIRED", 404)
        record = await load_owned_response_cohort_record(db, record_id, user_id=owner)
        if record is None:
            return _failure("COHORT_RECORD_NOT_FOUND_OR_NOT_OWNED", 404)
        payload = record.pop("record_payload")
        return JSONResponse(
            {
                **record,
                "representation": "FULL_RECORD" if include_record == "true" else "SUMMARY",
                "record_hash_scope": "UNCHANGED_E1_RECORD_PAYLOAD_EXCLUDING_OWN_HASH",
                "record_payload": payload if include_record == "true" else None,
            },
            headers=HEADERS,
        )
    except TimeoutError:
        return _failure("COHORT_STORAGE_TIME_LIMIT", 504)
    except CohortStorageError as exc:
        return _stored_failure(exc)
    except DEPENDENCY_ERRORS:
        return _failure("COHORT_STORAGE_DEPENDENCY_FAILURE", 503)


@router.post("/records/{record_id}/revalidate")
async def revalidate_cohort_record(
    record_id: UUID,
    request: CohortRevalidationRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    include_index: Literal["true", "false"] = "false",
):
    """Reassemble the retained exact request; no archive/split/evidence writes."""
    try:
        owner = await _owner_id(db)
        if owner is None:
            return _failure("COHORT_CONFIGURED_OWNER_REQUIRED", 404)
        saved = await load_owned_response_cohort_record(db, record_id, user_id=owner)
        if saved is None:
            return _failure("COHORT_RECORD_NOT_FOUND_OR_NOT_OWNED", 404)
        payload = saved["record_payload"]
        manifest = ResponseCohortManifest.model_validate(payload["request_manifest"])
        index = await assemble_response_cohort(db, manifest, user_id=owner, verify_chronology=True)
        if index.get("source_evidence_verified") is not True:
            return _source_failure(
                {
                    "upstream_reason": next(iter(index.get("blocking_reasons", [])), None),
                    "failed_member_canonical_index": index.get("failed_member_canonical_index"),
                }
            )
        if not verify_cohort_index_integrity(index):
            return _failure("COHORT_API_INDEX_INTEGRITY_FAILED", 503)
        if index != payload["cohort_index"]:
            return _failure("COHORT_ARCHIVE_CURRENT_INDEX_CHANGED", 409)
        # Detect a deleted, corrupted or retargeted archive during source checks.
        checked = await load_owned_response_cohort_record(db, record_id, user_id=owner)
        if checked is None or checked["record_payload"] != payload:
            return _failure("COHORT_ARCHIVE_CHANGED_DURING_REVALIDATION", 409)
        return JSONResponse(
            {
                "status": "CURRENT_SOURCES_MATCH_ARCHIVED_COHORT_WITH_LIMITATIONS",
                "claim_scope": "REVALIDATION_TIME_ASSEMBLER_AND_OWNED_ARCHIVE_BINDING_ONLY",
                "source_verification_scope": "PER_MEMBER_DURING_REVALIDATION_NOT_SIMULTANEOUS",
                "record_id": checked["record_id"],
                "record_hash": checked["record_hash"],
                "cohort_index_hash": checked["cohort_index_hash"],
                "stored_member_count": checked["stored_member_count"],
                "source_evidence_verified": True,
                "current_source_evidence_verified": True,
                "current_index_matches_archived_record": True,
                "chronological_cohort_order_verified": index["chronological_cohort_order_verified"],
                "chronological_split_verified": index["chronological_split_verified"],
                "representation": "FULL_INDEX" if include_index == "true" else "SUMMARY",
                "summary": _summary(index),
                "cohort_index": index if include_index == "true" else None,
                "storage_writes": 0,
                "environmental_provider_calls": 0,
                "scientific_evidence_writes": 0,
                "dataset_split_assignment_persisted": False,
                "split_assignment_persisted": False,
                "training_authorized": False,
                "numeric_output_authorized": False,
                "fixed_hr_shift_applied": False,
                "physiological_lag_ms": None,
            },
            headers=HEADERS,
        )
    except TimeoutError:
        return _failure("COHORT_STORAGE_TIME_LIMIT", 504)
    except CohortStorageError as exc:
        return _stored_failure(exc)
    except DEPENDENCY_ERRORS:
        return _failure("COHORT_STORAGE_DEPENDENCY_FAILURE", 503)
