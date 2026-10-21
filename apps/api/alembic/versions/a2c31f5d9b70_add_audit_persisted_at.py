"""add audit persisted timestamp

Revision ID: a2c31f5d9b70
Revises: e17b9c4d2a61
Create Date: 2026-10-21

Historical audit rows deliberately remain NULL because their original
database insertion time cannot be reconstructed retrospectively.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a2c31f5d9b70"
down_revision: Union[str, Sequence[str], None] = "e17b9c4d2a61"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "planning_audit_artifacts",
        sa.Column(
            "persisted_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "planning_audit_artifacts",
        "persisted_at",
    )
