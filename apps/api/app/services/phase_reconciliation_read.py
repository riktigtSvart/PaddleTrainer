"""Owner-scoped read and clarification inspection; no persistence or providers."""
from __future__ import annotations

import copy
from starlette.concurrency import run_in_threadpool

from app.planning_contracts.execution_adapter import canonical_bytes
from app.planning_contracts.legacy_plan_adapter import digest
from app.planning_contracts.phase_reconciliation import RULES_VERSION, ReconciliationError, reconcile
from app.planning_contracts.phase_reconciliation_input import prepare_api
from app.services.plan_execution_comparison_read import ComparisonReadError, read_owned_comparison

API_RULES_VERSION='phase-reconciliation-read-api-0.1'
MAX_RESPONSE_BYTES=12*1024*1024


class PhaseReconciliationReadError(ValueError):
    def __init__(self,code,status_code=409,*,upstream_reason=None):
        super().__init__(code)
        self.code,self.status_code,self.upstream_reason=code,status_code,upstream_reason


def capabilities():
    return {'status':'PHASE_RECONCILIATION_API_CAPABILITIES',
        'api_rules_version':API_RULES_VERSION,'rules_version':RULES_VERSION,'schema_version':'0.1',
        'identity_scope':'APPLICATION_CONFIGURED_EXISTING_OWNER',
        'source_mode':'CURRENT_OWNED_STORED_COMPARISON_FULL_REPLAY',
        'read_and_inspect_only':True,'clarifications_persisted':False,
        'stable_identity_basis':'SOURCE_CONTENT_PLAN_CONTENT_POLICY_AND_STABLE_SOURCE_LEAF_ORDINAL',
        'outcome_hr_used_for_boundaries':False,'source_samples_discarded':False,
        'actual_phase_alignment_verified':False,'numeric_prediction_authorized':False,
        'database_writes':0,'provider_calls':0,'speed_model_retrained':False,
        'state_model_trained':False,'new_independent_model_test':False}


def build_phase_reconciliation_read(comparison_read,*,include_source=False,clarifications=None):
    if type(include_source) is not bool:
        raise PhaseReconciliationReadError('PHASE_RECONCILIATION_INVALID_VIEW_FLAGS',422)
    try:
        spec=prepare_api(comparison_read)
        result=reconcile(spec,clarifications=clarifications)
    except ReconciliationError as exc:
        raise PhaseReconciliationReadError('PHASE_RECONCILIATION_'+str(exc)) from None
    except ComparisonReadError as exc:
        raise PhaseReconciliationReadError('PHASE_RECONCILIATION_SOURCE_REPLAY_WITHHELD',
            exc.status_code,upstream_reason=exc.code) from None
    except (KeyError,TypeError,ValueError,OverflowError,RecursionError):
        raise PhaseReconciliationReadError('PHASE_RECONCILIATION_SOURCE_CONVERSION_WITHHELD') from None
    inspection=clarifications is not None
    value={'status':'PHASE_RECONCILIATION_CLARIFICATION_INSPECTION_WITH_LIMITATIONS' if inspection
                    else 'PHASE_RECONCILIATION_READ_WITH_LIMITATIONS',
        'api_rules_version':API_RULES_VERSION,'rules_version':RULES_VERSION,'schema_version':'0.1',
        'identity_scope':'APPLICATION_CONFIGURED_EXISTING_OWNER',
        'session_id':spec['binding']['session_id'],'captured_at':comparison_read['captured_at'],
        'source_content_sha256':spec['binding']['source_sha256'],
        'plan_source_content_sha256':spec['binding']['plan_sha256'],
        'source_comparison_capture_id':comparison_read['capture_id'],
        'source_comparison_read_sha256':digest(comparison_read),
        'stable_artifact_id':result['artifact_id'],
        'stable_normalized_motion_input_sha256':result['normalized_input_sha256'],
        'source_capture_occurrence_mapping':[{'stable_source_occurrence_id':p['occurrence_id'],
            'captured_contract_occurrence_id':p['captured_contract_occurrence_id'],
            'source_pointer':p['source_pointer']} for p in spec['phases']],
        'result':result,'include_source':include_source,
        'source_comparison_read':copy.deepcopy(comparison_read) if include_source else None,
        'source_replay_material_included':include_source,
        'clarification_inspection_request':copy.deepcopy(clarifications),
        'clarifications_persisted':False,'user_answer_storage_writes':0,
        'actual_phase_alignment_verified':False,'historical_plan_content_verified':False,
        'numeric_prediction_authorized':False,'state_estimation_authorized':False,
        'training_authorized':False,'capability_update_performed':False,
        'database_writes':0,'provider_calls':0,'speed_model_retrained':False,
        'state_model_trained':False,'new_independent_model_test':False,
        'limitations':['CANDIDATE_WINDOWS_NOT_PROVIDER_PHASE_EVENTS',
            'NATIVE_ORIGIN_AND_CHANNEL_ALIGNMENT_UNVERIFIED','HISTORICAL_PLAN_CONTENT_UNVERIFIED',
            'USER_SELECTION_NOT_PROVIDER_VERIFICATION','INSPECTION_DOES_NOT_PERSIST_USER_ANSWERS',
            'NO_MODEL_OR_NEXT_WORKOUT_DECISION']}
    if len(canonical_bytes(value))>MAX_RESPONSE_BYTES:
        raise PhaseReconciliationReadError('PHASE_RECONCILIATION_RESPONSE_BYTE_LIMIT',413)
    return value


def verify_phase_reconciliation_read(value):
    if not isinstance(value,dict) or value.get('source_comparison_read') is None:
        raise PhaseReconciliationReadError('PHASE_RECONCILIATION_FULL_SOURCE_REQUIRED')
    repeated=build_phase_reconciliation_read(value['source_comparison_read'],
        include_source=value.get('include_source'),clarifications=value.get('clarification_inspection_request'))
    if value!=repeated:
        raise PhaseReconciliationReadError('PHASE_RECONCILIATION_FULL_SOURCE_REPLAY_DIFFERS')
    return True


async def read_owned_phase_reconciliation(db,row,owner_id,*,include_source=False,clarifications=None):
    if str(row.user_id)!=str(owner_id):
        raise PhaseReconciliationReadError('PHASE_RECONCILIATION_SESSION_NOT_FOUND',404)
    try:
        source=await read_owned_comparison(db,row,owner_id,include_bundle=True,include_source=True)
    except ComparisonReadError as exc:
        raise PhaseReconciliationReadError('PHASE_RECONCILIATION_UPSTREAM_WITHHELD',
            exc.status_code,upstream_reason=exc.code) from None
    return await run_in_threadpool(build_phase_reconciliation_read,source,
                                   include_source=include_source,clarifications=clarifications)
