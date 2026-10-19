"""Run the actual additive migration and compile its PostgreSQL DDL offline."""
import importlib.util
import io
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.models.phase_clarification import PhaseClarificationRevision as Revision


def module():
    path=Path(__file__).resolve().parents[1]/'alembic/versions/da7e4c92b610_phase_clarification_revisions.py'
    spec=importlib.util.spec_from_file_location('phase_revision_migration',path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value


def test_revision_extends_the_received_planning_head():
    migration=module()
    assert migration.revision=='da7e4c92b610' and migration.down_revision=='c91f7a3e2d40'


def test_complete_received_graph_has_one_head_and_preserves_planning_source():
    import hashlib
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    root=Path(__file__).resolve().parents[1]
    config=Config(str(root/'alembic.ini'));config.set_main_option('script_location',str(root/'alembic'))
    scripts=ScriptDirectory.from_config(config)
    assert scripts.get_heads() == ["c84d7e1a6f32"]
    current = scripts.get_revision("a91f6c3d7b20")
    assert current is not None
    assert current.down_revision == "e2a7c4b9d310"
    assert scripts.get_revision('c91f7a3e2d40').down_revision=='b8e4d6a10f32'
    actual=root/'alembic/versions/c91f7a3e2d40_add_planning_authoritative_plan_revisions.py'
    assert hashlib.sha256(actual.read_bytes()).hexdigest()=='9bd697b7982b15a54c19af65ad30c3224f8164e3e52f51210ebb6d9d3509ec98'


def test_original_planning_ddl_includes_its_four_tables_and_immutability_guards(monkeypatch):
    path=Path(__file__).resolve().parents[1]/'alembic/versions/c91f7a3e2d40_add_planning_authoritative_plan_revisions.py'
    spec=importlib.util.spec_from_file_location('received_planning_migration',path)
    migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
    out=io.StringIO();context=MigrationContext.configure(dialect_name='postgresql',opts={'as_sql':True,'output_buffer':out})
    monkeypatch.setattr(migration,'op',Operations(context));migration.upgrade();sql=out.getvalue()
    assert sql.count('CREATE TABLE ')==4
    assert sql.count('CREATE TRIGGER ')==3
    assert 'planning_reject_immutable_plan_history_mutation' in sql


def test_postgres_migration_only_creates_the_new_table_and_index(monkeypatch):
    migration=module();out=io.StringIO()
    ctx=MigrationContext.configure(dialect_name='postgresql',opts={'as_sql':True,'output_buffer':out})
    monkeypatch.setattr(migration,'op',Operations(ctx));migration.upgrade()
    sql=out.getvalue()
    assert 'CREATE TABLE phase_clarification_revisions' in sql
    assert 'request_json JSONB NOT NULL' in sql and 'evidence_gzip BYTEA NOT NULL' in sql
    assert 'UNIQUE (session_id, request_sha256)' in sql and 'UNIQUE (session_id, sequence)' in sql
    for forbidden in ('ALTER TABLE','UPDATE ','DELETE FROM ','DROP ','INSERT '): assert forbidden not in sql
    model=str(CreateTable(Revision.__table__).compile(dialect=postgresql.dialect()))
    assert 'request_json JSONB NOT NULL' in model and 'evidence_gzip BYTEA NOT NULL' in model


def test_upgrade_and_empty_downgrade_preserve_existing_rows(monkeypatch):
    migration=module();engine=create_engine('sqlite+pysqlite:///:memory:')
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE users (id VARCHAR PRIMARY KEY, marker TEXT)'))
        connection.execute(text('CREATE TABLE workout_sessions (id VARCHAR PRIMARY KEY, marker TEXT)'))
        connection.execute(text("INSERT INTO users VALUES ('u', 'keep')"))
        connection.execute(text("INSERT INTO workout_sessions VALUES ('s', 'keep')"))
        monkeypatch.setattr(migration,'op',Operations(MigrationContext.configure(connection)))
        migration.upgrade()
        assert set(inspect(connection).get_table_names())=={'users','workout_sessions','phase_clarification_revisions'}
        assert {x['name'] for x in inspect(connection).get_columns(Revision.__tablename__)}==set(Revision.__table__.columns.keys())
        migration.downgrade()
        assert set(inspect(connection).get_table_names())=={'users','workout_sessions'}
        assert connection.execute(text('SELECT marker FROM users')).scalar_one()=='keep'
        assert connection.execute(text('SELECT marker FROM workout_sessions')).scalar_one()=='keep'


def test_downgrade_refuses_any_saved_answer(monkeypatch):
    import pytest
    migration=module();engine=create_engine('sqlite+pysqlite:///:memory:')
    with engine.begin() as connection:
        # A minimal nonempty table is enough to exercise the deletion guard.
        connection.execute(text('CREATE TABLE phase_clarification_revisions (id TEXT)'))
        connection.execute(text("INSERT INTO phase_clarification_revisions VALUES ('retained')"))
        monkeypatch.setattr(migration,'op',Operations(MigrationContext.configure(connection)))
        with pytest.raises(RuntimeError,match='REFUSES_SAVED_ANSWERS'): migration.downgrade()
        assert connection.execute(text('SELECT id FROM phase_clarification_revisions')).scalar_one()=='retained'
