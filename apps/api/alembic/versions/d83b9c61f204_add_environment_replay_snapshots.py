"""Add immutable full environment replay inputs.

Revision ID: d83b9c61f204
Revises: c5e83a9d2714
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "d83b9c61f204"
down_revision = "c5e83a9d2714"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "route_environment_replay_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workout_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_set_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_schema_version", sa.String(16), nullable=False),
        sa.Column("snapshot_hash", sa.String(64), nullable=False),
        sa.Column("snapshot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["workout_session_id"], ["workout_sessions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["evidence_set_id"], ["route_environment_evidence_sets.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "evidence_set_id", "snapshot_hash", name="uq_environment_replay_set_hash"
        ),
    )
    op.create_index(
        "ix_environment_replay_owner_session",
        "route_environment_replay_snapshots",
        ["user_id", "workout_session_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_environment_replay_owner_session", table_name="route_environment_replay_snapshots"
    )
    op.drop_table("route_environment_replay_snapshots")
