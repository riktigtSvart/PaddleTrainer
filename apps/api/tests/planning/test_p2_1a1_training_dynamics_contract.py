from dataclasses import replace
from datetime import datetime, timezone

import pytest

from app.planning.domain.common.enums import KnowledgeStatus
from app.planning.domain.response_evidence import (
    TrainingResponseLinkBasis,
    TrainingResponseTiming,
)
from app.planning.domain.training_dynamics import (
    EffectEvidenceLevel,
    EstimateStatus,
    ExposureReferenceEndBasis,
    ResponseIsolationStatus,
    RetentionModelKind,
    StimulusFeature,
    TrainingEffectComponentKind,
    build_latent_training_effect_estimate,
    build_longitudinal_training_effect_state,
    build_observed_response_association,
    build_realized_training_stimulus,
    build_retention_estimate,
)


UTC = timezone.utc

ATHLETE = "11111111-1111-4111-8111-111111111111"
SESSION = "22222222-2222-4222-8222-222222222222"

EXECUTED_ID = (
    "pt-executed-training-evidence:"
    f"session:{SESSION}"
)

EXECUTED_HASH = "a" * 64
RESPONSE_HASH = "b" * 64


def dt(hour: int) -> datetime:
    return datetime(
        2026,
        10,
        20,
        hour,
        tzinfo=UTC,
    )


def stimulus(
    *,
    duration_status=KnowledgeStatus.KNOWN,
    duration_s=3600,
):
    return build_realized_training_stimulus(
        stimulus_id=(
            "pt-training-stimulus:"
            f"executed-session:{SESSION}"
        ),
        athlete_id=ATHLETE,
        workout_session_id=SESSION,
        executed_training_evidence_id=EXECUTED_ID,
        executed_training_evidence_hash=EXECUTED_HASH,
        exposure_observed_at=dt(8),
        modality_key="RUNNING",
        duration_status=duration_status,
        duration_s=duration_s,
        features=(
            StimulusFeature(
                metric_key="distance_m",
                knowledge_status=KnowledgeStatus.KNOWN,
                value=10000,
                unit="m",
            ),
        ),
        created_at=dt(10),
    )


def unknown_effect(
    kind: TrainingEffectComponentKind,
):
    return build_latent_training_effect_estimate(
        estimate_id=(
            "pt-training-effect-estimate:"
            f"{kind.value}-unknown"
        ),
        athlete_id=ATHLETE,
        component_kind=kind,
        estimated_at=dt(12),
        information_cutoff_at=dt(11),
        estimation_status=EstimateStatus.UNKNOWN,
        created_at=dt(13),
    )


def estimated_effect(
    kind: TrainingEffectComponentKind,
):
    return build_latent_training_effect_estimate(
        estimate_id=(
            "pt-training-effect-estimate:"
            f"{kind.value}-estimated"
        ),
        athlete_id=ATHLETE,
        component_kind=kind,
        estimated_at=dt(12),
        information_cutoff_at=dt(11),
        estimation_status=EstimateStatus.ESTIMATED,
        estimated_value=2.5,
        unit="model_unit",
        model_id="descriptive-effect-model",
        model_version="v0.1",
        source_stimulus_ids=(
            stimulus().stimulus_id,
        ),
        created_at=dt(13),
    )


def test_realized_stimulus_derives_reference_end_without_claiming_boundary():
    item = stimulus()

    assert item.reference_end_at == dt(9)
    assert (
        item.reference_end_basis
        == ExposureReferenceEndBasis
        .OBSERVED_AT_PLUS_KNOWN_DURATION
    )

    assert item.actual_start_boundary_verified is False
    assert item.actual_end_boundary_verified is False
    assert item.causal_effect_established is False
    assert item.planning_authorized is False

    assert item.verify_content_hash()


def test_unknown_duration_never_manufactures_reference_end():
    item = stimulus(
        duration_status=KnowledgeStatus.UNKNOWN,
        duration_s=None,
    )

    assert item.duration_s is None
    assert item.reference_end_at is None
    assert (
        item.reference_end_basis
        == ExposureReferenceEndBasis.UNKNOWN
    )


def test_stimulus_unknown_feature_cannot_be_zero():
    with pytest.raises(
        ValueError,
        match="requires value=None",
    ):
        StimulusFeature(
            metric_key="unknown_load",
            knowledge_status=KnowledgeStatus.UNKNOWN,
            value=0,
            unit="arbitrary",
        )


def test_known_zero_stimulus_feature_is_preserved():
    feature = StimulusFeature(
        metric_key="zone_5_seconds",
        knowledge_status=KnowledgeStatus.KNOWN,
        value=0,
        unit="s",
    )

    assert feature.value == 0


def test_response_association_computes_descriptive_lag_only():
    source = stimulus()

    association = build_observed_response_association(
        association_id="pt-response-association:test-1",
        stimulus=source,
        response_evidence_id=(
            "pt-evidence:session-feedback:"
            + RESPONSE_HASH
        ),
        response_evidence_hash=RESPONSE_HASH,
        response_workout_session_id=SESSION,
        response_timing=TrainingResponseTiming.SAME_DAY,
        session_link_basis=(
            TrainingResponseLinkBasis
            .SOURCE_EXPLICIT_SESSION_ID
        ),
        response_observed_at=dt(14),
        response_available_at=dt(15),
        isolation_status=(
            ResponseIsolationStatus
            .NO_INTERVENING_STIMULUS_OBSERVED
        ),
        created_at=dt(16),
    )

    assert (
        association.lag_from_reference_end_status
        == KnowledgeStatus.KNOWN
    )
    assert association.lag_from_reference_end_s == 5 * 3600

    assert association.causal_attribution_established is False
    assert association.effect_inference_authorized is False
    assert association.planning_authorized is False

    assert association.verify_content_hash()


def test_response_before_reference_end_does_not_create_negative_lag():
    source = stimulus()

    association = build_observed_response_association(
        association_id="pt-response-association:test-early",
        stimulus=source,
        response_evidence_id=(
            "pt-evidence:session-feedback:"
            + RESPONSE_HASH
        ),
        response_evidence_hash=RESPONSE_HASH,
        response_workout_session_id=SESSION,
        response_timing=TrainingResponseTiming.IMMEDIATE,
        session_link_basis=(
            TrainingResponseLinkBasis
            .SOURCE_EXPLICIT_SESSION_ID
        ),
        response_observed_at=datetime(
            2026,
            10,
            20,
            8,
            30,
            tzinfo=UTC,
        ),
        response_available_at=dt(10),
        isolation_status=ResponseIsolationStatus.UNKNOWN,
        created_at=dt(11),
    )

    assert (
        association.lag_from_reference_end_status
        == KnowledgeStatus.UNKNOWN
    )
    assert association.lag_from_reference_end_s is None


def test_intervening_stimulus_status_requires_explicit_identity():
    with pytest.raises(
        ValueError,
        match="requires at least one intervening",
    ):
        build_observed_response_association(
            association_id="pt-response-association:test-intervening",
            stimulus=stimulus(),
            response_evidence_id=(
                "pt-evidence:session-feedback:"
                + RESPONSE_HASH
            ),
            response_evidence_hash=RESPONSE_HASH,
            response_workout_session_id=SESSION,
            response_timing=TrainingResponseTiming.NEXT_MORNING,
            session_link_basis=(
                TrainingResponseLinkBasis
                .SOURCE_EXPLICIT_SESSION_ID
            ),
            response_observed_at=dt(14),
            response_available_at=dt(15),
            isolation_status=(
                ResponseIsolationStatus
                .INTERVENING_STIMULUS_OBSERVED
            ),
            created_at=dt(16),
        )


def test_unknown_effect_is_first_class_and_has_no_numeric_value():
    estimate = unknown_effect(
        TrainingEffectComponentKind.FATIGUE
    )

    assert estimate.estimation_status == EstimateStatus.UNKNOWN
    assert estimate.estimated_value is None
    assert estimate.unit is None
    assert estimate.model_id is None
    assert estimate.evidence_level == EffectEvidenceLevel.UNKNOWN
    assert estimate.planning_authorized is False

    assert estimate.verify_content_hash()


def test_descriptive_effect_estimate_remains_noncausal_and_nonplanning():
    estimate = estimated_effect(
        TrainingEffectComponentKind.ADAPTATION
    )

    assert estimate.estimation_status == EstimateStatus.ESTIMATED
    assert estimate.estimated_value == 2.5
    assert (
        estimate.evidence_level
        == EffectEvidenceLevel.DESCRIPTIVE
    )

    assert estimate.causal_attribution_established is False
    assert estimate.performance_prediction_authorized is False
    assert estimate.planning_authorized is False


def test_effect_estimate_rejects_nonfinite_numeric_value():
    with pytest.raises(
        ValueError,
        match="must be finite",
    ):
        build_latent_training_effect_estimate(
            estimate_id="pt-training-effect-estimate:nan",
            athlete_id=ATHLETE,
            component_kind=TrainingEffectComponentKind.FATIGUE,
            estimated_at=dt(12),
            information_cutoff_at=dt(11),
            estimation_status=EstimateStatus.ESTIMATED,
            estimated_value=float("nan"),
            unit="model_unit",
            model_id="model",
            model_version="v0.1",
            source_stimulus_ids=(
                stimulus().stimulus_id,
            ),
            created_at=dt(13),
        )


def test_longitudinal_state_requires_explicit_fatigue_and_adaptation():
    fatigue = unknown_effect(
        TrainingEffectComponentKind.FATIGUE
    )
    adaptation = estimated_effect(
        TrainingEffectComponentKind.ADAPTATION
    )

    state = build_longitudinal_training_effect_state(
        state_id="pt-training-effect-state:test-1",
        athlete_id=ATHLETE,
        as_of=dt(12),
        effect_estimates=(
            fatigue,
            adaptation,
        ),
        created_at=dt(14),
    )

    assert {
        component.component_kind
        for component in state.components
    } == {
        TrainingEffectComponentKind.FATIGUE,
        TrainingEffectComponentKind.ADAPTATION,
    }

    assert state.readiness_inference_authorized is False
    assert state.performance_prediction_authorized is False
    assert state.prescription_change_authorized is False

    assert state.verify_content_hash()


def test_longitudinal_state_rejects_missing_component():
    with pytest.raises(
        ValueError,
        match="requires explicit FATIGUE and ADAPTATION",
    ):
        build_longitudinal_training_effect_state(
            state_id="pt-training-effect-state:incomplete",
            athlete_id=ATHLETE,
            as_of=dt(12),
            effect_estimates=(
                unknown_effect(
                    TrainingEffectComponentKind.FATIGUE
                ),
            ),
            created_at=dt(14),
        )


def test_unknown_retention_does_not_assume_decay_model():
    state = build_longitudinal_training_effect_state(
        state_id="pt-training-effect-state:unknown-retention",
        athlete_id=ATHLETE,
        as_of=dt(12),
        effect_estimates=(
            unknown_effect(
                TrainingEffectComponentKind.FATIGUE
            ),
            unknown_effect(
                TrainingEffectComponentKind.ADAPTATION
            ),
        ),
        created_at=dt(14),
    )

    retention = build_retention_estimate(
        retention_id="pt-retention-estimate:unknown",
        source_state=state,
        to_at=datetime(
            2026,
            10,
            21,
            12,
            tzinfo=UTC,
        ),
        information_cutoff_at=datetime(
            2026,
            10,
            21,
            12,
            tzinfo=UTC,
        ),
        estimation_status=EstimateStatus.UNKNOWN,
        created_at=datetime(
            2026,
            10,
            21,
            13,
            tzinfo=UTC,
        ),
    )

    assert retention.retained_effect_value is None
    assert (
        retention.model_kind
        == RetentionModelKind.UNESTABLISHED
    )
    assert retention.model_id is None
    assert retention.evidence_level == EffectEvidenceLevel.UNKNOWN
    assert retention.planning_authorized is False

    assert retention.verify_content_hash()


def test_empirical_retention_does_not_encode_exponential_decay():
    state = build_longitudinal_training_effect_state(
        state_id="pt-training-effect-state:estimated-retention",
        athlete_id=ATHLETE,
        as_of=dt(12),
        effect_estimates=(
            estimated_effect(
                TrainingEffectComponentKind.FATIGUE
            ),
            estimated_effect(
                TrainingEffectComponentKind.ADAPTATION
            ),
        ),
        created_at=dt(14),
    )

    next_day = datetime(
        2026,
        10,
        21,
        12,
        tzinfo=UTC,
    )

    retention = build_retention_estimate(
        retention_id="pt-retention-estimate:empirical",
        source_state=state,
        to_at=next_day,
        information_cutoff_at=next_day,
        estimation_status=EstimateStatus.ESTIMATED,
        retained_effect_value=2.1,
        unit="model_unit",
        model_id="personal-retention-model",
        model_version="v0.1",
        created_at=datetime(
            2026,
            10,
            21,
            13,
            tzinfo=UTC,
        ),
    )

    assert (
        retention.component_kind
        == TrainingEffectComponentKind.ADAPTATION
    )
    assert retention.elapsed_s == 24 * 3600

    assert retention.model_kind == RetentionModelKind.EMPIRICAL
    assert (
        retention.evidence_level
        == EffectEvidenceLevel.DESCRIPTIVE
    )

    assert retention.causal_attribution_established is False
    assert retention.planning_authorized is False


def test_semantic_hash_ignores_identity_and_created_at():
    first = stimulus()

    second = build_realized_training_stimulus(
        stimulus_id="pt-training-stimulus:different-id",
        athlete_id=ATHLETE,
        workout_session_id=SESSION,
        executed_training_evidence_id=EXECUTED_ID,
        executed_training_evidence_hash=EXECUTED_HASH,
        exposure_observed_at=dt(8),
        modality_key="RUNNING",
        duration_status=KnowledgeStatus.KNOWN,
        duration_s=3600,
        features=(
            StimulusFeature(
                metric_key="distance_m",
                knowledge_status=KnowledgeStatus.KNOWN,
                value=10000,
                unit="m",
            ),
        ),
        created_at=dt(11),
    )

    assert first.content_hash == second.content_hash


def test_tampered_contract_hash_is_detected():
    item = stimulus()

    tampered = replace(
        item,
        modality_key="CYCLING",
    )

    assert tampered.verify_content_hash() is False
