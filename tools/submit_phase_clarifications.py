"""Submit only an explicitly completed user answer file; no guessed defaults."""
import argparse
import json
from pathlib import Path
import re
from uuid import UUID
from urllib.error import HTTPError
from probe_phase_clarification_storage import save_http_error

from probe_phase_reconciliation_api import request_json,validate_base,save,archive
from app.planning_contracts.phase_reconciliation import digest
from app.planning_contracts.phase_reconciliation_input import strict_loads
from app.schemas.phase_clarification_storage import PhaseClarificationSaveRequest
from app.services.phase_clarification_storage import verify_saved_state


def read_state(base,sid):
    current=request_json(base,f'/api/v1/sessions/{sid}/phase-reconciliation/state?include_source=true')
    old=None
    if current['latest_revision_id']:
        rid=str(UUID(current['latest_revision_id']))
        old=request_json(base,f'/api/v1/sessions/{sid}/phase-reconciliation/clarifications/{rid}?include_source=true')
    verify_saved_state(current,old)
    return current,old


def run_submit(answers,output,base='http://127.0.0.1:8000'):
    base=validate_base(base);source=Path(answers)
    if not source.is_file() or source.is_symlink() or source.stat().st_size>256*1024:
        raise ValueError('PHASE_STORAGE_ANSWER_FILE_INVALID')
    value=strict_loads(source.read_bytes())
    if not isinstance(value,dict) or set(value)!={'session_id','request'}:
        raise ValueError('PHASE_STORAGE_ANSWER_FILE_FIELDS_INVALID')
    sid=str(UUID(value['session_id']))
    request=PhaseClarificationSaveRequest.model_validate(value['request']).model_dump(mode='json')
    output=Path(output).resolve()
    if output.exists():raise ValueError('PHASE_STORAGE_SUBMIT_OUTPUT_EXISTS')
    output.mkdir(parents=True)
    save(output,'submitted_request.json',{'session_id':sid,'request':request})
    result={'status':'PHASE_STORAGE_SUBMISSION_STOPPED_WITH_SAVED_PROGRESS','session_id':sid,
            'submission_attempted':False,'commit_outcome':'NOT_ATTEMPTED','provider_calls':0,
            'actual_phase_alignment_verified':False,'result_zip':str(output.with_suffix('.zip'))}
    try:
        before,old=read_state(base,sid);save(output,'before_state.json.gz',before)
        if old:save(output,'before_archive.json.gz',old)
        if before['current_artifact_id']!=request['artifact_id']:
            raise ValueError('PHASE_STORAGE_ANSWER_SOURCE_CHANGED_REVIEW_AGAIN')
        exact_retry=before['saved_revision'] and before['saved_revision']['request_sha256']==digest(request)
        if before['latest_revision_id']!=request['expected_revision_id'] and not exact_retry:
            raise ValueError('PHASE_STORAGE_ANSWER_REVISION_CHANGED_REVIEW_AGAIN')
        result.update(submission_attempted=True,commit_outcome='UNKNOWN_CHECK_STATE_BEFORE_RETRY')
        response=request_json(base,f'/api/v1/sessions/{sid}/phase-reconciliation/clarifications',body=request)
        save(output,'save_response.json',response)
        result.update(commit_outcome=response['status'],database_writes_reported=response['database_writes'])
        after,old=read_state(base,sid);save(output,'after_state.json.gz',after)
        if old:save(output,'after_archive.json.gz',old)
        if after['applied_revision_id']!=response['revision']['revision_id']:
            raise ValueError('PHASE_STORAGE_SUBMITTED_REVISION_NOT_CURRENT_REVIEW_STATE')
        if after['saved_revision']['request_sha256']!=digest(request):
            raise ValueError('PHASE_STORAGE_READBACK_REQUEST_DIFFERS')
        result.update(status='PHASE_STORAGE_USER_ANSWERS_SAVED_AND_READBACK_VERIFIED',
                      revision_id=response['revision']['revision_id'],full_source_replay_verified=True)
    except Exception as exc:
        result['error_type']=type(exc).__name__
        if isinstance(exc,ValueError) and re.fullmatch('[A-Z0-9_]+',str(exc)):result['error_code']=str(exc)
        if isinstance(exc,HTTPError):result['http_status']=exc.code;save_http_error(output,exc)
    finally:
        save(output,'summary.json',result);archive(output)
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--answers',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--base',default='http://127.0.0.1:8000')
    args=parser.parse_args(argv)
    try:
        result=run_submit(args.answers,args.output,args.base)
    except Exception as exc:
        result={'status':'PHASE_STORAGE_ANSWER_FILE_PREFLIGHT_FAILED','submission_attempted':False,
                'commit_outcome':'NOT_ATTEMPTED','error_type':type(exc).__name__,
                'reason':'ANSWER_FILE_INVALID_OR_INCOMPLETE'}
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['status']=='PHASE_STORAGE_USER_ANSWERS_SAVED_AND_READBACK_VERIFIED' else 1


if __name__=='__main__':raise SystemExit(main())
