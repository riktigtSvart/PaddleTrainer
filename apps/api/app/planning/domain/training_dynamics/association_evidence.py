from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
import hashlib
import json

from ..common.time import to_utc
from .association_dataset import (
    PERSONAL_ASSOCIATION_DATASET_RULES_V01,
    PERSONAL_ASSOCIATION_DATASET_SCHEMA_V01,
    PersonalAssociationDataset,
    PersonalAssociationPredictorKey,
)
from .association_estimate import (
    PERSONAL_ASSOCIATION_ESTIMATE_RULES_V01,
    PERSONAL_ASSOCIATION_ESTIMATE_SCHEMA_V01,
    PersonalAssociationEstimate,
    build_personal_association_estimate,
)
from .association_support import (
    PERSONAL_ASSOCIATION_SUPPORT_RULES_V01,
    PERSONAL_ASSOCIATION_SUPPORT_SCHEMA_V01,
    PersonalAssociationSupportAssessment,
    PersonalAssociationSupportLimitationCode,
    PersonalAssociationSupportStatus,
    assess_personal_association_support,
)
from .models import EffectEvidenceLevel
from .response_reference import ResponseMetricReferenceKey


PERSONAL_ASSOCIATION_EVIDENCE_SCHEMA_V01 = (
    "personal-association-evidence-v0.1"
)

PERSONAL_ASSOCIATION_EVIDENCE_RULES_V01 = (
    "personal-association-evidence-rules-v0.1"
)


class PersonalAssociationEvidenceStatus(StrEnum):
    UNESTABLISHED = "UNESTABLISHED"
    ASSOCIATION_SUPPORTED = "ASSOCIATION_SUPPORTED"


@dataclass(frozen=True)
class PersonalAssociationEvidence:
    """P2.2D auditable personal association evidence artifact.

    This artifact may promote a successfully replayed P2.2C
    SUPPORT_CRITERIA_MET assessment to ASSOCIATION_SUPPORTED.

    Association support remains observational. It does not establish
    causality, prospective predictive validity, physiological effect,
    readiness/fatigue state, prescription change authority or planning
    authority.
    """

    evidence_id: str
    schema_version: str
    rules_version: str

    athlete_id: str

    source_dataset_id: str
    source_dataset_content_hash: str
    source_dataset_schema_version: str
    source_dataset_rules_version: str

    source_estimate_id: str
    source_estimate_content_hash: str
    source_estimate_schema_version: str
    source_estimate_rules_version: str

    source_support_assessment_id: str
    source_support_assessment_content_hash: str
    source_support_schema_version: str
    source_support_rules_version: str

    predictor_key: PersonalAssociationPredictorKey
    response_key: ResponseMetricReferenceKey

    observed_pair_count: int
    eligible_numeric_pair_count: int
    ineligible_pair_count: int

    spearman_rho: float | None
    pearson_r: float | None

    support_status: PersonalAssociationSupportStatus
    support_limitation_codes: tuple[
        PersonalAssociationSupportLimitationCode,
        ...,
    ]

    status: PersonalAssociationEvidenceStatus

    evidence_level: EffectEvidenceLevel
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
            == _evidence_content_hash(self)
        )


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


def _evidence_payload(
    evidence: PersonalAssociationEvidence,
) -> dict[str, object]:
    return {
        "schema_version": evidence.schema_version,
        "rules_version": evidence.rules_version,

        "athlete_id": evidence.athlete_id,

        "source_dataset_id": (
            evidence.source_dataset_id
        ),
        "source_dataset_content_hash": (
            evidence.source_dataset_content_hash
        ),
        "source_dataset_schema_version": (
            evidence.source_dataset_schema_version
        ),
        "source_dataset_rules_version": (
            evidence.source_dataset_rules_version
        ),

        "source_estimate_id": (
            evidence.source_estimate_id
        ),
        "source_estimate_content_hash": (
            evidence.source_estimate_content_hash
        ),
        "source_estimate_schema_version": (
            evidence.source_estimate_schema_version
        ),
        "source_estimate_rules_version": (
            evidence.source_estimate_rules_version
        ),

        "source_support_assessment_id": (
            evidence.source_support_assessment_id
        ),
        "source_support_assessment_content_hash": (
            evidence.source_support_assessment_content_hash
        ),
        "source_support_schema_version": (
            evidence.source_support_schema_version
        ),
        "source_support_rules_version": (
            evidence.source_support_rules_version
        ),

        "predictor_key": _predictor_key_payload(
            evidence.predictor_key
        ),
        "response_key": _response_key_payload(
            evidence.response_key
        ),

        "observed_pair_count": (
            evidence.observed_pair_count
        ),
        "eligible_numeric_pair_count": (
            evidence.eligible_numeric_pair_count
        ),
        "ineligible_pair_count": (
            evidence.ineligible_pair_count
        ),

        "spearman_rho": evidence.spearman_rho,
        "pearson_r": evidence.pearson_r,

        "support_status": (
            evidence.support_status.value
        ),
        "support_limitation_codes": [
            item.value
            for item
            in evidence.support_limitation_codes
        ],

        "status": evidence.status.value,

        "evidence_level": (
            evidence.evidence_level.value
        ),
        "association_supported": (
            evidence.association_supported
        ),

        "prospective_validation_established": (
            evidence.prospective_validation_established
        ),
        "causal_attribution_established": (
            evidence.causal_attribution_established
        ),
        "effect_inference_authorized": (
            evidence.effect_inference_authorized
        ),
        "readiness_inference_authorized": (
            evidence.readiness_inference_authorized
        ),
        "performance_prediction_authorized": (
            evidence.performance_prediction_authorized
        ),
        "prescription_change_authorized": (
            evidence.prescription_change_authorized
        ),
        "planning_authorized": (
            evidence.planning_authorized
        ),
    }


def _evidence_content_hash(
    evidence: PersonalAssociationEvidence,
) -> str:
    canonical = json.dumps(
        _evidence_payload(evidence),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )

    return hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()


def _validate_source_authority(
    *,
    dataset: PersonalAssociationDataset,
    estimate: PersonalAssociationEstimate,
    support: PersonalAssociationSupportAssessment,
) -> None:
    if (
        dataset.evidence_level_ceiling
        != EffectEvidenceLevel.DESCRIPTIVE
        or estimate.evidence_level_ceiling
        != EffectEvidenceLevel.DESCRIPTIVE
        or support.evidence_level_ceiling
        != EffectEvidenceLevel.DESCRIPTIVE
    ):
        raise ValueError(
            "P2.2D source authority must remain DESCRIPTIVE."
        )

    dataset_fields = (
        "association_supported",
        "prospective_validation_established",
        "causal_attribution_established",
        "effect_inference_authorized",
        "readiness_inference_authorized",
        "performance_prediction_authorized",
        "prescription_change_authorized",
        "planning_authorized",
    )

    estimate_fields = dataset_fields
    support_fields = dataset_fields

    for source_name, source, fields in (
        (
            "dataset",
            dataset,
            dataset_fields,
        ),
        (
            "estimate",
            estimate,
            estimate_fields,
        ),
        (
            "support",
            support,
            support_fields,
        ),
    ):
        for field_name in fields:
            if getattr(
                source,
                field_name,
            ) is not False:
                raise ValueError(
                    f"P2.2D source {source_name} contains "
                    "unsupported stronger authority: "
                    f"{field_name}."
                )


def _validate_contract_versions(
    *,
    dataset: PersonalAssociationDataset,
    estimate: PersonalAssociationEstimate,
    support: PersonalAssociationSupportAssessment,
) -> None:
    if (
        dataset.schema_version
        != PERSONAL_ASSOCIATION_DATASET_SCHEMA_V01
        or dataset.rules_version
        != PERSONAL_ASSOCIATION_DATASET_RULES_V01
    ):
        raise ValueError(
            "Unsupported personal association dataset contract."
        )

    if (
        estimate.schema_version
        != PERSONAL_ASSOCIATION_ESTIMATE_SCHEMA_V01
        or estimate.rules_version
        != PERSONAL_ASSOCIATION_ESTIMATE_RULES_V01
    ):
        raise ValueError(
            "Unsupported personal association estimate contract."
        )

    if (
        support.schema_version
        != PERSONAL_ASSOCIATION_SUPPORT_SCHEMA_V01
        or support.rules_version
        != PERSONAL_ASSOCIATION_SUPPORT_RULES_V01
    ):
        raise ValueError(
            "Unsupported personal association support contract."
        )


def build_personal_association_evidence(
    *,
    dataset: PersonalAssociationDataset,
    estimate: PersonalAssociationEstimate,
    support: PersonalAssociationSupportAssessment,
    created_at: datetime,
) -> PersonalAssociationEvidence:
    """Materialize P2.2D evidence after full A1/B/C replay."""

    if not dataset.verify_content_hash():
        raise ValueError(
            "Personal association dataset hash "
            "does not verify."
        )

    if not estimate.verify_content_hash():
        raise ValueError(
            "Personal association estimate hash "
            "does not verify."
        )

    if not support.verify_content_hash():
        raise ValueError(
            "Personal association support assessment hash "
            "does not verify."
        )

    _validate_contract_versions(
        dataset=dataset,
        estimate=estimate,
        support=support,
    )

    _validate_source_authority(
        dataset=dataset,
        estimate=estimate,
        support=support,
    )

    materialized = to_utc(
        created_at,
        field_name="created_at",
    )

    dataset_created = to_utc(
        dataset.created_at,
        field_name="dataset.created_at",
    )

    estimate_created = to_utc(
        estimate.created_at,
        field_name="estimate.created_at",
    )

    support_created = to_utc(
        support.created_at,
        field_name="support.created_at",
    )

    if (
        materialized < dataset_created
        or materialized < estimate_created
        or materialized < support_created
    ):
        raise ValueError(
            "P2.2D evidence cannot predate its sources."
        )

    if (
        estimate.source_dataset_id
        != dataset.dataset_id
        or estimate.source_dataset_content_hash
        != dataset.content_hash
    ):
        raise ValueError(
            "P2.2B estimate does not reference "
            "the supplied P2.2A1 dataset."
        )

    if (
        support.source_dataset_id
        != dataset.dataset_id
        or support.source_dataset_content_hash
        != dataset.content_hash
        or support.source_estimate_id
        != estimate.estimate_id
        or support.source_estimate_content_hash
        != estimate.content_hash
    ):
        raise ValueError(
            "P2.2C support assessment does not reference "
            "the supplied A1/B sources."
        )

    if (
        dataset.athlete_id
        != estimate.athlete_id
        or dataset.athlete_id
        != support.athlete_id
        or dataset.predictor_key
        != estimate.predictor_key
        or dataset.predictor_key
        != support.predictor_key
        or dataset.response_key
        != estimate.response_key
        or dataset.response_key
        != support.response_key
    ):
        raise ValueError(
            "P2.2D source context mismatch."
        )

    # Replay B from the immutable A1 source.
    replayed_estimate = (
        build_personal_association_estimate(
            dataset=dataset,
            created_at=estimate.created_at,
        )
    )

    if (
        replayed_estimate.content_hash
        != estimate.content_hash
        or replayed_estimate.estimate_id
        != estimate.estimate_id
    ):
        raise ValueError(
            "P2.2B estimate does not replay "
            "from the supplied P2.2A1 dataset."
        )

    # Replay C from the exact A1/B lineage.
    replayed_support = (
        assess_personal_association_support(
            dataset=dataset,
            estimate=estimate,
            created_at=support.created_at,
        )
    )

    if (
        replayed_support.content_hash
        != support.content_hash
        or replayed_support.assessment_id
        != support.assessment_id
    ):
        raise ValueError(
            "P2.2C support assessment does not replay "
            "from the supplied A1/B sources."
        )

    if (
        support.observed_pair_count
        != dataset.observed_pair_count
        or support.eligible_numeric_pair_count
        != dataset.eligible_numeric_pair_count
        or support.ineligible_pair_count
        != dataset.ineligible_pair_count
        or support.spearman_rho
        != estimate.spearman_rho
        or support.pearson_r
        != estimate.pearson_r
    ):
        raise ValueError(
            "P2.2C materialized values differ "
            "from their A1/B sources."
        )

    criteria_met = (
        support.status
        == PersonalAssociationSupportStatus
        .SUPPORT_CRITERIA_MET
    )

    if criteria_met:
        if support.limitation_codes:
            raise ValueError(
                "SUPPORT_CRITERIA_MET cannot carry "
                "support limitations."
            )

        status = (
            PersonalAssociationEvidenceStatus
            .ASSOCIATION_SUPPORTED
        )

        evidence_level = (
            EffectEvidenceLevel
            .ASSOCIATION_SUPPORTED
        )

        association_supported = True

    else:
        status = (
            PersonalAssociationEvidenceStatus
            .UNESTABLISHED
        )

        evidence_level = (
            EffectEvidenceLevel.DESCRIPTIVE
        )

        association_supported = False

    provisional = PersonalAssociationEvidence(
        evidence_id="PENDING",
        schema_version=(
            PERSONAL_ASSOCIATION_EVIDENCE_SCHEMA_V01
        ),
        rules_version=(
            PERSONAL_ASSOCIATION_EVIDENCE_RULES_V01
        ),

        athlete_id=dataset.athlete_id,

        source_dataset_id=dataset.dataset_id,
        source_dataset_content_hash=(
            dataset.content_hash
        ),
        source_dataset_schema_version=(
            dataset.schema_version
        ),
        source_dataset_rules_version=(
            dataset.rules_version
        ),

        source_estimate_id=estimate.estimate_id,
        source_estimate_content_hash=(
            estimate.content_hash
        ),
        source_estimate_schema_version=(
            estimate.schema_version
        ),
        source_estimate_rules_version=(
            estimate.rules_version
        ),

        source_support_assessment_id=(
            support.assessment_id
        ),
        source_support_assessment_content_hash=(
            support.content_hash
        ),
        source_support_schema_version=(
            support.schema_version
        ),
        source_support_rules_version=(
            support.rules_version
        ),

        predictor_key=dataset.predictor_key,
        response_key=dataset.response_key,

        observed_pair_count=(
            dataset.observed_pair_count
        ),
        eligible_numeric_pair_count=(
            dataset.eligible_numeric_pair_count
        ),
        ineligible_pair_count=(
            dataset.ineligible_pair_count
        ),

        spearman_rho=estimate.spearman_rho,
        pearson_r=estimate.pearson_r,

        support_status=support.status,
        support_limitation_codes=(
            support.limitation_codes
        ),

        status=status,

        evidence_level=evidence_level,
        association_supported=(
            association_supported
        ),

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

    digest = _evidence_content_hash(
        provisional
    )

    return PersonalAssociationEvidence(
        **{
            **provisional.__dict__,
            "evidence_id": (
                "pt-personal-association-evidence:"
                f"{digest}"
            ),
            "content_hash": digest,
        }
    )
