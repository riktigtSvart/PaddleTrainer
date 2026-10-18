"""Owner-scoped, hash-bound reference catalog and read-only evidence view."""
from copy import deepcopy
import hashlib
from pathlib import Path

from starlette.concurrency import run_in_threadpool

from app.planning_contracts.phase_reconciliation import canonical, digest
from app.planning_contracts.phase_reconciliation_input import strict_loads
from app.planning_contracts.flow_phase_time_evidence import (
    RULES_VERSION, FlowEvidenceError, require, validate_reference, evaluate_reference,
)
from app.services import phase_clarification_storage as storage
from app.services.phase_reconciliation_read import read_owned_phase_reconciliation

CATALOG_VERSION = 'flow-display-catalog-0.1-20261017'
CATALOG_SHA256 = '490c1290835b4121c66db8fb4ec9da6c92a2a160ef72e8cb695dad949b24581c'
CATALOG_PATH = Path(__file__).resolve().parents[1]/'phase_evidence/flow_display_catalog_v01.json'
MAX_RESPONSE_BYTES = 12*1024*1024


def load_catalog():
    try:
        require(CATALOG_PATH.is_file() and not CATALOG_PATH.is_symlink(), 'FLOW_REFERENCE_CATALOG_NOT_REGULAR_FILE')
        require(CATALOG_PATH.stat().st_size <= 512*1024, 'FLOW_REFERENCE_CATALOG_SIZE_LIMIT')
        raw = CATALOG_PATH.read_bytes()
        require(hashlib.sha256(raw).hexdigest() == CATALOG_SHA256, 'FLOW_REFERENCE_CATALOG_HASH_DIFFERS')
        value = strict_loads(raw)
        require(set(value) == {'schema_version', 'catalog_version', 'assembled_at_utc', 'records'}
                and value['schema_version'] == '0.1' and value['catalog_version'] == CATALOG_VERSION,
                'FLOW_REFERENCE_CATALOG_FIELDS_DIFFER')
        require(isinstance(value['records'], list) and len(value['records']) <= 1000, 'FLOW_REFERENCE_CATALOG_RECORD_LIMIT')
        keys = set()
        for record in value['records']:
            validate_reference(record)
            key = (record['athlete_id'], record['session_id'])
            require(key not in keys, 'FLOW_REFERENCE_CATALOG_DUPLICATE_OWNER_SESSION')
            keys.add(key)
        return value
    except FlowEvidenceError as exc:
        raise FlowEvidenceError(exc.code, 503) from None
    except (OSError, ValueError, TypeError, KeyError):
        raise FlowEvidenceError('FLOW_REFERENCE_CATALOG_INVALID', 503) from None


def select_reference(owner, sid):
    catalog = load_catalog()
    matches = [r for r in catalog['records'] if r['athlete_id'] == str(owner) and r['session_id'] == str(sid)]
    require(len(matches) <= 1, 'FLOW_REFERENCE_CATALOG_DUPLICATE_OWNER_SESSION')
    return deepcopy(matches[0]) if matches else None


def capabilities():
    return {'status': 'FLOW_PHASE_TIME_EVIDENCE_CAPABILITIES', 'rules_version': RULES_VERSION,
        'catalog_version': CATALOG_VERSION, 'catalog_sha256': CATALOG_SHA256,
        'evidence_location': 'VERSIONED_APPLICATION_REFERENCE_CATALOG',
        'read_only': True, 'reference_source': 'USER_SUPPLIED_FLOW_PHASE_TABLE_TRANSCRIPTION',
        'source_and_plan_hash_match_required': True, 'user_answers_modified': False,
        'availability_unknown_reference_usable_pre_exercise': False,
        'database_writes': 0, 'provider_calls': 0, 'actual_phase_alignment_verified': False,
        'numeric_prediction_authorized': False, 'model_trained': False}


def archived_response(row):
    if row is None:
        return None
    return {'status': 'PHASE_CLARIFICATION_ARCHIVED_REVISION', 'storage_version': storage.STORAGE_VERSION,
        'revision': storage.revision_metadata(row), 'archived_reconciliation': storage.verify_revision(row),
        'archived_evidence_is_current_source': False, 'database_writes': 0,
        'provider_calls': 0, 'actual_phase_alignment_verified': False}


def build_evidence_read(state, archived, reference, *, include_source=False):
    require(type(include_source) is bool, 'FLOW_EVIDENCE_VIEW_FLAG_INVALID')
    storage.verify_saved_state(state, archived)
    result = evaluate_reference(state, reference)
    current = state['effective_reconciliation']
    value = {'status': result['status'], 'rules_version': RULES_VERSION, 'schema_version': '0.1',
        'catalog_version': CATALOG_VERSION, 'catalog_sha256': CATALOG_SHA256,
        'identity_scope': 'APPLICATION_CONFIGURED_EXISTING_OWNER', 'session_id': state['session_id'],
        'current_artifact_id': state['current_artifact_id'], 'latest_user_revision_id': state['latest_revision_id'],
        'source_comparison_capture_id': current['source_comparison_capture_id'],
        'source_execution_capture_id': current['source_comparison_read']['source_execution_capture_id'],
        'source_plan_capture_id': current['source_comparison_read']['source_execution_read']['plan_capture']['capture_id'],
        'source_capture_occurrence_mapping': deepcopy(current['source_capture_occurrence_mapping']),
        'source_sha256': current['source_content_sha256'], 'plan_sha256': current['plan_source_content_sha256'],
        'reference_evidence_id': reference['evidence_id'] if reference else None,
        'source_state_sha256': digest(state), 'reference_record_sha256': digest(reference) if reference else None,
        'source_state': deepcopy(state) if include_source else None,
        'source_user_revision_archive': deepcopy(archived) if include_source else None,
        'reference_record': deepcopy(reference) if include_source else None,
        'include_source': include_source, 'source_replay_material_included': include_source,
        'result': result, 'user_answers_modified': False, 'database_writes': 0, 'provider_calls': 0,
        'actual_phase_alignment_verified': False, 'training_authorized': False,
        'numeric_prediction_authorized': False, 'model_trained': False,
        'new_independent_model_test': False}
    if len(canonical(value)) > MAX_RESPONSE_BYTES:
        raise FlowEvidenceError('FLOW_EVIDENCE_RESPONSE_SIZE_LIMIT', 413)
    return value


def verify_evidence_read(value):
    require(value.get('source_state') is not None and value.get('include_source') is True,
            'FLOW_EVIDENCE_FULL_SOURCE_REQUIRED')
    expected = build_evidence_read(value['source_state'], value['source_user_revision_archive'],
                                   value['reference_record'], include_source=True)
    require(value == expected, 'FLOW_EVIDENCE_FULL_SOURCE_REPLAY_DIFFERS')
    return True


async def read_owned_evidence(db, row, owner, *, include_source=False):
    require(str(row.user_id) == str(owner), 'FLOW_EVIDENCE_SESSION_NOT_FOUND')
    latest = await storage.latest_revision(db, owner, row.id)
    current = await read_owned_phase_reconciliation(db, row, owner, include_source=True)
    state = await run_in_threadpool(storage.build_saved_state, current, latest, include_source=True)
    archived = await run_in_threadpool(archived_response, latest)
    reference = await run_in_threadpool(select_reference, owner, row.id)
    return await run_in_threadpool(build_evidence_read, state, archived, reference, include_source=include_source)
