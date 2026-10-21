from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from fractions import Fraction
from math import comb

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


PROSPECTIVE_VALIDATION_ASSESSMENT_SCHEMA_V01 = (
    "prospective-validation-assessment-v0.1"
)

PROSPECTIVE_VALIDATION_ASSESSMENT_RULES_V01 = (
    "prospective-validation-assessment-rules-v0.1"
)

PROSPECTIVE_VALIDATION_ASSESSMENT_HASH_EXCLUDE_FIELDS = (
    frozenset(
        {
            "assessment_id",
            "created_at",
            "content_hash",
        }
    )
)


class ProspectiveValidationAssessmentStatus(StrEnum):
    INELIGIBLE = "ineligible"
    VALIDATION_UNESTABLISHED = (
        "validation_unestablished"
    )
    VALIDATION_CRITERIA_MET = (
        "validation_criteria_met"
    )


@dataclass(frozen=True)
class ProspectiveValidationAssessment:
    """Exact multi-challenge prospective directional assessment.

    This artifact may establish that validation criteria were met.
    It deliberately does NOT itself promote evidence to
    PROSPECTIVELY_VALIDATED. Promotion belongs to P2.3D.
    """

    assessment_id: str
    schema_version: str
    rules_version: str

    athlete_id: str
    family_key: ProspectiveValidationFamilyKey
    as_of: datetime

    source_cohort_id: str
    source_cohort_content_hash: str

    source_multiplicity_guard_id: str
    source_multiplicity_guard_content_hash: str

    issued_challenge_count: int
    bound_challenge_count: int

    directionally_scored_count: int
    matched_count: int
    mismatched_count: int
    tied_unscorable_count: int

    exact_issuance_universe_match: bool

    null_match_probability_numerator: int
    null_match_probability_denominator: int

    exact_one_sided_p_numerator: int
    exact_one_sided_p_denominator: int

    adjusted_alpha_numerator: int | None
    adjusted_alpha_denominator: int | None

    directional_success_above_chance: bool
    statistical_threshold_met: bool

    validation_criteria_met: bool
    status: ProspectiveValidationAssessmentStatus

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
                    PROSPECTIVE_VALIDATION_ASSESSMENT_HASH_EXCLUDE_FIELDS
                ),
            )
            == self.content_hash
        )


def _validate_source_authority(
    cohort: ProspectiveValidationCohort,
    guard: ProspectiveValidationMultiplicityGuard,
) -> None:
    if not cohort.verify_content_hash():
        raise ValueError(
            "Prospective cohort content hash does not verify."
        )

    if not guard.verify_content_hash():
        raise ValueError(
            "Prospective multiplicity guard content hash "
            "does not verify."
        )

    if (
        cohort.schema_version
        != PROSPECTIVE_VALIDATION_COHORT_SCHEMA_V01
        or cohort.rules_version
        != PROSPECTIVE_VALIDATION_COHORT_RULES_V01
    ):
        raise ValueError(
            "Unsupported prospective cohort contract."
        )

    if (
        guard.schema_version
        != PROSPECTIVE_MULTIPLICITY_GUARD_SCHEMA_V01
        or guard.rules_version
        != PROSPECTIVE_MULTIPLICITY_GUARD_RULES_V01
    ):
        raise ValueError(
            "Unsupported prospective multiplicity contract."
        )

    for source in (
        cohort,
        guard,
    ):
        if (
            source.evidence_level_ceiling
            != EffectEvidenceLevel.ASSOCIATION_SUPPORTED
            or source.association_supported is not True
        ):
            raise ValueError(
                "Prospective validation source lacks "
                "association-supported authority."
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
                "Prospective validation source claims "
                "unsupported stronger authority."
            )


def _exact_binomial_upper_tail(
    *,
    matches: int,
    trials: int,
) -> Fraction:
    if trials < 0:
        raise ValueError(
            "trials must be non-negative."
        )

    if matches < 0 or matches > trials:
        raise ValueError(
            "matches must be within trial count."
        )

    if trials == 0:
        return Fraction(1, 1)

    numerator = sum(
        comb(
            trials,
            value,
        )
        for value in range(
            matches,
            trials + 1,
        )
    )

    denominator = 2 ** trials

    return Fraction(
        numerator,
        denominator,
    )


def build_prospective_validation_assessment(
    *,
    cohort: ProspectiveValidationCohort,
    multiplicity_guard:
        ProspectiveValidationMultiplicityGuard,
    created_at: datetime,
) -> ProspectiveValidationAssessment:
    """Assess prospective directional prediction without promotion."""

    _validate_source_authority(
        cohort,
        multiplicity_guard,
    )

    if (
        cohort.athlete_id
        != multiplicity_guard.athlete_id
    ):
        raise ValueError(
            "Prospective cohort and multiplicity guard "
            "athlete identity differ."
        )

    if (
        cohort.family_key
        != multiplicity_guard.target_family_key
    ):
        raise ValueError(
            "Prospective cohort and multiplicity guard "
            "family differ."
        )

    if cohort.as_of != multiplicity_guard.as_of:
        raise ValueError(
            "Prospective cohort and multiplicity guard "
            "must use the same as_of boundary."
        )

    created = to_utc(
        created_at,
        field_name="created_at",
    )

    if created < cohort.as_of:
        raise ValueError(
            "Prospective validation assessment cannot "
            "predate as_of."
        )

    target_entry = next(
        (
            entry
            for entry
            in multiplicity_guard.family_census
            if entry.family_key
            == cohort.family_key
        ),
        None,
    )

    if target_entry is None:
        exact_universe_match = False
    else:
        cohort_ids = tuple(
            entry.issuance_id
            for entry in cohort.entries
        )

        cohort_hashes = tuple(
            entry.issuance_content_hash
            for entry in cohort.entries
        )

        exact_universe_match = (
            cohort_ids
            == target_entry.issuance_ids
            and cohort_hashes
            == target_entry.issuance_content_hashes
            and cohort.issued_challenge_count
            == target_entry.issuance_count
        )

    scored = cohort.directionally_scored_count
    matches = cohort.matched_count
    mismatches = cohort.mismatched_count

    if scored != matches + mismatches:
        raise ValueError(
            "Prospective cohort directional counts "
            "are inconsistent."
        )

    p_value = _exact_binomial_upper_tail(
        matches=matches,
        trials=scored,
    )

    alpha_num = (
        multiplicity_guard
        .adjusted_alpha_numerator
    )

    alpha_den = (
        multiplicity_guard
        .adjusted_alpha_denominator
    )

    if (
        alpha_num is None
        or alpha_den is None
    ):
        threshold_met = False
    else:
        if (
            alpha_num <= 0
            or alpha_den <= 0
        ):
            raise ValueError(
                "Adjusted alpha must be positive."
            )

        adjusted_alpha = Fraction(
            alpha_num,
            alpha_den,
        )

        threshold_met = (
            scored > 0
            and p_value <= adjusted_alpha
        )

    directional_above_chance = (
        scored > 0
        and matches > mismatches
    )

    structural_eligibility = (
        cohort.validation_assessment_input_eligible
        is True
        and multiplicity_guard
        .validation_assessment_input_eligible
        is True
        and exact_universe_match
    )

    criteria_met = (
        structural_eligibility
        and directional_above_chance
        and threshold_met
    )

    if not structural_eligibility:
        status = (
            ProspectiveValidationAssessmentStatus
            .INELIGIBLE
        )
    elif criteria_met:
        status = (
            ProspectiveValidationAssessmentStatus
            .VALIDATION_CRITERIA_MET
        )
    else:
        status = (
            ProspectiveValidationAssessmentStatus
            .VALIDATION_UNESTABLISHED
        )

    provisional = ProspectiveValidationAssessment(
        assessment_id="PENDING",
        schema_version=(
            PROSPECTIVE_VALIDATION_ASSESSMENT_SCHEMA_V01
        ),
        rules_version=(
            PROSPECTIVE_VALIDATION_ASSESSMENT_RULES_V01
        ),

        athlete_id=cohort.athlete_id,
        family_key=cohort.family_key,
        as_of=cohort.as_of,

        source_cohort_id=cohort.cohort_id,
        source_cohort_content_hash=(
            cohort.content_hash
        ),

        source_multiplicity_guard_id=(
            multiplicity_guard.guard_id
        ),
        source_multiplicity_guard_content_hash=(
            multiplicity_guard.content_hash
        ),

        issued_challenge_count=(
            cohort.issued_challenge_count
        ),
        bound_challenge_count=(
            cohort.bound_challenge_count
        ),

        directionally_scored_count=scored,
        matched_count=matches,
        mismatched_count=mismatches,
        tied_unscorable_count=(
            cohort.tied_unscorable_count
        ),

        exact_issuance_universe_match=(
            exact_universe_match
        ),

        null_match_probability_numerator=1,
        null_match_probability_denominator=2,

        exact_one_sided_p_numerator=(
            p_value.numerator
        ),
        exact_one_sided_p_denominator=(
            p_value.denominator
        ),

        adjusted_alpha_numerator=alpha_num,
        adjusted_alpha_denominator=alpha_den,

        directional_success_above_chance=(
            directional_above_chance
        ),
        statistical_threshold_met=(
            threshold_met
        ),

        validation_criteria_met=(
            criteria_met
        ),
        status=status,

        # P2.3C3 still does not perform the D promotion.
        evidence_level_ceiling=(
            EffectEvidenceLevel.ASSOCIATION_SUPPORTED
        ),
        association_supported=True,

        prospective_validation_established=False,
        causal_attribution_established=False,
        effect_inference_authorized=False,
        readiness_inference_authorized=False,
        performance_prediction_authorized=False,
        prescription_change_authorized=False,
        planning_authorized=False,

        created_at=created,

        content_hash_algorithm=(
            CONTENT_HASH_ALGORITHM
        ),
        content_hash="",
    )

    digest = compute_content_hash(
        provisional,
        exclude_fields=(
            PROSPECTIVE_VALIDATION_ASSESSMENT_HASH_EXCLUDE_FIELDS
        ),
    )

    return ProspectiveValidationAssessment(
        **{
            **provisional.__dict__,
            "assessment_id": (
                "pt-prospective-validation-assessment:"
                f"{digest}"
            ),
            "content_hash": digest,
        }
    )
