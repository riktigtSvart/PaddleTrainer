"""Append-only through the application API; original session rows are untouched."""
import uuid
from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, Integer, LargeBinary, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PhaseClarificationRevision(Base):
    __tablename__ = 'phase_clarification_revisions'
    __table_args__ = (
        UniqueConstraint('session_id', 'sequence', name='uq_phase_clarification_sequence'),
        UniqueConstraint('session_id', 'request_sha256', name='uq_phase_clarification_request'),
        CheckConstraint('sequence > 0', name='ck_phase_clarification_sequence'),
        Index('ix_phase_clarification_owner_session', 'user_id', 'session_id', 'sequence'),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('workout_sessions.id', ondelete='CASCADE'))
    sequence: Mapped[int] = mapped_column(Integer)
    previous_revision_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    artifact_id: Mapped[str] = mapped_column(String(100))
    rules_version: Mapped[str] = mapped_column(String(100))
    source_sha256: Mapped[str] = mapped_column(String(64))
    plan_sha256: Mapped[str] = mapped_column(String(64))
    motion_input_sha256: Mapped[str] = mapped_column(String(64))
    request_sha256: Mapped[str] = mapped_column(String(64))
    request_json: Mapped[dict] = mapped_column(JSON().with_variant(JSONB(), 'postgresql'))
    evidence_sha256: Mapped[str] = mapped_column(String(64))
    evidence_gzip: Mapped[bytes] = mapped_column(LargeBinary)
    record_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
