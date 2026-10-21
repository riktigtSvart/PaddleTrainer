from dataclasses import replace
from datetime import datetime, timezone

import pytest

import app.planning.application.assess_prospective_validation as application

from app.planning.domain.common.serialization import (
    CONTENT_HASH_ALGORITHM,
    compute_content_hash,
)
from app.planning.domain.response_evidence import (
    TrainingResponseTiming,
)
from app.planning.domain.training_dynamics import (
    EffectEvidenceLevel,
    PersonalAssociationPredictorKey,
    ResponseMetricReferenceKey,
)
from app.planning.domain.training_dynamics.prospective_cohort import (
    PROSPECTIVE_VALIDATION_COHORT_HASH_EXCLUDE_FIELDS,
    PROSPECTIVE_VALIDATION_COHORT_RULES_V01,
    PROSPECTIVE_VALIDATION_COHORT_SCHEMA_V01,
    ProspectiveChallengeCohortEntry,
    ProspectiveCohortOutcomeStatus,
    ProspectiveValidationCohort,
    ProspectiveValidationFamilyKey,
)
from app.planning.domain.training_dynamics.prospective_multiplicity import (
    PROSPECTIVE_MULTIPLICITY_GUARD_HASH_EXCLUDE_FIELDS,
    PROSPECTIVE_MULTIPLICITY_GUARD_RULES_V01,
    PROSPECTIVE_MULTIPLICITY_GUARD_SCHEMA_V01,
    ProspectiveMultiplicityMethod,
    ProspectiveValidationFamilyCensusEntry,
    ProspectiveValidationMultiplicityGuard,
)
from app.planning.domain.training_dynamics.prospective_validation import (
    ProspectiveValidationAssessmentStatus,
    build_prospective_validation_assessment,
)


UTC = timezone.utc

ATHLETE = "11111111-1111-4111-8111-111111111111"


def dt(hour: int) -> datetime:
    return datetime(
        2026,
        10,
        21,
        hour,
        tzinfo=UTC,
    )


FAMILY = ProspectiveValidationFamilyKey(
    model_id="personal-monotonic-median-direction",
    model_version="0.1.0",
    predictor_key=PersonalAssociationPredictorKey(
        metric_key="training_load_index",
        unit="au",
    ),
    response_key=ResponseMetricReferenceKey(
        metric_key="fatigue",
        unit="score_0_10",
        response_timing=TrainingResponseTiming.SAME_DAY,
        stimulus_modality_key="RUNNING",
    ),
)


def cohort(
    *,
    matches,
    mismatches,
    ties=0,
    eligible=True,
):
    total = matches + mismatches + ties

    entries = []

    for index in range(total):
        issuance_id = f"issuance-{index}"
        issuance_hash = f"{index + 1:064x}"[-64:]

        if index < matches:
            status = (
                ProspectiveCohortOutcomeStatus
                .DIRECTION_MATCHED
            )
            scored = True
        elif index < matches + mismatches:
            status = (
                ProspectiveCohortOutcomeStatus
                .DIRECTION_MISMATCHED
            )
            scored = True
        else:
            status = (
                ProspectiveCohortOutcomeStatus
                .TIED_UNSCORABLE
            )
            scored = False

        entries.append(
            ProspectiveChallengeCohortEntry(
                issuance_id=issuance_id,
                issuance_content_hash=issuance_hash,
                workout_session_id=f"session-{index}",
                issuance_persisted_at=dt(10),

                duplicate_session_issuance=False,

                outcome_status=status,

                binding_id=f"binding-{index}",
                binding_content_hash="a" * 64,
                binding_persisted_at=dt(15),

                response_artifact_id=f"response-{index}",
                response_artifact_content_hash="b" * 64,

                directional_score_available=scored,
            )
        )

    provisional = ProspectiveValidationCohort(
        cohort_id="PENDING",
        schema_version=(
            PROSPECTIVE_VALIDATION_COHORT_SCHEMA_V01
        ),
        rules_version=(
            PROSPECTIVE_VALIDATION_COHORT_RULES_V01
        ),

        athlete_id=ATHLETE,
        family_key=FAMILY,

        as_of=dt(20),

        audit_scan_complete=eligible,

        issued_challenge_count=total,
        bound_challenge_count=total,
        directionally_scored_count=(
            matches + mismatches
        ),

        matched_count=matches,
        mismatched_count=mismatches,
        tied_unscorable_count=ties,
        unbound_count=0,

        duplicate_session_count=0,
        duplicate_issuance_count=0,

        selection_guard_passed=eligible,
        outcome_completeness_established=True,
        validation_assessment_input_eligible=eligible,

        entries=tuple(entries),

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

        created_at=dt(20),

        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash="",
    )

    digest = compute_content_hash(
        provisional,
        exclude_fields=(
            PROSPECTIVE_VALIDATION_COHORT_HASH_EXCLUDE_FIELDS
        ),
    )

    return replace(
        provisional,
        cohort_id=(
            "pt-prospective-validation-cohort:"
            + digest
        ),
        content_hash=digest,
    )


def guard(
    source_cohort,
    *,
    family_count=1,
    eligible=True,
    override_ids=None,
):
    ids = tuple(
        entry.issuance_id
        for entry in source_cohort.entries
    )

    hashes = tuple(
        entry.issuance_content_hash
        for entry in source_cohort.entries
    )

    if override_ids is not None:
        ids = tuple(override_ids)

    target = ProspectiveValidationFamilyCensusEntry(
        family_key=FAMILY,
        issuance_count=len(ids),
        issuance_ids=ids,
        issuance_content_hashes=hashes,
        first_issuance_persisted_at=dt(10),
        last_issuance_persisted_at=dt(10),
    )

    provisional = ProspectiveValidationMultiplicityGuard(
        guard_id="PENDING",
        schema_version=(
            PROSPECTIVE_MULTIPLICITY_GUARD_SCHEMA_V01
        ),
        rules_version=(
            PROSPECTIVE_MULTIPLICITY_GUARD_RULES_V01
        ),

        athlete_id=ATHLETE,
        target_family_key=FAMILY,

        as_of=dt(20),

        audit_scan_complete=eligible,

        family_count=family_count,
        target_family_present=True,
        target_family_issuance_count=len(ids),

        family_census=(target,),

        multiplicity_method=(
            ProspectiveMultiplicityMethod
            .BONFERRONI_FWER
        ),

        familywise_alpha_numerator=1,
        familywise_alpha_denominator=20,

        adjusted_alpha_numerator=1,
        adjusted_alpha_denominator=(
            20 * family_count
        ),

        anti_selection_guard_passed=eligible,
        multiplicity_guard_passed=eligible,

        validation_assessment_input_eligible=eligible,

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

        created_at=dt(20),

        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash="",
    )

    digest = compute_content_hash(
        provisional,
        exclude_fields=(
            PROSPECTIVE_MULTIPLICITY_GUARD_HASH_EXCLUDE_FIELDS
        ),
    )

    return replace(
        provisional,
        guard_id=(
            "pt-prospective-multiplicity-guard:"
            + digest
        ),
        content_hash=digest,
    )


def assess(
    *,
    matches,
    mismatches,
    ties=0,
    family_count=1,
):
    c = cohort(
        matches=matches,
        mismatches=mismatches,
        ties=ties,
    )

    g = guard(
        c,
        family_count=family_count,
    )

    return build_prospective_validation_assessment(
        cohort=c,
        multiplicity_guard=g,
        created_at=dt(20),
    )


def test_five_of_five_matches_meet_single_family_threshold():
    result = assess(
        matches=5,
        mismatches=0,
    )

    assert result.directionally_scored_count == 5

    assert result.exact_one_sided_p_numerator == 1
    assert result.exact_one_sided_p_denominator == 32

    assert result.adjusted_alpha_numerator == 1
    assert result.adjusted_alpha_denominator == 20

    assert result.directional_success_above_chance is True
    assert result.statistical_threshold_met is True
    assert result.validation_criteria_met is True

    assert (
        result.status
        == ProspectiveValidationAssessmentStatus
        .VALIDATION_CRITERIA_MET
    )

    # Promotion is deliberately deferred to P2.3D.
    assert result.prospective_validation_established is False
    assert (
        result.evidence_level_ceiling
        == EffectEvidenceLevel.ASSOCIATION_SUPPORTED
    )
    assert result.planning_authorized is False

    assert result.verify_content_hash()


def test_four_of_five_matches_do_not_meet_threshold():
    result = assess(
        matches=4,
        mismatches=1,
    )

    assert result.exact_one_sided_p_numerator == 3
    assert result.exact_one_sided_p_denominator == 16

    assert result.statistical_threshold_met is False
    assert result.validation_criteria_met is False

    assert (
        result.status
        == ProspectiveValidationAssessmentStatus
        .VALIDATION_UNESTABLISHED
    )


def test_five_of_five_fail_after_two_family_multiplicity_correction():
    result = assess(
        matches=5,
        mismatches=0,
        family_count=2,
    )

    assert result.exact_one_sided_p_numerator == 1
    assert result.exact_one_sided_p_denominator == 32

    assert result.adjusted_alpha_denominator == 40

    assert result.statistical_threshold_met is False
    assert result.validation_criteria_met is False


def test_six_of_six_pass_two_family_multiplicity_correction():
    result = assess(
        matches=6,
        mismatches=0,
        family_count=2,
    )

    assert result.exact_one_sided_p_numerator == 1
    assert result.exact_one_sided_p_denominator == 64

    assert result.adjusted_alpha_denominator == 40

    assert result.statistical_threshold_met is True
    assert result.validation_criteria_met is True


def test_ties_are_retained_but_not_counted_as_directional_trials():
    result = assess(
        matches=5,
        mismatches=0,
        ties=3,
    )

    assert result.issued_challenge_count == 8
    assert result.bound_challenge_count == 8

    assert result.directionally_scored_count == 5
    assert result.tied_unscorable_count == 3

    assert result.exact_one_sided_p_denominator == 32
    assert result.validation_criteria_met is True


def test_zero_scorable_challenges_cannot_validate():
    result = assess(
        matches=0,
        mismatches=0,
        ties=8,
    )

    assert result.exact_one_sided_p_numerator == 1
    assert result.exact_one_sided_p_denominator == 1

    assert result.directional_success_above_chance is False
    assert result.statistical_threshold_met is False
    assert result.validation_criteria_met is False

    assert (
        result.status
        == ProspectiveValidationAssessmentStatus
        .VALIDATION_UNESTABLISHED
    )


def test_exact_issuance_universe_mismatch_is_ineligible():
    c = cohort(
        matches=5,
        mismatches=0,
    )

    ids = [
        entry.issuance_id
        for entry in c.entries
    ]

    ids[-1] = "different-issuance"

    g = guard(
        c,
        override_ids=ids,
    )

    result = build_prospective_validation_assessment(
        cohort=c,
        multiplicity_guard=g,
        created_at=dt(20),
    )

    assert result.exact_issuance_universe_match is False
    assert result.validation_criteria_met is False

    assert (
        result.status
        == ProspectiveValidationAssessmentStatus
        .INELIGIBLE
    )


def test_ineligible_cohort_cannot_be_rescued_by_good_results():
    c = cohort(
        matches=10,
        mismatches=0,
        eligible=False,
    )

    g = guard(
        c,
        eligible=True,
    )

    result = build_prospective_validation_assessment(
        cohort=c,
        multiplicity_guard=g,
        created_at=dt(20),
    )

    assert result.statistical_threshold_met is True
    assert result.validation_criteria_met is False

    assert (
        result.status
        == ProspectiveValidationAssessmentStatus
        .INELIGIBLE
    )


@pytest.mark.asyncio
async def test_application_assembles_c1_and_c2_on_same_boundary(
    monkeypatch,
):
    c = cohort(
        matches=5,
        mismatches=0,
    )

    g = guard(c)

    calls = []

    async def fake_cohort(**kwargs):
        calls.append(
            (
                "cohort",
                kwargs["athlete_id"],
                kwargs["family_key"],
                kwargs["as_of"],
                kwargs["created_at"],
            )
        )
        return c

    async def fake_guard(**kwargs):
        calls.append(
            (
                "guard",
                kwargs["athlete_id"],
                kwargs["target_family_key"],
                kwargs["as_of"],
                kwargs["created_at"],
            )
        )
        return g

    monkeypatch.setattr(
        application,
        "assemble_prospective_validation_cohort",
        fake_cohort,
    )

    monkeypatch.setattr(
        application,
        "assemble_prospective_validation_multiplicity_guard",
        fake_guard,
    )

    result = await (
        application.assess_prospective_validation(
            athlete_id=ATHLETE,
            family_key=FAMILY,
            as_of=dt(20),
            created_at=dt(20),
            audit_repository=object(),
        )
    )

    assert result.validation_criteria_met is True

    assert len(calls) == 2

    assert calls[0][1:] == (
        ATHLETE,
        FAMILY,
        dt(20),
        dt(20),
    )

    assert calls[1][1:] == (
        ATHLETE,
        FAMILY,
        dt(20),
        dt(20),
    )
