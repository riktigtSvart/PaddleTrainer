from __future__ import annotations

from dataclasses import dataclass

from ..common.serialization import (
    CONTENT_HASH_ALGORITHM,
    compute_content_hash,
)
from .association_dataset import (
    PersonalAssociationPredictorKey,
)
from .models import EffectEvidenceLevel
from .prospective_prediction import (
    PERSONAL_RESPONSE_PREDICTION_MODEL_ID_V01,
    PERSONAL_RESPONSE_PREDICTION_MODEL_VERSION_V01,
    PERSONAL_RESPONSE_PREDICTION_RULES_V01,
    PERSONAL_RESPONSE_PREDICTION_SCHEMA_V01,
    PersonalResponsePredictionCandidate,
    PersonalResponsePredictionStatus,
)
from .response_reference import (
    ResponseMetricReferenceKey,
)


PERSONAL_RESPONSE_PREDICTION_ISSUANCE_SCHEMA_V01 = (
    "personal-response-prediction-issuance-v0.1"
)

PERSONAL_RESPONSE_PREDICTION_ISSUANCE_RULES_V01 = (
    "personal-response-prediction-issuance-rules-v0.1"
)

PERSONAL_RESPONSE_PREDICTION_ISSUANCE_HASH_EXCLUDE_FIELDS = (
    frozenset(
        {
            "issuance_id",
            "content_hash",
        }
    )
)


@dataclass(frozen=True)
class PersonalResponsePredictionIssuanceContract:
    """Semantic contract frozen by P2.3A2 persistence.

    The contract deliberately contains no durable issuance timestamp.
    The repository row created_at is the first durable issuance time.

    Merely constructing this contract does not establish issuance proof.
    """

    issuance_id: str
    schema_version: str
    rules_version: str

    athlete_id: str
    workout_session_id: str

    source_candidate_id: str
    source_candidate_content_hash: str
    source_candidate_schema_version: str
    source_candidate_rules_version: str

    model_id: str
    model_version: str

    predictor_key: PersonalAssociationPredictorKey
    response_key: ResponseMetricReferenceKey

    information_cutoff_at: object
    prediction_at: object

    target_predictor_value: float
    historical_response_median: float

    predicted_response_direction: object

    response_prediction_available: bool

    evidence_level_ceiling: EffectEvidenceLevel
    association_supported: bool

    prospective_validation_established: bool
    causal_attribution_established: bool
    effect_inference_authorized: bool
    readiness_inference_authorized: bool
    performance_prediction_authorized: bool
    prescription_change_authorized: bool
    planning_authorized: bool

    content_hash_algorithm: str
    content_hash: str

    def verify_content_hash(self) -> bool:
        return (
            compute_content_hash(
                self,
                exclude_fields=(
                    PERSONAL_RESPONSE_PREDICTION_ISSUANCE_HASH_EXCLUDE_FIELDS
                ),
            )
            == self.content_hash
        )


def _validate_candidate(
    candidate: PersonalResponsePredictionCandidate,
) -> None:
    if not candidate.verify_content_hash():
        raise ValueError(
            "Prediction candidate content hash does not verify."
        )

    if (
        candidate.schema_version
        != PERSONAL_RESPONSE_PREDICTION_SCHEMA_V01
        or candidate.rules_version
        != PERSONAL_RESPONSE_PREDICTION_RULES_V01
    ):
        raise ValueError(
            "Unsupported prediction candidate contract."
        )

    if (
        candidate.model_id
        != PERSONAL_RESPONSE_PREDICTION_MODEL_ID_V01
        or candidate.model_version
        != PERSONAL_RESPONSE_PREDICTION_MODEL_VERSION_V01
    ):
        raise ValueError(
            "Unsupported prediction model contract."
        )

    if (
        candidate.status
        != PersonalResponsePredictionStatus
        .PREDICTION_AVAILABLE
        or candidate.response_prediction_available
        is not True
        or candidate.predicted_response_direction
        is None
    ):
        raise ValueError(
            "Durable issuance requires an available prediction."
        )

    if candidate.limitation_codes:
        raise ValueError(
            "Available prediction cannot carry withholding limitations."
        )

    if candidate.issuance_proof_established is not False:
        raise ValueError(
            "P2.3A1 candidate must not pre-claim issuance proof."
        )

    if (
        candidate.evidence_level_ceiling
        != EffectEvidenceLevel.ASSOCIATION_SUPPORTED
        or candidate.association_supported is not True
    ):
        raise ValueError(
            "Prediction candidate must remain association-supported."
        )

    if any(
        (
            candidate.prospective_validation_established,
            candidate.causal_attribution_established,
            candidate.effect_inference_authorized,
            candidate.readiness_inference_authorized,
            candidate.performance_prediction_authorized,
            candidate.prescription_change_authorized,
            candidate.planning_authorized,
        )
    ):
        raise ValueError(
            "Prediction candidate contains unsupported stronger authority."
        )

    if (
        candidate.information_cutoff_at
        > candidate.prediction_at
        or candidate.prediction_at
        > candidate.created_at
    ):
        raise ValueError(
            "Prediction candidate has invalid temporal ordering."
        )


def build_personal_response_prediction_issuance_contract(
    candidate: PersonalResponsePredictionCandidate,
) -> PersonalResponsePredictionIssuanceContract:
    """Build deterministic content to freeze at the issuance boundary."""

    _validate_candidate(candidate)

    provisional = PersonalResponsePredictionIssuanceContract(
        issuance_id="PENDING",
        schema_version=(
            PERSONAL_RESPONSE_PREDICTION_ISSUANCE_SCHEMA_V01
        ),
        rules_version=(
            PERSONAL_RESPONSE_PREDICTION_ISSUANCE_RULES_V01
        ),

        athlete_id=candidate.athlete_id,
        workout_session_id=candidate.workout_session_id,

        source_candidate_id=candidate.candidate_id,
        source_candidate_content_hash=(
            candidate.content_hash
        ),
        source_candidate_schema_version=(
            candidate.schema_version
        ),
        source_candidate_rules_version=(
            candidate.rules_version
        ),

        model_id=candidate.model_id,
        model_version=candidate.model_version,

        predictor_key=candidate.predictor_key,
        response_key=candidate.response_key,

        information_cutoff_at=(
            candidate.information_cutoff_at
        ),
        prediction_at=candidate.prediction_at,

        target_predictor_value=(
            candidate.target_predictor_value
        ),
        historical_response_median=(
            candidate.historical_response_median
        ),

        predicted_response_direction=(
            candidate.predicted_response_direction
        ),

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

    return PersonalResponsePredictionIssuanceContract(
        **{
            **provisional.__dict__,
            "issuance_id": (
                "pt-personal-response-prediction-issuance:"
                f"{digest}"
            ),
            "content_hash": digest,
        }
    )
