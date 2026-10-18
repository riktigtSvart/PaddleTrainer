from dataclasses import dataclass


@dataclass(frozen=True)
class ColumnContract:
    name: str
    sql_type: str
    nullable: bool


@dataclass(frozen=True)
class TableContract:
    name: str
    columns: tuple[ColumnContract, ...]
    primary_key: tuple[str, ...]
    unique_constraints: tuple[tuple[str, ...], ...] = ()


AUTHORITATIVE_PLAN_SCHEMA_VERSION = 'authoritative-plan-persistence-v0.1'
AUTHORITATIVE_PLAN_IMPLEMENTATION_VERSION = 'authoritative-plan-postgres-v0.1'
ALEMBIC_BASELINE_HEAD_OBSERVED_IN_P1_0 = 'b8e4d6a10f32'
AUTHORITATIVE_PLAN_MIGRATION_REVISION = 'c91f7a3e2d40'


LOGICAL_PLANS_TABLE = TableContract(
    name='planning_logical_plans',
    columns=(
        ColumnContract('logical_plan_id', 'text', False),
        ColumnContract('athlete_id', 'uuid', False),
        ColumnContract('source_workout_id', 'uuid', True),
        ColumnContract('current_revision_id', 'text', True),
        ColumnContract('current_revision_number', 'integer', False),
        ColumnContract('authority_established_at', 'timestamptz', True),
        ColumnContract('created_at', 'timestamptz', False),
        ColumnContract('updated_at', 'timestamptz', False),
    ),
    primary_key=('logical_plan_id',),
    unique_constraints=(('source_workout_id',),),
)


PLAN_REVISIONS_TABLE = TableContract(
    name='planning_plan_revisions',
    columns=(
        ColumnContract('revision_id', 'text', False),
        ColumnContract('logical_plan_id', 'text', False),
        ColumnContract('athlete_id', 'uuid', False),
        ColumnContract('revision_number', 'integer', False),
        ColumnContract('previous_revision_id', 'text', True),
        ColumnContract('origin', 'text', False),
        ColumnContract('history_claim', 'text', False),
        ColumnContract('authority_established_at', 'timestamptz', False),
        ColumnContract('effective_from', 'timestamptz', False),
        ColumnContract('created_at', 'timestamptz', False),
        ColumnContract('contract_schema_version', 'text', False),
        ColumnContract('canonical_contract_json', 'jsonb', False),
        ColumnContract('contract_content_hash', 'text', False),
        ColumnContract('revision_content_hash', 'text', False),
        ColumnContract('source_capture_id', 'text', True),
        ColumnContract('source_capture_hash', 'text', True),
        ColumnContract('source_read_content_hash', 'text', True),
        ColumnContract('source_content_sha256', 'text', True),
        ColumnContract('source_external_contract_plan_id', 'text', True),
        ColumnContract('source_external_contract_plan_revision', 'integer', True),
        ColumnContract('context_hash', 'text', True),
        ColumnContract('decision_hash', 'text', True),
        ColumnContract('rationale_hash', 'text', True),
        ColumnContract('instruction_hash', 'text', True),
    ),
    primary_key=('revision_id',),
    unique_constraints=(('logical_plan_id', 'revision_number'),),
)


OCCURRENCE_IDENTITIES_TABLE = TableContract(
    name='planning_plan_occurrence_identities',
    columns=(
        ColumnContract('occurrence_id', 'text', False),
        ColumnContract('logical_plan_id', 'text', False),
        ColumnContract('first_revision_id', 'text', False),
        ColumnContract('created_at', 'timestamptz', False),
    ),
    primary_key=('occurrence_id',),
)


REVISION_OCCURRENCES_TABLE = TableContract(
    name='planning_plan_revision_occurrences',
    columns=(
        ColumnContract('revision_id', 'text', False),
        ColumnContract('occurrence_id', 'text', False),
        ColumnContract('ordinal', 'integer', False),
        ColumnContract('lineage_kind', 'text', False),
        ColumnContract('source_capture_occurrence_id', 'text', True),
    ),
    primary_key=('revision_id', 'occurrence_id'),
    unique_constraints=(('revision_id', 'ordinal'),),
)


SCHEMA_TABLES = (
    LOGICAL_PLANS_TABLE,
    PLAN_REVISIONS_TABLE,
    OCCURRENCE_IDENTITIES_TABLE,
    REVISION_OCCURRENCES_TABLE,
)
