from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Mapping

from ..common.enums import KnowledgeStatus, ProvenanceKind
from ..common.serialization import (
    CONTENT_HASH_ALGORITHM,
    compute_content_hash,
    deep_freeze,
)
from ..common.time import to_utc


EVIDENCE_HASH_EXCLUDE_FIELDS = frozenset(
    {"content_hash", "evidence_id", "created_at"}
)
EVIDENCE_BUNDLE_HASH_EXCLUDE_FIELDS = frozenset(
    {"content_hash", "bundle_id", "created_at"}
)


class EvidenceQuality(StrEnum):
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    UNKNOWN = "unknown"


class EvidenceConflictError(RuntimeError):
    """Stable evidence identity was reused for different content."""


@dataclass(frozen=True)
class SourceRecordRef:
    source_system: str
    source_record_id: str
    source_version: str | None = None
    source_content_hash: str | None = None


@dataclass(frozen=True)
class EvidenceItem:
    evidence_id: str
    athlete_id: str
    evidence_type: str
    observed_at: datetime
    available_at: datetime
    created_at: datetime
    source_ref: SourceRecordRef
    provenance: ProvenanceKind
    knowledge_status: KnowledgeStatus
    quality: EvidenceQuality
    payload: Mapping[str, object]
    content_hash_algorithm: str
    content_hash: str

    def verify_content_hash(self) -> bool:
        return (
            compute_content_hash(
                self,
                exclude_fields=EVIDENCE_HASH_EXCLUDE_FIELDS,
            )
            == self.content_hash
        )


def create_evidence_item(
    *,
    evidence_id: str,
    athlete_id: str,
    evidence_type: str,
    observed_at: datetime,
    available_at: datetime,
    created_at: datetime,
    source_ref: SourceRecordRef,
    provenance: ProvenanceKind,
    knowledge_status: KnowledgeStatus,
    quality: EvidenceQuality,
    payload: Mapping[str, object],
) -> EvidenceItem:
    for field_name, value in (
        ("evidence_id", evidence_id),
        ("athlete_id", athlete_id),
        ("evidence_type", evidence_type),
    ):
        if not value or not value.strip():
            raise ValueError(f"{field_name} must be non-empty.")

    observed = to_utc(observed_at, field_name="observed_at")
    available = to_utc(available_at, field_name="available_at")
    created = to_utc(created_at, field_name="created_at")
    if available < observed:
        raise ValueError(
            "available_at must not be before observed_at."
        )

    frozen_payload = deep_freeze(payload)
    provisional = EvidenceItem(
        evidence_id=evidence_id,
        athlete_id=athlete_id,
        evidence_type=evidence_type,
        observed_at=observed,
        available_at=available,
        created_at=created,
        source_ref=source_ref,
        provenance=provenance,
        knowledge_status=knowledge_status,
        quality=quality,
        payload=frozen_payload,
        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash="",
    )
    digest = compute_content_hash(
        provisional,
        exclude_fields=EVIDENCE_HASH_EXCLUDE_FIELDS,
    )
    return EvidenceItem(
        evidence_id=provisional.evidence_id,
        athlete_id=provisional.athlete_id,
        evidence_type=provisional.evidence_type,
        observed_at=provisional.observed_at,
        available_at=provisional.available_at,
        created_at=provisional.created_at,
        source_ref=provisional.source_ref,
        provenance=provisional.provenance,
        knowledge_status=provisional.knowledge_status,
        quality=provisional.quality,
        payload=provisional.payload,
        content_hash_algorithm=provisional.content_hash_algorithm,
        content_hash=digest,
    )


@dataclass(frozen=True)
class EvidenceBundle:
    bundle_id: str
    athlete_id: str
    as_of: datetime
    information_cutoff_at: datetime
    created_at: datetime
    items: tuple[EvidenceItem, ...]
    content_hash_algorithm: str
    content_hash: str

    def verify_content_hash(self) -> bool:
        return (
            compute_content_hash(
                self,
                exclude_fields=EVIDENCE_BUNDLE_HASH_EXCLUDE_FIELDS,
            )
            == self.content_hash
        )


def create_evidence_bundle(
    *,
    bundle_id: str,
    athlete_id: str,
    as_of: datetime,
    information_cutoff_at: datetime,
    created_at: datetime,
    items: tuple[EvidenceItem, ...],
) -> EvidenceBundle:
    as_of_utc = to_utc(as_of, field_name="as_of")
    cutoff = to_utc(
        information_cutoff_at,
        field_name="information_cutoff_at",
    )
    created = to_utc(created_at, field_name="created_at")
    if cutoff > as_of_utc:
        raise ValueError(
            "information_cutoff_at must not be after as_of."
        )

    for item in items:
        if item.athlete_id != athlete_id:
            raise ValueError(
                "EvidenceBundle cannot mix athlete identities."
            )
        if item.observed_at > cutoff:
            raise ValueError(
                "Evidence observed after information cutoff is forbidden."
            )
        if item.available_at > cutoff:
            raise ValueError(
                "Evidence unavailable at information cutoff is forbidden."
            )
        if not item.verify_content_hash():
            raise ValueError("Evidence item hash does not verify.")

    ordered_items = tuple(
        sorted(
            items,
            key=lambda item: (
                item.available_at,
                item.evidence_type,
                item.content_hash,
            ),
        )
    )
    provisional = EvidenceBundle(
        bundle_id=bundle_id,
        athlete_id=athlete_id,
        as_of=as_of_utc,
        information_cutoff_at=cutoff,
        created_at=created,
        items=ordered_items,
        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash="",
    )
    digest = compute_content_hash(
        provisional,
        exclude_fields=EVIDENCE_BUNDLE_HASH_EXCLUDE_FIELDS,
    )
    return EvidenceBundle(
        bundle_id=provisional.bundle_id,
        athlete_id=provisional.athlete_id,
        as_of=provisional.as_of,
        information_cutoff_at=provisional.information_cutoff_at,
        created_at=provisional.created_at,
        items=provisional.items,
        content_hash_algorithm=provisional.content_hash_algorithm,
        content_hash=digest,
    )
