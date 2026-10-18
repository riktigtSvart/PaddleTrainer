from app.planning.domain.plan_revision.postgres_schema_contract import (
    ALEMBIC_BASELINE_HEAD_OBSERVED_IN_P1_0,
    AUTHORITATIVE_PLAN_SCHEMA_VERSION,
    LOGICAL_PLANS_TABLE,
    OCCURRENCE_IDENTITIES_TABLE,
    PLAN_REVISIONS_TABLE,
    REVISION_OCCURRENCES_TABLE,
    SCHEMA_TABLES,
)


def test_p1_1_schema_contract_uses_separate_authoritative_tables() -> None:
    names = {table.name for table in SCHEMA_TABLES}
    assert names == {
        'planning_logical_plans',
        'planning_plan_revisions',
        'planning_plan_occurrence_identities',
        'planning_plan_revision_occurrences',
    }
    assert 'planned_workouts' not in names
    assert 'workout_blocks' not in names


def test_revision_number_is_unique_within_logical_plan() -> None:
    assert ('logical_plan_id', 'revision_number') in PLAN_REVISIONS_TABLE.unique_constraints


def test_source_workout_is_binding_not_revision_identity() -> None:
    assert ('source_workout_id',) in LOGICAL_PLANS_TABLE.unique_constraints
    assert 'source_workout_id' not in PLAN_REVISIONS_TABLE.primary_key


def test_occurrence_identity_is_separate_from_revision_membership() -> None:
    assert OCCURRENCE_IDENTITIES_TABLE.primary_key == ('occurrence_id',)
    assert REVISION_OCCURRENCES_TABLE.primary_key == (
        'revision_id', 'occurrence_id'
    )
    assert ('revision_id', 'ordinal') in REVISION_OCCURRENCES_TABLE.unique_constraints


def test_schema_contract_pins_observed_alembic_head_but_does_not_create_migration() -> None:
    assert ALEMBIC_BASELINE_HEAD_OBSERVED_IN_P1_0 == 'b8e4d6a10f32'
    assert AUTHORITATIVE_PLAN_SCHEMA_VERSION == 'authoritative-plan-persistence-v0.1'
