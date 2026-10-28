"""Real owned HTTP persistence, immutable revisions and retry conflicts."""
from copy import deepcopy
from uuid import UUID
from datetime import UTC, datetime
import pytest
from sqlalchemy.orm import Session
from app.models.entities import WorkoutSession
from app.services import session_feedback as service
from app.schemas.session_feedback import FeedbackInput
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from tests.planning.test_p2_4c6_calendar_workspace import agenda, ACTUAL
from tests.planning.test_p2_4c3_goal_workflow_api import count

BASE = f"/api/v1/planning/calendar/sessions/{ACTUAL}/feedback"

def body(token=110001, **changes):
    return {"request_id": str(UUID(int=token)), "timing": "IMMEDIATE", "expected_revision": 0,
        "observed_at": "2026-10-23T17:00:00+00:00", "rpe": 5, "fatigue": 0,
        "soreness": None, "recovery": None, "energy": 7, "comment": "", **changes}

def post(env, payload, status=201, path=BASE):
    reply = env.client.post(path, json=payload)
    assert reply.status_code == status, reply.text
    assert reply.headers['cache-control'] == 'no-store'
    return reply.json()

def test_feedback_survives_reload_and_provider_summary_updates(agenda):
    saved = post(agenda, body())
    assert saved['committed'] and not saved['reused']
    assert saved['artifact']['revision'] == 1
    current = agenda.client.get(BASE).json()['current']['IMMEDIATE']
    assert current == saved['artifact']
    assert current['proposal']['fatigue'] == 0 and current['proposal']['soreness'] is None
    with Session(agenda.engine) as db:
        workout = db.get(WorkoutSession, UUID(ACTUAL))
        assert workout.raw_data == {'unchanged': True} and workout.rpe is None
        workout.rpe, workout.raw_data = 8, {'provider': 'refreshed'}
        db.commit()
    assert agenda.client.get(BASE).json()['current']['IMMEDIATE'] == current
    assert all(not r.in_transaction() for r in agenda.requests)

def test_retries_are_exact_and_edits_form_one_chain(agenda):
    a = post(agenda, body())
    assert post(agenda, body(), 200)['artifact'] == a['artifact']
    post(agenda, body(comment='different'), 409)
    b = post(agenda, body(110002, expected_revision=1, rpe=6, comment='<script>literal</script>'))
    assert b['artifact']['previous_hash'] == a['artifact']['content_hash']
    post(agenda, body(110003), 409)
    # A delayed retry of an older committed revision remains a valid receipt.
    assert post(agenda, body(), 200)['artifact']['revision'] == 1
    data = agenda.client.get(BASE).json()
    assert len(data['history']) == 2 and data['current']['IMMEDIATE']['revision'] == 2
    assert count(agenda, PlanningAuditArtifactRow) == 2

def test_next_morning_is_separate_and_uses_the_athletes_local_day(agenda):
    post(agenda, body())
    post(agenda, body(110002, timing='NEXT_MORNING', observed_at='2026-10-24T05:00:00Z'))
    data = agenda.client.get(BASE).json()
    assert data['current']['NEXT_MORNING']['revision'] == 1
    assert data['current']['IMMEDIATE']['revision'] == 1
    post(agenda, body(110003, timing='NEXT_MORNING'), 409)
    post(agenda, body(110004, observed_at='2099-01-01T00:00:00Z'), 409)
    post(agenda, body(110005, observed_at='2026-10-23T15:00:00Z'), 409)

@pytest.mark.parametrize('changes', [
    {'rpe': True}, {'rpe': '5'}, {'rpe': -1}, {'rpe': 11}, {'rpe': float('inf')},
    {'expected_revision': True}, {'observed_at': '2026-10-23T17:00:00'},
    {'comment': 'a'*2001}, {'timing': 'FOLLOW_UP'}, {'extra': 1},
    {'rpe': None, 'fatigue': None, 'energy': None},
])
def test_schema_rejects_invalid_or_empty_answers(changes):
    with pytest.raises(ValueError):
        FeedbackInput.model_validate(body(**changes))

def test_foreign_session_read_and_write_are_not_found(agenda):
    path = f'/api/v1/planning/calendar/sessions/{UUID(int=702099)}/feedback'
    assert agenda.client.get(path).status_code == 404
    post(agenda, body(), 404, path)
    assert count(agenda, PlanningAuditArtifactRow) == 0

def test_failed_commit_never_reports_success_or_leaves_a_revision(agenda, monkeypatch):
    async def fail(session):
        raise RuntimeError('synthetic commit failure')
    monkeypatch.setattr(service.setup, 'commit', fail)
    post(agenda, body(), 503)
    assert count(agenda, PlanningAuditArtifactRow) == 0


def test_synthetic_frontend_contract_fixture(agenda, monkeypatch):
    import os, json
    from pathlib import Path
    monkeypatch.setattr(service, '_now', lambda: datetime(2026,10,28,12,tzinfo=UTC))
    first = post(agenda, body(rpe=5.5, comment='Őszinte <script>szöveg</script>'))
    next_day = post(agenda, body(110002, timing='NEXT_MORNING', observed_at='2026-10-24T06:00:00Z', energy=None))
    current = agenda.client.get(BASE).json()
    out = os.environ.get('P24C11_FIXTURE')
    if out:
        Path(out).write_text(json.dumps({'owner':first['artifact']['athlete_id'], 'session':ACTUAL,
            'receipt':first, 'next_receipt':next_day, 'context':current}, ensure_ascii=False, indent=2)+'\n')
    assert current['current']['IMMEDIATE']['proposal']['rpe'] == 5.5


def test_commit_acknowledgement_loss_is_resolved_by_the_same_request(agenda, monkeypatch):
    commit = service.setup.commit
    async def commit_then_fail(session):
        await commit(session)
        raise RuntimeError('Synthetic lost commit acknowledgement')
    with monkeypatch.context() as scoped:
        scoped.setattr(service.setup, 'commit', commit_then_fail)
        post(agenda, body(), 503)
    assert count(agenda, PlanningAuditArtifactRow) == 1
    assert post(agenda, body(), 200)['reused'] is True
    assert count(agenda, PlanningAuditArtifactRow) == 1


def test_request_identity_cannot_be_reused_for_another_owned_session(agenda):
    from app.models.entities import Sport
    other = str(UUID(int=702002))
    with Session(agenda.engine) as db:
        source = db.get(WorkoutSession, UUID(ACTUAL))
        db.add(WorkoutSession(id=UUID(other), user_id=source.user_id, external_provider='TEST',
            external_id='another-owned', sport=Sport.KAYAK, started_at=source.started_at, ended_at=source.ended_at))
        db.commit()
    post(agenda, body())
    post(agenda, body(), 409, f'/api/v1/planning/calendar/sessions/{other}/feedback')
    assert count(agenda, PlanningAuditArtifactRow) == 1
