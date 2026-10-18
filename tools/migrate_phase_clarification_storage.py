"""Guard and apply only the additive phase clarification migration."""
import argparse
import asyncio
import importlib.util
import hashlib
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'apps/api'))
OLD='c91f7a3e2d40'
NEW='da7e4c92b610'
TABLE='phase_clarification_revisions'
PLANNING_KEYS={
    'planning_logical_plans':('logical_plan_id',),
    'planning_plan_revisions':('revision_id',),
    'planning_plan_occurrence_identities':('occurrence_id',),
    'planning_plan_revision_occurrences':('revision_id','occurrence_id'),
}


def require(value,code):
    if not value: raise ValueError(code)


def source_config(root=ROOT):
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    path=root/'apps/api/alembic.ini'
    require(path.is_file(),'PHASE_STORAGE_ALEMBIC_CONFIG_MISSING')
    config=Config(str(path))
    config.set_main_option('script_location',str(root/'apps/api/alembic'))
    scripts=ScriptDirectory.from_config(config)
    require(scripts.get_heads()==[NEW],'PHASE_STORAGE_ALEMBIC_SOURCE_HEAD_DIFFERS')
    require(scripts.get_revision(NEW).down_revision==OLD,'PHASE_STORAGE_ALEMBIC_PARENT_DIFFERS')
    return config


def validate_database_state(info):
    require(info['revision'] in (OLD,NEW),'PHASE_STORAGE_DATABASE_REVISION_DIFFERS')
    if info['revision']==OLD:
        require(not info['table_exists'],'PHASE_STORAGE_TABLE_EXISTS_BEFORE_MIGRATION')
    else:
        from app.models.phase_clarification import PhaseClarificationRevision as Revision
        require(info['table_exists'],'PHASE_STORAGE_TABLE_MISSING_AFTER_MIGRATION')
        require(set(info['columns'])==set(Revision.__table__.columns.keys()),'PHASE_STORAGE_TABLE_COLUMNS_DIFFER')
        require(set(info['unique_constraints']) >= {'uq_phase_clarification_sequence','uq_phase_clarification_request'},
                'PHASE_STORAGE_TABLE_CONSTRAINTS_DIFFER')
        require('ix_phase_clarification_owner_session' in info['indexes'],'PHASE_STORAGE_TABLE_INDEX_MISSING')
    return info


async def database_state():
    from sqlalchemy import text,inspect
    from sqlalchemy.ext.asyncio import create_async_engine
    from app.core.config import get_settings
    engine=create_async_engine(get_settings().database_url,pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            require(conn.dialect.name=='postgresql','PHASE_STORAGE_POSTGRESQL_REQUIRED')
            async with conn.begin():
                await conn.execute(text('SET TRANSACTION READ ONLY'))
                require((await conn.scalar(text('SHOW transaction_read_only')))=='on','PHASE_STORAGE_READ_ONLY_NOT_CONFIRMED')
                require((await conn.scalar(text('SELECT current_schema()')))=='public','PHASE_STORAGE_PUBLIC_SCHEMA_REQUIRED')
                revisions=list((await conn.execute(text('SELECT version_num FROM public.alembic_version'))).scalars())
                require(len(revisions)==1,'PHASE_STORAGE_DATABASE_MULTIPLE_REVISIONS')
                present=await conn.scalar(text("SELECT to_regclass('public.phase_clarification_revisions') IS NOT NULL"))
                info={'revision':revisions[0],'table_exists':bool(present),'columns':[],
                      'unique_constraints':[],'indexes':[],'stored_revision_count':0}
                existing=await conn.run_sync(lambda sync:set(inspect(sync).get_table_names(schema='public')))
                require(set(PLANNING_KEYS)<=existing,'PHASE_STORAGE_PLANNING_PARENT_TABLES_MISSING')
                info['planning_parent_tables_present']=sorted(PLANNING_KEYS)
                if present:
                    def schema(sync):
                        i=inspect(sync)
                        return ([x['name'] for x in i.get_columns(TABLE,schema='public')],
                                [x['name'] for x in i.get_unique_constraints(TABLE,schema='public')],
                                [x['name'] for x in i.get_indexes(TABLE,schema='public')])
                    info['columns'],info['unique_constraints'],info['indexes']=await conn.run_sync(schema)
                    info['stored_revision_count']=await conn.scalar(text('SELECT count(*) FROM public.phase_clarification_revisions'))
                return validate_database_state(info)
    finally:
        await engine.dispose()


def planning_fingerprints(connection):
    """Hash complete ordered rows; no original row content leaves the tool."""
    from sqlalchemy import MetaData,Table,select
    schema='public' if connection.dialect.name=='postgresql' else None
    values={}
    for name,keys in PLANNING_KEYS.items():
        table=Table(name,MetaData(),schema=schema,autoload_with=connection)
        query=select(table).order_by(*(table.c[key] for key in keys)).execution_options(stream_results=True)
        result=connection.execute(query).mappings()
        count=0;digest=hashlib.sha256()
        try:
            while True:
                rows=result.fetchmany(128)
                if not rows:break
                for row in rows:
                    raw=json.dumps(dict(row),sort_keys=True,ensure_ascii=False,allow_nan=False,
                                   default=str,separators=(',',':')).encode('utf-8')
                    digest.update(len(raw).to_bytes(8,'big'));digest.update(raw);count+=1
        finally:result.close()
        values[name]={'row_count':count,'rows_sha256':digest.hexdigest()}
    return values


def apply_on_connection(connection):
    """DDL and version transition use the same explicit transaction/connection.

    The original env.py was not part of the captured source. Do not execute an
    unseen environment that might select a different database connection.
    """
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import text
    prefix='public.' if connection.dialect.name=='postgresql' else ''
    lock=' FOR UPDATE' if connection.dialect.name=='postgresql' else ''
    if connection.dialect.name=='postgresql':
        connection.execute(text("SET LOCAL lock_timeout = '10s'"))
        connection.execute(text("SET LOCAL statement_timeout = '60s'"))
    values=list(connection.execute(text('SELECT version_num FROM '+prefix+'alembic_version'+lock)).scalars())
    require(values==[OLD],'PHASE_STORAGE_REVISION_CHANGED_BEFORE_APPLY')
    if connection.dialect.name=='postgresql':
        require(connection.scalar(text('SELECT current_schema()'))=='public','PHASE_STORAGE_PUBLIC_SCHEMA_REQUIRED')
        # These are the four tables added by the reviewed c91 parent. Block
        # their writers briefly while checking complete rows before and after.
        connection.execute(text('LOCK TABLE '+', '.join('public.'+name for name in PLANNING_KEYS)+' IN SHARE MODE'))
    before=planning_fingerprints(connection)
    path=ROOT/'apps/api/alembic/versions/da7e4c92b610_phase_clarification_revisions.py'
    spec=importlib.util.spec_from_file_location('phase_storage_transaction_migration',path)
    migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
    require(migration.revision==NEW and migration.down_revision==OLD,'PHASE_STORAGE_MIGRATION_LINEAGE_DIFFERS')
    context=MigrationContext.configure(connection)
    with Operations.context(context):
        migration.upgrade()
    result=connection.execute(text('UPDATE '+prefix+'alembic_version SET version_num=:new WHERE version_num=:old'),
                              {'new':NEW,'old':OLD})
    require(result.rowcount==1,'PHASE_STORAGE_VERSION_TRANSITION_FAILED')
    after=planning_fingerprints(connection)
    require(before==after,'PHASE_STORAGE_PLANNING_ROWS_CHANGED_TRANSACTION_ABORTED')
    return {'planning_rows_unchanged_within_migration_transaction':True,'planning_table_fingerprints':after}


async def apply_migration():
    from sqlalchemy.ext.asyncio import create_async_engine
    from app.core.config import get_settings
    engine=create_async_engine(get_settings().database_url,pool_pre_ping=True)
    try:
        async with engine.begin() as connection:
            require(connection.dialect.name=='postgresql','PHASE_STORAGE_POSTGRESQL_REQUIRED')
            return await connection.run_sync(apply_on_connection)
    finally:
        await engine.dispose()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args(argv)
    stage='SOURCE_GRAPH_CHECK'
    try:
        config=source_config()
        stage='DATABASE_READ_ONLY_PREFLIGHT'
        before=asyncio.run(database_state())
        if before['revision']==NEW:
            print(json.dumps({'status':'PHASE_STORAGE_MIGRATION_ALREADY_PRESENT',**before,
                'existing_training_data_modified':False,'database_schema_writes':0},indent=2));return 0
        if not args.apply:
            print(json.dumps({'status':'PHASE_STORAGE_MIGRATION_PREFLIGHT_PASSED','database_revision':OLD,
                'target_revision':NEW,'apply_flag_required':True,'database_writes':0},indent=2));return 0
        stage='APPLY_SINGLE_ADDITIVE_MIGRATION'
        preservation=asyncio.run(apply_migration())
        stage='NEW_CONNECTION_READBACK'
        after=asyncio.run(database_state())
        require(after['revision']==NEW,'PHASE_STORAGE_MIGRATION_READBACK_DIFFERS')
        print(json.dumps({'status':'PHASE_STORAGE_MIGRATION_AND_NEW_CONNECTION_READBACK_VERIFIED',
            **after,**preservation,'old_revision':OLD,'new_tables':1,'existing_training_data_modified':False,
            'automatic_answer_rows_inserted':0,'model_trained':False},indent=2));return 0
    except Exception as exc:
        result={'status':'PHASE_STORAGE_MIGRATION_STOPPED','stage':stage,'error_type':type(exc).__name__}
        if isinstance(exc,ValueError) and re.fullmatch('[A-Z0-9_]+',str(exc)): result['reason']=str(exc)
        code=getattr(getattr(exc,'orig',None),'sqlstate',None)
        if code: result['sqlstate']=code
        print(json.dumps(result,indent=2));return 1


if __name__=='__main__':raise SystemExit(main())
