"""Source preservation, ambiguity, leakage, and source-bound feedback checks."""
import copy
from dataclasses import replace
from functools import lru_cache
import gzip
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from app.planning_contracts.phase_reconciliation_input import load_api, prepare_api, strict_loads
from phase_reconciliation_reference import evaluate
from app.planning_contracts.execution_adapter import build_execution_read
from app.planning_contracts.phase_reconciliation import Policy, ReconciliationError, digest, motion_runs, reconcile
from app.services.plan_execution_comparison_read import build_comparison_read, verify_comparison_read
from phase_reconciliation_test_workflow import offline_network_guard, run_saved_sources

P=Path(__file__).resolve().parent/"fixtures/phase_reconciliation"
PRIVATE_REPLAY_AVAILABLE = all((P/name).is_file() for name in (
    "api_00.json.gz", "api_01.json.gz", "api_02.json.gz",
    "additional_case_index.json", "flow_validation_only.json",
))
PRIVATE_REPLAY_REASON = 'private real-derived Polar replay fixtures are not installed; synthetic/public regression coverage still runs'


@lru_cache(maxsize=3)
def original(i):
    return load_api(P/f'api_{i:02}.json.gz')


@lru_cache(maxsize=3)
def prepared(i):
    return prepare_api(original(i))


def fixture(phases=None,n=180,speed=None,distance=None):
    phases=phases or [('DURATION',20,'MANUAL'),('DURATION',10,'AUTOMATIC'),('DURATION',40,'AUTOMATIC')]
    return {'schema_version':'0.1','input_kind':'SYNTHETIC_TEST_FIXTURE',
        'binding':{'session_id':'synthetic-session','athlete_id':'synthetic-owner',
                   'source_sha256':'1'*64,'plan_sha256':'2'*64},
        'scope':'PHASED','sport':'KAYAK','phase_blocking_reasons':[],
        'phases':[{'occurrence_id':f'occ:{i}','block_id':f'block:{i}',
                   'display_name':'Name is not a goal','advance':a,
                   'goal':{'type':t,'value':v}} for i,(t,v,a) in enumerate(phases)],
        'grid':{'slot_count':n,'speed_kmh':speed if speed is not None else [8.0]*n,
                'distance_m':distance if distance is not None else [i*2.0 for i in range(n)],
                'route_origin_candidate_s':None},
        'whole_session_observations':{'execution_role':'WHOLE_SESSION_SUMMARY','test_only':True}}


def answer(result,q,kind='DONT_KNOW',candidate=None):
    return {'schema_version':'0.1','artifact_id':result['artifact_id'],'answers':[{
        'question_id':q['question_id'],'answer_type':kind,'candidate_id':candidate,
        'submitted_at':'2026-10-17T09:36:11+02:00'}]}


def rebuild(api,mutator):
    old=api['source_execution_read'];source=copy.deepcopy(old['source_snapshot'])
    mutator(source)
    er=build_execution_read(source,captured_at=old['captured_at'],plan_read=old['plan_capture'],
                            plan_selection=old['plan_selection'],source_mode=old['source_mode'])
    return build_comparison_read(er,include_bundle=True,include_source=True)


def shape(result):
    return [[(p['phase_number'],p['start_window_s'],p['goal_completion_window_s'])
             for p in h['phase_windows']] for h in result['hypotheses']]


@unittest.skipUnless(PRIVATE_REPLAY_AVAILABLE, PRIVATE_REPLAY_REASON)
class RealSources(unittest.TestCase):
    def test_all_three_full_api_replays(self):
        for i in range(3):
            self.assertTrue(verify_comparison_read(original(i)))

    def test_all_24_phase_goals_survive_manual_projection(self):
        self.assertEqual([len(prepared(i)['phases']) for i in range(3)],[7,10,7])
        self.assertEqual(prepared(0)['phases'][2]['goal']['value'],300)
        self.assertEqual(prepared(1)['phases'][0]['goal']['value'],1500)

    def test_only_five_internal_manual_questions(self):
        self.assertEqual([reconcile(prepared(i))['question_count'] for i in range(3)],[2,1,2])

    def test_structural_repeat_does_not_add_manual_events(self):
        r=reconcile(prepared(1))
        self.assertEqual([q['after_phase_number'] for q in r['questions']],[1])

    def test_terminal_manual_recovery_does_not_request_third_restart(self):
        r=reconcile(prepared(2))
        self.assertEqual([q['after_phase_number'] for q in r['questions']],[1,4])

    def test_all_source_slots_and_source_json_retained(self):
        for i in range(3):
            api=original(i);before=digest(api);spec=prepared(i);r=reconcile(spec)
            self.assertEqual(digest(api),before)
            self.assertEqual(r['source_preservation']['retained_native_index_interval'],[0,spec['grid']['slot_count']])
            self.assertEqual(r['source_preservation']['discarded_sample_count'],0)

    def test_original_phase_audit_and_speed_results_unchanged(self):
        for i in range(3):
            api=original(i);before=digest(api['source_execution_read']['adapter_result'])
            reconcile(prepared(i))
            self.assertEqual(digest(api['source_execution_read']['adapter_result']),before)

    def test_missing_lap_fields_do_not_become_zero_events(self):
        r=reconcile(prepared(0))
        self.assertTrue(all(q['provider_phase_event_available'] is None for q in r['questions']))
        self.assertTrue(r['unlocalized_alternatives_retained'])

    def test_repeated_motion_keeps_multiple_options(self):
        q=reconcile(prepared(0))['questions'][0]
        self.assertGreaterEqual(sum(o['kind']=='LOW_SPEED_AND_MOVEMENT_CANDIDATE' for o in q['options']),2)

    def test_single_motion_option_does_not_authorize_boundary(self):
        r=reconcile(prepared(1))
        self.assertEqual(sum(o['kind']=='LOW_SPEED_AND_MOVEMENT_CANDIDATE' for o in r['questions'][0]['options']),1)
        self.assertEqual(r['pending_question_count'],1)
        self.assertFalse(r['actual_phase_alignment_verified'])

    def test_hr_outcome_change_does_not_move_candidate_windows(self):
        def change(source):
            for key in ('exerciseSamples','exercises'):
                for e in source['raw_data'].get(key,[]):
                    s=e.get('samples',{})
                    for v in s.get('samples',[]) if isinstance(s,dict) else s:
                        if v.get('type')=='HEART_RATE':
                            v['values']=[80.0+(j%100) for j in range(len(v['values']))]
        changed=rebuild(original(0),change)
        self.assertNotEqual(changed['source_content_sha256'],original(0)['source_content_sha256'])
        self.assertEqual(shape(reconcile(prepare_api(changed))),shape(reconcile(prepared(0))))

    def test_reference_read_does_not_change_results(self):
        reference=json.loads((P/'flow_validation_only.json').read_text(encoding='utf-8'))
        r=reconcile(prepared(0));before=digest(r)
        e=evaluate(r,reference)
        self.assertEqual(digest(r),before)
        self.assertFalse(e['used_for_inference'])
        self.assertFalse(e['new_independent_test'])

    def test_inference_cannot_open_reference_or_other_files(self):
        spec=copy.deepcopy(prepared(1))
        with patch('builtins.open',side_effect=AssertionError('file access forbidden during inference')), \
             patch.object(Path,'open',side_effect=AssertionError('path access forbidden during inference')):
            r=reconcile(spec)
        self.assertFalse(r['flow_reference_used_for_inference'])

    def test_reference_source_version_mismatch_withheld(self):
        reference=json.loads((P/'flow_validation_only.json').read_text(encoding='utf-8'))
        r=reconcile(prepared(0));r['binding']['source_sha256']='3'*64
        self.assertEqual(evaluate(r,reference)['status'],'NO_EXACT_SOURCE_BOUND_DEVELOPMENT_REFERENCE')

    def test_tampered_source_not_accepted(self):
        api=copy.deepcopy(original(0));api['source_execution_read']['source_snapshot']['raw_data']['distanceMeters']+=1
        with self.assertRaises(Exception):prepare_api(api)

    def test_tampered_plan_not_accepted(self):
        api=copy.deepcopy(original(0));api['source_execution_read']['plan_capture']['source_snapshot']['raw_data']['exercise'][0]['phaseOrRepeat'][0]['goal']['distance']+=10
        with self.assertRaises(Exception):prepare_api(api)

    def test_interior_pause_requires_clock_reconciliation(self):
        def change(source):
            e=source['raw_data']['exerciseSamples'][0]
            e['pauseTimes'].append({'startTime':'2026-07-25T13:10:00','endTime':'2026-07-25T13:10:30'})
        r=reconcile(prepare_api(rebuild(original(0),change)))
        self.assertEqual(r['status'],'PHASE_RECONCILIATION_WITHHELD_WHOLE_SOURCE_RETAINED')
        self.assertIn('INTERIOR_PAUSE_REQUIRES_TIMEBASE_RECONCILIATION',r['issues'])

    def test_irregular_route_not_silently_compressed(self):
        def change(source):
            source['raw_data']['exerciseSamples'][0]['routes']['route']['wayPoints'][300]['elapsedMillis']+=12000
        r=reconcile(prepare_api(rebuild(original(0),change)))
        self.assertIn('ROUTE_GRID_NOT_ONE_SECOND_REGULAR',r['issues'])
        self.assertEqual(r['source_preservation']['discarded_sample_count'],0)


class GenericCases(unittest.TestCase):
    def test_automatic_timers_do_not_shift_at_slowdown(self):
        speed=[8.0]*150;speed[25:40]=[0.0]*15
        r=reconcile(fixture([('DURATION',30,'AUTOMATIC'),('DURATION',60,'AUTOMATIC')],n=150,speed=speed))
        self.assertEqual([p['goal_completion_window_s'] for p in r['hypotheses'][0]['phase_windows']],[[30.0,30.0],[90.0,90.0]])
        self.assertEqual(r['question_count'],0)

    def test_distance_goal_uses_counter_not_name(self):
        a=fixture([('DISTANCE',60,'AUTOMATIC')],distance=[i*3 for i in range(180)])
        b=copy.deepcopy(a);b['phases'][0]['display_name']='Warm Up 900 km'
        self.assertEqual(shape(reconcile(a)),shape(reconcile(b)))
        self.assertEqual(reconcile(a)['hypotheses'][0]['phase_windows'][0]['goal_completion_window_s'],[20.0,20.0])

    def test_moving_manual_advance_is_kept_unlocalized(self):
        r=reconcile(fixture())
        self.assertEqual(r['question_count'],1)
        self.assertTrue(r['unlocalized_alternatives_retained'])
        self.assertFalse(r['actual_phase_alignment_verified'])

    def test_missing_speed_keeps_timer_and_question(self):
        s=fixture();s['grid']['speed_kmh']=None
        r=reconcile(s)
        self.assertEqual(r['question_count'],1)
        self.assertEqual(len(r['questions'][0]['options']),1)

    def test_missing_distance_withholds_only_goal_projection(self):
        s=fixture([('DURATION',10,'AUTOMATIC'),('DISTANCE',200,'AUTOMATIC')]);s['grid']['distance_m']=None
        r=reconcile(s)
        self.assertEqual(r['hypotheses'][0]['phase_windows'][0]['goal_completion_window_s'],[10.0,10.0])
        self.assertEqual(r['status'],'PARTIAL_NOMINAL_GOALS_WITH_UNRESOLVED_REMAINDER')

    def test_incomplete_recording_does_not_invent_completion(self):
        r=reconcile(fixture([('DURATION',300,'AUTOMATIC')],n=100))
        self.assertTrue(r['hypotheses'][0]['stopped'])
        self.assertEqual(r['source_preservation']['discarded_sample_count'],0)

    def test_early_target_does_not_cut_large_tail(self):
        r=reconcile(fixture([('DURATION',20,'AUTOMATIC')],n=180))
        self.assertEqual(r['source_preservation']['retained_native_index_interval'],[0,180])
        self.assertEqual(r['hypotheses'][0]['terminal_source_suffix_start_window_s'],[20.0,20.0])
        self.assertFalse(r['hypotheses'][0]['terminal_source_suffix_discarded'])

    def test_whole_session_target_is_not_fake_phase(self):
        s=fixture();s['scope']='WHOLE_SESSION_TARGET';s['phases']=[]
        s['whole_session_target']={'distance_m':50,'duration_s':None,'goal_does_not_define_recording_end':True}
        r=reconcile(s)
        self.assertEqual(r['status'],'WHOLE_SESSION_TARGET_PRESERVED')
        self.assertEqual(r['question_count'],0)
        self.assertEqual(r['hypotheses'],[])

    def test_reversed_distance_is_rejected(self):
        s=fixture();s['grid']['distance_m'][20]=-1
        with self.assertRaises(ReconciliationError):reconcile(s)

    def test_unsupported_goal_does_not_become_duration(self):
        s=fixture();s['phases'][0]['goal']['type']='CALORIES'
        with self.assertRaises(ReconciliationError):reconcile(s)

    def test_boolean_goal_is_not_numeric(self):
        s=fixture();s['phases'][0]['goal']['value']=True
        with self.assertRaises(ReconciliationError):reconcile(s)

    def test_duplicate_occurrence_rejected(self):
        s=fixture();s['phases'][1]['occurrence_id']=s['phases'][0]['occurrence_id']
        with self.assertRaises(ReconciliationError):reconcile(s)

    def test_search_limits_never_produce_unique_proof(self):
        speed=[8.0]*300
        for i in range(30,160,20):speed[i:i+5]=[0.0]*5
        r=reconcile(fixture(n=300,speed=speed),policy=replace(Policy(),max_paths=2,max_motion_options_per_event=1))
        self.assertTrue(r['search_limits_reached'])
        self.assertTrue(r['unlocalized_alternatives_retained'])
        self.assertFalse(r['actual_phase_alignment_verified'])

    def test_long_wait_outside_search_stays_unresolved(self):
        speed=[8.0]*500;speed[400:415]=[0.0]*15
        r=reconcile(fixture(n=500,speed=speed))
        self.assertTrue(r['unlocalized_alternatives_retained'])
        self.assertEqual(len(r['questions'][0]['options']),1)

    def test_policy_thresholds_validate(self):
        with self.assertRaises(ReconciliationError):reconcile(fixture(),policy=replace(Policy(),low_speed_kmh=10))

    def test_policy_change_invalidates_old_answers(self):
        s=fixture();r=reconcile(s);v=answer(r,r['questions'][0])
        with self.assertRaises(ReconciliationError):reconcile(s,policy=replace(Policy(),motion_margin_s=6),clarifications=v)

    def test_deterministic_repeat_result_and_question_ids(self):
        a=reconcile(fixture());b=reconcile(fixture())
        self.assertEqual(a,b)


@unittest.skipUnless(PRIVATE_REPLAY_AVAILABLE, PRIVATE_REPLAY_REASON)
class AdditionalRealCases(unittest.TestCase):
    def case(self,name):
        return load_api(P/'additional_cases'/f'{name}.json.gz')

    def test_additional_five_full_source_replays(self):
        for name in json.loads((P/'additional_case_index.json').read_text(encoding='utf-8')):
            self.assertTrue(verify_comparison_read(self.case(name)))

    def test_explicit_user_confirmed_plan_link_is_accepted(self):
        spec=prepare_api(self.case('user_confirmed_plan_link'))
        self.assertEqual(spec['source_plan_link_status'],'MANUAL_CONFIRMED')
        self.assertNotIn('PLAN_LINK_NOT_EXACT_OR_USER_CONFIRMED',spec['phase_blocking_reasons'])

    def test_unconfirmed_candidate_link_keeps_whole_source(self):
        value=rebuild(self.case('user_confirmed_plan_link'),
            lambda source:source.update(planned_workout_link_source='UNCONFIRMED'))
        spec=prepare_api(value)
        self.assertEqual(spec['source_plan_link_status'],'CANDIDATE')
        result=reconcile(spec)
        self.assertEqual(result['status'],'PHASE_RECONCILIATION_WITHHELD_WHOLE_SOURCE_RETAINED')
        self.assertEqual(result['source_preservation']['discarded_sample_count'],0)

    def test_real_whole_target_does_not_become_unassigned_phase(self):
        result=reconcile(prepare_api(self.case('whole_target')))
        self.assertEqual(result['status'],'WHOLE_SESSION_TARGET_PRESERVED')
        self.assertEqual(result['phase_inventory'],[])

    def test_real_partial_source_is_retained(self):
        result=reconcile(prepare_api(self.case('partial_source')))
        self.assertEqual(result['status'],'PARTIAL_NOMINAL_GOALS_WITH_UNRESOLVED_REMAINDER')
        self.assertEqual(result['source_preservation']['discarded_sample_count'],0)

    def test_real_irregular_clock_is_withheld_locally(self):
        result=reconcile(prepare_api(self.case('timebase_withheld')))
        self.assertEqual(result['status'],'PHASE_RECONCILIATION_WITHHELD_WHOLE_SOURCE_RETAINED')
        self.assertIn('ROUTE_GRID_NOT_ONE_SECOND_REGULAR',result['issues'])

    def test_real_automatic_source_has_no_manual_timing_question(self):
        result=reconcile(prepare_api(self.case('automatic_source')))
        self.assertEqual(result['status'],'NOMINAL_GOAL_CANDIDATES_WITH_LIMITATIONS')
        self.assertEqual(result['question_count'],0)


class Clarifications(unittest.TestCase):
    def test_unknown_acknowledges_without_false_resolution(self):
        s=fixture();r=reconcile(s)
        updated=reconcile(s,clarifications=answer(r,r['questions'][0]))
        self.assertEqual(updated['pending_question_count'],0)
        self.assertEqual(updated['questions'][0]['state'],'ACKNOWLEDGED_UNRESOLVED')
        self.assertFalse(updated['actual_phase_alignment_verified'])

    @unittest.skipUnless(PRIVATE_REPLAY_AVAILABLE, PRIVATE_REPLAY_REASON)
    def test_candidate_selection_is_user_evidence_only(self):
        s=copy.deepcopy(prepared(1));r=reconcile(s);q=r['questions'][0]
        v=answer(r,q,'SELECT_CANDIDATE',q['options'][-1]['candidate_id'])
        updated=reconcile(s,clarifications=v)
        self.assertEqual(len(updated['consistent_hypotheses_after_clarification']),1)
        self.assertFalse(updated['actual_phase_alignment_verified'])
        self.assertFalse(updated['numeric_prediction_authorized'])

    def test_wrong_source_or_owner_answers_rejected(self):
        s=fixture();r=reconcile(s);v=answer(r,r['questions'][0])
        s['binding']['athlete_id']='another-owner'
        with self.assertRaises(ReconciliationError):reconcile(s,clarifications=v)

    def test_changed_motion_input_invalidates_old_answers(self):
        s=fixture();r=reconcile(s);v=answer(r,r['questions'][0])
        s['grid']['speed_kmh'][30]=1.0
        with self.assertRaises(ReconciliationError):reconcile(s,clarifications=v)

    def test_wrong_candidate_rejected(self):
        s=fixture();r=reconcile(s);v=answer(r,r['questions'][0],'SELECT_CANDIDATE','other-candidate')
        with self.assertRaises(ReconciliationError):reconcile(s,clarifications=v)

    def test_exact_repeat_answer_is_idempotent(self):
        s=fixture();r=reconcile(s);v=answer(r,r['questions'][0]);v['answers']*=2
        updated=reconcile(s,clarifications=v)
        self.assertEqual(len(updated['retained_user_clarifications']),1)

    def test_conflicting_duplicate_answers_rejected(self):
        s=fixture();r=reconcile(s);v=answer(r,r['questions'][0])
        v['answers'].append({**v['answers'][0],'submitted_at':'2026-10-17T09:37:00+02:00'})
        with self.assertRaises(ReconciliationError):reconcile(s,clarifications=v)

    def test_timezone_required_for_answer_availability(self):
        s=fixture();r=reconcile(s);v=answer(r,r['questions'][0]);v['answers'][0]['submitted_at']='2026-10-17T09:36:11'
        with self.assertRaises(ReconciliationError):reconcile(s,clarifications=v)

    def test_jointly_inconsistent_answers_do_not_choose_fallback(self):
        speed=[8.0]*151;speed[10:15]=[0.0]*5;speed[80:85]=[0.0]*5
        s=fixture([('DURATION',5,'MANUAL'),('DISTANCE',100,'MANUAL'),('DURATION',10,'AUTOMATIC')],
                  n=151,speed=speed,distance=list(range(151)))
        r=reconcile(s);q1,q2=r['questions']
        late=max(q1['options'],key=lambda o:o['transition_window_s'][1])
        v=answer(r,q1,'SELECT_CANDIDATE',late['candidate_id'])
        v['answers'].extend(answer(r,q2,'SELECT_CANDIDATE',q2['options'][0]['candidate_id'])['answers'])
        updated=reconcile(s,clarifications=v)
        self.assertEqual(updated['status'],'CLARIFICATION_CONFLICT_WHOLE_SOURCE_RETAINED')
        self.assertEqual(updated['consistent_hypotheses_after_clarification'],[])
        self.assertEqual(updated['source_preservation']['discarded_sample_count'],0)


class Workflow(unittest.TestCase):
    def test_network_attempt_is_blocked(self):
        with offline_network_guard():
            with self.assertRaises(RuntimeError):socket.create_connection(('example.com',443))

    def test_duplicate_json_key_rejected(self):
        with self.assertRaises(ReconciliationError):strict_loads('{"x":1,"x":2}')

    def test_nonfinite_json_number_rejected(self):
        with self.assertRaises(ReconciliationError):strict_loads('{"x":NaN}')

    @unittest.skipUnless(PRIVATE_REPLAY_AVAILABLE, PRIVATE_REPLAY_REASON)
    def test_full_offline_round_trip_and_archive(self):
        with tempfile.TemporaryDirectory(prefix='phase reconciliation with spaces ') as tmp:
            out=Path(tmp)/'results'
            with offline_network_guard():
                s=run_saved_sources(sorted(P.glob('api_*.json.gz')),out,
                    reference_path=P/'flow_validation_only.json')
            self.assertEqual(s['phase_inventory_count'],24)
            self.assertEqual(s['manual_timing_question_count'],5)
            self.assertEqual(s['discarded_native_sample_count'],0)
            self.assertFalse(s['api_integrated'])
            for i in range(3):
                saved=json.loads(gzip.decompress((out/'sessions'/f'{i:03}'/'original_api_source.json.gz').read_bytes()))
                self.assertEqual(saved,original(i))
                self.assertTrue(verify_comparison_read(saved))
            with zipfile.ZipFile(out.with_suffix('.zip')) as z:
                self.assertIsNone(z.testzip())
                manifest=json.loads(z.read('OUTPUT_MANIFEST.json'))
                import hashlib
                for name,entry in manifest['files'].items():
                    self.assertEqual(hashlib.sha256(z.read(name)).hexdigest(),entry['sha256'])

    @unittest.skipUnless(PRIVATE_REPLAY_AVAILABLE, PRIVATE_REPLAY_REASON)
    def test_existing_output_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ReconciliationError):run_saved_sources([P/'api_00.json.gz'],Path(tmp))

    def test_failed_source_is_saved_as_withheld_without_exception_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'bad.json';source.write_text('{"secret":"not-an-api-response"}')
            s=run_saved_sources([source],Path(tmp)/'out')
            self.assertEqual(s['withheld_source_count'],1)
            self.assertNotIn('not-an-api-response',json.dumps(s))

    @unittest.skipUnless(PRIVATE_REPLAY_AVAILABLE, PRIVATE_REPLAY_REASON)
    def test_unused_answer_session_is_reported_not_silently_dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=run_saved_sources([P/'api_00.json.gz'],Path(tmp)/'out',
                                clarifications_by_session={'different-session':{}})
            self.assertEqual(s['unused_clarification_session_count'],1)
            self.assertNotEqual(s['status'],'API_PHASE_RECONCILIATION_OFFLINE_REPLAY_PASSED')


if __name__=='__main__':unittest.main(verbosity=2)
