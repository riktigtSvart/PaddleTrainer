"""Reference-supported execution times, with explicit clock alternatives."""
from copy import deepcopy
from datetime import datetime
import math

from app.schemas.flow_phase_time_evidence import FlowPhaseTimeReference
from app.planning_contracts.phase_reconciliation import canonical, digest
from app.planning_contracts.phase_reconciliation_input import prepare_api

RULES_VERSION = 'flow-phase-time-evidence-0.1'
REFERENCE_PREFIX = 'flow_display_reference_'


class FlowEvidenceError(ValueError):
    def __init__(self, code, status_code=409):
        super().__init__(code)
        self.code, self.status_code = code, status_code


def require(ok, code):
    if not ok:
        raise FlowEvidenceError(code)


def reference_id(value):
    return REFERENCE_PREFIX + digest({k: v for k, v in value.items() if k != 'evidence_id'})


def validate_reference(value):
    try:
        parsed = FlowPhaseTimeReference.model_validate(value).model_dump(mode='json')
        require(parsed == value, 'FLOW_REFERENCE_CANONICAL_FIELDS_DIFFER')
        require(value['evidence_id'] == reference_id(value), 'FLOW_REFERENCE_RECORD_HASH_DIFFERS')
        phases = value['phases']
        require([p['phase_number'] for p in phases] == list(range(1, len(phases)+1)), 'FLOW_REFERENCE_PHASE_SEQUENCE_INVALID')
        previous_end = 0
        for phase in phases:
            start = phase['cumulative_end_s']-phase['duration_s']
            require(start >= previous_end, 'FLOW_REFERENCE_PHASE_WINDOWS_OVERLAP')
            previous_end = phase['cumulative_end_s']
        reports = {r['report_number']: r for r in value['user_reports']}
        require(len(reports) == len(value['user_reports']), 'FLOW_REFERENCE_DUPLICATE_REPORT')
        for report in reports.values():
            at = datetime.fromisoformat(report['reported_at'].replace('Z', '+00:00'))
            require(at.tzinfo is not None and at.utcoffset() is not None, 'FLOW_REFERENCE_REPORT_TIME_OFFSET_REQUIRED')
        for event in value['reported_events']:
            require(event['report_number'] in reports and event['phase_number'] <= len(phases), 'FLOW_REFERENCE_REPORTED_EVENT_BINDING_INVALID')
        require(len(canonical(value)) <= 256*1024, 'FLOW_REFERENCE_SIZE_LIMIT')
        return value
    except FlowEvidenceError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError):
        raise FlowEvidenceError('FLOW_REFERENCE_SCHEMA_INVALID') from None


def _domains(spec, source):
    result = [{'name': 'NATIVE_INDEX_ZERO_ASSUMPTION', 'offset_s': 0.0}]
    exercise = source['raw_data']['exerciseSamples'][0]
    route = exercise.get('routes', {}).get('route', {})
    points = route.get('wayPoints')
    origin = spec['grid'].get('route_origin_candidate_s')
    if points and isinstance(origin, (int, float)) and not isinstance(origin, bool):
        elapsed = points[0].get('elapsedMillis')
        require(type(elapsed) is int and elapsed >= 0, 'FLOW_SOURCE_ROUTE_ORIGIN_INVALID')
        result += [
            {'name': 'ROUTE_FIRST_POINT_RELATIVE_PRECISE_ROUTE_START', 'offset_s': elapsed/1000},
            {'name': 'PREEXISTING_ROUTE_FIRST_POINT_RELATIVE_COARSE_EXERCISE_START', 'offset_s': origin},
        ]
    return result


def _native_views(start, end, domains, slots):
    out = []
    for domain in domains:
        offset = domain['offset_s']
        a, b = start-offset, end-offset
        out.append({'clock_assumption': domain['name'], 'offset_s': offset,
            'native_start_range_s': [a-1, a+1], 'native_end_range_s': [b-1, b+1],
            'nominal_observed_native_interval': [max(0, min(slots, math.ceil(a))), max(0, min(slots, math.ceil(b)))],
            'has_unobserved_prefix': a < 0, 'has_unobserved_suffix': b > slots,
            'clock_alignment_verified': False})
    return out


def _empty(state, status, reasons, reference=None):
    current = state.get('effective_reconciliation')
    pending = current['result']['pending_question_count'] if current else None
    return {'rules_version': RULES_VERSION, 'status': status, 'blocking_reasons': reasons,
        'reference_evidence_id': reference['evidence_id'] if reference else None,
        'current_user_question_count_pending': pending, 'reference_supported_pending_question_count': 0,
        'pending_questions_without_reference_support': pending, 'phase_times': [], 'transition_intervals': [],
        'manual_question_evidence': [], 'source_time_discrepancies': [], 'clock_assumptions': [],
        'preserved_source_suffix': None, 'reference_supported_joint_path_count': None,
        'user_answers_modified': False, 'source_samples_discarded': 0,
        'actual_phase_alignment_verified': False, 'numeric_prediction_authorized': False,
        'training_authorized': False, 'capability_update_performed': False,
        'source_available_at_utc': None, 'pre_exercise_use_authorized': False,
        'reference_counts_as_user_answer': False, 'new_independent_model_test': False}


def evaluate_reference(state, reference):
    """No mutation, no HR-based fitting, and no synthesized user answer."""
    if reference is None:
        return _empty(state, 'NO_REGISTERED_FLOW_REFERENCE', [])
    validate_reference(reference)
    current = state.get('effective_reconciliation')
    if current is None:
        return _empty(state, 'FLOW_REFERENCE_RECHECK_REQUIRED', ['CURRENT_SOURCE_WITHHELD'], reference)
    result = current['result']
    binding = result['binding']
    require(reference['athlete_id'] == binding['athlete_id'] and reference['session_id'] == binding['session_id'], 'FLOW_REFERENCE_OWNER_SESSION_DIFFERS')
    reasons = [reason for reason, expected, actual in (
        ('SOURCE_CONTENT_CHANGED', reference['source_sha256'], binding['source_sha256']),
        ('PLAN_CONTENT_CHANGED', reference['plan_sha256'], binding['plan_sha256']),
    ) if expected != actual]
    if reasons:
        return _empty(state, 'FLOW_REFERENCE_RECHECK_REQUIRED', reasons, reference)
    spec = prepare_api(current['source_comparison_read'])
    before = digest(current)
    if spec['phase_blocking_reasons'] or result['search_limits_reached']:
        return _empty(state, 'FLOW_REFERENCE_RECHECK_REQUIRED', spec['phase_blocking_reasons'] or ['CANDIDATE_SEARCH_LIMIT_REACHED'], reference)
    require(len(reference['phases']) == len(spec['phases']), 'FLOW_REFERENCE_PLAN_PHASE_COUNT_DIFFERS')
    source = current['source_comparison_read']['source_execution_read']['source_snapshot']
    domains = _domains(spec, source)
    require(len(domains) == 3, 'FLOW_REFERENCE_ROUTE_CLOCK_ALTERNATIVES_UNAVAILABLE')
    slots = spec['grid']['slot_count']
    out = _empty(state, 'FLOW_TIME_EVIDENCE_SUPPORTED_WITH_LIMITATIONS', [], reference)
    out['clock_assumptions'] = domains
    phases, gaps = [], []
    previous_end = 0
    for i, (display, plan) in enumerate(zip(reference['phases'], spec['phases'])):
        end = display['cumulative_end_s']; start = end-display['duration_s']
        if plan['goal']['type'] == 'DURATION':
            goal_duration = plan['goal']['value']
            compatible = (0 < display['duration_s'] <= goal_duration+1 if i == len(spec['phases'])-1
                          else abs(display['duration_s']-goal_duration) <= 1)
            require(compatible, 'FLOW_REFERENCE_STRUCTURED_DURATION_CONFLICT')
        difference = start-previous_end
        if i == 0:
            require(start == 0, 'FLOW_REFERENCE_FIRST_PHASE_START_NOT_ZERO')
        elif difference:
            kind = 'DISPLAY_PRECISION_OR_BOUNDARY_POLICY_UNRESOLVED'
            if difference > 1:
                require(spec['phases'][i-1]['advance'] == 'MANUAL', 'FLOW_REFERENCE_GAP_AFTER_AUTOMATIC_PHASE')
                kind = 'MANUAL_PHASE_WAIT_REFERENCE_SUPPORTED'
            gaps.append({'after_phase_number': i, 'before_phase_number': i+1,
                'kind': kind, 'reference_start_s': previous_end, 'reference_end_s': start,
                'nominal_duration_s': difference, 'native_views': _native_views(previous_end, start, domains, slots),
                'may_include_movement': True, 'whole_recording_pause_verified': False, 'discard_source_samples': False})
        phases.append({'phase_number': i+1, 'stable_source_occurrence_id': plan['occurrence_id'],
            'source_pointer': plan['source_pointer'], 'displayed_name': display['displayed_name'],
            'structured_goal': plan['goal'], 'reference_start_s': start, 'reference_end_s': end,
            'nominal_reference_duration_s': display['duration_s'],
            'start_derivation': 'DISPLAYED_CUMULATIVE_END_MINUS_DISPLAYED_PHASE_DURATION',
            'reference_clock_domain': 'FLOW_ELAPSED_DISPLAY', 'native_views': _native_views(start, end, domains, slots),
            'actual_boundary_verified': False})
        previous_end = end
    question_rows, supported_ids = [], {}
    conflicts = []
    answers = {x['question_id']: x for x in result['retained_user_clarifications']}
    for q in result['questions']:
        next_index = q['after_phase_number']
        require(next_index < len(phases), 'FLOW_QUESTION_HAS_NO_NEXT_PHASE')
        t = phases[next_index]['reference_start_s']
        matching = []
        for option in q['options']:
            lo, hi = option['transition_window_s']
            if all(lo <= t-d['offset_s']-1 <= t-d['offset_s']+1 <= hi for d in domains):
                matching.append(option)
        selected = matching[0] if len(matching) == 1 else None
        qid = q['question_id']
        conflict = bool(selected and qid in answers and answers[qid]['answer_type'] == 'SELECT_CANDIDATE'
                        and answers[qid]['candidate_id'] != selected['candidate_id'])
        if conflict:
            conflicts.append(qid)
        if selected and not conflict:
            supported_ids[qid] = selected['candidate_id']
        question_rows.append({'question_id': qid, 'after_phase_number': q['after_phase_number'],
            'current_question_state': q['state'], 'reference_start_s': t,
            'reference_supported_candidate_id': selected['candidate_id'] if selected else None,
            'candidate_window_s': selected['transition_window_s'] if selected else None,
            'status': 'SOURCE_USER_SELECTION_CONFLICT' if conflict else
                      'REFERENCE_SUPPORTED_CANDIDATE_RANGE' if selected else 'REFERENCE_NOT_LOCALIZED_TO_ONE_CANDIDATE',
            'user_answer_preserved': deepcopy(answers.get(qid)),
            'reference_is_user_confirmation': False, 'provider_event_verified': False})
    paths = [p for p in result['consistent_hypotheses_after_clarification'] if all(
        any(x['question_id'] == qid and x['candidate_id'] == cid for x in p['manual_choices'])
        for qid, cid in supported_ids.items())]
    if conflicts or (supported_ids and not paths):
        out['status'] = 'FLOW_TIME_EVIDENCE_CONFLICT_REQUIRES_REVIEW'
        out['blocking_reasons'] = ['SOURCE_USER_SELECTION_CONFLICT'] if conflicts else ['REFERENCE_JOINT_PATH_CONFLICT']
    pending = sum(q['state'] == 'NEEDS_CLARIFICATION' and q['question_id'] in supported_ids for q in result['questions'])
    discrepancies = []
    for event in reference['reported_events']:
        index = event['phase_number']-1
        require(index < len(phases), 'FLOW_REPORTED_EVENT_PHASE_OUT_OF_RANGE')
        t = phases[index]['reference_start_s']; difference = event['reported_time_s']-t
        if abs(difference) > 1:
            discrepancies.append({'status': 'UNRESOLVED_SOURCE_TIME_DIFFERENCE', 'phase_number': index+1,
                'event_role': event['event_role'], 'report_number': event['report_number'],
                'reported_time_s': event['reported_time_s'], 'reported_clock_domain': event['clock_domain'],
                'flow_derived_start_s': t, 'raw_display_difference_s': difference,
                'difference_is_verified_physical_delay': False, 'automatic_clock_or_gps_correction_applied': False})
    out.update(phase_times=phases, transition_intervals=gaps, manual_question_evidence=question_rows,
        reference_supported_pending_question_count=pending,
        pending_questions_without_reference_support=result['pending_question_count']-pending,
        reference_supported_joint_path_count=len(paths), source_time_discrepancies=discrepancies,
        preserved_source_suffix={'after_reference_elapsed_s': previous_end,
            'native_views': [{'clock_assumption': d['name'],
                'start_range_s': [previous_end-d['offset_s']-1, previous_end-d['offset_s']+1],
                'observed_suffix_start_index_candidate': max(0, min(slots, math.ceil(previous_end-d['offset_s']))),
                'observed_source_end_index_exclusive': slots} for d in domains], 'discard_source_samples': False})
    require(digest(current) == before, 'FLOW_EVIDENCE_MUTATED_CURRENT_RESULT')
    out['evidence_result_id'] = 'flow_time_result_' + digest({'rules': RULES_VERSION,
        'reference_id': reference['evidence_id'], 'artifact_id': state['current_artifact_id'],
        'latest_user_revision_id': state['latest_revision_id']})
    out['result_sha256'] = digest(out)
    return out
