"""initial schema

Revision ID: 0001
Revises:
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    sport_enum = postgresql.ENUM("KAYAK", "RUNNING", "SWIMMING", "STRENGTH", "CYCLING", "OTHER", name="sport_enum", create_type=False)
    session_sport_enum = postgresql.ENUM("KAYAK", "RUNNING", "SWIMMING", "STRENGTH", "CYCLING", "OTHER", name="session_sport_enum", create_type=False)
    status_enum = postgresql.ENUM("DRAFT", "PLANNED", "SCHEDULED", "COMPLETED", "SKIPPED", "CANCELLED", name="workout_status_enum", create_type=False)
    block_enum = postgresql.ENUM("WORK", "RECOVERY", "WARMUP", "COOLDOWN", "REPEAT", name="block_type_enum", create_type=False)
    sport_enum.create(op.get_bind(), checkfirst=True)
    session_sport_enum.create(op.get_bind(), checkfirst=True)
    status_enum.create(op.get_bind(), checkfirst=True)
    block_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("name", sa.String(200)),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "external_connections",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_user_id", sa.String(128)),
        sa.Column("access_token_encrypted", sa.Text(), nullable=False),
        sa.Column("refresh_token_encrypted", sa.Text()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "provider", name="uq_user_provider"),
    )
    op.create_index("ix_external_connections_user_id", "external_connections", ["user_id"])

    op.create_table(
        "planned_workouts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("planned_start_time", sa.DateTime(timezone=True)),
        sa.Column("sport", sport_enum, nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("duration_sec", sa.Integer()),
        sa.Column("distance_m", sa.Float()),
        sa.Column("intensity_type", sa.String(32)),
        sa.Column("status", status_enum, nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("polar_target_id", sa.String(128)),
        sa.Column("raw_data", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_planned_workouts_user_id", "planned_workouts", ["user_id"])
    op.create_index("ix_planned_workouts_date", "planned_workouts", ["date"])
    op.create_index("ix_planned_workouts_polar_target_id", "planned_workouts", ["polar_target_id"])

    op.create_table(
        "workout_blocks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workout_id", sa.Uuid(), sa.ForeignKey("planned_workouts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parent_block_id", sa.Uuid(), sa.ForeignKey("workout_blocks.id")),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("block_type", block_enum, nullable=False),
        sa.Column("name", sa.String(120)),
        sa.Column("duration_sec", sa.Integer()),
        sa.Column("distance_m", sa.Float()),
        sa.Column("intensity_type", sa.String(32)),
        sa.Column("intensity_min", sa.Float()),
        sa.Column("intensity_max", sa.Float()),
        sa.Column("repeat_count", sa.Integer()),
    )
    op.create_index("ix_workout_blocks_workout_id", "workout_blocks", ["workout_id"])

    op.create_table(
        "workout_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("planned_workout_id", sa.Uuid(), sa.ForeignKey("planned_workouts.id")),
        sa.Column("external_provider", sa.String(32), nullable=False),
        sa.Column("external_id", sa.String(128), nullable=False),
        sa.Column("sport", session_sport_enum, nullable=False),
        sa.Column("name", sa.String(200)),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("duration_sec", sa.Integer()),
        sa.Column("distance_m", sa.Float()),
        sa.Column("calories", sa.Float()),
        sa.Column("avg_hr", sa.Float()),
        sa.Column("max_hr", sa.Float()),
        sa.Column("avg_speed", sa.Float()),
        sa.Column("max_speed", sa.Float()),
        sa.Column("avg_cadence", sa.Float()),
        sa.Column("max_cadence", sa.Float()),
        sa.Column("avg_power", sa.Float()),
        sa.Column("max_power", sa.Float()),
        sa.Column("cardio_load", sa.Float()),
        sa.Column("perceived_load", sa.Float()),
        sa.Column("rpe", sa.Float()),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("external_provider", "external_id", name="uq_external_session"),
    )
    op.create_index("ix_workout_sessions_user_id", "workout_sessions", ["user_id"])
    op.create_index("ix_workout_sessions_started_at", "workout_sessions", ["started_at"])


def downgrade() -> None:
    op.drop_table("workout_sessions")
    op.drop_table("workout_blocks")
    op.drop_table("planned_workouts")
    op.drop_table("external_connections")
    op.drop_table("users")
    for name in ["block_type_enum", "workout_status_enum", "session_sport_enum", "sport_enum"]:
        postgresql.ENUM(name=name).drop(op.get_bind(), checkfirst=True)
