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
from .descriptive import (
    TRAINING_DYNAMICS_DESCRIPTIVE_SUMMARY_SCHEMA_V01,
    DescriptiveSampleSupport,
    TrainingDynamicsDescriptiveSummary,
    summarize_training_dynamics_history,
)
from .history import (
    TRAINING_DYNAMICS_HISTORY_SCHEMA_V01,
    TrainingDynamicsHistory,
    TrainingDynamicsHistoryCoverage,
)
from .models import EffectEvidenceLevel
from .response_reference import (
    DESCRIPTIVE_RESPONSE_METRIC_REFERENCE_SCHEMA_V01,
    DescriptiveResponseMetricReference,
    ResponseMetricReferenceEligibility,
)


TRAINING_DYNAMICS_DATA_SUFFICIENCY_SCHEMA_V01 = (
    "training-dynamics-data-sufficiency-v0.1"
)

TRAINING_DYNAMICS_DATA_SUFFICIENCY_RULES_V01 = (
    "training-dynamics-data-sufficiency-rules-v0.1"
)

TRAINING_DYNAMICS_DATA_SUFFICIENCY_HASH_EXCLUDE_FIELDS = (
    frozenset(
        {
            "assessment_id",
            "created_at",
            "content_hash",
        }
    )
)


class TrainingDynamicsDataSufficiencyStatus(StrEnum):
    UNKNOWN = "unknown"
    INSUFFICIENT = "insufficient"
    DESCRIPTIVE_SUPPORTED = "descriptive_supported"


class TrainingDynamicsDataSufficiencyComponentKind(StrEnum):
    STRUCTURAL_HISTORY = "structural_history"
    RESPONSE_OBSERVATION = "response_observation"
    RESPONSE_LAG = "response_lag"
    PERSONAL_METRIC_REFERENCE = "personal_metric_reference"


class TrainingDynamicsDataSufficiencyLimitationCode(StrEnum):
    STIMULUS_SOURCE_COVERAGE_UNKNOWN = (
        "stimulus_source_coverage_unknown"
    )
    STIMULUS_SOURCE_COVERAGE_PARTIAL = (
        "stimulus_source_coverage_partial"
    )

    RESPONSE_SOURCE_COVERAGE_UNKNOWN = (
        "response_source_coverage_unknown"
    )
    RESPONSE_SOURCE_COVERAGE_PARTIAL = (
        "response_source_coverage_partial"
    )

    NO_OBSERVED_STIMULI = "no_observed_stimuli"
    NO_OBSERVED_RESPONSES = "no_observed_responses"
    NO_KNOWN_RESPONSE_LAGS = "no_known_response_lags"

    NO_RESPONSE_METRIC_REFERENCES = (
        "no_response_metric_references"
    )
    NO_ELIGIBLE_NUMERIC_RESPONSE_SAMPLES = (
        "no_eligible_numeric_response_samples"
    )

    NON_KNOWN_RESPONSE_SAMPLES_PRESENT = (
        "non_known_response_samples_present"
    )
    KNOWN_NON_NUMERIC_RESPONSE_SAMPLES_PRESENT = (
        "known_non_numeric_response_samples_present"
    )

    CONTEXT_FRAGMENTATION_PRESENT = (
        "context_fragmentation_present"
    )


@dataclass(frozen=True)
class TrainingDynamicsDataSufficiencyComponent:
    kind: TrainingDynamicsDataSufficiencyComponentKind
    status: TrainingDynamicsDataSufficiencyStatus

    source_coverage: TrainingDynamicsHistoryCoverage

    observed_count: int
    usable_count: int

    limitation_codes: tuple[
        TrainingDynamicsDataSufficiencyLimitationCode,
        ...,
    ]


@dataclass(frozen=True)
class TrainingDynamicsDataSufficiencyAssessment:
    """Fail-closed P2.1 assessment of descriptive data support.

    The assessment describes what the available cutoff-safe dataset can
    support descriptively. It does not establish a biological baseline,
    association, causal effect, prediction, readiness/fatigue state or
    planning authority.
    """

    assessment_id: str
    schema_version: str
    rules_version: str

    athlete_id: str

    source_history_id: str
    source_history_content_hash: str

    source_summary_id: str
    source_summary_content_hash: str

    source_reference_ids: tuple[str, ...]
    source_reference_content_hashes: tuple[str, ...]

    window_start_at: datetime
    as_of: datetime
    information_cutoff_at: datetime

    stimulus_coverage: TrainingDynamicsHistoryCoverage
    response_coverage: TrainingDynamicsHistoryCoverage

    status: TrainingDynamicsDataSufficiencyStatus

    components: tuple[
        TrainingDynamicsDataSufficiencyComponent,
        ...,
    ]

    reference_context_count: int
    eligible_numeric_reference_context_count: int

    observed_reference_observation_count: int
    eligible_numeric_response_sample_count: int

    excluded_non_known_response_sample_count: int
    excluded_known_non_numeric_response_sample_count: int

    fragmented_metric_keys: tuple[str, ...]

    limitation_codes: tuple[
        TrainingDynamicsDataSufficiencyLimitationCode,
        ...,
    ]

    # Hard P2.1 ceiling. This is an upper authority boundary, not proof
    # that DESCRIPTIVE support is available for every component.
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
                    TRAINING_DYNAMICS_DATA_SUFFICIENCY_HASH_EXCLUDE_FIELDS
                ),
            )
            == self.content_hash
        )


def _ordered_limitations(
    *groups,
) -> tuple[
    TrainingDynamicsDataSufficiencyLimitationCode,
    ...,
]:
    values = {
        value
        for group in groups
        for value in tuple(group)
    }

    return tuple(
        sorted(
            values,
            key=lambda value: value.value,
        )
    )


def _coverage_limitations(
    coverage: TrainingDynamicsHistoryCoverage,
    *,
    partial_code: TrainingDynamicsDataSufficiencyLimitationCode,
    unknown_code: TrainingDynamicsDataSufficiencyLimitationCode,
) -> tuple[
    TrainingDynamicsDataSufficiencyLimitationCode,
    ...,
]:
    if coverage == TrainingDynamicsHistoryCoverage.PARTIAL:
        return (partial_code,)

    if coverage == TrainingDynamicsHistoryCoverage.UNKNOWN:
        return (unknown_code,)

    return ()


def _status_for_usable_data(
    *,
    usable_count: int,
    source_observation_count: int,
    coverage: TrainingDynamicsHistoryCoverage,
) -> TrainingDynamicsDataSufficiencyStatus:
    if usable_count > 0:
        return (
            TrainingDynamicsDataSufficiencyStatus
            .DESCRIPTIVE_SUPPORTED
        )

    # UNKNOWN is reserved for an absence that cannot safely be
    # interpreted because source coverage itself is unknown.
    if (
        source_observation_count == 0
        and coverage == TrainingDynamicsHistoryCoverage.UNKNOWN
    ):
        return TrainingDynamicsDataSufficiencyStatus.UNKNOWN

    return TrainingDynamicsDataSufficiencyStatus.INSUFFICIENT


def _component(
    *,
    kind: TrainingDynamicsDataSufficiencyComponentKind,
    status: TrainingDynamicsDataSufficiencyStatus,
    source_coverage: TrainingDynamicsHistoryCoverage,
    observed_count: int,
    usable_count: int,
    limitation_codes,
) -> TrainingDynamicsDataSufficiencyComponent:
    if observed_count < 0 or usable_count < 0:
        raise ValueError(
            "Data sufficiency counts must be non-negative."
        )

    if usable_count > observed_count:
        raise ValueError(
            "Data sufficiency usable_count cannot exceed "
            "observed_count."
        )

    return TrainingDynamicsDataSufficiencyComponent(
        kind=kind,
        status=status,
        source_coverage=source_coverage,
        observed_count=observed_count,
        usable_count=usable_count,
        limitation_codes=_ordered_limitations(
            limitation_codes
        ),
    )


def _validate_history(
    history: TrainingDynamicsHistory,
) -> None:
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


def _validate_summary(
    *,
    history: TrainingDynamicsHistory,
    summary: TrainingDynamicsDescriptiveSummary,
    materialized: datetime,
) -> None:
    if not summary.verify_content_hash():
        raise ValueError(
            "Training-dynamics descriptive summary hash "
            "does not verify."
        )

    if (
        summary.schema_version
        != TRAINING_DYNAMICS_DESCRIPTIVE_SUMMARY_SCHEMA_V01
    ):
        raise ValueError(
            "Unsupported training-dynamics descriptive "
            "summary schema."
        )

    if (
        summary.source_history_id != history.history_id
        or summary.source_history_content_hash
        != history.content_hash
    ):
        raise ValueError(
            "Descriptive summary does not belong to "
            "the source history."
        )

    if (
        summary.athlete_id != history.athlete_id
        or summary.window_start_at != history.window_start_at
        or summary.as_of != history.as_of
        or summary.information_cutoff_at
        != history.information_cutoff_at
        or summary.stimulus_coverage
        != history.stimulus_coverage
        or summary.response_coverage
        != history.response_coverage
    ):
        raise ValueError(
            "Descriptive summary replay context does not "
            "match source history."
        )

    if (
        summary.causal_attribution_established is not False
        or summary.effect_inference_authorized is not False
        or summary.readiness_inference_authorized is not False
        or summary.performance_prediction_authorized is not False
        or summary.prescription_change_authorized is not False
    ):
        raise ValueError(
            "Descriptive summary contains unsupported "
            "stronger authority."
        )

    if summary.created_at > materialized:
        raise ValueError(
            "Data sufficiency assessment cannot predate "
            "its descriptive summary."
        )

    # Rebuild from the exact immutable history. This prevents a
    # independently manufactured but self-consistent summary from
    # changing sufficiency counts.
    expected = summarize_training_dynamics_history(
        history,
        created_at=summary.created_at,
    )

    if expected.content_hash != summary.content_hash:
        raise ValueError(
            "Descriptive summary does not reproduce from "
            "the source history."
        )


def _reference_sample_support(
    count: int,
) -> DescriptiveSampleSupport:
    if count == 0:
        return DescriptiveSampleSupport.NO_SAMPLES

    if count == 1:
        return DescriptiveSampleSupport.SINGLE_SAMPLE

    return DescriptiveSampleSupport.MULTIPLE_SAMPLES


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

    if reference.created_at > materialized:
        raise ValueError(
            "Data sufficiency assessment cannot predate "
            "a descriptive response reference."
        )

    sources = tuple(
        reference.source_observations
    )

    if (
        len(sources)
        != reference.observed_observation_count
    ):
        raise ValueError(
            "Response reference observed count does not match "
            "its source observations."
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
            "match its source observations."
        )

    if (
        reference.sample_support
        != _reference_sample_support(
            reference.eligible_numeric_sample_count
        )
    ):
        raise ValueError(
            "Response reference sample support does not "
            "match eligible sample count."
        )

    history_entries = {
        entry.stimulus.workout_session_id: entry
        for entry in history.entries
    }

    for source in sources:
        entry = history_entries.get(
            source.workout_session_id
        )

        if entry is None:
            raise ValueError(
                "Response reference source session is not "
                "present in source history."
            )

        if (
            entry.stimulus.modality_key
            != reference.key.stimulus_modality_key
        ):
            raise ValueError(
                "Response reference modality does not match "
                "source history."
            )

        matching_associations = tuple(
            association
            for association in entry.responses
            if (
                association.response_evidence_id
                == source.response_evidence_id
                and association.response_evidence_hash
                == source.response_evidence_hash
                and association.response_observed_at
                == source.response_observed_at
            )
        )

        if len(matching_associations) != 1:
            raise ValueError(
                "Response reference source observation cannot "
                "be uniquely linked to source history."
            )

        association = matching_associations[0]

        if (
            association.response_timing
            != reference.key.response_timing
        ):
            raise ValueError(
                "Response reference timing does not match "
                "source history."
            )


def assess_training_dynamics_data_sufficiency(
    *,
    history: TrainingDynamicsHistory,
    summary: TrainingDynamicsDescriptiveSummary,
    references: tuple[
        DescriptiveResponseMetricReference,
        ...,
    ],
    created_at: datetime,
) -> TrainingDynamicsDataSufficiencyAssessment:
    _validate_history(
        history
    )

    materialized = to_utc(
        created_at,
        field_name="created_at",
    )

    if materialized < history.created_at:
        raise ValueError(
            "Data sufficiency assessment cannot predate "
            "its source history."
        )

    _validate_summary(
        history=history,
        summary=summary,
        materialized=materialized,
    )

    ordered_references = tuple(
        sorted(
            tuple(references),
            key=lambda reference: (
                reference.key.metric_key,
                reference.key.unit is not None,
                reference.key.unit or "",
                reference.key.response_timing.value,
                reference.key.stimulus_modality_key,
                reference.reference_id,
            ),
        )
    )

    seen_reference_ids: set[str] = set()
    seen_reference_keys = set()
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
                    "Duplicate response metric observation across "
                    "descriptive references."
                )

            seen_observation_ids.add(
                source.observation_id
            )

    stimulus_coverage_limits = _coverage_limitations(
        history.stimulus_coverage,
        partial_code=(
            TrainingDynamicsDataSufficiencyLimitationCode
            .STIMULUS_SOURCE_COVERAGE_PARTIAL
        ),
        unknown_code=(
            TrainingDynamicsDataSufficiencyLimitationCode
            .STIMULUS_SOURCE_COVERAGE_UNKNOWN
        ),
    )

    response_coverage_limits = _coverage_limitations(
        history.response_coverage,
        partial_code=(
            TrainingDynamicsDataSufficiencyLimitationCode
            .RESPONSE_SOURCE_COVERAGE_PARTIAL
        ),
        unknown_code=(
            TrainingDynamicsDataSufficiencyLimitationCode
            .RESPONSE_SOURCE_COVERAGE_UNKNOWN
        ),
    )

    stimulus_count = summary.observed_stimulus_count
    response_count = summary.observed_response_count

    known_lag_count = (
        summary.response_lag_from_reference_end_s.sample_count
    )

    observed_reference_observation_count = sum(
        reference.observed_observation_count
        for reference in ordered_references
    )

    eligible_numeric_sample_count = sum(
        reference.eligible_numeric_sample_count
        for reference in ordered_references
    )

    excluded_non_known_count = sum(
        reference.excluded_non_known_count
        for reference in ordered_references
    )

    excluded_known_non_numeric_count = sum(
        reference.excluded_known_non_numeric_count
        for reference in ordered_references
    )

    structural_limits = list(
        stimulus_coverage_limits
    )

    if stimulus_count == 0:
        structural_limits.append(
            TrainingDynamicsDataSufficiencyLimitationCode
            .NO_OBSERVED_STIMULI
        )

    structural_status = _status_for_usable_data(
        usable_count=stimulus_count,
        source_observation_count=stimulus_count,
        coverage=history.stimulus_coverage,
    )

    structural_component = _component(
        kind=(
            TrainingDynamicsDataSufficiencyComponentKind
            .STRUCTURAL_HISTORY
        ),
        status=structural_status,
        source_coverage=history.stimulus_coverage,
        observed_count=stimulus_count,
        usable_count=stimulus_count,
        limitation_codes=structural_limits,
    )

    response_limits = list(
        response_coverage_limits
    )

    if response_count == 0:
        response_limits.append(
            TrainingDynamicsDataSufficiencyLimitationCode
            .NO_OBSERVED_RESPONSES
        )

    response_status = _status_for_usable_data(
        usable_count=response_count,
        source_observation_count=response_count,
        coverage=history.response_coverage,
    )

    response_component = _component(
        kind=(
            TrainingDynamicsDataSufficiencyComponentKind
            .RESPONSE_OBSERVATION
        ),
        status=response_status,
        source_coverage=history.response_coverage,
        observed_count=response_count,
        usable_count=response_count,
        limitation_codes=response_limits,
    )

    lag_limits = list(
        response_coverage_limits
    )

    if known_lag_count == 0:
        lag_limits.append(
            TrainingDynamicsDataSufficiencyLimitationCode
            .NO_KNOWN_RESPONSE_LAGS
        )

    lag_status = _status_for_usable_data(
        usable_count=known_lag_count,
        source_observation_count=response_count,
        coverage=history.response_coverage,
    )

    lag_component = _component(
        kind=(
            TrainingDynamicsDataSufficiencyComponentKind
            .RESPONSE_LAG
        ),
        status=lag_status,
        source_coverage=history.response_coverage,
        observed_count=response_count,
        usable_count=known_lag_count,
        limitation_codes=lag_limits,
    )

    metric_limits = list(
        response_coverage_limits
    )

    if not ordered_references:
        metric_limits.append(
            TrainingDynamicsDataSufficiencyLimitationCode
            .NO_RESPONSE_METRIC_REFERENCES
        )

    if eligible_numeric_sample_count == 0:
        metric_limits.append(
            TrainingDynamicsDataSufficiencyLimitationCode
            .NO_ELIGIBLE_NUMERIC_RESPONSE_SAMPLES
        )

    if excluded_non_known_count > 0:
        metric_limits.append(
            TrainingDynamicsDataSufficiencyLimitationCode
            .NON_KNOWN_RESPONSE_SAMPLES_PRESENT
        )

    if excluded_known_non_numeric_count > 0:
        metric_limits.append(
            TrainingDynamicsDataSufficiencyLimitationCode
            .KNOWN_NON_NUMERIC_RESPONSE_SAMPLES_PRESENT
        )

    metric_context_counts = Counter(
        reference.key.metric_key
        for reference in ordered_references
    )

    fragmented_metric_keys = tuple(
        sorted(
            metric_key
            for metric_key, count in metric_context_counts.items()
            if count > 1
        )
    )

    if fragmented_metric_keys:
        metric_limits.append(
            TrainingDynamicsDataSufficiencyLimitationCode
            .CONTEXT_FRAGMENTATION_PRESENT
        )

    metric_status = _status_for_usable_data(
        usable_count=eligible_numeric_sample_count,
        source_observation_count=response_count,
        coverage=history.response_coverage,
    )

    metric_component = _component(
        kind=(
            TrainingDynamicsDataSufficiencyComponentKind
            .PERSONAL_METRIC_REFERENCE
        ),
        status=metric_status,
        source_coverage=history.response_coverage,
        observed_count=observed_reference_observation_count,
        usable_count=eligible_numeric_sample_count,
        limitation_codes=metric_limits,
    )

    components = (
        structural_component,
        response_component,
        lag_component,
        metric_component,
    )

    if any(
        component.status
        == TrainingDynamicsDataSufficiencyStatus.DESCRIPTIVE_SUPPORTED
        for component in components
    ):
        overall_status = (
            TrainingDynamicsDataSufficiencyStatus
            .DESCRIPTIVE_SUPPORTED
        )
    elif any(
        component.status
        == TrainingDynamicsDataSufficiencyStatus.UNKNOWN
        for component in components
    ):
        overall_status = (
            TrainingDynamicsDataSufficiencyStatus.UNKNOWN
        )
    else:
        overall_status = (
            TrainingDynamicsDataSufficiencyStatus.INSUFFICIENT
        )

    all_limitations = _ordered_limitations(
        *(
            component.limitation_codes
            for component in components
        )
    )

    eligible_reference_context_count = sum(
        1
        for reference in ordered_references
        if reference.eligible_numeric_sample_count > 0
    )

    provisional = TrainingDynamicsDataSufficiencyAssessment(
        assessment_id="",
        schema_version=(
            TRAINING_DYNAMICS_DATA_SUFFICIENCY_SCHEMA_V01
        ),
        rules_version=(
            TRAINING_DYNAMICS_DATA_SUFFICIENCY_RULES_V01
        ),

        athlete_id=history.athlete_id,

        source_history_id=history.history_id,
        source_history_content_hash=history.content_hash,

        source_summary_id=summary.summary_id,
        source_summary_content_hash=summary.content_hash,

        source_reference_ids=tuple(
            reference.reference_id
            for reference in ordered_references
        ),
        source_reference_content_hashes=tuple(
            reference.content_hash
            for reference in ordered_references
        ),

        window_start_at=history.window_start_at,
        as_of=history.as_of,
        information_cutoff_at=(
            history.information_cutoff_at
        ),

        stimulus_coverage=history.stimulus_coverage,
        response_coverage=history.response_coverage,

        status=overall_status,

        components=components,

        reference_context_count=len(
            ordered_references
        ),
        eligible_numeric_reference_context_count=(
            eligible_reference_context_count
        ),

        observed_reference_observation_count=(
            observed_reference_observation_count
        ),
        eligible_numeric_response_sample_count=(
            eligible_numeric_sample_count
        ),

        excluded_non_known_response_sample_count=(
            excluded_non_known_count
        ),
        excluded_known_non_numeric_response_sample_count=(
            excluded_known_non_numeric_count
        ),

        fragmented_metric_keys=fragmented_metric_keys,

        limitation_codes=all_limitations,

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
            TRAINING_DYNAMICS_DATA_SUFFICIENCY_HASH_EXCLUDE_FIELDS
        ),
    )

    return TrainingDynamicsDataSufficiencyAssessment(
        **{
            **provisional.__dict__,
            "assessment_id": (
                "pt-training-dynamics-data-sufficiency:"
                f"{digest}"
            ),
            "content_hash": digest,
        }
    )
