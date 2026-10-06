"""add trusted route environment context snapshot lineage

Revision ID: e7b5d9c2a4f1
Revises: c4a8e13f72b9
Create Date: 2026-10-06 09:40:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "e7b5d9c2a4f1"
down_revision: Union[str, Sequence[str], None] = "c4a8e13f72b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "route_trusted_environment_context_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "evidence_set_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("snapshot_schema_version", sa.String(length=16), nullable=False),
        sa.Column(
            "trusted_environment_context_schema_version",
            sa.String(length=16),
            nullable=True,
        ),
        sa.Column(
            "projection_policy_schema_version",
            sa.String(length=16),
            nullable=False,
        ),
        sa.Column("projection_status", sa.String(length=64), nullable=True),
        sa.Column("water_environment_identity_hash", sa.String(length=64), nullable=True),
        sa.Column("hydrology_trust_decision_hash", sa.String(length=64), nullable=True),
        sa.Column("projection_policy_hash", sa.String(length=64), nullable=False),
        sa.Column("water_identity_mask_hash", sa.String(length=64), nullable=False),
        sa.Column("weather_mask_hash", sa.String(length=64), nullable=False),
        sa.Column("wind_mask_hash", sa.String(length=64), nullable=False),
        sa.Column("hydrology_mask_hash", sa.String(length=64), nullable=False),
        sa.Column("aggregate_environment_mask_hash", sa.String(length=64), nullable=False),
        sa.Column("projection_hash", sa.String(length=64), nullable=False),
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
            "projection_hash",
            name="uq_route_trusted_environment_context_evidence_hash",
        ),
    )
    op.create_index(
        "ix_route_trusted_environment_context_snapshots_evidence_set",
        "route_trusted_environment_context_snapshots",
        ["evidence_set_id"],
        unique=False,
    )
    op.create_index(
        "ix_route_trusted_environment_context_snapshots_projection_hash",
        "route_trusted_environment_context_snapshots",
        ["projection_hash"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_route_trusted_environment_context_snapshots_projection_hash",
        table_name="route_trusted_environment_context_snapshots",
    )
    op.drop_index(
        "ix_route_trusted_environment_context_snapshots_evidence_set",
        table_name="route_trusted_environment_context_snapshots",
    )
    op.drop_table("route_trusted_environment_context_snapshots")
