from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
import hashlib
import math

from ..common.enums import KnowledgeStatus
from ..common.serialization import (
    CONTENT_HASH_ALGORITHM,
    compute_content_hash,
)
from ..common.time import to_utc
from ..executed_training import (
    AUTHORITATIVE_EXECUTED_TRAINING_SCHEMA_VERSION,
    AuthoritativeExecutedTrainingEvidence,
)
from ..response_evidence import (
    TRAINING_RESPONSE_EVIDENCE_SCHEMA_V02,
    AuthoritativeTrainingResponseEvidence,
    TrainingResponseInterpretation,
    TrainingResponseKind,
    TrainingResponseLinkBasis,
)
from .models import EffectEvidenceLevel
from .prospective_issuance import (
    PERSONAL_RESPONSE_PREDICTION_ISSUANCE_RULES_V01,
    PERSONAL_RESPONSE_PREDICTION_ISSUANCE_SCHEMA_V01,
    PersonalResponsePredictionIssuanceContract,
)
from .prospective_prediction import (
    PersonalResponsePredictionDirection,
)
from .response_reference import ResponseMetricReferenceKey


PROSPECTIVE_RESPONSE_CHALLENGE_SCHEMA_V01 = (
    "prospective-response-challenge-v0.1"
)

PROSPECTIVE_RESPONSE_CHALLENGE_RULES_V01 = (
    "prospective-response-challenge-rules-v0.1"
)

PROSPECTIVE_RESPONSE_CHALLENGE_HASH_EXCLUDE_FIELDS = (
    frozenset(
        {
            "binding_id",
            "created_at",
            "content_hash",
        }
    )
)


class ProspectiveResponseActualDirection(StrEnum):
    BELOW_HISTORICAL_MEDIAN = (
        "below_historical_median"
    )
    AT_HISTORICAL_MEDIAN = (
        "at_historical_median"
    )
    ABOVE_HISTORICAL_MEDIAN = (
        "above_historical_median"
    )


class ProspectiveResponseChallengeResult(StrEnum):
    DIRECTION_MATCHED = "direction_matched"
    DIRECTION_MISMATCHED = "direction_mismatched"
    TIED_UNSCORABLE = "tied_unscorable"


@dataclass(frozen=True)
class ProspectiveResponseChallenge:
    """One prospectively issued prediction bound to one later outcome.

    This is a single challenge result, not prospective validation.

    A matched challenge does not establish causality, readiness,
    performance-prediction authority, prescription authority, or
    planning authority.
    """

    binding_id: str
    schema_version: str
    rules_version: str

    athlete_id: str
    workout_session_id: str

    source_issuance_id: str
    source_issuance_content_hash: str

    source_candidate_id: str
    source_candidate_content_hash: str

    source_response_artifact_id: str
    source_response_content_hash: str

    source_executed_training_evidence_id: str
    source_executed_training_evidence_hash: str

    response_key: ResponseMetricReferenceKey

    prediction_direction: (
        PersonalResponsePredictionDirection
    )

    historical_response_median: float
    actual_response_value: float

    actual_response_direction: (
        ProspectiveResponseActualDirection
    )

    result: ProspectiveResponseChallengeResult

    issuance_persisted_at: datetime

    response_observed_at: datetime
    response_available_at: datetime
    response_persisted_at: datetime

    prospective_challenge_established: bool
    directional_score_available: bool

    evidence_level_ceiling: EffectEvidenceLevel
    association_supported: bool

    prospective_validation_established: bool
    causal_attribution_established: bool
    effect_inference_authorized: bool
    readiness_inference_authorized: bool
    performance_prediction_authorized: bool
    prescription_change_authorized: bool
    planning_authorized: bool

    created_at: datetime

    content_hash_algorithm: str
    content_hash: str

    def verify_content_hash(self) -> bool:
        return (
            compute_content_hash(
                self,
                exclude_fields=(
                    PROSPECTIVE_RESPONSE_CHALLENGE_HASH_EXCLUDE_FIELDS
                ),
            )
            == self.content_hash
        )


def personal_response_prediction_outcome_binding_id(
    issuance_id: str,
) -> str:
    """Stable one-binding-per-issuance identity."""

    if (
        not isinstance(issuance_id, str)
        or not issuance_id.strip()
    ):
        raise ValueError(
            "issuance_id must be a non-empty string."
        )

    digest = hashlib.sha256(
        issuance_id.encode("utf-8")
    ).hexdigest()

    return (
        "pt-personal-response-prediction-outcome:"
        f"{digest}"
    )


def _validate_issuance(
    issuance: PersonalResponsePredictionIssuanceContract,
) -> PersonalResponsePredictionDirection:
    if not issuance.verify_content_hash():
        raise ValueError(
            "Prediction issuance content hash does not verify."
        )

    if (
        issuance.schema_version
        != PERSONAL_RESPONSE_PREDICTION_ISSUANCE_SCHEMA_V01
        or issuance.rules_version
        != PERSONAL_RESPONSE_PREDICTION_ISSUANCE_RULES_V01
    ):
        raise ValueError(
            "Unsupported prediction issuance contract."
        )

    if issuance.response_prediction_available is not True:
        raise ValueError(
            "Prediction issuance has no available prediction."
        )

    if (
        issuance.evidence_level_ceiling
        != EffectEvidenceLevel.ASSOCIATION_SUPPORTED
        or issuance.association_supported is not True
    ):
        raise ValueError(
            "Prediction issuance must remain association-supported."
        )

    if any(
        (
            issuance.prospective_validation_established,
            issuance.causal_attribution_established,
            issuance.effect_inference_authorized,
            issuance.readiness_inference_authorized,
            issuance.performance_prediction_authorized,
            issuance.prescription_change_authorized,
            issuance.planning_authorized,
        )
    ):
        raise ValueError(
            "Prediction issuance contains unsupported "
            "stronger authority."
        )

    return PersonalResponsePredictionDirection(
        issuance.predicted_response_direction
    )


def _validate_response(
    response: AuthoritativeTrainingResponseEvidence,
) -> None:
    if not response.verify_content_hash():
        raise ValueError(
            "Authoritative response content hash does not verify."
        )

    if (
        response.schema_version
        != TRAINING_RESPONSE_EVIDENCE_SCHEMA_V02
    ):
        raise ValueError(
            "Unsupported authoritative response schema."
        )

    if (
        response.response_kind
        != TrainingResponseKind.SESSION_FEEDBACK
        or response.session_link_basis
        != TrainingResponseLinkBasis
        .SOURCE_EXPLICIT_SESSION_ID
        or response.interpretation
        != TrainingResponseInterpretation.DESCRIPTIVE_ONLY
        or response.session_identity_linked is not True
    ):
        raise ValueError(
            "Response artifact lacks the required "
            "authoritative descriptive session linkage."
        )

    if any(
        (
            response.causal_attribution_established,
            response.readiness_inference_authorized,
            response.fatigue_diagnosis_authorized,
            response.performance_prediction_authorized,
            response.prescription_change_authorized,
        )
    ):
        raise ValueError(
            "Response artifact claims unsupported stronger authority."
        )


def _validate_executed_training(
    executed: AuthoritativeExecutedTrainingEvidence,
) -> None:
    if not executed.verify_content_hash():
        raise ValueError(
            "Executed-training content hash does not verify."
        )

    if (
        executed.schema_version
        != AUTHORITATIVE_EXECUTED_TRAINING_SCHEMA_VERSION
    ):
        raise ValueError(
            "Unsupported authoritative executed-training schema."
        )

    if (
        executed.plan_identity_linked is not True
        or executed.plan_content_at_execution_status
        != "unverified"
    ):
        raise ValueError(
            "Executed-training artifact contains unsupported "
            "plan authority."
        )

    for field_name in (
        "occurrence_alignment_verified",
        "phase_alignment_verified",
        "provider_event_verified",
        "clock_alignment_verified",
        "actual_boundary_verified",
        "temporal_match_used",
    ):
        if getattr(executed, field_name) is not False:
            raise ValueError(
                f"{field_name} must remain false."
            )


def _numeric_response_value(
    *,
    response: AuthoritativeTrainingResponseEvidence,
    key: ResponseMetricReferenceKey,
) -> float:
    matching = tuple(
        measurement
        for measurement in response.measurements
        if measurement.metric_key == key.metric_key
    )

    if len(matching) != 1:
        raise ValueError(
            "Authoritative response must contain exactly one "
            "measurement for the predicted metric."
        )

    measurement = matching[0]

    if measurement.unit != key.unit:
        raise ValueError(
            "Response measurement unit does not match "
            "the prediction context."
        )

    if measurement.knowledge_status != KnowledgeStatus.KNOWN:
        raise ValueError(
            "Prospective challenge requires a KNOWN response value."
        )

    value = measurement.value

    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
    ):
        raise ValueError(
            "Prospective challenge requires a numeric "
            "response value."
        )

    numeric = float(value)

    if not math.isfinite(numeric):
        raise ValueError(
            "Prospective challenge response value must be finite."
        )

    return numeric


def build_prospective_response_challenge(
    *,
    issuance: PersonalResponsePredictionIssuanceContract,
    issuance_persisted_at: datetime,
    response: AuthoritativeTrainingResponseEvidence,
    response_persisted_at: datetime,
    executed_training: AuthoritativeExecutedTrainingEvidence,
) -> ProspectiveResponseChallenge:
    """Bind one durable prediction issuance to one later response.

    Prospective eligibility requires the durable issuance to predate:
    - real-world response observation,
    - response availability,
    - durable response persistence.

    The executed-training artifact independently verifies the exact
    stimulus modality linked by the response.

    The actual response is scored only against the historical median
    frozen in the issuance. No later baseline/reference recomputation
    is allowed here.
    """

    predicted_direction = _validate_issuance(
        issuance
    )

    _validate_response(response)
    _validate_executed_training(executed_training)

    if (
        response.athlete_id != issuance.athlete_id
        or executed_training.athlete_id
        != issuance.athlete_id
    ):
        raise ValueError(
            "Prediction, response, and execution athlete "
            "identity must match exactly."
        )

    if (
        response.workout_session_id
        != issuance.workout_session_id
        or executed_training.workout_session_id
        != issuance.workout_session_id
    ):
        raise ValueError(
            "Prediction, response, and execution session "
            "identity must match exactly."
        )

    if (
        response.executed_training_evidence_id
        != executed_training.artifact_id
        or response.executed_training_evidence_hash
        != executed_training.content_hash
    ):
        raise ValueError(
            "Response does not hash-bind the supplied "
            "executed-training artifact."
        )

    if (
        response.response_timing
        != issuance.response_key.response_timing
    ):
        raise ValueError(
            "Response timing does not match the prediction context."
        )

    if (
        executed_training.modality_key
        != issuance.response_key.stimulus_modality_key
    ):
        raise ValueError(
            "Executed-training modality does not match "
            "the prediction context."
        )

    actual_value = _numeric_response_value(
        response=response,
        key=issuance.response_key,
    )

    historical_median = float(
        issuance.historical_response_median
    )

    if not math.isfinite(historical_median):
        raise ValueError(
            "Frozen historical response median must be finite."
        )

    issued_at = to_utc(
        issuance_persisted_at,
        field_name="issuance_persisted_at",
    )

    prediction_at = to_utc(
        issuance.prediction_at,
        field_name="issuance.prediction_at",
    )

    cutoff_at = to_utc(
        issuance.information_cutoff_at,
        field_name="issuance.information_cutoff_at",
    )

    response_observed = to_utc(
        response.observed_at,
        field_name="response.observed_at",
    )

    response_available = to_utc(
        response.available_at,
        field_name="response.available_at",
    )

    response_created = to_utc(
        response.created_at,
        field_name="response.created_at",
    )

    response_persisted = to_utc(
        response_persisted_at,
        field_name="response_persisted_at",
    )

    if issued_at < prediction_at:
        raise ValueError(
            "Durable issuance cannot predate prediction_at."
        )

    if issued_at < cutoff_at:
        raise ValueError(
            "Durable issuance cannot predate its information cutoff."
        )

    if response_available < response_observed:
        raise ValueError(
            "Response availability cannot predate observation."
        )

    if response_created < response_available:
        raise ValueError(
            "Response artifact cannot predate availability."
        )

    if response_persisted < response_created:
        raise ValueError(
            "Durable response persistence cannot predate "
            "the response artifact."
        )

    if not issued_at < response_observed:
        raise ValueError(
            "Prediction issuance must strictly predate "
            "response observation."
        )

    if not issued_at < response_available:
        raise ValueError(
            "Prediction issuance must strictly predate "
            "response availability."
        )

    if not issued_at < response_persisted:
        raise ValueError(
            "Prediction issuance must strictly predate "
            "durable response persistence."
        )

    if actual_value > historical_median:
        actual_direction = (
            ProspectiveResponseActualDirection
            .ABOVE_HISTORICAL_MEDIAN
        )
    elif actual_value < historical_median:
        actual_direction = (
            ProspectiveResponseActualDirection
            .BELOW_HISTORICAL_MEDIAN
        )
    else:
        actual_direction = (
            ProspectiveResponseActualDirection
            .AT_HISTORICAL_MEDIAN
        )

    if (
        actual_direction
        == ProspectiveResponseActualDirection
        .AT_HISTORICAL_MEDIAN
    ):
        result = (
            ProspectiveResponseChallengeResult
            .TIED_UNSCORABLE
        )
        directional_score_available = False
    else:
        if (
            predicted_direction
            == PersonalResponsePredictionDirection
            .ABOVE_HISTORICAL_MEDIAN
        ):
            expected_actual = (
                ProspectiveResponseActualDirection
                .ABOVE_HISTORICAL_MEDIAN
            )
        elif (
            predicted_direction
            == PersonalResponsePredictionDirection
            .BELOW_HISTORICAL_MEDIAN
        ):
            expected_actual = (
                ProspectiveResponseActualDirection
                .BELOW_HISTORICAL_MEDIAN
            )
        else:
            raise ValueError(
                "Unsupported prediction direction."
            )

        result = (
            ProspectiveResponseChallengeResult
            .DIRECTION_MATCHED
            if actual_direction == expected_actual
            else ProspectiveResponseChallengeResult
            .DIRECTION_MISMATCHED
        )

        directional_score_available = True

    binding_id = (
        personal_response_prediction_outcome_binding_id(
            issuance.issuance_id
        )
    )

    created_at = response_persisted

    provisional = ProspectiveResponseChallenge(
        binding_id=binding_id,
        schema_version=(
            PROSPECTIVE_RESPONSE_CHALLENGE_SCHEMA_V01
        ),
        rules_version=(
            PROSPECTIVE_RESPONSE_CHALLENGE_RULES_V01
        ),

        athlete_id=issuance.athlete_id,
        workout_session_id=(
            issuance.workout_session_id
        ),

        source_issuance_id=issuance.issuance_id,
        source_issuance_content_hash=(
            issuance.content_hash
        ),

        source_candidate_id=(
            issuance.source_candidate_id
        ),
        source_candidate_content_hash=(
            issuance.source_candidate_content_hash
        ),

        source_response_artifact_id=(
            response.artifact_id
        ),
        source_response_content_hash=(
            response.content_hash
        ),

        source_executed_training_evidence_id=(
            executed_training.artifact_id
        ),
        source_executed_training_evidence_hash=(
            executed_training.content_hash
        ),

        response_key=issuance.response_key,

        prediction_direction=predicted_direction,

        historical_response_median=(
            historical_median
        ),
        actual_response_value=actual_value,

        actual_response_direction=(
            actual_direction
        ),

        result=result,

        issuance_persisted_at=issued_at,

        response_observed_at=response_observed,
        response_available_at=response_available,
        response_persisted_at=response_persisted,

        prospective_challenge_established=True,
        directional_score_available=(
            directional_score_available
        ),

        # One challenge result remains below prospective validation.
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

        created_at=created_at,

        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash="",
    )

    digest = compute_content_hash(
        provisional,
        exclude_fields=(
            PROSPECTIVE_RESPONSE_CHALLENGE_HASH_EXCLUDE_FIELDS
        ),
    )

    return ProspectiveResponseChallenge(
        **{
            **provisional.__dict__,
            "content_hash": digest,
        }
    )
