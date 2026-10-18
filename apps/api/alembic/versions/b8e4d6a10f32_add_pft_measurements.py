"""Add PFT recording retention and immutable processing revisions.

Revision ID: b8e4d6a10f32
Revises: e4f7a92c1836
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "b8e4d6a10f32"
down_revision = "e4f7a92c1836"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "pft_recordings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("source_kind", sa.String(32), nullable=False),
        sa.Column("source_filename", sa.String(200), nullable=False),
        sa.Column("raw_sha256", sa.String(64), nullable=False),
        sa.Column("recording_hash", sa.String(64), nullable=False),
        sa.Column("raw_tcx", sa.LargeBinary(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "user_id", name="uq_pft_recording_owner"),
        sa.UniqueConstraint("user_id", "recording_hash", name="uq_pft_recording_owner_hash"),
        sa.CheckConstraint("sample_count BETWEEN 1 AND 20000", name="ck_pft_recording_sample_count"),
    )
    op.create_index("ix_pft_recording_owner_started", "pft_recordings", ["user_id", "started_at", "id"])
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    op.create_table(
        "pft_measurements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("recording_id", sa.Uuid(), nullable=False),
        sa.Column("processing_key", sa.String(64), nullable=False),
        sa.Column("processing_manifest", json_type, nullable=False),
        sa.Column("result_hash", sa.String(64), nullable=False),
        sa.Column("result_json", json_type, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recording_id", "user_id"], ["pft_recordings.id", "pft_recordings.user_id"],
                                name="fk_pft_measurement_recording_owner", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "recording_id", "processing_key", name="uq_pft_measurement_version"),
    )
    op.create_index("ix_pft_measurement_owner_started", "pft_measurements", ["user_id", "started_at", "id"])


def downgrade():
    op.drop_index("ix_pft_measurement_owner_started", table_name="pft_measurements")
    op.drop_table("pft_measurements")
    op.drop_index("ix_pft_recording_owner_started", table_name="pft_recordings")
    op.drop_table("pft_recordings")
