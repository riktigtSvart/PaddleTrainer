from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from enum import Enum
import math
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ...domain.common.enums import (
    KnowledgeStatus,
    ProvenanceKind,
)
from ...domain.common.time import to_utc
from ...domain.evidence.models import (
    EvidenceConflictError,
    EvidenceItem,
    EvidenceQuality,
    SourceRecordRef,
    create_evidence_item,
)
from ..persistence.sqlalchemy_models import (
    PlanningEvidenceItemRow,
)


def _uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(
            "Evidence athlete_id must be a UUID."
        ) from exc


def _db_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _json_value(value):
    """Thaw EvidenceItem payload into strict JSON-compatible values."""

    if value is None:
        return None

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        return value

    if isinstance(value, int):
        return value

    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(
                "Evidence payload cannot persist NaN or infinity."
            )
        return value

    if isinstance(value, Enum):
        return _json_value(value.value)

    if isinstance(value, Mapping):
        result = {}
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError(
                    "Evidence payload JSON object keys "
                    "must be strings."
                )
            result[key] = _json_value(child)
        return result

    if isinstance(value, (tuple, list)):
        return [
            _json_value(child)
            for child in value
        ]

    raise ValueError(
        "Evidence payload contains a non-JSON value: "
        f"{type(value).__name__}."
    )


def _same_semantic_evidence(
    left: EvidenceItem,
    right: EvidenceItem,
) -> bool:
    """created_at is intentionally non-semantic in EvidenceItem hashing."""

    return (
        left.evidence_id == right.evidence_id
        and left.athlete_id == right.athlete_id
        and left.evidence_type == right.evidence_type
        and left.observed_at == right.observed_at
        and left.available_at == right.available_at
        and left.source_ref == right.source_ref
        and left.provenance == right.provenance
        and left.knowledge_status == right.knowledge_status
        and left.quality == right.quality
        and left.payload == right.payload
        and left.content_hash_algorithm
        == right.content_hash_algorithm
        and left.content_hash == right.content_hash
    )


class SqlAlchemyEvidenceRepository:
    """Immutable production persistence for planning EvidenceItem values.

    The repository flushes but never commits. Transaction ownership belongs
    to the application service.
    """

    def __init__(self, session) -> None:
        self._session = session

    async def save(
        self,
        item: EvidenceItem,
    ) -> EvidenceItem:
        if not item.verify_content_hash():
            raise ValueError(
                "Evidence item content hash does not verify."
            )

        result = await self._session.execute(
            select(PlanningEvidenceItemRow).where(
                PlanningEvidenceItemRow.evidence_id
                == item.evidence_id
            )
        )
        row = result.scalar_one_or_none()

        if row is not None:
            current = self._from_row(row)

            if _same_semantic_evidence(current, item):
                # Preserve the originally persisted created_at value.
                return current

            raise EvidenceConflictError(
                "Immutable evidence identity already exists "
                "with different content."
            )

        source_hash = item.source_ref.source_content_hash
        if source_hash is not None:
            if (
                len(source_hash) != 64
                or any(
                    char not in "0123456789abcdef"
                    for char in source_hash
                )
            ):
                raise ValueError(
                    "Evidence source_content_hash must be "
                    "a lowercase SHA-256 digest."
                )

        self._session.add(
            PlanningEvidenceItemRow(
                evidence_id=item.evidence_id,
                athlete_id=_uuid(item.athlete_id),
                evidence_type=item.evidence_type,
                observed_at=item.observed_at,
                available_at=item.available_at,
                created_at=item.created_at,
                source_system=item.source_ref.source_system,
                source_record_id=item.source_ref.source_record_id,
                source_version=item.source_ref.source_version,
                source_content_hash=source_hash,
                provenance=item.provenance.value,
                knowledge_status=item.knowledge_status.value,
                quality=item.quality.value,
                payload_json=_json_value(item.payload),
                content_hash_algorithm=item.content_hash_algorithm,
                content_hash=item.content_hash,
            )
        )

        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise EvidenceConflictError(
                "Planning evidence insert conflict."
            ) from exc

        return item

    async def list_available(
        self,
        *,
        athlete_id: str,
        information_cutoff_at: datetime,
    ) -> tuple[EvidenceItem, ...]:
        cutoff = to_utc(
            information_cutoff_at,
            field_name="information_cutoff_at",
        )

        result = await self._session.execute(
            select(PlanningEvidenceItemRow)
            .where(
                PlanningEvidenceItemRow.athlete_id
                == _uuid(athlete_id),
                PlanningEvidenceItemRow.available_at <= cutoff,
                PlanningEvidenceItemRow.observed_at <= cutoff,
            )
            .order_by(
                PlanningEvidenceItemRow.available_at,
                PlanningEvidenceItemRow.evidence_id,
            )
        )

        return tuple(
            self._from_row(row)
            for row in result.scalars().all()
        )

    @staticmethod
    def _from_row(
        row: PlanningEvidenceItemRow,
    ) -> EvidenceItem:
        restored = create_evidence_item(
            evidence_id=row.evidence_id,
            athlete_id=str(row.athlete_id),
            evidence_type=row.evidence_type,
            observed_at=_db_utc(row.observed_at),
            available_at=_db_utc(row.available_at),
            created_at=_db_utc(row.created_at),
            source_ref=SourceRecordRef(
                source_system=row.source_system,
                source_record_id=row.source_record_id,
                source_version=row.source_version,
                source_content_hash=row.source_content_hash,
            ),
            provenance=ProvenanceKind(row.provenance),
            knowledge_status=KnowledgeStatus(
                row.knowledge_status
            ),
            quality=EvidenceQuality(row.quality),
            payload=row.payload_json,
        )

        if (
            restored.content_hash_algorithm
            != row.content_hash_algorithm
            or restored.content_hash
            != row.content_hash
        ):
            raise ValueError(
                "Persisted planning evidence does not "
                "round-trip to its stored content hash."
            )

        return restored


def build_production_evidence_repository(
    session,
) -> SqlAlchemyEvidenceRepository:
    return SqlAlchemyEvidenceRepository(session)
