"""add hydrology source resolution snapshot

Revision ID: 9d0f3b7a21c4
Revises: 7f6c2a91d4e8
Create Date: 2026-10-05 21:50:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "9d0f3b7a21c4"
down_revision: Union[str, Sequence[str], None] = "7f6c2a91d4e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "route_hydrology_source_resolution_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "evidence_set_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("snapshot_schema_version", sa.String(length=16), nullable=False),
        sa.Column("resolution_schema_version", sa.String(length=16), nullable=True),
        sa.Column("resolution_hash", sa.String(length=64), nullable=False),
        sa.Column("snapshot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["evidence_set_id"],
            ["route_environment_evidence_sets.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "evidence_set_id",
            name="uq_route_hydrology_source_resolution_snapshot_evidence_set",
        ),
    )
    op.create_index(
        "ix_route_hydrology_source_resolution_snapshots_hash",
        "route_hydrology_source_resolution_snapshots",
        ["resolution_hash"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_route_hydrology_source_resolution_snapshots_hash",
        table_name="route_hydrology_source_resolution_snapshots",
    )
    op.drop_table("route_hydrology_source_resolution_snapshots")
