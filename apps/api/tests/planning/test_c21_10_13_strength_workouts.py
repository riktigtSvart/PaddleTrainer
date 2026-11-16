"""Actual HTTP logs and independent strength doses, with immutable source proof."""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
from uuid import UUID
import pytest
from sqlalchemy.orm import Session
from app.models.entities import Sport, WorkoutSession, PlannedWorkout
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from app.services import strength_workout_log as log, training_strength_workout as work, session_feedback
from tests.planning.test_c21_10_9_profile_sources import env, configure, full, initial_context
from tests.planning.test_p2_4c20_1_prescriptions import completed
from tests.planning.test_p2_4c3_goal_workflow_api import ATHLETE, OTHER, count
from tests.planning.test_p2_4c18_4_training_plan import accept
from tests.planning.test_c21_10_7_calendar_cycles import get

ACTUAL = str(UUID(int=21113001))
PATH = f'/api/v1/planning/calendar/sessions/{ACTUAL}/strength-log'


def export(key, value):
    if os.getenv('C21_10_13_EXPORT'):
        path = Path(os.environ['C21_10_13_EXPORT'])
        data = json.loads(path.read_text()) if path.exists() else {}
        data[key] = value
        path.write_text(json.dumps(data), encoding='utf-8')


def prepare(e, patch):
    configure(e)
    patch.setattr(log, '_now', e.clock.tick)
    patch.setattr(session_feedback, '_now', e.clock.tick)
    completed(e, 21113001, Sport.STRENGTH, minutes=45, day='2026-10-23')
    original = initial_context(e)
    entries = deepcopy(original['data']['exercises'][:2])
    for i, entry in enumerate(entries):
        entry['id'] = str(UUID(int=21113100+i))
        entry['performed_on'] = '2026-10-23'
        entry['familiarity'], entry['comfort'], entry['side'] = 'regular', 'none', 'both'
        first = deepcopy(entry['sets'][0])
        entry['sets'] = [{**first, 'id': str(UUID(int=21113200+i*10+j)), 'repetitions': 10,
                          'hold_seconds': None, 'rir': '4', 'technique': 'stable', 'symptoms': 'none'} for j in range(4)]
    return {'request_id': str(UUID(int=21113300)), 'expected_revision': 0, 'purpose': 'training',
            'exercises': entries, 'note': 'Actual training · not an assessment', 'confirmed_actual': True}


def post(e, body, status=201, path=PATH):
    r = e.client.post(path, json=body)
    assert r.status_code == status, r.text
    assert r.headers['cache-control'] == 'no-store'
    return r.json()


def candidates(review):
    return [c for group in review['result']['alternatives'] for c in group['candidates'] if c['sport']=='STRENGTH' and c.get('strength_prescription',{}).get('schema_version') == work.SCHEMA]


def test_regular_default_is_separate_from_reference_and_times_are_computed(env):
    configure(env)
    before = deepcopy(initial_context(env)['saved'])
    r = full(env)
    values = candidates(r)
    assert values
    for c in values:
        d = c['strength_prescription']
        assert all(m['work_sets'] >= 2 for m in d['movements'])
        assert all('sets' not in m and m['reference']['set_id'] == m['reference_set']['id'] for m in d['movements'])
        assert d['work_seconds'] == work.work_seconds(d['movements'])
        assert sum(b['duration_sec'] for b in c['blocks']) == c['duration_sec']
        assert d['duration_sec'] <= d['desired_duration_sec'] <= 4500
        assert not d['load_increased'] and not d['one_rm_estimated']
    assert initial_context(env)['saved'] == before
    export('default_review', r)


def test_log_reloads_retries_and_revision_conflicts_without_provider_or_assessment_writes(env, monkeypatch):
    p = prepare(env, monkeypatch)
    before = deepcopy(initial_context(env)['saved'])
    with Session(env.engine) as db:
        raw = deepcopy(db.get(WorkoutSession, UUID(ACTUAL)).raw_data)
    a = post(env, p)
    assert post(env, p, 200) == {**a, 'reused': True}
    assert env.client.get(PATH).json()['current']['artifact'] == a['artifact']
    post(env, {**p, 'note': 'changed'}, 409)
    p2 = {**p, 'request_id': str(UUID(int=21113301)), 'expected_revision': 1, 'note': 'corrected'}
    b = post(env, p2)
    assert b['artifact']['previous_hash'] == a['artifact']['content_hash']
    post(env, {**p, 'request_id': str(UUID(int=21113302))}, 409)
    assert initial_context(env)['saved'] == before
    with Session(env.engine) as db:
        assert db.get(WorkoutSession, UUID(ACTUAL)).raw_data == raw
    export('log_context', env.client.get(PATH).json())


def test_owned_log_is_a_volume_source_with_source_bound_preview_and_calendar(env, monkeypatch):
    p = prepare(env, monkeypatch)
    a = post(env, p)
    r = full(env)
    assert len(r['inputs']['strength_workout_context']['logs']) == 1
    values = candidates(r)
    logged = [m for c in values for m in c['strength_prescription']['movements'] if m['reference']['kind']=='workout_log']
    assert logged and all(m['reference']['artifact_id'] == a['artifact']['artifact_id'] for m in logged)
    assert all(m['observed_work_sets'] == 4 and m['work_sets'] == 4 for m in logged if m['role']=='main')
    before = count(env, PlanningAuditArtifactRow), count(env, WorkoutSession), count(env, PlannedWorkout)
    repeated = full(env)
    assert repeated['artifact_id'] == r['artifact_id']
    assert before == (count(env, PlanningAuditArtifactRow), count(env, WorkoutSession), count(env, PlannedWorkout))
    accept(env, r, token=21113303)
    feed = get(env, path='feed')
    rows = [w for w in feed['planned'] if w['sport']=='STRENGTH']
    assert rows and all(w['planning_context']['instructions']['main']['strength']['schema_version']==work.SCHEMA for w in rows)
    export('logged_review', r)
    export('logged_feed', feed)


def test_assessment_purpose_and_not_yet_durable_feedback_are_not_volume_evidence(env, monkeypatch):
    p = prepare(env, monkeypatch)
    post(env, {**p, 'purpose': 'assessment'})
    assert full(env)['inputs']['strength_workout_context']['logs'] == []
    a = post(env, {**p, 'request_id': str(UUID(int=21113304)), 'expected_revision': 1})
    r = full(env)
    assert r['inputs']['strength_workout_context']['logs'][0]['log']['artifact'] == a['artifact']
    f = {'request_id': str(UUID(int=21113305)), 'timing': 'IMMEDIATE', 'expected_revision': 0,
         'observed_at': '2026-10-23T08:00:00+00:00', 'rpe': 9, 'fatigue': 8}
    post(env, f, path=PATH.replace('strength-log','feedback'))
    changed = full(env)
    assert changed['artifact_id'] != r['artifact_id']
    movements = [m for c in candidates(changed) for m in c['strength_prescription']['movements'] if m['reference']['kind']=='workout_log']
    assert movements and all(m['volume_basis']=='feedback_reduced' and m['work_sets']<=3 for m in movements)
    # Revisions are source time; no retrospective mutation of the first review.
    assert r['inputs']['strength_workout_context']['logs'][0]['feedback'] == []
    export('feedback_review', changed)


@pytest.mark.parametrize('change', ['empty','unconfirmed','wrong_day','unknown_exercise','other_owner','future'])
def test_invalid_logs_are_rejected_without_partial_commit(env, monkeypatch, change):
    p = prepare(env, monkeypatch)
    before = count(env, PlanningAuditArtifactRow)
    path, status = PATH, 422
    if change=='empty': p['exercises']=[]
    if change=='unconfirmed': p['confirmed_actual']=False
    if change=='wrong_day': p['exercises'][0]['performed_on']='2026-10-21';status=409
    if change=='unknown_exercise': p['exercises'][0]['exercise_id']='invented';status=409
    if change in {'other_owner','future'}:
        with Session(env.engine) as db:
            row=db.get(WorkoutSession,UUID(ACTUAL))
            if change=='other_owner':row.user_id=UUID(OTHER);status=404
            else:row.ended_at=datetime(2099,1,1,tzinfo=UTC);status=409
            db.commit()
    post(env,p,status,path)
    assert count(env,PlanningAuditArtifactRow)==before


def test_time_reduction_drops_accessories_first_and_never_shortens_rest(env):
    configure(env)
    r=full(env)
    c=candidates(r)[0]
    data=r['inputs'];context=data['strength_assessment']
    group=next(g for d in data['days'] if d['date']==c['date'] for g in d['opportunities'] if g['key']==c['opportunity_key'])
    selected,_=work.selected(context,data,'KAYAK',c['date'],group)
    assert len(selected)==2
    # A fixture-only additional own-reference movement, independent of load.
    accessory=deepcopy(selected[0]);accessory['entry']['exercise_id']='another_pull';accessory['role']='accessory'
    longer=work.make_dose(context,selected+[accessory],4500)
    shorter=work.make_dose(context,selected+[accessory],1200)
    assert shorter['shortened_for_time'] and shorter['omitted_accessory_ids']==['another_pull']
    assert len(shorter['movements'])==2 and all(m['rest_seconds']==120 for m in shorter['movements'])
    assert longer['duration_sec']>shorter['duration_sec'] and longer['movements'][-1]['work_sets']==2


def test_regular_start_is_three_sets_without_inventing_three_measurements(env):
    configure(env)
    r=full(env);data=deepcopy(r['inputs']);context=data['strength_assessment']
    context['receipt']['artifact']['proposal']['data']['experience']='regular'
    c=candidates(r)[0]
    group=next(g for d in data['days'] if d['date']==c['date'] for g in d['opportunities'] if g['key']==c['opportunity_key'])
    selected,_=work.selected(context,data,'KAYAK',c['date'],group)
    d=work.make_dose(context,selected,4500)
    assert [m['work_sets'] for m in d['movements']]==[3,3]
    assert d['duration_sec']==2100 and len({m['reference']['set_id'] for m in d['movements']})==2


def test_accessory_without_formal_assessment_uses_its_own_actual_log(env, monkeypatch):
    p=prepare(env,monkeypatch)
    # Dumbbells and floor are available; this exercise was never assessed.
    e=deepcopy(p['exercises'][1]);e.update(id=str(UUID(int=21113401)),exercise_id='db_overhead_press',pattern='push',machine_note='')
    e['sets']=[{**e['sets'][0],'id':str(UUID(int=21113402)),'load_kind':'external_kg','load_basis':'per_hand','load_value':'10.500000'}]
    p['exercises'].append(e);post(env,p)
    r=full(env)
    accessories=[m for c in candidates(r) for m in c['strength_prescription']['movements'] if m['role']=='accessory']
    assert accessories and any(m['reference']['kind']=='workout_log' for m in accessories)
    assert any(m['exercise_id']=='db_overhead_press' and m['target']['load_value']=='10.500000' for m in accessories)
    assert all(sum(x['work_sets'] for x in c['strength_prescription']['movements'] if x['pattern']==m['pattern'])<=7 for c in candidates(r) for m in c['strength_prescription']['movements'])
    export('accessory_review',r)


def test_mixed_weights_do_not_become_repeated_heaviest_work_sets(env, monkeypatch):
    p=prepare(env,monkeypatch)
    e=p['exercises'][0]
    for i,s in enumerate(e['sets']):
        s.update(load_kind='external_kg',load_basis='per_hand',load_value='70.000' if i<2 else '80.000',repetitions=12 if i==0 else 8)
    post(env,p);r=full(env)
    rows=[m for c in candidates(r) for m in c['strength_prescription']['movements'] if m['exercise_id']==e['exercise_id']]
    assert rows and all(m['observed_work_sets']==2 and m['target']['load_value']=='70.000' and m['target']['repetitions']==8 and m['work_sets']<=2 for m in rows)


def test_latest_pain_withholds_the_affected_exercise_instead_of_falling_back_to_older_good_sets(env,monkeypatch):
    p=prepare(env,monkeypatch);p['exercises'][0]['sets'][-1]['symptoms']='pain';post(env,p)
    r=full(env)
    assert all(m['exercise_id']!=p['exercises'][0]['exercise_id'] for c in candidates(r) for m in c['strength_prescription']['movements'])


def test_unilateral_pain_cannot_fall_back_to_a_bilateral_reference_or_introductory_plan(env,monkeypatch):
    from tests.planning.test_p2_4c20_5_assessed_strength import request
    from tests.planning.test_p2_4c20_4_initial_assessment import save as save_initial
    p=prepare(env,monkeypatch)
    intake=request(env,token=21113600)
    intake['data']['exercises']=intake['data']['exercises'][:2]
    save_initial(env,intake)
    painful=deepcopy(p)
    painful['exercises'][0]['side']='left'
    painful['exercises'][0]['sets'][-1]['symptoms']='pain'
    post(env,painful)
    reviewed=full(env)
    assert not any(c['sport']=='STRENGTH' for g in reviewed['result']['alternatives'] for c in g['candidates'])
    # A later explicit symptom-free actual report can be used without another
    # formal assessment; old pain remains preserved in the revision history.
    p.update(request_id=str(UUID(int=21113601)),expected_revision=1)
    post(env,p)
    assert candidates(full(env))
