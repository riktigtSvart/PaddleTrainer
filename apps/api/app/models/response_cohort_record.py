"""Immutable cohort archives and complete, owner-bound source membership."""

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ResponseCohortRecord(Base):
    __tablename__ = "response_cohort_records"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "record_schema_version", "record_hash", name="uq_cohort_owner_version_hash"
        ),
        UniqueConstraint("id", "user_id", name="uq_cohort_record_owner"),
        CheckConstraint("member_count BETWEEN 1 AND 20", name="ck_cohort_member_count"),
        Index("ix_cohort_owner_created", "user_id", "created_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    record_schema_version: Mapped[str] = mapped_column(String(16))
    task: Mapped[str] = mapped_column(String(64))
    request_manifest_hash: Mapped[str] = mapped_column(String(64))
    cohort_index_hash: Mapped[str] = mapped_column(String(64))
    record_hash: Mapped[str] = mapped_column(String(64))
    member_count: Mapped[int] = mapped_column(Integer)
    record_json: Mapped[dict] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ResponseCohortMember(Base):
    __tablename__ = "response_cohort_members"
    __table_args__ = (
        ForeignKeyConstraint(
            ["record_id", "user_id"],
            ["response_cohort_records.id", "response_cohort_records.user_id"],
            name="fk_cohort_member_record_owner",
            ondelete="CASCADE",
        ),
        UniqueConstraint("record_id", "workout_session_id", name="uq_cohort_member_workout"),
        UniqueConstraint("record_id", "replay_snapshot_id", name="uq_cohort_member_replay"),
        UniqueConstraint("record_id", "evidence_set_id", name="uq_cohort_member_evidence"),
        CheckConstraint("canonical_index BETWEEN 0 AND 19", name="ck_cohort_member_index"),
        Index("ix_cohort_member_workout", "workout_session_id"),
        Index("ix_cohort_member_replay", "replay_snapshot_id"),
        Index("ix_cohort_member_evidence", "evidence_set_id"),
    )

    record_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    canonical_index: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column()
    # Deferred NO ACTION prevents source deletion from leaving an incomplete archive,
    # while allowing owner deletion to cascade both archives and sources in any order.
    workout_session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "workout_sessions.id",
            ondelete="NO ACTION",
            deferrable=True,
            initially="DEFERRED",
        )
    )
    replay_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "route_environment_replay_snapshots.id",
            ondelete="NO ACTION",
            deferrable=True,
            initially="DEFERRED",
        )
    )
    evidence_set_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "route_environment_evidence_sets.id",
            ondelete="NO ACTION",
            deferrable=True,
            initially="DEFERRED",
        )
    )
    provider: Mapped[str] = mapped_column(String(32))
    session_external_id: Mapped[str] = mapped_column(String(200))
