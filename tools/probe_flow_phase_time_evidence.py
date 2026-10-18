"""Loopback GET-only probe of registered Flow execution-time evidence."""
import argparse
import json
from pathlib import Path
import re
import time
from urllib.error import HTTPError

from probe_phase_reconciliation_api import TARGETS, request_json, validate_base, save, archive
from probe_phase_clarification_storage import save_http_error
from app.services.flow_phase_time_evidence_read import (
    RULES_VERSION, CATALOG_VERSION, CATALOG_SHA256, verify_evidence_read,
)


def run_probe(output, base='http://127.0.0.1:8000'):
    base = validate_base(base)
    output = Path(output).resolve()
    if output.exists():
        raise ValueError('FLOW_PROBE_OUTPUT_ALREADY_EXISTS')
    output.mkdir(parents=True)
    started = time.monotonic(); calls = 0; rows = []; stage = 'CAPABILITIES'
    summary = {'status': 'FLOW_TIME_EVIDENCE_READ_PROBE_STOPPED_WITH_SAVED_PROGRESS',
        'rules_version': RULES_VERSION, 'catalog_version': CATALOG_VERSION,
        'requested_session_count': len(TARGETS), 'database_writes': 0, 'provider_calls': 0,
        'user_answers_submitted': 0, 'user_answers_modified': False,
        'actual_phase_alignment_verified': False, 'numeric_prediction_authorized': False,
        'model_trained': False, 'new_independent_model_test': False,
        'output_folder': str(output), 'result_zip': str(output.with_suffix('.zip'))}
    try:
        calls += 1
        caps = request_json(base, '/api/v1/planning/phase-reconciliation/execution-time-evidence-capabilities')
        save(output, 'capabilities.json', caps)
        if caps['rules_version'] != RULES_VERSION or caps['catalog_sha256'] != CATALOG_SHA256:
            raise ValueError('FLOW_PROBE_CATALOG_OR_RULES_VERSION_DIFFERS')
        for i, (day, sid) in enumerate(TARGETS):
            print(f'Flow time evidence {i+1}/{len(TARGETS)}: {day}', flush=True)
            values = []
            for repeat in (1, 2):
                stage = f'SESSION_{i+1}_READ_{repeat}'; calls += 1
                value = request_json(base, f'/api/v1/sessions/{sid}/phase-reconciliation/execution-time-evidence?include_source=true')
                save(output, f'sessions/{i:02}_read_{repeat}.json.gz', value)
                if value['session_id'] != sid:
                    raise ValueError('FLOW_PROBE_SESSION_DIFFERS')
                verify_evidence_read(value)
                if value['status'] != 'FLOW_TIME_EVIDENCE_SUPPORTED_WITH_LIMITATIONS':
                    raise ValueError('FLOW_PROBE_REFERENCE_NOT_SUPPORTED_REVIEW_EXPORTED_RESULT')
                values.append(value)
            a, b = values
            if any(a[k] != b[k] for k in ('reference_evidence_id', 'current_artifact_id', 'latest_user_revision_id', 'result')):
                raise ValueError('FLOW_PROBE_SOURCE_OR_ANSWER_CHANGED_DURING_READS')
            r = b['result']
            if r['pending_questions_without_reference_support'] or r['reference_supported_joint_path_count'] != 1:
                raise ValueError('FLOW_PROBE_REFERENCE_LOCALIZATION_REQUIRES_REVIEW')
            rows.append({'date': day, 'session_id': sid, 'full_source_and_saved_answer_replay_verified': True,
                'reference_evidence_id': b['reference_evidence_id'],
                'phase_count': len(r['phase_times']), 'transition_interval_count': len(r['transition_intervals']),
                'manual_question_evidence_count': len(r['manual_question_evidence']),
                'current_user_question_count_pending': r['current_user_question_count_pending'],
                'reference_supported_pending_question_count': r['reference_supported_pending_question_count'],
                'pending_questions_without_reference_support': r['pending_questions_without_reference_support'],
                'source_time_discrepancy_count': len(r['source_time_discrepancies']),
                'user_answers_modified': False, 'actual_phase_alignment_verified': False})
        summary.update(status='FLOW_TIME_EVIDENCE_READ_AND_FULL_SOURCE_REPLAY_PROBE_PASSED',
            phase_count=sum(r['phase_count'] for r in rows),
            current_user_question_count_pending=sum(r['current_user_question_count_pending'] for r in rows),
            reference_supported_pending_question_count=sum(r['reference_supported_pending_question_count'] for r in rows),
            pending_questions_without_reference_support=sum(r['pending_questions_without_reference_support'] for r in rows),
            source_time_discrepancy_count=sum(r['source_time_discrepancy_count'] for r in rows))
    except Exception as exc:
        summary.update(failed_stage=stage, error_type=type(exc).__name__)
        if isinstance(exc, ValueError) and re.fullmatch('[A-Z0-9_]+', str(exc)):
            summary['error_code'] = str(exc)
        if isinstance(exc, HTTPError):
            summary['http_status'] = exc.code; save_http_error(output, exc)
    finally:
        summary.update(completed_session_count=len(rows), local_api_requests=calls,
                       elapsed_seconds=round(time.monotonic()-started, 3), sessions=rows)
        save(output, 'summary.json', summary); archive(output)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--base', default='http://127.0.0.1:8000')
    args = parser.parse_args(argv)
    result = run_probe(args.output, args.base)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['status'] == 'FLOW_TIME_EVIDENCE_READ_AND_FULL_SOURCE_REPLAY_PROBE_PASSED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
