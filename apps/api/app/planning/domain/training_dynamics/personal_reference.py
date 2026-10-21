from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ..common.serialization import (
    CONTENT_HASH_ALGORITHM,
    compute_content_hash,
)
from ..common.time import to_utc
from .descriptive import DescriptiveSampleSupport
from .history import TrainingDynamicsHistoryCoverage
from .models import EffectEvidenceLevel
from .reference_sufficiency import (
    RESPONSE_METRIC_REFERENCE_SUFFICIENCY_SCHEMA_V01,
    ResponseMetricReferenceContextDimension,
    ResponseMetricReferenceSufficiencyAssessment,
)
from .response_reference import (
    DESCRIPTIVE_RESPONSE_METRIC_REFERENCE_SCHEMA_V01,
    DescriptiveResponseMetricReference,
    ResponseMetricReferenceEligibility,
    ResponseMetricReferenceKey,
)
from .sufficiency import (
    TRAINING_DYNAMICS_DATA_SUFFICIENCY_RULES_V01,
    TrainingDynamicsDataSufficiencyLimitationCode,
    TrainingDynamicsDataSufficiencyStatus,
)


PERSONAL_RESPONSE_REFERENCE_ASSESSMENT_SCHEMA_V01 = (
    "personal-response-reference-assessment-v0.1"
)

PERSONAL_RESPONSE_REFERENCE_RULES_V01 = (
    "personal-response-reference-rules-v0.1"
)

PERSONAL_RESPONSE_REFERENCE_HASH_EXCLUDE_FIELDS = frozenset(
    {
        "assessment_id",
        "created_at",
        "content_hash",
    }
)


class PersonalResponseReferenceStatus(StrEnum):
    UNESTABLISHED = "unestablished"
    DESCRIPTIVE_REFERENCE_AVAILABLE = (
        "descriptive_reference_available"
    )


@dataclass(frozen=True)
class PersonalResponseReferenceAssessment:
    """P2.1E interpretation of one personal descriptive reference.

    DESCRIPTIVE_REFERENCE_AVAILABLE only means that an exact personal
    response context has at least one eligible numeric observation and
    descriptive support.

    It does not establish stability, representativeness, a validated
    physiological baseline, association, causal effect, readiness/fatigue
    state, prediction, comparison authority or planning authority.
    """

    assessment_id: str
    schema_version: str
    rules_version: str

    athlete_id: str

    source_reference_id: str
    source_reference_content_hash: str

    source_sufficiency_assessment_id: str
    source_sufficiency_content_hash: str

    key: ResponseMetricReferenceKey

    status: PersonalResponseReferenceStatus

    response_coverage: TrainingDynamicsHistoryCoverage

    sample_support: DescriptiveSampleSupport

    observed_observation_count: int
    eligible_numeric_sample_count: int

    excluded_non_known_count: int
    excluded_known_non_numeric_count: int

    reference_minimum: float | None
    reference_median: float | None
    reference_maximum: float | None
    reference_median_absolute_deviation: float | None

    first_eligible_observed_at: datetime | None
    last_eligible_observed_at: datetime | None
    eligible_observation_span_s: float | None

    metric_context_count: int

    fragmented_dimensions: tuple[
        ResponseMetricReferenceContextDimension,
        ...,
    ]

    limitation_codes: tuple[
        TrainingDynamicsDataSufficiencyLimitationCode,
        ...,
    ]

    evidence_level_ceiling: EffectEvidenceLevel

    stability_established: bool
    representativeness_established: bool
    validated_baseline_established: bool

    comparison_interpretation_authorized: bool
    association_inference_authorized: bool
    effect_inference_authorized: bool
    causal_attribution_established: bool
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
                    PERSONAL_RESPONSE_REFERENCE_HASH_EXCLUDE_FIELDS
                ),
            )
            == self.content_hash
        )


def _expected_sample_support(
    count: int,
) -> DescriptiveSampleSupport:
    if count == 0:
        return DescriptiveSampleSupport.NO_SAMPLES

    if count == 1:
        return DescriptiveSampleSupport.SINGLE_SAMPLE

    return DescriptiveSampleSupport.MULTIPLE_SAMPLES


def _validate_reference(
    *,
    reference: DescriptiveResponseMetricReference,
    materialized: datetime,
) -> None:
    if not reference.verify_content_hash():
        raise ValueError(
            "Descriptive response reference hash does not verify."
        )

    if (
        reference.schema_version
        != DESCRIPTIVE_RESPONSE_METRIC_REFERENCE_SCHEMA_V01
    ):
        raise ValueError(
            "Unsupported descriptive response reference schema."
        )

    if reference.created_at > materialized:
        raise ValueError(
            "Personal response reference assessment cannot predate "
            "its descriptive reference."
        )

    if (
        reference.causal_attribution_established is not False
        or reference.effect_inference_authorized is not False
        or reference.readiness_inference_authorized is not False
        or reference.performance_prediction_authorized is not False
        or reference.prescription_change_authorized is not False
    ):
        raise ValueError(
            "Descriptive response reference contains unsupported "
            "stronger authority."
        )

    sources = tuple(reference.source_observations)

    if len(sources) != reference.observed_observation_count:
        raise ValueError(
            "Response reference observed count does not match "
            "its source observations."
        )

    observation_ids = tuple(
        source.observation_id
        for source in sources
    )

    if len(set(observation_ids)) != len(observation_ids):
        raise ValueError(
            "Response reference contains duplicate source "
            "observation identities."
        )

    eligible_count = sum(
        1
        for source in sources
        if (
            source.eligibility
            == ResponseMetricReferenceEligibility.ELIGIBLE_NUMERIC
        )
    )

    non_known_count = sum(
        1
        for source in sources
        if (
            source.eligibility
            == ResponseMetricReferenceEligibility.NON_KNOWN
        )
    )

    non_numeric_count = sum(
        1
        for source in sources
        if (
            source.eligibility
            == ResponseMetricReferenceEligibility.KNOWN_NON_NUMERIC
        )
    )

    if (
        eligible_count != reference.eligible_numeric_sample_count
        or non_known_count != reference.excluded_non_known_count
        or non_numeric_count
        != reference.excluded_known_non_numeric_count
    ):
        raise ValueError(
            "Response reference eligibility counts do not "
            "match source observations."
        )

    if (
        reference.sample_support
        != _expected_sample_support(
            reference.eligible_numeric_sample_count
        )
    ):
        raise ValueError(
            "Response reference sample support does not match "
            "eligible numeric sample count."
        )

    if reference.eligible_numeric_sample_count == 0:
        if any(
            value is not None
            for value in (
                reference.minimum,
                reference.median,
                reference.maximum,
                reference.median_absolute_deviation,
            )
        ):
            raise ValueError(
                "Reference without eligible numeric samples "
                "cannot contain numeric aggregates."
            )

    else:
        if (
            reference.minimum is None
            or reference.median is None
            or reference.maximum is None
        ):
            raise ValueError(
                "Reference with eligible numeric samples "
                "requires minimum, median and maximum."
            )

        if (
            reference.eligible_numeric_sample_count == 1
            and reference.median_absolute_deviation is not None
        ):
            raise ValueError(
                "Single-sample reference must not claim "
                "observed variability."
            )


def _validate_sufficiency(
    *,
    reference: DescriptiveResponseMetricReference,
    sufficiency: ResponseMetricReferenceSufficiencyAssessment,
    materialized: datetime,
) -> None:
    if not sufficiency.verify_content_hash():
        raise ValueError(
            "Response reference sufficiency hash does not verify."
        )

    if (
        sufficiency.schema_version
        != RESPONSE_METRIC_REFERENCE_SUFFICIENCY_SCHEMA_V01
    ):
        raise ValueError(
            "Unsupported response reference sufficiency schema."
        )

    if (
        sufficiency.rules_version
        != TRAINING_DYNAMICS_DATA_SUFFICIENCY_RULES_V01
    ):
        raise ValueError(
            "Unsupported response reference sufficiency rules."
        )

    if sufficiency.created_at > materialized:
        raise ValueError(
            "Personal response reference assessment cannot predate "
            "its reference sufficiency assessment."
        )

    if (
        sufficiency.source_reference_id != reference.reference_id
        or sufficiency.source_reference_content_hash
        != reference.content_hash
    ):
        raise ValueError(
            "Reference sufficiency does not belong to "
            "the descriptive response reference."
        )

    if (
        sufficiency.athlete_id != reference.athlete_id
        or sufficiency.key != reference.key
        or sufficiency.response_coverage
        != reference.response_coverage
    ):
        raise ValueError(
            "Reference sufficiency context does not match "
            "the descriptive response reference."
        )

    if (
        sufficiency.sample_support != reference.sample_support
        or sufficiency.observed_observation_count
        != reference.observed_observation_count
        or sufficiency.eligible_numeric_sample_count
        != reference.eligible_numeric_sample_count
        or sufficiency.excluded_non_known_count
        != reference.excluded_non_known_count
        or sufficiency.excluded_known_non_numeric_count
        != reference.excluded_known_non_numeric_count
    ):
        raise ValueError(
            "Reference sufficiency counts do not match "
            "the descriptive response reference."
        )

    expected_status = (
        TrainingDynamicsDataSufficiencyStatus.DESCRIPTIVE_SUPPORTED
        if reference.eligible_numeric_sample_count > 0
        else TrainingDynamicsDataSufficiencyStatus.INSUFFICIENT
    )

    if sufficiency.status != expected_status:
        raise ValueError(
            "Reference sufficiency status does not match "
            "eligible numeric support."
        )

    if (
        sufficiency.evidence_level_ceiling
        != EffectEvidenceLevel.DESCRIPTIVE
    ):
        raise ValueError(
            "Reference sufficiency authority exceeds DESCRIPTIVE."
        )

    if (
        sufficiency.association_inference_authorized is not False
        or sufficiency.effect_inference_authorized is not False
        or sufficiency.causal_attribution_established is not False
        or sufficiency.readiness_inference_authorized is not False
        or sufficiency.performance_prediction_authorized is not False
        or sufficiency.prescription_change_authorized is not False
        or sufficiency.planning_authorized is not False
    ):
        raise ValueError(
            "Reference sufficiency contains unsupported "
            "stronger authority."
        )


def build_personal_response_reference_assessment(
    *,
    reference: DescriptiveResponseMetricReference,
    sufficiency: ResponseMetricReferenceSufficiencyAssessment,
    created_at: datetime,
) -> PersonalResponseReferenceAssessment:
    materialized = to_utc(
        created_at,
        field_name="created_at",
    )

    _validate_reference(
        reference=reference,
        materialized=materialized,
    )

    _validate_sufficiency(
        reference=reference,
        sufficiency=sufficiency,
        materialized=materialized,
    )

    eligible_times = tuple(
        sorted(
            source.response_observed_at
            for source in reference.source_observations
            if (
                source.eligibility
                == ResponseMetricReferenceEligibility.ELIGIBLE_NUMERIC
            )
        )
    )

    if eligible_times:
        first_eligible = eligible_times[0]
        last_eligible = eligible_times[-1]

        eligible_span_s = (
            last_eligible - first_eligible
        ).total_seconds()

        if eligible_span_s < 0:
            raise ValueError(
                "Eligible observation span cannot be negative."
            )

        status = (
            PersonalResponseReferenceStatus
            .DESCRIPTIVE_REFERENCE_AVAILABLE
        )
    else:
        first_eligible = None
        last_eligible = None
        eligible_span_s = None
        status = PersonalResponseReferenceStatus.UNESTABLISHED

    if (
        status
        == PersonalResponseReferenceStatus
        .DESCRIPTIVE_REFERENCE_AVAILABLE
        and sufficiency.status
        != TrainingDynamicsDataSufficiencyStatus.DESCRIPTIVE_SUPPORTED
    ):
        raise ValueError(
            "Descriptive personal reference requires "
            "DESCRIPTIVE_SUPPORTED sufficiency."
        )

    provisional = PersonalResponseReferenceAssessment(
        assessment_id="",
        schema_version=(
            PERSONAL_RESPONSE_REFERENCE_ASSESSMENT_SCHEMA_V01
        ),
        rules_version=PERSONAL_RESPONSE_REFERENCE_RULES_V01,

        athlete_id=reference.athlete_id,

        source_reference_id=reference.reference_id,
        source_reference_content_hash=reference.content_hash,

        source_sufficiency_assessment_id=(
            sufficiency.assessment_id
        ),
        source_sufficiency_content_hash=(
            sufficiency.content_hash
        ),

        key=reference.key,

        status=status,

        response_coverage=reference.response_coverage,

        sample_support=reference.sample_support,

        observed_observation_count=(
            reference.observed_observation_count
        ),
        eligible_numeric_sample_count=(
            reference.eligible_numeric_sample_count
        ),

        excluded_non_known_count=(
            reference.excluded_non_known_count
        ),
        excluded_known_non_numeric_count=(
            reference.excluded_known_non_numeric_count
        ),

        reference_minimum=reference.minimum,
        reference_median=reference.median,
        reference_maximum=reference.maximum,
        reference_median_absolute_deviation=(
            reference.median_absolute_deviation
        ),

        first_eligible_observed_at=first_eligible,
        last_eligible_observed_at=last_eligible,
        eligible_observation_span_s=eligible_span_s,

        metric_context_count=sufficiency.metric_context_count,

        fragmented_dimensions=sufficiency.fragmented_dimensions,

        limitation_codes=sufficiency.limitation_codes,

        evidence_level_ceiling=EffectEvidenceLevel.DESCRIPTIVE,

        stability_established=False,
        representativeness_established=False,
        validated_baseline_established=False,

        comparison_interpretation_authorized=False,
        association_inference_authorized=False,
        effect_inference_authorized=False,
        causal_attribution_established=False,
        readiness_inference_authorized=False,
        performance_prediction_authorized=False,
        prescription_change_authorized=False,
        planning_authorized=False,

        created_at=materialized,

        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash="",
    )

    digest = compute_content_hash(
        provisional,
        exclude_fields=(
            PERSONAL_RESPONSE_REFERENCE_HASH_EXCLUDE_FIELDS
        ),
    )

    return PersonalResponseReferenceAssessment(
        **{
            **provisional.__dict__,
            "assessment_id": (
                "pt-personal-response-reference-assessment:"
                f"{digest}"
            ),
            "content_hash": digest,
        }
    )
