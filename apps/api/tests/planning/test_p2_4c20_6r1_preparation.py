"""Selection in preparation never bypasses the existing start prerequisites."""
from copy import deepcopy
from uuid import UUID

import pytest

from app.models.entities import WorkoutSession
from tests.planning.test_p2_4c3_goal_workflow_api import count
from tests.planning.test_p2_4c20_4_initial_assessment import save as save_initial
from tests.planning.test_p2_4c20_6_guided_strength import context, send, start_request
from tests.planning.test_p2_4c20_6_guided_strength import guided as guided_fixture


@pytest.fixture(name='guided')
def guided_case(tmp_path, monkeypatch):
    yield from guided_fixture.__wrapped__(tmp_path, monkeypatch)


def revise(env, field, value, token=206601):
    c=context(env)
    data=deepcopy(c['intake']['data'])
    if field=='strength_role':
        next(s for s in data['sports'] if s['sport_key']=='STRENGTH')['role']=value
    else:
        data[field]=value
    return save_initial(env,{'request_id':str(UUID(int=token)), 'previous_reference':c['intake']['reference'],
                            'source_hash':c['intake']['sources']['source_hash'],'data':data})


@pytest.mark.parametrize('field,value,code', [
    ('strength_role','recreation','GUIDED_STRENGTH_ROLE_REQUIRED'),
    ('supervision','needed','GUIDED_HISTORY_OR_SUPERVISION_REVIEW'),
    ('reviewed',False,'GUIDED_INTAKE_REVIEW_REQUIRED'),
    ('state_change','unknown','GUIDED_STATE_REVIEW'),
])
def test_choosing_eligible_exercises_cannot_bypass_a_global_start_requirement(guided, field, value, code):
    revise(guided,field,value)
    c=context(guided)
    assert code in c['preparation']['issues']
    rows=[e for p in c['preparation']['locations'] for e in p['entries'] if not e['issues']]
    assert rows and all(not e['ready'] for e in rows)
    before=count(guided,WorkoutSession)
    assert send(guided,start_request(c),409)['detail']['code']=='GUIDED_PREPARATION_CHANGED'
    assert context(guided)['latest'] is None and count(guided,WorkoutSession)==before
