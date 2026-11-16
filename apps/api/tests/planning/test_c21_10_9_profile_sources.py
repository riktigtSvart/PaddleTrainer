"""Live profile updates retain strength observations; meaningful changes stay explicit."""
from copy import deepcopy
import json
import os
from pathlib import Path
from uuid import UUID

import pytest

from app.planning.application import calendar_workspace
from app.planning.domain.athlete_setup import reference
from app.services import initial_assessment
from tests.planning.test_c21_9_1_calendar_endurance import env as source_fixture
from tests.planning.test_c21_10_swimming_load import configure
from tests.planning.test_c21_10_5_goal_coverage import full
from tests.planning.test_c21_10_6_reusable_references import change_options
from tests.planning.test_c21_10_8_strength_and_distribution import new_pool
from tests.planning.test_p2_4c5r2_athlete_setup import post as post_profile, get as get_profile
from tests.planning.test_p2_4c18_4_training_plan import accept
from tests.planning.test_p2_4c20_4_initial_assessment import context as initial_context, save as save_initial
from tests.planning.test_p2_4c20_5_assessed_strength import request
from tests.planning.test_c21_10_7_calendar_cycles import get as calendar_get


@pytest.fixture
def env(tmp_path, monkeypatch):
    wrapper=source_fixture.__wrapped__(tmp_path,monkeypatch)
    e=next(wrapper)
    monkeypatch.setattr(calendar_workspace,'_now',e.clock.tick)
    try:
        yield e
    finally:
        wrapper.close()


def export(name, value):
    if os.getenv('C21_10_9_EXPORT'):
        path=Path(os.environ['C21_10_9_EXPORT'])
        values=json.loads(path.read_text()) if path.exists() else {}
        values[name]=value
        path.write_text(json.dumps(values),encoding='utf-8')


def profile_change(e, change, token=2110901):
    current=full(e)['inputs']['profile']
    data=deepcopy(current['data'])
    change(data)
    return post_profile(e,'profiles',{'request_id':str(UUID(int=token)),
        'previous_reference':{k:current['reference'][k] for k in ('artifact_id','content_hash')},'data':data})


def strength(value):
    return [c for c in value['result']['proposals'] if c['sport']=='STRENGTH']


@pytest.mark.parametrize('field', ['resources','duration_doubling_slowdown_pct','manual_observations','source_window'])
def test_live_profile_fields_do_not_invalidate_actual_strength_references(env,field):
    configure(env)
    before=initial_context(env)
    def change(data):
        if field=='resources':data[field].append('Új általános eszköz')
        elif field=='duration_doubling_slowdown_pct':data[field]=7
        elif field=='source_window':data[field]={'start_date':'2026-09-01','end_date':'2026-10-22'}
        else:data[field]=[{'observation_id':str(UUID(int=2110902)),'metric':'training_minutes','value':'180',
            'start_date':'2026-10-19','end_date':'2026-10-22','method':'self_report','aggregation':'total'}]
    profile_change(env,change)
    after=initial_context(env)
    assert after['reference']==before['reference'] and after['saved']['artifact']==before['saved']['artifact']
    assert after['sources_changed'] is False
    value=full(env)
    context=value['inputs']['strength_assessment']
    assert context['profile_comparison']=={'schema_version':'strength-profile-comparison-v0.1',
        'changed_fields':[field],'blocking_fields':[],'source_reference_changed':False,'reference_reusable':True}
    assert context['current_profile_receipt']['artifact']['proposal']['data']==value['inputs']['profile']['data']
    assert strength(value)
    original={v['id']:v for v in before['data']['exercises']}
    for candidate in strength(value):
        assert candidate['strength_prescription']['assessment_reference']==before['reference']
        for movement in candidate['strength_prescription']['movements']:
            assert movement['reference_set'] in original[movement['entry_id']]['sets']
    export(field,value)


def test_selected_history_sources_and_new_venue_are_independently_verified(env):
    saved=configure(env)
    history=get_profile(env,'history?start_date=2026-10-01&end_date=2026-10-22')
    assert history['items']
    def change(data):
        data['source_window']={'start_date':'2026-10-01','end_date':'2026-10-22'}
        data['source_selections']=[reference(v) for v in history['items']]
    profile_change(env,change)
    change_options(env,saved,2110903,new_pool)
    value=full(env)
    c=value['inputs']['strength_assessment']
    assert c['profile_comparison']['reference_reusable'] is True
    assert c['profile_comparison']['changed_fields']==['source_selections','source_window']
    assert c['source_comparison']['reusable'] is True
    assert strength(value)
    export('selected_sources_and_pool',value)
    accept(env,value,token=2110904)
    again=full(env)
    assert not again['result']['create'] and not again['result']['cancel']
    export('repeated',again)


@pytest.mark.parametrize('field', ['birth_date','sex_reference','participation','interruption','recovery_notes','accessibility_needs','body_mass_kg','height_cm','constraints'])
def test_actual_health_movement_and_body_changes_remain_review_boundaries(env,field):
    configure(env)
    def change(data):
        if field=='birth_date':data[field]='1979-01-01'
        elif field=='sex_reference':data[field]='male' if data[field]!='male' else 'female'
        elif field=='participation':data[field]='paused'
        elif field=='interruption':data[field]='returning'
        elif field=='recovery_notes':data[field]='Új, felülvizsgálandó állapotjelzés'
        elif field=='accessibility_needs':data[field]='Megváltozott mozgássegítési igény'
        elif field=='body_mass_kg':data.update(body_mass_kg='83.5',body_mass_recorded_on='2026-10-22')
        elif field=='height_cm':data.update(height_cm='180',body_measurements_recorded_on='2026-10-22')
        else:data.update(constraint_status='present',constraints=[{'key':'shoulder','duration':'permanent','area':'movement',
            'affected_area':'Váll','restricted_activities':['Fej fölötti nyomás'],'adaptations':'','professional_guidance':'',
            'starts_on':None,'review_on':None}])
    profile_change(env,change)
    assert initial_context(env)['sources_changed'] is True
    value=full(env)
    c=value['inputs']['strength_assessment']
    assert field in c['profile_comparison']['blocking_fields']
    assert c['profile_comparison']['reference_reusable'] is False
    assert not strength(value)
    assert c['profile_source_receipt']['artifact']['proposal']['data']==value['inputs']['profile']['data']
    if field=='recovery_notes':
        cycles=calendar_get(env)
        assert any(row['latest_review']['profile_comparison']['blocking_fields']==['recovery_notes'] for row in cycles['cycles'] if row['latest_review'])
        export('calendar_blocked',cycles)
    export('changed_'+field,value)


def test_intermediate_health_change_is_not_erased_by_a_later_equal_profile(env):
    configure(env)
    profile_change(env,lambda d:d.update(recovery_notes='Átmeneti állapotváltozás'))
    profile_change(env,lambda d:d.update(recovery_notes=''),token=2110905)
    value=full(env)
    comparison=value['inputs']['strength_assessment']['profile_comparison']
    assert not comparison['changed_fields'] and not comparison['blocking_fields']
    assert comparison['source_reference_changed'] and not comparison['reference_reusable']
    assert not strength(value)
    export('reverted_profile',value)


def test_explicit_review_of_changed_profile_reuses_recorded_sets_without_a_new_physical_test(env):
    configure(env)
    before=initial_context(env)['data']
    profile_change(env,lambda d:d.update(recovery_notes='Pontosított állapotmegjegyzés'))
    assert not strength(full(env))
    proposal=request(env,token=2110906)
    assert proposal['data']['exercises']==before['exercises']
    save_initial(env,proposal)
    value=full(env)
    assert strength(value)
    assert value['inputs']['strength_assessment']['profile_comparison']['reference_reusable']
    export('reviewed_profile',value)
