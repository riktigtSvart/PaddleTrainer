from datetime import datetime, timezone

import pytest

from app.planning.domain.common.enums import (
    KnowledgeStatus,
    ProvenanceKind,
)
from app.planning.domain.evidence.models import (
    EvidenceQuality,
    SourceRecordRef,
    create_evidence_item,
)
from app.planning.domain.training_state.evidence import (
    EXECUTED_TRAINING_SESSION,
    training_exposure_from_evidence,
)


def _dt() -> datetime:
    return datetime(2026, 10, 16, 12, tzinfo=timezone.utc)


def _item(payload):
    return create_evidence_item(
        evidence_id="session-evidence-1",
        athlete_id="athlete-1",
        evidence_type=EXECUTED_TRAINING_SESSION,
        observed_at=_dt(),
        available_at=_dt(),
        created_at=_dt(),
        source_ref=SourceRecordRef(
            source_system="test",
            source_record_id="session-1",
        ),
        provenance=ProvenanceKind.SOURCE,
        knowledge_status=KnowledgeStatus.KNOWN,
        quality=EvidenceQuality.HIGH,
        payload=payload,
    )


def test_training_session_contract_accepts_explicit_unknown_duration() -> None:
    observation = training_exposure_from_evidence(
        _item(
            {
                "schema_version":
                    "executed_training_session_evidence_v0.1",
                "session_id": "session-1",
                "modality_key": "KAYAK",
                "duration_status": "unknown",
                "duration_s": None,
            }
        )
    )

    assert observation is not None
    assert observation.duration_status == KnowledgeStatus.UNKNOWN
    assert observation.duration_s is None


def test_training_session_contract_rejects_value_when_duration_unknown() -> None:
    with pytest.raises(ValueError, match="requires duration_s=None"):
        training_exposure_from_evidence(
            _item(
                {
                    "schema_version":
                        "executed_training_session_evidence_v0.1",
                    "session_id": "session-1",
                    "modality_key": "KAYAK",
                    "duration_status": "unknown",
                    "duration_s": 3600,
                }
            )
        )


def test_training_session_contract_rejects_unversioned_payload() -> None:
    with pytest.raises(ValueError, match="Unsupported"):
        training_exposure_from_evidence(
            _item(
                {
                    "session_id": "session-1",
                    "modality_key": "KAYAK",
                    "duration_status": "known",
                    "duration_s": 3600,
                }
            )
        )
