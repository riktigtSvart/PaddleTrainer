"""API-only nominal goals, motion hypotheses, and source-bound clarifications.

No heart-rate outcome is used to choose boundaries. Hypotheses are explicitly
incomplete and never become provider events or model-authorized observations.
"""
from __future__ import annotations

from bisect import bisect_left
import copy
from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json
import math

RULES_VERSION = 'phase-reconciliation-0.1-draft2'
MAX_SLOTS = 20000
MAX_PHASES = 400


class ReconciliationError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise ReconciliationError(code)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def interval(a, b):
    return [round(float(a), 6), round(float(b), 6)]


@dataclass(frozen=True)
class Policy:
    low_speed_kmh: float = 2.0
    sustained_speed_kmh: float = 4.0
    minimum_low_samples: int = 3
    sustained_samples: int = 5
    resume_search_s: int = 60
    motion_margin_s: int = 5
    manual_search_horizon_s: int = 300
    max_motion_options_per_event: int = 8
    max_paths: int = 32

    def validate(self):
        require(number(self.low_speed_kmh) and number(self.sustained_speed_kmh)
                and 0 <= self.low_speed_kmh < self.sustained_speed_kmh <= 100,
                'MOTION_THRESHOLD_POLICY_INVALID')
        for key in ('minimum_low_samples', 'sustained_samples', 'resume_search_s',
                    'motion_margin_s', 'manual_search_horizon_s',
                    'max_motion_options_per_event', 'max_paths'):
            v = getattr(self, key)
            require(type(v) is int and 1 <= v <= 3600, 'POLICY_LIMIT_INVALID:' + key)
        require(self.max_paths <= 128 and self.max_motion_options_per_event <= 32,
                'POLICY_SEARCH_LIMIT_TOO_LARGE')


def motion_runs(speed, policy):
    """Low reported ground speed followed by sustained movement; no stop claim."""
    if speed is None:
        return []
    runs, i = [], 0
    while i < len(speed):
        if not number(speed[i]) or not 0 <= speed[i] <= policy.low_speed_kmh:
            i += 1
            continue
        end = i
        while end < len(speed) and number(speed[end]) and 0 <= speed[end] <= policy.low_speed_kmh:
            end += 1
        if end-i >= policy.minimum_low_samples:
            limit = min(len(speed)-policy.sustained_samples+1, end+policy.resume_search_s)
            resumed = next((r for r in range(end, limit)
                            if all(number(v) and v >= policy.sustained_speed_kmh
                                   for v in speed[r:r+policy.sustained_samples])), None)
            if resumed is not None:
                runs.append({'motion_id': f'low:{i}:{end}:resume:{resumed}',
                    'low_start_s': i, 'low_end_s': end, 'sustained_movement_start_s': resumed,
                    'interpretation': 'REPORTED_SPEED_PATTERN_NOT_VERIFIED_RECORDING_PAUSE'})
        i = end
    return runs


def _distance_at(t, distance):
    if t <= 0:
        return distance[0]
    i = min(len(distance)-1, int(math.floor(t)))
    if i+1 == len(distance):
        return distance[i]
    return distance[i] + (distance[i+1]-distance[i])*(t-i)


def _goal_end(start, goal, distance, last):
    if goal['type'] == 'DURATION':
        return start + goal['value']
    if goal['type'] != 'DISTANCE' or distance is None:
        return None
    threshold = _distance_at(start, distance) + goal['value']
    i = bisect_left(distance, threshold)
    if i >= len(distance):
        return last+1
    if i == 0:
        return 0.0
    before, after = distance[i-1], distance[i]
    return float(i) if after == before else i-1+(threshold-before)/(after-before)


def _validate_spec(spec):
    require(isinstance(spec, dict) and spec.get('schema_version') == '0.1', 'INPUT_SCHEMA_INVALID')
    binding = spec.get('binding')
    require(isinstance(binding, dict), 'SOURCE_BINDING_MISSING')
    for key in ('session_id','athlete_id','source_sha256','plan_sha256'):
        require(isinstance(binding.get(key), str) and binding[key], 'SOURCE_BINDING_INVALID:' + key)
    for key in ('source_sha256','plan_sha256'):
        require(len(binding[key]) == 64 and all(c in '0123456789abcdef' for c in binding[key]),
                'SOURCE_HASH_INVALID:' + key)
    phases = spec.get('phases')
    require(isinstance(phases, list) and len(phases) <= MAX_PHASES, 'PHASE_COUNT_INVALID')
    ids = []
    for p in phases:
        require(isinstance(p, dict) and isinstance(p.get('occurrence_id'), str), 'PHASE_ID_INVALID')
        require(p.get('advance') in ('AUTOMATIC','MANUAL'), 'ADVANCE_TYPE_UNSUPPORTED')
        goal = p.get('goal')
        require(isinstance(goal, dict) and goal.get('type') in ('DISTANCE','DURATION'), 'GOAL_TYPE_UNSUPPORTED')
        require(number(goal.get('value')) and goal['value'] > 0, 'STRUCTURED_GOAL_INVALID')
        ids.append(p['occurrence_id'])
    require(len(ids) == len(set(ids)), 'DUPLICATE_OCCURRENCE_ID')
    grid = spec.get('grid')
    require(isinstance(grid, dict), 'MOTION_GRID_MISSING')
    slots = grid.get('slot_count')
    require(type(slots) is int and 2 <= slots <= MAX_SLOTS, 'MOTION_GRID_SLOT_COUNT_INVALID')
    for name in ('speed_kmh','distance_m'):
        channel = grid.get(name)
        if channel is None:
            continue
        require(isinstance(channel, list) and len(channel) == slots, 'MOTION_CHANNEL_LENGTH_INVALID:' + name)
        if name == 'distance_m':
            require(all(number(v) and v >= 0 for v in channel)
                    and all(a <= b for a,b in zip(channel,channel[1:])), 'DISTANCE_COUNTER_INVALID')
    canonical(spec)


def _question_id(binding, occurrence, policy):
    return 'phase_question_' + digest({'binding': binding, 'occurrence_id': occurrence,
                                       'rules': RULES_VERSION, 'policy': asdict(policy)})


def _option(binding, phase, kind, window, policy, motion=None):
    identity = {'binding': binding, 'occurrence_id': phase['occurrence_id'],
                'rules': RULES_VERSION, 'policy': asdict(policy), 'kind': kind,
                'motion_id': motion['motion_id'] if motion else None}
    return {'candidate_id': 'phase_option_' + digest(identity), 'kind': kind,
            'transition_window_s': interval(*window), 'clock_domain': 'NATIVE_INDEX_CANDIDATE',
            'clock_alignment_verified': False, 'motion': copy.deepcopy(motion),
            'provider_event_verified': False}


def _answers(value, result):
    if value is None:
        return {}, []
    require(isinstance(value, dict) and set(value) == {'schema_version','artifact_id','answers'}
            and value['schema_version'] == '0.1' and value['artifact_id'] == result['artifact_id'],
            'CLARIFICATION_SOURCE_BINDING_MISMATCH')
    require(isinstance(value['answers'], list) and len(value['answers']) <= MAX_PHASES,
            'CLARIFICATION_LIST_INVALID')
    questions = {q['question_id']:q for q in result['questions']}
    selected, retained = {}, []
    for answer in value['answers']:
        require(isinstance(answer, dict) and set(answer) == {
            'question_id','answer_type','candidate_id','submitted_at'}, 'CLARIFICATION_FIELDS_INVALID')
        qid = answer['question_id']
        require(qid in questions, 'CLARIFICATION_QUESTION_NOT_IN_THIS_SOURCE')
        require(answer['answer_type'] in ('SELECT_CANDIDATE','DONT_KNOW'), 'CLARIFICATION_TYPE_INVALID')
        try:
            submitted = datetime.fromisoformat(answer['submitted_at'].replace('Z','+00:00'))
        except (TypeError, ValueError, AttributeError):
            raise ReconciliationError('CLARIFICATION_TIMESTAMP_INVALID') from None
        require(submitted.tzinfo is not None and submitted.utcoffset() is not None,
                'CLARIFICATION_TIMESTAMP_REQUIRES_OFFSET')
        candidate = answer['candidate_id']
        if answer['answer_type'] == 'SELECT_CANDIDATE':
            require(candidate in {v['candidate_id'] for v in questions[qid]['options']},
                    'CLARIFICATION_CANDIDATE_NOT_IN_QUESTION')
        else:
            require(candidate is None, 'DONT_KNOW_CANNOT_SELECT_CANDIDATE')
        if qid in selected:
            require(selected[qid] == answer, 'CONFLICTING_DUPLICATE_CLARIFICATION')
            continue
        selected[qid] = copy.deepcopy(answer)
        retained.append(copy.deepcopy(answer))
    return selected, retained


def _finish_without_paths(result, clarifications):
    _, retained = _answers(clarifications,result)
    result.update(retained_user_clarifications=retained,
                  consistent_hypotheses_after_clarification=[],
                  pending_question_count=0, question_count=0)
    result['result_sha256']=digest(result)
    return result


def normalized_decision_input(spec):
    """Exclude per-read capture IDs while binding all decision-driving values.

    The raw source hashes remain authoritative for the complete stored source.
    A new server capture of unchanged content must not invalidate an answer.
    """
    phase_keys=('occurrence_id','block_id','source_pointer','advance','goal')
    grid_keys=('slot_count','speed_kmh','distance_m','index_clock_assumption',
               'native_unit_policy','native_units_independently_verified',
               'route_origin_candidate_s','source_grid_issues')
    return {'binding':copy.deepcopy(spec['binding']), 'input_kind':spec.get('input_kind'),
        'sport':spec.get('sport'),'scope':spec.get('scope'),
        'source_plan_link_status':spec.get('source_plan_link_status'),
        'phase_blocking_reasons':copy.deepcopy(spec.get('phase_blocking_reasons',[])),
        'whole_session_target':copy.deepcopy(spec.get('whole_session_target')),
        'phases':[{k:copy.deepcopy(p.get(k)) for k in phase_keys} for p in spec['phases']],
        'grid':{k:copy.deepcopy(spec['grid'].get(k)) for k in grid_keys}}


def reconcile(spec, *, policy=None, clarifications=None):
    """Retain the whole source and expose incomplete, conditional interpretations."""
    _validate_spec(spec)
    policy = policy or Policy()
    policy.validate()
    binding, phases, grid = spec['binding'], spec['phases'], spec['grid']
    last = float(grid['slot_count']-1)
    context = {'binding': binding, 'rules_version': RULES_VERSION, 'policy': asdict(policy),
               'normalized_input_sha256':digest(normalized_decision_input(spec))}
    result = {'artifact_type': 'ApiPhaseReconciliation', 'schema_version': '0.1',
        'rules_version': RULES_VERSION, 'artifact_id': 'phase_reconciliation_'+digest(context),
        'binding': copy.deepcopy(binding), 'policy': asdict(policy),
        'normalized_input_sha256':context['normalized_input_sha256'],
        'input_kind': spec.get('input_kind','UNKNOWN'), 'status':'CANDIDATES_WITH_LIMITATIONS',
        'source_preservation': {'native_slot_count':grid['slot_count'],
            'retained_native_index_interval':[0,grid['slot_count']], 'discarded_sample_count':0,
            'whole_source_preserved_by_input_binding':True,
            'candidate_windows_are_not_a_partition_or_summable_observations':True},
        'whole_session_observations':copy.deepcopy(spec.get('whole_session_observations')),
        'phase_inventory':copy.deepcopy(phases), 'hypotheses':[], 'questions':[],
        'issues':[], 'search_limits_reached':False, 'unlocalized_alternatives_retained':False,
        'outcome_hr_used_for_boundaries':False, 'flow_reference_used_for_inference':False,
        'actual_phase_alignment_verified':False, 'numeric_prediction_authorized':False,
        'training_authorized':False, 'capability_update_performed':False,
        'source_or_database_writes':0, 'provider_requests':0,
        'speed_model_retrained':False, 'new_independent_model_test':False,
        'source_preserved_sport':spec.get('sport'), 'sport_reclassified':False,
        'source_route_origin_candidate_s':grid.get('route_origin_candidate_s'),
        'current_stored_plan_is_verified_historical_plan':False,
        'limitations':['NATIVE_ORIGIN_AND_CHANNEL_ALIGNMENT_UNVERIFIED',
            'NATIVE_UNITS_NOT_INDEPENDENTLY_VERIFIED',
            'NOMINAL_GOALS_DO_NOT_ESTABLISH_ACTUAL_PHASE_EVENTS',
            'MOTION_HEURISTIC_UNCALIBRATED_AND_NOT_EXHAUSTIVE',
            'NO_HR_OR_SPEED_MODEL_INFERENCE_OR_ADHERENCE_CLAIM']}
    if spec.get('phase_blocking_reasons'):
        result['status']='PHASE_RECONCILIATION_WITHHELD_WHOLE_SOURCE_RETAINED'
        result['issues']=list(spec['phase_blocking_reasons'])
        return _finish_without_paths(result,clarifications)
    if spec.get('scope') == 'WHOLE_SESSION_TARGET':
        result['status']='WHOLE_SESSION_TARGET_PRESERVED'
        result['whole_session_target']=copy.deepcopy(spec['whole_session_target'])
        return _finish_without_paths(result,clarifications)
    require(phases, 'PHASED_SOURCE_WITHOUT_LEAVES')
    distance, speed = grid.get('distance_m'), grid.get('speed_kmh')
    runs = motion_runs(speed, policy)
    result['motion_features']=runs
    paths=[{'phase_windows':[], 'manual_choices':[], 'next_start_range_s':[0.0,0.0], 'stopped':False}]
    for index, phase in enumerate(phases):
        next_paths=[]
        for path in paths:
            if path['stopped']:
                next_paths.append(path)
                continue
            lo,hi=path['next_start_range_s']
            ends=[_goal_end(t,phase['goal'],distance,last) for t in (lo,hi)]
            row={'occurrence_id':phase['occurrence_id'], 'phase_number':index+1,
                 'start_window_s':interval(lo,hi), 'goal':copy.deepcopy(phase['goal']),
                 'advance':phase['advance'], 'clock_domain':'NATIVE_INDEX_CANDIDATE',
                 'kind':'NOMINAL_GOAL_WINDOW_CANDIDATE', 'provider_event_verified':False}
            base=copy.deepcopy(path)
            if ends[0] is None or ends[1] is None:
                row.update(goal_completion_window_s=None,status='GOAL_CHANNEL_UNRESOLVED')
                base['phase_windows'].append(row);base['stopped']=True
                next_paths.append(base)
                continue
            elo,ehi=ends
            if ehi>last or lo>=last:
                row.update(goal_completion_window_s=interval(min(elo,last),last),
                           status='INCOMPLETE_OR_POSSIBLY_INCOMPLETE_OBSERVED_GOAL')
                base['phase_windows'].append(row);base['stopped']=True
                next_paths.append(base)
                continue
            row.update(goal_completion_window_s=interval(elo,ehi),status='NOMINAL_GOAL_CANDIDATE')
            base['phase_windows'].append(row)
            if phase['advance']=='AUTOMATIC' or index+1==len(phases):
                base['next_start_range_s']=interval(elo,ehi)
                if index+1==len(phases):
                    base['terminal_source_suffix_start_window_s']=interval(elo,ehi)
                    base['terminal_source_suffix_discarded']=False
                next_paths.append(base)
                continue
            result['unlocalized_alternatives_retained']=True
            qid=_question_id(binding,phase['occurrence_id'],policy)
            remaining_timers=sum(p['goal']['value'] for p in phases[index+1:]
                                 if p['goal']['type']=='DURATION')
            latest=last-remaining_timers
            if latest<elo:
                base['stopped']=True
                row['status']='REMAINING_NOMINAL_TIMERS_DO_NOT_FIT_OBSERVED_SOURCE'
                next_paths.append(base)
                continue
            options=[_option(binding,phase,'NO_ADDITIONAL_WAIT_CANDIDATE',(elo,min(ehi,latest)),policy)]
            motion_options=[]
            for run in runs:
                a=max(elo,run['low_start_s']-policy.motion_margin_s)
                b=min(latest,elo+policy.manual_search_horizon_s,
                      run['sustained_movement_start_s']+policy.motion_margin_s)
                if a>b or run['sustained_movement_start_s']<elo or a>elo+policy.manual_search_horizon_s:
                    continue
                motion_options.append(_option(binding,phase,'LOW_SPEED_AND_MOVEMENT_CANDIDATE',(a,b),policy,run))
            if len(motion_options)>policy.max_motion_options_per_event:
                result['search_limits_reached']=True
                result['issues'].append('MOTION_CANDIDATE_LIMIT_REACHED')
            options.extend(motion_options[:policy.max_motion_options_per_event])
            for option in options:
                branch=copy.deepcopy(base)
                branch['manual_choices'].append({'question_id':qid,'after_occurrence_id':phase['occurrence_id'],
                    'after_phase_number':index+1,**option,
                    'goal_completion_must_not_follow_manual_advance':True})
                branch['next_start_range_s']=option['transition_window_s']
                next_paths.append(branch)
        if len(next_paths)>policy.max_paths:
            result['search_limits_reached']=True
            result['issues'].append('HYPOTHESIS_PATH_LIMIT_REACHED')
        paths=next_paths[:policy.max_paths]
    questions={}
    for path in paths:
        for option in path['manual_choices']:
            qid=option['question_id']
            if qid not in questions:
                questions[qid]={'question_id':qid,'kind':'MANUAL_ADVANCE_TIMING',
                    'after_occurrence_id':option['after_occurrence_id'],
                    'after_phase_number':option['after_phase_number'],
                    'prompt_hu':f"Mikor indítottad a következő szakaszt a(z) {option['after_phase_number']}. szakasz céljának elérése után?",
                    'known_purpose_not_asked_again':True,'options':[],
                    'allowed_answer_types':['SELECT_CANDIDATE','DONT_KNOW'],
                    'unlocalized_option_hu':'Nem tudom / egyik jelölt időszak sem biztos',
                    'unanswered_behavior':'PRESERVE_SOURCE_AND_KEEP_BOUNDARIES_UNRESOLVED',
                    'state':'NEEDS_CLARIFICATION', 'provider_phase_event_available':None,
                    'provider_phase_event_availability_status':'NO_USABLE_EVENT_IN_CURRENT_ADAPTER',
                    'user_selection_is_provider_verified_event':False}
            q=questions[qid]
            existing=next((v for v in q['options'] if v['candidate_id']==option['candidate_id']),None)
            if existing:
                existing['transition_window_s']=interval(min(existing['transition_window_s'][0],option['transition_window_s'][0]),
                                                         max(existing['transition_window_s'][1],option['transition_window_s'][1]))
            else:
                q['options'].append({k:copy.deepcopy(option[k]) for k in (
                    'candidate_id','kind','transition_window_s','clock_domain','clock_alignment_verified','motion','provider_event_verified')})
    result['questions']=list(questions.values())
    for path in paths:
        path.pop('next_start_range_s',None)
        path['hypothesis_id']='phase_path_'+digest({'context':context,'path':path})
        path['scope']='INCOMPLETE_MOTION_HYPOTHESIS_NOT_ACTUAL_EXECUTION_PROOF'
    result['hypotheses']=paths
    if result['questions']:
        result['status']='API_PHASE_CANDIDATES_REQUIRE_CLARIFICATION'
    elif any(p['stopped'] for p in paths):
        result['status']='PARTIAL_NOMINAL_GOALS_WITH_UNRESOLVED_REMAINDER'
    else:
        result['status']='NOMINAL_GOAL_CANDIDATES_WITH_LIMITATIONS'
    selected,retained=_answers(clarifications,result)
    result['retained_user_clarifications']=retained
    allowed=paths
    for q in result['questions']:
        answer=selected.get(q['question_id'])
        if not answer:
            continue
        if answer['answer_type']=='DONT_KNOW':
            q['state']='ACKNOWLEDGED_UNRESOLVED'
        else:
            q['state']='USER_CONFIRMED_CANDIDATE_RANGE_NOT_PROVIDER_EVENT'
            q['selected_candidate_id']=answer['candidate_id']
            allowed=[p for p in allowed if any(v['question_id']==q['question_id']
                and v['candidate_id']==answer['candidate_id'] for v in p['manual_choices'])]
    result['consistent_hypotheses_after_clarification']=allowed
    if any(a['answer_type']=='SELECT_CANDIDATE' for a in retained) and not allowed:
        result['status']='CLARIFICATION_CONFLICT_WHOLE_SOURCE_RETAINED'
        result['issues'].append('NO_JOINT_HYPOTHESIS_FOR_SELECTED_ANSWERS')
    result['pending_question_count']=sum(q['state']=='NEEDS_CLARIFICATION' for q in result['questions'])
    result['question_count']=len(result['questions'])
    result['issues']=sorted(set(result['issues']))
    result['result_sha256']=digest(result)
    return result
