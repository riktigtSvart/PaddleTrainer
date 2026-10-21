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
from .prospective_issuance import (
    PERSONAL_RESPONSE_PREDICTION_ISSUANCE_RULES_V01,
    PERSONAL_RESPONSE_PREDICTION_ISSUANCE_SCHEMA_V01,
    PersonalResponsePredictionIssuanceContract,
)
from .response_reference import (
    ResponseMetricReferenceKey,
)


PERSONAL_RESPONSE_PREDICTION_CHALLENGE_SLOT_SCHEMA_V01 = (
    "personal-response-prediction-challenge-slot-v0.1"
)

PERSONAL_RESPONSE_PREDICTION_CHALLENGE_SLOT_RULES_V01 = (
    "personal-response-prediction-challenge-slot-rules-v0.1"
)

PERSONAL_RESPONSE_PREDICTION_CHALLENGE_SLOT_IDENTITY_V01 = (
    "personal-response-prediction-challenge-slot-identity-v0.1"
)

PERSONAL_RESPONSE_PREDICTION_CHALLENGE_SLOT_HASH_EXCLUDE_FIELDS = (
    frozenset(
        {
            "slot_id",
            "content_hash",
        }
    )
)


@dataclass(frozen=True)
class _ChallengeSlotIdentity:
    identity_version: str

    athlete_id: str
    workout_session_id: str

    model_id: str
    model_version: str

    predictor_key: PersonalAssociationPredictorKey
    response_key: ResponseMetricReferenceKey


@dataclass(frozen=True)
class PersonalResponsePredictionChallengeSlot:
    """Immutable one-issuance reservation for one prospective challenge.

    Slot identity intentionally excludes:
    - candidate identity,
    - target predictor value,
    - historical baseline values,
    - predicted direction,
    - association source identity.

    Therefore those values cannot be changed and re-issued for the same
    athlete/session/model/predictor/response challenge.
    """

    slot_id: str
    schema_version: str
    rules_version: str

    athlete_id: str
    workout_session_id: str

    model_id: str
    model_version: str

    predictor_key: PersonalAssociationPredictorKey
    response_key: ResponseMetricReferenceKey

    source_issuance_id: str
    source_issuance_content_hash: str
    source_issuance_schema_version: str
    source_issuance_rules_version: str

    content_hash_algorithm: str
    content_hash: str

    def verify_content_hash(self) -> bool:
        return (
            compute_content_hash(
                self,
                exclude_fields=(
                    PERSONAL_RESPONSE_PREDICTION_CHALLENGE_SLOT_HASH_EXCLUDE_FIELDS
                ),
            )
            == self.content_hash
        )


def _require_non_empty(
    value: str,
    *,
    field_name: str,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"{field_name} must be a non-empty string."
        )

    return value


def _validate_issuance(
    issuance: PersonalResponsePredictionIssuanceContract,
) -> None:
    if not issuance.verify_content_hash():
        raise ValueError(
            "Challenge-slot issuance content hash "
            "does not verify."
        )

    if (
        issuance.schema_version
        != PERSONAL_RESPONSE_PREDICTION_ISSUANCE_SCHEMA_V01
        or issuance.rules_version
        != PERSONAL_RESPONSE_PREDICTION_ISSUANCE_RULES_V01
    ):
        raise ValueError(
            "Unsupported challenge-slot issuance contract."
        )

    _require_non_empty(
        issuance.athlete_id,
        field_name="issuance.athlete_id",
    )

    _require_non_empty(
        issuance.workout_session_id,
        field_name="issuance.workout_session_id",
    )

    _require_non_empty(
        issuance.model_id,
        field_name="issuance.model_id",
    )

    _require_non_empty(
        issuance.model_version,
        field_name="issuance.model_version",
    )

    if (
        issuance.response_prediction_available is not True
        or issuance.evidence_level_ceiling
        != EffectEvidenceLevel.ASSOCIATION_SUPPORTED
        or issuance.association_supported is not True
    ):
        raise ValueError(
            "Challenge-slot issuance lacks required "
            "association-supported prediction authority."
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
            "Challenge-slot issuance contains unsupported "
            "stronger authority."
        )


def personal_response_prediction_challenge_slot_id(
    issuance: PersonalResponsePredictionIssuanceContract,
) -> str:
    """Stable identity for one exact prospective prediction question."""

    _validate_issuance(
        issuance
    )

    identity = _ChallengeSlotIdentity(
        identity_version=(
            PERSONAL_RESPONSE_PREDICTION_CHALLENGE_SLOT_IDENTITY_V01
        ),

        athlete_id=issuance.athlete_id,
        workout_session_id=(
            issuance.workout_session_id
        ),

        model_id=issuance.model_id,
        model_version=issuance.model_version,

        predictor_key=issuance.predictor_key,
        response_key=issuance.response_key,
    )

    digest = compute_content_hash(
        identity
    )

    return (
        "pt-personal-response-prediction-challenge-slot:"
        + digest
    )


def build_personal_response_prediction_challenge_slot(
    issuance: PersonalResponsePredictionIssuanceContract,
) -> PersonalResponsePredictionChallengeSlot:
    """Bind one stable challenge slot to exactly one issuance."""

    _validate_issuance(
        issuance
    )

    slot_id = (
        personal_response_prediction_challenge_slot_id(
            issuance
        )
    )

    provisional = PersonalResponsePredictionChallengeSlot(
        slot_id=slot_id,
        schema_version=(
            PERSONAL_RESPONSE_PREDICTION_CHALLENGE_SLOT_SCHEMA_V01
        ),
        rules_version=(
            PERSONAL_RESPONSE_PREDICTION_CHALLENGE_SLOT_RULES_V01
        ),

        athlete_id=issuance.athlete_id,
        workout_session_id=(
            issuance.workout_session_id
        ),

        model_id=issuance.model_id,
        model_version=issuance.model_version,

        predictor_key=issuance.predictor_key,
        response_key=issuance.response_key,

        source_issuance_id=(
            issuance.issuance_id
        ),
        source_issuance_content_hash=(
            issuance.content_hash
        ),
        source_issuance_schema_version=(
            issuance.schema_version
        ),
        source_issuance_rules_version=(
            issuance.rules_version
        ),

        content_hash_algorithm=(
            CONTENT_HASH_ALGORITHM
        ),
        content_hash="",
    )

    digest = compute_content_hash(
        provisional,
        exclude_fields=(
            PERSONAL_RESPONSE_PREDICTION_CHALLENGE_SLOT_HASH_EXCLUDE_FIELDS
        ),
    )

    return PersonalResponsePredictionChallengeSlot(
        **{
            **provisional.__dict__,
            "content_hash": digest,
        }
    )
