from datetime import datetime, timezone

import pytest

from app.planning.domain.common.enums import (
    KnowledgeStatus,
    ProvenanceKind,
)
from app.planning.domain.evidence.models import (
    EvidenceQuality,
)
from app.planning.domain.response_evidence import (
    TRAINING_RESPONSE_EVIDENCE_SCHEMA_V02,
    TrainingResponseInterpretation,
    TrainingResponseKind,
    TrainingResponseLinkBasis,
    TrainingResponseMeasurement,
    TrainingResponseTiming,
    build_authoritative_training_response_evidence,
)


UTC = timezone.utc

ATHLETE_ID = (
    "11111111-1111-4111-8111-111111111111"
)
SESSION_ID = (
    "22222222-2222-4222-8222-222222222222"
)

EXECUTED_ID = (
    "pt-executed-training-evidence:"
    "session:22222222-2222-4222-8222-222222222222"
)

EXECUTED_HASH = "a" * 64
SOURCE_HASH = "b" * 64


def dt(hour: int) -> datetime:
    return datetime(
        2026,
        10,
        20,
        hour,
        tzinfo=UTC,
    )


def known(
    metric_key: str,
    value,
    unit: str | None = None,
) -> TrainingResponseMeasurement:
    return TrainingResponseMeasurement(
        metric_key=metric_key,
        knowledge_status=KnowledgeStatus.KNOWN,
        value=value,
        unit=unit,
    )


def build(
    *,
    artifact_id: str = (
        "pt-training-response-evidence:test-1"
    ),
    response_kind: TrainingResponseKind = (
        TrainingResponseKind.SESSION_FEEDBACK
    ),
    session_link_basis: TrainingResponseLinkBasis = (
        TrainingResponseLinkBasis.SOURCE_EXPLICIT_SESSION_ID
    ),
    provenance: ProvenanceKind = ProvenanceKind.SOURCE,
    observed_at: datetime | None = None,
    available_at: datetime | None = None,
    created_at: datetime | None = None,
    measurements=None,
):
    return build_authoritative_training_response_evidence(
        artifact_id=artifact_id,
        athlete_id=ATHLETE_ID,
        workout_session_id=SESSION_ID,
        executed_training_evidence_id=EXECUTED_ID,
        executed_training_evidence_hash=EXECUTED_HASH,
        response_kind=response_kind,
        response_timing=TrainingResponseTiming.IMMEDIATE,
        session_link_basis=session_link_basis,
        observed_at=observed_at or dt(8),
        available_at=available_at or dt(9),
        source_system="session-feedback-test",
        source_record_id="feedback-1",
        source_record_version="v1",
        source_content_hash=SOURCE_HASH,
        provenance=provenance,
        quality=EvidenceQuality.HIGH,
        measurements=(
            tuple(measurements)
            if measurements is not None
            else (
                known(
                    "overall_exertion",
                    7,
                    "score_0_10",
                ),
                known(
                    "prescription_completion",
                    "completed",
                ),
            )
        ),
        created_at=created_at or dt(10),
    )


def test_builds_hash_verified_descriptive_response_evidence():
    artifact = build()

    assert (
        artifact.schema_version
        == TRAINING_RESPONSE_EVIDENCE_SCHEMA_V02
    )
    assert (
        artifact.response_kind
        == TrainingResponseKind.SESSION_FEEDBACK
    )
    assert artifact.session_identity_linked is True

    assert (
        artifact.interpretation
        == TrainingResponseInterpretation.DESCRIPTIVE_ONLY
    )

    assert artifact.causal_attribution_established is False
    assert artifact.readiness_inference_authorized is False
    assert artifact.fatigue_diagnosis_authorized is False
    assert artifact.performance_prediction_authorized is False
    assert artifact.prescription_change_authorized is False

    assert artifact.verify_content_hash()


def test_physiological_response_is_still_descriptive_only():
    artifact = build(
        response_kind=(
            TrainingResponseKind.PHYSIOLOGICAL_RESPONSE
        ),
        provenance=ProvenanceKind.DERIVED,
        measurements=(
            known(
                "heart_rate_recovery_60s",
                28,
                "bpm",
            ),
        ),
    )

    assert (
        artifact.response_kind
        == TrainingResponseKind.PHYSIOLOGICAL_RESPONSE
    )
    assert (
        artifact.interpretation
        == TrainingResponseInterpretation.DESCRIPTIVE_ONLY
    )

    assert artifact.causal_attribution_established is False
    assert artifact.readiness_inference_authorized is False
    assert artifact.fatigue_diagnosis_authorized is False
    assert artifact.prescription_change_authorized is False


def test_unknown_response_never_becomes_zero():
    unknown = TrainingResponseMeasurement(
        metric_key="overall_exertion",
        knowledge_status=KnowledgeStatus.UNKNOWN,
        value=None,
        unit="score_0_10",
    )

    assert unknown.value is None

    with pytest.raises(
        ValueError,
        match="requires value=None",
    ):
        TrainingResponseMeasurement(
            metric_key="overall_exertion",
            knowledge_status=KnowledgeStatus.UNKNOWN,
            value=0,
            unit="score_0_10",
        )


def test_known_zero_is_preserved_as_real_observation():
    measurement = TrainingResponseMeasurement(
        metric_key="symptom_severity",
        knowledge_status=KnowledgeStatus.KNOWN,
        value=0,
        unit="score_0_10",
    )

    assert measurement.value == 0


def test_known_measurement_requires_actual_value():
    with pytest.raises(
        ValueError,
        match="KNOWN response measurement requires a value",
    ):
        TrainingResponseMeasurement(
            metric_key="overall_exertion",
            knowledge_status=KnowledgeStatus.KNOWN,
            value=None,
            unit="score_0_10",
        )


def test_non_finite_numeric_response_is_rejected():
    with pytest.raises(
        ValueError,
        match="must be finite",
    ):
        known(
            "derived_metric",
            float("nan"),
            "arbitrary",
        )


def test_temporal_proximity_is_not_a_link_basis():
    assert {
        basis.value
        for basis in TrainingResponseLinkBasis
    } == {
        "source_explicit_session_id",
        "user_confirmed_session_id",
    }


def test_inferred_response_is_not_authoritative_observation():
    with pytest.raises(
        ValueError,
        match="must be SOURCE or DERIVED",
    ):
        build(
            provenance=ProvenanceKind.INFERRED,
        )


def test_response_cannot_be_available_before_observed():
    with pytest.raises(
        ValueError,
        match="available_at must not be before observed_at",
    ):
        build(
            observed_at=dt(9),
            available_at=dt(8),
        )


def test_artifact_cannot_predate_source_availability():
    with pytest.raises(
        ValueError,
        match="created_at must not be before available_at",
    ):
        build(
            available_at=dt(9),
            created_at=dt(8),
        )


def test_response_artifact_requires_measurement():
    with pytest.raises(
        ValueError,
        match="requires at least one",
    ):
        build(
            measurements=(),
        )


def test_duplicate_metric_keys_are_rejected():
    with pytest.raises(
        ValueError,
        match="must be unique",
    ):
        build(
            measurements=(
                known(
                    "overall_exertion",
                    7,
                    "score_0_10",
                ),
                known(
                    "overall_exertion",
                    8,
                    "score_0_10",
                ),
            )
        )


def test_semantic_hash_is_stable_across_artifact_identity_creation_time_and_order():
    left = build(
        artifact_id=(
            "pt-training-response-evidence:left"
        ),
        created_at=dt(10),
        measurements=(
            known(
                "prescription_completion",
                "completed",
            ),
            known(
                "overall_exertion",
                7,
                "score_0_10",
            ),
        ),
    )

    right = build(
        artifact_id=(
            "pt-training-response-evidence:right"
        ),
        created_at=dt(11),
        measurements=(
            known(
                "overall_exertion",
                7,
                "score_0_10",
            ),
            known(
                "prescription_completion",
                "completed",
            ),
        ),
    )

    assert left.artifact_id != right.artifact_id
    assert left.created_at != right.created_at

    assert left.measurements == right.measurements
    assert left.content_hash == right.content_hash

    assert left.verify_content_hash()
    assert right.verify_content_hash()


def test_block_level_or_performance_authority_is_not_part_of_v01_contract():
    assert {
        kind.value
        for kind in TrainingResponseKind
    } == {
        "session_feedback",
        "physiological_response",
    }


# P1_8A_HARDENING


def test_response_contract_has_no_block_or_phase_authority_surface():
    import inspect

    signature = inspect.signature(
        build_authoritative_training_response_evidence
    )

    forbidden = {
        "executed_block_id",
        "authoritative_occurrence_id",
        "occurrence_execution_link_id",
        "phase_id",
        "phase_alignment_verified",
        "actual_boundary_verified",
    }

    assert forbidden.isdisjoint(
        signature.parameters
    )


def test_available_at_is_part_of_response_semantic_identity():
    early = build(
        artifact_id=(
            "pt-training-response-evidence:availability-early"
        ),
        available_at=dt(9),
        created_at=dt(11),
    )

    late = build(
        artifact_id=(
            "pt-training-response-evidence:availability-late"
        ),
        available_at=dt(10),
        created_at=dt(11),
    )

    assert early.content_hash != late.content_hash

    assert early.verify_content_hash()
    assert late.verify_content_hash()


def test_observed_at_is_part_of_response_semantic_identity():
    first = build(
        artifact_id=(
            "pt-training-response-evidence:observed-first"
        ),
        observed_at=dt(8),
        available_at=dt(10),
        created_at=dt(11),
    )

    second = build(
        artifact_id=(
            "pt-training-response-evidence:observed-second"
        ),
        observed_at=dt(9),
        available_at=dt(10),
        created_at=dt(11),
    )

    assert first.content_hash != second.content_hash


def test_session_link_basis_is_part_of_semantic_identity():
    source_linked = build(
        artifact_id=(
            "pt-training-response-evidence:source-linked"
        ),
        session_link_basis=(
            TrainingResponseLinkBasis.SOURCE_EXPLICIT_SESSION_ID
        ),
    )

    user_linked = build(
        artifact_id=(
            "pt-training-response-evidence:user-linked"
        ),
        session_link_basis=(
            TrainingResponseLinkBasis.USER_CONFIRMED_SESSION_ID
        ),
    )

    assert (
        source_linked.content_hash
        != user_linked.content_hash
    )


def test_source_content_identity_is_part_of_semantic_hash():
    first = build(
        artifact_id=(
            "pt-training-response-evidence:source-a"
        ),
    )

    changed = (
        build_authoritative_training_response_evidence(
            artifact_id=(
                "pt-training-response-evidence:source-b"
            ),
            athlete_id=ATHLETE_ID,
            workout_session_id=SESSION_ID,
            executed_training_evidence_id=EXECUTED_ID,
            executed_training_evidence_hash=EXECUTED_HASH,
            response_kind=(
                TrainingResponseKind.SESSION_FEEDBACK
            ),
            response_timing=(
                TrainingResponseTiming.IMMEDIATE
            ),
            session_link_basis=(
                TrainingResponseLinkBasis
                .SOURCE_EXPLICIT_SESSION_ID
            ),
            observed_at=dt(8),
            available_at=dt(9),
            source_system="session-feedback-test",
            source_record_id="feedback-1",
            source_record_version="v1",
            source_content_hash="c" * 64,
            provenance=ProvenanceKind.SOURCE,
            quality=EvidenceQuality.HIGH,
            measurements=(
                known(
                    "overall_exertion",
                    7,
                    "score_0_10",
                ),
                known(
                    "prescription_completion",
                    "completed",
                ),
            ),
            created_at=dt(10),
        )
    )

    assert first.content_hash != changed.content_hash


def test_p1_8a_does_not_model_performance_as_response_kind():
    assert "performance" not in {
        kind.value
        for kind in TrainingResponseKind
    }
