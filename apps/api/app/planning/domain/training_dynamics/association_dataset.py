from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
import math

from ..common.enums import KnowledgeStatus
from ..common.serialization import (
    CONTENT_HASH_ALGORITHM,
    compute_content_hash,
)
from ..common.time import to_utc
from .history import (
    TRAINING_DYNAMICS_HISTORY_SCHEMA_V01,
    TrainingDynamicsHistory,
    TrainingDynamicsHistoryCoverage,
)
from .models import (
    EffectEvidenceLevel,
    RealizedTrainingStimulus,
    StimulusFeature,
    ResponseIsolationStatus,
)
from .personal_reference import (
    PERSONAL_RESPONSE_REFERENCE_ASSESSMENT_SCHEMA_V01,
    PERSONAL_RESPONSE_REFERENCE_RULES_V01,
    PersonalResponseReferenceAssessment,
    PersonalResponseReferenceStatus,
)
from .response_metrics import (
    RESPONSE_METRIC_OBSERVATION_SCHEMA_V01,
    ResponseMetricObservation,
)
from .response_reference import (
    DESCRIPTIVE_RESPONSE_METRIC_REFERENCE_SCHEMA_V01,
    DescriptiveResponseMetricReference,
    ResponseMetricReferenceEligibility,
    ResponseMetricReferenceKey,
)


PERSONAL_ASSOCIATION_DATASET_SCHEMA_V01 = (
    "personal-association-dataset-v0.1"
)

PERSONAL_ASSOCIATION_DATASET_RULES_V01 = (
    "personal-association-dataset-rules-v0.1"
)

PERSONAL_ASSOCIATION_PAIR_SCHEMA_V01 = (
    "personal-association-pair-v0.1"
)

PERSONAL_ASSOCIATION_PAIR_HASH_EXCLUDE_FIELDS = frozenset(
    {
        "pair_id",
        "created_at",
        "content_hash",
    }
)

PERSONAL_ASSOCIATION_DATASET_HASH_EXCLUDE_FIELDS = frozenset(
    {
        "dataset_id",
        "created_at",
        "content_hash",
    }
)


AssociationScalar = str | int | float | bool


@dataclass(frozen=True)
class PersonalAssociationPredictorKey:
    """Exact realized-stimulus feature selected as predictor."""

    metric_key: str
    unit: str | None


class PersonalAssociationPairEligibility(StrEnum):
    ELIGIBLE_NUMERIC_PAIR = "eligible_numeric_pair"
    INELIGIBLE = "ineligible"


class PersonalAssociationPairExclusionReason(StrEnum):
    RESPONSE_NON_KNOWN = "response_non_known"
    RESPONSE_KNOWN_NON_NUMERIC = "response_known_non_numeric"

    PREDICTOR_MISSING = "predictor_missing"
    PREDICTOR_NON_KNOWN = "predictor_non_known"
    PREDICTOR_KNOWN_NON_NUMERIC = (
        "predictor_known_non_numeric"
    )
    PREDICTOR_UNIT_MISMATCH = "predictor_unit_mismatch"


@dataclass(frozen=True)
class PersonalAssociationExclusionCount:
    reason: PersonalAssociationPairExclusionReason
    observed_count: int


@dataclass(frozen=True)
class PersonalAssociationPair:
    """One auditable historical stimulus-feature/response pair.

    Pair eligibility only means that both selected values are known,
    finite and numeric in the requested exact context.

    It does not establish association, causality, effect, prediction
    or planning utility.
    """

    pair_id: str
    schema_version: str

    athlete_id: str
    workout_session_id: str

    stimulus_id: str
    stimulus_content_hash: str

    response_observation_id: str
    response_observation_content_hash: str

    response_evidence_id: str
    response_evidence_hash: str

    predictor_key: PersonalAssociationPredictorKey

    predictor_knowledge_status: KnowledgeStatus | None
    predictor_observed_unit: str | None
    predictor_value: AssociationScalar | None
    predictor_numeric_value: float | None

    response_key: ResponseMetricReferenceKey

    response_knowledge_status: KnowledgeStatus
    response_value: AssociationScalar | None
    response_numeric_value: float | None

    response_observed_at: datetime
    response_available_at: datetime

    lag_from_reference_end_status: KnowledgeStatus
    lag_from_reference_end_s: float | None

    isolation_status: ResponseIsolationStatus
    intervening_stimulus_ids: tuple[str, ...]

    eligibility: PersonalAssociationPairEligibility
    exclusion_reasons: tuple[
        PersonalAssociationPairExclusionReason,
        ...,
    ]

    association_supported: bool
    causal_attribution_established: bool
    effect_inference_authorized: bool
    prediction_authorized: bool
    planning_authorized: bool

    created_at: datetime

    content_hash_algorithm: str
    content_hash: str

    def verify_content_hash(self) -> bool:
        return (
            compute_content_hash(
                self,
                exclude_fields=(
                    PERSONAL_ASSOCIATION_PAIR_HASH_EXCLUDE_FIELDS
                ),
            )
            == self.content_hash
        )


@dataclass(frozen=True)
class PersonalAssociationDataset:
    """P2.2A1 exact-context paired historical dataset.

    This object organizes candidate paired observations for later
    association analysis. It deliberately does not compute or claim
    statistical association.

    Even a dataset with many eligible pairs remains DESCRIPTIVE here.
    """

    dataset_id: str
    schema_version: str
    rules_version: str

    athlete_id: str

    source_history_id: str
    source_history_content_hash: str

    source_response_reference_id: str
    source_response_reference_content_hash: str

    source_personal_reference_assessment_id: str
    source_personal_reference_assessment_content_hash: str

    predictor_key: PersonalAssociationPredictorKey
    response_key: ResponseMetricReferenceKey

    stimulus_coverage: TrainingDynamicsHistoryCoverage
    response_coverage: TrainingDynamicsHistoryCoverage

    observed_pair_count: int
    eligible_numeric_pair_count: int
    ineligible_pair_count: int

    exclusion_counts: tuple[
        PersonalAssociationExclusionCount,
        ...,
    ]

    pairs: tuple[
        PersonalAssociationPair,
        ...,
    ]

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
                    PERSONAL_ASSOCIATION_DATASET_HASH_EXCLUDE_FIELDS
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

    return value.strip()


def _numeric_value(
    value: AssociationScalar | None,
) -> float | None:
    if isinstance(value, bool):
        return None

    if not isinstance(value, (int, float)):
        return None

    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(
            "Numeric association value cannot be represented "
            "as a finite float."
        ) from None

    if not math.isfinite(numeric):
        raise ValueError(
            "Numeric association value must be finite."
        )

    return numeric


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
            "Association dataset cannot predate "
            "its descriptive response reference."
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


def _validate_personal_reference(
    *,
    reference: DescriptiveResponseMetricReference,
    assessment: PersonalResponseReferenceAssessment,
    materialized: datetime,
) -> None:
    if not assessment.verify_content_hash():
        raise ValueError(
            "Personal response reference assessment hash "
            "does not verify."
        )

    if (
        assessment.schema_version
        != PERSONAL_RESPONSE_REFERENCE_ASSESSMENT_SCHEMA_V01
    ):
        raise ValueError(
            "Unsupported personal response reference schema."
        )

    if (
        assessment.rules_version
        != PERSONAL_RESPONSE_REFERENCE_RULES_V01
    ):
        raise ValueError(
            "Unsupported personal response reference rules."
        )

    if assessment.created_at > materialized:
        raise ValueError(
            "Association dataset cannot predate "
            "its personal response reference assessment."
        )

    if (
        assessment.source_reference_id != reference.reference_id
        or assessment.source_reference_content_hash
        != reference.content_hash
    ):
        raise ValueError(
            "Personal response reference assessment does not belong "
            "to the descriptive response reference."
        )

    if (
        assessment.athlete_id != reference.athlete_id
        or assessment.key != reference.key
        or assessment.response_coverage
        != reference.response_coverage
    ):
        raise ValueError(
            "Personal response reference context does not match "
            "the descriptive response reference."
        )

    if (
        assessment.sample_support != reference.sample_support
        or assessment.observed_observation_count
        != reference.observed_observation_count
        or assessment.eligible_numeric_sample_count
        != reference.eligible_numeric_sample_count
        or assessment.excluded_non_known_count
        != reference.excluded_non_known_count
        or assessment.excluded_known_non_numeric_count
        != reference.excluded_known_non_numeric_count
    ):
        raise ValueError(
            "Personal response reference counts do not match "
            "the descriptive response reference."
        )

    expected_status = (
        PersonalResponseReferenceStatus
        .DESCRIPTIVE_REFERENCE_AVAILABLE
        if reference.eligible_numeric_sample_count > 0
        else PersonalResponseReferenceStatus.UNESTABLISHED
    )

    if assessment.status != expected_status:
        raise ValueError(
            "Personal response reference status does not match "
            "the descriptive source reference."
        )

    if (
        assessment.evidence_level_ceiling
        != EffectEvidenceLevel.DESCRIPTIVE
    ):
        raise ValueError(
            "Personal response reference authority "
            "exceeds DESCRIPTIVE."
        )

    if (
        assessment.stability_established is not False
        or assessment.representativeness_established is not False
        or assessment.validated_baseline_established is not False
        or assessment.comparison_interpretation_authorized is not False
        or assessment.association_inference_authorized is not False
        or assessment.effect_inference_authorized is not False
        or assessment.causal_attribution_established is not False
        or assessment.readiness_inference_authorized is not False
        or assessment.performance_prediction_authorized is not False
        or assessment.prescription_change_authorized is not False
        or assessment.planning_authorized is not False
    ):
        raise ValueError(
            "Personal response reference contains unsupported "
            "stronger authority."
        )


def _history_index(
    history: TrainingDynamicsHistory,
):
    by_stimulus = {}
    by_association = {}

    for entry in history.entries:
        stimulus = entry.stimulus

        if stimulus.stimulus_id in by_stimulus:
            raise ValueError(
                "Training-dynamics history contains duplicate "
                "stimulus identity."
            )

        by_stimulus[stimulus.stimulus_id] = stimulus

        for association in entry.responses:
            if association.association_id in by_association:
                raise ValueError(
                    "Training-dynamics history contains duplicate "
                    "response association identity."
                )

            by_association[association.association_id] = (
                stimulus,
                association,
            )

    return by_stimulus, by_association


def _validate_observation(
    *,
    history: TrainingDynamicsHistory,
    reference: DescriptiveResponseMetricReference,
    source_by_id,
    association_index,
    observation: ResponseMetricObservation,
    materialized: datetime,
) -> tuple[
    RealizedTrainingStimulus,
    StimulusFeature,
    ResponseMetricReferenceEligibility,
]:
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

    source = source_by_id.get(
        observation.observation_id
    )

    if source is None:
        raise ValueError(
            "Response metric observation is not part of "
            "the exact descriptive reference source set."
        )

    if (
        source.observation_content_hash
        != observation.content_hash
    ):
        raise ValueError(
            "Response metric observation hash does not match "
            "the descriptive reference source."
        )

    if (
        source.workout_session_id
        != observation.workout_session_id
        or source.response_evidence_id
        != observation.response_evidence_id
        or source.response_evidence_hash
        != observation.response_evidence_hash
        or source.response_observed_at
        != observation.response_observed_at
    ):
        raise ValueError(
            "Response metric observation identity context does not "
            "match the descriptive reference source."
        )

    if observation.athlete_id != history.athlete_id:
        raise ValueError(
            "Response metric observation belongs to another athlete."
        )

    if observation.created_at > materialized:
        raise ValueError(
            "Association dataset cannot predate "
            "a source response observation."
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
            "Response metric observation is unavailable "
            "at the history information cutoff."
        )

    if (
        observation.metric_key != reference.key.metric_key
        or observation.unit != reference.key.unit
        or observation.response_timing
        != reference.key.response_timing
        or observation.stimulus_modality_key
        != reference.key.stimulus_modality_key
    ):
        raise ValueError(
            "Response metric observation does not match "
            "the exact response reference key."
        )

    context = association_index.get(
        observation.association_id
    )

    if context is None:
        raise ValueError(
            "Response metric observation association is not "
            "present in source history."
        )

    stimulus, association = context

    if (
        observation.association_content_hash
        != association.content_hash
        or observation.workout_session_id
        != association.workout_session_id
        or observation.stimulus_id
        != stimulus.stimulus_id
        or observation.stimulus_content_hash
        != stimulus.content_hash
    ):
        raise ValueError(
            "Response metric observation stimulus/association "
            "context does not match source history."
        )

    if (
        observation.response_evidence_id
        != association.response_evidence_id
        or observation.response_evidence_hash
        != association.response_evidence_hash
        or observation.response_observed_at
        != association.response_observed_at
        or observation.response_available_at
        != association.response_available_at
        or observation.response_timing
        != association.response_timing
        or observation.session_link_basis
        != association.session_link_basis
        or observation.lag_from_reference_end_status
        != association.lag_from_reference_end_status
        or observation.lag_from_reference_end_s
        != association.lag_from_reference_end_s
        or observation.reference_end_basis
        != association.reference_end_basis
        or observation.isolation_status
        != association.isolation_status
        or observation.intervening_stimulus_ids
        != association.intervening_stimulus_ids
    ):
        raise ValueError(
            "Response metric observation response context "
            "does not match source history."
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

    return stimulus, source.eligibility


def _response_numeric(
    *,
    observation: ResponseMetricObservation,
    expected_eligibility: ResponseMetricReferenceEligibility,
) -> tuple[
    float | None,
    tuple[PersonalAssociationPairExclusionReason, ...],
]:
    reasons = []

    if observation.knowledge_status != KnowledgeStatus.KNOWN:
        if observation.value is not None:
            raise ValueError(
                "Non-KNOWN response observation must have value=None."
            )

        actual_eligibility = (
            ResponseMetricReferenceEligibility.NON_KNOWN
        )

        reasons.append(
            PersonalAssociationPairExclusionReason
            .RESPONSE_NON_KNOWN
        )

        numeric = None

    else:
        numeric = _numeric_value(
            observation.value
        )

        if numeric is None:
            actual_eligibility = (
                ResponseMetricReferenceEligibility
                .KNOWN_NON_NUMERIC
            )

            reasons.append(
                PersonalAssociationPairExclusionReason
                .RESPONSE_KNOWN_NON_NUMERIC
            )

        else:
            actual_eligibility = (
                ResponseMetricReferenceEligibility
                .ELIGIBLE_NUMERIC
            )

    if actual_eligibility != expected_eligibility:
        raise ValueError(
            "Response observation eligibility does not match "
            "the descriptive response reference."
        )

    return numeric, tuple(reasons)


def _predictor_context(
    *,
    stimulus: RealizedTrainingStimulus,
    predictor_key: PersonalAssociationPredictorKey,
) -> tuple[
    KnowledgeStatus | None,
    str | None,
    AssociationScalar | None,
    float | None,
    tuple[PersonalAssociationPairExclusionReason, ...],
]:
    feature = next(
        (
            item
            for item in stimulus.features
            if item.metric_key == predictor_key.metric_key
        ),
        None,
    )

    if feature is None and predictor_key.metric_key == "duration_s":
        # A measured duration is an exposure descriptor, not a physiological
        # load estimate. Reuse the explicit source status; never fill a gap.
        feature = StimulusFeature(metric_key="duration_s", knowledge_status=stimulus.duration_status,
            value=stimulus.duration_s, unit="s")

    if feature is None:
        return (
            None,
            None,
            None,
            None,
            (
                PersonalAssociationPairExclusionReason
                .PREDICTOR_MISSING,
            ),
        )

    reasons = []

    if feature.unit != predictor_key.unit:
        reasons.append(
            PersonalAssociationPairExclusionReason
            .PREDICTOR_UNIT_MISMATCH
        )

    status = KnowledgeStatus(
        feature.knowledge_status
    )

    if status != KnowledgeStatus.KNOWN:
        if feature.value is not None:
            raise ValueError(
                "Non-KNOWN stimulus feature must have value=None."
            )

        reasons.append(
            PersonalAssociationPairExclusionReason
            .PREDICTOR_NON_KNOWN
        )

        numeric = None

    else:
        numeric = _numeric_value(
            feature.value
        )

        if numeric is None:
            reasons.append(
                PersonalAssociationPairExclusionReason
                .PREDICTOR_KNOWN_NON_NUMERIC
            )

    if feature.unit != predictor_key.unit:
        numeric = None

    return (
        status,
        feature.unit,
        feature.value,
        numeric,
        tuple(
            sorted(
                set(reasons),
                key=lambda item: item.value,
            )
        ),
    )


def _build_pair(
    *,
    athlete_id: str,
    stimulus: RealizedTrainingStimulus,
    observation: ResponseMetricObservation,
    expected_response_eligibility: (
        ResponseMetricReferenceEligibility
    ),
    predictor_key: PersonalAssociationPredictorKey,
    response_key: ResponseMetricReferenceKey,
    created_at: datetime,
) -> PersonalAssociationPair:
    response_numeric, response_reasons = _response_numeric(
        observation=observation,
        expected_eligibility=expected_response_eligibility,
    )

    (
        predictor_status,
        predictor_unit,
        predictor_value,
        predictor_numeric,
        predictor_reasons,
    ) = _predictor_context(
        stimulus=stimulus,
        predictor_key=predictor_key,
    )

    exclusion_reasons = tuple(
        sorted(
            set(
                response_reasons
                + predictor_reasons
            ),
            key=lambda item: item.value,
        )
    )

    eligibility = (
        PersonalAssociationPairEligibility
        .ELIGIBLE_NUMERIC_PAIR
        if (
            not exclusion_reasons
            and response_numeric is not None
            and predictor_numeric is not None
        )
        else PersonalAssociationPairEligibility.INELIGIBLE
    )

    provisional = PersonalAssociationPair(
        pair_id="",
        schema_version=PERSONAL_ASSOCIATION_PAIR_SCHEMA_V01,

        athlete_id=athlete_id,
        workout_session_id=observation.workout_session_id,

        stimulus_id=stimulus.stimulus_id,
        stimulus_content_hash=stimulus.content_hash,

        response_observation_id=observation.observation_id,
        response_observation_content_hash=observation.content_hash,

        response_evidence_id=observation.response_evidence_id,
        response_evidence_hash=observation.response_evidence_hash,

        predictor_key=predictor_key,

        predictor_knowledge_status=predictor_status,
        predictor_observed_unit=predictor_unit,
        predictor_value=predictor_value,
        predictor_numeric_value=predictor_numeric,

        response_key=response_key,

        response_knowledge_status=observation.knowledge_status,
        response_value=observation.value,
        response_numeric_value=response_numeric,

        response_observed_at=observation.response_observed_at,
        response_available_at=observation.response_available_at,

        lag_from_reference_end_status=(
            observation.lag_from_reference_end_status
        ),
        lag_from_reference_end_s=(
            observation.lag_from_reference_end_s
        ),

        isolation_status=observation.isolation_status,
        intervening_stimulus_ids=(
            observation.intervening_stimulus_ids
        ),

        eligibility=eligibility,
        exclusion_reasons=exclusion_reasons,

        association_supported=False,
        causal_attribution_established=False,
        effect_inference_authorized=False,
        prediction_authorized=False,
        planning_authorized=False,

        created_at=created_at,

        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash="",
    )

    digest = compute_content_hash(
        provisional,
        exclude_fields=(
            PERSONAL_ASSOCIATION_PAIR_HASH_EXCLUDE_FIELDS
        ),
    )

    return PersonalAssociationPair(
        **{
            **provisional.__dict__,
            "pair_id": (
                "pt-personal-association-pair:"
                f"{digest}"
            ),
            "content_hash": digest,
        }
    )


def build_personal_association_dataset(
    *,
    history: TrainingDynamicsHistory,
    response_reference: DescriptiveResponseMetricReference,
    personal_reference: PersonalResponseReferenceAssessment,
    observations: tuple[
        ResponseMetricObservation,
        ...,
    ],
    predictor_key: PersonalAssociationPredictorKey,
    created_at: datetime,
) -> PersonalAssociationDataset:
    _validate_history(
        history
    )

    materialized = to_utc(
        created_at,
        field_name="created_at",
    )

    if materialized < history.created_at:
        raise ValueError(
            "Association dataset cannot predate its source history."
        )

    predictor_metric = _require_non_empty(
        predictor_key.metric_key,
        field_name="predictor_key.metric_key",
    )

    predictor_unit = predictor_key.unit

    if predictor_unit is not None:
        predictor_unit = _require_non_empty(
            predictor_unit,
            field_name="predictor_key.unit",
        )

    normalized_predictor_key = PersonalAssociationPredictorKey(
        metric_key=predictor_metric,
        unit=predictor_unit,
    )

    _validate_reference(
        history=history,
        reference=response_reference,
        materialized=materialized,
    )

    _validate_personal_reference(
        reference=response_reference,
        assessment=personal_reference,
        materialized=materialized,
    )

    _, association_index = _history_index(
        history
    )

    reference_sources = tuple(
        response_reference.source_observations
    )

    source_by_id = {
        source.observation_id: source
        for source in reference_sources
    }

    if len(source_by_id) != len(reference_sources):
        raise ValueError(
            "Descriptive response reference contains duplicate "
            "source observation identities."
        )

    ordered_observations = tuple(
        sorted(
            tuple(observations),
            key=lambda item: (
                item.response_observed_at,
                item.workout_session_id,
                item.observation_id,
            ),
        )
    )

    observation_ids = tuple(
        item.observation_id
        for item in ordered_observations
    )

    if len(set(observation_ids)) != len(observation_ids):
        raise ValueError(
            "Association dataset contains duplicate "
            "response observation identities."
        )

    expected_ids = tuple(
        sorted(
            source.observation_id
            for source in reference_sources
        )
    )

    actual_ids = tuple(
        sorted(
            observation_ids
        )
    )

    if actual_ids != expected_ids:
        raise ValueError(
            "Association dataset observations must exactly match "
            "the descriptive response reference source set."
        )

    pairs = []

    for observation in ordered_observations:
        stimulus, expected_eligibility = _validate_observation(
            history=history,
            reference=response_reference,
            source_by_id=source_by_id,
            association_index=association_index,
            observation=observation,
            materialized=materialized,
        )

        pairs.append(
            _build_pair(
                athlete_id=history.athlete_id,
                stimulus=stimulus,
                observation=observation,
                expected_response_eligibility=(
                    expected_eligibility
                ),
                predictor_key=normalized_predictor_key,
                response_key=response_reference.key,
                created_at=materialized,
            )
        )

    pairs_tuple = tuple(
        pairs
    )

    for pair in pairs_tuple:
        if not pair.verify_content_hash():
            raise ValueError(
                "Constructed association pair hash does not verify."
            )

    eligible_count = sum(
        1
        for pair in pairs_tuple
        if (
            pair.eligibility
            == PersonalAssociationPairEligibility
            .ELIGIBLE_NUMERIC_PAIR
        )
    )

    reason_counter = Counter(
        reason
        for pair in pairs_tuple
        for reason in pair.exclusion_reasons
    )

    exclusion_counts = tuple(
        PersonalAssociationExclusionCount(
            reason=reason,
            observed_count=reason_counter.get(
                reason,
                0,
            ),
        )
        for reason in sorted(
            PersonalAssociationPairExclusionReason,
            key=lambda item: item.value,
        )
    )

    provisional = PersonalAssociationDataset(
        dataset_id="",
        schema_version=PERSONAL_ASSOCIATION_DATASET_SCHEMA_V01,
        rules_version=PERSONAL_ASSOCIATION_DATASET_RULES_V01,

        athlete_id=history.athlete_id,

        source_history_id=history.history_id,
        source_history_content_hash=history.content_hash,

        source_response_reference_id=(
            response_reference.reference_id
        ),
        source_response_reference_content_hash=(
            response_reference.content_hash
        ),

        source_personal_reference_assessment_id=(
            personal_reference.assessment_id
        ),
        source_personal_reference_assessment_content_hash=(
            personal_reference.content_hash
        ),

        predictor_key=normalized_predictor_key,
        response_key=response_reference.key,

        stimulus_coverage=history.stimulus_coverage,
        response_coverage=history.response_coverage,

        observed_pair_count=len(
            pairs_tuple
        ),
        eligible_numeric_pair_count=eligible_count,
        ineligible_pair_count=(
            len(pairs_tuple) - eligible_count
        ),

        exclusion_counts=exclusion_counts,

        pairs=pairs_tuple,

        evidence_level_ceiling=EffectEvidenceLevel.DESCRIPTIVE,

        association_supported=False,
        prospective_validation_established=False,
        causal_attribution_established=False,
        effect_inference_authorized=False,
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
            PERSONAL_ASSOCIATION_DATASET_HASH_EXCLUDE_FIELDS
        ),
    )

    return PersonalAssociationDataset(
        **{
            **provisional.__dict__,
            "dataset_id": (
                "pt-personal-association-dataset:"
                f"{digest}"
            ),
            "content_hash": digest,
        }
    )
