"""Read-only calendar cycles use current goals and genuinely accepted waves."""
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import PlannedWorkout, TrainingPeriod, WorkoutSession, WorkoutStatus, Sport
from app.planning.application import calendar_workspace
from app.planning.domain.athlete_setup import digest
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from tests.planning.test_c21_9_1_calendar_endurance import env as source_fixture
from tests.planning.test_c21_10_swimming_load import configure
from tests.planning.test_c21_10_5_goal_coverage import full
from tests.planning.test_p2_4c18_4_training_plan import accept
from tests.planning.test_p2_4c3_goal_workflow_api import ATHLETE, OTHER_EMAIL, count


@pytest.fixture
def env(tmp_path, monkeypatch):
    wrapper = source_fixture.__wrapped__(tmp_path, monkeypatch)
    e = next(wrapper)
    monkeypatch.setattr(calendar_workspace, '_now', e.clock.tick)
    configure(e)
    try:
        yield e
    finally:
        wrapper.close()


def get(e, first='2026-10-26', last='2026-11-22', path='cycles', expected=200):
    r = e.client.get(f'/api/v1/planning/calendar/{path}?start_date={first}&end_date={last}')
    assert r.status_code == expected, r.text
    assert r.headers['Cache-Control'] == 'no-store'
    return r.json()


def export(name, **value):
    if os.getenv('C21_10_7_EXPORT'):
        p = Path(os.environ['C21_10_7_EXPORT'])
        rows = json.loads(p.read_text()) if p.exists() else {}
        rows[name] = value
        p.write_text(json.dumps(rows))


def first_meso(e):
    return next(p for p in e.program['periods'] if p['period_type'] == 'MESOCYCLE')


def test_saved_goals_are_available_before_a_plan_is_accepted_but_no_wave_is_invented(env):
    before = count(env, PlanningAuditArtifactRow), count(env, PlannedWorkout)
    value = get(env)
    assert value['content_hash'] == digest({k: v for k, v in value.items() if k != 'content_hash'})
    assert value['cycles'] and any(g['capability_key'] == 'MAX_STRENGTH' and g['role'] == 'primary_development'
        for c in value['cycles'] for g in c['goals'])
    assert all(c['wave_status'] == 'not_accepted' and not c['blocks'] and c['wave_source'] is None for c in value['cycles'])
    assert (count(env, PlanningAuditArtifactRow), count(env, PlannedWorkout)) == before
    export('unaccepted', context=value)


def test_actual_accepted_wave_matches_the_saved_review_and_leaves_all_records_unchanged(env):
    reviewed = full(env)
    accepted = accept(env, reviewed, token=2110701)['artifact']
    before = count(env, PlanningAuditArtifactRow), count(env, PlannedWorkout), count(env, WorkoutSession)
    value = get(env)
    for c in value['cycles']:
        assert c['wave_status'] == 'accepted'
        assert c['blocks'] == [b for b in reviewed['result']['mesocycle_coordination']['blocks'] if b['mesocycle_id'] == c['period']['id']]
        assert c['wave_source']['acceptance_reference']['content_hash'] == accepted['content_hash']
        assert c['latest_review']['review_reference']['content_hash'] == reviewed['content_hash']
    assert all(value[k] is False for k in ('planning_authorized', 'workouts_changed', 'adaptation_measured', 'has_more'))
    assert before == (count(env, PlanningAuditArtifactRow), count(env, PlannedWorkout), count(env, WorkoutSession))
    p = first_meso(env)
    export('accepted', context=get(env, p['start_date'], p['end_date']), feed=get(env, p['start_date'], p['end_date'], path='feed'))


def test_an_unaccepted_preview_can_update_diagnostics_but_cannot_repaint_the_calendar(env):
    reviewed = full(env)
    accept(env, reviewed, token=2110702)
    before = get(env)
    r = env.client.post(env.plan_url + '/review', json={'start_date': '2026-10-26', 'end_date': '2026-10-28', 'coordinate_mesocycles': False})
    assert r.status_code == 200, r.text
    after = get(env)
    assert [(c['blocks'], c['wave_source']) for c in after['cycles']] == [(c['blocks'], c['wave_source']) for c in before['cycles']]
    export('preview_only', context=after, previous_context=before)


def test_a_moved_saved_cycle_does_not_inherit_colours_from_its_old_dates(env):
    accept(env, full(env), token=2110703)
    period = first_meso(env)
    with Session(env.engine) as db:
        row = db.get(TrainingPeriod, UUID(period['id']))
        row.end_date -= timedelta(days=1)
        db.commit()
    value = get(env)
    row = next(c for c in value['cycles'] if c['period']['id'] == period['id'])
    assert row['wave_status'] == 'dates_changed' and row['blocks'] == [] and row['wave_source'] is None
    export('changed_dates', context=value)


def test_short_accepted_review_is_labelled_without_inventing_a_four_week_wave(env):
    accept(env, full(env), token=2110704)
    r = env.client.post(env.plan_url + '/review', json={'start_date': '2026-10-26', 'end_date': '2026-10-28', 'coordinate_mesocycles': False})
    assert r.status_code == 200, r.text
    accept(env, r.json()['review'], token=2110705)
    value = get(env)
    assert all(c['wave_status'] == 'short_review' and not c['blocks'] for c in value['cycles'])


def test_cycle_context_is_owner_scoped_and_empty_for_another_athlete(env):
    accept(env, full(env), token=2110706)
    env.email = OTHER_EMAIL
    value = get(env)
    assert value['athlete_id'] != ATHLETE and value['cycles'] == []


def test_past_unlabelled_strength_is_retained_without_assigning_it_a_made_up_goal(env):
    accept(env, full(env), token=2110707)
    with Session(env.engine) as db:
        plan = next(p for p in db.scalars(select(PlannedWorkout).where(PlannedWorkout.user_id == UUID(ATHLETE))) if p.sport == Sport.STRENGTH)
        started = plan.planned_start_time.replace(tzinfo=UTC)
        db.add(WorkoutSession(id=UUID(int=2110708), user_id=UUID(ATHLETE), external_provider='MANUAL', external_id='cycle-linked',
            sport=Sport.STRENGTH, started_at=started, ended_at=started+timedelta(seconds=plan.duration_sec), duration_sec=plan.duration_sec,
            planned_workout_id=plan.id, raw_data={}))
        db.add(WorkoutSession(id=UUID(int=2110709), user_id=UUID(ATHLETE), external_provider='MANUAL', external_id='cycle-unknown-purpose',
            sport=Sport.STRENGTH, started_at=started+timedelta(hours=2), ended_at=started+timedelta(hours=2,minutes=10), duration_sec=600, raw_data={}))
        plan.status = WorkoutStatus.COMPLETED
        db.commit()
    env.clock.current = started+timedelta(days=1)
    p = first_meso(env)
    feed = get(env, p['start_date'], p['end_date'], path='feed')
    assert len(feed['sessions']) == 2
    linked = next(s for s in feed['sessions'] if s['planned_workout_id'])
    planned = next(p for p in feed['planned'] if p['id'] == linked['planned_workout_id'])
    assert planned['planning_context']['primary_goal'] == 'MAX_STRENGTH'
    unknown = next(s for s in feed['sessions'] if not s['planned_workout_id'])
    assert unknown['goal_tag'] is None and unknown['linked_goal_tag'] is None
    export('recorded', context=get(env, p['start_date'], p['end_date']), feed=feed)


@pytest.mark.parametrize('query', ['?start_date=2026-10-26', '?start_date=2026-02-30&end_date=2026-03-01', '?start_date=2026-10-27&end_date=2026-10-26', '?start_date=2025-01-01&end_date=2026-11-14', '?start_date=2026-10-26&end_date=2026-11-22&owner=other'])
def test_cycle_reads_reject_missing_invalid_or_injected_ranges(env, query):
    assert env.client.get('/api/v1/planning/calendar/cycles' + query).status_code == 422
