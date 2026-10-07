import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class HRAcquisitionDeclaration(Base):
    __tablename__ = "hr_acquisition_declarations"
    __table_args__ = (
        UniqueConstraint("user_id", "declaration_hash", name="uq_hr_acquisition_owner_hash"),
        Index(
            "ix_hr_acquisition_current_source",
            "user_id",
            "source_provider",
            "session_external_id",
            "api_source_hash",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    source_provider: Mapped[str] = mapped_column(String(32))
    session_external_id: Mapped[str] = mapped_column(String(200))
    exercise_external_id: Mapped[str] = mapped_column(String(200))
    api_source_hash: Mapped[str] = mapped_column(String(64))
    declaration_hash: Mapped[str] = mapped_column(String(64))
    declaration_json: Mapped[dict] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
