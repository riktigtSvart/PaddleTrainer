from dataclasses import replace
from datetime import datetime, timezone

import pytest

import app.planning.application.assemble_prospective_validation_evidence as application

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
    PROSPECTIVE_VALIDATION_ASSESSMENT_HASH_EXCLUDE_FIELDS,
    ProspectiveValidationAssessmentStatus,
    build_prospective_validation_assessment,
)
from app.planning.domain.training_dynamics.prospective_validation_evidence import (
    ProspectiveValidationEvidenceStatus,
    build_prospective_validation_evidence,
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
    matches=5,
    mismatches=0,
):
    total = matches + mismatches
    entries = []

    for index in range(total):
        if index < matches:
            status = (
                ProspectiveCohortOutcomeStatus
                .DIRECTION_MATCHED
            )
        else:
            status = (
                ProspectiveCohortOutcomeStatus
                .DIRECTION_MISMATCHED
            )

        entries.append(
            ProspectiveChallengeCohortEntry(
                issuance_id=f"issuance-{index}",
                issuance_content_hash=(
                    f"{index + 1:064x}"[-64:]
                ),
                workout_session_id=f"session-{index}",
                issuance_persisted_at=dt(10),

                duplicate_session_issuance=False,

                outcome_status=status,

                binding_id=f"binding-{index}",
                binding_content_hash="a" * 64,
                binding_persisted_at=dt(15),

                response_artifact_id=f"response-{index}",
                response_artifact_content_hash="b" * 64,

                directional_score_available=True,
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

        audit_scan_complete=True,

        issued_challenge_count=total,
        bound_challenge_count=total,
        directionally_scored_count=total,

        matched_count=matches,
        mismatched_count=mismatches,
        tied_unscorable_count=0,
        unbound_count=0,

        duplicate_session_count=0,
        duplicate_issuance_count=0,

        selection_guard_passed=True,
        outcome_completeness_established=True,
        validation_assessment_input_eligible=True,

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
):
    ids = tuple(
        entry.issuance_id
        for entry in source_cohort.entries
    )

    hashes = tuple(
        entry.issuance_content_hash
        for entry in source_cohort.entries
    )

    entry = ProspectiveValidationFamilyCensusEntry(
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

        audit_scan_complete=True,

        family_count=family_count,
        target_family_present=True,
        target_family_issuance_count=len(ids),

        family_census=(entry,),

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

        anti_selection_guard_passed=True,
        multiplicity_guard_passed=True,
        validation_assessment_input_eligible=True,

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


def sources(
    *,
    matches=5,
    mismatches=0,
    family_count=1,
):
    c = cohort(
        matches=matches,
        mismatches=mismatches,
    )

    g = guard(
        c,
        family_count=family_count,
    )

    a = build_prospective_validation_assessment(
        cohort=c,
        multiplicity_guard=g,
        created_at=dt(20),
    )

    return c, g, a


def test_successful_replay_promotes_to_prospectively_validated():
    c, g, a = sources(
        matches=5,
        mismatches=0,
    )

    evidence = build_prospective_validation_evidence(
        cohort=c,
        multiplicity_guard=g,
        assessment=a,
        created_at=dt(21),
    )

    assert (
        a.status
        == ProspectiveValidationAssessmentStatus
        .VALIDATION_CRITERIA_MET
    )

    assert (
        evidence.status
        == ProspectiveValidationEvidenceStatus
        .PROSPECTIVELY_VALIDATED
    )

    assert (
        evidence.evidence_level
        == EffectEvidenceLevel.PROSPECTIVELY_VALIDATED
    )

    assert evidence.association_supported is True

    assert (
        evidence.prospective_validation_established
        is True
    )

    assert evidence.causal_attribution_established is False
    assert evidence.effect_inference_authorized is False
    assert evidence.readiness_inference_authorized is False
    assert evidence.performance_prediction_authorized is False
    assert evidence.prescription_change_authorized is False
    assert evidence.planning_authorized is False

    assert evidence.verify_content_hash()


def test_unsuccessful_assessment_remains_unestablished():
    c, g, a = sources(
        matches=4,
        mismatches=1,
    )

    evidence = build_prospective_validation_evidence(
        cohort=c,
        multiplicity_guard=g,
        assessment=a,
        created_at=dt(21),
    )

    assert (
        a.status
        == ProspectiveValidationAssessmentStatus
        .VALIDATION_UNESTABLISHED
    )

    assert (
        evidence.status
        == ProspectiveValidationEvidenceStatus
        .UNESTABLISHED
    )

    assert (
        evidence.evidence_level
        == EffectEvidenceLevel.ASSOCIATION_SUPPORTED
    )

    assert (
        evidence.prospective_validation_established
        is False
    )


def test_tampered_assessment_hash_is_rejected():
    c, g, a = sources()

    bad = replace(
        a,
        content_hash="f" * 64,
    )

    with pytest.raises(
        ValueError,
        match="assessment hash",
    ):
        build_prospective_validation_evidence(
            cohort=c,
            multiplicity_guard=g,
            assessment=bad,
            created_at=dt(21),
        )


def test_assessment_must_reference_exact_c1_c2_sources():
    c, g, a = sources()

    bad = replace(
        a,
        source_cohort_content_hash="f" * 64,
    )

    digest = compute_content_hash(
        bad,
        exclude_fields=(
            PROSPECTIVE_VALIDATION_ASSESSMENT_HASH_EXCLUDE_FIELDS
        ),
    )

    bad = replace(
        bad,
        assessment_id=(
            "pt-prospective-validation-assessment:"
            + digest
        ),
        content_hash=digest,
    )

    with pytest.raises(
        ValueError,
        match="does not reference",
    ):
        build_prospective_validation_evidence(
            cohort=c,
            multiplicity_guard=g,
            assessment=bad,
            created_at=dt(21),
        )


def test_materialized_but_non_replayable_assessment_is_rejected():
    c, g, a = sources()

    bad = replace(
        a,
        exact_one_sided_p_numerator=2,
    )

    digest = compute_content_hash(
        bad,
        exclude_fields=(
            PROSPECTIVE_VALIDATION_ASSESSMENT_HASH_EXCLUDE_FIELDS
        ),
    )

    bad = replace(
        bad,
        assessment_id=(
            "pt-prospective-validation-assessment:"
            + digest
        ),
        content_hash=digest,
    )

    with pytest.raises(
        ValueError,
        match="does not replay exactly",
    ):
        build_prospective_validation_evidence(
            cohort=c,
            multiplicity_guard=g,
            assessment=bad,
            created_at=dt(21),
        )


def test_evidence_cannot_predate_sources():
    c, g, a = sources()

    with pytest.raises(
        ValueError,
        match="cannot predate",
    ):
        build_prospective_validation_evidence(
            cohort=c,
            multiplicity_guard=g,
            assessment=a,
            created_at=dt(19),
        )


@pytest.mark.asyncio
async def test_application_replays_c1_c2_c3_before_promotion(
    monkeypatch,
):
    c, g, _ = sources()

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
        application.assemble_prospective_validation_evidence(
            athlete_id=ATHLETE,
            family_key=FAMILY,
            as_of=dt(20),
            created_at=dt(21),
            audit_repository=object(),
        )
    )

    assert (
        result.status
        == ProspectiveValidationEvidenceStatus
        .PROSPECTIVELY_VALIDATED
    )

    assert (
        result.prospective_validation_established
        is True
    )

    assert len(calls) == 2

    assert calls[0][1:] == (
        ATHLETE,
        FAMILY,
        dt(20),
        dt(21),
    )

    assert calls[1][1:] == (
        ATHLETE,
        FAMILY,
        dt(20),
        dt(21),
    )
