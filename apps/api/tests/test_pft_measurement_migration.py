import importlib.util
import io
from pathlib import Path

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.db.base import Base
from app.models.entities import User
from app.models.pft_measurement import PftMeasurement, PftRecording

ROOT = Path(__file__).resolve().parents[1]


def migration():
    p = ROOT/"alembic/versions/b8e4d6a10f32_add_pft_measurements.py"
    spec = importlib.util.spec_from_file_location("pft_migration", p)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_single_head_extends_the_existing_cohort_revision():
    scripts = ScriptDirectory.from_config(Config(str(ROOT/"alembic.ini")))
    assert scripts.get_heads() == ["a91f6c3d7b20"]
    current = scripts.get_revision("a91f6c3d7b20")
    assert current is not None
    assert current.down_revision == "e2a7c4b9d310"
    assert scripts.get_revision("da7e4c92b610").down_revision == "c91f7a3e2d40"
    assert scripts.get_revision("c91f7a3e2d40").down_revision == "b8e4d6a10f32"
    assert scripts.get_revision("b8e4d6a10f32").down_revision == "e4f7a92c1836"
    assert scripts.get_revision("e4f7a92c1836").down_revision == "d83b9c61f204"


def test_models_register_jsonb_and_composite_owner_constraints():
    for model in (PftRecording, PftMeasurement):
        assert Base.metadata.tables[model.__tablename__] is model.__table__
    source = str(CreateTable(PftRecording.__table__).compile(dialect=postgresql.dialect()))
    record = str(CreateTable(PftMeasurement.__table__).compile(dialect=postgresql.dialect()))
    assert "raw_tcx BYTEA NOT NULL" in source
    assert "UNIQUE (user_id, recording_hash)" in source
    assert "processing_manifest JSONB NOT NULL" in record
    assert "result_json JSONB NOT NULL" in record
    assert "FOREIGN KEY(recording_id, user_id) REFERENCES pft_recordings (id, user_id)" in record
    assert "UNIQUE (user_id, recording_id, processing_key)" in record


def test_postgres_ddl_only_adds_pft_tables(monkeypatch):
    module = migration()
    output = io.StringIO()
    context = MigrationContext.configure(dialect_name="postgresql",
        opts={"as_sql": True, "output_buffer": output})
    monkeypatch.setattr(module, "op", Operations(context))
    module.upgrade()
    sql = output.getvalue()
    assert "CREATE TABLE pft_recordings" in sql
    assert "CREATE TABLE pft_measurements" in sql
    for forbidden in ("ALTER TABLE users", "ALTER TABLE workout_sessions", "UPDATE ", "DELETE FROM "):
        assert forbidden not in sql


def test_executed_migration_preserves_user_data_and_model_columns(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    User.__table__.create(engine)
    module = migration()
    with engine.begin() as connection:
        monkeypatch.setattr(module, "op", Operations(MigrationContext.configure(connection)))
        module.upgrade()
        inspector = inspect(connection)
        assert set(inspector.get_table_names()) == {"users", "pft_recordings", "pft_measurements"}
        for model in (PftRecording, PftMeasurement):
            assert {c["name"] for c in inspector.get_columns(model.__tablename__)} == set(model.__table__.columns.keys())
        module.downgrade()
        assert set(inspect(connection).get_table_names()) == {"users"}
    engine.dispose()
