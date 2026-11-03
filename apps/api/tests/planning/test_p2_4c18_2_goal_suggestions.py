"""Declared intent → review matrix → existing durable goal writer → planner inputs."""
from copy import deepcopy
import pytest
from app.services.planning_goal_suggestions import _declared as build  # C18.2 vocabulary layer remains separately testable
from app.planning.domain.common.serialization import compute_content_hash
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from tests.planning.test_p2_4c18_planning_inputs import inputs, get, macro_goals
from tests.planning.test_p2_4c3_goal_workflow_api import count, OTHER_EMAIL


def test_owned_http_suggestions_are_read_only_and_covered_by_capture_hash(inputs):
    before=count(inputs,PlanningAuditArtifactRow)
    data=get(inputs)
    s=data['goal_suggestions'];assert s['review_required'] and not s['committed'] and not s['dose_selected']
    assert s['macrocycles'][0]['rows']==[]  # regular activity is not an invented VO2 prescription
    assert 'regular_activity' in s['macrocycles'][0]['unmapped_goal_keys']
    assert count(inputs,PlanningAuditArtifactRow)==before
    assert compute_content_hash({k:v for k,v in data.items() if k!='content_hash'},exclude_fields=frozenset())==data['content_hash']


def test_current_declared_roles_and_rationales_are_preserved_in_all_children(inputs):
    a=macro_goals(inputs,'permitted_decline');m=get(inputs)['goal_suggestions']['macrocycles'][0]
    assert m['base_reference']=={'artifact_id':a['artifact_id'],'content_hash':a['content_hash']}
    row=m['rows'][0];assert row['role']=='primary_development' and row['rationale']=='explicit'
    assert all(d['role']=='permitted_decline' and d['rationale']=='explicit' and d['origin']=='recorded' for d in row['mesocycle_directives'])
    assert all(not f['selected'] and not f['eligibility_evaluated'] for f in row['family_links'])


def synthetic(inputs, goals=None):
    d=get(inputs);d['declared_goals']=goals or []
    macro=next(p for p in d['periods'] if p['period_type']=='MACROCYCLE')
    d['competitions']=[{'key':'race','status':'planned','start_date':macro['end_date'],'end_date':macro['end_date'],
       'profile':{'capability_basis':'coach_declared','capability_keys':['MAX_STRENGTH','SPRINT_SPEED_AND_START']}}]
    return d


def test_event_profiles_supply_candidates_not_guessed_mesocycle_roles_or_taper(inputs):
    d=synthetic(inputs);before=deepcopy(d);s=build(d);m=s['macrocycles'][0]
    assert d==before
    assert {r['capability_key'] for r in m['rows']}=={'MAX_STRENGTH','SPRINT_SPEED_AND_START'}
    for r in m['rows']:
        assert r['role'] is None and all(v['role'] is None for v in r['mesocycle_directives'])
    sprint=next(r for r in m['rows'] if r['capability_key']=='SPRINT_SPEED_AND_START')
    assert sprint['family_coverage']=='missing' and not sprint['family_links']
    assert s['periodization_inferred'] is False and not s['family_selection_authorized']


@pytest.mark.parametrize('key,direction,role',[('strength','improve','primary_development'),('strength','maintain','maintenance'),('aerobic_fitness','improve','primary_development'),('aerobic_fitness',None,None)])
def test_only_explicit_supported_goal_direction_suggests_macro_role(inputs,key,direction,role):
    d=synthetic(inputs,[{'key':key,'details':{'direction':direction}}]);d['competitions']=[]
    rows=build(d)['macrocycles'][0]['rows'];assert rows
    assert all(r['role']==role for r in rows)
    assert all(v['role'] is None for r in rows for v in r['mesocycle_directives'])


def test_weight_and_mobility_are_not_silently_relabelled_as_strength_or_vo2(inputs):
    d=synthetic(inputs,[{'key':'weight_loss'},{'key':'mobility','details':{'direction':'improve'}}]);d['competitions']=[]
    m=build(d)['macrocycles'][0];assert m['rows']==[];assert set(m['unmapped_goal_keys'])=={'weight_loss','mobility'}


def test_cancelled_outside_and_unprofiled_events_are_distinguishable(inputs):
    d=synthetic(inputs);event=d['competitions'][0];event['profile']['capability_keys']=[];event['profile']['capability_basis']='unassessed'
    m=build(d)['macrocycles'][0];assert m['unprofiled_event_keys']==['race'] and not m['rows']
    event['status']='cancelled';assert not build(d)['macrocycles'][0]['unprofiled_event_keys']
    event['status']='planned';event['start_date']='2030-01-01';event['end_date']='2030-01-02';assert not build(d)['macrocycles'][0]['unprofiled_event_keys']


def test_reviewed_matrix_saves_via_existing_writer_and_appears_in_next_inputs(inputs):
    d=synthetic(inputs,[{'key':'strength','details':{'direction':'improve'}}]);d['competitions']=[]
    m=build(d)['macrocycles'][0];r=m['rows'][0]
    proposal={'macrocycle_period_id':m['macrocycle_period_id'],'revision':1,'supersedes':None,
      'goals':[{'capability_key':r['capability_key'],'role':r['role'],'rationale':r['rationale']}],
      'mesocycle_directives':[{'mesocycle_period_id':v['mesocycle_period_id'],'capability_key':r['capability_key'],'role':'maintenance','rationale':'Reviewed for this mesocycle'} for v in r['mesocycle_directives']],
      'rationale':'Reviewed preparation goals'}
    response=inputs.client.post('/api/v1/planning/goals/macrocycle-plans',json=proposal);assert response.status_code==201,response.text
    reply=response.json();assert reply['committed'] and not reply['planning_authorized']
    data=get(inputs);assert all(day['capability_roles'][0]['role']=='maintenance' for day in data['days'])
    assert data['goal_suggestions']['macrocycles'][0]['base_revision']==1
    assert inputs.client.post('/api/v1/planning/goals/macrocycle-plans',json=proposal).status_code==200


def test_foreign_owner_still_cannot_obtain_suggestions(inputs):
    inputs.email=OTHER_EMAIL;get(inputs,status=404)
