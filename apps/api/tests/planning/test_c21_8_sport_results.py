"""Typed historical results remain separate from recent calibrated strength sets."""
from copy import deepcopy
from uuid import UUID
import pytest
from app.schemas.athlete_setup import SportPerformance
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from tests.planning.test_p2_4c5r2_athlete_setup import intake, profile, post, get
from tests.planning.test_p2_4c3_goal_workflow_api import count


def result(protocol='strength_1rm',token=218001):
    common=dict(result_id=str(UUID(int=token)),kind='personal_best',recorded_on=None,year=2000,conditions='Saját korábbi adat',source='self_report')
    if protocol=='legacy':return dict(common,distance_m='500.000',time='1:42.500')
    if protocol=='cooper_12min':return dict(common,protocol=protocol,distance_m='2800.50',time='12:00')
    if protocol=='strength_1rm':return dict(common,protocol=protocol,exercise='Fekvenyomás rúddal',repetitions=1,load_kind='external_kg',load_kg='100.500',load_basis='total_external')
    return dict(common,protocol=protocol,exercise='Húzódzkodás, szigorú',repetitions=0,load_kind='bodyweight',**({'time':'1:00'} if protocol=='timed_repetitions' else {}))


@pytest.mark.parametrize('protocol',['legacy','cooper_12min','strength_1rm','repetitions','timed_repetitions'])
def test_actual_profile_persists_each_result_type_with_exact_values_and_no_invented_fields(intake,protocol):
    row=result(protocol);p=profile(218002);p['data']['sport_history'][0]['performances']=[row]
    saved=post(intake,'profiles',p)['artifact']
    assert saved['proposal']['data']['sport_history'][0]['performances']==[row]
    assert get(intake,'profiles/'+saved['artifact_id'])['artifact']==saved
    assert post(intake,'profiles',p,200)['artifact']==saved
    assert count(intake,PlanningAuditArtifactRow)==1
    assert not saved['planning_authorized']
    assert get(intake,'context')['profile']['artifact']['proposal']['data']['manual_observations']==[]


def test_old_profile_receipt_and_retry_stay_exact_after_new_strength_result_is_added(intake):
    p=profile(218010);p['data']['sport_history'][0]['performances']=[result('legacy')]
    old=post(intake,'profiles',p)['artifact']
    changed=profile(218011,old);changed['data']['sport_history'][0]['performances']=[result('legacy'),result('repetitions',218012)]
    post(intake,'profiles',changed)
    assert post(intake,'profiles',p,200)['artifact']==old
    assert get(intake,'profiles/'+old['artifact_id'])['artifact']==old


@pytest.mark.parametrize('protocol,patch',[
 ('cooper_12min',dict(time='11:59')),('cooper_12min',dict(distance_m='0')),
 ('cooper_12min',dict(repetitions=10)),('strength_1rm',dict(repetitions=2)),
 ('strength_1rm',dict(load_kg='0')),('strength_1rm',dict(load_basis=None)),
 ('repetitions',dict(repetitions=True)),('repetitions',dict(repetitions=1.5)),
 ('repetitions',dict(repetitions=None)),('repetitions',dict(repetitions=-1)),
 ('repetitions',dict(load_kg='0')),('repetitions',dict(time='1:00')),
 ('timed_repetitions',dict(time=None)),('timed_repetitions',dict(time='0:00')),
 ('timed_repetitions',dict(exercise='')),('legacy',dict(protocol='future_protocol')),
])
def test_ambiguous_result_never_creates_a_profile(intake,protocol,patch):
    p=profile(218020);p['data']['sport_history'][0]['performances']=[{**result(protocol),**patch}]
    post(intake,'profiles',p,422)
    assert count(intake,PlanningAuditArtifactRow)==0


def test_loaded_repetition_result_retains_explicit_total_or_added_load():
    r=result('timed_repetitions');r.update(load_kind='external_kg',load_kg='10.750',load_basis='additional_to_bodyweight',repetitions=15)
    assert SportPerformance.model_validate(r).model_dump()==r
    assert SportPerformance.model_validate(result('legacy')).model_dump()==result('legacy')
