"""Validate a saved full API response before exposing motion-only inputs."""
from __future__ import annotations

import copy
import gzip
import json
from pathlib import Path

from app.planning_contracts.execution_adapter import _grid, _repeat_policy
from app.planning_contracts.legacy_plan_adapter import digest
from app.planning_contracts.phase_reconciliation import ReconciliationError, require, number
from app.services.plan_execution_comparison_read import verify_comparison_read

MAX_INPUT_BYTES = 12*1024*1024


def strict_loads(raw):
    def pairs(entries):
        result={}
        for k,v in entries:
            require(k not in result, 'DUPLICATE_JSON_KEY')
            result[k]=v
        return result
    def invalid(v):
        raise ReconciliationError('NONFINITE_JSON_NUMBER')
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=invalid)


def load_api(path):
    p=Path(path)
    require(p.is_file() and not p.is_symlink(), 'INPUT_FILE_NOT_REGULAR')
    require(p.stat().st_size<=MAX_INPUT_BYTES, 'INPUT_FILE_TOO_LARGE')
    if p.name.endswith('.gz'):
        with gzip.open(p,'rb') as stream:
            raw=stream.read(MAX_INPUT_BYTES+1)
    else:
        raw=p.read_bytes()
    require(len(raw)<=MAX_INPUT_BYTES,'DECOMPRESSED_INPUT_TOO_LARGE')
    value=strict_loads(raw)
    require(isinstance(value,dict),'API_INPUT_NOT_OBJECT')
    if 'response' in value:
        require(value.get('status')=='REPLAY_VERIFIED_CURRENT_API_CAPTURE', 'CAPTURE_STATUS_NOT_VERIFIED')
        value=value['response']
    return value


def pointer(value,path):
    for token in path.split('/')[1:]:
        token=token.replace('~1','/').replace('~0','~')
        value=value[int(token)] if isinstance(value,list) else value[token]
    return value


def source_goal(value):
    require(isinstance(value,dict),'STRUCTURED_GOAL_MISSING')
    kind=value.get('type')
    if kind=='DURATION':
        v=value.get('duration')
        require(number(v) and v>0,'STRUCTURED_DURATION_INVALID')
        return {'type':'DURATION','value':v/1000,'unit':'SECOND'}
    if kind=='DISTANCE':
        v=value.get('distance')
        require(number(v) and v>0,'STRUCTURED_DISTANCE_INVALID')
        return {'type':'DISTANCE','value':v,'unit':'METRE'}
    raise ReconciliationError('STRUCTURED_GOAL_TYPE_UNSUPPORTED')


def prepare_api(api):
    before=digest(api)
    verify_comparison_read(api)
    require(digest(api)==before,'INPUT_MODIFIED_DURING_REPLAY')
    er=api['source_execution_read']
    source,pc=er['source_snapshot'],er['plan_capture']
    require(pc is not None and pc['source_kind']=='STORED_POLAR_TARGET','OWNED_POLAR_PLAN_REQUIRED')
    require(source['external_provider']=='POLAR','POLAR_SOURCE_REQUIRED')
    require(source['user_id']==pc['source_snapshot']['user_id'],'CROSS_ATHLETE_SOURCE_REJECTED')
    link_status=er['adapter_result']['plan_link_audit']['status']
    plan=pc['source_snapshot']['raw_data']
    exercises=plan.get('exercise')
    require(isinstance(exercises,list) and len(exercises)==1,'SINGLE_TARGET_EXERCISE_REQUIRED')
    raw_goal=exercises[0]
    grid,audit=_grid(source['raw_data'])
    require(grid is not None,'NATIVE_GRID_UNAVAILABLE')
    blocking=[]
    if link_status not in ('EXACT_PROVIDER_ID','MANUAL_CONFIRMED'):
        blocking.append('PLAN_LINK_NOT_EXACT_OR_USER_CONFIRMED')
    if source['sport']!=pc['adapter_result']['plan']['sport']:
        blocking.append('PLAN_SESSION_SPORT_MISMATCH')
    blocked_containers,_=_repeat_policy(pc)
    if blocked_containers:
        blocking.append('REPEAT_CONTAINER_SEMANTICS_UNRESOLVED')
    phase_clock=audit.get('phase_timebase',{})
    for reason in phase_clock.get('blocking_reasons',[]):
        if reason in ('INTERIOR_PAUSE_REQUIRES_TIMEBASE_RECONCILIATION',
                      'ROUTE_GRID_NOT_ONE_SECOND_REGULAR','PAUSE_CLOCK_INVALID'):
            blocking.append(reason)
    expanded=pc['adapter_result']['expanded_occurrences']
    mapping={v['block_id']:v for v in pc['adapter_result']['block_mapping']}
    phases=[]
    scope='PHASED'
    whole_goal=None
    if raw_goal.get('type')=='VOLUME' and not raw_goal.get('phaseOrRepeat'):
        scope='WHOLE_SESSION_TARGET'
        whole_goal={'scope':'WHOLE_SESSION','distance_m':raw_goal.get('distance'),
                    'duration_s':raw_goal['duration']/1000 if number(raw_goal.get('duration')) else None,
                    'goal_does_not_define_recording_end':True,'source_goal':copy.deepcopy(raw_goal)}
    else:
        require(raw_goal.get('type')=='PHASED','TARGET_SCOPE_UNSUPPORTED')
        for phase_index, occurrence in enumerate(expanded):
            m=mapping.get(occurrence['block_id'])
            require(m is not None and m['source_type']=='PHASE','EXPANDED_LEAF_SOURCE_MAPPING_MISSING')
            leaf=pointer(plan,m['source_pointer'])
            require(not leaf.get('phaseOrRepeat'),'EXPANDED_LEAF_IS_CONTAINER')
            stable_occurrence='phase-source-occurrence_'+digest({
                'athlete_id':source['user_id'],'plan_source_sha256':pc['source_content_sha256'],
                'source_pointer':m['source_pointer'],'expanded_phase_index':phase_index})
            phases.append({'occurrence_id':stable_occurrence,
                'captured_contract_occurrence_id':occurrence['planned_occurrence_id'],
                'block_id':occurrence['block_id'],'source_pointer':m['source_pointer'],
                'display_name':leaf.get('name'), 'advance':leaf['changeType'],
                'goal':source_goal(leaf['goal']),
                'goal_authority':'STRUCTURED_PROVIDER_GOAL_NOT_DISPLAY_NAME'})
    spec={'schema_version':'0.1','input_kind':'PINNED_FULL_API_REPLAY',
        'binding':{'session_id':source['id'],'athlete_id':source['user_id'],
                   'source_sha256':er['source_content_sha256'],
                   'plan_sha256':pc['source_content_sha256']},
        'local_date':source['raw_data']['startTime'][:10],
        'sport':source['sport'],'scope':scope,'whole_session_target':whole_goal,
        'source_plan_link_status':link_status,
        'phases':phases,'phase_blocking_reasons':sorted(set(blocking)),
        'grid':{'slot_count':grid['slots'],'distance_m':copy.deepcopy(grid['channels'].get('DISTANCE')),
                'speed_kmh':copy.deepcopy(grid['channels'].get('SPEED')),
                'index_clock_assumption':'ONE_SECOND_NATIVE_INDEX_CANDIDATE',
                'native_unit_policy':audit['native_unit_policy'],
                'native_units_independently_verified':False,
                'route_origin_candidate_s':phase_clock.get('selected_native_origin_s'),
                'source_grid_issues':audit.get('issues',[])},
        'whole_session_observations':copy.deepcopy(er['adapter_result']['executed']['blocks'][0]),
        'original_api_capture_sha256':before,
        'original_api_phase_audit_sha256':digest(er['adapter_result']['phase_audit'])}
    require('HEART_RATE' not in spec['grid'],'HR_OUTCOME_MUST_NOT_ENTER_RECONCILIATION_GRID')
    require(digest(api)==before,'INPUT_MODIFIED_DURING_EXTRACTION')
    return spec
