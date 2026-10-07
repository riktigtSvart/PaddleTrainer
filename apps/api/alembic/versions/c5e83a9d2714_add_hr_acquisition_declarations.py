"""Add scoped sensor declarations, preserving explicit correction history.

Revision ID: c5e83a9d2714
Revises: a6d2c4e91b70
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "c5e83a9d2714"
down_revision = "a6d2c4e91b70"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "hr_acquisition_declarations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_provider", sa.String(32), nullable=False),
        sa.Column("session_external_id", sa.String(200), nullable=False),
        sa.Column("exercise_external_id", sa.String(200), nullable=False),
        sa.Column("api_source_hash", sa.String(64), nullable=False),
        sa.Column("declaration_hash", sa.String(64), nullable=False),
        sa.Column("declaration_json", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "declaration_hash", name="uq_hr_acquisition_owner_hash"),
    )
    op.create_index(
        "ix_hr_acquisition_current_source",
        "hr_acquisition_declarations",
        ["user_id", "source_provider", "session_external_id", "api_source_hash"],
    )


def downgrade():
    op.drop_index("ix_hr_acquisition_current_source", table_name="hr_acquisition_declarations")
    op.drop_table("hr_acquisition_declarations")
