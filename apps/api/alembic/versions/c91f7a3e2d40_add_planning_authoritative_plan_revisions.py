"""add planning authoritative plan revisions

Revision ID: c91f7a3e2d40
Revises: b8e4d6a10f32
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c91f7a3e2d40"
down_revision: Union[str, None] = "b8e4d6a10f32"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "planning_logical_plans",
        sa.Column("logical_plan_id", sa.Text(), primary_key=True),
        sa.Column(
            "athlete_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "source_workout_id",
            sa.Uuid(),
            sa.ForeignKey("planned_workouts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("current_revision_id", sa.Text(), nullable=True),
        sa.Column(
            "current_revision_number",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("authority_established_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "source_workout_id",
            name="uq_planning_logical_plans_source_workout_id",
        ),
        sa.CheckConstraint(
            "(current_revision_id IS NULL AND current_revision_number = 0 "
            "AND authority_established_at IS NULL) OR "
            "(current_revision_id IS NOT NULL AND current_revision_number >= 1 "
            "AND authority_established_at IS NOT NULL)",
            name="ck_planning_logical_plan_pointer_state",
        ),
    )
    op.create_index(
        "ix_planning_logical_plans_athlete_id",
        "planning_logical_plans",
        ["athlete_id"],
    )

    op.create_table(
        "planning_plan_revisions",
        sa.Column("revision_id", sa.Text(), primary_key=True),
        sa.Column(
            "logical_plan_id",
            sa.Text(),
            sa.ForeignKey("planning_logical_plans.logical_plan_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "athlete_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column(
            "previous_revision_id",
            sa.Text(),
            sa.ForeignKey("planning_plan_revisions.revision_id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("origin", sa.Text(), nullable=False),
        sa.Column("history_claim", sa.Text(), nullable=False),
        sa.Column("authority_established_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("contract_schema_version", sa.Text(), nullable=False),
        sa.Column("canonical_contract_json", postgresql.JSONB(), nullable=False),
        sa.Column("contract_content_hash", sa.Text(), nullable=False),
        sa.Column("revision_content_hash", sa.Text(), nullable=False),
        sa.Column("source_capture_id", sa.Text(), nullable=True),
        sa.Column("source_capture_hash", sa.Text(), nullable=True),
        sa.Column("source_read_content_hash", sa.Text(), nullable=True),
        sa.Column("source_content_sha256", sa.Text(), nullable=True),
        sa.Column("source_external_contract_plan_id", sa.Text(), nullable=True),
        sa.Column("source_external_contract_plan_revision", sa.Integer(), nullable=True),
        sa.Column("context_hash", sa.Text(), nullable=True),
        sa.Column("decision_hash", sa.Text(), nullable=True),
        sa.Column("rationale_hash", sa.Text(), nullable=True),
        sa.Column("instruction_hash", sa.Text(), nullable=True),
        sa.UniqueConstraint(
            "logical_plan_id",
            "revision_number",
            name="uq_planning_plan_revision_number",
        ),
        sa.CheckConstraint(
            "revision_number >= 1",
            name="ck_planning_plan_revision_number_positive",
        ),
        sa.CheckConstraint(
            "origin IN ('adopted_current_state', 'planner_created', 'external_reconciled')",
            name="ck_planning_plan_revision_origin",
        ),
        sa.CheckConstraint(
            "history_claim IN ('current_state_baseline_only', 'verified_from_authority_start')",
            name="ck_planning_plan_revision_history_claim",
        ),
        sa.CheckConstraint(
            "origin <> 'adopted_current_state' OR "
            "(revision_number = 1 AND previous_revision_id IS NULL "
            "AND history_claim = 'current_state_baseline_only' "
            "AND source_capture_id IS NOT NULL "
            "AND source_capture_hash IS NOT NULL "
            "AND source_read_content_hash IS NOT NULL "
            "AND source_content_sha256 IS NOT NULL "
            "AND source_external_contract_plan_id IS NOT NULL "
            "AND source_external_contract_plan_revision IS NOT NULL "
            "AND context_hash IS NULL AND decision_hash IS NULL "
            "AND rationale_hash IS NULL AND instruction_hash IS NULL)",
            name="ck_planning_adoption_revision_semantics",
        ),
        sa.CheckConstraint(
            "origin <> 'planner_created' OR "
            "(history_claim = 'verified_from_authority_start' "
            "AND source_capture_id IS NULL AND source_capture_hash IS NULL "
            "AND source_read_content_hash IS NULL AND source_content_sha256 IS NULL "
            "AND source_external_contract_plan_id IS NULL "
            "AND source_external_contract_plan_revision IS NULL "
            "AND context_hash IS NOT NULL AND decision_hash IS NOT NULL "
            "AND rationale_hash IS NOT NULL AND instruction_hash IS NOT NULL)",
            name="ck_planning_planner_revision_semantics",
        ),
    )
    op.create_index(
        "ix_planning_plan_revisions_logical_plan_id",
        "planning_plan_revisions",
        ["logical_plan_id"],
    )
    op.create_index(
        "ix_planning_plan_revisions_athlete_id",
        "planning_plan_revisions",
        ["athlete_id"],
    )
    op.create_index(
        "ix_planning_plan_revisions_previous_revision_id",
        "planning_plan_revisions",
        ["previous_revision_id"],
    )

    op.create_foreign_key(
        "fk_planning_logical_plans_current_revision_id",
        "planning_logical_plans",
        "planning_plan_revisions",
        ["current_revision_id"],
        ["revision_id"],
        ondelete="RESTRICT",
    )

    op.create_table(
        "planning_plan_occurrence_identities",
        sa.Column("occurrence_id", sa.Text(), primary_key=True),
        sa.Column(
            "logical_plan_id",
            sa.Text(),
            sa.ForeignKey("planning_logical_plans.logical_plan_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "first_revision_id",
            sa.Text(),
            sa.ForeignKey("planning_plan_revisions.revision_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_planning_plan_occurrence_identities_logical_plan_id",
        "planning_plan_occurrence_identities",
        ["logical_plan_id"],
    )
    op.create_index(
        "ix_planning_plan_occurrence_identities_first_revision_id",
        "planning_plan_occurrence_identities",
        ["first_revision_id"],
    )

    op.create_table(
        "planning_plan_revision_occurrences",
        sa.Column(
            "revision_id",
            sa.Text(),
            sa.ForeignKey("planning_plan_revisions.revision_id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column(
            "occurrence_id",
            sa.Text(),
            sa.ForeignKey(
                "planning_plan_occurrence_identities.occurrence_id",
                ondelete="RESTRICT",
            ),
            primary_key=True,
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("lineage_kind", sa.Text(), nullable=False),
        sa.Column("source_capture_occurrence_id", sa.Text(), nullable=True),
        sa.UniqueConstraint(
            "revision_id",
            "ordinal",
            name="uq_planning_plan_revision_occurrence_ordinal",
        ),
        sa.CheckConstraint(
            "ordinal >= 0",
            name="ck_planning_plan_revision_occurrence_ordinal_nonnegative",
        ),
        sa.CheckConstraint(
            "lineage_kind IN ('new', 'preserved')",
            name="ck_planning_plan_revision_occurrence_lineage_kind",
        ),
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION planning_reject_immutable_plan_history_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'planning authoritative history is immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    for table_name in (
        "planning_plan_revisions",
        "planning_plan_occurrence_identities",
        "planning_plan_revision_occurrences",
    ):
        op.execute(
            f"""
            CREATE TRIGGER trg_{table_name}_immutable
            BEFORE UPDATE OR DELETE ON {table_name}
            FOR EACH ROW EXECUTE FUNCTION planning_reject_immutable_plan_history_mutation()
            """
        )


def downgrade() -> None:
    op.drop_table("planning_plan_revision_occurrences")
    op.drop_index(
        "ix_planning_plan_occurrence_identities_first_revision_id",
        table_name="planning_plan_occurrence_identities",
    )
    op.drop_index(
        "ix_planning_plan_occurrence_identities_logical_plan_id",
        table_name="planning_plan_occurrence_identities",
    )
    op.drop_table("planning_plan_occurrence_identities")
    op.drop_constraint(
        "fk_planning_logical_plans_current_revision_id",
        "planning_logical_plans",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_planning_plan_revisions_previous_revision_id",
        table_name="planning_plan_revisions",
    )
    op.drop_index(
        "ix_planning_plan_revisions_athlete_id",
        table_name="planning_plan_revisions",
    )
    op.drop_index(
        "ix_planning_plan_revisions_logical_plan_id",
        table_name="planning_plan_revisions",
    )
    op.drop_table("planning_plan_revisions")
    op.execute("DROP FUNCTION IF EXISTS planning_reject_immutable_plan_history_mutation()")
    op.drop_index(
        "ix_planning_logical_plans_athlete_id",
        table_name="planning_logical_plans",
    )
    op.drop_table("planning_logical_plans")
