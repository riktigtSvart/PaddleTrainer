"""Real authoring HTTP flows, atomic recurrence and protected execution evidence."""
from copy import deepcopy
from datetime import date
import json
import os
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from app.models.entities import PlannedWorkout, WorkoutBlock, WorkoutSession, WorkoutStatus, Sport
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from app.services import manual_workouts as service
from tests.planning.test_p2_4c6_calendar_workspace import agenda, BASE, PLAN, OTHER_PLAN, get as feed
from tests.planning.test_p2_4c3_goal_workflow_api import count, ATHLETE

URL = BASE + '/manual-workouts'


def draft(**changes):
    return {'date': '2026-11-20', 'start_time': '18:30', 'sport': 'STRENGTH', 'title': 'Saját erősítés',
        'duration_sec': 3600, 'description': 'Saját edzéstervem', 'location': 'Csónakház',
        'primary_goal': 'MAX_STRENGTH', 'phases': [
            {'block_type': 'WARMUP', 'name': 'Bemelegítés', 'duration_sec': 600},
            {'block_type': 'WORK', 'name': 'Erősítés', 'duration_sec': 2400},
            {'block_type': 'COOLDOWN', 'name': 'Levezetés', 'duration_sec': 600}],
        'exercises': [{'name': 'Saját fekvenyomás', 'sets': 4, 'reps': 8, 'load_mode': 'kg',
            'weight_kg': '72.125', 'rest_seconds': 180, 'reserve_reps': 2},
            {'exercise_id': 'pullup', 'name': 'Húzódzkodás', 'sets': 3, 'reps': 6,
             'load_mode': 'bodyweight', 'rest_seconds': 120}], **changes}


def body(token=21120001, **changes):
    return {'request_id': str(UUID(int=token)), 'operation': 'create', 'timezone_name': 'Europe/Budapest',
            'draft': draft(), **changes}


def post(e, value, status=200):
    r = e.client.post(URL, json=value)
    assert r.status_code == status, r.text
    return r.json()


def source(e, workout_id=None, status=200):
    r = e.client.get(URL + ('/' + workout_id if workout_id else '/context'))
    assert r.status_code == status, r.text
    return r.json()


def export(name, value):
    if os.getenv('C21_10_20_EXPORT'):
        p = Path(os.environ['C21_10_20_EXPORT'])
        values = json.loads(p.read_text()) if p.exists() else {}
        values[name] = value
        p.write_text(json.dumps(values, ensure_ascii=False), encoding='utf-8')


def edits(e, receipt, token=21120002, operation='update'):
    s = source(e, receipt['workout_ids'][0])['workout']
    return body(token, operation=operation, workout_id=s['id'], expected_source_hash=s['source_hash'],
                expected_goal_reference=s['goal_reference'], draft=s['draft'] if operation != 'cancel' else None)


def test_create_reopen_edit_copy_cancel_and_retry_are_exact_and_local(agenda, monkeypatch):
    def forbidden(*a, **k):
        raise AssertionError('authoring must not run a planner')
    from app.services import training_plans
    monkeypatch.setattr(training_plans, 'review', forbidden)
    sessions = count(agenda, WorkoutSession)
    before = source(agenda)
    saved = post(agenda, body())
    assert saved['committed'] and len(saved['workout_ids']) == 1 and not saved['provider_writeback']
    assert post(agenda, body())['reused']
    opened = source(agenda, saved['workout_ids'][0])
    s = opened['workout']
    assert s['editable'] and s['copyable'] and s['source'] == 'MANUAL'
    assert s['draft']['exercises'][0]['weight_kg'] == '72.125'
    assert s['draft']['exercises'][0]['sets'] == 4 and s['draft']['phases'][1]['duration_sec'] == 2400
    edit = edits(agenda, saved); edit['draft']['title'] = 'Módosított saját erősítés'
    edited = post(agenda, edit)
    assert edited['workout_ids'] == saved['workout_ids']
    assert post(agenda, body())['reused']  # historical retry does not undo edit
    current = source(agenda, saved['workout_ids'][0])['workout']
    assert current['draft']['title'] == 'Módosított saját erősítés'
    copied_body = body(21120003, copy_from=current['id'], copy_source_hash=current['source_hash'],
        draft={**current['draft'], 'date': '2026-11-27', 'primary_goal': None})
    copied = post(agenda, copied_body)
    assert copied['workout_ids'] != saved['workout_ids']
    cancel = edits(agenda, copied, 21120004, 'cancel')
    cancelled = post(agenda, cancel)
    assert source(agenda, copied['workout_ids'][0])['workout']['status'] == 'CANCELLED'
    assert post(agenda, cancel)['reused'] and count(agenda, WorkoutSession) == sessions
    data = feed(agenda, '?start_date=2026-11-20&end_date=2026-11-27')
    planned = next(p for p in data['planned'] if p['id'] == current['id'])
    assert planned['goal_tag']['primary_goal'] == 'MAX_STRENGTH'
    assert planned['manual_context']['recipe']['exercises'][0]['sets'] == 4
    assert len(planned['blocks']) == 3 and planned['planned_start_time'].endswith('17:30:00+00:00')
    assert all(not request.in_transaction() for request in agenda.requests)
    for name, value in [('context', before), ('created', saved), ('opened', opened), ('edit_body', edit),
                        ('edited', edited), ('copy_body', copied_body), ('copied', copied), ('cancelled', cancelled), ('feed', data)]:
        export(name, value)


def test_weekly_occurrences_save_atomically_and_do_not_become_training_history(agenda):
    b = body(repeat_dates=['2026-11-27', '2026-12-04', '2026-12-11'])
    saved = post(agenda, b)
    assert len(saved['workout_ids']) == 4 and post(agenda, b)['reused']
    with Session(agenda.engine) as db:
        rows = db.query(PlannedWorkout).filter(PlannedWorkout.id.in_([UUID(v) for v in saved['workout_ids']])).all()
        assert {r.date.isoformat() for r in rows} == {b['draft']['date'], *b['repeat_dates']}
        assert all(r.status == WorkoutStatus.PLANNED and r.source == 'MANUAL' for r in rows)
        assert not db.query(PlanningAuditArtifactRow).filter_by(artifact_kind='strength_workout_log').count()


@pytest.mark.parametrize('change', ['workout', 'goal', 'request', 'timezone', 'copy'])
def test_stale_or_reused_identity_never_overwrites_or_duplicates(agenda, change):
    saved = post(agenda, body()); b = edits(agenda, saved)
    if change == 'request':
        b = body(); b['draft']['title'] = 'Different bytes'
    elif change == 'timezone':
        b['timezone_name'] = 'UTC'
    elif change == 'copy':
        b = body(21120002, copy_from=saved['workout_ids'][0], copy_source_hash='f' * 64)
    elif change == 'workout':
        b['expected_source_hash'] = 'f' * 64
    else:
        b['expected_goal_reference'] = None
    before = count(agenda, PlannedWorkout), count(agenda, PlanningAuditArtifactRow)
    post(agenda, b, 409)
    assert before == (count(agenda, PlannedWorkout), count(agenda, PlanningAuditArtifactRow))


@pytest.mark.parametrize('proof', ['linked', 'completed', 'skipped', 'cancelled', 'polar', 'generated', 'foreign'])
def test_protected_or_executed_workout_cannot_be_edited_or_cancelled(agenda, proof):
    saved = post(agenda, body()); workout_id = saved['workout_ids'][0]
    with Session(agenda.engine) as db:
        row = db.get(PlannedWorkout, UUID(workout_id))
        if proof in {'completed', 'skipped', 'cancelled'}: row.status = WorkoutStatus(proof.upper())
        elif proof == 'polar': row.polar_target_id = 'provider-target'
        elif proof == 'generated': row.source = 'PADDLETRAINER_C18_4'
        elif proof == 'foreign':
            from tests.planning.test_p2_4c3_goal_workflow_api import OTHER
            row.user_id = UUID(OTHER)
        else:
            db.add(WorkoutSession(id=UUID(int=21120999), user_id=UUID(ATHLETE), sport=Sport.STRENGTH,
                external_provider='LOCAL', external_id='executed', started_at=agenda.clock.current,
                planned_workout_id=row.id, raw_data={}))
        db.commit()
    if proof == 'foreign':
        source(agenda, workout_id, 404)
        b = body(21120002, operation='cancel', workout_id=workout_id, expected_source_hash='f'*64, draft=None)
        post(agenda, b, 404)
    else:
        opened = source(agenda, workout_id)['workout']
        assert not opened['editable']
        for operation in ['update', 'cancel']:
            post(agenda, edits(agenda, saved, operation=operation), 409)


@pytest.mark.parametrize('change', ['phase_time', 'missing_title', 'negative_sets', 'reserve_boolean',
    'weight_without_kg', 'kg_without_weight', 'reps_and_hold', 'duplicate_day', 'invalid_day', 'status', 'owner', 'exercise_id'])
def test_invalid_forms_explain_errors_at_save_and_leave_no_partial_rows(agenda, change):
    b = body(repeat_dates=['2026-11-27'])
    if change == 'phase_time': b['draft']['duration_sec'] = 1200
    elif change == 'missing_title': b['draft']['title'] = ' '
    elif change == 'negative_sets': b['draft']['exercises'][0]['sets'] = -1
    elif change == 'reserve_boolean': b['draft']['exercises'][0]['reserve_reps'] = True
    elif change == 'weight_without_kg': b['draft']['exercises'][0]['load_mode'] = 'bodyweight'
    elif change == 'kg_without_weight': b['draft']['exercises'][0].pop('weight_kg')
    elif change == 'reps_and_hold': b['draft']['exercises'][0]['hold_seconds'] = 30
    elif change == 'duplicate_day': b['repeat_dates'].append(b['draft']['date'])
    elif change == 'invalid_day': b['repeat_dates'] = ['2026-02-30']
    elif change in {'status', 'owner'}: b[change] = 'COMPLETED'
    else: b['draft']['exercises'][0]['exercise_id'] = 'pullup'
    before = count(agenda, PlannedWorkout), count(agenda, PlanningAuditArtifactRow)
    rejected = post(agenda, b, 409 if change == 'exercise_id' else 422)
    if change != 'exercise_id': assert rejected['detail']['issues']
    assert before == (count(agenda, PlannedWorkout), count(agenda, PlanningAuditArtifactRow))


@pytest.mark.parametrize('day,fold,status', [('2027-03-28',None,409), ('2026-10-25',None,409), ('2026-10-25',1,200)])
def test_local_time_obeys_dst_and_failed_recurrence_rolls_back_every_occurrence(agenda, day, fold, status):
    b = body(draft=draft(date='2026-10-18', start_time='02:30', start_fold=fold), repeat_dates=[day])
    before = count(agenda, PlannedWorkout), count(agenda, PlanningAuditArtifactRow)
    post(agenda, b, status)
    if status != 200:
        assert before == (count(agenda, PlannedWorkout), count(agenda, PlanningAuditArtifactRow))


def test_copy_preserves_source_and_overlap_warns_without_cancelling_anything(agenda):
    current = source(agenda, PLAN)['workout']
    assert not current['editable']  # already linked to an executed session
    before = source(agenda, PLAN)
    b = body(copy_from=PLAN, copy_source_hash=current['source_hash'],
        draft=draft(date='2026-10-23', sport='KAYAK', exercises=[]))
    result = post(agenda, b)
    assert result['warnings'] == [{'code': 'OTHER_WORKOUT_ON_DAY', 'date': '2026-10-23'}]
    assert source(agenda, PLAN) == before
    source(agenda, OTHER_PLAN, 404)


def test_edit_and_copy_preserve_numeric_intensity_and_phase_repetition(agenda):
    d = draft(intensity_type='HR', phases=[{'block_type': 'WORK', 'name': 'Sorozat',
        'duration_sec': 600, 'repeat_count': 3, 'intensity_type': 'RPE', 'intensity_min': 6.5, 'intensity_max': 7.5}])
    saved = post(agenda, body(draft=d))
    opened = source(agenda, saved['workout_ids'][0])['workout']
    edit = edits(agenda, saved); edit['draft']['title'] = 'Új név'; post(agenda, edit)
    with Session(agenda.engine) as db:
        row = db.get(PlannedWorkout, UUID(opened['id']))
        assert row.intensity_type == 'HR'
        assert row.blocks[0].intensity_min == 6.5 and row.blocks[0].intensity_max == 7.5
        assert row.blocks[0].repeat_count == 3
    current = source(agenda, opened['id'])['workout']
    copied = post(agenda, body(21120003, draft={**current['draft'], 'date': '2026-11-27'},
        copy_from=current['id'], copy_source_hash=current['source_hash']))
    assert source(agenda, copied['workout_ids'][0])['workout']['draft']['phases'] == current['draft']['phases']


def test_concurrent_goal_edit_is_preserved_until_the_form_is_reopened(agenda):
    from tests.planning.test_p2_4c6_calendar_workspace import post as goal_post, goal
    saved = post(agenda, body()); edit = edits(agenda, saved)
    previous = source(agenda, saved['workout_ids'][0])['workout']['goal_reference']
    goal_post(agenda, goal(entity=saved['workout_ids'][0], primary='RECOVERY', previous=previous))
    post(agenda, edit, 409)
    assert source(agenda, saved['workout_ids'][0])['workout']['draft']['primary_goal'] == 'RECOVERY'


def test_repeated_occurrences_cannot_spill_out_of_an_explicit_mesocycle(agenda):
    context = source(agenda)
    period = context['mesocycles'][0]
    before = count(agenda, PlannedWorkout), count(agenda, PlanningAuditArtifactRow)
    post(agenda, body(draft=draft(date=period['start_date'], mesocycle_id=period['id']), repeat_dates=['2027-01-01']), 409)
    assert before == (count(agenda, PlannedWorkout), count(agenda, PlanningAuditArtifactRow))


def test_replanning_preserves_authored_workout_and_counts_its_occupancy(tmp_path, monkeypatch):
    from tests.planning.test_c21_10_9_profile_sources import env as fixture, configure, full
    from tests.planning.test_p2_4c18_4_training_plan import accept
    from tests.planning.test_c21_10_17_direct_picker import snapshots
    wrapper = fixture.__wrapped__(tmp_path, monkeypatch); e = next(wrapper)
    try:
        configure(e)
        saved = post(e, body(draft=draft(date='2026-11-02', start_time='18:00', duration_sec=1200,
            phases=[], exercises=[], sport='KAYAK', primary_goal='TECHNICAL_SKILL')))
        manual_id = saved['workout_ids'][0]
        before = snapshots(e)[manual_id]
        value = full(e)
        assert manual_id not in value['result']['cancel']
        snapshot = next(p for p in value['plan_snapshots'] if p['workout']['id'] == manual_id)
        assert not snapshot['replaceable'] and not snapshot['owned_sample']
        for candidate in value['result']['proposals']:
            if candidate['date'] == '2026-11-02':
                assert candidate['end_at'] <= '2026-11-02T17:00:00+00:00' or candidate['start_at'] >= '2026-11-02T17:20:00+00:00'
        accept(e, value, token=21120099)
        assert snapshots(e)[manual_id] == before
    finally:
        wrapper.close()
