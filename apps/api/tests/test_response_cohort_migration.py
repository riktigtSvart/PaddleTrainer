import importlib.util
import io
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.db.base import Base
from app.models import ResponseCohortMember, ResponseCohortRecord

API_ROOT = Path(__file__).resolve().parents[1]
REVISION = "e4f7a92c1836"
NEW_TABLES = {"response_cohort_records", "response_cohort_members"}


def migration():
    path = API_ROOT / "alembic/versions" / f"{REVISION}_add_response_cohort_records.py"
    spec = importlib.util.spec_from_file_location("cohort_migration_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_single_migration_head_adds_cohorts_after_replay_without_changing_prior_chain():
    scripts = ScriptDirectory.from_config(Config(str(API_ROOT / "alembic.ini")))
    assert scripts.get_heads() == [REVISION]
    assert scripts.get_revision(REVISION).down_revision == "d83b9c61f204"
    assert scripts.get_revision("d83b9c61f204").down_revision == "c5e83a9d2714"


def test_registered_models_have_jsonb_scope_constraints_and_deferred_source_retention():
    record = ResponseCohortRecord.__table__
    member = ResponseCohortMember.__table__
    assert (
        Base.metadata.tables[record.name] is record and Base.metadata.tables[member.name] is member
    )
    sql = str(CreateTable(record).compile(dialect=postgresql.dialect()))
    assert "record_json JSONB NOT NULL" in sql
    assert "UNIQUE (user_id, record_schema_version, record_hash)" in sql
    assert "UNIQUE (id, user_id)" in sql
    assert "member_count BETWEEN 1 AND 20" in sql
    assert "REFERENCES users (id) ON DELETE CASCADE" in sql
    sql = str(CreateTable(member).compile(dialect=postgresql.dialect()))
    assert "PRIMARY KEY (record_id, canonical_index)" in sql
    assert "canonical_index BETWEEN 0 AND 19" in sql
    assert (
        "FOREIGN KEY(record_id, user_id) REFERENCES response_cohort_records (id, user_id) ON DELETE CASCADE"
        in sql
    )
    for column in ("workout_session_id", "replay_snapshot_id", "evidence_set_id"):
        assert f"UNIQUE (record_id, {column})" in sql
    source_keys = [
        key for key in member.foreign_key_constraints if key.referred_table.name != record.name
    ]
    assert len(source_keys) == 3
    assert all(
        key.ondelete == "NO ACTION" and key.deferrable and key.initially == "DEFERRED"
        for key in source_keys
    )
    assert sql.count("ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED") == 3


@pytest.mark.parametrize("direction", ["upgrade", "downgrade"])
def test_postgres_migration_changes_only_two_new_tables_and_their_indexes(monkeypatch, direction):
    module = migration()
    output = io.StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output}
    )
    monkeypatch.setattr(module, "op", Operations(context))
    getattr(module, direction)()
    sql = output.getvalue()
    if direction == "upgrade":
        assert "CREATE TABLE response_cohort_records" in sql
        assert "CREATE TABLE response_cohort_members" in sql
        assert "record_json JSONB NOT NULL" in sql
        assert sql.count("CREATE INDEX ") == 4
        assert sql.count("ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED") == 3
    else:
        assert sql.index("DROP TABLE response_cohort_members") < sql.index(
            "DROP TABLE response_cohort_records"
        )
    for statement in ("UPDATE ", "DELETE FROM ", "ALTER TABLE "):
        assert statement not in sql
    for previous in (
        "users",
        "workout_sessions",
        "route_environment_evidence_sets",
        "route_environment_replay_snapshots",
        "heart_rate_timebase_snapshots",
        "hr_acquisition_declarations",
    ):
        assert f"CREATE TABLE {previous}" not in sql and f"DROP TABLE {previous}" not in sql


def test_executed_sqlite_upgrade_and_downgrade_preserve_existing_schema(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    previous_tables = [
        table for table in Base.metadata.sorted_tables if table.name not in NEW_TABLES
    ]
    Base.metadata.create_all(engine, tables=previous_tables)
    original = set(inspect(engine).get_table_names())
    module = migration()
    with engine.begin() as connection:
        monkeypatch.setattr(module, "op", Operations(MigrationContext.configure(connection)))
        module.upgrade()
        inspector = inspect(connection)
        assert set(inspector.get_table_names()) == original | NEW_TABLES
        assert inspector.get_pk_constraint("response_cohort_members")["constrained_columns"] == [
            "record_id",
            "canonical_index",
        ]
        for model in (ResponseCohortRecord, ResponseCohortMember):
            assert {column["name"] for column in inspector.get_columns(model.__tablename__)} == {
                column.name for column in model.__table__.columns
            }
        constraints = inspector.get_foreign_keys("response_cohort_members")
        assert len(constraints) == 4
        source_keys = [
            key for key in constraints if key["referred_table"] != "response_cohort_records"
        ]
        assert all(
            key["options"]["deferrable"] and key["options"]["initially"] == "DEFERRED"
            for key in source_keys
        )
        module.downgrade()
        assert set(inspect(connection).get_table_names()) == original
    engine.dispose()
