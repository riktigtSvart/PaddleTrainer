"""First real occasion without measured history; atomic load and reference publication."""
from copy import deepcopy
from datetime import datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from app.api.routes import guided_strength as routes
from app.models.entities import PlannedWorkout, Sport, WorkoutSession
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from app.schemas.guided_strength import GuidedCommand
from app.services import guided_strength as service
from app.services import guided_strength_domain as domain
from tests.planning.test_p2_4c3_goal_workflow_api import OTHER_EMAIL, count
from tests.planning.test_p2_4c20_4_initial_assessment import context as initial_context
from tests.planning.test_p2_4c20_4_initial_assessment import save as save_initial
from tests.planning.test_p2_4c20_5_assessed_strength import planner as planner_fixture
from tests.planning.test_p2_4c20_5_assessed_strength import request as initial_request

BASE = '/api/v1/planning/guided-strength'


@pytest.fixture
def guided(tmp_path, monkeypatch):
    wrapper = planner_fixture.__wrapped__(tmp_path, monkeypatch)
    env = next(wrapper)
    env.app.include_router(routes.router, prefix='/api/v1')
    monkeypatch.setattr(service, '_now', env.clock.tick)
    p = initial_request(env)
    p['data'].update(experience='none', strength_frequency='none', last_strength_date=None)
    for e in p['data']['exercises']:
        e.update(sets=[], performed_on=None)
    env.initial = save_initial(env, p)
    try:
        yield env
    finally:
        wrapper.close()


def context(env):
    r = env.client.get(BASE)
    assert r.status_code == 200, r.text
    return r.json()


def start_request(c, token=206001, mode='manual'):
    ids = [e['id'] for e in c['intake']['data']['exercises'][:2]]
    return GuidedCommand.model_validate({'request_id': str(UUID(int=token)), 'action': 'start', 'previous_reference': None,
        'assessment_reference': c['intake']['reference'], 'source_hash': c['intake']['sources']['source_hash'],
        'location_id': c['intake']['data']['default_location_id'], 'selected_entry_ids': ids, 'recording_mode': mode,
        'precheck_confirmed': True, 'progress': domain.initial_progress(c['intake']['data'], ids)}).model_dump(mode='json')


def send(env, p, expected=201):
    r = env.client.post(BASE, json=p)
    assert r.status_code == expected, r.text
    assert r.headers['Cache-Control'] == 'no-store'
    return r.json()


def next_request(receipt, action='checkpoint', token=206002):
    value = deepcopy(receipt['artifact']['proposal'])
    value.update(request_id=str(UUID(int=token)), action=action, previous_reference=domain.reference(receipt['artifact']))
    return value


def measured(env, receipt, token=206002):
    p = next_request(receipt, 'finish', token)
    p['progress'].update(phase='review', warmup_completed=True)
    for i, row in enumerate(p['progress']['results']):
        row.update(state='recorded', side='both', observations=[{'id': str(UUID(int=206100+i)), 'purpose':'reference',
            'performed_on': env.initial['artifact']['proposal']['data']['assessment_date'],
            'repetitions':6, 'hold_seconds':None, 'load_kind':'external_kg' if i==0 else 'bodyweight',
            'load_value':'12.500000' if i==0 else None, 'load_basis':'per_hand' if i==0 else 'not_applicable',
            'load_note':'', 'rir':'3', 'technique':'stable', 'symptoms':'none'}])
    env.clock.current += timedelta(minutes=20)
    p.update(actual_start_at=receipt['artifact']['created_at'], actual_end_at=env.clock.current.isoformat(),
             no_other_recording_confirmed=True, reviewed=True)
    return p


def test_zero_references_can_start_without_creating_workouts(guided):
    c = context(guided)
    assert c['intake']['summary']['recorded_reference_count'] == 0
    assert c['preparation']['fresh_reference_required_to_start'] is False and not c['preparation']['issues']
    assert any(e['ready'] for p in c['preparation']['locations'] for e in p['entries'])
    before = count(guided, WorkoutSession), count(guided, PlannedWorkout)
    result = send(guided, start_request(c))
    assert result['artifact']['state'] == 'active' and result['assessment_receipt'] is None
    assert context(guided)['latest']['artifact'] == result['artifact']
    assert before == (count(guided, WorkoutSession), count(guided, PlannedWorkout))


def test_manual_finish_atomically_publishes_true_sets_once(guided):
    started = send(guided, start_request(context(guided)))
    proposal = measured(guided, started)
    before = count(guided, WorkoutSession), count(guided, PlannedWorkout)
    result = send(guided, proposal)
    assert result['artifact']['state'] == 'finished'
    assert result['assessment_receipt']['artifact']['summary']['recorded_reference_count'] == 2
    assert result['assessment_receipt']['artifact']['proposal']['data']['experience'] == 'none'
    assert result['assessment_receipt']['artifact']['proposal']['data']['exercises'][0]['sets'][0]['load_value'] == '12.500000'
    assert count(guided, WorkoutSession) == before[0]+1 and count(guided, PlannedWorkout) == before[1]
    with Session(guided.engine) as db:
        workout = db.get(WorkoutSession, UUID(result['artifact']['result']['workout_session_id']))
        assert workout.duration_sec == 1200 and workout.avg_hr is None
        assert workout.external_provider == 'PADDLETRAINER_GUIDED'
    retried = send(guided, proposal, 200)
    assert retried['artifact'] == result['artifact'] and retried['reused']
    assert count(guided, WorkoutSession) == before[0]+1
    assert all(not s.in_transaction() for s in guided.requests)


def test_checkpoint_survives_reload_and_rejects_stale_revision(guided):
    started = send(guided, start_request(context(guided)))
    p = next_request(started)
    p['progress'].update(warmup_completed=True, phase='movements')
    saved = send(guided, p)
    assert context(guided)['latest']['artifact'] == saved['artifact']
    p['request_id'] = str(UUID(int=206003))
    assert send(guided, p, 409)['detail']['code'] == 'GUIDED_REVISION_CONFLICT'
    assert send(guided, start_request(context(guided), 206004), 409)['detail']['code'] == 'GUIDED_ACTIVE_EXISTS'


def test_failed_commit_rolls_back_all_related_writes(guided, monkeypatch):
    started = send(guided, start_request(context(guided)))
    p = measured(guided, started)
    before = count(guided, WorkoutSession), count(guided, PlanningAuditArtifactRow)
    commit = service.transactions.commit
    async def fail(_session):
        raise RuntimeError('simulated disk failure')
    monkeypatch.setattr(service.transactions, 'commit', fail)
    send(guided, p, 503)
    assert before == (count(guided, WorkoutSession), count(guided, PlanningAuditArtifactRow))
    monkeypatch.setattr(service.transactions, 'commit', commit)
    assert send(guided, p)['assessment_receipt']['artifact']['summary']['recorded_reference_count'] == 2


def test_device_finish_links_owned_import_without_duplicate(guided):
    started = send(guided, start_request(context(guided), mode='device'))
    p = measured(guided, started)
    with Session(guided.engine) as db:
        row = WorkoutSession(id=UUID(int=206800), user_id=UUID(started['artifact']['athlete_id']), external_provider='POLAR', external_id='actual-device',
            sport=Sport.STRENGTH, started_at=datetime.fromisoformat(started['artifact']['created_at']), ended_at=guided.clock.current,
            duration_sec=1200, raw_data={'keep':'provider'})
        db.add(row)
        db.commit()
    before = count(guided, WorkoutSession)
    p.update(workout_session_id=str(UUID(int=206800)), actual_start_at=None, actual_end_at=None, no_other_recording_confirmed=False)
    result = send(guided, p)
    assert not result['artifact']['result']['workout_created'] and count(guided, WorkoutSession) == before
    with Session(guided.engine) as db:
        assert db.get(WorkoutSession, UUID(int=206800)).raw_data == {'keep':'provider'}


def test_changed_intake_retains_results_until_explicit_apply(guided):
    started = send(guided, start_request(context(guided)))
    fresh = initial_request(guided, 206500)
    fresh['data']['goal_label'] = 'Friss megjegyzés megőrzése'
    for e in fresh['data']['exercises']:
        e.update(sets=[], performed_on=None)
    save_initial(guided, fresh)
    result = send(guided, measured(guided, started))
    assert result['artifact']['result']['application_pending'] and result['assessment_receipt'] is None
    assert initial_context(guided)['data']['goal_label'] == 'Friss megjegyzés megőrzése'
    p = next_request(result, 'apply', 206003)
    c = context(guided)
    p.update(assessment_reference=c['intake']['reference'], source_hash=c['intake']['sources']['source_hash'])
    before = count(guided, WorkoutSession)
    applied = send(guided, p)
    assert applied['assessment_receipt']['artifact']['summary']['recorded_reference_count'] == 2
    assert applied['assessment_receipt']['artifact']['proposal']['data']['goal_label'] == 'Friss megjegyzés megőrzése'
    assert count(guided, WorkoutSession) == before


@pytest.mark.parametrize('field,value', [('rir','unknown'), ('repetitions',0), ('technique','unknown'), ('symptoms','unknown')])
def test_partial_actual_results_are_not_invented_references(guided, field, value):
    started = send(guided, start_request(context(guided)))
    p = measured(guided, started)
    for row in p['progress']['results']:
        row['observations'][0][field] = value
    result = send(guided, p)
    assert result['assessment_receipt']['artifact']['summary']['recorded_reference_count'] == 0


def test_pain_is_retained_and_blocks_reuse(guided):
    started = send(guided, start_request(context(guided)))
    p = measured(guided, started)
    p['progress']['results'][0]['observations'][0]['symptoms'] = 'pain'
    result = send(guided, p)
    assert result['artifact']['result']['stop_required']
    assert result['assessment_receipt']['artifact']['proposal']['data']['state_change'] == 'changed'


@pytest.mark.parametrize('case', ['future','date','duplicate','boolean','clock','no_recording'])
def test_invalid_results_fail_before_write(guided, case):
    started = send(guided, start_request(context(guided)))
    p = measured(guided, started)
    expected = 409
    if case == 'future': p['progress']['results'][0]['observations'][0]['performed_on'] = '2027-01-01'
    if case == 'date': p['progress']['results'][0]['observations'][0]['performed_on'] = '2026-02-30'; expected=422
    if case == 'duplicate': p['progress']['results'][0]['observations'] *= 2; expected=422
    if case == 'boolean': p['progress']['results'][0]['observations'][0]['repetitions'] = True; expected=422
    if case == 'clock': p['actual_end_at'] = p['actual_start_at']
    if case == 'no_recording': p['no_other_recording_confirmed'] = False
    before = count(guided, WorkoutSession), count(guided, PlanningAuditArtifactRow)
    send(guided, p, expected)
    assert before == (count(guided, WorkoutSession), count(guided, PlanningAuditArtifactRow))


def test_other_owner_cannot_resume(guided):
    started = send(guided, start_request(context(guided)))
    p = measured(guided, started)
    guided.email = OTHER_EMAIL
    assert context(guided)['latest'] is None
    send(guided, p, 409)


def test_practice_is_not_copied_as_training_dose(guided):
    started = send(guided, start_request(context(guided)))
    p = measured(guided, started)
    for i, row in enumerate(p['progress']['results']):
        row['observations'].insert(0, {**row['observations'][0], 'id': str(UUID(int=206150+i)), 'purpose':'practice', 'repetitions':3})
    result = send(guided, p)
    assert all(len(e['sets'])==1 for e in result['assessment_receipt']['artifact']['proposal']['data']['exercises'][:2])


def test_abandon_requires_no_physical_activity(guided):
    started = send(guided, start_request(context(guided)))
    p=next_request(started, 'abandon')
    p['progress']['warmup_completed']=True
    send(guided,p,409)
    p['progress']['warmup_completed']=False
    assert send(guided,p)['artifact']['state']=='abandoned'


def test_real_occasion_enables_beginner_without_becoming_duration_capacity(guided):
    from tests.planning.test_p2_4c18_4_training_plan import review
    from tests.planning.test_p2_4c20_5_assessed_strength import strength_candidates
    started=send(guided,start_request(context(guided)))
    active=review(guided)
    assert any(d['reason']=='GUIDED_ASSESSMENT_PENDING' for d in active['result']['days_without_proposal'])
    result=send(guided,measured(guided,started))
    value=review(guided)
    candidates=strength_candidates(value)
    assert candidates
    for candidate in candidates:
        meta=value['result']['prescription_context']['by_candidate'][candidate['candidate_key']]
        assert meta['reference_session_ids']==[] and meta['product_default_used']
    marked=[s for s in value['inputs']['recent_sessions'] if s.get('reference_occasion')]
    assert len(marked)==1 and marked[0]['id']==result['artifact']['result']['workout_session_id']
    assert marked[0]['duration_sec']==1200
