from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ..common.serialization import (
    CONTENT_HASH_ALGORITHM,
    compute_content_hash,
)
from ..common.time import to_utc
from .descriptive import DescriptiveSampleSupport
from .history import (
    TrainingDynamicsHistory,
    TrainingDynamicsHistoryCoverage,
)
from .models import EffectEvidenceLevel
from .response_reference import (
    DESCRIPTIVE_RESPONSE_METRIC_REFERENCE_SCHEMA_V01,
    DescriptiveResponseMetricReference,
    ResponseMetricReferenceEligibility,
    ResponseMetricReferenceKey,
)
from .sufficiency import (
    TRAINING_DYNAMICS_DATA_SUFFICIENCY_RULES_V01,
    TRAINING_DYNAMICS_DATA_SUFFICIENCY_SCHEMA_V01,
    TrainingDynamicsDataSufficiencyAssessment,
    TrainingDynamicsDataSufficiencyLimitationCode,
    TrainingDynamicsDataSufficiencyStatus,
)


RESPONSE_METRIC_REFERENCE_SUFFICIENCY_SCHEMA_V01 = (
    "response-metric-reference-sufficiency-v0.1"
)

RESPONSE_METRIC_REFERENCE_SUFFICIENCY_HASH_EXCLUDE_FIELDS = (
    frozenset(
        {
            "assessment_id",
            "created_at",
            "content_hash",
        }
    )
)


class ResponseMetricReferenceContextDimension(StrEnum):
    UNIT = "unit"
    RESPONSE_TIMING = "response_timing"
    STIMULUS_MODALITY = "stimulus_modality"


@dataclass(frozen=True)
class ResponseMetricReferenceSufficiencyAssessment:
    """Descriptive support assessment for one exact response context.

    One assessment corresponds to exactly one response-reference key:
    metric + unit + response timing + stimulus modality.

    It does not establish a physiological baseline, association,
    causal effect, prediction, readiness/fatigue state or planning
    authority.
    """

    assessment_id: str
    schema_version: str
    rules_version: str

    athlete_id: str

    source_history_id: str
    source_history_content_hash: str

    source_data_sufficiency_assessment_id: str
    source_data_sufficiency_content_hash: str

    source_reference_id: str
    source_reference_content_hash: str

    key: ResponseMetricReferenceKey

    response_coverage: TrainingDynamicsHistoryCoverage

    status: TrainingDynamicsDataSufficiencyStatus
    sample_support: DescriptiveSampleSupport

    observed_observation_count: int
    eligible_numeric_sample_count: int

    excluded_non_known_count: int
    excluded_known_non_numeric_count: int

    metric_context_count: int
    sibling_reference_ids: tuple[str, ...]
    sibling_reference_content_hashes: tuple[str, ...]

    fragmented_dimensions: tuple[
        ResponseMetricReferenceContextDimension,
        ...,
    ]

    limitation_codes: tuple[
        TrainingDynamicsDataSufficiencyLimitationCode,
        ...,
    ]

    evidence_level_ceiling: EffectEvidenceLevel

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
                    RESPONSE_METRIC_REFERENCE_SUFFICIENCY_HASH_EXCLUDE_FIELDS
                ),
            )
            == self.content_hash
        )


def _ordered_limitations(
    values,
) -> tuple[
    TrainingDynamicsDataSufficiencyLimitationCode,
    ...,
]:
    return tuple(
        sorted(
            set(values),
            key=lambda value: value.value,
        )
    )


def _expected_sample_support(
    count: int,
) -> DescriptiveSampleSupport:
    if count == 0:
        return DescriptiveSampleSupport.NO_SAMPLES

    if count == 1:
        return DescriptiveSampleSupport.SINGLE_SAMPLE

    return DescriptiveSampleSupport.MULTIPLE_SAMPLES


def _validate_history(
    history: TrainingDynamicsHistory,
) -> None:
    if not history.verify_content_hash():
        raise ValueError(
            "Training-dynamics history hash does not verify."
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


def _validate_d1_assessment(
    *,
    history: TrainingDynamicsHistory,
    assessment: TrainingDynamicsDataSufficiencyAssessment,
    materialized: datetime,
) -> None:
    if not assessment.verify_content_hash():
        raise ValueError(
            "Training-dynamics data sufficiency assessment hash "
            "does not verify."
        )

    if (
        assessment.schema_version
        != TRAINING_DYNAMICS_DATA_SUFFICIENCY_SCHEMA_V01
    ):
        raise ValueError(
            "Unsupported training-dynamics data sufficiency schema."
        )

    if (
        assessment.rules_version
        != TRAINING_DYNAMICS_DATA_SUFFICIENCY_RULES_V01
    ):
        raise ValueError(
            "Unsupported training-dynamics data sufficiency rules."
        )

    if (
        assessment.source_history_id != history.history_id
        or assessment.source_history_content_hash
        != history.content_hash
    ):
        raise ValueError(
            "Data sufficiency assessment does not belong "
            "to the source history."
        )

    if (
        assessment.athlete_id != history.athlete_id
        or assessment.window_start_at != history.window_start_at
        or assessment.as_of != history.as_of
        or assessment.information_cutoff_at
        != history.information_cutoff_at
        or assessment.stimulus_coverage
        != history.stimulus_coverage
        or assessment.response_coverage
        != history.response_coverage
    ):
        raise ValueError(
            "Data sufficiency assessment replay context "
            "does not match source history."
        )

    if assessment.created_at > materialized:
        raise ValueError(
            "Reference sufficiency assessment cannot predate "
            "its P2.1D1 assessment."
        )

    if (
        assessment.evidence_level_ceiling
        != EffectEvidenceLevel.DESCRIPTIVE
    ):
        raise ValueError(
            "P2.1D1 evidence authority exceeds DESCRIPTIVE."
        )

    if (
        assessment.association_inference_authorized is not False
        or assessment.effect_inference_authorized is not False
        or assessment.causal_attribution_established is not False
        or assessment.readiness_inference_authorized is not False
        or assessment.performance_prediction_authorized is not False
        or assessment.prescription_change_authorized is not False
        or assessment.planning_authorized is not False
    ):
        raise ValueError(
            "P2.1D1 assessment contains unsupported "
            "stronger authority."
        )


def _validate_reference(
    *,
    history: TrainingDynamicsHistory,
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

    if (
        reference.source_history_id != history.history_id
        or reference.source_history_content_hash
        != history.content_hash
    ):
        raise ValueError(
            "Descriptive response reference does not belong "
            "to the source history."
        )

    if (
        reference.athlete_id != history.athlete_id
        or reference.window_start_at != history.window_start_at
        or reference.as_of != history.as_of
        or reference.information_cutoff_at
        != history.information_cutoff_at
        or reference.stimulus_coverage
        != history.stimulus_coverage
        or reference.response_coverage
        != history.response_coverage
    ):
        raise ValueError(
            "Descriptive response reference replay context "
            "does not match source history."
        )

    if reference.created_at > materialized:
        raise ValueError(
            "Reference sufficiency assessment cannot predate "
            "its source response reference."
        )

    if (
        reference.causal_attribution_established is not False
        or reference.effect_inference_authorized is not False
        or reference.readiness_inference_authorized is not False
        or reference.performance_prediction_authorized is not False
        or reference.prescription_change_authorized is not False
    ):
        raise ValueError(
            "Descriptive response reference contains "
            "unsupported stronger authority."
        )

    sources = tuple(
        reference.source_observations
    )

    if not sources:
        raise ValueError(
            "Descriptive response reference must contain "
            "at least one source observation."
        )

    if (
        len(sources)
        != reference.observed_observation_count
    ):
        raise ValueError(
            "Response reference observed count does not match "
            "source observations."
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
        eligible_count
        != reference.eligible_numeric_sample_count
        or non_known_count
        != reference.excluded_non_known_count
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


def _reference_sort_key(
    reference: DescriptiveResponseMetricReference,
):
    return (
        reference.key.metric_key,
        reference.key.unit is not None,
        reference.key.unit or "",
        reference.key.response_timing.value,
        reference.key.stimulus_modality_key,
        reference.reference_id,
    )


def _fragmented_dimensions(
    *,
    reference: DescriptiveResponseMetricReference,
    metric_contexts: tuple[
        DescriptiveResponseMetricReference,
        ...,
    ],
) -> tuple[
    ResponseMetricReferenceContextDimension,
    ...,
]:
    dimensions = []

    if len(
        {
            item.key.unit
            for item in metric_contexts
        }
    ) > 1:
        dimensions.append(
            ResponseMetricReferenceContextDimension.UNIT
        )

    if len(
        {
            item.key.response_timing
            for item in metric_contexts
        }
    ) > 1:
        dimensions.append(
            ResponseMetricReferenceContextDimension.RESPONSE_TIMING
        )

    if len(
        {
            item.key.stimulus_modality_key
            for item in metric_contexts
        }
    ) > 1:
        dimensions.append(
            ResponseMetricReferenceContextDimension.STIMULUS_MODALITY
        )

    return tuple(
        sorted(
            dimensions,
            key=lambda value: value.value,
        )
    )


def _reference_status(
    reference: DescriptiveResponseMetricReference,
) -> TrainingDynamicsDataSufficiencyStatus:
    if reference.eligible_numeric_sample_count > 0:
        return (
            TrainingDynamicsDataSufficiencyStatus
            .DESCRIPTIVE_SUPPORTED
        )

    # A materialized C2b reference always has at least one observed
    # source observation. Therefore zero numeric eligibility is known
    # insufficiency, not UNKNOWN source absence.
    return TrainingDynamicsDataSufficiencyStatus.INSUFFICIENT


def assess_response_metric_reference_sufficiency(
    *,
    history: TrainingDynamicsHistory,
    data_sufficiency: TrainingDynamicsDataSufficiencyAssessment,
    references: tuple[
        DescriptiveResponseMetricReference,
        ...,
    ],
    created_at: datetime,
) -> tuple[
    ResponseMetricReferenceSufficiencyAssessment,
    ...,
]:
    _validate_history(
        history
    )

    materialized = to_utc(
        created_at,
        field_name="created_at",
    )

    if materialized < history.created_at:
        raise ValueError(
            "Reference sufficiency assessment cannot predate "
            "its source history."
        )

    _validate_d1_assessment(
        history=history,
        assessment=data_sufficiency,
        materialized=materialized,
    )

    ordered_references = tuple(
        sorted(
            tuple(references),
            key=_reference_sort_key,
        )
    )

    seen_reference_ids: set[str] = set()
    seen_reference_keys: set[ResponseMetricReferenceKey] = set()
    seen_observation_ids: set[str] = set()

    for reference in ordered_references:
        if reference.reference_id in seen_reference_ids:
            raise ValueError(
                "Duplicate descriptive response reference identity."
            )

        seen_reference_ids.add(
            reference.reference_id
        )

        if reference.key in seen_reference_keys:
            raise ValueError(
                "Duplicate descriptive response reference key."
            )

        seen_reference_keys.add(
            reference.key
        )

        _validate_reference(
            history=history,
            reference=reference,
            materialized=materialized,
        )

        for source in reference.source_observations:
            if source.observation_id in seen_observation_ids:
                raise ValueError(
                    "Response metric observation appears in "
                    "multiple descriptive references."
                )

            seen_observation_ids.add(
                source.observation_id
            )

    reference_ids = tuple(
        reference.reference_id
        for reference in ordered_references
    )

    reference_hashes = tuple(
        reference.content_hash
        for reference in ordered_references
    )

    if (
        reference_ids
        != data_sufficiency.source_reference_ids
        or reference_hashes
        != data_sufficiency.source_reference_content_hashes
    ):
        raise ValueError(
            "Reference set does not exactly match the P2.1D1 "
            "assessment source references."
        )

    if (
        len(ordered_references)
        != data_sufficiency.reference_context_count
    ):
        raise ValueError(
            "Reference context count does not match P2.1D1."
        )

    eligible_context_count = sum(
        1
        for reference in ordered_references
        if reference.eligible_numeric_sample_count > 0
    )

    observed_count = sum(
        reference.observed_observation_count
        for reference in ordered_references
    )

    eligible_sample_count = sum(
        reference.eligible_numeric_sample_count
        for reference in ordered_references
    )

    non_known_count = sum(
        reference.excluded_non_known_count
        for reference in ordered_references
    )

    non_numeric_count = sum(
        reference.excluded_known_non_numeric_count
        for reference in ordered_references
    )

    if (
        eligible_context_count
        != data_sufficiency.eligible_numeric_reference_context_count
        or observed_count
        != data_sufficiency.observed_reference_observation_count
        or eligible_sample_count
        != data_sufficiency.eligible_numeric_response_sample_count
        or non_known_count
        != data_sufficiency.excluded_non_known_response_sample_count
        or non_numeric_count
        != data_sufficiency.excluded_known_non_numeric_response_sample_count
    ):
        raise ValueError(
            "Reference aggregate counts do not match P2.1D1."
        )

    metric_counts = Counter(
        reference.key.metric_key
        for reference in ordered_references
    )

    expected_fragmented_metric_keys = tuple(
        sorted(
            metric_key
            for metric_key, count in metric_counts.items()
            if count > 1
        )
    )

    if (
        expected_fragmented_metric_keys
        != data_sufficiency.fragmented_metric_keys
    ):
        raise ValueError(
            "Reference fragmentation does not match P2.1D1."
        )

    result = []

    for reference in ordered_references:
        metric_contexts = tuple(
            item
            for item in ordered_references
            if item.key.metric_key == reference.key.metric_key
        )

        siblings = tuple(
            item
            for item in metric_contexts
            if item.reference_id != reference.reference_id
        )

        fragmented_dimensions = _fragmented_dimensions(
            reference=reference,
            metric_contexts=metric_contexts,
        )

        limitations = []

        if (
            history.response_coverage
            == TrainingDynamicsHistoryCoverage.PARTIAL
        ):
            limitations.append(
                TrainingDynamicsDataSufficiencyLimitationCode
                .RESPONSE_SOURCE_COVERAGE_PARTIAL
            )

        elif (
            history.response_coverage
            == TrainingDynamicsHistoryCoverage.UNKNOWN
        ):
            limitations.append(
                TrainingDynamicsDataSufficiencyLimitationCode
                .RESPONSE_SOURCE_COVERAGE_UNKNOWN
            )

        if reference.eligible_numeric_sample_count == 0:
            limitations.append(
                TrainingDynamicsDataSufficiencyLimitationCode
                .NO_ELIGIBLE_NUMERIC_RESPONSE_SAMPLES
            )

        if reference.excluded_non_known_count > 0:
            limitations.append(
                TrainingDynamicsDataSufficiencyLimitationCode
                .NON_KNOWN_RESPONSE_SAMPLES_PRESENT
            )

        if reference.excluded_known_non_numeric_count > 0:
            limitations.append(
                TrainingDynamicsDataSufficiencyLimitationCode
                .KNOWN_NON_NUMERIC_RESPONSE_SAMPLES_PRESENT
            )

        if siblings:
            limitations.append(
                TrainingDynamicsDataSufficiencyLimitationCode
                .CONTEXT_FRAGMENTATION_PRESENT
            )

        provisional = ResponseMetricReferenceSufficiencyAssessment(
            assessment_id="",
            schema_version=(
                RESPONSE_METRIC_REFERENCE_SUFFICIENCY_SCHEMA_V01
            ),
            rules_version=(
                TRAINING_DYNAMICS_DATA_SUFFICIENCY_RULES_V01
            ),

            athlete_id=history.athlete_id,

            source_history_id=history.history_id,
            source_history_content_hash=history.content_hash,

            source_data_sufficiency_assessment_id=(
                data_sufficiency.assessment_id
            ),
            source_data_sufficiency_content_hash=(
                data_sufficiency.content_hash
            ),

            source_reference_id=reference.reference_id,
            source_reference_content_hash=reference.content_hash,

            key=reference.key,

            response_coverage=history.response_coverage,

            status=_reference_status(
                reference
            ),
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

            metric_context_count=len(
                metric_contexts
            ),
            sibling_reference_ids=tuple(
                item.reference_id
                for item in siblings
            ),
            sibling_reference_content_hashes=tuple(
                item.content_hash
                for item in siblings
            ),

            fragmented_dimensions=fragmented_dimensions,

            limitation_codes=_ordered_limitations(
                limitations
            ),

            evidence_level_ceiling=EffectEvidenceLevel.DESCRIPTIVE,

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
                RESPONSE_METRIC_REFERENCE_SUFFICIENCY_HASH_EXCLUDE_FIELDS
            ),
        )

        result.append(
            ResponseMetricReferenceSufficiencyAssessment(
                **{
                    **provisional.__dict__,
                    "assessment_id": (
                        "pt-response-metric-reference-sufficiency:"
                        f"{digest}"
                    ),
                    "content_hash": digest,
                }
            )
        )

    return tuple(result)
