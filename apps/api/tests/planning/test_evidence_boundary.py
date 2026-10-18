from datetime import datetime, timezone

import pytest

from app.planning.application.collect_evidence import collect_available_evidence
from app.planning.domain.common.enums import KnowledgeStatus, ProvenanceKind
from app.planning.domain.evidence.models import (
    EvidenceQuality,
    SourceRecordRef,
    create_evidence_bundle,
    create_evidence_item,
)
from app.planning.infrastructure.repositories.in_memory import (
    InMemoryEvidenceRepository,
)


def _dt(hour: int) -> datetime:
    return datetime(2026, 10, 16, hour, tzinfo=timezone.utc)


def _item(evidence_id: str, *, observed: int, available: int):
    return create_evidence_item(
        evidence_id=evidence_id,
        athlete_id="athlete-1",
        evidence_type="SESSION_FEEDBACK",
        observed_at=_dt(observed),
        available_at=_dt(available),
        created_at=_dt(20),
        source_ref=SourceRecordRef(
            source_system="test",
            source_record_id=evidence_id,
        ),
        provenance=ProvenanceKind.SOURCE,
        knowledge_status=KnowledgeStatus.KNOWN,
        quality=EvidenceQuality.MODERATE,
        payload={"rpe": 3},
    )


def test_available_at_may_be_later_than_observed_at() -> None:
    item = _item("e-1", observed=10, available=12)
    assert item.observed_at == _dt(10)
    assert item.available_at == _dt(12)
    assert item.verify_content_hash()


def test_evidence_cannot_be_available_before_observation() -> None:
    with pytest.raises(ValueError, match="before observed_at"):
        _item("e-1", observed=12, available=10)


def test_evidence_bundle_rejects_late_feedback() -> None:
    late = _item("late", observed=10, available=19)
    with pytest.raises(ValueError, match="unavailable"):
        create_evidence_bundle(
            bundle_id="bundle-1",
            athlete_id="athlete-1",
            as_of=_dt(18),
            information_cutoff_at=_dt(18),
            created_at=_dt(20),
            items=(late,),
        )


def test_repository_collection_excludes_late_feedback() -> None:
    repo = InMemoryEvidenceRepository()
    repo.save(_item("early", observed=10, available=12))
    repo.save(_item("late", observed=10, available=19))
    bundle = collect_available_evidence(
        repository=repo,
        bundle_id="bundle-1",
        athlete_id="athlete-1",
        as_of=_dt(18),
        information_cutoff_at=_dt(18),
        created_at=_dt(20),
    )
    assert tuple(item.evidence_id for item in bundle.items) == ("early",)


def test_evidence_bundle_order_is_deterministic() -> None:
    first = _item("b", observed=9, available=12)
    second = _item("a", observed=9, available=11)
    left = create_evidence_bundle(
        bundle_id="left",
        athlete_id="athlete-1",
        as_of=_dt(18),
        information_cutoff_at=_dt(18),
        created_at=_dt(20),
        items=(first, second),
    )
    right = create_evidence_bundle(
        bundle_id="right",
        athlete_id="athlete-1",
        as_of=_dt(18),
        information_cutoff_at=_dt(18),
        created_at=_dt(21),
        items=(second, first),
    )
    assert left.content_hash == right.content_hash


def test_evidence_payload_is_immutable() -> None:
    item = _item("e-1", observed=10, available=12)
    with pytest.raises(TypeError):
        item.payload["rpe"] = 4  # type: ignore[index]
