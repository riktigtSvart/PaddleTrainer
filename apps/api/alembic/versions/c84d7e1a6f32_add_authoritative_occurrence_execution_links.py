"""add authoritative occurrence execution links

Revision ID: c84d7e1a6f32
Revises: a91f6c3d7b20
Create Date: 2026-10-19
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c84d7e1a6f32"
down_revision: Union[str, None] = "a91f6c3d7b20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "planning_occurrence_execution_links",
        sa.Column("link_id", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.Text(), nullable=False),
        sa.Column("athlete_id", sa.Uuid(), nullable=False),
        sa.Column(
            "plan_execution_link_id",
            sa.Text(),
            nullable=False,
        ),
        sa.Column("logical_plan_id", sa.Text(), nullable=False),
        sa.Column(
            "observed_revision_id",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "authoritative_occurrence_id",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "workout_session_id",
            sa.Uuid(),
            nullable=False,
        ),
        sa.Column("link_basis", sa.Text(), nullable=False),
        sa.Column(
            "phase_reconciliation_artifact_id",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "phase_reconciliation_rules_version",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "session_source_content_hash",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "plan_source_content_hash",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "stable_source_occurrence_id",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "captured_contract_occurrence_id",
            sa.Text(),
            nullable=False,
        ),
        sa.Column("hypothesis_id", sa.Text(), nullable=False),
        sa.Column(
            "candidate_start_min_s",
            sa.Float(),
            nullable=False,
        ),
        sa.Column(
            "candidate_start_max_s",
            sa.Float(),
            nullable=False,
        ),
        sa.Column(
            "candidate_completion_min_s",
            sa.Float(),
            nullable=False,
        ),
        sa.Column(
            "candidate_completion_max_s",
            sa.Float(),
            nullable=False,
        ),
        sa.Column("clock_domain", sa.Text(), nullable=False),
        sa.Column("confirmation_id", sa.Text(), nullable=False),
        sa.Column(
            "confirmation_submitted_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "occurrence_alignment_status",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "plan_content_at_execution_status",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "provider_event_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "clock_alignment_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "actual_boundary_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "temporal_match_used",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "content_hash_algorithm",
            sa.Text(),
            nullable=False,
        ),
        sa.Column("content_hash", sa.Text(), nullable=False),

        sa.ForeignKeyConstraint(
            ["athlete_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["plan_execution_link_id"],
            ["planning_plan_execution_links.link_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["logical_plan_id"],
            ["planning_logical_plans.logical_plan_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["observed_revision_id"],
            ["planning_plan_revisions.revision_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["authoritative_occurrence_id"],
            [
                "planning_plan_occurrence_identities."
                "occurrence_id"
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workout_session_id"],
            ["workout_sessions.id"],
            ondelete="RESTRICT",
        ),

        sa.CheckConstraint(
            "link_basis = "
            "'user_confirmed_candidate_segment'",
            name="ck_planning_occ_exec_basis",
        ),
        sa.CheckConstraint(
            "occurrence_alignment_status = "
            "'user_confirmed_candidate_segment'",
            name="ck_planning_occ_exec_alignment_status",
        ),
        sa.CheckConstraint(
            "plan_content_at_execution_status = 'unverified'",
            name="ck_planning_occ_exec_plan_content_status",
        ),
        sa.CheckConstraint(
            "provider_event_verified = false",
            name="ck_planning_occ_exec_no_provider_event",
        ),
        sa.CheckConstraint(
            "clock_alignment_verified = false",
            name="ck_planning_occ_exec_no_clock_alignment",
        ),
        sa.CheckConstraint(
            "actual_boundary_verified = false",
            name="ck_planning_occ_exec_no_actual_boundary",
        ),
        sa.CheckConstraint(
            "temporal_match_used = false",
            name="ck_planning_occ_exec_no_temporal_match",
        ),
        sa.CheckConstraint(
            "candidate_start_min_s >= 0 AND "
            "candidate_start_max_s >= candidate_start_min_s",
            name="ck_planning_occ_exec_start_window",
        ),
        sa.CheckConstraint(
            "candidate_completion_min_s >= 0 AND "
            "candidate_completion_max_s "
            ">= candidate_completion_min_s",
            name="ck_planning_occ_exec_completion_window",
        ),
        sa.CheckConstraint(
            "length(session_source_content_hash) = 64",
            name="ck_planning_occ_exec_session_hash_length",
        ),
        sa.CheckConstraint(
            "length(plan_source_content_hash) = 64",
            name="ck_planning_occ_exec_plan_hash_length",
        ),
        sa.CheckConstraint(
            "length(content_hash) = 64",
            name="ck_planning_occ_exec_hash_length",
        ),
        sa.PrimaryKeyConstraint("link_id"),
        sa.UniqueConstraint(
            "plan_execution_link_id",
            "authoritative_occurrence_id",
            name="uq_planning_occ_exec_authoritative_occurrence",
        ),
        sa.UniqueConstraint(
            "plan_execution_link_id",
            "phase_reconciliation_artifact_id",
            "stable_source_occurrence_id",
            name="uq_planning_occ_exec_source_candidate",
        ),
        sa.UniqueConstraint(
            "confirmation_id",
            name="uq_planning_occ_exec_confirmation",
        ),
    )

    for name, columns in (
        (
            "ix_planning_occ_exec_athlete",
            ["athlete_id"],
        ),
        (
            "ix_planning_occ_exec_plan_execution",
            ["plan_execution_link_id"],
        ),
        (
            "ix_planning_occ_exec_revision",
            ["observed_revision_id"],
        ),
        (
            "ix_planning_occ_exec_occurrence",
            ["authoritative_occurrence_id"],
        ),
        (
            "ix_planning_occ_exec_session",
            ["workout_session_id"],
        ),
    ):
        op.create_index(
            name,
            "planning_occurrence_execution_links",
            columns,
            unique=False,
        )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION
            planning_occurrence_execution_links_immutable_guard()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                RAISE EXCEPTION
                    'planning_occurrence_execution_links is immutable';
            END;
            $$;
            """
        )
        op.execute(
            """
            CREATE TRIGGER
            trg_planning_occurrence_execution_links_immutable
            BEFORE UPDATE OR DELETE
            ON planning_occurrence_execution_links
            FOR EACH ROW
            EXECUTE FUNCTION
            planning_occurrence_execution_links_immutable_guard();
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            DROP TRIGGER IF EXISTS
            trg_planning_occurrence_execution_links_immutable
            ON planning_occurrence_execution_links;
            """
        )
        op.execute(
            """
            DROP FUNCTION IF EXISTS
            planning_occurrence_execution_links_immutable_guard();
            """
        )

    for name in (
        "ix_planning_occ_exec_session",
        "ix_planning_occ_exec_occurrence",
        "ix_planning_occ_exec_revision",
        "ix_planning_occ_exec_plan_execution",
        "ix_planning_occ_exec_athlete",
    ):
        op.drop_index(
            name,
            table_name="planning_occurrence_execution_links",
        )

    op.drop_table("planning_occurrence_execution_links")
