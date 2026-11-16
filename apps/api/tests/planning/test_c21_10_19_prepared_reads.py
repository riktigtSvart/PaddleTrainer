"""Prepared views separate display reads from explicit planning and selection."""
import asyncio
from datetime import timedelta
import importlib.util
import json
import os
from pathlib import Path
from uuid import UUID
import pytest
from sqlalchemy.orm import Session
from app.models.entities import PlannedWorkout, WorkoutSession, WorkoutStatus, Sport
from app.planning.domain.athlete_setup import digest
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow as Row
from app.services import training_plans as plans, training_read_models as views
from tests.planning.test_c21_10_9_profile_sources import env, configure, full
from tests.planning.test_c21_10_17_direct_picker import setup, snapshots
from tests.planning.test_c21_10_15_today_and_variants import feed
from tests.planning.test_p2_4c18_4_training_plan import accept
from tests.planning.test_p2_4c3_goal_workflow_api import OTHER, count
from tests.planning.test_p2_4a2_planning_utility_storage import AsyncSQLiteBridge


def export(name, value):
    if os.getenv('C21_10_19_EXPORT'):
        path = Path(os.environ['C21_10_19_EXPORT'])
        values = json.loads(path.read_text()) if path.exists() else {}
        values[name] = value
        path.write_text(json.dumps(values, ensure_ascii=False), encoding='utf-8')


def options(e, target, status=200):
    response = e.client.get(f"/api/v1/planning/calendar/workouts/{target['id']}/alternatives")
    assert response.status_code == status, response.text
    return response.json()


def select(e, target, value, candidate, status=200, **changes):
    response = e.client.post(f"/api/v1/planning/calendar/workouts/{target['id']}/alternatives/choose", json={
        'expected_workout_hash': target['planning_context']['workout_hash'],
        'source_review_reference': value['source_review_reference'], 'candidate_key': candidate['candidate']['candidate_key'], **changes})
    assert response.status_code == status, response.text
    return response.json()


def test_opening_and_reopening_reads_prepared_cards_without_planner_locks_or_writes(env, monkeypatch):
    target, _ = setup(env)
    before = snapshots(env), count(env, Row), count(env, WorkoutSession)
    async def forbidden(*args, **kwargs):
        raise AssertionError('A display read must not invoke planning or persist a review')
    monkeypatch.setattr(plans, 'assess', forbidden)
    monkeypatch.setattr(plans, 'review', forbidden)
    monkeypatch.setattr(plans, 'persist', forbidden)
    value = options(env, target)
    assert value['status'] == 'ready' and value['candidates']
    assert any(r['candidate']['sport'] == 'STRENGTH' and r['instructions']['main']['strength'] for r in value['candidates'])
    assert all('inputs' not in r and 'plan_snapshots' not in r for r in value['candidates'])
    assert value['content_hash'] == digest({k: v for k, v in value.items() if k != 'content_hash'})
    assert options(env, target)['candidates'] == value['candidates']
    assert before == (snapshots(env), count(env, Row), count(env, WorkoutSession))
    export('target', target); export('options', value); export('feed', feed(env))


def test_only_a_deliberate_selection_runs_one_fresh_review_and_preserves_other_days(env, monkeypatch):
    target, _ = setup(env); value = options(env, target)
    candidate = next(r for r in value['candidates'] if r['candidate']['sport'] == 'STRENGTH')
    before = snapshots(env); original, calls = plans.assess, []
    async def assess(*args, **kwargs):
        calls.append(kwargs.get('alternatives_for'))
        return await original(*args, **kwargs)
    monkeypatch.setattr(plans, 'assess', assess)
    chosen = select(env, target, value, candidate)['review']
    assert len(calls) == 1 and calls[0]['workout_id'] == target['id']
    assert snapshots(env) == before and chosen['result']['cancel'] == [target['id']]
    receipt = accept(env, chosen, token=21119001)
    assert len(calls) == 2
    after = snapshots(env)
    assert all(after[k] == v for k, v in before.items() if k != target['id'])
    assert after[target['id']][0] == 'CANCELLED'
    assert accept(env, chosen, token=21119001, expected=200)['reused']
    assert snapshots(env) == after
    export('chosen', chosen); export('receipt', receipt); export('clicked', candidate)


@pytest.mark.parametrize('proof', ['completed', 'skipped', 'linked', 'unlinked', 'approved', 'changed'])
def test_prepared_cards_disappear_when_current_evidence_blocks_the_target(env, proof):
    target, _ = setup(env); value = options(env, target); candidate = value['candidates'][0]
    with Session(env.engine) as db:
        row = db.get(PlannedWorkout, UUID(target['id']))
        if proof == 'completed': row.status = WorkoutStatus.COMPLETED
        if proof == 'skipped': row.status = WorkoutStatus.SKIPPED
        if proof == 'approved': row.polar_target_id = 'approved-provider-target'
        if proof == 'changed': row.duration_sec += 300
        if proof in {'linked', 'unlinked'}:
            db.add(WorkoutSession(id=UUID(int=21119101), user_id=row.user_id, external_provider='LOCAL', external_id='new-evidence',
                sport=Sport(row.sport), started_at=env.clock.current, planned_workout_id=row.id if proof == 'linked' else None, raw_data={}))
        db.commit()
    before = snapshots(env)
    assert options(env, target)['status'] == 'unavailable'
    select(env, target, value, candidate, 409)
    assert snapshots(env) == before


def test_expiry_filters_saved_options_without_a_new_review(env):
    from app.services.training_alternative_availability import at
    target, _ = setup(env); value = options(env, target)
    longest = min(value['candidates'], key=lambda r: r['timing']['expires_at'])
    env.clock.current = at(longest['timing']['expires_at']) + timedelta(seconds=1)
    before = count(env, Row), snapshots(env)
    assert all(r['candidate']['candidate_key'] != longest['candidate']['candidate_key'] for r in options(env, target)['candidates'])
    select(env, target, value, longest, 409)
    assert before == (count(env, Row), snapshots(env))


@pytest.mark.parametrize('change', ['foreign', 'wrong_hash', 'wrong_candidate', 'wrong_reference'])
def test_saved_view_identity_cannot_authorize_a_different_workout_or_dose(env, change):
    target, _ = setup(env); value = options(env, target); candidate = value['candidates'][0]; extra = {}
    if change == 'foreign':
        with Session(env.engine) as db:
            db.get(PlannedWorkout, UUID(target['id'])).user_id = UUID(OTHER); db.commit()
    if change == 'wrong_hash': extra['expected_workout_hash'] = 'f' * 64
    if change == 'wrong_candidate': extra['candidate_key'] = 'f' * 64
    if change == 'wrong_reference': extra['source_review_reference'] = {**value['source_review_reference'], 'content_hash': 'f' * 64}
    before = snapshots(env)
    select(env, target, value, candidate, 404 if change == 'foreign' else 409, **extra)
    assert snapshots(env) == before


def test_corrupt_prepared_source_is_rejected_while_original_evidence_stays_unchanged(env):
    target, _ = setup(env); value = options(env, target)
    with Session(env.engine) as db:
        original = db.query(Row).filter_by(artifact_id=value['source_review_reference']['artifact_id']).one().contract_json
        row = db.query(Row).filter_by(artifact_id=views.identity(value['source_review_reference']['artifact_id'])).one()
        row.contract_json = row.contract_json.replace('"timezone_name":"Europe/Budapest"', '"timezone_name":"UTC"'); db.commit()
    options(env, target, 503)
    with Session(env.engine) as db:
        assert db.query(Row).filter_by(artifact_id=value['source_review_reference']['artifact_id']).one().contract_json == original


def test_preparation_backfills_legacy_sources_once_and_never_rewrites_originals(env):
    configure(env); reviewed = full(env); accept(env, reviewed, token=21119002)
    with Session(env.engine) as db:
        originals = {r.artifact_id: r.contract_json for r in db.query(Row).filter(Row.artifact_kind != views.KIND.value)}
        db.query(Row).filter(Row.artifact_kind == views.KIND.value).delete(); db.commit()
    source = Path(__file__).resolve().parents[4] / 'tools/prepare_c21_10_19_views.py'
    spec = importlib.util.spec_from_file_location('prepare_views', source); module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    with Session(env.engine, expire_on_commit=False) as db:
        first = asyncio.run(module.prepare(AsyncSQLiteBridge(db), reviewed['athlete_id']))
        second = asyncio.run(module.prepare(AsyncSQLiteBridge(db), reviewed['athlete_id']))
    assert first['prepared_sources'] >= 2 and second['prepared_sources'] == 0
    with Session(env.engine) as db:
        assert originals == {r.artifact_id: r.contract_json for r in db.query(Row).filter(Row.artifact_kind != views.KIND.value)}


def test_prepared_calendar_and_schedule_slices_match_real_narrow_reads(env):
    configure(env); reviewed = full(env); accept(env, reviewed, token=21119003); values = {}
    for key, first, last in [('wide', '2026-10-26', '2026-11-22'), ('week', '2026-11-02', '2026-11-08'), ('day', '2026-11-05', '2026-11-05')]:
        values[key] = {}
        for endpoint in ['feed', 'constraints', 'cycles']:
            r = env.client.get(f'/api/v1/planning/calendar/{endpoint}?start_date={first}&end_date={last}')
            assert r.status_code == 200, r.text
            values[key][endpoint] = r.json()
    export('ranges', values)


@pytest.mark.parametrize('mode', ['legacy_week', 'coordinated_month'])
def test_every_saved_card_is_selectable_with_unchanged_inputs_and_without_changing_other_days(env, mode):
    if mode == 'legacy_week':
        target, _ = setup(env)
    else:
        configure(env); reviewed = full(env); accept(env, reviewed, token=21119004)
        target = env.client.get('/api/v1/planning/calendar/feed?start_date=2026-10-26&end_date=2026-11-22').json()['planned'][0]
    value = options(env, target); before = snapshots(env)
    for candidate in value['candidates']:
        if candidate['is_current']:
            continue
        selected = select(env, target, value, candidate)['review']
        assert selected['coordinate_mesocycles'] is (mode == 'coordinated_month')
        assert selected['result']['cancel'] == [target['id']]
        assert snapshots(env) == before
