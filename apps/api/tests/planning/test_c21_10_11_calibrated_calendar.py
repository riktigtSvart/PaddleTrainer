"""Real calibrated starter plans remain readable without changing measurements."""
from contextlib import nullcontext
import json
import os
from pathlib import Path

import pytest

from app.api.routes import planning_calendar
from app.models.entities import PlannedWorkout, WorkoutSession
from app.planning.application import calendar_workspace
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from app.services import training_instructions, training_plan_policy
from tests.planning.test_p2_4c20_6_guided_strength import guided as fixture, send
from tests.planning.test_p2_4c20_7_calibration import start, finish
from tests.planning.test_p2_4c20_4_initial_assessment import context as initial_context
from tests.planning.test_p2_4c18_4_training_plan import review, accept
from tests.planning.test_p2_4c3_goal_workflow_api import count


@pytest.fixture
def env(tmp_path, monkeypatch):
    wrapper = fixture.__wrapped__(tmp_path, monkeypatch)
    e = next(wrapper)
    e.app.include_router(planning_calendar.router, prefix='/api/v1')
    monkeypatch.setattr(calendar_workspace, '_now', e.clock.tick)
    try:
        yield e
    finally:
        wrapper.close()


def export(name, value):
    if os.getenv('C21_10_11_EXPORT'):
        path = Path(os.environ['C21_10_11_EXPORT'])
        values = json.loads(path.read_text()) if path.exists() else {}
        values[name] = value
        path.write_text(json.dumps(values), encoding='utf-8')


@pytest.mark.parametrize('legacy', [False, True])
@pytest.mark.parametrize('measured_rir', ['2', '3'])
def test_calibrated_unknown_future_reserve_keeps_owned_source_and_unchanged_records(env, monkeypatch, legacy, measured_rir):
    measured = send(env, finish(env, start(env), repetitions=8, rir=measured_rir))
    observed = initial_context(env)['saved']['artifact']
    with monkeypatch.context() if legacy else nullcontext() as patch:
        if legacy:
            patch.setattr(training_instructions, 'attach', lambda result: result)
            patch.setitem(training_plan_policy.POLICY, 'version', 'training-plan-policy-v0.13')
        plan = review(env)
        assert any(c['sport'] == 'STRENGTH' for c in plan['result']['create'])
        accept(env, plan, token=21111001)
    stats = lambda: tuple(count(env, t) for t in (PlanningAuditArtifactRow, PlannedWorkout, WorkoutSession))
    before = stats()
    r = env.client.get('/api/v1/planning/calendar/feed?start_date=2026-10-24&end_date=2026-10-29')
    assert r.status_code == 200, r.text
    feed = r.json()
    strength = [p for p in feed['planned'] if p['sport'] == 'STRENGTH']
    assert strength
    for row in strength:
        dose = row['planning_context']['instructions']['main']['strength']
        assert dose['minimum_rir'] == 3 and not dose['load_increased']
        if legacy:
            assert dose['rest_seconds'] == 180 and dose['calibration_derivations'] and not dose['sets_added']
        for m in dose['movements']:
            d = next(d for d in dose['calibration_derivations'] if d['entry_id'] == m['entry_id']) if legacy else m['calibration_derivation']
            reference = m['sets'][0] if legacy else m['reference_set']
            assert d['guided_reference']['artifact_id'] == measured['artifact']['artifact_id']
            assert d['source_rir'] == measured_rir and d['source_repetitions'] == 8
            assert d['planned_repetitions'] == reference['repetitions'] == 6
            assert reference['rir'] == 'unknown'
            if not legacy:
                assert m['target']['repetitions'] == 6 and m['rest_seconds'] == 180
    assert stats() == before
    assert initial_context(env)['saved']['artifact'] == observed
    name = ('legacy' if legacy else 'current') + '_rir_' + measured_rir
    export(name, {'review': plan, 'feed': feed})
