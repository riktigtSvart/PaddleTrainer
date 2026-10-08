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
from app.models import EnvironmentReplaySnapshot

API_ROOT = Path(__file__).resolve().parents[1]
REVISION = "d83b9c61f204"


def test_replay_migration_is_the_single_additive_head_and_registered_jsonb_model():
    scripts = ScriptDirectory.from_config(Config(str(API_ROOT / "alembic.ini")))
    assert scripts.get_heads() == [REVISION]
    assert scripts.get_revision(REVISION).down_revision == "c5e83a9d2714"
    table = EnvironmentReplaySnapshot.__table__
    assert Base.metadata.tables[table.name] is table
    sql = str(CreateTable(table).compile(dialect=postgresql.dialect()))
    assert "snapshot_json JSONB NOT NULL" in sql
    assert "UNIQUE (evidence_set_id, snapshot_hash)" in sql
    for parent in ("users", "workout_sessions", "route_environment_evidence_sets"):
        assert f"REFERENCES {parent} (id) ON DELETE CASCADE" in sql
    assert "user_id, workout_session_id" in str(
        CreateIndex(next(iter(table.indexes))).compile(dialect=postgresql.dialect())
    )


@pytest.mark.parametrize("direction", ["upgrade", "downgrade"])
def test_upgrade_and_downgrade_change_only_the_new_replay_table(monkeypatch, direction):
    path = API_ROOT / "alembic" / "versions" / f"{REVISION}_add_environment_replay_snapshots.py"
    spec = importlib.util.spec_from_file_location("replay_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    output = io.StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output}
    )
    monkeypatch.setattr(module, "op", Operations(context))
    getattr(module, direction)()
    sql = output.getvalue()
    if direction == "upgrade":
        assert "CREATE TABLE route_environment_replay_snapshots" in sql
        assert "CREATE INDEX ix_environment_replay_owner_session" in sql
    else:
        assert "DROP TABLE route_environment_replay_snapshots" in sql
    for other in (
        "heart_rate_timebase_snapshots",
        "hr_acquisition_declarations",
        "route_environment_segments",
    ):
        assert f"CREATE TABLE {other}" not in sql and f"DROP TABLE {other}" not in sql
    assert "UPDATE " not in sql and "DELETE FROM " not in sql and "ALTER TABLE " not in sql
