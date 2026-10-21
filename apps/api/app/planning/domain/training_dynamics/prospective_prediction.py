from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
import hashlib
import json
import math
from statistics import median

from ..common.time import to_utc
from .association_dataset import (
    PersonalAssociationDataset,
    PersonalAssociationPredictorKey,
)
from .association_estimate import (
    PersonalAssociationEstimate,
    build_personal_association_estimate,
)
from .association_support import (
    PersonalAssociationSupportAssessment,
    PersonalAssociationSupportStatus,
    assess_personal_association_support,
)
from .association_evidence import (
    PersonalAssociationEvidence,
    PersonalAssociationEvidenceStatus,
    build_personal_association_evidence,
)
from .models import EffectEvidenceLevel
from .response_reference import ResponseMetricReferenceKey


PREDICTION_TARGET_PREDICTOR_SCHEMA_V01 = (
    "prediction-target-predictor-v0.1"
)

PERSONAL_RESPONSE_PREDICTION_SCHEMA_V01 = (
    "personal-response-prediction-candidate-v0.1"
)

PERSONAL_RESPONSE_PREDICTION_RULES_V01 = (
    "personal-response-prediction-rules-v0.1"
)

PERSONAL_RESPONSE_PREDICTION_MODEL_ID_V01 = (
    "personal-monotonic-median-direction"
)

PERSONAL_RESPONSE_PREDICTION_MODEL_VERSION_V01 = (
    "0.1.0"
)


class PersonalResponsePredictionStatus(StrEnum):
    WITHHELD = "WITHHELD"
    PREDICTION_AVAILABLE = "PREDICTION_AVAILABLE"


class PersonalResponsePredictionDirection(StrEnum):
    BELOW_HISTORICAL_MEDIAN = (
        "BELOW_HISTORICAL_MEDIAN"
    )
    ABOVE_HISTORICAL_MEDIAN = (
        "ABOVE_HISTORICAL_MEDIAN"
    )


class PersonalResponsePredictionLimitationCode(StrEnum):
    TARGET_PREDICTOR_EQUALS_HISTORICAL_MEDIAN = (
        "TARGET_PREDICTOR_EQUALS_HISTORICAL_MEDIAN"
    )
    TARGET_PREDICTOR_OUTSIDE_HISTORICAL_RANGE = (
        "TARGET_PREDICTOR_OUTSIDE_HISTORICAL_RANGE"
    )


@dataclass(frozen=True)
class PredictionTargetPredictorObservation:
    observation_id: str
    schema_version: str

    athlete_id: str
    workout_session_id: str

    source_evidence_id: str
    source_evidence_content_hash: str

    predictor_key: PersonalAssociationPredictorKey
    stimulus_modality_key: str
    predictor_value: float

    observed_at: datetime
    available_at: datetime

    created_at: datetime
    content_hash: str

    def verify_content_hash(self) -> bool:
        return (
            self.content_hash
            == _target_observation_content_hash(self)
        )


@dataclass(frozen=True)
class PersonalResponsePredictionCandidate:
    """P2.3A1 deterministic prediction candidate.

    This is a prediction model output, but not prospective-validation
    evidence. In particular, created_at/prediction_at alone do not prove
    that the prediction was durably issued before a later outcome.

    P2.3A2 must provide independent durable issuance proof before this
    candidate can participate in prospective validation.
    """

    candidate_id: str
    schema_version: str
    rules_version: str

    model_id: str
    model_version: str

    athlete_id: str
    workout_session_id: str

    source_dataset_id: str
    source_dataset_content_hash: str

    source_estimate_id: str
    source_estimate_content_hash: str

    source_support_assessment_id: str
    source_support_assessment_content_hash: str

    source_association_evidence_id: str
    source_association_evidence_content_hash: str

    target_predictor_observation_id: str
    target_predictor_observation_content_hash: str

    predictor_key: PersonalAssociationPredictorKey
    response_key: ResponseMetricReferenceKey

    historical_pair_count: int

    historical_predictor_min: float
    historical_predictor_median: float
    historical_predictor_max: float

    historical_response_median: float

    source_spearman_rho: float

    target_predictor_value: float

    predicted_response_direction: (
        PersonalResponsePredictionDirection
        | None
    )

    status: PersonalResponsePredictionStatus

    limitation_codes: tuple[
        PersonalResponsePredictionLimitationCode,
        ...,
    ]

    information_cutoff_at: datetime
    prediction_at: datetime

    response_prediction_available: bool

    # A1 does not prove real-world issuance timing.
    issuance_proof_established: bool

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
    content_hash: str

    def verify_content_hash(self) -> bool:
        return (
            self.content_hash
            == _prediction_content_hash(self)
        )


def _require_text(
    value: str,
    *,
    field_name: str,
) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
    ):
        raise ValueError(
            f"{field_name} must be non-empty."
        )

    return value.strip()


def _require_hash(
    value: str,
    *,
    field_name: str,
) -> str:
    text = _require_text(
        value,
        field_name=field_name,
    )

    if (
        len(text) != 64
        or any(
            char not in "0123456789abcdef"
            for char in text.lower()
        )
    ):
        raise ValueError(
            f"{field_name} must be a 64-character hex hash."
        )

    return text.lower()


def _finite_numeric(
    value: object,
    *,
    field_name: str,
) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(
            value,
            (int, float),
        )
    ):
        raise ValueError(
            f"{field_name} must be numeric."
        )

    numeric = float(value)

    if not math.isfinite(numeric):
        raise ValueError(
            f"{field_name} must be finite."
        )

    if numeric == 0.0:
        return 0.0

    return numeric


def _enum_value(value: object) -> object:
    if isinstance(value, StrEnum):
        return value.value

    return getattr(
        value,
        "value",
        value,
    )


def _predictor_key_payload(
    key: PersonalAssociationPredictorKey,
) -> dict[str, object]:
    return {
        "metric_key": key.metric_key,
        "unit": key.unit,
    }


def _response_key_payload(
    key: ResponseMetricReferenceKey,
) -> dict[str, object]:
    return {
        "metric_key": key.metric_key,
        "unit": key.unit,
        "response_timing": _enum_value(
            key.response_timing
        ),
        "stimulus_modality_key": (
            key.stimulus_modality_key
        ),
    }


def _target_observation_payload(
    observation: PredictionTargetPredictorObservation,
) -> dict[str, object]:
    return {
        "schema_version": observation.schema_version,

        "athlete_id": observation.athlete_id,
        "workout_session_id": (
            observation.workout_session_id
        ),

        "source_evidence_id": (
            observation.source_evidence_id
        ),
        "source_evidence_content_hash": (
            observation.source_evidence_content_hash
        ),

        "predictor_key": _predictor_key_payload(
            observation.predictor_key
        ),

        "stimulus_modality_key": (
            observation.stimulus_modality_key
        ),

        "predictor_value": (
            observation.predictor_value
        ),

        "observed_at": (
            observation.observed_at.isoformat()
        ),
        "available_at": (
            observation.available_at.isoformat()
        ),
    }


def _target_observation_content_hash(
    observation: PredictionTargetPredictorObservation,
) -> str:
    canonical = json.dumps(
        _target_observation_payload(
            observation
        ),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )

    return hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()


def create_prediction_target_predictor_observation(
    *,
    athlete_id: str,
    workout_session_id: str,
    source_evidence_id: str,
    source_evidence_content_hash: str,
    predictor_key: PersonalAssociationPredictorKey,
    stimulus_modality_key: str,
    predictor_value: float,
    observed_at: datetime,
    available_at: datetime,
    created_at: datetime,
) -> PredictionTargetPredictorObservation:
    athlete = _require_text(
        athlete_id,
        field_name="athlete_id",
    )

    session = _require_text(
        workout_session_id,
        field_name="workout_session_id",
    )

    source_id = _require_text(
        source_evidence_id,
        field_name="source_evidence_id",
    )

    source_hash = _require_hash(
        source_evidence_content_hash,
        field_name="source_evidence_content_hash",
    )

    modality = _require_text(
        stimulus_modality_key,
        field_name="stimulus_modality_key",
    )

    value = _finite_numeric(
        predictor_value,
        field_name="predictor_value",
    )

    observed = to_utc(
        observed_at,
        field_name="observed_at",
    )

    available = to_utc(
        available_at,
        field_name="available_at",
    )

    materialized = to_utc(
        created_at,
        field_name="created_at",
    )

    if available < observed:
        raise ValueError(
            "Target predictor available_at cannot "
            "precede observed_at."
        )

    if materialized < available:
        raise ValueError(
            "Target predictor observation cannot "
            "predate source availability."
        )

    provisional = PredictionTargetPredictorObservation(
        observation_id="PENDING",
        schema_version=(
            PREDICTION_TARGET_PREDICTOR_SCHEMA_V01
        ),

        athlete_id=athlete,
        workout_session_id=session,

        source_evidence_id=source_id,
        source_evidence_content_hash=source_hash,

        predictor_key=predictor_key,
        stimulus_modality_key=modality,
        predictor_value=value,

        observed_at=observed,
        available_at=available,

        created_at=materialized,
        content_hash="PENDING",
    )

    digest = _target_observation_content_hash(
        provisional
    )

    return PredictionTargetPredictorObservation(
        **{
            **provisional.__dict__,
            "observation_id": (
                "pt-prediction-target-predictor:"
                f"{digest}"
            ),
            "content_hash": digest,
        }
    )


def _prediction_payload(
    prediction: PersonalResponsePredictionCandidate,
) -> dict[str, object]:
    return {
        "schema_version": prediction.schema_version,
        "rules_version": prediction.rules_version,

        "model_id": prediction.model_id,
        "model_version": prediction.model_version,

        "athlete_id": prediction.athlete_id,
        "workout_session_id": (
            prediction.workout_session_id
        ),

        "source_dataset_id": (
            prediction.source_dataset_id
        ),
        "source_dataset_content_hash": (
            prediction.source_dataset_content_hash
        ),

        "source_estimate_id": (
            prediction.source_estimate_id
        ),
        "source_estimate_content_hash": (
            prediction.source_estimate_content_hash
        ),

        "source_support_assessment_id": (
            prediction.source_support_assessment_id
        ),
        "source_support_assessment_content_hash": (
            prediction
            .source_support_assessment_content_hash
        ),

        "source_association_evidence_id": (
            prediction.source_association_evidence_id
        ),
        "source_association_evidence_content_hash": (
            prediction
            .source_association_evidence_content_hash
        ),

        "target_predictor_observation_id": (
            prediction.target_predictor_observation_id
        ),
        "target_predictor_observation_content_hash": (
            prediction
            .target_predictor_observation_content_hash
        ),

        "predictor_key": _predictor_key_payload(
            prediction.predictor_key
        ),
        "response_key": _response_key_payload(
            prediction.response_key
        ),

        "historical_pair_count": (
            prediction.historical_pair_count
        ),

        "historical_predictor_min": (
            prediction.historical_predictor_min
        ),
        "historical_predictor_median": (
            prediction.historical_predictor_median
        ),
        "historical_predictor_max": (
            prediction.historical_predictor_max
        ),

        "historical_response_median": (
            prediction.historical_response_median
        ),

        "source_spearman_rho": (
            prediction.source_spearman_rho
        ),

        "target_predictor_value": (
            prediction.target_predictor_value
        ),

        "predicted_response_direction": (
            prediction.predicted_response_direction.value
            if (
                prediction.predicted_response_direction
                is not None
            )
            else None
        ),

        "status": prediction.status.value,

        "limitation_codes": [
            item.value
            for item in prediction.limitation_codes
        ],

        "information_cutoff_at": (
            prediction.information_cutoff_at.isoformat()
        ),
        "prediction_at": (
            prediction.prediction_at.isoformat()
        ),

        "response_prediction_available": (
            prediction.response_prediction_available
        ),

        "issuance_proof_established": (
            prediction.issuance_proof_established
        ),

        "evidence_level_ceiling": (
            prediction.evidence_level_ceiling.value
        ),
        "association_supported": (
            prediction.association_supported
        ),

        "prospective_validation_established": (
            prediction.prospective_validation_established
        ),
        "causal_attribution_established": (
            prediction.causal_attribution_established
        ),
        "effect_inference_authorized": (
            prediction.effect_inference_authorized
        ),
        "readiness_inference_authorized": (
            prediction.readiness_inference_authorized
        ),
        "performance_prediction_authorized": (
            prediction.performance_prediction_authorized
        ),
        "prescription_change_authorized": (
            prediction.prescription_change_authorized
        ),
        "planning_authorized": (
            prediction.planning_authorized
        ),
    }


def _prediction_content_hash(
    prediction: PersonalResponsePredictionCandidate,
) -> str:
    canonical = json.dumps(
        _prediction_payload(
            prediction
        ),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )

    return hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()


def _validate_association_source(
    *,
    dataset: PersonalAssociationDataset,
    estimate: PersonalAssociationEstimate,
    support: PersonalAssociationSupportAssessment,
    evidence: PersonalAssociationEvidence,
) -> None:
    if not dataset.verify_content_hash():
        raise ValueError(
            "Association dataset hash does not verify."
        )

    if not estimate.verify_content_hash():
        raise ValueError(
            "Association estimate hash does not verify."
        )

    if not support.verify_content_hash():
        raise ValueError(
            "Association support hash does not verify."
        )

    if not evidence.verify_content_hash():
        raise ValueError(
            "Association evidence hash does not verify."
        )

    replayed_estimate = (
        build_personal_association_estimate(
            dataset=dataset,
            created_at=estimate.created_at,
        )
    )

    if (
        replayed_estimate.estimate_id
        != estimate.estimate_id
        or replayed_estimate.content_hash
        != estimate.content_hash
    ):
        raise ValueError(
            "Association estimate does not replay."
        )

    replayed_support = (
        assess_personal_association_support(
            dataset=dataset,
            estimate=estimate,
            created_at=support.created_at,
        )
    )

    if (
        replayed_support.assessment_id
        != support.assessment_id
        or replayed_support.content_hash
        != support.content_hash
    ):
        raise ValueError(
            "Association support does not replay."
        )

    replayed_evidence = (
        build_personal_association_evidence(
            dataset=dataset,
            estimate=estimate,
            support=support,
            created_at=evidence.created_at,
        )
    )

    if (
        replayed_evidence.evidence_id
        != evidence.evidence_id
        or replayed_evidence.content_hash
        != evidence.content_hash
    ):
        raise ValueError(
            "Association evidence does not replay."
        )

    if (
        evidence.status
        != PersonalAssociationEvidenceStatus
        .ASSOCIATION_SUPPORTED
        or evidence.evidence_level
        != EffectEvidenceLevel
        .ASSOCIATION_SUPPORTED
        or evidence.association_supported
        is not True
    ):
        raise ValueError(
            "Prediction candidate requires "
            "ASSOCIATION_SUPPORTED evidence."
        )

    if (
        support.status
        != PersonalAssociationSupportStatus
        .SUPPORT_CRITERIA_MET
    ):
        raise ValueError(
            "Prediction candidate requires "
            "SUPPORT_CRITERIA_MET source support."
        )

    if any(
        (
            evidence.prospective_validation_established,
            evidence.causal_attribution_established,
            evidence.effect_inference_authorized,
            evidence.readiness_inference_authorized,
            evidence.performance_prediction_authorized,
            evidence.prescription_change_authorized,
            evidence.planning_authorized,
        )
    ):
        raise ValueError(
            "Association evidence contains unsupported "
            "stronger authority."
        )


def build_personal_response_prediction_candidate(
    *,
    dataset: PersonalAssociationDataset,
    estimate: PersonalAssociationEstimate,
    support: PersonalAssociationSupportAssessment,
    association_evidence: PersonalAssociationEvidence,
    target_predictor: PredictionTargetPredictorObservation,
    information_cutoff_at: datetime,
    prediction_at: datetime,
    created_at: datetime,
) -> PersonalResponsePredictionCandidate:
    """Build a bounded P2.3A1 post-exposure/pre-response prediction.

    This function deliberately performs no outcome read and accepts no
    response observation for the target session.
    """

    _validate_association_source(
        dataset=dataset,
        estimate=estimate,
        support=support,
        evidence=association_evidence,
    )

    if not target_predictor.verify_content_hash():
        raise ValueError(
            "Target predictor observation hash "
            "does not verify."
        )

    cutoff = to_utc(
        information_cutoff_at,
        field_name="information_cutoff_at",
    )

    predicted_at = to_utc(
        prediction_at,
        field_name="prediction_at",
    )

    materialized = to_utc(
        created_at,
        field_name="created_at",
    )

    if cutoff > predicted_at:
        raise ValueError(
            "information_cutoff_at cannot be after "
            "prediction_at."
        )

    if materialized < predicted_at:
        raise ValueError(
            "Prediction candidate cannot be materialized "
            "before prediction_at."
        )

    source_created_times = (
        to_utc(
            dataset.created_at,
            field_name="dataset.created_at",
        ),
        to_utc(
            estimate.created_at,
            field_name="estimate.created_at",
        ),
        to_utc(
            support.created_at,
            field_name="support.created_at",
        ),
        to_utc(
            association_evidence.created_at,
            field_name="association_evidence.created_at",
        ),
        to_utc(
            target_predictor.created_at,
            field_name="target_predictor.created_at",
        ),
    )

    if max(source_created_times) > cutoff:
        raise ValueError(
            "Prediction source was not materialized by "
            "the information cutoff."
        )

    if target_predictor.available_at > cutoff:
        raise ValueError(
            "Target predictor was unavailable at "
            "the information cutoff."
        )

    if (
        target_predictor.athlete_id
        != association_evidence.athlete_id
        or target_predictor.athlete_id
        != dataset.athlete_id
    ):
        raise ValueError(
            "Prediction target athlete does not match "
            "association evidence."
        )

    if (
        target_predictor.predictor_key
        != association_evidence.predictor_key
        or target_predictor.predictor_key
        != dataset.predictor_key
    ):
        raise ValueError(
            "Prediction target predictor context mismatch."
        )

    if (
        target_predictor.stimulus_modality_key
        != association_evidence
        .response_key.stimulus_modality_key
    ):
        raise ValueError(
            "Prediction target modality does not match "
            "response context."
        )

    historical_sources = tuple(
        estimate.source_pairs
    )

    if not historical_sources:
        raise ValueError(
            "Association-supported estimate must contain "
            "historical source pairs."
        )

    historical_sessions = {
        source.workout_session_id
        for source in historical_sources
    }

    if (
        target_predictor.workout_session_id
        in historical_sessions
    ):
        raise ValueError(
            "Prediction target session is already present "
            "in historical model sources."
        )

    x_values = tuple(
        _finite_numeric(
            source.predictor_value,
            field_name="source.predictor_value",
        )
        for source in historical_sources
    )

    y_values = tuple(
        _finite_numeric(
            source.response_value,
            field_name="source.response_value",
        )
        for source in historical_sources
    )

    predictor_min = min(x_values)
    predictor_max = max(x_values)
    predictor_median = float(
        median(x_values)
    )

    response_median = float(
        median(y_values)
    )

    rho = _finite_numeric(
        association_evidence.spearman_rho,
        field_name="association_evidence.spearman_rho",
    )

    if rho == 0.0:
        raise ValueError(
            "Association-supported source cannot carry "
            "zero Spearman direction."
        )

    target_value = _finite_numeric(
        target_predictor.predictor_value,
        field_name="target_predictor.predictor_value",
    )

    limitations = []

    if (
        target_value < predictor_min
        or target_value > predictor_max
    ):
        limitations.append(
            PersonalResponsePredictionLimitationCode
            .TARGET_PREDICTOR_OUTSIDE_HISTORICAL_RANGE
        )

    if target_value == predictor_median:
        limitations.append(
            PersonalResponsePredictionLimitationCode
            .TARGET_PREDICTOR_EQUALS_HISTORICAL_MEDIAN
        )

    if limitations:
        status = (
            PersonalResponsePredictionStatus.WITHHELD
        )

        direction = None
        prediction_available = False

    else:
        predictor_above = (
            target_value > predictor_median
        )

        response_above = (
            predictor_above
            if rho > 0.0
            else not predictor_above
        )

        direction = (
            PersonalResponsePredictionDirection
            .ABOVE_HISTORICAL_MEDIAN
            if response_above
            else PersonalResponsePredictionDirection
            .BELOW_HISTORICAL_MEDIAN
        )

        status = (
            PersonalResponsePredictionStatus
            .PREDICTION_AVAILABLE
        )

        prediction_available = True

    ordered_limitations = tuple(
        sorted(
            set(limitations),
            key=lambda item: item.value,
        )
    )

    provisional = PersonalResponsePredictionCandidate(
        candidate_id="PENDING",
        schema_version=(
            PERSONAL_RESPONSE_PREDICTION_SCHEMA_V01
        ),
        rules_version=(
            PERSONAL_RESPONSE_PREDICTION_RULES_V01
        ),

        model_id=(
            PERSONAL_RESPONSE_PREDICTION_MODEL_ID_V01
        ),
        model_version=(
            PERSONAL_RESPONSE_PREDICTION_MODEL_VERSION_V01
        ),

        athlete_id=target_predictor.athlete_id,
        workout_session_id=(
            target_predictor.workout_session_id
        ),

        source_dataset_id=dataset.dataset_id,
        source_dataset_content_hash=(
            dataset.content_hash
        ),

        source_estimate_id=estimate.estimate_id,
        source_estimate_content_hash=(
            estimate.content_hash
        ),

        source_support_assessment_id=(
            support.assessment_id
        ),
        source_support_assessment_content_hash=(
            support.content_hash
        ),

        source_association_evidence_id=(
            association_evidence.evidence_id
        ),
        source_association_evidence_content_hash=(
            association_evidence.content_hash
        ),

        target_predictor_observation_id=(
            target_predictor.observation_id
        ),
        target_predictor_observation_content_hash=(
            target_predictor.content_hash
        ),

        predictor_key=dataset.predictor_key,
        response_key=association_evidence.response_key,

        historical_pair_count=len(
            historical_sources
        ),

        historical_predictor_min=predictor_min,
        historical_predictor_median=(
            predictor_median
        ),
        historical_predictor_max=predictor_max,

        historical_response_median=response_median,

        source_spearman_rho=rho,

        target_predictor_value=target_value,

        predicted_response_direction=direction,

        status=status,
        limitation_codes=ordered_limitations,

        information_cutoff_at=cutoff,
        prediction_at=predicted_at,

        response_prediction_available=(
            prediction_available
        ),

        # A caller-supplied timestamp is not prospective proof.
        issuance_proof_established=False,

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

        created_at=materialized,
        content_hash="PENDING",
    )

    digest = _prediction_content_hash(
        provisional
    )

    return PersonalResponsePredictionCandidate(
        **{
            **provisional.__dict__,
            "candidate_id": (
                "pt-personal-response-prediction:"
                f"{digest}"
            ),
            "content_hash": digest,
        }
    )
