"""Bounded, read-only API over the actual V24.10-C cohort verifier."""

import json
from math import isfinite
from typing import Annotated, Literal

from cryptography.fernet import InvalidToken
from fastapi import APIRouter, Depends, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db
from app.models.entities import User
from app.schemas.response_cohort import ResponseCohortManifest
from app.services.response_cohort_assembly import (
    MAX_EXECUTION_MEMBERS,
    UPSTREAM_CODES,
    assemble_response_cohort,
    verify_cohort_index_integrity,
)

MAX_REQUEST_BYTES = 128 * 1024
FAILURE_HTTP_STATUS = {
    "COHORT_MEMBER_EXECUTION_LIMIT": 422,
    "COHORT_OWNER_MISMATCH": 403,
    "COHORT_POLAR_CONNECTION_REQUIRED": 404,
    "COHORT_POLAR_SCOPE_REQUIRED": 403,
    "COHORT_SNAPSHOT_NOT_FOUND_OR_NOT_OWNED": 404,
    "COHORT_SNAPSHOT_PIN_MISMATCH": 409,
    "COHORT_SNAPSHOT_VERSION_MISMATCH": 409,
    "COHORT_ENVIRONMENT_PIN_MISMATCH": 409,
    "COHORT_EXECUTION_TIME_LIMIT": 504,
    "COHORT_CURRENT_SOURCE_PAYLOAD_INVALID": 502,
    "COHORT_CURRENT_SOURCE_SESSION_MISSING": 404,
    "COHORT_CURRENT_SOURCE_SESSION_AMBIGUOUS": 409,
    "COHORT_CURRENT_SOURCE_SIZE_LIMIT": 413,
    "COHORT_SNAPSHOT_SIZE_LIMIT": 413,
    "COHORT_INDEX_SIZE_LIMIT": 413,
    "COHORT_DATASET_VERSION_MISMATCH": 409,
    "COHORT_DATASET_OWNER_OR_SESSION_MISMATCH": 409,
    "COHORT_DATASET_WITHHELD": 409,
    "COHORT_UNASSIGNED_BASE_REQUIRED": 409,
    "COHORT_REPLAY_PACKAGE_PIN_MISMATCH": 409,
    "COHORT_MEMBER_EVIDENCE_VERIFICATION_FAILED": 409,
    "COHORT_POLAR_SOURCE_REQUEST_FAILED": 502,
    "COHORT_DEPENDENCY_FAILURE": 503,
}
HEADERS = {"Cache-Control": "no-store"}
SUMMARY_KEYS = (
    "status",
    "schema_version",
    "assembly_version",
    "task",
    "claim_scope",
    "request_manifest_hash",
    "cohort_index_hash",
    "requested_member_count",
    "verified_member_count",
    "source_evidence_verified",
    "totals",
    "requested_split_counts",
    "chronological_cohort_order_verified",
    "chronological_split_verified",
    "chronology_claim_scope",
    "training_blocking_reasons",
    "policy",
    "execution_limits",
    "split_assignment_persisted",
    "independence_between_sessions_verified",
    "training_authorized",
    "numeric_output_authorized",
    "pre_exercise_prediction_authorized",
    "causal_prediction_authorized",
    "environmental_provider_calls",
    "science_storage_writes",
)
TEMPORAL_SUMMARY_KEYS = (
    "status",
    "claim_scope",
    "source_verification_performed",
    "supported_interval_count",
    "unsupported_member_canonical_indices",
    "compared_interval_pair_count",
    "ordered_member_canonical_indices",
    "missing_evaluation_partitions",
    "split_boundaries_utc",
    "chronology_blocking_reasons",
    "split_blocking_reasons",
    "duplicate_check_scope",
    "duplicate_check_complete_for_supported_members",
    "all_possible_duplicates_ruled_out",
)
VALIDATION_FIELDS = frozenset(
    {
        "body",
        "query",
        "include_index",
        "schema_version",
        "manifest_id",
        "task",
        "members",
        "provider",
        "athlete_id",
        "session_external_id",
        "route_date",
        "replay_snapshot_id",
        "expected_snapshot_hash",
        "expected_evidence_set_id",
        "expected_evidence_hash",
        "expected_unassigned_replay_package_hash",
        "expected_dataset_version",
        "expected_snapshot_schema_version",
        "split_manifest",
        "assignments",
        "split",
    }
)


def _failure(code, http_status, *, rejected=False, upstream=None, failed_member=None):
    """Never publish a successful prefix, source hash, or raw exception on failure."""
    return JSONResponse(
        status_code=http_status,
        headers=HEADERS,
        content={
            "status": "REJECTED" if rejected else "WITHHELD",
            "blocking_reasons": [code],
            "upstream_reason": upstream if upstream in UPSTREAM_CODES else None,
            "failed_member_canonical_index": failed_member,
            "claim_scope": "NO_COHORT_SOURCE_PROOF_ISSUED",
            "source_evidence_verified": False,
            "verified_member_count": 0,
            "cohort_index_hash": None,
            "cohort_index": None,
            "members": [],
            "totals": None,
            "temporal_audit": None,
            "chronological_cohort_order_verified": False,
            "chronological_split_verified": False,
            "split_assignment_persisted": False,
            "training_authorized": False,
            "numeric_output_authorized": False,
            "pre_exercise_prediction_authorized": False,
            "causal_prediction_authorized": False,
            "environmental_provider_calls": 0,
            "science_storage_writes": 0,
        },
    )


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate key")
        result[key] = value
    return result


def _nonfinite(value):
    raise ValueError("Non-finite number")


def _finite_float(value):
    number = float(value)
    if not isfinite(number):
        raise ValueError("Non-finite number")
    return number


class CohortRequestRoute(APIRoute):
    """Bound input before FastAPI parsing/dependencies; redact validation values."""

    def get_route_handler(self):
        original = super().get_route_handler()

        async def bounded(request: Request):
            if (
                set(request.query_params) - {"include_index"}
                or len(request.query_params.getlist("include_index")) > 1
            ):
                return _failure("COHORT_QUERY_INVALID", 422, rejected=True)
            if (
                request.headers.get("content-type", "").split(";")[0].strip().lower()
                != "application/json"
            ):
                return _failure("COHORT_JSON_CONTENT_TYPE_REQUIRED", 415, rejected=True)
            raw = bytearray()
            async for chunk in request.stream():
                if len(raw) + len(chunk) > MAX_REQUEST_BYTES:
                    return _failure("COHORT_REQUEST_SIZE_LIMIT", 413, rejected=True)
                raw.extend(chunk)
            try:
                json.loads(
                    raw.decode("utf-8-sig"),
                    object_pairs_hook=_object,
                    parse_constant=_nonfinite,
                    parse_float=_finite_float,
                )
            except (ValueError, UnicodeError, RecursionError):
                return _failure("COHORT_JSON_INVALID", 400, rejected=True)

            delivered = False

            async def receive():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": bytes(raw), "more_body": False}
                return await request.receive()

            try:
                # A new public Request replays the bounded body for normal Pydantic
                # validation and OpenAPI. No mutation of Starlette private caches.
                return await original(Request(request.scope, receive=receive))
            except RequestValidationError as exc:
                response = _failure("COHORT_REQUEST_INVALID", 422, rejected=True)
                payload = json.loads(response.body)
                payload["errors"] = [
                    {
                        "loc": [
                            part if isinstance(part, int) or part in VALIDATION_FIELDS else "field"
                            for part in error["loc"]
                        ],
                        "type": error["type"],
                    }
                    for error in exc.errors()[:20]
                ]
                return JSONResponse(payload, status_code=422, headers=HEADERS)

        return bounded


router = APIRouter(prefix="/integrations/polar", tags=["polar"], route_class=CohortRequestRoute)


def _summary(index):
    summary = {key: index[key] for key in SUMMARY_KEYS}
    audit = index["temporal_audit"]
    summary["temporal_audit"] = {key: audit[key] for key in TEMPORAL_SUMMARY_KEYS}
    summary["temporal_audit"].update(
        interval_conflict_count=len(audit["interval_conflicts"]),
        possible_duplicate_pair_count=len(audit["possible_duplicate_pairs"]),
    )
    return summary


@router.post(
    "/response-cohorts/assemble",
    responses={
        200: {
            "description": "All member sources verified; summary or unchanged full C index. Temporal limitations may remain."
        },
        400: {"description": "Invalid JSON or duplicate/non-finite input."},
        403: {"description": "Owner pin mismatch or missing Polar read scope."},
        404: {
            "description": "Required owner, connection, owned snapshot or current session absent."
        },
        409: {"description": "Pinned source/evidence conflict or ambiguous current session."},
        413: {"description": "Request or verification payload size limit."},
        415: {"description": "JSON content type required."},
        422: {"description": "Strict request/query contract or member execution limit rejected."},
        502: {"description": "Polar request failed or current source response malformed."},
        503: {"description": "Local dependency or internal index publication failure."},
        504: {"description": "Cohort assembly time limit."},
    },
)
async def assemble_cohort(
    manifest: ResponseCohortManifest,
    db: Annotated[AsyncSession, Depends(get_db)],
    include_index: Literal["true", "false"] = "false",
):
    """Verify pinned current sources and whole-session chronology; no scientific writes.

    Uses the existing configured demo user. It does not authenticate a remote
    caller as that user. Keep the current demo API deployment local.
    """
    if len(manifest.members) > MAX_EXECUTION_MEMBERS:
        return _failure("COHORT_MEMBER_EXECUTION_LIMIT", 422, rejected=True)
    try:
        user = (
            await db.execute(select(User).where(User.email == get_settings().demo_user_email))
        ).scalar_one_or_none()
        if user is None:
            return _failure("COHORT_CONFIGURED_OWNER_REQUIRED", 404)
        # The request's athlete_id is a checked pin, never an owner selector.
        index = await assemble_response_cohort(
            db, manifest, user_id=user.id, verify_chronology=True
        )
        if index["source_evidence_verified"] is not True:
            code = index["blocking_reasons"][0]
            if code not in FAILURE_HTTP_STATUS:
                return _failure("COHORT_API_DEPENDENCY_FAILURE", 503)
            position = index.get("failed_member_canonical_index")
            return _failure(
                code,
                FAILURE_HTTP_STATUS[code],
                upstream=index.get("upstream_reason"),
                failed_member=position
                if type(position) is int and 0 <= position < MAX_EXECUTION_MEMBERS
                else None,
            )
        if not verify_cohort_index_integrity(index):
            return _failure("COHORT_API_INDEX_INTEGRITY_FAILED", 503)
        return JSONResponse(
            headers=HEADERS,
            content={
                "schema_version": "0.1",
                "representation": "FULL_INDEX" if include_index == "true" else "SUMMARY",
                "cohort_index_hash_scope": "COMPLETE_INDEX_EXCLUDING_OWN_HASH_NOT_API_SUMMARY",
                "summary": _summary(index),
                "cohort_index": index if include_index == "true" else None,
            },
        )
    except (
        SQLAlchemyError,
        InvalidToken,
        RuntimeError,
        OSError,
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
    ):
        return _failure("COHORT_API_DEPENDENCY_FAILURE", 503)
