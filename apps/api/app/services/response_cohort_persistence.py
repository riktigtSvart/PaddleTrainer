"""Capture actual assembler output, atomically archive it, and verify owned readback.

Capture/delete own a clean session and their transactions. An uploaded local
candidate is never accepted. Source checks are per member during capture;
ordinary archived readback does not repeat them or claim current source truth.
"""

import asyncio
from copy import deepcopy
from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import delete, or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.models.entities import RouteEnvironmentEvidenceSet, User, WorkoutSession
from app.models.environment_replay_snapshot import EnvironmentReplaySnapshot
from app.models.response_cohort_record import ResponseCohortMember, ResponseCohortRecord
from app.schemas.response_cohort import ResponseCohortManifest
from app.services.response_cohort_assembly import UPSTREAM_CODES, assemble_response_cohort
from app.services.response_cohort_storage_contract import (
    build_cohort_record_payload,
    check_cohort_record_payload,
)

MAX_STORAGE_SECONDS = 30
ASSEMBLY_DIAGNOSTICS = UPSTREAM_CODES | frozenset(
    {
        "COHORT_MEMBER_EXECUTION_LIMIT",
        "COHORT_OWNER_MISMATCH",
        "COHORT_POLAR_CONNECTION_REQUIRED",
        "COHORT_POLAR_SCOPE_REQUIRED",
        "COHORT_SNAPSHOT_NOT_FOUND_OR_NOT_OWNED",
        "COHORT_SNAPSHOT_PIN_MISMATCH",
        "COHORT_SNAPSHOT_VERSION_MISMATCH",
        "COHORT_ENVIRONMENT_PIN_MISMATCH",
        "COHORT_EXECUTION_TIME_LIMIT",
        "COHORT_CURRENT_SOURCE_PAYLOAD_INVALID",
        "COHORT_CURRENT_SOURCE_SESSION_MISSING",
        "COHORT_CURRENT_SOURCE_SESSION_AMBIGUOUS",
        "COHORT_CURRENT_SOURCE_SIZE_LIMIT",
        "COHORT_SNAPSHOT_SIZE_LIMIT",
        "COHORT_INDEX_SIZE_LIMIT",
        "COHORT_DATASET_VERSION_MISMATCH",
        "COHORT_DATASET_OWNER_OR_SESSION_MISMATCH",
        "COHORT_DATASET_WITHHELD",
        "COHORT_UNASSIGNED_BASE_REQUIRED",
        "COHORT_REPLAY_PACKAGE_PIN_MISMATCH",
        "COHORT_MEMBER_EVIDENCE_VERIFICATION_FAILED",
        "COHORT_POLAR_SOURCE_REQUEST_FAILED",
        "COHORT_DEPENDENCY_FAILURE",
    }
)


class CohortStorageError(ValueError):
    """Fixed, non-secret diagnostic; raw database/provider exceptions never escape."""


def _require(condition, code):
    if not condition:
        raise CohortStorageError(code)


def _clean_session(db):
    # Do not commit or roll back unrelated caller work, including Core SQL writes.
    return not db.in_transaction() and not (db.new or db.dirty or db.deleted)


def _failure(code, *, rejected=False, attempted=False, upstream=None, failed_member=None):
    return {
        "status": "REJECTED" if rejected else "WITHHELD",
        "claim_scope": "NO_COHORT_CAPTURE_PROOF_ISSUED",
        "blocking_reasons": [code],
        "upstream_reason": upstream if upstream in ASSEMBLY_DIAGNOSTICS else None,
        "failed_member_canonical_index": failed_member,
        "record_id": None,
        "record_hash": None,
        "cohort_index_hash": None,
        "stored_member_count": 0,
        "round_trip_verified": False,
        "commit_acknowledged": False,
        "owner_authorization_verified": False,
        "source_evidence_verified": False,
        "current_source_evidence_verified": False,
        "storage_attempted": attempted,
        # A lost commit acknowledgement can be ambiguous; never invent zero writes.
        "storage_outcome": "NOT_CONFIRMED" if attempted else "NOT_ATTEMPTED",
        "database_record_persisted": None if attempted else False,
        "cohort_storage_rows_written": None if attempted else 0,
        "environmental_provider_calls": 0,
        "scientific_evidence_writes": 0,
        "split_assignment_persisted": False,
        "dataset_split_assignment_persisted": False,
        "training_authorized": False,
        "numeric_output_authorized": False,
        "fixed_hr_shift_applied": False,
        "physiological_lag_ms": None,
    }


async def _source_links(db, payload, *, lock=False):
    owner = UUID(payload["owner_id"])
    links = []
    for position, member in enumerate(payload["request_manifest"]["members"]):
        statement = (
            select(
                WorkoutSession.id.label("workout_id"),
                EnvironmentReplaySnapshot.id.label("replay_id"),
                EnvironmentReplaySnapshot.evidence_set_id.label("evidence_id"),
                EnvironmentReplaySnapshot.snapshot_hash,
                EnvironmentReplaySnapshot.snapshot_schema_version,
                RouteEnvironmentEvidenceSet.evidence_hash,
            )
            .select_from(WorkoutSession)
            .join(
                EnvironmentReplaySnapshot,
                EnvironmentReplaySnapshot.workout_session_id == WorkoutSession.id,
            )
            .join(
                RouteEnvironmentEvidenceSet,
                RouteEnvironmentEvidenceSet.id == EnvironmentReplaySnapshot.evidence_set_id,
            )
            .where(
                WorkoutSession.user_id == owner,
                WorkoutSession.external_provider == member["provider"],
                WorkoutSession.external_id == member["session_external_id"],
                EnvironmentReplaySnapshot.id == UUID(member["replay_snapshot_id"]),
                EnvironmentReplaySnapshot.user_id == owner,
                RouteEnvironmentEvidenceSet.user_id == owner,
                RouteEnvironmentEvidenceSet.workout_session_id == WorkoutSession.id,
                RouteEnvironmentEvidenceSet.provider == member["provider"],
                RouteEnvironmentEvidenceSet.session_external_id == member["session_external_id"],
            )
        )
        if lock:
            statement = statement.with_for_update()
        row = (await db.execute(statement)).one_or_none()
        _require(row is not None, "COHORT_STORAGE_SOURCE_LINK_CHANGED")
        _require(
            row.snapshot_hash == member["expected_snapshot_hash"]
            and row.snapshot_schema_version == member["expected_snapshot_schema_version"]
            and str(row.evidence_id) == member["expected_evidence_set_id"]
            and row.evidence_hash == member["expected_evidence_hash"],
            "COHORT_STORAGE_SOURCE_PIN_CHANGED",
        )
        links.append(
            {
                "canonical_index": position,
                "user_id": owner,
                "workout_session_id": row.workout_id,
                "replay_snapshot_id": row.replay_id,
                "evidence_set_id": row.evidence_id,
                "provider": member["provider"],
                "session_external_id": member["session_external_id"],
            }
        )
    return links


def _owned_record(owner):
    return (
        select(ResponseCohortRecord)
        .where(
            ResponseCohortRecord.user_id == owner,
        )
        .execution_options(populate_existing=True)
    )


async def _checked_record(db, row, *, expected_payload=None, expected_links=None):
    try:
        check_cohort_record_payload(row.record_json)
    except (ValueError, KeyError, TypeError, RecursionError):
        raise CohortStorageError("COHORT_STORED_PAYLOAD_INVALID") from None
    payload = row.record_json
    _require(
        str(row.user_id) == payload["owner_id"]
        and row.record_schema_version == payload["record_schema_version"]
        and row.task == payload["task"]
        and row.record_hash == payload["record_hash"]
        and row.request_manifest_hash == payload["request_manifest_hash"]
        and row.cohort_index_hash == payload["cohort_index_hash"]
        and type(row.member_count) is int
        and row.member_count == len(payload["request_manifest"]["members"])
        and isinstance(row.id, UUID)
        and isinstance(row.created_at, datetime),
        "COHORT_STORED_ROW_BINDING_INVALID",
    )
    if expected_payload is not None:
        _require(payload == expected_payload, "COHORT_STORED_ROUND_TRIP_FAILED")
    links = expected_links if expected_links is not None else await _source_links(db, payload)
    statement = (
        select(ResponseCohortMember)
        .where(ResponseCohortMember.record_id == row.id)
        .order_by(ResponseCohortMember.canonical_index)
        .execution_options(populate_existing=True)
    )
    if expected_payload is not None:
        statement = statement.with_for_update()
    stored = (await db.execute(statement)).scalars().all()
    _require(len(stored) == len(links), "COHORT_STORED_MEMBERSHIP_INVALID")
    for actual, expected in zip(stored, links):
        _require(
            all(getattr(actual, key) == value for key, value in expected.items()),
            "COHORT_STORED_MEMBERSHIP_INVALID",
        )
    stamp = row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=UTC)
    return {
        "record_id": str(row.id),
        "created_at": stamp.astimezone(UTC).isoformat(),
        "record_hash": row.record_hash,
        "record_schema_version": row.record_schema_version,
        "request_manifest_hash": row.request_manifest_hash,
        "cohort_index_hash": row.cohort_index_hash,
        "stored_member_count": row.member_count,
        "record_payload": deepcopy(payload),
    }


async def _store_transaction(db, payload, progress, *, duplicate_only=False):
    owner = UUID(payload["owner_id"])
    async with db.begin():
        # Serialize cooperating captures for this owner; canonical member lock order
        # plus database uniqueness also protects against non-cooperating writers.
        owned = (
            await db.execute(select(User.id).where(User.id == owner).with_for_update())
        ).scalar_one_or_none()
        _require(owned is not None, "COHORT_STORAGE_OWNER_MISSING")
        links = await _source_links(db, payload, lock=True)
        candidates = (
            (
                await db.execute(
                    _owned_record(owner)
                    .where(
                        or_(
                            ResponseCohortRecord.record_hash == payload["record_hash"],
                            ResponseCohortRecord.record_json["record_hash"].as_string()
                            == payload["record_hash"],
                        ),
                    )
                    .limit(2)
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )
        _require(len(candidates) <= 1, "COHORT_STORED_IDENTITY_AMBIGUOUS")
        row = candidates[0] if candidates else None
        status = "ALREADY_PRESENT"
        if row is None:
            _require(not duplicate_only, "COHORT_STORAGE_WRITE_CONFLICT")
            row = ResponseCohortRecord(
                id=uuid4(),
                user_id=owner,
                member_count=len(links),
                record_json=payload,
                **{
                    key: payload[key]
                    for key in (
                        "record_schema_version",
                        "task",
                        "request_manifest_hash",
                        "cohort_index_hash",
                        "record_hash",
                    )
                },
            )
            progress["attempted"] = True
            db.add(row)
            await db.flush()
            for link in links:
                db.add(ResponseCohortMember(record_id=row.id, **link))
            await db.flush()
            status = "CREATED"
        # Check actual serialized database readback and all links before committing.
        row = (
            await db.execute(
                _owned_record(owner).where(
                    ResponseCohortRecord.id == row.id,
                )
            )
        ).scalar_one_or_none()
        _require(row is not None, "COHORT_STORED_ROUND_TRIP_FAILED")
        saved = await _checked_record(db, row, expected_payload=payload, expected_links=links)
    saved.pop("record_payload")
    return {
        **saved,
        "status": status,
        "claim_scope": "CAPTURE_TIME_ASSEMBLER_CHECKS_AND_COMMITTED_RECORD_READBACK_ONLY",
        "source_verification_scope": "PER_MEMBER_DURING_CAPTURE_NOT_SIMULTANEOUS",
        "round_trip_verified": True,
        "commit_acknowledged": True,
        "owner_authorization_verified": True,
        "source_evidence_verified": True,
        "current_source_evidence_verified": True,
        "database_record_persisted": True,
        "storage_attempted": progress["attempted"],
        "storage_outcome": "COMMITTED_RECORD_VERIFIED",
        "cohort_storage_rows_written": 1 + len(links) if status == "CREATED" else 0,
        "split_request_archived": True,
        "requested_split_manifest_present": payload["request_manifest"]["split_manifest"]
        is not None,
        "dataset_split_assignment_persisted": False,
        "split_assignment_persisted": False,
        "environmental_provider_calls": 0,
        "scientific_evidence_writes": 0,
        "training_authorized": False,
        "numeric_output_authorized": False,
        "fixed_hr_shift_applied": False,
        "physiological_lag_ms": None,
    }


async def capture_response_cohort_record(db, manifest, *, user_id):
    """Trusted server-selected owner; strict request only; every repeat re-verifies sources.

    Use a fresh session with no active transaction/pending work. The assembler may
    refresh the existing Polar token. Its read transaction ends before the archive
    transaction, which rechecks and locks actual owned source links and pins.
    """
    if not _clean_session(db):
        return _failure("COHORT_STORAGE_CLEAN_SESSION_REQUIRED", rejected=True)
    progress = {"attempted": False}
    try:
        try:
            owner = UUID(str(user_id))
            request = ResponseCohortManifest.model_validate(
                manifest.model_dump(mode="json")
                if isinstance(manifest, ResponseCohortManifest)
                else manifest
            )
        except (ValueError, ValidationError, TypeError):
            return _failure("COHORT_STORAGE_REQUEST_INVALID", rejected=True)
        index = await assemble_response_cohort(db, request, user_id=owner, verify_chronology=True)
        if index.get("source_evidence_verified") is not True:
            position = index.get("failed_member_canonical_index")
            return _failure(
                "COHORT_CURRENT_SOURCE_CHECK_FAILED",
                upstream=next(iter(index.get("blocking_reasons", [])), None),
                failed_member=position if type(position) is int and 0 <= position < 20 else None,
            )
        try:
            payload = build_cohort_record_payload(request, index, owner_id=owner)
        except (ValueError, TypeError, KeyError, RecursionError):
            return _failure("COHORT_CAPTURE_PAYLOAD_INVALID")
        # All database reads and any completed token refresh belong to this service.
        await db.rollback()
        async with asyncio.timeout(MAX_STORAGE_SECONDS):
            try:
                return await _store_transaction(db, payload, progress)
            except IntegrityError:
                # The entire failed transaction was rolled back. A race may only
                # resolve to a complete, identical winner; never insert again here.
                return await _store_transaction(db, payload, progress, duplicate_only=True)
    except CohortStorageError as exc:
        return _failure(str(exc), attempted=progress["attempted"])
    except TimeoutError:
        return _failure("COHORT_STORAGE_TIME_LIMIT", attempted=progress["attempted"])
    except (
        SQLAlchemyError,
        RuntimeError,
        OSError,
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
    ):
        return _failure("COHORT_STORAGE_DEPENDENCY_FAILURE", attempted=progress["attempted"])
    finally:
        if db.in_transaction():
            try:
                await db.rollback()
            except SQLAlchemyError:
                raise CohortStorageError("COHORT_STORAGE_CLEANUP_FAILED") from None


async def load_owned_response_cohort_record(db, record_id, *, user_id):
    """Archived ownership/payload/link checks only; no assembler, Polar or writes."""
    owner, record_id = UUID(str(user_id)), UUID(str(record_id))
    async with asyncio.timeout(MAX_STORAGE_SECONDS):
        row = (
            await db.execute(_owned_record(owner).where(ResponseCohortRecord.id == record_id))
        ).scalar_one_or_none()
        if row is None:
            return None
        checked = await _checked_record(db, row)
    return {
        **checked,
        "status": "ARCHIVED_COHORT_RECORD_WITH_LIMITATIONS",
        "claim_scope": "OWNED_STORED_PAYLOAD_AND_COMPLETE_MEMBER_BINDING_ONLY",
        "payload_integrity_verified": True,
        "request_index_binding_verified": True,
        "member_links_verified": True,
        "owner_authorization_verified": True,
        "database_record_persisted": True,
        "source_evidence_verified": False,
        "current_source_evidence_verified": False,
        "chronological_cohort_order_verified": False,
        "chronological_split_verified": False,
        "dataset_split_assignment_persisted": False,
        "split_assignment_persisted": False,
        "environmental_provider_calls": 0,
        "storage_writes": 0,
        "training_authorized": False,
        "numeric_output_authorized": False,
    }


async def delete_owned_response_cohort_record(db, record_id, *, user_id):
    """Explicit server-authorized removal; cascades complete membership, retains sources.

    No automatic retirement or mutable replacement exists. This helper deliberately
    permits removal of an owned corrupt archive and does not require current sources.
    """
    _require(_clean_session(db), "COHORT_STORAGE_CLEAN_SESSION_REQUIRED")
    owner, record_id = UUID(str(user_id)), UUID(str(record_id))
    async with db.begin():
        row = (
            await db.execute(
                _owned_record(owner)
                .where(
                    ResponseCohortRecord.id == record_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        found = row is not None
        if found:
            await db.execute(
                delete(ResponseCohortRecord).where(
                    ResponseCohortRecord.id == record_id,
                    ResponseCohortRecord.user_id == owner,
                )
            )
    return {"status": "DELETED" if found else "NOT_FOUND", "database_record_deleted": found}
