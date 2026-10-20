from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from math import isfinite
from statistics import median

from ..common.enums import KnowledgeStatus
from ..common.serialization import (
    CONTENT_HASH_ALGORITHM,
    compute_content_hash,
)
from ..common.time import to_utc
from ..response_evidence import TrainingResponseTiming
from .history import (
    TRAINING_DYNAMICS_HISTORY_SCHEMA_V01,
    TrainingDynamicsHistory,
    TrainingDynamicsHistoryCoverage,
)
from .models import ResponseIsolationStatus


TRAINING_DYNAMICS_DESCRIPTIVE_SUMMARY_SCHEMA_V01 = (
    "training-dynamics-descriptive-summary-v0.1"
)

TRAINING_DYNAMICS_DESCRIPTIVE_SUMMARY_HASH_EXCLUDE_FIELDS = frozenset(
    {
        "summary_id",
        "created_at",
        "content_hash",
    }
)


class DescriptiveSampleSupport(StrEnum):
    NO_SAMPLES = "no_samples"
    SINGLE_SAMPLE = "single_sample"
    MULTIPLE_SAMPLES = "multiple_samples"


@dataclass(frozen=True)
class DescriptiveNumericSummary:
    """Observed numeric values only; never a population/effect estimate."""

    sample_count: int
    sample_support: DescriptiveSampleSupport

    minimum: float | None
    median: float | None
    maximum: float | None

    # Variability is withheld for fewer than two observations.
    median_absolute_deviation: float | None


@dataclass(frozen=True)
class DescriptiveCategoryCount:
    category_key: str
    observed_count: int


@dataclass(frozen=True)
class TrainingDynamicsDescriptiveSummary:
    """Descriptive longitudinal features from one immutable P2 history.

    This contract does not estimate biological effect, adaptation, fatigue,
    readiness, performance, causality or prescription utility.
    """

    summary_id: str
    schema_version: str

    athlete_id: str

    source_history_id: str
    source_history_content_hash: str

    window_start_at: datetime
    as_of: datetime
    information_cutoff_at: datetime

    stimulus_coverage: TrainingDynamicsHistoryCoverage
    response_coverage: TrainingDynamicsHistoryCoverage

    observed_stimulus_count: int
    known_duration_stimulus_count: int

    observed_response_count: int
    stimuli_with_observed_response_count: int

    modality_stimulus_counts: tuple[
        DescriptiveCategoryCount,
        ...,
    ]

    response_timing_counts: tuple[
        DescriptiveCategoryCount,
        ...,
    ]

    response_isolation_counts: tuple[
        DescriptiveCategoryCount,
        ...,
    ]

    observed_stimulus_spacing_s: DescriptiveNumericSummary
    response_lag_from_reference_end_s: DescriptiveNumericSummary

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
                    TRAINING_DYNAMICS_DESCRIPTIVE_SUMMARY_HASH_EXCLUDE_FIELDS
                ),
            )
            == self.content_hash
        )


def _sample_support(
    count: int,
) -> DescriptiveSampleSupport:
    if count <= 0:
        return DescriptiveSampleSupport.NO_SAMPLES

    if count == 1:
        return DescriptiveSampleSupport.SINGLE_SAMPLE

    return DescriptiveSampleSupport.MULTIPLE_SAMPLES


def _numeric_summary(
    values,
) -> DescriptiveNumericSummary:
    normalized = tuple(
        float(value)
        for value in values
    )

    if any(
        not isfinite(value)
        for value in normalized
    ):
        raise ValueError(
            "Descriptive numeric values must be finite."
        )

    count = len(normalized)

    if count == 0:
        return DescriptiveNumericSummary(
            sample_count=0,
            sample_support=(
                DescriptiveSampleSupport.NO_SAMPLES
            ),
            minimum=None,
            median=None,
            maximum=None,
            median_absolute_deviation=None,
        )

    center = float(
        median(normalized)
    )

    variability = None

    if count >= 2:
        variability = float(
            median(
                abs(value - center)
                for value in normalized
            )
        )

    return DescriptiveNumericSummary(
        sample_count=count,
        sample_support=_sample_support(count),
        minimum=min(normalized),
        median=center,
        maximum=max(normalized),
        median_absolute_deviation=variability,
    )


def _category_counts(
    observed_values,
    *,
    declared_categories=(),
) -> tuple[DescriptiveCategoryCount, ...]:
    counts = Counter(
        str(value)
        for value in observed_values
    )

    categories = {
        str(value)
        for value in declared_categories
    }

    categories.update(
        counts.keys()
    )

    return tuple(
        DescriptiveCategoryCount(
            category_key=category,
            observed_count=counts.get(
                category,
                0,
            ),
        )
        for category in sorted(categories)
    )


def summarize_training_dynamics_history(
    history: TrainingDynamicsHistory,
    *,
    created_at: datetime,
) -> TrainingDynamicsDescriptiveSummary:
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
            "Descriptive summary cannot predate its source history."
        )

    entries = tuple(
        sorted(
            history.entries,
            key=lambda entry: (
                entry.stimulus.exposure_observed_at,
                entry.stimulus.stimulus_id,
            ),
        )
    )

    stimuli = tuple(
        entry.stimulus
        for entry in entries
    )

    responses = tuple(
        response
        for entry in entries
        for response in entry.responses
    )

    known_duration_count = sum(
        1
        for stimulus in stimuli
        if stimulus.duration_status
        == KnowledgeStatus.KNOWN
    )

    stimuli_with_response_count = sum(
        1
        for entry in entries
        if entry.responses
    )

    spacing_values = tuple(
        (
            current.exposure_observed_at
            - previous.exposure_observed_at
        ).total_seconds()
        for previous, current in zip(
            stimuli,
            stimuli[1:],
        )
    )

    if any(
        value < 0.0
        for value in spacing_values
    ):
        raise ValueError(
            "Observed stimulus ordering produced negative spacing."
        )

    response_lags = []

    for response in responses:
        if (
            response.lag_from_reference_end_status
            == KnowledgeStatus.KNOWN
        ):
            if response.lag_from_reference_end_s is None:
                raise ValueError(
                    "Known response lag requires a numeric value."
                )

            if response.lag_from_reference_end_s < 0:
                raise ValueError(
                    "Known response lag must be non-negative."
                )

            response_lags.append(
                response.lag_from_reference_end_s
            )

        elif (
            response.lag_from_reference_end_s
            is not None
        ):
            raise ValueError(
                "Non-KNOWN response lag must not contain "
                "a numeric value."
            )

    modality_counts = _category_counts(
        stimulus.modality_key
        for stimulus in stimuli
    )

    timing_counts = _category_counts(
        (
            response.response_timing.value
            for response in responses
        ),
        declared_categories=tuple(
            timing.value
            for timing in TrainingResponseTiming
        ),
    )

    isolation_counts = _category_counts(
        (
            response.isolation_status.value
            for response in responses
        ),
        declared_categories=tuple(
            status.value
            for status in ResponseIsolationStatus
        ),
    )

    provisional = TrainingDynamicsDescriptiveSummary(
        summary_id=(
            "pt-training-dynamics-descriptive-summary:"
            f"{history.content_hash}"
        ),
        schema_version=(
            TRAINING_DYNAMICS_DESCRIPTIVE_SUMMARY_SCHEMA_V01
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

        observed_stimulus_count=len(stimuli),
        known_duration_stimulus_count=(
            known_duration_count
        ),

        observed_response_count=len(responses),
        stimuli_with_observed_response_count=(
            stimuli_with_response_count
        ),

        modality_stimulus_counts=modality_counts,
        response_timing_counts=timing_counts,
        response_isolation_counts=isolation_counts,

        observed_stimulus_spacing_s=(
            _numeric_summary(
                spacing_values
            )
        ),
        response_lag_from_reference_end_s=(
            _numeric_summary(
                response_lags
            )
        ),

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
            TRAINING_DYNAMICS_DESCRIPTIVE_SUMMARY_HASH_EXCLUDE_FIELDS
        ),
    )

    return TrainingDynamicsDescriptiveSummary(
        **{
            **provisional.__dict__,
            "content_hash": digest,
        }
    )
