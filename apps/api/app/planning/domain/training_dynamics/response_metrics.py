from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..common.enums import KnowledgeStatus
from ..common.serialization import (
    CONTENT_HASH_ALGORITHM,
    compute_content_hash,
)
from ..common.time import to_utc
from ..response_evidence import (
    TrainingResponseLinkBasis,
    TrainingResponseMeasurement,
    TrainingResponseTiming,
)
from .models import (
    ExposureReferenceEndBasis,
    ObservedResponseAssociation,
    RealizedTrainingStimulus,
    ResponseIsolationStatus,
)


RESPONSE_METRIC_OBSERVATION_SCHEMA_V01 = (
    "response-metric-observation-v0.1"
)

RESPONSE_METRIC_OBSERVATION_HASH_EXCLUDE_FIELDS = frozenset(
    {
        "observation_id",
        "created_at",
        "content_hash",
    }
)


ResponseMetricScalar = str | int | float | bool


@dataclass(frozen=True)
class ResponseMetricObservation:
    """One response measurement rejoined to its historical context.

    This is descriptive evidence organization only. The observation does
    not establish causality, fatigue/readiness state, performance effect,
    prediction, baseline eligibility or prescription authority.
    """

    observation_id: str
    schema_version: str

    athlete_id: str
    workout_session_id: str

    stimulus_id: str
    stimulus_content_hash: str
    stimulus_modality_key: str

    association_id: str
    association_content_hash: str

    response_evidence_id: str
    response_evidence_hash: str

    response_timing: TrainingResponseTiming
    session_link_basis: TrainingResponseLinkBasis

    response_observed_at: datetime
    response_available_at: datetime

    lag_from_reference_end_status: KnowledgeStatus
    lag_from_reference_end_s: float | None
    reference_end_basis: ExposureReferenceEndBasis

    isolation_status: ResponseIsolationStatus
    intervening_stimulus_ids: tuple[str, ...]

    metric_key: str
    knowledge_status: KnowledgeStatus
    value: ResponseMetricScalar | None
    unit: str | None

    causal_attribution_established: bool
    effect_inference_authorized: bool
    readiness_inference_authorized: bool
    performance_prediction_authorized: bool
    prescription_change_authorized: bool

    created_at: datetime

    content_hash_algorithm: str
    content_hash: str

    def verify_content_hash(self) -> bool:
        return (
            compute_content_hash(
                self,
                exclude_fields=(
                    RESPONSE_METRIC_OBSERVATION_HASH_EXCLUDE_FIELDS
                ),
            )
            == self.content_hash
        )


def build_response_metric_observation(
    *,
    stimulus: RealizedTrainingStimulus,
    association: ObservedResponseAssociation,
    measurement: TrainingResponseMeasurement,
    created_at: datetime,
) -> ResponseMetricObservation:
    if not stimulus.verify_content_hash():
        raise ValueError(
            "Response-metric stimulus hash does not verify."
        )

    if not association.verify_content_hash():
        raise ValueError(
            "Response-metric association hash does not verify."
        )

    if (
        association.athlete_id != stimulus.athlete_id
        or association.workout_session_id
        != stimulus.workout_session_id
        or association.stimulus_id
        != stimulus.stimulus_id
        or association.stimulus_content_hash
        != stimulus.content_hash
    ):
        raise ValueError(
            "Response-metric association does not match its stimulus."
        )

    if (
        association.causal_attribution_established is not False
        or association.effect_inference_authorized is not False
        or association.planning_authorized is not False
    ):
        raise ValueError(
            "Response association contains unsupported "
            "stronger authority."
        )

    if not isinstance(
        measurement,
        TrainingResponseMeasurement,
    ):
        raise ValueError(
            "measurement must be TrainingResponseMeasurement."
        )

    materialized = to_utc(
        created_at,
        field_name="created_at",
    )

    association_created = to_utc(
        association.created_at,
        field_name="association.created_at",
    )

    if materialized < association_created:
        raise ValueError(
            "Response-metric observation cannot predate "
            "its association."
        )

    provisional = ResponseMetricObservation(
        observation_id=(
            "pt-response-metric-observation:"
            f"{association.content_hash}:"
            f"{measurement.metric_key}"
        ),
        schema_version=(
            RESPONSE_METRIC_OBSERVATION_SCHEMA_V01
        ),

        athlete_id=association.athlete_id,
        workout_session_id=(
            association.workout_session_id
        ),

        stimulus_id=stimulus.stimulus_id,
        stimulus_content_hash=stimulus.content_hash,
        stimulus_modality_key=stimulus.modality_key,

        association_id=association.association_id,
        association_content_hash=association.content_hash,

        response_evidence_id=(
            association.response_evidence_id
        ),
        response_evidence_hash=(
            association.response_evidence_hash
        ),

        response_timing=association.response_timing,
        session_link_basis=association.session_link_basis,

        response_observed_at=(
            association.response_observed_at
        ),
        response_available_at=(
            association.response_available_at
        ),

        lag_from_reference_end_status=(
            association.lag_from_reference_end_status
        ),
        lag_from_reference_end_s=(
            association.lag_from_reference_end_s
        ),
        reference_end_basis=(
            association.reference_end_basis
        ),

        isolation_status=association.isolation_status,
        intervening_stimulus_ids=(
            association.intervening_stimulus_ids
        ),

        metric_key=measurement.metric_key,
        knowledge_status=measurement.knowledge_status,
        value=measurement.value,
        unit=measurement.unit,

        causal_attribution_established=False,
        effect_inference_authorized=False,
        readiness_inference_authorized=False,
        performance_prediction_authorized=False,
        prescription_change_authorized=False,

        created_at=materialized,
        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash="",
    )

    digest = compute_content_hash(
        provisional,
        exclude_fields=(
            RESPONSE_METRIC_OBSERVATION_HASH_EXCLUDE_FIELDS
        ),
    )

    return ResponseMetricObservation(
        **{
            **provisional.__dict__,
            "content_hash": digest,
        }
    )
