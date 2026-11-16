"""Owned availability declarations bridge catalogue gaps without inventing equipment or sets."""
from copy import deepcopy
from uuid import UUID

import pytest

from app.models.entities import PlannedWorkout
from app.planning.domain.athlete_setup import digest
from app.schemas.training_options import OptionsInput
from app.services import initial_assessment as intake
from app.services import strength_catalog as catalog
from tests.planning.test_p2_4c3_goal_workflow_api import OTHER_EMAIL, count
from tests.planning.test_p2_4c18_4_training_plan import accept, review
from tests.planning.test_p2_4c19_training_options import HOME, WATER
from tests.planning.test_p2_4c19_training_options import body as options_body
from tests.planning.test_p2_4c19_training_options import context as options_context
from tests.planning.test_p2_4c19_training_options import save as save_options
from tests.planning.test_p2_4c20_4_initial_assessment import context as initial_context
from tests.planning.test_p2_4c20_4_initial_assessment import save as save_initial
from tests.planning.test_p2_4c20_5_assessed_strength import request as initial_request
from tests.planning.test_p2_4c20_5_assessed_strength import strength_candidates
from tests.planning.test_p2_4c20_6_guided_strength import context, measured, send, start_request
from tests.planning.test_p2_4c20_6_guided_strength import guided as guided_fixture


def confirmation(exercise='barbell_benchpress', note='Saját fekvenyomó pad, rúd és súlytárcsák'):
    return {'exercise_id':exercise,'source_kind':'self_report','note':note}


@pytest.fixture
def venue(tmp_path, monkeypatch):
    wrapper=guided_fixture.__wrapped__(tmp_path,monkeypatch)
    env=next(wrapper)
    try:
        env.legacy_options=deepcopy(env.options)
        p=options_body(206701,intake.reference(env.options['artifact']))
        p['data']['locations'][0].update(sports=['STRENGTH'],resources=[],exercise_confirmations=[confirmation(),confirmation('squat','Saját testsúlyos guggoláshoz van hely')])
        env.options_request=deepcopy(p)
        env.options=save_options(env,p)
        p=initial_request(env,206702)
        p['data'].update(experience='none',strength_frequency='none',last_strength_date=None)
        p['data']['exercises']=[p['data']['exercises'][1],p['data']['exercises'][2]]
        for e,exercise in zip(p['data']['exercises'],['barbell_benchpress','squat'],strict=True):
            e.update(exercise_id=exercise,sets=[],performed_on=None)
        env.initial=save_initial(env,p)
        yield env
    finally:
        wrapper.close()


@pytest.mark.parametrize('resources,expected',[
    (['Fekvenyomó pad','Súlyzórúd','Súlytárcsák'],True),
    (['Fekvenyomópad','Súlyzórúd','Súlytárcsák'],True),
    (['Fekvenyomó pad rúdtartóval'],False),
    (['Vízszintes edzőpad','Súlyzórúd','Súlytárcsák'],False),
    (['Állítható edzőpad','Erőkeret / guggolókeret','Súlyzórúd','Súlytárcsák','Tárcsarögzítők'],True),
])
def test_explicit_bench_alternatives(resources,expected):
    assert ('barbell_benchpress' in catalog.exercise_ids(resources)) is expected
    assert 'seal_row_barbell' not in catalog.exercise_ids(resources)


def test_old_normalized_options_keep_their_exact_shape(venue):
    old=venue.legacy_options['artifact']['proposal']
    assert all('exercise_confirmations' not in p for p in old['data']['locations'])
    assert OptionsInput.model_validate(old).model_dump(mode='json')==old
    assert venue.legacy_options['artifact']['content_hash']==digest({k:v for k,v in venue.legacy_options['artifact'].items() if k!='content_hash'})


def test_owned_declaration_roundtrips_without_fabricated_equipment_or_references(venue):
    r=save_options(venue,venue.options_request,200)
    assert r['artifact']==venue.options['artifact']
    c=options_context(venue);p=next(p for p in c['data']['locations'] if p['id']==WATER)
    assert p['resources']==[] and p['exercise_confirmations'][0]==confirmation()
    o=next(o for o in c['strength_options'] if o['location_id']==WATER)
    assert o['equipment_ids']==[] and o['equipment_exercise_ids']==[]
    assert set(o['exercise_ids'])==set(o['declared_exercise_ids'])=={'squat','barbell_benchpress'}
    assert c['planning_authorized'] is False
    assert context(venue)['intake']['summary']['recorded_reference_count']==0
    assert all(not e['sets'] for e in initial_context(venue)['data']['exercises'])


def test_real_guided_finish_and_review_and_plan_acceptance_use_the_declaration(venue):
    c=context(venue);assert not c['preparation']['issues']
    assert all(e['ready'] for p in c['preparation']['locations'] if p['location_id']==WATER for e in p['entries'])
    started=send(venue,start_request(c,206703));p=measured(venue,started,206704)
    p['progress']['results'][0]['observations'][0].update(load_basis='total',load_value='25.000000')
    finished=send(venue,p)
    assert finished['assessment_receipt']['artifact']['summary']['recorded_reference_count']==2
    before=count(venue,PlannedWorkout);plan=review(venue);candidates=strength_candidates(plan)
    assert candidates and count(venue,PlannedWorkout)==before
    for c in candidates:
        assert c['location_id']==WATER
        m=next(m for m in c['strength_prescription']['movements'] if m['exercise_id']=='barbell_benchpress')
        assert m['reference_set']['load_value']=='25.000000'
    assert accept(venue,plan)['committed']


def test_location_declaration_never_grants_familiarity_or_another_venue(venue):
    c=context(venue)
    assert catalog.available_exercise_ids(next(p for p in c['intake']['sources']['locations'] if p['id']==HOME))==[]
    p=initial_request(venue,206705);p['data']=deepcopy(c['intake']['data']);p['data']['exercises'][0]['familiarity']='unfamiliar'
    save_initial(venue,p);c=context(venue)
    e=next(e for p in c['preparation']['locations'] for e in p['entries'] if e['exercise_id']=='barbell_benchpress')
    assert not e['ready'] and 'GUIDED_INSTRUCTION_REQUIRED' in e['issues']


def test_removal_changes_sources_without_rewriting_old_receipts(venue):
    old=deepcopy(venue.options);p=deepcopy(venue.options_request)
    p.update(request_id=str(UUID(int=206706)),previous_reference=intake.reference(old['artifact']))
    p['data']['locations'][0]['exercise_confirmations']=[];save_options(venue,p)
    c=context(venue)
    assert c['intake']['sources_changed'] and 'GUIDED_SOURCES_CHANGED' in c['preparation']['issues']
    assert any('GUIDED_EQUIPMENT_MISSING' in e['issues'] for p in c['preparation']['locations'] for e in p['entries'])
    assert save_options(venue,venue.options_request,200)['artifact']==old['artifact']


@pytest.mark.parametrize('case',['duplicate','unknown','authority','bad_source','long_note'])
def test_strict_known_exercise_inputs(venue,case):
    p=deepcopy(venue.options_request)
    p.update(request_id=str(UUID(int=206707)),previous_reference=intake.reference(venue.options['artifact']))
    rows=p['data']['locations'][0]['exercise_confirmations']
    if case=='duplicate': rows.append(deepcopy(rows[0]))
    if case=='unknown': rows[0]['exercise_id']='not_in_catalogue'
    if case=='authority': rows[0]['planning_authorized']=True
    if case=='bad_source': rows[0]['source_kind']='clinically_verified'
    if case=='long_note': rows[0]['note']='x'*501
    save_options(venue,p,422)


def test_request_identity_and_owner_cannot_be_reused_for_other_content(venue):
    p=deepcopy(venue.options_request);p['data']['locations'][0]['exercise_confirmations'][0]['note']='Más beállítás'
    assert save_options(venue,p,409)['detail']['code']=='TRAINING_OPTIONS_REQUEST_CONFLICT'
    venue.email=OTHER_EMAIL
    assert options_context(venue)['data']['locations']==[]
    assert context(venue)['intake']['data'] is None
