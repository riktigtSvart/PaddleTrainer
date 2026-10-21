from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..domain.common.time import to_utc
from ..domain.evidence.models import EvidenceItem
from ..domain.training_dynamics import (
    DescriptiveResponseMetricReference,
    EffectEvidenceLevel,
    PersonalAssociationDataset,
    PersonalAssociationPredictorKey,
    PersonalResponseReferenceAssessment,
    ResponseMetricObservation,
    ResponseMetricReferenceSufficiencyAssessment,
    TrainingDynamicsDataSufficiencyAssessment,
    TrainingDynamicsDescriptiveSummary,
    TrainingDynamicsHistory,
    assess_response_metric_reference_sufficiency,
    assess_training_dynamics_data_sufficiency,
    build_descriptive_response_metric_references,
    build_personal_association_dataset,
    build_personal_response_reference_assessment,
    summarize_training_dynamics_history,
)
from .rejoin_training_response_metrics import (
    rejoin_response_metric_observations,
)


@dataclass(frozen=True)
class PersonalAssociationDatasetAssembly:
    """Cutoff-safe P2.2A2 application assembly.

    This is orchestration only. It does not estimate statistical
    association and cannot raise evidence beyond DESCRIPTIVE.
    """

    source_history_id: str
    source_history_content_hash: str

    response_observations: tuple[
        ResponseMetricObservation,
        ...,
    ]

    descriptive_summary: TrainingDynamicsDescriptiveSummary

    response_references: tuple[
        DescriptiveResponseMetricReference,
        ...,
    ]

    data_sufficiency: TrainingDynamicsDataSufficiencyAssessment

    reference_sufficiency: tuple[
        ResponseMetricReferenceSufficiencyAssessment,
        ...,
    ]

    personal_references: tuple[
        PersonalResponseReferenceAssessment,
        ...,
    ]

    predictor_keys: tuple[
        PersonalAssociationPredictorKey,
        ...,
    ]

    datasets: tuple[
        PersonalAssociationDataset,
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


def _normalize_predictor_keys(
    predictor_keys: tuple[
        PersonalAssociationPredictorKey,
        ...,
    ],
) -> tuple[
    PersonalAssociationPredictorKey,
    ...,
]:
    normalized = []

    for raw in tuple(predictor_keys):
        if not isinstance(
            raw,
            PersonalAssociationPredictorKey,
        ):
            raise ValueError(
                "predictor_keys must contain "
                "PersonalAssociationPredictorKey values."
            )

        metric_key = _require_non_empty(
            raw.metric_key,
            field_name="predictor_key.metric_key",
        )

        unit = raw.unit

        if unit is not None:
            unit = _require_non_empty(
                unit,
                field_name="predictor_key.unit",
            )

        normalized.append(
            PersonalAssociationPredictorKey(
                metric_key=metric_key,
                unit=unit,
            )
        )

    if not normalized:
        raise ValueError(
            "At least one explicit association predictor is required."
        )

    if len(set(normalized)) != len(normalized):
        raise ValueError(
            "Association predictor keys must be unique."
        )

    return tuple(
        sorted(
            normalized,
            key=lambda key: (
                key.metric_key,
                key.unit is not None,
                key.unit or "",
            ),
        )
    )


def _observation_index(
    observations: tuple[
        ResponseMetricObservation,
        ...,
    ],
) -> dict[str, ResponseMetricObservation]:
    result = {}

    for observation in observations:
        if observation.observation_id in result:
            raise ValueError(
                "Rejoined response observations contain "
                "duplicate identities."
            )

        result[
            observation.observation_id
        ] = observation

    return result


def assemble_personal_association_datasets(
    *,
    history: TrainingDynamicsHistory,
    response_evidence_items: tuple[
        EvidenceItem,
        ...,
    ],
    predictor_keys: tuple[
        PersonalAssociationPredictorKey,
        ...,
    ],
    created_at: datetime,
) -> PersonalAssociationDatasetAssembly:
    """Build the descriptive input chain for P2.2 analysis.

    The history is supplied by the existing cutoff-safe history layer.
    Response observations are reconstructed through the existing
    durable-evidence rejoin service rather than accepted from callers.

    Every materialized exact response context is retained. No context
    is discarded because it is unestablished or numerically unsupported.
    """

    materialized = to_utc(
        created_at,
        field_name="created_at",
    )

    normalized_predictors = _normalize_predictor_keys(
        predictor_keys
    )

    observations = rejoin_response_metric_observations(
        history=history,
        evidence_items=tuple(
            response_evidence_items
        ),
        created_at=materialized,
    )

    descriptive_summary = (
        summarize_training_dynamics_history(
            history,
            created_at=materialized,
        )
    )

    references = (
        build_descriptive_response_metric_references(
            history=history,
            observations=observations,
            created_at=materialized,
        )
    )

    data_sufficiency = (
        assess_training_dynamics_data_sufficiency(
            history=history,
            summary=descriptive_summary,
            references=references,
            created_at=materialized,
        )
    )

    reference_sufficiency = (
        assess_response_metric_reference_sufficiency(
            history=history,
            data_sufficiency=data_sufficiency,
            references=references,
            created_at=materialized,
        )
    )

    sufficiency_by_reference_id = {}

    for assessment in reference_sufficiency:
        reference_id = (
            assessment.source_reference_id
        )

        if reference_id in sufficiency_by_reference_id:
            raise ValueError(
                "Duplicate response-reference "
                "sufficiency mapping."
            )

        sufficiency_by_reference_id[
            reference_id
        ] = assessment

    if (
        len(sufficiency_by_reference_id)
        != len(references)
    ):
        raise ValueError(
            "Response-reference sufficiency set does not map "
            "one-to-one to descriptive references."
        )

    personal_references = []

    for reference in references:
        sufficiency = (
            sufficiency_by_reference_id.get(
                reference.reference_id
            )
        )

        if sufficiency is None:
            raise ValueError(
                "Missing response-reference "
                "sufficiency assessment."
            )

        personal_references.append(
            build_personal_response_reference_assessment(
                reference=reference,
                sufficiency=sufficiency,
                created_at=materialized,
            )
        )

    personal_references_tuple = tuple(
        personal_references
    )

    personal_by_reference_id = {}

    for personal in personal_references_tuple:
        reference_id = (
            personal.source_reference_id
        )

        if reference_id in personal_by_reference_id:
            raise ValueError(
                "Duplicate personal response "
                "reference mapping."
            )

        personal_by_reference_id[
            reference_id
        ] = personal

    observation_by_id = _observation_index(
        observations
    )

    datasets = []

    for reference in references:
        personal = personal_by_reference_id.get(
            reference.reference_id
        )

        if personal is None:
            raise ValueError(
                "Missing personal response "
                "reference assessment."
            )

        context_observations = []

        for source in reference.source_observations:
            observation = observation_by_id.get(
                source.observation_id
            )

            if observation is None:
                raise ValueError(
                    "Descriptive response reference source "
                    "observation is missing after durable rejoin."
                )

            if (
                observation.content_hash
                != source.observation_content_hash
            ):
                raise ValueError(
                    "Rejoined response observation hash does not "
                    "match descriptive reference source."
                )

            context_observations.append(
                observation
            )

        for predictor_key in normalized_predictors:
            datasets.append(
                build_personal_association_dataset(
                    history=history,
                    response_reference=reference,
                    personal_reference=personal,
                    observations=tuple(
                        context_observations
                    ),
                    predictor_key=predictor_key,
                    created_at=materialized,
                )
            )

    datasets_tuple = tuple(
        datasets
    )

    for dataset in datasets_tuple:
        if (
            dataset.evidence_level_ceiling
            != EffectEvidenceLevel.DESCRIPTIVE
        ):
            raise ValueError(
                "P2.2A2 dataset authority exceeds DESCRIPTIVE."
            )

        if (
            dataset.association_supported is not False
            or dataset.prospective_validation_established is not False
            or dataset.causal_attribution_established is not False
            or dataset.effect_inference_authorized is not False
            or dataset.readiness_inference_authorized is not False
            or dataset.performance_prediction_authorized is not False
            or dataset.prescription_change_authorized is not False
            or dataset.planning_authorized is not False
        ):
            raise ValueError(
                "P2.2A2 dataset contains unsupported "
                "stronger authority."
            )

    return PersonalAssociationDatasetAssembly(
        source_history_id=history.history_id,
        source_history_content_hash=(
            history.content_hash
        ),

        response_observations=observations,

        descriptive_summary=descriptive_summary,

        response_references=references,

        data_sufficiency=data_sufficiency,

        reference_sufficiency=reference_sufficiency,

        personal_references=(
            personal_references_tuple
        ),

        predictor_keys=normalized_predictors,

        datasets=datasets_tuple,

        evidence_level_ceiling=(
            EffectEvidenceLevel.DESCRIPTIVE
        ),

        association_supported=False,
        prospective_validation_established=False,
        causal_attribution_established=False,
        effect_inference_authorized=False,
        readiness_inference_authorized=False,
        performance_prediction_authorized=False,
        prescription_change_authorized=False,
        planning_authorized=False,

        created_at=materialized,
    )
