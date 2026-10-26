"""Content-addressed provider snapshots, separate from mutable calendar projections."""

from datetime import UTC, datetime

from sqlalchemy import select

from app.models.entities import ProviderDataRecord
from app.planning.domain.common.serialization import compute_content_hash


async def archive_payload(db, user, category, payload, *, first=None, last=None):
    content_hash = compute_content_hash(payload, exclude_fields=frozenset())
    record_id = "sync:" + content_hash
    existing = (await db.execute(select(ProviderDataRecord.id).where(
        ProviderDataRecord.user_id == user.id,
        ProviderDataRecord.provider == "POLAR",
        ProviderDataRecord.data_type == category,
        ProviderDataRecord.provider_record_id == record_id,
    ))).scalar_one_or_none()
    if existing is None:
        db.add(ProviderDataRecord(
            user_id=user.id, provider="POLAR", data_type=category,
            provider_record_id=record_id, raw_data=payload,
            period_start=datetime.combine(first, datetime.min.time(), UTC) if first else None,
            period_end=datetime.combine(last, datetime.min.time(), UTC) if last else None,
            fetched_at=datetime.now(UTC),
        ))
        await db.flush()
