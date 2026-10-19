"""add authoritative plan execution links

Revision ID: a91f6c3d7b20
Revises: e2a7c4b9d310
Create Date: 2026-10-19
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a91f6c3d7b20"
down_revision: Union[str, None] = "e2a7c4b9d310"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "planning_plan_execution_links",
        sa.Column("link_id", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.Text(), nullable=False),
        sa.Column("athlete_id", sa.Uuid(), nullable=False),
        sa.Column("logical_plan_id", sa.Text(), nullable=False),
        sa.Column("observed_revision_id", sa.Text(), nullable=False),
        sa.Column("workout_session_id", sa.Uuid(), nullable=False),
        sa.Column("source_workout_id", sa.Uuid(), nullable=False),
        sa.Column("link_basis", sa.Text(), nullable=False),
        sa.Column("provider_target_id", sa.Text(), nullable=True),
        sa.Column(
            "source_workout_content_hash",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "session_source_content_hash",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "observed_revision_content_hash",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "plan_content_at_execution_status",
            sa.Text(),
            nullable=False,
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
            ["workout_session_id"],
            ["workout_sessions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_workout_id"],
            ["planned_workouts.id"],
            ondelete="RESTRICT",
        ),

        sa.CheckConstraint(
            "link_basis IN "
            "('exact_provider_id', 'manual_confirmed')",
            name="ck_planning_plan_execution_link_basis",
        ),
        sa.CheckConstraint(
            "plan_content_at_execution_status = 'unverified'",
            name="ck_planning_plan_execution_content_status",
        ),
        sa.CheckConstraint(
            "temporal_match_used = false",
            name="ck_planning_plan_execution_no_temporal_match",
        ),
        sa.CheckConstraint(
            "(link_basis = 'exact_provider_id' "
            "AND provider_target_id IS NOT NULL) OR "
            "(link_basis = 'manual_confirmed' "
            "AND provider_target_id IS NULL)",
            name="ck_planning_plan_execution_provider_proof",
        ),
        sa.CheckConstraint(
            "length(source_workout_content_hash) = 64",
            name="ck_planning_plan_execution_source_hash_length",
        ),
        sa.CheckConstraint(
            "length(session_source_content_hash) = 64",
            name="ck_planning_plan_execution_session_hash_length",
        ),
        sa.CheckConstraint(
            "length(observed_revision_content_hash) = 64",
            name="ck_planning_plan_execution_revision_hash_length",
        ),
        sa.CheckConstraint(
            "length(content_hash) = 64",
            name="ck_planning_plan_execution_hash_length",
        ),

        sa.PrimaryKeyConstraint("link_id"),
        sa.UniqueConstraint(
            "workout_session_id",
            name="uq_planning_plan_execution_link_session",
        ),
    )

    op.create_index(
        "ix_planning_plan_execution_link_athlete",
        "planning_plan_execution_links",
        ["athlete_id"],
        unique=False,
    )
    op.create_index(
        "ix_planning_plan_execution_link_plan",
        "planning_plan_execution_links",
        ["logical_plan_id"],
        unique=False,
    )
    op.create_index(
        "ix_planning_plan_execution_link_revision",
        "planning_plan_execution_links",
        ["observed_revision_id"],
        unique=False,
    )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION
            planning_plan_execution_links_immutable_guard()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                RAISE EXCEPTION
                    'planning_plan_execution_links is immutable';
            END;
            $$;
            """
        )
        op.execute(
            """
            CREATE TRIGGER
            trg_planning_plan_execution_links_immutable
            BEFORE UPDATE OR DELETE
            ON planning_plan_execution_links
            FOR EACH ROW
            EXECUTE FUNCTION
            planning_plan_execution_links_immutable_guard();
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            DROP TRIGGER IF EXISTS
            trg_planning_plan_execution_links_immutable
            ON planning_plan_execution_links;
            """
        )
        op.execute(
            """
            DROP FUNCTION IF EXISTS
            planning_plan_execution_links_immutable_guard();
            """
        )

    op.drop_index(
        "ix_planning_plan_execution_link_revision",
        table_name="planning_plan_execution_links",
    )
    op.drop_index(
        "ix_planning_plan_execution_link_plan",
        table_name="planning_plan_execution_links",
    )
    op.drop_index(
        "ix_planning_plan_execution_link_athlete",
        table_name="planning_plan_execution_links",
    )
    op.drop_table("planning_plan_execution_links")
