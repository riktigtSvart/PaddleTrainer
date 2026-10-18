"""Read-only live storage probe; exports draft answer files without submitting."""
import argparse
import json
from pathlib import Path
import re
import time
from uuid import UUID
from urllib.error import HTTPError

from probe_phase_reconciliation_api import TARGETS, request_json, validate_base, save, archive
from app.services.phase_clarification_storage import STORAGE_VERSION, verify_saved_state
from app.planning_contracts.phase_reconciliation_input import strict_loads


def save_http_error(output,exc):
    if isinstance(exc,HTTPError):
        raw=exc.read(65537)
        if len(raw)<=65536:
            try:save(output,'http_error_response.json',strict_loads(raw))
            except (ValueError,TypeError):pass


def clock(value):
    value=max(0,round(value))
    return f'{value//3600:02}:{value//60%60:02}:{value%60:02}'


def review_files(output,index,day,state):
    current=state['effective_reconciliation'];questions=current['result']['questions']
    existing={x['question_id']:x for x in (state['saved_revision']['answers']
              if state['saved_answers_status']=='APPLIED' else [])}
    answers=[]
    lines=[f'# {day} – szakaszváltások pontosítása','',
           'A felsorolt idők a mintasor feltételes eltelt idejei; az óra tényleges gombnyomásait nem igazolják.',
           'A JSON-tervezetet ez a próba nem küldi el. A null mezők megválaszolatlan helyőrzők.',
           'A DONT_KNOW válasz megőrzi a bizonytalanságot; a SELECT_CANDIDATE csak felhasználói jelölés.','']
    for q in questions:
        lines += [q['prompt_hu'],'',f"Kérdésazonosító: `{q['question_id']}`",'']
        for option in q['options']:
            lo,hi=option['transition_window_s']
            label='Külön várakozás nélkül' if option['kind']=='NO_ADDITIONAL_WAIT_CANDIDATE' else 'Lassulás utáni mozgás környékén'
            lines += [f"- {label}: kb. {clock(lo)}–{clock(hi)}; `{option['candidate_id']}`"]
        lines += ['- Nem tudom / egyik jelölt időszak sem biztos: `DONT_KNOW`, `candidate_id: null`.','']
        answers.append(existing.get(q['question_id'],{'question_id':q['question_id'],'answer_type':None,
                         'candidate_id':None,'submitted_at':None}))
    path=output/'review';path.mkdir(exist_ok=True)
    (path/f'{index:02}_questions.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    save(output,f'review/{index:02}_answers_DRAFT.json',{'session_id':state['session_id'],
        'request':{'schema_version':'0.1','artifact_id':state['current_artifact_id'],
                   'expected_revision_id':state['latest_revision_id'],'answers':answers}})


def run_probe(output,base='http://127.0.0.1:8000'):
    base=validate_base(base);output=Path(output).resolve()
    if output.exists():raise ValueError('PHASE_STORAGE_PROBE_OUTPUT_EXISTS')
    output.mkdir(parents=True);started=time.monotonic();rows=[];requests=0;stage='CAPABILITIES'
    result={'status':'PHASE_STORAGE_READ_PROBE_STOPPED_WITH_SAVED_PROGRESS',
            'storage_version':STORAGE_VERSION,'database_writes':0,'user_answers_submitted':0,
            'provider_calls':0,'actual_phase_alignment_verified':False,'model_trained':False,
            'new_independent_model_test':False,'output_folder':str(output),'result_zip':str(output.with_suffix('.zip'))}
    try:
        requests+=1;caps=request_json(base,'/api/v1/planning/phase-reconciliation/storage-capabilities')
        save(output,'capabilities.json',caps)
        if caps['storage_version']!=STORAGE_VERSION:raise ValueError('PHASE_STORAGE_VERSION_DIFFERS')
        for i,(day,sid) in enumerate(TARGETS):
            print(f'Saved-answer read {i+1}/{len(TARGETS)}: {day}',flush=True)
            values=[]
            for repeat in (1,2):
                stage=f'SESSION_{i+1}_READ_{repeat}';requests+=1
                state=request_json(base,f'/api/v1/sessions/{sid}/phase-reconciliation/state?include_source=true')
                save(output,f'sessions/{i:02}_state_{repeat}.json.gz',state)
                if state['session_id']!=sid:raise ValueError('PHASE_STORAGE_SESSION_DIFFERS')
                old=None
                if state['latest_revision_id']:
                    stage=f'SESSION_{i+1}_ARCHIVE_{repeat}';rid=str(UUID(state['latest_revision_id']));requests+=1
                    old=request_json(base,f'/api/v1/sessions/{sid}/phase-reconciliation/clarifications/{rid}?include_source=true')
                    save(output,f'sessions/{i:02}_archive_{repeat}.json.gz',old)
                verify_saved_state(state,old);values.append(state)
            a,b=values
            for key in ('current_artifact_id','latest_revision_id','saved_answers_status','applied_revision_id'):
                if a[key]!=b[key]:raise ValueError('PHASE_STORAGE_STATE_CHANGED_DURING_PROBE')
            if a['effective_reconciliation']['result']['questions']!=b['effective_reconciliation']['result']['questions']:
                raise ValueError('PHASE_STORAGE_QUESTION_IDENTITY_DIFFERS')
            review_files(output,i,day,b)
            rows.append({'date':day,'session_id':sid,'saved_answers_status':b['saved_answers_status'],
                'latest_revision_id':b['latest_revision_id'],'question_count':b['effective_reconciliation']['result']['question_count'],
                'pending_question_count':b['effective_reconciliation']['result']['pending_question_count'],
                'full_state_replay_verified':True})
        result['status']='PHASE_STORAGE_READ_AND_SOURCE_REPLAY_PROBE_PASSED'
    except Exception as exc:
        result.update(error_type=type(exc).__name__,failed_stage=stage)
        if isinstance(exc,ValueError) and re.fullmatch('[A-Z0-9_]+',str(exc)):result['error_code']=str(exc)
        if isinstance(exc,HTTPError):result['http_status']=exc.code;save_http_error(output,exc)
    finally:
        result.update(sessions=rows,completed_session_count=len(rows),local_api_requests=requests,
                      elapsed_seconds=round(time.monotonic()-started,3))
        save(output,'summary.json',result);archive(output)
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True);parser.add_argument('--base',default='http://127.0.0.1:8000')
    args=parser.parse_args(argv);result=run_probe(args.output,args.base)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['status']=='PHASE_STORAGE_READ_AND_SOURCE_REPLAY_PROBE_PASSED' else 1


if __name__=='__main__':raise SystemExit(main())
