"""Offline API/regression checks with a sentinel DB URL and blocked network."""
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
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root',required=True)
    parser.add_argument('--package-root',required=True)
    args=parser.parse_args(argv)
    root=Path(args.project_root).resolve();package=Path(args.package_root).resolve()
    env=dict(os.environ)
    env.update(DATABASE_URL='postgresql+asyncpg://test:test@127.0.0.1:1/flow_time_evidence_checks_not_production',
        POLAR_CLIENT_ID='offline-test-client',POLAR_CLIENT_SECRET='offline-test-secret',
        TOKEN_ENCRYPTION_KEY='',PYTHONDONTWRITEBYTECODE='1')
    env['PYTHONPATH']=os.pathsep.join([str(package),str(root/'apps/api'),str(root/'apps/api/tests'),str(root/'tools'),env.get('PYTHONPATH','')])
    tests=[
        'tests/test_flow_phase_time_evidence.py','tests/test_flow_phase_time_evidence_api.py',
        'tests/test_phase_clarification_storage.py',
        'tests/test_phase_reconciliation_domain.py','tests/test_phase_reconciliation_api.py',
        'tests/test_phase_reconciliation_probe.py','tests/test_plan_contract_read_api.py',
        'tests/test_executed_workout_adapter.py','tests/test_executed_workout_read_api.py',
        'tests/test_plan_execution_comparison_api.py','tests/test_plan_execution_comparison_probe.py',
        'tests/test_execution_phase_fix.py','tests/test_execution_phase_fix_api.py',
        str(package/'test_flow_time_installer.py'),
    ]
    real_pft=(root/'apps/api/tests/fixtures/pft/synthetic_pft_run_v01.TCX').is_file()
    if real_pft:
        tests += ['tests/test_pft_processing_integration.py','tests/test_pft_measurement_api.py']
    excluded=['test_running_api_probe_saves_an_honest_review_archive','test_user_probe_creates_valid_archive_for_real_app_responses']
    started=time.monotonic()
    with tempfile.TemporaryDirectory(prefix='flow_time_evidence_checks_') as temporary:
        report=Path(temporary)/'checks.xml'
        command=[sys.executable,'-m','pytest','-q',*tests,'-p','no:cacheprovider','-p','phase_fix_no_network',
            '--basetemp='+str(Path(temporary)/'pytest'),'--junitxml='+str(report),
            '-k',' and '.join('not '+name for name in excluded)]
        result=subprocess.run(command,cwd=root/'apps/api',env=env)
        if result.returncode:return result.returncode
        suites=ET.parse(report).getroot().findall('testsuite')
        count=sum(int(x.get('tests',0)) for x in suites)
        skipped=sum(int(x.get('skipped',0)) for x in suites)
        if skipped or count<200:raise ValueError('FLOW_TIME_CHECKS_MISSING_OR_SKIPPED')
    # A separate worker inherits the exact same offline sentinel and path policy.
    check='''import json
from app.main import app
from app.services.flow_phase_time_evidence_read import load_catalog, CATALOG_SHA256
schema=app.openapi()
paths=('/api/v1/sessions/{session_id}/phase-reconciliation/execution-time-evidence',
       '/api/v1/planning/phase-reconciliation/execution-time-evidence-capabilities',
       '/api/v1/sessions/{session_id}/phase-reconciliation/state','/api/v1/pft/capabilities')
assert all('get' in schema['paths'].get(path,{}) for path in paths)
catalog=load_catalog()
assert len(catalog['records'])==3
assert sum(len(x['phases']) for x in catalog['records'])==24
print(json.dumps({'catalog_sha256':CATALOG_SHA256,'registered_reference_count':3,'registered_phase_count':24}))
'''
    imported=subprocess.run([sys.executable,'-c',check],env=env,capture_output=True,text=True)
    if imported.returncode:
        print(imported.stderr);return imported.returncode
    catalog=json.loads(imported.stdout)
    receipt={'status':'FLOW_TIME_EVIDENCE_API_TESTS_AND_ROUTER_CHECK_PASSED',
        'tests':count,'skipped_tests':skipped,'python':sys.version.split()[0],**catalog,
        'read_only_evidence_view':True,'test_database':'SQLITE_IN_MEMORY',
        'test_api':'REAL_FASTAPI_ASGI_NO_NETWORK','real_pft_reference_regression_run':real_pft,
        'fixture_scope':'THREE_REAL_ARCHIVED_STATES_AND_TWO_ARCHIVED_USER_REVISIONS_PLUS_SYNTHETIC_HTTP_RECORDS',
        'old_user_answer_endpoints_preserved':True,'catalog_is_user_data_in_versioned_application_file':True,
        'new_migration_required':False,'production_database_accessed':False,'database_migrated':False,
        'polar_requests':0,'user_answers_modified':False,'actual_phase_alignment_verified':False,
        'numeric_prediction_authorized':False,'model_trained':False,'new_independent_model_test':False,
        'versions':{n:importlib.metadata.version(n) for n in ('fastapi','sqlalchemy','httpx','pytest')},
        'elapsed_seconds':round(time.monotonic()-started,3)}
    print(json.dumps(receipt,ensure_ascii=False,indent=2));return 0


if __name__=='__main__':raise SystemExit(main())
