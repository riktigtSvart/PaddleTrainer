"""add planning audit artifacts

Revision ID: e2a7c4b9d310
Revises: f14c7b2e9d01
Create Date: 2026-10-19
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e2a7c4b9d310"
down_revision: Union[str, None] = "f14c7b2e9d01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "planning_audit_artifacts",
        sa.Column(
            "artifact_kind",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "artifact_id",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "athlete_id",
            sa.Uuid(),
            nullable=False,
        ),
        sa.Column(
            "schema_version",
            sa.Text(),
            nullable=False,
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
        sa.Column(
            "content_hash",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "contract_json",
            sa.Text(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["athlete_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "artifact_kind",
            "artifact_id",
        ),
    )

    op.create_index(
        "ix_planning_audit_athlete_kind_created",
        "planning_audit_artifacts",
        [
            "athlete_id",
            "artifact_kind",
            "created_at",
        ],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_planning_audit_athlete_kind_created",
        table_name="planning_audit_artifacts",
    )
    op.drop_table("planning_audit_artifacts")
