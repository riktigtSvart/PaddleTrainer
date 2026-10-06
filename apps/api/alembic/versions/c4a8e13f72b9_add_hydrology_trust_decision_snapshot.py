"""add hydrology trust decision snapshot lineage

Revision ID: c4a8e13f72b9
Revises: 9d0f3b7a21c4
Create Date: 2026-10-06 08:20:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c4a8e13f72b9"
down_revision: Union[str, Sequence[str], None] = "9d0f3b7a21c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "route_hydrology_trust_decision_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "evidence_set_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("snapshot_schema_version", sa.String(length=16), nullable=False),
        sa.Column("trusted_context_schema_version", sa.String(length=16), nullable=True),
        sa.Column(
            "representativeness_schema_version",
            sa.String(length=16),
            nullable=True,
        ),
        sa.Column("trust_policy_schema_version", sa.String(length=16), nullable=False),
        sa.Column("decision_status", sa.String(length=64), nullable=True),
        sa.Column("hydrology_source_resolution_hash", sa.String(length=64), nullable=True),
        sa.Column("trust_policy_hash", sa.String(length=64), nullable=False),
        sa.Column("representativeness_policy_hash", sa.String(length=64), nullable=False),
        sa.Column("temporal_support_mask_hash", sa.String(length=64), nullable=False),
        sa.Column("decision_hash", sa.String(length=64), nullable=False),
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
            "decision_hash",
            name="uq_route_hydrology_trust_decision_evidence_hash",
        ),
    )
    op.create_index(
        "ix_route_hydrology_trust_decision_snapshots_evidence_set",
        "route_hydrology_trust_decision_snapshots",
        ["evidence_set_id"],
        unique=False,
    )
    op.create_index(
        "ix_route_hydrology_trust_decision_snapshots_decision_hash",
        "route_hydrology_trust_decision_snapshots",
        ["decision_hash"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_route_hydrology_trust_decision_snapshots_decision_hash",
        table_name="route_hydrology_trust_decision_snapshots",
    )
    op.drop_index(
        "ix_route_hydrology_trust_decision_snapshots_evidence_set",
        table_name="route_hydrology_trust_decision_snapshots",
    )
    op.drop_table("route_hydrology_trust_decision_snapshots")
