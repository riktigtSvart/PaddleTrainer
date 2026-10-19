from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from app.planning.infrastructure.persistence.sqlalchemy_models import (
    PlanningPlanExecutionLinkRow,
)


API_ROOT = Path(__file__).resolve().parents[2]


def test_execution_link_model_has_immutable_binding_columns():
    columns = set(
        PlanningPlanExecutionLinkRow.__table__.columns.keys()
    )

    assert {
        "link_id",
        "schema_version",
        "athlete_id",
        "logical_plan_id",
        "observed_revision_id",
        "workout_session_id",
        "source_workout_id",
        "link_basis",
        "provider_target_id",
        "source_workout_content_hash",
        "session_source_content_hash",
        "observed_revision_content_hash",
        "plan_content_at_execution_status",
        "temporal_match_used",
        "created_at",
        "content_hash_algorithm",
        "content_hash",
    } == columns


def test_p1_6_migration_extends_previous_head():
    scripts = ScriptDirectory.from_config(
        Config(str(API_ROOT / "alembic.ini"))
    )

    assert scripts.get_heads() == ["c84d7e1a6f32"]

    current = scripts.get_revision("c84d7e1a6f32")
    assert current is not None
    assert current.down_revision == "a91f6c3d7b20"
