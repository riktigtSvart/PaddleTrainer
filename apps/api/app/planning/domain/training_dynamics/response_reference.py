from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
import math
from statistics import median

from ..common.enums import KnowledgeStatus
from ..common.serialization import (
    CONTENT_HASH_ALGORITHM,
    compute_content_hash,
)
from ..common.time import to_utc
from ..response_evidence import TrainingResponseTiming
from .descriptive import (
    DescriptiveCategoryCount,
    DescriptiveSampleSupport,
)
from .history import (
    TRAINING_DYNAMICS_HISTORY_SCHEMA_V01,
    TrainingDynamicsHistory,
    TrainingDynamicsHistoryCoverage,
)
from .models import (
    ResponseIsolationStatus,
)
from .response_metrics import (
    RESPONSE_METRIC_OBSERVATION_SCHEMA_V01,
    ResponseMetricObservation,
)


DESCRIPTIVE_RESPONSE_METRIC_REFERENCE_SCHEMA_V01 = (
    "descriptive-response-metric-reference-v0.1"
)

DESCRIPTIVE_RESPONSE_METRIC_REFERENCE_HASH_EXCLUDE_FIELDS = (
    frozenset(
        {
            "reference_id",
            "created_at",
            "content_hash",
        }
    )
)


class ResponseMetricReferenceEligibility(StrEnum):
    ELIGIBLE_NUMERIC = "eligible_numeric"
    NON_KNOWN = "non_known"
    KNOWN_NON_NUMERIC = "known_non_numeric"


@dataclass(frozen=True)
class ResponseMetricReferenceKey:
    """Context dimensions that must remain homogeneous."""

    metric_key: str
    unit: str | None
    response_timing: TrainingResponseTiming
    stimulus_modality_key: str


@dataclass(frozen=True)
class ResponseMetricReferenceSource:
    """Audit identity of one observation considered for the reference."""

    observation_id: str
    observation_content_hash: str

    workout_session_id: str

    response_evidence_id: str
    response_evidence_hash: str

    response_observed_at: datetime

    eligibility: ResponseMetricReferenceEligibility


@dataclass(frozen=True)
class DescriptiveResponseMetricReference:
    """Personal descriptive reference from observed response metrics.

    This is not a validated physiological baseline, latent effect estimate,
    predictor, readiness/fatigue diagnosis, or planning authority.
    """

    reference_id: str
    schema_version: str

    athlete_id: str

    source_history_id: str
    source_history_content_hash: str

    window_start_at: datetime
    as_of: datetime
    information_cutoff_at: datetime

    stimulus_coverage: TrainingDynamicsHistoryCoverage
    response_coverage: TrainingDynamicsHistoryCoverage

    key: ResponseMetricReferenceKey

    observed_observation_count: int
    eligible_numeric_sample_count: int
    excluded_non_known_count: int
    excluded_known_non_numeric_count: int

    sample_support: DescriptiveSampleSupport

    minimum: float | None
    median: float | None
    maximum: float | None
    median_absolute_deviation: float | None

    response_isolation_counts: tuple[
        DescriptiveCategoryCount,
        ...,
    ]

    source_observations: tuple[
        ResponseMetricReferenceSource,
        ...,
    ]

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
                    DESCRIPTIVE_RESPONSE_METRIC_REFERENCE_HASH_EXCLUDE_FIELDS
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


def _sample_support(
    count: int,
) -> DescriptiveSampleSupport:
    if count == 0:
        return DescriptiveSampleSupport.NO_SAMPLES

    if count == 1:
        return DescriptiveSampleSupport.SINGLE_SAMPLE

    return DescriptiveSampleSupport.MULTIPLE_SAMPLES


def _numeric_value(
    observation: ResponseMetricObservation,
) -> tuple[
    ResponseMetricReferenceEligibility,
    float | None,
]:
    if observation.knowledge_status != KnowledgeStatus.KNOWN:
        if observation.value is not None:
            raise ValueError(
                "Non-KNOWN response metric observation "
                "must not contain a value."
            )

        return (
            ResponseMetricReferenceEligibility.NON_KNOWN,
            None,
        )

    value = observation.value

    # bool is intentionally not treated as numeric, despite Python's
    # bool subclassing int.
    if isinstance(value, bool):
        return (
            ResponseMetricReferenceEligibility.KNOWN_NON_NUMERIC,
            None,
        )

    if not isinstance(value, (int, float)):
        return (
            ResponseMetricReferenceEligibility.KNOWN_NON_NUMERIC,
            None,
        )

    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(
            "Numeric response metric cannot be represented "
            "as a finite float."
        ) from None

    if not math.isfinite(numeric):
        raise ValueError(
            "Numeric response metric must be finite."
        )

    return (
        ResponseMetricReferenceEligibility.ELIGIBLE_NUMERIC,
        numeric,
    )


def _isolation_counts(
    observations: tuple[
        ResponseMetricObservation,
        ...,
    ],
) -> tuple[DescriptiveCategoryCount, ...]:
    counts = Counter(
        observation.isolation_status.value
        for observation in observations
    )

    return tuple(
        DescriptiveCategoryCount(
            category_key=status.value,
            observed_count=counts.get(
                status.value,
                0,
            ),
        )
        for status in sorted(
            ResponseIsolationStatus,
            key=lambda item: item.value,
        )
    )


def _association_index(
    history: TrainingDynamicsHistory,
):
    result = {}

    for entry in history.entries:
        stimulus = entry.stimulus

        for association in entry.responses:
            if association.association_id in result:
                raise ValueError(
                    "Training-dynamics history contains duplicate "
                    "response association identity."
                )

            result[association.association_id] = (
                stimulus,
                association,
            )

    return result


def _validate_observation_against_history(
    *,
    history: TrainingDynamicsHistory,
    association_index,
    observation: ResponseMetricObservation,
    materialized: datetime,
) -> None:
    if not observation.verify_content_hash():
        raise ValueError(
            "Response metric observation hash does not verify."
        )

    if (
        observation.schema_version
        != RESPONSE_METRIC_OBSERVATION_SCHEMA_V01
    ):
        raise ValueError(
            "Unsupported response metric observation schema."
        )

    if observation.athlete_id != history.athlete_id:
        raise ValueError(
            "Response metric observation belongs to another athlete."
        )

    if (
        observation.causal_attribution_established is not False
        or observation.effect_inference_authorized is not False
        or observation.readiness_inference_authorized is not False
        or observation.performance_prediction_authorized is not False
        or observation.prescription_change_authorized is not False
    ):
        raise ValueError(
            "Response metric observation contains unsupported "
            "stronger authority."
        )

    if observation.created_at > materialized:
        raise ValueError(
            "Descriptive reference cannot predate "
            "a source observation."
        )

    if observation.response_observed_at > history.as_of:
        raise ValueError(
            "Response metric observation is after history as_of."
        )

    if (
        observation.response_available_at
        > history.information_cutoff_at
    ):
        raise ValueError(
            "Response metric observation is unavailable at "
            "the history information cutoff."
        )

    context = association_index.get(
        observation.association_id
    )

    if context is None:
        raise ValueError(
            "Response metric observation association is not "
            "present in the source history."
        )

    stimulus, association = context

    if (
        observation.association_content_hash
        != association.content_hash
    ):
        raise ValueError(
            "Response metric observation association hash "
            "does not match source history."
        )

    if (
        observation.workout_session_id
        != association.workout_session_id
        or observation.stimulus_id
        != stimulus.stimulus_id
        or observation.stimulus_content_hash
        != stimulus.content_hash
        or observation.stimulus_modality_key
        != stimulus.modality_key
    ):
        raise ValueError(
            "Response metric observation stimulus context "
            "does not match source history."
        )

    if (
        observation.response_evidence_id
        != association.response_evidence_id
        or observation.response_evidence_hash
        != association.response_evidence_hash
    ):
        raise ValueError(
            "Response metric observation evidence identity "
            "does not match source history."
        )

    if (
        observation.response_timing
        != association.response_timing
        or observation.session_link_basis
        != association.session_link_basis
    ):
        raise ValueError(
            "Response metric observation response context "
            "does not match source history."
        )

    if (
        observation.response_observed_at
        != association.response_observed_at
        or observation.response_available_at
        != association.response_available_at
    ):
        raise ValueError(
            "Response metric observation timestamps "
            "do not match source history."
        )

    if (
        observation.lag_from_reference_end_status
        != association.lag_from_reference_end_status
        or observation.lag_from_reference_end_s
        != association.lag_from_reference_end_s
        or observation.reference_end_basis
        != association.reference_end_basis
    ):
        raise ValueError(
            "Response metric observation lag context "
            "does not match source history."
        )

    if (
        observation.isolation_status
        != association.isolation_status
        or observation.intervening_stimulus_ids
        != association.intervening_stimulus_ids
    ):
        raise ValueError(
            "Response metric observation isolation context "
            "does not match source history."
        )


def build_descriptive_response_metric_references(
    *,
    history: TrainingDynamicsHistory,
    observations: tuple[
        ResponseMetricObservation,
        ...,
    ],
    created_at: datetime,
) -> tuple[
    DescriptiveResponseMetricReference,
    ...,
]:
    if not history.verify_content_hash():
        raise ValueError(
            "Training-dynamics history hash does not verify."
        )

    if (
        history.schema_version
        != TRAINING_DYNAMICS_HISTORY_SCHEMA_V01
    ):
        raise ValueError(
            "Unsupported training-dynamics history schema."
        )

    if (
        history.causal_attribution_established is not False
        or history.effect_inference_authorized is not False
        or history.performance_prediction_authorized is not False
        or history.prescription_change_authorized is not False
    ):
        raise ValueError(
            "Training-dynamics history contains unsupported "
            "stronger authority."
        )

    materialized = to_utc(
        created_at,
        field_name="created_at",
    )

    if materialized < history.created_at:
        raise ValueError(
            "Descriptive response reference cannot predate "
            "its source history."
        )

    association_index = _association_index(
        history
    )

    seen_observation_ids: set[str] = set()

    grouped: dict[
        ResponseMetricReferenceKey,
        list[
            tuple[
                ResponseMetricObservation,
                ResponseMetricReferenceEligibility,
                float | None,
            ]
        ],
    ] = {}

    for observation in tuple(observations):
        if observation.observation_id in seen_observation_ids:
            raise ValueError(
                "Duplicate response metric observation identity."
            )

        seen_observation_ids.add(
            observation.observation_id
        )

        _validate_observation_against_history(
            history=history,
            association_index=association_index,
            observation=observation,
            materialized=materialized,
        )

        metric_key = _require_non_empty(
            observation.metric_key,
            field_name="metric_key",
        )

        modality = _require_non_empty(
            observation.stimulus_modality_key,
            field_name="stimulus_modality_key",
        )

        unit = observation.unit

        if unit is not None:
            _require_non_empty(
                unit,
                field_name="unit",
            )

        key = ResponseMetricReferenceKey(
            metric_key=metric_key,
            unit=unit,
            response_timing=observation.response_timing,
            stimulus_modality_key=modality,
        )

        eligibility, numeric = _numeric_value(
            observation
        )

        grouped.setdefault(
            key,
            [],
        ).append(
            (
                observation,
                eligibility,
                numeric,
            )
        )

    references = []

    ordered_keys = sorted(
        grouped,
        key=lambda key: (
            key.metric_key,
            key.unit is not None,
            key.unit or "",
            key.response_timing.value,
            key.stimulus_modality_key,
        ),
    )

    for key in ordered_keys:
        records = tuple(
            sorted(
                grouped[key],
                key=lambda record: (
                    record[0].response_observed_at,
                    record[0].workout_session_id,
                    record[0].observation_id,
                ),
            )
        )

        group_observations = tuple(
            record[0]
            for record in records
        )

        numeric_values = tuple(
            record[2]
            for record in records
            if (
                record[1]
                == ResponseMetricReferenceEligibility.ELIGIBLE_NUMERIC
                and record[2] is not None
            )
        )

        sample_count = len(
            numeric_values
        )

        if sample_count:
            center = float(
                median(
                    numeric_values
                )
            )

            minimum = min(
                numeric_values
            )
            maximum = max(
                numeric_values
            )

            mad = None

            if sample_count >= 2:
                mad = float(
                    median(
                        abs(value - center)
                        for value in numeric_values
                    )
                )
        else:
            center = None
            minimum = None
            maximum = None
            mad = None

        sources = tuple(
            ResponseMetricReferenceSource(
                observation_id=(
                    observation.observation_id
                ),
                observation_content_hash=(
                    observation.content_hash
                ),
                workout_session_id=(
                    observation.workout_session_id
                ),
                response_evidence_id=(
                    observation.response_evidence_id
                ),
                response_evidence_hash=(
                    observation.response_evidence_hash
                ),
                response_observed_at=(
                    observation.response_observed_at
                ),
                eligibility=eligibility,
            )
            for (
                observation,
                eligibility,
                _,
            ) in records
        )

        provisional = DescriptiveResponseMetricReference(
            reference_id="",
            schema_version=(
                DESCRIPTIVE_RESPONSE_METRIC_REFERENCE_SCHEMA_V01
            ),

            athlete_id=history.athlete_id,

            source_history_id=history.history_id,
            source_history_content_hash=history.content_hash,

            window_start_at=history.window_start_at,
            as_of=history.as_of,
            information_cutoff_at=(
                history.information_cutoff_at
            ),

            stimulus_coverage=history.stimulus_coverage,
            response_coverage=history.response_coverage,

            key=key,

            observed_observation_count=len(
                records
            ),
            eligible_numeric_sample_count=(
                sample_count
            ),
            excluded_non_known_count=sum(
                1
                for _, eligibility, _ in records
                if (
                    eligibility
                    == ResponseMetricReferenceEligibility.NON_KNOWN
                )
            ),
            excluded_known_non_numeric_count=sum(
                1
                for _, eligibility, _ in records
                if (
                    eligibility
                    == ResponseMetricReferenceEligibility.KNOWN_NON_NUMERIC
                )
            ),

            sample_support=_sample_support(
                sample_count
            ),

            minimum=minimum,
            median=center,
            maximum=maximum,
            median_absolute_deviation=mad,

            response_isolation_counts=_isolation_counts(
                group_observations
            ),

            source_observations=sources,

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
                DESCRIPTIVE_RESPONSE_METRIC_REFERENCE_HASH_EXCLUDE_FIELDS
            ),
        )

        references.append(
            DescriptiveResponseMetricReference(
                **{
                    **provisional.__dict__,
                    "reference_id": (
                        "pt-descriptive-response-metric-reference:"
                        f"{digest}"
                    ),
                    "content_hash": digest,
                }
            )
        )

    return tuple(
        references
    )
