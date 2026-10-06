"""add hydrology relation decision lineage and trusted projection link

Revision ID: f3c91ab84d27
Revises: e7b5d9c2a4f1
Create Date: 2026-10-06 15:20:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f3c91ab84d27"
down_revision: Union[str, Sequence[str], None] = "e7b5d9c2a4f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "route_hydrology_relation_decision_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "evidence_set_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("snapshot_schema_version", sa.String(length=16), nullable=False),
        sa.Column("relation_catalog_schema_version", sa.String(length=16), nullable=True),
        sa.Column("relation_catalog_provider", sa.String(length=128), nullable=True),
        sa.Column("relation_catalog_product", sa.String(length=256), nullable=True),
        sa.Column("relation_evidence_schema_version", sa.String(length=16), nullable=True),
        sa.Column("relation_aware_context_schema_version", sa.String(length=16), nullable=True),
        sa.Column("relation_evidence_status", sa.String(length=64), nullable=True),
        sa.Column("relation_aware_context_status", sa.String(length=64), nullable=True),
        sa.Column("hydrology_source_resolution_hash", sa.String(length=64), nullable=True),
        sa.Column("relation_catalog_hash", sa.String(length=64), nullable=False),
        sa.Column("relation_policy_hash", sa.String(length=64), nullable=False),
        sa.Column("relation_decision_hash", sa.String(length=64), nullable=False),
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
            "relation_decision_hash",
            name="uq_route_hydrology_relation_decision_evidence_hash",
        ),
    )
    op.create_index(
        "ix_route_hydrology_relation_decision_evidence_set",
        "route_hydrology_relation_decision_snapshots",
        ["evidence_set_id"],
        unique=False,
    )
    op.create_index(
        "ix_route_hydrology_relation_decision_hash",
        "route_hydrology_relation_decision_snapshots",
        ["relation_decision_hash"],
        unique=False,
    )
    op.add_column(
        "route_trusted_environment_context_snapshots",
        sa.Column(
            "hydrology_relation_decision_hash",
            sa.String(length=64),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_route_trusted_environment_context_relation_decision_hash",
        "route_trusted_environment_context_snapshots",
        ["hydrology_relation_decision_hash"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_route_trusted_environment_context_relation_decision_hash",
        table_name="route_trusted_environment_context_snapshots",
    )
    op.drop_column(
        "route_trusted_environment_context_snapshots",
        "hydrology_relation_decision_hash",
    )
    op.drop_index(
        "ix_route_hydrology_relation_decision_hash",
        table_name="route_hydrology_relation_decision_snapshots",
    )
    op.drop_index(
        "ix_route_hydrology_relation_decision_evidence_set",
        table_name="route_hydrology_relation_decision_snapshots",
    )
    op.drop_table("route_hydrology_relation_decision_snapshots")
