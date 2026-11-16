"""Windows code pages must not invalidate a valid, accepted prescription."""
from copy import deepcopy
import json
import os
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import PlannedWorkout
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from app.services import training_instructions as instructions
from tests.planning.test_c21_10_9_profile_sources import env, configure, full, initial_context
from tests.planning.test_c21_10_7_calendar_cycles import get
from tests.planning.test_c21_10_10_workout_instructions import stats
from tests.planning.test_p2_4c18_4_training_plan import accept


def export(name, value):
    if os.getenv('C21_10_12_EXPORT'):
        path = Path(os.environ['C21_10_12_EXPORT'])
        values = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        values[name] = value
        path.write_text(json.dumps(values), encoding='utf-8')


def test_library_uses_utf8_even_when_windows_default_is_cp1250(monkeypatch):
    original = Path.read_text
    requested = []
    def windows_read(path, *args, **kwargs):
        if path == instructions.LIBRARY_FILE:
            requested.append(kwargs.get('encoding'))
            kwargs.setdefault('encoding', 'cp1250')
        return original(path, *args, **kwargs)
    instructions.library.cache_clear()
    try:
        with monkeypatch.context() as patch:
            patch.setattr(Path, 'read_text', windows_read)
            value = instructions.library()
        assert requested == ['utf-8']
        assert value['sports']['STRENGTH']['easy'] == 'Könnyű séta vagy helyben lépkedés'
        web = Path(__file__).resolve().parents[4] / 'apps/web/src/lib/planning-cycles/training-routines.v0.1.json'
        assert value == json.loads(web.read_text(encoding='utf-8'))
    finally:
        instructions.library.cache_clear()


@pytest.mark.parametrize('encoding', ['cp1250', 'cp1252'])
def test_accepted_windows_plan_reads_correctly_without_changing_its_source(env, monkeypatch, encoding):
    configure(env)
    assessment = initial_context(env)['saved']['artifact']
    old_library = json.loads(instructions.LIBRARY_FILE.read_bytes().decode(encoding))
    assert old_library != instructions.library()
    with monkeypatch.context() as patch:
        patch.setattr(instructions, 'library', lambda: old_library)
        old_review = full(env)
        accept(env, old_review, token=21112001)
        old_feed = get(env, path='feed')
    with Session(env.engine) as db:
        sources = {str(row.artifact_id): row.contract_json for row in db.scalars(select(PlanningAuditArtifactRow))}
        workouts = {str(row.id): deepcopy(row.raw_data) for row in db.scalars(select(PlannedWorkout))}
    before = stats(env)
    feed = get(env, path='feed')
    assert stats(env) == before
    for row in feed['planned']:
        key = row['planning_context']['candidate_key']
        c = next(c for c in old_review['result']['create'] if c['candidate_key'] == key)
        meta = old_review['result']['prescription_context']['by_candidate'][key]
        value = row['planning_context']['instructions']
        assert value == instructions.derive(c, meta)
        assert value['main'] == old_review['result']['instruction_context']['by_candidate'][key]['main']
        assert value['duration_sec'] == c['duration_sec']
    with Session(env.engine) as db:
        assert {str(row.artifact_id): row.contract_json for row in db.scalars(select(PlanningAuditArtifactRow))} == sources
        assert {str(row.id): row.raw_data for row in db.scalars(select(PlannedWorkout))} == workouts
    assert initial_context(env)['saved']['artifact'] == assessment
    again = full(env)
    assert not again['result']['create'] and not again['result']['cancel']
    export(encoding, {'legacy_review': old_review, 'legacy_feed': old_feed, 'feed': feed, 'current_review': again})


@pytest.mark.parametrize('sport', ['STRENGTH', 'RUNNING', 'SWIMMING', 'KAYAK'])
def test_known_encoding_compatibility_never_repairs_changed_work_or_arbitrary_text(sport):
    candidate = {'sport': sport, 'duration_sec': 1200, 'description': 'Eredeti saját előírás',
        'blocks': [{'duration_sec': 300}, {'duration_sec': 600}, {'duration_sec': 300}]}
    for old in instructions._legacy_libraries():
        stored = instructions._derive(candidate, {}, old)
        assert instructions.matches_stored(stored, candidate, {})
        changed = deepcopy(stored)
        changed['main']['instruction'] += ' átírva'
        assert not instructions.matches_stored(changed, candidate, {})
        changed = deepcopy(stored)
        changed['warmup']['steps'][1]['instruction'] += ' új gyakorlat'
        assert not instructions.matches_stored(changed, candidate, {})
        changed = deepcopy(stored)
        changed['duration_sec'] += 60
        assert not instructions.matches_stored(changed, candidate, {})
        changed = deepcopy(stored)
        changed['main']['strength'] = {'invented_weight': 100}
        assert not instructions.matches_stored(changed, candidate, {})
