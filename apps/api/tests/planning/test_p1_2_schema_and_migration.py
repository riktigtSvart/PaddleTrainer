import importlib.util
from pathlib import Path

from sqlalchemy import Text

from app.planning.domain.plan_revision.postgres_schema_contract import (
    ALEMBIC_BASELINE_HEAD_OBSERVED_IN_P1_0,
    AUTHORITATIVE_PLAN_IMPLEMENTATION_VERSION,
    AUTHORITATIVE_PLAN_MIGRATION_REVISION,
    AUTHORITATIVE_PLAN_SCHEMA_VERSION,
    LOGICAL_PLANS_TABLE,
    OCCURRENCE_IDENTITIES_TABLE,
    PLAN_REVISIONS_TABLE,
)
from app.planning.infrastructure.persistence.sqlalchemy_models import (
    PlanningLogicalPlanRow,
    PlanningPlanOccurrenceIdentityRow,
    PlanningPlanRevisionRow,
)


def _column(table, name):
    return next(item for item in table.columns if item.name == name)


def test_p1_2_corrects_planning_owned_ids_to_text_before_migration() -> None:
    assert _column(LOGICAL_PLANS_TABLE, "current_revision_id").sql_type == "text"
    assert _column(PLAN_REVISIONS_TABLE, "revision_id").sql_type == "text"
    assert _column(PLAN_REVISIONS_TABLE, "previous_revision_id").sql_type == "text"
    assert _column(OCCURRENCE_IDENTITIES_TABLE, "occurrence_id").sql_type == "text"
    assert isinstance(PlanningPlanRevisionRow.__table__.c.revision_id.type, Text)
    assert isinstance(PlanningPlanOccurrenceIdentityRow.__table__.c.occurrence_id.type, Text)


def test_revision_storage_can_round_trip_all_domain_provenance_fields() -> None:
    columns = {item.name for item in PLAN_REVISIONS_TABLE.columns}
    assert {
        "athlete_id",
        "source_external_contract_plan_id",
        "source_external_contract_plan_revision",
        "context_hash",
        "decision_hash",
        "rationale_hash",
        "instruction_hash",
    } <= columns

    orm_columns = set(PlanningPlanRevisionRow.__table__.columns.keys())
    assert columns == orm_columns


def test_logical_plan_current_pointer_has_named_foreign_key() -> None:
    column = PlanningLogicalPlanRow.__table__.c.current_revision_id
    foreign_keys = list(column.foreign_keys)
    assert len(foreign_keys) == 1
    assert foreign_keys[0].target_fullname == "planning_plan_revisions.revision_id"
    assert foreign_keys[0].constraint.name == "fk_planning_logical_plans_current_revision_id"


def test_migration_is_linear_from_observed_production_head() -> None:
    assert ALEMBIC_BASELINE_HEAD_OBSERVED_IN_P1_0 == "b8e4d6a10f32"
    assert AUTHORITATIVE_PLAN_MIGRATION_REVISION == "c91f7a3e2d40"
    assert AUTHORITATIVE_PLAN_SCHEMA_VERSION == "authoritative-plan-persistence-v0.1"
    assert AUTHORITATIVE_PLAN_IMPLEMENTATION_VERSION == "authoritative-plan-postgres-v0.1"

    path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "c91f7a3e2d40_add_planning_authoritative_plan_revisions.py"
    )
    spec = importlib.util.spec_from_file_location("p1_2_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.revision == "c91f7a3e2d40"
    assert module.down_revision == "b8e4d6a10f32"


def test_migration_does_not_mutate_operational_workout_tables() -> None:
    path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "c91f7a3e2d40_add_planning_authoritative_plan_revisions.py"
    )
    source = path.read_text(encoding="utf-8")
    assert 'op.alter_column("planned_workouts"' not in source
    assert 'op.add_column("planned_workouts"' not in source
    assert 'op.alter_column("workout_blocks"' not in source
    assert 'op.add_column("workout_blocks"' not in source
    import re
    assert len(re.findall(r'op\.create_table\(\s*\"planning_', source)) == 4
    assert "planning_reject_immutable_plan_history_mutation" in source
    assert "BEFORE UPDATE OR DELETE" in source
