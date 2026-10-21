from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ..common.serialization import (
    CONTENT_HASH_ALGORITHM,
    compute_content_hash,
)
from ..common.time import to_utc
from .models import EffectEvidenceLevel
from .prospective_cohort import (
    PROSPECTIVE_VALIDATION_COHORT_RULES_V01,
    PROSPECTIVE_VALIDATION_COHORT_SCHEMA_V01,
    ProspectiveValidationCohort,
    ProspectiveValidationFamilyKey,
)
from .prospective_multiplicity import (
    PROSPECTIVE_MULTIPLICITY_GUARD_RULES_V01,
    PROSPECTIVE_MULTIPLICITY_GUARD_SCHEMA_V01,
    ProspectiveValidationMultiplicityGuard,
)
from .prospective_validation import (
    PROSPECTIVE_VALIDATION_ASSESSMENT_RULES_V01,
    PROSPECTIVE_VALIDATION_ASSESSMENT_SCHEMA_V01,
    ProspectiveValidationAssessment,
    ProspectiveValidationAssessmentStatus,
    build_prospective_validation_assessment,
)


PROSPECTIVE_VALIDATION_EVIDENCE_SCHEMA_V01 = (
    "prospective-validation-evidence-v0.1"
)

PROSPECTIVE_VALIDATION_EVIDENCE_RULES_V01 = (
    "prospective-validation-evidence-rules-v0.1"
)

PROSPECTIVE_VALIDATION_EVIDENCE_HASH_EXCLUDE_FIELDS = (
    frozenset(
        {
            "evidence_id",
            "created_at",
            "content_hash",
        }
    )
)


class ProspectiveValidationEvidenceStatus(StrEnum):
    UNESTABLISHED = "UNESTABLISHED"
    PROSPECTIVELY_VALIDATED = "PROSPECTIVELY_VALIDATED"


@dataclass(frozen=True)
class ProspectiveValidationEvidence:
    """P2.3D auditable prospective validation evidence.

    Promotion means the bounded directional prediction family passed
    the pre-specified prospective validation assessment.

    It does NOT establish causality, physiological effect, readiness,
    generic performance-prediction authority, prescription authority,
    or planning authority.
    """

    evidence_id: str
    schema_version: str
    rules_version: str

    athlete_id: str
    family_key: ProspectiveValidationFamilyKey
    as_of: datetime

    source_cohort_id: str
    source_cohort_content_hash: str
    source_cohort_schema_version: str
    source_cohort_rules_version: str

    source_multiplicity_guard_id: str
    source_multiplicity_guard_content_hash: str
    source_multiplicity_guard_schema_version: str
    source_multiplicity_guard_rules_version: str

    source_assessment_id: str
    source_assessment_content_hash: str
    source_assessment_schema_version: str
    source_assessment_rules_version: str

    issued_challenge_count: int
    directionally_scored_count: int
    matched_count: int
    mismatched_count: int
    tied_unscorable_count: int

    exact_one_sided_p_numerator: int
    exact_one_sided_p_denominator: int

    adjusted_alpha_numerator: int | None
    adjusted_alpha_denominator: int | None

    assessment_status: ProspectiveValidationAssessmentStatus
    validation_criteria_met: bool

    status: ProspectiveValidationEvidenceStatus

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

    content_hash_algorithm: str
    content_hash: str

    def verify_content_hash(self) -> bool:
        return (
            compute_content_hash(
                self,
                exclude_fields=(
                    PROSPECTIVE_VALIDATION_EVIDENCE_HASH_EXCLUDE_FIELDS
                ),
            )
            == self.content_hash
        )


def _validate_source_contracts(
    *,
    cohort: ProspectiveValidationCohort,
    multiplicity_guard:
        ProspectiveValidationMultiplicityGuard,
    assessment: ProspectiveValidationAssessment,
) -> None:
    if (
        cohort.schema_version
        != PROSPECTIVE_VALIDATION_COHORT_SCHEMA_V01
        or cohort.rules_version
        != PROSPECTIVE_VALIDATION_COHORT_RULES_V01
    ):
        raise ValueError(
            "Unsupported P2.3C1 cohort contract."
        )

    if (
        multiplicity_guard.schema_version
        != PROSPECTIVE_MULTIPLICITY_GUARD_SCHEMA_V01
        or multiplicity_guard.rules_version
        != PROSPECTIVE_MULTIPLICITY_GUARD_RULES_V01
    ):
        raise ValueError(
            "Unsupported P2.3C2 multiplicity contract."
        )

    if (
        assessment.schema_version
        != PROSPECTIVE_VALIDATION_ASSESSMENT_SCHEMA_V01
        or assessment.rules_version
        != PROSPECTIVE_VALIDATION_ASSESSMENT_RULES_V01
    ):
        raise ValueError(
            "Unsupported P2.3C3 assessment contract."
        )


def _validate_source_identity(
    *,
    cohort: ProspectiveValidationCohort,
    multiplicity_guard:
        ProspectiveValidationMultiplicityGuard,
    assessment: ProspectiveValidationAssessment,
) -> None:
    if (
        cohort.cohort_id
        != "pt-prospective-validation-cohort:"
        + cohort.content_hash
    ):
        raise ValueError(
            "P2.3C1 cohort identity does not match its hash."
        )

    if (
        multiplicity_guard.guard_id
        != "pt-prospective-multiplicity-guard:"
        + multiplicity_guard.content_hash
    ):
        raise ValueError(
            "P2.3C2 multiplicity identity does not match "
            "its hash."
        )

    if (
        assessment.assessment_id
        != "pt-prospective-validation-assessment:"
        + assessment.content_hash
    ):
        raise ValueError(
            "P2.3C3 assessment identity does not match its hash."
        )


def _validate_source_authority(
    *,
    cohort: ProspectiveValidationCohort,
    multiplicity_guard:
        ProspectiveValidationMultiplicityGuard,
    assessment: ProspectiveValidationAssessment,
) -> None:
    for source_name, source in (
        ("cohort", cohort),
        ("multiplicity_guard", multiplicity_guard),
        ("assessment", assessment),
    ):
        if (
            source.evidence_level_ceiling
            != EffectEvidenceLevel.ASSOCIATION_SUPPORTED
            or source.association_supported is not True
        ):
            raise ValueError(
                f"P2.3D source {source_name} must remain "
                "ASSOCIATION_SUPPORTED."
            )

        if any(
            (
                source.prospective_validation_established,
                source.causal_attribution_established,
                source.effect_inference_authorized,
                source.readiness_inference_authorized,
                source.performance_prediction_authorized,
                source.prescription_change_authorized,
                source.planning_authorized,
            )
        ):
            raise ValueError(
                f"P2.3D source {source_name} contains "
                "unsupported stronger authority."
            )


def build_prospective_validation_evidence(
    *,
    cohort: ProspectiveValidationCohort,
    multiplicity_guard:
        ProspectiveValidationMultiplicityGuard,
    assessment: ProspectiveValidationAssessment,
    created_at: datetime,
) -> ProspectiveValidationEvidence:
    """Promote only a fully replayed successful P2.3C assessment."""

    if not cohort.verify_content_hash():
        raise ValueError(
            "P2.3C1 cohort hash does not verify."
        )

    if not multiplicity_guard.verify_content_hash():
        raise ValueError(
            "P2.3C2 multiplicity guard hash does not verify."
        )

    if not assessment.verify_content_hash():
        raise ValueError(
            "P2.3C3 assessment hash does not verify."
        )

    _validate_source_contracts(
        cohort=cohort,
        multiplicity_guard=multiplicity_guard,
        assessment=assessment,
    )

    _validate_source_identity(
        cohort=cohort,
        multiplicity_guard=multiplicity_guard,
        assessment=assessment,
    )

    _validate_source_authority(
        cohort=cohort,
        multiplicity_guard=multiplicity_guard,
        assessment=assessment,
    )

    if (
        cohort.athlete_id
        != multiplicity_guard.athlete_id
        or cohort.athlete_id
        != assessment.athlete_id
        or cohort.family_key
        != multiplicity_guard.target_family_key
        or cohort.family_key
        != assessment.family_key
        or cohort.as_of
        != multiplicity_guard.as_of
        or cohort.as_of
        != assessment.as_of
    ):
        raise ValueError(
            "P2.3D source context mismatch."
        )

    if (
        assessment.source_cohort_id
        != cohort.cohort_id
        or assessment.source_cohort_content_hash
        != cohort.content_hash
        or assessment.source_multiplicity_guard_id
        != multiplicity_guard.guard_id
        or assessment.source_multiplicity_guard_content_hash
        != multiplicity_guard.content_hash
    ):
        raise ValueError(
            "P2.3C3 assessment does not reference "
            "the supplied C1/C2 sources."
        )

    materialized = to_utc(
        created_at,
        field_name="created_at",
    )

    for source_name, source_created_at in (
        ("cohort", cohort.created_at),
        (
            "multiplicity_guard",
            multiplicity_guard.created_at,
        ),
        ("assessment", assessment.created_at),
    ):
        if materialized < to_utc(
            source_created_at,
            field_name=f"{source_name}.created_at",
        ):
            raise ValueError(
                "P2.3D evidence cannot predate its sources."
            )

    # Replay C3 exactly from C1 + C2.
    replayed = build_prospective_validation_assessment(
        cohort=cohort,
        multiplicity_guard=multiplicity_guard,
        created_at=assessment.created_at,
    )

    if replayed != assessment:
        raise ValueError(
            "P2.3C3 assessment does not replay exactly "
            "from the supplied C1/C2 sources."
        )

    criteria_met = (
        replayed.validation_criteria_met is True
        and replayed.status
        == ProspectiveValidationAssessmentStatus
        .VALIDATION_CRITERIA_MET
    )

    if criteria_met:
        status = (
            ProspectiveValidationEvidenceStatus
            .PROSPECTIVELY_VALIDATED
        )

        evidence_level = (
            EffectEvidenceLevel.PROSPECTIVELY_VALIDATED
        )

        prospective_validation_established = True

    else:
        status = (
            ProspectiveValidationEvidenceStatus
            .UNESTABLISHED
        )

        evidence_level = (
            EffectEvidenceLevel.ASSOCIATION_SUPPORTED
        )

        prospective_validation_established = False

    provisional = ProspectiveValidationEvidence(
        evidence_id="PENDING",
        schema_version=(
            PROSPECTIVE_VALIDATION_EVIDENCE_SCHEMA_V01
        ),
        rules_version=(
            PROSPECTIVE_VALIDATION_EVIDENCE_RULES_V01
        ),

        athlete_id=cohort.athlete_id,
        family_key=cohort.family_key,
        as_of=cohort.as_of,

        source_cohort_id=cohort.cohort_id,
        source_cohort_content_hash=cohort.content_hash,
        source_cohort_schema_version=(
            cohort.schema_version
        ),
        source_cohort_rules_version=(
            cohort.rules_version
        ),

        source_multiplicity_guard_id=(
            multiplicity_guard.guard_id
        ),
        source_multiplicity_guard_content_hash=(
            multiplicity_guard.content_hash
        ),
        source_multiplicity_guard_schema_version=(
            multiplicity_guard.schema_version
        ),
        source_multiplicity_guard_rules_version=(
            multiplicity_guard.rules_version
        ),

        source_assessment_id=(
            assessment.assessment_id
        ),
        source_assessment_content_hash=(
            assessment.content_hash
        ),
        source_assessment_schema_version=(
            assessment.schema_version
        ),
        source_assessment_rules_version=(
            assessment.rules_version
        ),

        issued_challenge_count=(
            assessment.issued_challenge_count
        ),
        directionally_scored_count=(
            assessment.directionally_scored_count
        ),
        matched_count=assessment.matched_count,
        mismatched_count=assessment.mismatched_count,
        tied_unscorable_count=(
            assessment.tied_unscorable_count
        ),

        exact_one_sided_p_numerator=(
            assessment.exact_one_sided_p_numerator
        ),
        exact_one_sided_p_denominator=(
            assessment.exact_one_sided_p_denominator
        ),

        adjusted_alpha_numerator=(
            assessment.adjusted_alpha_numerator
        ),
        adjusted_alpha_denominator=(
            assessment.adjusted_alpha_denominator
        ),

        assessment_status=assessment.status,
        validation_criteria_met=(
            assessment.validation_criteria_met
        ),

        status=status,

        evidence_level=evidence_level,
        association_supported=True,
        prospective_validation_established=(
            prospective_validation_established
        ),

        # Prospective predictive validation is not causal authority.
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
            PROSPECTIVE_VALIDATION_EVIDENCE_HASH_EXCLUDE_FIELDS
        ),
    )

    return ProspectiveValidationEvidence(
        **{
            **provisional.__dict__,
            "evidence_id": (
                "pt-prospective-validation-evidence:"
                f"{digest}"
            ),
            "content_hash": digest,
        }
    )
