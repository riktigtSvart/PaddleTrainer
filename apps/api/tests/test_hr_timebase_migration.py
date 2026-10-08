import importlib.util
import io
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from app.db.base import Base
from app.models import HeartRateTimebaseSnapshot

API_ROOT = Path(__file__).resolve().parents[1]
REVISION = "a6d2c4e91b70"


def test_alembic_has_one_linked_head_and_resolves_paths_from_project_root():
    config = Config(str(API_ROOT / "alembic.ini"))
    scripts = ScriptDirectory.from_config(config)
    assert scripts.get_heads() == ["d83b9c61f204"]
    assert scripts.get_revision(REVISION).down_revision == "f3c91ab84d27"
    assert Path(config.get_main_option("prepend_sys_path")) == API_ROOT


def test_orm_registers_postgres_jsonb_foreign_key_and_unique_scope():
    table = HeartRateTimebaseSnapshot.__table__
    assert Base.metadata.tables[table.name] is table
    sql = str(CreateTable(table).compile(dialect=postgresql.dialect()))
    assert "snapshot_json JSONB NOT NULL" in sql
    assert "FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE" in sql
    assert (
        "UNIQUE (user_id, source_provider, session_external_id, exercise_external_id, verification_decision_hash)"
        in sql
    )
    index = next(iter(table.indexes))
    assert "user_id, source_provider, session_external_id, api_source_hash" in str(
        CreateIndex(index).compile(dialect=postgresql.dialect())
    )


@pytest.mark.parametrize("direction", ["upgrade", "downgrade"])
def test_migration_emits_only_its_own_table_and_index_operations(monkeypatch, direction):
    path = API_ROOT / "alembic" / "versions" / f"{REVISION}_add_hr_timebase_snapshots.py"
    spec = importlib.util.spec_from_file_location("hr_timebase_migration_under_test", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    output = io.StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output}
    )
    monkeypatch.setattr(migration, "op", Operations(context))
    getattr(migration, direction)()
    sql = output.getvalue()
    if direction == "upgrade":
        assert "CREATE TABLE heart_rate_timebase_snapshots" in sql
        assert "CREATE INDEX ix_hr_timebase_current_source" in sql
        assert "snapshot_json JSONB NOT NULL" in sql
    else:
        assert "DROP INDEX ix_hr_timebase_current_source" in sql
        assert "DROP TABLE heart_rate_timebase_snapshots" in sql
    assert "UPDATE " not in sql and "DELETE FROM " not in sql and "ALTER TABLE " not in sql
