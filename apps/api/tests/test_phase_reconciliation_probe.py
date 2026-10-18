"""Probe exercises real ASGI reads without any service socket or user answer."""
import importlib.util
import json
from pathlib import Path
import sys
import zipfile

import pytest

from test_plan_contract_read_api import environment
from test_executed_workout_read_api import executions
from test_phase_reconciliation_api import make_session


def module():
    path=Path(__file__).resolve().parents[3]/'tools/probe_phase_reconciliation_api.py'
    spec=importlib.util.spec_from_file_location('phase_probe_for_tests',path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value


def test_full_probe_uses_real_app_three_times_and_no_user_answer(executions,tmp_path,monkeypatch):
    env=executions;row=make_session(env);probe=module();requests=[]
    monkeypatch.setattr(probe,'TARGETS',( ('synthetic',str(row.id)), ))
    def fetch(base,path,*,body=None):
        requests.append((path,body))
        response=env.client.post(path,json=body) if body is not None else env.client.get(path)
        assert response.status_code==200,response.text
        return response.json()
    monkeypatch.setattr(probe,'request_json',fetch)
    out=tmp_path/'probe with spaces'
    result=probe.run_probe(out)
    assert result['status']=='PHASE_RECONCILIATION_API_READ_AND_EMPTY_INSPECTION_PROBE_PASSED'
    assert result['local_api_requests']==4 and len(requests)==4
    assert requests[-1][1]['answers']==[]
    assert result['user_answers_submitted']==0 and not result['user_answers_persisted']
    assert set(env.sql)=={'SELECT'}
    with zipfile.ZipFile(out.with_suffix('.zip')) as z:
        assert z.testzip() is None
        summary=json.loads(z.read('summary.json'))
        assert summary['stable_question_identity_verified']
        assert len(z.read('sessions/00_empty_inspection.json.gz'))>0


def test_probe_failure_preserves_partial_zip(tmp_path,monkeypatch):
    probe=module()
    def fail(*args,**kwargs):raise RuntimeError('private detail must not enter output')
    monkeypatch.setattr(probe,'request_json',fail)
    out=tmp_path/'partial'
    result=probe.run_probe(out)
    assert result['status']=='PHASE_RECONCILIATION_API_READ_PROBE_STOPPED_WITH_SAVED_PROGRESS'
    assert result['failed_stage']=='CAPABILITIES' and out.with_suffix('.zip').is_file()
    assert 'private detail' not in json.dumps(result)


@pytest.mark.parametrize('url',['https://127.0.0.1:8000','http://localhost:8000',
    'http://192.168.1.10:8000','http://127.0.0.1:8000/path','http://name:secret@127.0.0.1:8000',
    'http://127.0.0.1:8000?proxy=1','http://127.0.0.1'])
def test_probe_rejects_remote_proxy_or_credential_bases(url):
    with pytest.raises(ValueError):module().validate_base(url)


def test_probe_accepts_only_literal_loopback_with_port():
    probe=module()
    assert probe.validate_base('http://127.0.0.1:8000/')=='http://127.0.0.1:8000'
    assert probe.validate_base('http://[::1]:8000')=='http://[::1]:8000'
