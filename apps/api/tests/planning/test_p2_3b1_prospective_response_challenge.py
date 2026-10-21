from dataclasses import dataclass, replace
from datetime import datetime, timezone

import pytest

from app.planning.domain.common.enums import (
    KnowledgeStatus,
)
from app.planning.domain.common.serialization import (
    CONTENT_HASH_ALGORITHM,
    compute_content_hash,
)
from app.planning.domain.executed_training import (
    AUTHORITATIVE_EXECUTED_TRAINING_SCHEMA_VERSION,
)
from app.planning.domain.response_evidence import (
    TRAINING_RESPONSE_EVIDENCE_SCHEMA_V02,
    TrainingResponseInterpretation,
    TrainingResponseKind,
    TrainingResponseLinkBasis,
    TrainingResponseMeasurement,
    TrainingResponseTiming,
)
from app.planning.domain.training_dynamics import (
    EffectEvidenceLevel,
    PersonalAssociationPredictorKey,
    PersonalResponsePredictionDirection,
    ResponseMetricReferenceKey,
)
from app.planning.domain.training_dynamics.prospective_issuance import (
    PERSONAL_RESPONSE_PREDICTION_ISSUANCE_HASH_EXCLUDE_FIELDS,
    PERSONAL_RESPONSE_PREDICTION_ISSUANCE_RULES_V01,
    PERSONAL_RESPONSE_PREDICTION_ISSUANCE_SCHEMA_V01,
    PersonalResponsePredictionIssuanceContract,
)
from app.planning.domain.training_dynamics.prospective_outcome import (
    ProspectiveResponseActualDirection,
    ProspectiveResponseChallengeResult,
    build_prospective_response_challenge,
)


UTC = timezone.utc

ATHLETE = "11111111-1111-4111-8111-111111111111"
SESSION = "22222222-2222-4222-8222-222222222222"


def dt(hour: int) -> datetime:
    return datetime(
        2026,
        10,
        21,
        hour,
        tzinfo=UTC,
    )


def issuance(
    *,
    predicted_direction=(
        PersonalResponsePredictionDirection
        .ABOVE_HISTORICAL_MEDIAN
    ),
    historical_median=3.0,
):
    provisional = PersonalResponsePredictionIssuanceContract(
        issuance_id="PENDING",
        schema_version=(
            PERSONAL_RESPONSE_PREDICTION_ISSUANCE_SCHEMA_V01
        ),
        rules_version=(
            PERSONAL_RESPONSE_PREDICTION_ISSUANCE_RULES_V01
        ),

        athlete_id=ATHLETE,
        workout_session_id=SESSION,

        source_candidate_id="candidate-1",
        source_candidate_content_hash="a" * 64,
        source_candidate_schema_version=(
            "personal-response-prediction-candidate-v0.1"
        ),
        source_candidate_rules_version=(
            "personal-response-prediction-rules-v0.1"
        ),

        model_id="personal-monotonic-median-direction",
        model_version="0.1.0",

        predictor_key=PersonalAssociationPredictorKey(
            metric_key="training_load_index",
            unit="au",
        ),

        response_key=ResponseMetricReferenceKey(
            metric_key="self_reported_fatigue_score",
            unit="score_0_10",
            response_timing=TrainingResponseTiming.SAME_DAY,
            stimulus_modality_key="RUNNING",
        ),

        information_cutoff_at=dt(10),
        prediction_at=dt(11),

        target_predictor_value=4.5,
        historical_response_median=historical_median,

        predicted_response_direction=predicted_direction,

        response_prediction_available=True,

        evidence_level_ceiling=(
            EffectEvidenceLevel.ASSOCIATION_SUPPORTED
        ),
        association_supported=True,

        prospective_validation_established=False,
        causal_attribution_established=False,
        effect_inference_authorized=False,
        readiness_inference_authorized=False,
        performance_prediction_authorized=False,
        prescription_change_authorized=False,
        planning_authorized=False,

        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash="",
    )

    digest = compute_content_hash(
        provisional,
        exclude_fields=(
            PERSONAL_RESPONSE_PREDICTION_ISSUANCE_HASH_EXCLUDE_FIELDS
        ),
    )

    return replace(
        provisional,
        issuance_id=(
            "pt-personal-response-prediction-issuance:"
            + digest
        ),
        content_hash=digest,
    )


@dataclass(frozen=True)
class ResponseStub:
    artifact_id: str
    schema_version: str
    athlete_id: str
    workout_session_id: str

    executed_training_evidence_id: str
    executed_training_evidence_hash: str

    response_kind: TrainingResponseKind
    response_timing: TrainingResponseTiming
    session_link_basis: TrainingResponseLinkBasis

    observed_at: datetime
    available_at: datetime

    measurements: tuple[
        TrainingResponseMeasurement,
        ...,
    ]

    interpretation: TrainingResponseInterpretation
    session_identity_linked: bool

    causal_attribution_established: bool
    readiness_inference_authorized: bool
    fatigue_diagnosis_authorized: bool
    performance_prediction_authorized: bool
    prescription_change_authorized: bool

    created_at: datetime
    content_hash: str

    hash_valid: bool = True

    def verify_content_hash(self):
        return self.hash_valid


@dataclass(frozen=True)
class ExecutedStub:
    artifact_id: str
    schema_version: str
    athlete_id: str
    workout_session_id: str

    modality_key: str

    plan_identity_linked: bool
    plan_content_at_execution_status: str

    occurrence_alignment_verified: bool
    phase_alignment_verified: bool
    provider_event_verified: bool
    clock_alignment_verified: bool
    actual_boundary_verified: bool
    temporal_match_used: bool

    content_hash: str
    hash_valid: bool = True

    def verify_content_hash(self):
        return self.hash_valid


def executed(
    *,
    modality="RUNNING",
):
    return ExecutedStub(
        artifact_id=(
            "pt-executed-training-evidence:"
            f"session:{SESSION}"
        ),
        schema_version=(
            AUTHORITATIVE_EXECUTED_TRAINING_SCHEMA_VERSION
        ),
        athlete_id=ATHLETE,
        workout_session_id=SESSION,

        modality_key=modality,

        plan_identity_linked=True,
        plan_content_at_execution_status="unverified",

        occurrence_alignment_verified=False,
        phase_alignment_verified=False,
        provider_event_verified=False,
        clock_alignment_verified=False,
        actual_boundary_verified=False,
        temporal_match_used=False,

        content_hash="b" * 64,
    )


def response(
    *,
    value=4.0,
    unit="score_0_10",
    timing=TrainingResponseTiming.SAME_DAY,
    knowledge_status=KnowledgeStatus.KNOWN,
    measurement_value_marker=None,
):
    execution = executed()

    measurement_value = (
        value
        if measurement_value_marker is None
        else measurement_value_marker
    )

    return ResponseStub(
        artifact_id="pt-training-response-evidence:response-1",
        schema_version=(
            TRAINING_RESPONSE_EVIDENCE_SCHEMA_V02
        ),
        athlete_id=ATHLETE,
        workout_session_id=SESSION,

        executed_training_evidence_id=(
            execution.artifact_id
        ),
        executed_training_evidence_hash=(
            execution.content_hash
        ),

        response_kind=(
            TrainingResponseKind.SESSION_FEEDBACK
        ),
        response_timing=timing,
        session_link_basis=(
            TrainingResponseLinkBasis
            .SOURCE_EXPLICIT_SESSION_ID
        ),

        observed_at=dt(13),
        available_at=dt(14),

        measurements=(
            TrainingResponseMeasurement(
                metric_key=(
                    "self_reported_fatigue_score"
                ),
                knowledge_status=knowledge_status,
                value=(
                    measurement_value
                    if knowledge_status
                    == KnowledgeStatus.KNOWN
                    else None
                ),
                unit=unit,
            ),
        ),

        interpretation=(
            TrainingResponseInterpretation
            .DESCRIPTIVE_ONLY
        ),
        session_identity_linked=True,

        causal_attribution_established=False,
        readiness_inference_authorized=False,
        fatigue_diagnosis_authorized=False,
        performance_prediction_authorized=False,
        prescription_change_authorized=False,

        created_at=dt(14),
        content_hash="c" * 64,
    )


def build(
    *,
    issuance_value=None,
    response_value=None,
    executed_value=None,
    issuance_persisted_at=None,
    response_persisted_at=None,
):
    return build_prospective_response_challenge(
        issuance=(
            issuance_value
            if issuance_value is not None
            else issuance()
        ),
        issuance_persisted_at=(
            issuance_persisted_at or dt(12)
        ),
        response=(
            response_value
            if response_value is not None
            else response()
        ),
        response_persisted_at=(
            response_persisted_at or dt(15)
        ),
        executed_training=(
            executed_value
            if executed_value is not None
            else executed()
        ),
    )


def test_above_prediction_matches_later_above_response():
    result = build()

    assert (
        result.actual_response_direction
        == ProspectiveResponseActualDirection
        .ABOVE_HISTORICAL_MEDIAN
    )

    assert (
        result.result
        == ProspectiveResponseChallengeResult
        .DIRECTION_MATCHED
    )

    assert result.directional_score_available is True
    assert result.prospective_challenge_established is True

    assert (
        result.evidence_level_ceiling
        == EffectEvidenceLevel.ASSOCIATION_SUPPORTED
    )

    assert result.prospective_validation_established is False
    assert result.causal_attribution_established is False
    assert result.effect_inference_authorized is False
    assert result.readiness_inference_authorized is False
    assert result.performance_prediction_authorized is False
    assert result.prescription_change_authorized is False
    assert result.planning_authorized is False

    assert result.verify_content_hash()


def test_above_prediction_mismatches_later_below_response():
    result = build(
        response_value=response(value=2.0)
    )

    assert (
        result.actual_response_direction
        == ProspectiveResponseActualDirection
        .BELOW_HISTORICAL_MEDIAN
    )

    assert (
        result.result
        == ProspectiveResponseChallengeResult
        .DIRECTION_MISMATCHED
    )

    assert result.directional_score_available is True


def test_below_prediction_matches_later_below_response():
    source = issuance(
        predicted_direction=(
            PersonalResponsePredictionDirection
            .BELOW_HISTORICAL_MEDIAN
        )
    )

    result = build(
        issuance_value=source,
        response_value=response(value=2.0),
    )

    assert (
        result.result
        == ProspectiveResponseChallengeResult
        .DIRECTION_MATCHED
    )


def test_response_equal_to_frozen_median_is_retained_but_unscorable():
    result = build(
        response_value=response(value=3.0)
    )

    assert (
        result.actual_response_direction
        == ProspectiveResponseActualDirection
        .AT_HISTORICAL_MEDIAN
    )

    assert (
        result.result
        == ProspectiveResponseChallengeResult
        .TIED_UNSCORABLE
    )

    assert result.prospective_challenge_established is True
    assert result.directional_score_available is False


def test_issuance_must_strictly_predate_response_observation():
    with pytest.raises(
        ValueError,
        match="strictly predate response observation",
    ):
        build(
            issuance_persisted_at=dt(13)
        )


def test_response_timing_must_match_prediction_context():
    with pytest.raises(
        ValueError,
        match="Response timing does not match",
    ):
        build(
            response_value=response(
                timing=TrainingResponseTiming.NEXT_MORNING
            )
        )


def test_executed_modality_must_match_prediction_context():
    with pytest.raises(
        ValueError,
        match="modality does not match",
    ):
        build(
            executed_value=executed(
                modality="CYCLING"
            )
        )


def test_response_unit_must_match_prediction_context():
    with pytest.raises(
        ValueError,
        match="unit does not match",
    ):
        build(
            response_value=response(
                unit="other-unit"
            )
        )


def test_non_known_response_is_not_scorable():
    with pytest.raises(
        ValueError,
        match="requires a KNOWN response value",
    ):
        build(
            response_value=response(
                knowledge_status=KnowledgeStatus.UNKNOWN
            )
        )


def test_boolean_response_is_not_numeric_prediction_outcome():
    with pytest.raises(
        ValueError,
        match="requires a numeric response value",
    ):
        build(
            response_value=response(
                value=True
            )
        )


def test_binding_identity_is_stable_per_issuance_not_response_choice():
    first_response = response(
        value=4.0
    )

    second_response = replace(
        response(value=2.0),
        artifact_id=(
            "pt-training-response-evidence:response-2"
        ),
        content_hash="d" * 64,
    )

    first = build(
        response_value=first_response
    )

    second = build(
        response_value=second_response
    )

    # B2 will use this stable identity for immutable first-write-wins
    # binding. Different response content therefore conflicts rather
    # than silently creating another outcome for the same issuance.
    assert first.binding_id == second.binding_id

    assert first.content_hash != second.content_hash
