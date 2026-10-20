from datetime import datetime, timedelta, timezone
from dataclasses import replace

import pytest

from app.planning.application.project_authoritative_training_response import (
    AUTHORITATIVE_TRAINING_RESPONSE_SOURCE_SYSTEM,
    project_authoritative_training_response_evidence,
)
from app.planning.domain.common.enums import (
    KnowledgeStatus,
    ProvenanceKind,
)
from app.planning.domain.evidence.models import EvidenceQuality
from app.planning.domain.response_evidence import (
    TrainingResponseKind,
    TrainingResponseLinkBasis,
    TrainingResponseMeasurement,
    TrainingResponseTiming,
    build_authoritative_training_response_evidence,
)
from app.planning.domain.training_state.evidence import (
    SESSION_FEEDBACK,
    SESSION_FEEDBACK_SCHEMA_V01,
    evidence_domain,
)
from app.planning.domain.training_state.models import (
    EvidenceDomain,
)


UTC = timezone.utc

ATHLETE = "11111111-1111-4111-8111-111111111111"
SESSION = "22222222-2222-4222-8222-222222222222"
RESPONSE = "33333333-3333-4333-8333-333333333333"

OBSERVED = datetime(
    2026,
    10,
    20,
    8,
    0,
    tzinfo=UTC,
)

SOURCE_AVAILABLE = datetime(
    2026,
    10,
    20,
    9,
    0,
    tzinfo=UTC,
)

ARTIFACT_CREATED = datetime(
    2026,
    10,
    20,
    10,
    0,
    tzinfo=UTC,
)

PROJECTED = datetime(
    2026,
    10,
    20,
    11,
    0,
    tzinfo=UTC,
)


def source_artifact():
    return build_authoritative_training_response_evidence(
        artifact_id=(
            "pt-training-response-evidence:"
            f"athlete-response:{RESPONSE}"
        ),
        athlete_id=ATHLETE,
        workout_session_id=SESSION,
        executed_training_evidence_id=(
            "pt-executed-training-evidence:"
            f"session:{SESSION}"
        ),
        executed_training_evidence_hash="a" * 64,
        response_kind=TrainingResponseKind.SESSION_FEEDBACK,
        response_timing=TrainingResponseTiming.SAME_DAY,
        session_link_basis=(
            TrainingResponseLinkBasis
            .SOURCE_EXPLICIT_SESSION_ID
        ),
        observed_at=OBSERVED,
        available_at=SOURCE_AVAILABLE,
        source_system="current_app_athlete_response",
        source_record_id=RESPONSE,
        source_record_version=(
            "current-app-athlete-response-source-v0.1"
        ),
        source_content_hash="b" * 64,
        provenance=ProvenanceKind.SOURCE,
        quality=EvidenceQuality.MODERATE,
        measurements=(
            TrainingResponseMeasurement(
                metric_key="self_reported_energy_score",
                knowledge_status=KnowledgeStatus.KNOWN,
                value=0.0,
                unit=None,
            ),
            TrainingResponseMeasurement(
                metric_key="self_reported_fatigue_score",
                knowledge_status=KnowledgeStatus.KNOWN,
                value=6.0,
                unit=None,
            ),
        ),
        created_at=ARTIFACT_CREATED,
    )


def test_projection_enters_response_domain_without_state_inference():
    source = source_artifact()

    item = project_authoritative_training_response_evidence(
        source,
        created_at=PROJECTED,
    )

    assert item.evidence_type == SESSION_FEEDBACK
    assert evidence_domain(item) == EvidenceDomain.RESPONSE

    assert (
        item.payload["schema_version"]
        == SESSION_FEEDBACK_SCHEMA_V01
    )

    assert item.payload["session_id"] == SESSION
    assert item.payload["response_timing"] == "same_day"

    assert item.payload["session_identity_linked"] is True
    assert (
        item.payload["causal_attribution_established"]
        is False
    )
    assert (
        item.payload["readiness_inference_authorized"]
        is False
    )
    assert (
        item.payload["fatigue_diagnosis_authorized"]
        is False
    )
    assert (
        item.payload["performance_prediction_authorized"]
        is False
    )
    assert (
        item.payload["prescription_change_authorized"]
        is False
    )

    assert item.verify_content_hash()


def test_projection_is_not_available_before_authoritative_artifact_exists():
    source = source_artifact()

    item = project_authoritative_training_response_evidence(
        source,
        created_at=PROJECTED,
    )

    assert source.available_at == SOURCE_AVAILABLE
    assert source.created_at == ARTIFACT_CREATED

    assert item.observed_at == OBSERVED

    # Deliberately NOT source.available_at.
    assert item.available_at == ARTIFACT_CREATED


def test_projection_source_ref_is_authoritative_response_not_mutable_source():
    source = source_artifact()

    item = project_authoritative_training_response_evidence(
        source,
        created_at=PROJECTED,
    )

    assert (
        item.source_ref.source_system
        == AUTHORITATIVE_TRAINING_RESPONSE_SOURCE_SYSTEM
    )
    assert (
        item.source_ref.source_record_id
        == source.artifact_id
    )
    assert (
        item.source_ref.source_version
        == source.schema_version
    )
    assert (
        item.source_ref.source_content_hash
        == source.content_hash
    )

    assert item.provenance == ProvenanceKind.DERIVED
    assert item.quality == EvidenceQuality.MODERATE


def test_projection_preserves_measurements_including_zero():
    item = project_authoritative_training_response_evidence(
        source_artifact(),
        created_at=PROJECTED,
    )

    measurements = {
        measurement["metric_key"]: measurement
        for measurement in item.payload["measurements"]
    }

    assert (
        measurements["self_reported_energy_score"]["value"]
        == 0.0
    )
    assert (
        measurements[
            "self_reported_fatigue_score"
        ]["value"]
        == 6.0
    )

    assert all(
        measurement["knowledge_status"] == "known"
        for measurement in measurements.values()
    )


def test_projection_preserves_execution_authority_reference_without_upgrading_it():
    source = source_artifact()

    item = project_authoritative_training_response_evidence(
        source,
        created_at=PROJECTED,
    )

    assert (
        item.payload["authoritative_response_evidence_id"]
        == source.artifact_id
    )
    assert (
        item.payload["authoritative_response_evidence_hash"]
        == source.content_hash
    )
    assert (
        item.payload["executed_training_evidence_id"]
        == source.executed_training_evidence_id
    )
    assert (
        item.payload["executed_training_evidence_hash"]
        == source.executed_training_evidence_hash
    )

    assert (
        item.payload["session_link_basis"]
        == "source_explicit_session_id"
    )


def test_projection_rejects_tampered_authoritative_source_hash():
    source = replace(
        source_artifact(),
        content_hash="f" * 64,
    )

    with pytest.raises(
        ValueError,
        match="hash",
    ):
        project_authoritative_training_response_evidence(
            source,
            created_at=PROJECTED,
        )


def test_projection_cannot_predate_authoritative_source_artifact():
    with pytest.raises(
        ValueError,
        match="cannot predate",
    ):
        project_authoritative_training_response_evidence(
            source_artifact(),
            created_at=(
                ARTIFACT_CREATED
                - timedelta(seconds=1)
            ),
        )


def test_projection_identity_and_hash_are_stable_across_retry_creation_time():
    source = source_artifact()

    first = project_authoritative_training_response_evidence(
        source,
        created_at=PROJECTED,
    )

    second = project_authoritative_training_response_evidence(
        source,
        created_at=PROJECTED + timedelta(hours=1),
    )

    assert first.evidence_id == second.evidence_id
    assert first.content_hash == second.content_hash

    assert first.created_at != second.created_at
