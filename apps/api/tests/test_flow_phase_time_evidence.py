"""Real archived cases, provenance failures, and source-preserving projections."""
from copy import deepcopy
import gzip
import json
from pathlib import Path

import pytest

from app.planning_contracts.flow_phase_time_evidence import FlowEvidenceError, reference_id, validate_reference
from app.planning_contracts.phase_reconciliation import digest
from app.services import flow_phase_time_evidence_read as service
from app.services import phase_clarification_storage as storage
from app.services.phase_reconciliation_read import build_phase_reconciliation_read
from app.services.plan_contract_read import build_plan_read
from app.planning_contracts.execution_adapter import build_execution_read
from app.services.plan_execution_comparison_read import build_comparison_read
from test_phase_reconciliation_api import recapture

FIXTURES = Path(__file__).resolve().parent/'fixtures/flow_phase_time_evidence'
PRIVATE_FLOW_REPLAY_AVAILABLE = (
    all((FIXTURES/name).is_file() for name in ('00_state.json.gz','01_state.json.gz','02_state.json.gz'))
    and service.CATALOG_PATH.is_file()
)
PRIVATE_FLOW_REPLAY_REASON = 'private real-derived Polar replay fixtures are not installed; synthetic/public regression coverage still runs'
pytestmark = pytest.mark.skipif(
    not PRIVATE_FLOW_REPLAY_AVAILABLE, reason=PRIVATE_FLOW_REPLAY_REASON
)


def case(index):
    state = json.loads(gzip.decompress((FIXTURES/f'{index:02}_state.json.gz').read_bytes()))
    path = FIXTURES/f'{index:02}_archive.json.gz'
    archive = json.loads(gzip.decompress(path.read_bytes())) if path.exists() else None
    reference = deepcopy(service.load_catalog()['records'][index])
    return state, archive, reference


def seal(value):
    value['evidence_id'] = reference_id(value)
    return value


@pytest.mark.parametrize('index,phases,transitions', [(0,7,2),(1,10,2),(2,7,3)])
def test_archived_cases_replay_and_support_all_remaining_questions(index, phases, transitions):
    state, archive, reference = case(index); before = digest(state)
    value = service.build_evidence_read(state, archive, reference, include_source=True)
    assert service.verify_evidence_read(value)
    r = value['result']
    assert value['status'] == 'FLOW_TIME_EVIDENCE_SUPPORTED_WITH_LIMITATIONS'
    assert len(r['phase_times']) == phases and len(r['transition_intervals']) == transitions
    assert r['current_user_question_count_pending'] == r['reference_supported_pending_question_count'] == 1
    assert r['pending_questions_without_reference_support'] == 0
    assert r['reference_supported_joint_path_count'] == 1 and digest(state) == before
    assert not value['actual_phase_alignment_verified'] and not r['training_authorized']
    assert r['source_samples_discarded'] == 0 and not value['user_answers_modified']
    assert r['source_available_at_utc'] is None and not r['pre_exercise_use_authorized']


def test_ten_second_source_discrepancy_is_retained_without_clock_correction():
    value = service.build_evidence_read(*case(2), include_source=True)
    d, = value['result']['source_time_discrepancies']
    assert (d['reported_time_s'], d['flow_derived_start_s'], d['raw_display_difference_s']) == (1281,1271,10)
    assert not d['automatic_clock_or_gps_correction_applied']
    assert value['source_state']['saved_answers_status'] == 'APPLIED'
    assert all(q['status'] == 'REFERENCE_SUPPORTED_CANDIDATE_RANGE' for q in value['result']['manual_question_evidence'])


def test_one_second_boundaries_are_not_promoted_to_manual_waits():
    values = [service.build_evidence_read(*case(i)) for i in (1,2)]
    gaps = [g for v in values for g in v['result']['transition_intervals']]
    assert sum(g['kind'] == 'DISPLAY_PRECISION_OR_BOUNDARY_POLICY_UNRESOLVED' for g in gaps) == 2
    assert all(not g['discard_source_samples'] and not g['whole_recording_pause_verified'] for g in gaps)


def test_large_august_suffix_and_unobserved_prefix_remain_explicit():
    v = service.build_evidence_read(*case(2))['result']
    suffix = v['preserved_source_suffix']
    assert suffix['after_reference_elapsed_s'] == 3042
    assert all(3483-x['observed_suffix_start_index_candidate'] >= 441 for x in suffix['native_views'])
    assert not suffix['discard_source_samples']
    assert any(x['has_unobserved_prefix'] for x in v['phase_times'][0]['native_views'])


def test_fresh_capture_changes_audit_capture_but_keeps_evidence_result():
    state, archive, reference = case(0)
    baseline = state['effective_reconciliation']
    fresh = recapture(baseline['source_comparison_read'], '2026-10-17T22:00:00+00:00')
    current = build_phase_reconciliation_read(fresh, include_source=True)
    latest = storage.archived_row_from_response(archive)
    new_state = storage.build_saved_state(current, latest, include_source=True)
    a = service.build_evidence_read(state, archive, reference, include_source=True)
    b = service.build_evidence_read(new_state, archive, reference, include_source=True)
    assert a['source_state_sha256'] != b['source_state_sha256']
    assert a['source_plan_capture_id'] != b['source_plan_capture_id']
    assert a['source_capture_occurrence_mapping'] != b['source_capture_occurrence_mapping']
    assert a['result'] == b['result'] and service.verify_evidence_read(b)


def test_compact_evidence_can_join_every_phase_to_its_captured_plan_occurrence():
    value = service.build_evidence_read(*case(1))
    mapping = value['source_capture_occurrence_mapping']
    joined = {item['stable_source_occurrence_id']: item for item in mapping}
    assert len(joined) == len(mapping) == len(value['result']['phase_times']) == 10
    for phase in value['result']['phase_times']:
        item = joined[phase['stable_source_occurrence_id']]
        assert item['source_pointer'] == phase['source_pointer']
        assert item['captured_contract_occurrence_id'].startswith('occ_')
    assert value['source_state'] is None and value['source_execution_capture_id']


@pytest.mark.parametrize('field', ['athlete_id','session_id'])
def test_reference_never_crosses_owner_or_session(field):
    state, archive, reference = case(1)
    reference[field] = '00000000-0000-0000-0000-000000008802'; seal(reference)
    with pytest.raises(FlowEvidenceError, match='OWNER_SESSION_DIFFERS'):
        service.build_evidence_read(state, archive, reference)


@pytest.mark.parametrize('change', ['SOURCE','PLAN'])
def test_changed_source_or_plan_keeps_reference_for_review_without_application(change):
    state, _, reference = case(1)
    er = state['effective_reconciliation']['source_comparison_read']['source_execution_read']
    source, snapshot = deepcopy(er['source_snapshot']), deepcopy(er['plan_capture']['source_snapshot'])
    if change == 'SOURCE': source['raw_data']['name'] = 'source changed'
    else: snapshot['raw_data']['session']['name'] = 'plan changed'
    plan = build_plan_read(snapshot)
    execution = build_execution_read(source, plan_read=plan, plan_selection=er['plan_selection'], source_mode=er['source_mode'])
    comparison = build_comparison_read(execution, include_source=True, include_bundle=True)
    fresh = build_phase_reconciliation_read(comparison, include_source=True)
    current = storage.build_saved_state(fresh, include_source=True)
    value = service.build_evidence_read(current, None, reference, include_source=True)
    assert value['status'] == 'FLOW_REFERENCE_RECHECK_REQUIRED'
    assert value['result']['phase_times'] == [] and not value['result']['reference_counts_as_user_answer']
    assert service.verify_evidence_read(value)


@pytest.mark.parametrize('change', ['unknown','hash','negative','bool','time_offset','overlap'])
def test_invalid_reference_is_rejected(change):
    reference = case(0)[2]
    if change == 'unknown': reference['training_authorized'] = True
    if change == 'hash': reference['images'][0]['sha256'] = '0'*64
    if change == 'negative': reference['phases'][0]['duration_s'] = -1; seal(reference)
    if change == 'bool': reference['phases'][0]['duration_s'] = True; seal(reference)
    if change == 'time_offset': reference['user_reports'][0]['reported_at'] = '2026-10-17T10:00:00'; seal(reference)
    if change == 'overlap': reference['phases'][1]['cumulative_end_s'] = 600; seal(reference)
    with pytest.raises(FlowEvidenceError): validate_reference(reference)


def test_gap_after_automatic_phase_is_a_source_sequence_conflict():
    state, archive, reference = case(0)
    for phase in reference['phases'][5:]: phase['cumulative_end_s'] += 4
    seal(reference)
    with pytest.raises(FlowEvidenceError, match='GAP_AFTER_AUTOMATIC_PHASE'):
        service.build_evidence_read(state, archive, reference)


def test_compact_view_cannot_claim_a_full_replay():
    value = service.build_evidence_read(*case(1))
    assert value['source_state'] is value['reference_record'] is None
    with pytest.raises(FlowEvidenceError, match='FULL_SOURCE_REQUIRED'):
        service.verify_evidence_read(value)


def test_modified_result_cannot_pass_full_replay():
    value = service.build_evidence_read(*case(1), include_source=True)
    value['result']['phase_times'][0]['reference_end_s'] += 1
    with pytest.raises(FlowEvidenceError, match='FULL_SOURCE_REPLAY_DIFFERS'):
        service.verify_evidence_read(value)


def test_missing_reference_does_not_guess_or_disclose_catalog_records():
    state, archive, _ = case(1)
    value = service.build_evidence_read(state, archive, None, include_source=True)
    assert value['status'] == 'NO_REGISTERED_FLOW_REFERENCE'
    assert value['reference_record'] is None and value['result']['phase_times'] == []
    assert service.verify_evidence_read(value)


def test_catalog_change_requires_503_instead_of_loading_unreviewed_data(tmp_path, monkeypatch):
    path = tmp_path/'catalog.json'; path.write_bytes(service.CATALOG_PATH.read_bytes()+b' ')
    monkeypatch.setattr(service, 'CATALOG_PATH', path)
    with pytest.raises(FlowEvidenceError, match='CATALOG_HASH_DIFFERS') as exc:
        service.load_catalog()
    assert exc.value.status_code == 503


def test_response_budget_is_enforced(monkeypatch):
    monkeypatch.setattr(service, 'MAX_RESPONSE_BYTES', 100)
    with pytest.raises(FlowEvidenceError, match='RESPONSE_SIZE_LIMIT') as exc:
        service.build_evidence_read(*case(1), include_source=True)
    assert exc.value.status_code == 413
