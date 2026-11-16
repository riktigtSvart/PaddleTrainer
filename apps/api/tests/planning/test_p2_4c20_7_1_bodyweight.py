"""Released instructions, pending starts and measured bodyweight results remain distinct."""
import json
from copy import deepcopy
from pathlib import Path

import pytest

from app.planning.domain.athlete_setup import digest
from app.services import strength_calibration_domain as calibration
from tests.planning.test_p2_4c20_6_guided_strength import guided, context, send, start_request
from tests.planning.test_p2_4c20_7_calibration import finish


def old_bank():
    path = Path(calibration.__file__).with_name('strength_calibration_protocols_v0_3.json')
    value = json.loads(path.read_text(encoding='utf-8'))
    return {**value, 'content_hash': digest(value)}


def test_bodyweight_observation_has_no_load_search_target_and_other_cards_are_unchanged():
    old = old_bank()
    current = calibration.protocols()
    before = {v['exercise_id']: v for v in old['entries']}
    changed = [v for v in current['entries'] if v != before[v['exercise_id']]]
    assert len(changed) == 19 and all(v['family'] == 'bodyweight_repetitions' for v in changed)
    assert all(v['planned_measurement']['target_repetitions'] is None for v in changed)
    assert all(v['planned_measurement']['repetition_cap'] == 12 and v['planned_measurement']['target_rir'] == 2 for v in changed)
    assert calibration.protocols(old['content_hash']) == old
    with pytest.raises(ValueError, match='CALIBRATION_PROTOCOL_CHANGED'):
        calibration.protocols('f' * 64)


@pytest.mark.parametrize('legacy', [False, True])
@pytest.mark.parametrize('mode', ['calibration', 'repeatability'])
def test_reviewed_bank_is_frozen_through_start_finish_retry_and_context(guided, legacy, mode):
    c = context(guided)
    bank = old_bank() if legacy else c['calibration_protocols']
    p = start_request(c, 2071010)
    p.update(protocol_version='strength-calibration-v0.3', protocol_hash=bank['content_hash'], measurement_mode=mode)
    p['progress']['protocol_version'] = p['protocol_version']
    before = deepcopy(p)
    started = send(guided, p)
    snapshot = started['artifact']['measurement_protocols']
    assert p == before and snapshot['protocol_hash'] == bank['content_hash']
    bodyweight = next(v['protocol'] for v in snapshot['entries'] if v['protocol']['family'] == 'bodyweight_repetitions')
    if mode == 'repeatability':
        assert bodyweight['steps'] == bank['repeatability'].get('bodyweight_steps', bank['repeatability']['steps'])
    else:
        assert bodyweight == next(v for v in bank['entries'] if v['exercise_id'] == bodyweight['exercise_id'])
    completed = finish(guided, started, token=2071011, repetitions=12, rir='5_plus', stop_reason='planned_cap')
    if mode == 'repeatability':
        for row in completed['progress']['results']:
            for value in row['observations']:
                value['purpose'] = 'repeatability'
    result = send(guided, completed)
    actual = result['artifact']['proposal']['progress']['results'][1]['observations'][0]
    assert actual['load_kind'] == 'bodyweight' and actual['load_value'] is None and actual['repetitions'] == 12
    assert actual['rir'] == '5_plus' and actual['stop_reason'] == 'planned_cap'
    assert result['base']['measurement_protocols'] == snapshot
    assert send(guided, completed, 200)['artifact'] == result['artifact']
    assert context(guided)['latest']['base']['measurement_protocols'] == snapshot


def test_unknown_protocol_bank_is_rejected_before_an_occasion_is_created(guided):
    c = context(guided)
    p = start_request(c, 2071020)
    p.update(protocol_version='strength-calibration-v0.3', protocol_hash='f' * 64, measurement_mode='calibration')
    p['progress']['protocol_version'] = p['protocol_version']
    assert send(guided, p, 409)['detail']['code'] == 'CALIBRATION_PROTOCOL_CHANGED'
    assert context(guided)['latest'] is None
