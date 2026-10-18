"""Saved-source replay and review artifacts. No application or network access."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import socket
from unittest.mock import patch
import zipfile

from app.planning_contracts.phase_reconciliation_input import load_api, prepare_api, strict_loads
from app.planning_contracts.phase_reconciliation import canonical, digest, reconcile, require

PACKAGE=Path(__file__).resolve().parent/"fixtures/phase_reconciliation"


@contextmanager
def offline_network_guard():
    def blocked(*args,**kwargs):
        raise RuntimeError('NETWORK_ACCESS_DISABLED_FOR_OFFLINE_PHASE_CHECKS')
    with patch.object(socket,'socket',blocked), patch.object(socket,'create_connection',blocked), \
            patch.object(socket,'getaddrinfo',blocked):
        yield


def verify_package(root=PACKAGE):
    value=strict_loads((root/'FILE_HASHES.json').read_bytes())
    for name,entry in value['files'].items():
        p=root/name
        require(not Path(name).is_absolute() and '..' not in Path(name).parts
                and not p.is_symlink() and p.is_file(),'PACKAGE_PATH_INVALID')
        raw=p.read_bytes()
        require(len(raw)==entry['bytes'] and hashlib.sha256(raw).hexdigest()==entry['sha256'],
                'PACKAGE_FILE_CHANGED:'+name)
    return hashlib.sha256((root/'FILE_HASHES.json').read_bytes()).hexdigest()


def write_gzip(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(gzip.compress(canonical(value),mtime=0))


def clock(t):
    t=max(0,round(t))
    return f'{t//3600:02}:{t//60%60:02}:{t%60:02}'


def review_markdown(items):
    lines=['# Kézi váltások – előkészített pontosítások','',
        'Ezek az offline adapter kérdésjavaslatai; az alkalmazás felületébe még nincsenek bekötve.',
        'Az idősávok mintasorból becsült, feltételes eltelt idők. Nem órából visszaadott szakaszesemények.',
        'Ha egyik időszak sem biztos, a „Nem tudom” válasz megőrzi a bizonytalanságot és a teljes felvételt.','']
    for item in items:
        r=item['result']
        lines.extend([f"## {item['local_date']}",''])
        if not r['questions']:
            lines.extend(['Nincs kézi váltás időzítésére készített kérdés ebben az eredményben.',''])
        for q in r['questions']:
            lines.extend([q['prompt_hu'],''])
            for o in q['options']:
                a,b=o['transition_window_s']
                label='A cél elérésekor, külön várakozás nélkül' if o['kind']=='NO_ADDITIONAL_WAIT_CANDIDATE' else 'A lassulás utáni újraindulás környékén'
                lines.append(f'- {label}: kb. {clock(a)}–{clock(b)}.')
            lines.extend(['- Nem tudom / egyik jelölt időszak sem biztos.',''])
    return '\n'.join(lines)+'\n'


def save_output_manifest(output):
    files={}
    for p in sorted(output.rglob('*')):
        if p.is_file() and p.name!='OUTPUT_MANIFEST.json':
            raw=p.read_bytes()
            files[p.relative_to(output).as_posix()]={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
    (output/'OUTPUT_MANIFEST.json').write_text(json.dumps({'files':files},indent=2)+'\n',encoding='utf-8')
    archive=output.with_suffix('.zip')
    require(not archive.exists(),'RESULT_ARCHIVE_ALREADY_EXISTS')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(output.rglob('*')):
            if p.is_file():
                z.write(p,p.relative_to(output).as_posix())
    return archive


def run_saved_sources(paths, output, *, reference_path=None, clarifications_by_session=None,
                      check_summary=None):
    output=Path(output).resolve()
    require(not output.exists(),'OUTPUT_DIRECTORY_ALREADY_EXISTS')
    paths=[Path(p) for p in paths]
    require(1<=len(paths)<=200,'INPUT_FILE_COUNT_INVALID')
    require(all(p.is_file() for p in paths),'INPUT_SOURCE_FILE_MISSING')
    output.mkdir(parents=True)
    items,failures=[],[]
    seen=set()
    for index,path in enumerate(paths):
        try:
            api=load_api(path)
            before=digest(api)
            spec=prepare_api(api)
            key=(spec['binding']['session_id'],spec['binding']['source_sha256'],spec['binding']['plan_sha256'])
            require(key not in seen,'DUPLICATE_SOURCE_VERSION')
            seen.add(key)
            answers=(clarifications_by_session or {}).get(spec['binding']['session_id'])
            result=reconcile(spec,clarifications=answers)
            require(digest(api)==before,'SOURCE_CHANGED_DURING_RECONCILIATION')
            item={'local_date':spec['local_date'],'result':result,'input_api_sha256':before,
                  'input_spec_sha256':digest(spec)}
            base=output/'sessions'/f'{index:03}'
            write_gzip(base/'original_api_source.json.gz',api)
            write_gzip(base/'motion_input.json.gz',spec)
            write_gzip(base/'reconciliation.json.gz',result)
            (base/'clarifications_template.json').write_text(json.dumps({
                'schema_version':'0.1','artifact_id':result['artifact_id'],'answers':[]},indent=2)+'\n',encoding='utf-8')
            items.append(item)
        except Exception as exc:
            # Never export arbitrary exception text from source replayers.
            failures.append({'input_index':index,'error_type':type(exc).__name__,
                'stage':'SAVED_SOURCE_REPLAY_OR_RECONCILIATION','database_writes':0})
    # Reference data is opened only after every API-only result has been frozen.
    before_reference=[digest(v['result']) for v in items]
    evaluations=[]
    if reference_path is not None:
        from phase_reconciliation_reference import evaluate
        reference=strict_loads(Path(reference_path).read_bytes())
        for item in items:
            evaluations.append({'session_id':item['result']['binding']['session_id'],
                                'evaluation':evaluate(item['result'],reference)})
    require([digest(v['result']) for v in items]==before_reference,'REFERENCE_CHANGED_INFERENCE_RESULTS')
    evaluation_path=output/'reference_evaluation.json'
    evaluation_path.write_text(json.dumps(evaluations,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (output/'questions_HU.md').write_text(review_markdown(items),encoding='utf-8')
    if check_summary is not None:
        (output/'offline_checks.json').write_text(json.dumps(check_summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    unused=set(clarifications_by_session or {})-{v['result']['binding']['session_id'] for v in items}
    summary={'status':'API_PHASE_RECONCILIATION_OFFLINE_REPLAY_PASSED' if not failures and not unused else 'OFFLINE_REPLAY_WITH_WITHHELD_SOURCES_OR_ANSWERS',
        'created_at':datetime.now(timezone.utc).isoformat(), 'input_file_count':len(paths),
        'source_replayed_session_count':len(items),'withheld_source_count':len(failures),
        'phase_inventory_count':sum(len(i['result']['phase_inventory']) for i in items),
        'manual_timing_question_count':sum(i['result']['question_count'] for i in items),
        'pending_question_count':sum(i['result']['pending_question_count'] for i in items),
        'unused_clarification_session_count':len(unused),
        'hypothesis_count':sum(len(i['result']['hypotheses']) for i in items),
        'search_limit_reached_session_count':sum(i['result']['search_limits_reached'] for i in items),
        'discarded_native_sample_count':sum(i['result']['source_preservation']['discarded_sample_count'] for i in items),
        'reference_opened_after_all_inference_results':reference_path is not None,
        'flow_reference_used_for_inference':False, 'outcome_hr_used_for_boundaries':False,
        'actual_phase_alignment_verified':False,'provider_events_created':0,
        'source_project_modified':False,'database_accessed':False,'database_writes':0,
        'api_requests':0,'polar_requests':0,'network_calls':0,
        'speed_model_retrained':False,'numeric_prediction_authorized':False,
        'new_independent_model_test':False,'api_integrated':False,
        'failures':failures,'output_folder':str(output),'result_zip':str(output.with_suffix('.zip'))}
    (output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    save_output_manifest(output)
    return summary
