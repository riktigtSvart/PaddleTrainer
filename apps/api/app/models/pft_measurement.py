"""A recording is retained once; each processing/context revision is immutable."""
import uuid
from datetime import datetime
from sqlalchemy import (
    JSON, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index,
    Integer, LargeBinary, String, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

PFT_JSON = JSON().with_variant(JSONB(), "postgresql")


class PftRecording(Base):
    __tablename__ = "pft_recordings"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_pft_recording_owner"),
        UniqueConstraint("user_id", "recording_hash", name="uq_pft_recording_owner_hash"),
        CheckConstraint("sample_count BETWEEN 1 AND 20000", name="ck_pft_recording_sample_count"),
        Index("ix_pft_recording_owner_started", "user_id", "started_at", "id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    source_kind: Mapped[str] = mapped_column(String(32), default="TCX_UPLOAD")
    source_filename: Mapped[str] = mapped_column(String(200))
    raw_sha256: Mapped[str] = mapped_column(String(64))
    recording_hash: Mapped[str] = mapped_column(String(64))
    raw_tcx: Mapped[bytes] = mapped_column(LargeBinary)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sample_count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PftMeasurement(Base):
    __tablename__ = "pft_measurements"
    __table_args__ = (
        ForeignKeyConstraint(
            ["recording_id", "user_id"], ["pft_recordings.id", "pft_recordings.user_id"],
            name="fk_pft_measurement_recording_owner", ondelete="CASCADE",
        ),
        UniqueConstraint("user_id", "recording_id", "processing_key", name="uq_pft_measurement_version"),
        Index("ix_pft_measurement_owner_started", "user_id", "started_at", "id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    recording_id: Mapped[uuid.UUID] = mapped_column()
    processing_key: Mapped[str] = mapped_column(String(64))
    processing_manifest: Mapped[dict] = mapped_column(PFT_JSON)
    result_hash: Mapped[str] = mapped_column(String(64))
    result_json: Mapped[dict] = mapped_column(PFT_JSON)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
