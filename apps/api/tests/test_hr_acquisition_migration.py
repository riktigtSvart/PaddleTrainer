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
from app.models import HRAcquisitionDeclaration

API_ROOT = Path(__file__).resolve().parents[1]
REVISION = "c5e83a9d2714"


def test_single_migration_head_extends_v24_4_without_altering_its_table():
    scripts = ScriptDirectory.from_config(Config(str(API_ROOT / "alembic.ini")))
    assert scripts.get_heads() == ["d83b9c61f204"]
    assert scripts.get_revision(REVISION).down_revision == "a6d2c4e91b70"
    table = HRAcquisitionDeclaration.__table__
    assert Base.metadata.tables[table.name] is table
    sql = str(CreateTable(table).compile(dialect=postgresql.dialect()))
    assert "declaration_json JSONB NOT NULL" in sql
    assert "FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE" in sql
    assert "UNIQUE (user_id, declaration_hash)" in sql
    index = next(iter(table.indexes))
    assert "user_id, source_provider, session_external_id, api_source_hash" in str(
        CreateIndex(index).compile(dialect=postgresql.dialect())
    )


@pytest.mark.parametrize("direction", ["upgrade", "downgrade"])
def test_migration_emits_only_its_own_additive_table_and_index(monkeypatch, direction):
    path = API_ROOT / "alembic" / "versions" / f"{REVISION}_add_hr_acquisition_declarations.py"
    spec = importlib.util.spec_from_file_location("hr_acquisition_migration_under_test", path)
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
        assert "CREATE TABLE hr_acquisition_declarations" in sql
        assert "CREATE INDEX ix_hr_acquisition_current_source" in sql
        assert "declaration_json JSONB NOT NULL" in sql
    else:
        assert "DROP TABLE hr_acquisition_declarations" in sql
    assert "heart_rate_timebase_snapshots" not in sql
    assert "UPDATE " not in sql and "DELETE FROM " not in sql and "ALTER TABLE " not in sql
