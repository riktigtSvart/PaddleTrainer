"""Owner-bound answer revisions, immutable evidence, and source-aware reads."""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import gzip
import io
from uuid import uuid4
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, ProgrammingError, OperationalError
from starlette.concurrency import run_in_threadpool

from app.models.entities import WorkoutSession
from app.models.phase_clarification import PhaseClarificationRevision as Revision
from app.planning_contracts.phase_reconciliation import canonical, digest, RULES_VERSION
from app.planning_contracts.phase_reconciliation_input import strict_loads
from app.schemas.phase_clarification_storage import PhaseClarificationSaveRequest
from app.services.phase_reconciliation_read import (
    MAX_RESPONSE_BYTES, PhaseReconciliationReadError, build_phase_reconciliation_read,
    read_owned_phase_reconciliation, verify_phase_reconciliation_read,
)

STORAGE_VERSION = 'phase-clarification-storage-0.1'
MAX_EVIDENCE_BYTES = 12*1024*1024


class PhaseStorageError(ValueError):
    def __init__(self, code, status_code=409):
        super().__init__(code)
        self.code, self.status_code = code, status_code


def require(condition, code):
    if not condition:
        raise PhaseStorageError(code)


def utc(value):
    return (value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)).isoformat()


def storage_capabilities():
    return {'status': 'PHASE_CLARIFICATION_STORAGE_CAPABILITIES', 'storage_version': STORAGE_VERSION,
            'rules_version': RULES_VERSION, 'identity_scope': 'APPLICATION_CONFIGURED_EXISTING_OWNER',
            'answer_set_semantics': 'FULL_REPLACEMENT_WITH_APPEND_ONLY_REVISIONS',
            'concurrency': 'EXPECTED_LATEST_REVISION_AND_POSTGRES_SESSION_ROW_LOCK',
            'read_applies_only_latest_matching_revision': True, 'server_received_time_retained': True,
            'historical_answers_retroactively_available': False,
            'migration_revision': 'da7e4c92b610', 'schema_presence_checked_by_probe': False,
            'actual_phase_alignment_verified': False, 'numeric_prediction_authorized': False,
            'model_training_performed': False, 'provider_calls': 0}


def record_fields(row):
    return {'id': str(row.id), 'user_id': str(row.user_id), 'session_id': str(row.session_id),
            'sequence': row.sequence, 'previous_revision_id': str(row.previous_revision_id) if row.previous_revision_id else None,
            'artifact_id': row.artifact_id, 'rules_version': row.rules_version,
            'source_sha256': row.source_sha256, 'plan_sha256': row.plan_sha256,
            'motion_input_sha256': row.motion_input_sha256, 'request_sha256': row.request_sha256,
            'evidence_sha256': row.evidence_sha256, 'created_at': utc(row.created_at)}


def verify_revision(row):
    try:
        require(digest(record_fields(row)) == row.record_sha256, 'PHASE_STORAGE_RECORD_HASH_MISMATCH')
        require(digest(row.request_json) == row.request_sha256, 'PHASE_STORAGE_REQUEST_HASH_MISMATCH')
        request = PhaseClarificationSaveRequest.model_validate(row.request_json).model_dump(mode='json')
        require(request == row.request_json, 'PHASE_STORAGE_REQUEST_FIELDS_DIFFER')
        require(request['artifact_id'] == row.artifact_id, 'PHASE_STORAGE_ARTIFACT_BINDING_MISMATCH')
        require(request['expected_revision_id'] == (str(row.previous_revision_id) if row.previous_revision_id else None),
                'PHASE_STORAGE_PREVIOUS_REVISION_BINDING_MISMATCH')
        require((row.sequence == 1) == (row.previous_revision_id is None), 'PHASE_STORAGE_SEQUENCE_BINDING_MISMATCH')
        require(len(row.evidence_gzip) <= MAX_EVIDENCE_BYTES, 'PHASE_STORAGE_EVIDENCE_SIZE_LIMIT')
        with gzip.GzipFile(fileobj=io.BytesIO(row.evidence_gzip)) as stream:
            raw = stream.read(MAX_EVIDENCE_BYTES+1)
        require(len(raw) <= MAX_EVIDENCE_BYTES, 'PHASE_STORAGE_EVIDENCE_SIZE_LIMIT')
        evidence = strict_loads(raw)
        require(canonical(evidence) == raw and digest(evidence) == row.evidence_sha256,
                'PHASE_STORAGE_EVIDENCE_HASH_MISMATCH')
        require(evidence['session_id'] == str(row.session_id)
                and evidence['result']['binding']['athlete_id'] == str(row.user_id),
                'PHASE_STORAGE_OWNER_SESSION_BINDING_MISMATCH')
        require(evidence['stable_artifact_id'] == row.artifact_id
                and evidence['rules_version'] == row.rules_version
                and evidence['source_content_sha256'] == row.source_sha256
                and evidence['plan_source_content_sha256'] == row.plan_sha256
                and evidence['stable_normalized_motion_input_sha256'] == row.motion_input_sha256,
                'PHASE_STORAGE_SOURCE_BINDING_MISMATCH')
        inspection = {key: copy.deepcopy(request[key]) for key in ('schema_version', 'artifact_id', 'answers')}
        require(evidence['clarification_inspection_request'] == inspection, 'PHASE_STORAGE_ANSWER_EVIDENCE_MISMATCH')
        for key in ('actual_phase_alignment_verified', 'numeric_prediction_authorized', 'training_authorized'):
            require(evidence[key] is False, 'PHASE_STORAGE_AUTHORITY_CHANGED')
        # Future rules may still audit the original document and hashes. They
        # must never apply an older ruleset's answers to the new result.
        if row.rules_version == RULES_VERSION:
            verify_phase_reconciliation_read(evidence)
        return evidence
    except PhaseStorageError:
        raise
    except (ValueError, KeyError, TypeError, OSError, EOFError, OverflowError, RecursionError):
        raise PhaseStorageError('PHASE_STORAGE_STORED_EVIDENCE_INVALID') from None


def revision_metadata(row):
    verify_revision(row)
    return {**record_fields(row), 'revision_id': str(row.id), 'record_sha256': row.record_sha256,
            'answers': copy.deepcopy(row.request_json['answers']),
            'available_at_utc': utc(row.created_at),
            'availability_basis': 'SERVER_RECEIVED_TIME_NOT_CLIENT_SUBMITTED_TIME',
            'answer_authority': 'USER_REPORTED_NOT_PROVIDER_VERIFIED'}


async def latest_revision(db, owner, sid):
    with db.no_autoflush:
        return await db.scalar(select(Revision).where(Revision.user_id == owner, Revision.session_id == sid)
                               .order_by(Revision.sequence.desc()).limit(1))


def locked_session_statement(sid, owner):
    return select(WorkoutSession).where(WorkoutSession.id == sid, WorkoutSession.user_id == owner)\
        .with_for_update().execution_options(populate_existing=True)


def stale_reasons(row, current):
    return [reason for reason, expected, actual in (
        ('SOURCE_CONTENT_CHANGED', row.source_sha256, current['source_content_sha256']),
        ('PLAN_CONTENT_CHANGED', row.plan_sha256, current['plan_source_content_sha256']),
        ('RULES_CHANGED', row.rules_version, current['rules_version']),
        ('NORMALIZED_MOTION_INPUT_CHANGED', row.motion_input_sha256, current['stable_normalized_motion_input_sha256']),
        ('ARTIFACT_CHANGED', row.artifact_id, current['stable_artifact_id']),
    ) if expected != actual]


def build_saved_state(current, latest=None, *, include_source=False):
    metadata, reasons = None, []
    effective = current
    state = 'NO_SAVED_ANSWERS'
    if latest is not None:
        require(str(latest.session_id) == current['session_id']
                and str(latest.user_id) == current['result']['binding']['athlete_id'],
                'PHASE_STORAGE_CURRENT_OWNER_SESSION_DIFFERS')
        metadata = revision_metadata(latest)
        reasons = stale_reasons(latest, current)
        state = 'RECHECK_REQUIRED' if reasons else 'APPLIED'
        if not reasons:
            request = {key: copy.deepcopy(latest.request_json[key]) for key in ('schema_version', 'artifact_id', 'answers')}
            effective = build_phase_reconciliation_read(current['source_comparison_read'],
                                                        include_source=True, clarifications=request)
    effective = copy.deepcopy(effective)
    if not include_source:
        effective.update(include_source=False, source_comparison_read=None, source_replay_material_included=False)
    value = {'status': 'SAVED_PHASE_RECONCILIATION_STATE_WITH_LIMITATIONS',
             'storage_version': STORAGE_VERSION, 'session_id': current['session_id'],
             'current_artifact_id': current['stable_artifact_id'],
             'latest_revision_id': str(latest.id) if latest else None,
             'applied_revision_id': str(latest.id) if latest and not reasons else None,
             'saved_answers_status': state, 'recheck_reasons': reasons,
             'saved_revision': metadata, 'effective_reconciliation': effective,
             'saved_answers_used': state == 'APPLIED', 'database_writes': 0, 'provider_calls': 0,
             'actual_phase_alignment_verified': False, 'numeric_prediction_authorized': False,
             'speed_model_retrained': False, 'new_independent_model_test': False}
    require(len(canonical(value)) <= MAX_RESPONSE_BYTES, 'PHASE_STORAGE_RESPONSE_SIZE_LIMIT')
    return value


async def read_saved_state(db, row, owner, *, include_source=False):
    latest = await latest_revision(db, owner, row.id)
    try:
        current = await read_owned_phase_reconciliation(db, row, owner, include_source=True)
    except PhaseReconciliationReadError as exc:
        # Even if current source conversion is unavailable, preserve the audit
        # metadata and make it explicit that no stored answer was applied.
        metadata = await run_in_threadpool(revision_metadata, latest) if latest else None
        return {'status': 'SAVED_PHASE_RECONCILIATION_CURRENT_SOURCE_WITHHELD',
                'storage_version': STORAGE_VERSION, 'session_id': str(row.id),
                'latest_revision_id': str(latest.id) if latest else None, 'applied_revision_id': None,
                'saved_answers_status': 'RECHECK_REQUIRED' if latest else 'NO_SAVED_ANSWERS',
                'recheck_reasons': [exc.code], 'saved_revision': metadata,
                'effective_reconciliation': None, 'current_artifact_id': None,
                'saved_answers_used': False, 'database_writes': 0, 'provider_calls': 0,
                'actual_phase_alignment_verified': False, 'numeric_prediction_authorized': False,
                'speed_model_retrained': False, 'new_independent_model_test': False}
    return await run_in_threadpool(build_saved_state, current, latest, include_source=include_source)


def assert_clean_session(db):
    require(not any(bool(getattr(db, key, ())) for key in ('new', 'dirty', 'deleted')),
            'PHASE_STORAGE_UNRELATED_PENDING_CHANGES')


async def save_revision(db, sid, owner, request):
    assert_clean_session(db)
    with db.no_autoflush:
        # PostgreSQL serializes all answer writes for this session, including
        # distinct artifact versions. populate_existing avoids stale ORM data.
        row = await db.scalar(locked_session_statement(sid, owner))
    if row is None:
        raise PhaseStorageError('PHASE_STORAGE_SESSION_NOT_FOUND', 404)
    latest = await latest_revision(db, owner, sid)
    if latest is not None:
        await run_in_threadpool(verify_revision, latest)
    inspection = {key: copy.deepcopy(request[key]) for key in ('schema_version', 'artifact_id', 'answers')}
    evidence = await read_owned_phase_reconciliation(db, row, owner, include_source=True, clarifications=inspection)
    require(evidence['result']['status'] != 'CLARIFICATION_CONFLICT_WHOLE_SOURCE_RETAINED',
            'PHASE_STORAGE_CONFLICTING_CANDIDATE_SELECTIONS')
    request_sha = digest(request)
    with db.no_autoflush:
        existing = await db.scalar(select(Revision).where(Revision.user_id == owner, Revision.session_id == sid,
                                                        Revision.request_sha256 == request_sha))
    if existing is not None:
        metadata = await run_in_threadpool(revision_metadata, existing)
        # Release the SELECT FOR UPDATE lock even on an idempotent retry.
        await db.commit()
        return {'status': 'PHASE_CLARIFICATION_ALREADY_PRESENT', 'revision': metadata,
                'latest_revision_id': str(latest.id), 'returned_revision_is_latest': latest.id == existing.id,
                'database_writes': 0, 'provider_calls': 0, 'actual_phase_alignment_verified': False,
                'numeric_prediction_authorized': False}
    expected = str(latest.id) if latest else None
    require(request['expected_revision_id'] == expected, 'PHASE_STORAGE_REVISION_CONFLICT_RELOAD_STATE')
    require(request['answers'] or latest is not None, 'PHASE_STORAGE_INITIAL_EMPTY_ANSWER_SET_NOT_ALLOWED')
    now = datetime.now(timezone.utc)
    new = Revision(id=uuid4(), user_id=owner, session_id=sid,
                   sequence=latest.sequence+1 if latest else 1,
                   previous_revision_id=latest.id if latest else None,
                   artifact_id=evidence['stable_artifact_id'], rules_version=evidence['rules_version'],
                   source_sha256=evidence['source_content_sha256'], plan_sha256=evidence['plan_source_content_sha256'],
                   motion_input_sha256=evidence['stable_normalized_motion_input_sha256'],
                   request_sha256=request_sha, request_json=copy.deepcopy(request),
                   evidence_sha256=digest(evidence), evidence_gzip=gzip.compress(canonical(evidence), mtime=0),
                   created_at=now)
    new.record_sha256 = digest(record_fields(new))
    await run_in_threadpool(verify_revision, new)
    db.add(new)
    try:
        await db.flush()
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise PhaseStorageError('PHASE_STORAGE_CONCURRENT_WRITE_RELOAD_STATE') from None
    return {'status': 'PHASE_CLARIFICATION_REVISION_CREATED', 'revision': revision_metadata(new),
            'latest_revision_id': str(new.id), 'returned_revision_is_latest': True,
            'database_writes': 1, 'provider_calls': 0, 'actual_phase_alignment_verified': False,
            'numeric_prediction_authorized': False}


def archived_row_from_response(response):
    """Reconstruct all persisted bindings from a full audit response, offline."""
    try:
        meta = response['revision']
        evidence = response['archived_reconciliation']
        require(response['status'] == 'PHASE_CLARIFICATION_ARCHIVED_REVISION'
                and response['storage_version'] == STORAGE_VERSION
                and response['archived_evidence_is_current_source'] is False,
                'PHASE_STORAGE_ARCHIVE_RESPONSE_FIELDS_DIFFER')
        fields = {key: meta[key] for key in ('id','user_id','session_id','sequence','previous_revision_id',
            'artifact_id','rules_version','source_sha256','plan_sha256','motion_input_sha256',
            'request_sha256','evidence_sha256','record_sha256')}
        fields['created_at'] = datetime.fromisoformat(meta['created_at'])
        fields['request_json'] = {'schema_version':'0.1', 'artifact_id':meta['artifact_id'],
            'expected_revision_id':meta['previous_revision_id'], 'answers':copy.deepcopy(meta['answers'])}
        fields['evidence_gzip'] = gzip.compress(canonical(evidence), mtime=0)
        row = SimpleNamespace(**fields)
        require(revision_metadata(row) == meta, 'PHASE_STORAGE_ARCHIVE_METADATA_DIFFERS')
        require(response['database_writes'] == response['provider_calls'] == 0
                and response['actual_phase_alignment_verified'] is False,
                'PHASE_STORAGE_ARCHIVE_AUTHORITY_DIFFERS')
        return row
    except PhaseStorageError:
        raise
    except (ValueError, TypeError, KeyError):
        raise PhaseStorageError('PHASE_STORAGE_ARCHIVE_RESPONSE_INVALID') from None


def verify_saved_state(value, archived_response=None):
    require(value.get('effective_reconciliation') is not None, 'PHASE_STORAGE_FULL_CURRENT_SOURCE_REQUIRED')
    current = value['effective_reconciliation']
    verify_phase_reconciliation_read(current)
    baseline = build_phase_reconciliation_read(current['source_comparison_read'], include_source=True)
    row = archived_row_from_response(archived_response) if archived_response is not None else None
    require((row is None) == (value.get('latest_revision_id') is None), 'PHASE_STORAGE_ARCHIVE_REQUIRED_FOR_SAVED_STATE')
    expected = build_saved_state(baseline, row, include_source=True)
    require(expected == value, 'PHASE_STORAGE_STATE_FULL_REPLAY_DIFFERS')
    return True
