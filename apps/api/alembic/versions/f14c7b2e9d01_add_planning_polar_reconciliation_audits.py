"""add immutable planning Polar reconciliation audits

Revision ID: f14c7b2e9d01
Revises: da7e4c92b610
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f14c7b2e9d01"
down_revision: Union[str, None] = "da7e4c92b610"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "planning_plan_revision_reconciliation_audits",
        sa.Column(
            "revision_id",
            sa.Text(),
            sa.ForeignKey("planning_plan_revisions.revision_id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("audit_schema_version", sa.Text(), nullable=False),
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
        sa.Column(
            "source_workout_id",
            sa.Uuid(),
            sa.ForeignKey("planned_workouts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("capture_id", sa.Text(), nullable=False),
        sa.Column("reconciliation_schema_version", sa.Text(), nullable=False),
        sa.Column("reconciliation_rules_version", sa.Text(), nullable=False),
        sa.Column("reconciliation_content_hash_algorithm", sa.Text(), nullable=False),
        sa.Column("reconciliation_content_hash", sa.Text(), nullable=False),
        sa.Column("reconciliation_artifact_json", postgresql.JSONB(), nullable=False),
        sa.Column("reconciliation_captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_content_sha256", sa.Text(), nullable=False),
        sa.Column("source_read_content_hash", sa.Text(), nullable=False),
        sa.Column("timezone_context_name", sa.Text(), nullable=False),
        sa.Column("timezone_context_source", sa.Text(), nullable=False),
        sa.Column("reconciliation_status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("audit_content_hash_algorithm", sa.Text(), nullable=False),
        sa.Column("audit_content_hash", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "reconciliation_status = 'sync_projection_match'",
            name="ck_planning_polar_reconciliation_audit_status",
        ),
        sa.CheckConstraint(
            "length(reconciliation_content_hash) = 64",
            name="ck_planning_polar_reconciliation_content_hash_length",
        ),
        sa.CheckConstraint(
            "length(source_content_sha256) = 64",
            name="ck_planning_polar_reconciliation_source_hash_length",
        ),
        sa.CheckConstraint(
            "length(source_read_content_hash) = 64",
            name="ck_planning_polar_reconciliation_source_read_hash_length",
        ),
        sa.CheckConstraint(
            "length(audit_content_hash) = 64",
            name="ck_planning_polar_reconciliation_audit_hash_length",
        ),
    )
    op.create_index(
        "ix_planning_plan_revision_reconciliation_audits_logical_plan_id",
        "planning_plan_revision_reconciliation_audits",
        ["logical_plan_id"],
    )
    op.create_index(
        "ix_planning_plan_revision_reconciliation_audits_athlete_id",
        "planning_plan_revision_reconciliation_audits",
        ["athlete_id"],
    )
    op.create_index(
        "ix_planning_plan_revision_reconciliation_audits_capture_id",
        "planning_plan_revision_reconciliation_audits",
        ["capture_id"],
    )
    # The immutable-history rejection function was introduced by c91f7a3e2d40
    # and remains present through da7e4c92b610.
    op.execute(
        """
        CREATE TRIGGER trg_planning_plan_revision_reconciliation_audits_immutable
        BEFORE UPDATE OR DELETE ON planning_plan_revision_reconciliation_audits
        FOR EACH ROW EXECUTE FUNCTION planning_reject_immutable_plan_history_mutation()
        """
    )


def downgrade() -> None:
    if op.get_context().as_sql:
        raise RuntimeError(
            "PLANNING_POLAR_RECONCILIATION_AUDIT_DOWNGRADE_REQUIRES_ONLINE_EMPTY_TABLE_CHECK"
        )
    count = op.get_bind().execute(
        sa.text("SELECT count(*) FROM planning_plan_revision_reconciliation_audits")
    ).scalar_one()
    if count:
        raise RuntimeError(
            "PLANNING_POLAR_RECONCILIATION_AUDIT_DOWNGRADE_REFUSES_SAVED_AUDITS"
        )
    op.drop_index(
        "ix_planning_plan_revision_reconciliation_audits_capture_id",
        table_name="planning_plan_revision_reconciliation_audits",
    )
    op.drop_index(
        "ix_planning_plan_revision_reconciliation_audits_athlete_id",
        table_name="planning_plan_revision_reconciliation_audits",
    )
    op.drop_index(
        "ix_planning_plan_revision_reconciliation_audits_logical_plan_id",
        table_name="planning_plan_revision_reconciliation_audits",
    )
    op.drop_table("planning_plan_revision_reconciliation_audits")
