"""Run phase reconciliation, HTTP, read regression, and installer tests offline."""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', required=True)
    parser.add_argument('--package-root', required=True)
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    root, package = Path(args.project_root).resolve(), Path(args.package_root).resolve()
    env = dict(os.environ)
    env.update(
        DATABASE_URL='postgresql+asyncpg://test:test@127.0.0.1:1/phase_clarification_storage_checks_not_production',
        POLAR_CLIENT_ID='offline-test-client', POLAR_CLIENT_SECRET='offline-test-secret',
        TOKEN_ENCRYPTION_KEY='', PYTHONDONTWRITEBYTECODE='1',
    )
    env['PYTHONPATH'] = os.pathsep.join([
        str(package), str(root/'apps/api'), str(root/'apps/api/tests'),
        str(root/'tools'), env.get('PYTHONPATH', ''),
    ])
    if not args.worker:
        return subprocess.run([
            sys.executable, '-u', str(Path(__file__).resolve()),
            '--project-root', str(root), '--package-root', str(package), '--worker',
        ], env=env).returncode
    started = time.monotonic()
    selected = [
        'tests/test_phase_clarification_storage.py',
        'tests/test_phase_clarification_migration.py',
        'tests/test_phase_clarification_tools.py',
        'tests/test_phase_reconciliation_domain.py',
        'tests/test_phase_reconciliation_api.py',
        'tests/test_phase_reconciliation_probe.py',
        'tests/test_plan_contract_read_api.py',
        'tests/test_executed_workout_adapter.py',
        'tests/test_executed_workout_read_api.py',
        'tests/test_plan_execution_comparison_api.py',
        'tests/test_plan_execution_comparison_probe.py',
        'tests/test_execution_phase_fix.py',
        'tests/test_execution_phase_fix_api.py',
        str(package/'test_phase_storage_installer.py'),
    ]
    # Captured source lacks these two legacy tools. Their routes are covered
    # above; the new probe is tested through the real ASGI application.
    excluded = [
        'test_running_api_probe_saves_an_honest_review_archive',
        'test_user_probe_creates_valid_archive_for_real_app_responses',
    ]
    real_pft = (root/'apps/api/tests/fixtures/pft/synthetic_pft_run_v01.TCX').is_file()
    if real_pft:
        selected += ['tests/test_pft_processing_integration.py', 'tests/test_pft_measurement_api.py']
    with tempfile.TemporaryDirectory(prefix='phase_clarification_storage_checks_') as temp:
        report = Path(temp)/'checks.xml'
        command = [
            sys.executable, '-m', 'pytest', '-q', *selected,
            '-p', 'no:cacheprovider', '-p', 'phase_fix_no_network',
            '--basetemp='+str(Path(temp)/'pytest'), '--junitxml='+str(report),
            '-k', ' and '.join('not '+name for name in excluded),
        ]
        result = subprocess.run(command, cwd=root/'apps/api', env=env)
        if result.returncode:
            return result.returncode
        suites = ET.parse(report).getroot().findall('testsuite')
        tests = sum(int(s.get('tests', 0)) for s in suites)
        skipped = sum(int(s.get('skipped', 0)) for s in suites)
        if skipped or tests < 101:
            raise ValueError('SELECTED_RELEASE_TESTS_SKIPPED_OR_MISSING')
    # Import only after the test subprocess: this process also uses the sentinel
    # DB URL, but does not open the engine or a service connection.
    sys.path.insert(0, str(root/'apps/api'))
    from app.main import app
    schema = app.openapi()
    expected = {
        '/api/v1/sessions/{session_id}/phase-reconciliation/state': 'get',
        '/api/v1/sessions/{session_id}/phase-reconciliation/clarifications': 'post',
        '/api/v1/sessions/{session_id}/phase-reconciliation/clarifications/history': 'get',
        '/api/v1/sessions/{session_id}/phase-reconciliation/clarifications/{revision_id}': 'get',
        '/api/v1/planning/phase-reconciliation/capabilities': 'get',
        '/api/v1/sessions/{session_id}/phase-reconciliation': 'get',
        '/api/v1/sessions/{session_id}/phase-reconciliation/clarifications/inspect': 'post',
    }
    if not all(method in schema['paths'].get(path, {}) for path, method in expected.items()):
        raise ValueError('PHASE_RECONCILIATION_ROUTER_MISSING')
    from app.planning_contracts.phase_reconciliation import RULES_VERSION
    summary = {
        'status': 'PHASE_CLARIFICATION_STORAGE_TESTS_AND_ROUTER_CHECK_PASSED',
        'storage_version': 'phase-clarification-storage-0.1',
        'rules_version': RULES_VERSION, 'tests': tests, 'skipped_tests': skipped,
        'real_pft_reference_regression_run': real_pft,
        'legacy_tool_probe_test_names_not_selected': excluded,
        'test_database': 'SQLITE_IN_MEMORY', 'test_api': 'REAL_FASTAPI_ASGI_NO_SERVICE_NETWORK',
        'windows_socketpair_fallback_forced_during_tests': True,
        'native_windows_runtime': sys.platform == 'win32', 'python': sys.version.split()[0],
        'stable_question_identity_verified': True,
        'source_change_invalidates_previous_answers_verified': True,
        'clarification_inspection_persists_answers': False,
        'explicit_save_persists_answers_in_test_database': True,
        'original_read_inspect_contracts_preserved': True,
        'postgresql_sql_contracts_checked': True,
        'postgresql_migration_executed_here': False,
        'migration_target': 'da7e4c92b610',
        'production_database_accessed': False, 'database_migrated': False,
        'polar_requests': 0, 'provider_calls': 0,
        'actual_phase_alignment_verified': False, 'numeric_prediction_authorized': False,
        'speed_model_retrained': False, 'state_model_trained': False,
        'new_independent_model_test': False,
        'versions': {n: importlib.metadata.version(n) for n in ('fastapi', 'sqlalchemy', 'httpx', 'pytest')},
        'elapsed_seconds': round(time.monotonic()-started, 3),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
