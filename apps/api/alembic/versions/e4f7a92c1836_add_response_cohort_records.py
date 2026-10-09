"""Add immutable cohort archives and complete source membership.

Revision ID: e4f7a92c1836
Revises: d83b9c61f204
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "e4f7a92c1836"
down_revision = "d83b9c61f204"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "response_cohort_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("record_schema_version", sa.String(16), nullable=False),
        sa.Column("task", sa.String(64), nullable=False),
        sa.Column("request_manifest_hash", sa.String(64), nullable=False),
        sa.Column("cohort_index_hash", sa.String(64), nullable=False),
        sa.Column("record_hash", sa.String(64), nullable=False),
        sa.Column("member_count", sa.Integer(), nullable=False),
        sa.Column(
            "record_json", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "record_schema_version", "record_hash", name="uq_cohort_owner_version_hash"
        ),
        sa.UniqueConstraint("id", "user_id", name="uq_cohort_record_owner"),
        sa.CheckConstraint("member_count BETWEEN 1 AND 20", name="ck_cohort_member_count"),
    )
    op.create_index(
        "ix_cohort_owner_created", "response_cohort_records", ["user_id", "created_at", "id"]
    )
    op.create_table(
        "response_cohort_members",
        sa.Column("record_id", sa.Uuid(), nullable=False),
        sa.Column("canonical_index", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("workout_session_id", sa.Uuid(), nullable=False),
        sa.Column("replay_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_set_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("session_external_id", sa.String(200), nullable=False),
        sa.ForeignKeyConstraint(
            ["record_id", "user_id"],
            ["response_cohort_records.id", "response_cohort_records.user_id"],
            name="fk_cohort_member_record_owner",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workout_session_id"],
            ["workout_sessions.id"],
            ondelete="NO ACTION",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.ForeignKeyConstraint(
            ["replay_snapshot_id"],
            ["route_environment_replay_snapshots.id"],
            ondelete="NO ACTION",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_set_id"],
            ["route_environment_evidence_sets.id"],
            ondelete="NO ACTION",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.PrimaryKeyConstraint("record_id", "canonical_index"),
        sa.UniqueConstraint("record_id", "workout_session_id", name="uq_cohort_member_workout"),
        sa.UniqueConstraint("record_id", "replay_snapshot_id", name="uq_cohort_member_replay"),
        sa.UniqueConstraint("record_id", "evidence_set_id", name="uq_cohort_member_evidence"),
        sa.CheckConstraint("canonical_index BETWEEN 0 AND 19", name="ck_cohort_member_index"),
    )
    for suffix, column in (
        ("workout", "workout_session_id"),
        ("replay", "replay_snapshot_id"),
        ("evidence", "evidence_set_id"),
    ):
        op.create_index("ix_cohort_member_" + suffix, "response_cohort_members", [column])


def downgrade() -> None:
    # Explicit downgrade discards only the new archive; source/HR tables remain.
    for suffix in ("evidence", "replay", "workout"):
        op.drop_index("ix_cohort_member_" + suffix, table_name="response_cohort_members")
    op.drop_table("response_cohort_members")
    op.drop_index("ix_cohort_owner_created", table_name="response_cohort_records")
    op.drop_table("response_cohort_records")
