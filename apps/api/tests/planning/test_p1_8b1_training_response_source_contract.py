from datetime import datetime, timezone
import inspect

import pytest

from app.planning.domain.common.enums import (
    KnowledgeStatus,
)
from app.planning.domain.response_evidence import (
    TRAINING_RESPONSE_EVIDENCE_SCHEMA_V01,
    TRAINING_RESPONSE_EVIDENCE_SCHEMA_V02,
    TrainingResponseKind,
    TrainingResponseLinkBasis,
    TrainingResponseMeasurement,
    TrainingResponseTiming,
    build_authoritative_training_response_evidence,
)
from app.planning.domain.response_evidence.source_capture import (
    build_training_response_source_capture,
)
from app.planning.domain.common.enums import (
    ProvenanceKind,
)
from app.planning.domain.evidence.models import (
    EvidenceQuality,
)
from app.planning.ports.training_response_source import (
    LockedTrainingResponseSourceProvider,
)


UTC = timezone.utc

ATHLETE_ID = (
    "11111111-1111-4111-8111-111111111111"
)

SESSION_ID = (
    "22222222-2222-4222-8222-222222222222"
)

RESPONSE_ID = (
    "33333333-3333-4333-8333-333333333333"
)

EXECUTED_ID = (
    "pt-executed-training-evidence:"
    "session:22222222-2222-4222-8222-222222222222"
)


def dt(hour: int) -> datetime:
    return datetime(
        2026,
        10,
        20,
        hour,
        tzinfo=UTC,
    )


def measurement(
    key: str,
    value: float,
) -> TrainingResponseMeasurement:
    return TrainingResponseMeasurement(
        metric_key=key,
        knowledge_status=KnowledgeStatus.KNOWN,
        value=value,
        unit="score",
    )


def test_v01_remains_named_but_new_artifacts_use_v02():
    artifact = build_authoritative_training_response_evidence(
        artifact_id=(
            "pt-training-response-evidence:b1-schema"
        ),
        athlete_id=ATHLETE_ID,
        workout_session_id=SESSION_ID,
        executed_training_evidence_id=EXECUTED_ID,
        executed_training_evidence_hash="a" * 64,
        response_kind=TrainingResponseKind.SESSION_FEEDBACK,
        response_timing=TrainingResponseTiming.NEXT_MORNING,
        session_link_basis=(
            TrainingResponseLinkBasis.SOURCE_EXPLICIT_SESSION_ID
        ),
        observed_at=dt(8),
        available_at=dt(9),
        source_system="athlete_response",
        source_record_id=RESPONSE_ID,
        source_record_version=None,
        source_content_hash="b" * 64,
        provenance=ProvenanceKind.SOURCE,
        quality=EvidenceQuality.MODERATE,
        measurements=(
            measurement(
                "self_reported_fatigue_score",
                6.0,
            ),
        ),
        created_at=dt(10),
    )

    assert (
        TRAINING_RESPONSE_EVIDENCE_SCHEMA_V01
        == "authoritative-training-response-evidence-v0.1"
    )

    assert (
        artifact.schema_version
        == TRAINING_RESPONSE_EVIDENCE_SCHEMA_V02
    )

    assert (
        artifact.response_timing
        == TrainingResponseTiming.NEXT_MORNING
    )

    assert artifact.verify_content_hash()


def test_response_timing_is_semantic_identity():
    common = dict(
        athlete_id=ATHLETE_ID,
        workout_session_id=SESSION_ID,
        executed_training_evidence_id=EXECUTED_ID,
        executed_training_evidence_hash="a" * 64,
        response_kind=TrainingResponseKind.SESSION_FEEDBACK,
        session_link_basis=(
            TrainingResponseLinkBasis.SOURCE_EXPLICIT_SESSION_ID
        ),
        observed_at=dt(8),
        available_at=dt(9),
        source_system="athlete_response",
        source_record_id=RESPONSE_ID,
        source_record_version=None,
        source_content_hash="b" * 64,
        provenance=ProvenanceKind.SOURCE,
        quality=EvidenceQuality.MODERATE,
        measurements=(
            measurement(
                "self_reported_recovery_score",
                7.0,
            ),
        ),
        created_at=dt(10),
    )

    immediate = build_authoritative_training_response_evidence(
        artifact_id=(
            "pt-training-response-evidence:timing-immediate"
        ),
        response_timing=TrainingResponseTiming.IMMEDIATE,
        **common,
    )

    next_morning = build_authoritative_training_response_evidence(
        artifact_id=(
            "pt-training-response-evidence:timing-next"
        ),
        response_timing=TrainingResponseTiming.NEXT_MORNING,
        **common,
    )

    assert (
        immediate.content_hash
        != next_morning.content_hash
    )


def test_source_capture_requires_explicit_session_identity():
    with pytest.raises(
        ValueError,
        match="workout_session_id must be a non-empty string",
    ):
        build_training_response_source_capture(
            athlete_id=ATHLETE_ID,
            workout_session_id="",
            response_source_id=RESPONSE_ID,
            response_kind=(
                TrainingResponseKind.SESSION_FEEDBACK
            ),
            response_timing=(
                TrainingResponseTiming.SAME_DAY
            ),
            observed_at=dt(8),
            available_at=dt(9),
            source_system="athlete_response",
            source_record_id=RESPONSE_ID,
            source_record_version=None,
            source_content_hash="c" * 64,
            measurements=(
                measurement(
                    "self_reported_energy_score",
                    5.0,
                ),
            ),
        )


def test_source_capture_rejects_malformed_session_identity():
    with pytest.raises(
        ValueError,
        match="workout_session_id must be a canonical UUID",
    ):
        build_training_response_source_capture(
            athlete_id=ATHLETE_ID,
            workout_session_id="not-a-uuid",
            response_source_id=RESPONSE_ID,
            response_kind=(
                TrainingResponseKind.SESSION_FEEDBACK
            ),
            response_timing=(
                TrainingResponseTiming.SAME_DAY
            ),
            observed_at=dt(8),
            available_at=dt(9),
            source_system="athlete_response",
            source_record_id=RESPONSE_ID,
            source_record_version=None,
            source_content_hash="c" * 64,
            measurements=(
                measurement(
                    "self_reported_energy_score",
                    5.0,
                ),
            ),
        )


def test_source_capture_preserves_observation_and_availability():
    capture = build_training_response_source_capture(
        athlete_id=ATHLETE_ID,
        workout_session_id=SESSION_ID,
        response_source_id=RESPONSE_ID,
        response_kind=TrainingResponseKind.SESSION_FEEDBACK,
        response_timing=TrainingResponseTiming.SAME_DAY,
        observed_at=dt(8),
        available_at=dt(11),
        source_system="athlete_response",
        source_record_id=RESPONSE_ID,
        source_record_version=None,
        source_content_hash="c" * 64,
        measurements=(
            measurement(
                "self_reported_energy_score",
                5.0,
            ),
        ),
    )

    assert capture.observed_at == dt(8)
    assert capture.available_at == dt(11)


def test_source_capture_rejects_future_information_leakage_shape():
    with pytest.raises(
        ValueError,
        match="available_at must not be before observed_at",
    ):
        build_training_response_source_capture(
            athlete_id=ATHLETE_ID,
            workout_session_id=SESSION_ID,
            response_source_id=RESPONSE_ID,
            response_kind=(
                TrainingResponseKind.SESSION_FEEDBACK
            ),
            response_timing=(
                TrainingResponseTiming.SAME_DAY
            ),
            observed_at=dt(11),
            available_at=dt(8),
            source_system="athlete_response",
            source_record_id=RESPONSE_ID,
            source_record_version=None,
            source_content_hash="c" * 64,
            measurements=(
                measurement(
                    "self_reported_energy_score",
                    5.0,
                ),
            ),
        )


def test_source_capture_requires_promotable_measurement():
    with pytest.raises(
        ValueError,
        match="at least one promotable measurement",
    ):
        build_training_response_source_capture(
            athlete_id=ATHLETE_ID,
            workout_session_id=SESSION_ID,
            response_source_id=RESPONSE_ID,
            response_kind=(
                TrainingResponseKind.SESSION_FEEDBACK
            ),
            response_timing=(
                TrainingResponseTiming.SAME_DAY
            ),
            observed_at=dt(8),
            available_at=dt(9),
            source_system="athlete_response",
            source_record_id=RESPONSE_ID,
            source_record_version=None,
            source_content_hash="c" * 64,
            measurements=(),
        )


def test_source_capture_has_no_temporal_matching_surface():
    signature = inspect.signature(
        LockedTrainingResponseSourceProvider
        .lock_and_capture
    )

    forbidden = {
        "candidate_session_id",
        "started_at",
        "ended_at",
        "temporal_tolerance",
        "temporal_match",
    }

    assert forbidden.isdisjoint(
        signature.parameters
    )


def test_source_capture_has_no_block_phase_or_performance_authority():
    capture_signature = inspect.signature(
        build_training_response_source_capture
    )

    forbidden = {
        "executed_block_id",
        "phase_id",
        "occurrence_id",
        "performance_prediction",
        "readiness",
        "fatigue_diagnosis",
        "prescription_change",
    }

    assert forbidden.isdisjoint(
        capture_signature.parameters
    )
