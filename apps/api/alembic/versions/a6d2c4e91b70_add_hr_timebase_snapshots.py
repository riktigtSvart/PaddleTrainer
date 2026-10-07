"""Add athlete-owned, immutable HR export timebase snapshots.

Revision ID: a6d2c4e91b70
Revises: f3c91ab84d27
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "a6d2c4e91b70"
down_revision = "f3c91ab84d27"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "heart_rate_timebase_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_provider", sa.String(32), nullable=False),
        sa.Column("session_external_id", sa.String(200), nullable=False),
        sa.Column("exercise_external_id", sa.String(200), nullable=False),
        sa.Column("api_source_hash", sa.String(64), nullable=False),
        sa.Column("verification_decision_hash", sa.String(64), nullable=False),
        sa.Column("snapshot_hash", sa.String(64), nullable=False),
        sa.Column("snapshot_json", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "user_id",
            "source_provider",
            "session_external_id",
            "exercise_external_id",
            "verification_decision_hash",
            name="uq_hr_timebase_owner_provider_decision",
        ),
    )
    op.create_index(
        "ix_hr_timebase_current_source",
        "heart_rate_timebase_snapshots",
        ["user_id", "source_provider", "session_external_id", "api_source_hash"],
    )


def downgrade():
    op.drop_index("ix_hr_timebase_current_source", table_name="heart_rate_timebase_snapshots")
    op.drop_table("heart_rate_timebase_snapshots")
