"""Immutable full replay inputs; existing scientific evidence retains its owner."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EnvironmentReplaySnapshot(Base):
    __tablename__ = "route_environment_replay_snapshots"
    __table_args__ = (
        UniqueConstraint("evidence_set_id", "snapshot_hash", name="uq_environment_replay_set_hash"),
        Index("ix_environment_replay_owner_session", "user_id", "workout_session_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    workout_session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workout_sessions.id", ondelete="CASCADE")
    )
    evidence_set_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("route_environment_evidence_sets.id", ondelete="CASCADE")
    )
    snapshot_schema_version: Mapped[str] = mapped_column(String(16))
    snapshot_hash: Mapped[str] = mapped_column(String(64))
    snapshot_json: Mapped[dict] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
