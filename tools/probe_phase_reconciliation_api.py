"""Loopback-only read/empty-inspection probe. Does not submit user decisions."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler,ProxyHandler,Request,build_opener
import zipfile

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'apps/api'))
from app.planning_contracts.phase_reconciliation import RULES_VERSION,canonical,digest
from app.planning_contracts.phase_reconciliation_input import strict_loads
from app.services.phase_reconciliation_read import verify_phase_reconciliation_read

TARGETS=(
    ('2026-07-25','d0b049e5-3b25-48a6-b869-64c7ee306b24'),
    ('2026-07-29','9b965faf-ddde-42ff-9c2d-04ea3c332407'),
    ('2026-08-14','9c0413d6-f2eb-4b31-9969-af766e130e54'),
)
MAX_HTTP_BYTES=12*1024*1024


def require(condition,code):
    if not condition:raise ValueError(code)


def validate_base(base):
    value=urlsplit(base)
    require(value.scheme=='http' and value.hostname in ('127.0.0.1','::1')
        and value.username is None and value.password is None and value.path in ('','/')
        and not value.query and not value.fragment,'LITERAL_LOOPBACK_HTTP_BASE_REQUIRED')
    require(value.port is not None and 1<=value.port<=65535,'EXPLICIT_LOOPBACK_PORT_REQUIRED')
    return base.rstrip('/')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise ValueError('PROBE_REDIRECT_FORBIDDEN')


def request_json(base,path,*,body=None):
    require(path.startswith('/api/v1/') and '://' not in path and '..' not in path,'PROBE_PATH_INVALID')
    payload=canonical(body) if body is not None else None
    request=Request(validate_base(base)+path,data=payload,
        headers={'Accept':'application/json',**({'Content-Type':'application/json'} if payload else {})},
        method='POST' if body is not None else 'GET')
    opener=build_opener(ProxyHandler({}),NoRedirect())
    with opener.open(request,timeout=60) as response:
        require(response.status==200,'PROBE_HTTP_STATUS_NOT_200')
        raw=response.read(MAX_HTTP_BYTES+1)
        require(len(raw)<=MAX_HTTP_BYTES,'PROBE_HTTP_RESPONSE_TOO_LARGE')
        require(response.headers.get('Cache-Control')=='no-store','PROBE_CACHE_POLICY_DIFFERS')
    return strict_loads(raw)


def save(output,name,value):
    path=output/name;path.parent.mkdir(parents=True,exist_ok=True)
    raw=canonical(value)
    path.write_bytes(gzip.compress(raw,mtime=0) if name.endswith('.gz') else raw+b'\n')


def archive(output):
    files={}
    for file in sorted(output.rglob('*')):
        if file.is_file() and file.name!='OUTPUT_MANIFEST.json':
            raw=file.read_bytes()
            files[file.relative_to(output).as_posix()]={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
    save(output,'OUTPUT_MANIFEST.json',{'files':files})
    target=output.with_suffix('.zip');require(not target.exists(),'PROBE_ZIP_ALREADY_EXISTS')
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        for file in sorted(output.rglob('*')):
            if file.is_file():z.write(file,file.relative_to(output).as_posix())
    return target


def run_probe(output,base='http://127.0.0.1:8000'):
    base=validate_base(base)
    output=Path(output).resolve();require(not output.exists(),'PROBE_OUTPUT_ALREADY_EXISTS')
    output.mkdir(parents=True)
    started=time.monotonic();rows=[];requests=0
    summary={'status':'PHASE_RECONCILIATION_API_READ_PROBE_STOPPED_WITH_SAVED_PROGRESS',
        'rules_version':RULES_VERSION,'requested_session_count':len(TARGETS),
        'completed_session_count':0,'local_api_requests':0,'database_writes':0,
        'provider_calls':0,'user_answers_submitted':0,'user_answers_persisted':False,
        'actual_phase_alignment_verified':False,'speed_model_retrained':False,
        'new_independent_model_test':False,'output_folder':str(output),
        'result_zip':str(output.with_suffix('.zip'))}
    stage='CAPABILITIES'
    try:
        requests+=1
        caps=request_json(base,'/api/v1/planning/phase-reconciliation/capabilities')
        save(output,'capabilities.json',caps)
        require(caps['rules_version']==RULES_VERSION and caps['read_and_inspect_only']
                and not caps['clarifications_persisted'],'PROBE_API_CAPABILITIES_DIFFER')
        for i,(day,sid) in enumerate(TARGETS):
            print(f'Phase API {i+1}/{len(TARGETS)}: {day}',flush=True)
            stage=f'SESSION_{i+1}_FIRST_READ'
            path=f'/api/v1/sessions/{sid}/phase-reconciliation?include_source=true'
            requests+=1
            a=request_json(base,path);save(output,f'sessions/{i:02}_read_1.json.gz',a)
            require(a['session_id']==sid and verify_phase_reconciliation_read(a),'PROBE_FIRST_FULL_REPLAY_FAILED')
            stage=f'SESSION_{i+1}_REPEAT_READ'
            requests+=1
            b=request_json(base,path);save(output,f'sessions/{i:02}_read_2.json.gz',b)
            require(b['session_id']==sid and verify_phase_reconciliation_read(b),'PROBE_REPEAT_FULL_REPLAY_FAILED')
            require(a['source_content_sha256']==b['source_content_sha256']
                    and a['plan_source_content_sha256']==b['plan_source_content_sha256'],'SOURCE_CHANGED_DURING_PROBE')
            require(a['stable_artifact_id']==b['stable_artifact_id']
                    and a['result']['questions']==b['result']['questions'],'QUESTION_IDENTITY_CHANGED_ON_UNCHANGED_SOURCE')
            request={'schema_version':'0.1','artifact_id':a['stable_artifact_id'],'answers':[]}
            stage=f'SESSION_{i+1}_EMPTY_INSPECTION'
            requests+=1
            c=request_json(base,f'/api/v1/sessions/{sid}/phase-reconciliation/clarifications/inspect?include_source=true',body=request)
            save(output,f'sessions/{i:02}_empty_inspection.json.gz',c)
            require(c['session_id']==sid and verify_phase_reconciliation_read(c),'PROBE_INSPECTION_FULL_REPLAY_FAILED')
            require(c['stable_artifact_id']==a['stable_artifact_id']
                    and c['result']['questions']==a['result']['questions'],'INSPECTION_SOURCE_CHANGED')
            require(not c['clarifications_persisted'] and c['user_answer_storage_writes']==0
                    and c['result']['source_preservation']['discarded_sample_count']==0,
                    'PROBE_INSPECTION_OR_SOURCE_PRESERVATION_SCOPE_DIFFERS')
            rows.append({'date':day,'session_id':sid,'question_count':a['result']['question_count'],
                'pending_question_count':a['result']['pending_question_count'],
                'phase_count':len(a['result']['phase_inventory']),
                'stable_artifact_id':a['stable_artifact_id'],
                'source_sha256':a['source_content_sha256'],'plan_sha256':a['plan_source_content_sha256'],
                'stable_question_identity_verified':True,'three_full_source_replays_verified':True})
        summary.update(status='PHASE_RECONCILIATION_API_READ_AND_EMPTY_INSPECTION_PROBE_PASSED',
            stable_question_identity_verified=True,full_source_replay_verified=True,
            question_count=sum(v['question_count'] for v in rows),
            pending_question_count=sum(v['pending_question_count'] for v in rows),
            phase_count=sum(v['phase_count'] for v in rows),discarded_samples=0)
    except Exception as exc:
        summary['error_type']=type(exc).__name__
        summary['failed_stage']=stage
        if isinstance(exc,ValueError) and re.fullmatch(r'[A-Z][A-Z0-9_]{0,160}',str(exc)):
            summary['error_code']=str(exc)
        if isinstance(exc,HTTPError):
            summary['http_status']=exc.code
            raw=exc.read(65537)
            if len(raw)<=65536:
                try:save(output,'http_error_response.json',strict_loads(raw))
                except (ValueError,TypeError):pass
    finally:
        summary.update(completed_session_count=len(rows),local_api_requests=requests,
                       elapsed_seconds=round(time.monotonic()-started,3),sessions=rows)
        save(output,'summary.json',summary);archive(output)
    return summary


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True);parser.add_argument('--base',default='http://127.0.0.1:8000')
    args=parser.parse_args(argv)
    result=run_probe(args.output,args.base)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['status']=='PHASE_RECONCILIATION_API_READ_AND_EMPTY_INSPECTION_PROBE_PASSED' else 1


if __name__=='__main__':raise SystemExit(main())
