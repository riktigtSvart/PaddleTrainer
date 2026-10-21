from dataclasses import replace
from datetime import datetime, timezone

import pytest

import app.planning.application.assemble_prospective_validation_cohort as assembler

from app.planning.domain.common.serialization import (
    CONTENT_HASH_ALGORITHM,
    compute_content_hash,
)
from app.planning.domain.persistence.audit import (
    AuditArtifactKind,
    AuditArtifactRecord,
)
from app.planning.domain.response_evidence import (
    TrainingResponseTiming,
)
from app.planning.domain.training_dynamics import (
    EffectEvidenceLevel,
    PersonalAssociationPredictorKey,
    PersonalResponsePredictionDirection,
    ResponseMetricReferenceKey,
)
from app.planning.domain.training_dynamics.prospective_cohort import (
    ProspectiveCohortOutcomeStatus,
    ProspectiveIssuanceCohortSource,
    ProspectiveOutcomeCohortSource,
    ProspectiveValidationFamilyKey,
    build_prospective_validation_cohort,
)
from app.planning.domain.training_dynamics.prospective_issuance import (
    PERSONAL_RESPONSE_PREDICTION_ISSUANCE_HASH_EXCLUDE_FIELDS,
    PERSONAL_RESPONSE_PREDICTION_ISSUANCE_RULES_V01,
    PERSONAL_RESPONSE_PREDICTION_ISSUANCE_SCHEMA_V01,
    PersonalResponsePredictionIssuanceContract,
)
from app.planning.domain.training_dynamics.prospective_outcome import (
    PROSPECTIVE_RESPONSE_CHALLENGE_HASH_EXCLUDE_FIELDS,
    PROSPECTIVE_RESPONSE_CHALLENGE_RULES_V01,
    PROSPECTIVE_RESPONSE_CHALLENGE_SCHEMA_V01,
    ProspectiveResponseActualDirection,
    ProspectiveResponseChallenge,
    ProspectiveResponseChallengeResult,
    personal_response_prediction_outcome_binding_id,
)


UTC = timezone.utc

ATHLETE = "11111111-1111-4111-8111-111111111111"

SESSION_1 = "22222222-2222-4222-8222-222222222222"
SESSION_2 = "33333333-3333-4333-8333-333333333333"
SESSION_3 = "44444444-4444-4444-8444-444444444444"


def dt(
    hour: int,
    minute: int = 0,
) -> datetime:
    return datetime(
        2026,
        10,
        21,
        hour,
        minute,
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
        metric_key="self_reported_fatigue_score",
        unit="score_0_10",
        response_timing=TrainingResponseTiming.SAME_DAY,
        stimulus_modality_key="RUNNING",
    ),
)


def issuance(
    *,
    session_id=SESSION_1,
    predictor_value=4.5,
    model_version="0.1.0",
):
    provisional = PersonalResponsePredictionIssuanceContract(
        issuance_id="PENDING",
        schema_version=(
            PERSONAL_RESPONSE_PREDICTION_ISSUANCE_SCHEMA_V01
        ),
        rules_version=(
            PERSONAL_RESPONSE_PREDICTION_ISSUANCE_RULES_V01
        ),

        athlete_id=ATHLETE,
        workout_session_id=session_id,

        source_candidate_id=(
            f"candidate:{session_id}:{predictor_value}"
        ),
        source_candidate_content_hash="a" * 64,
        source_candidate_schema_version=(
            "personal-response-prediction-candidate-v0.1"
        ),
        source_candidate_rules_version=(
            "personal-response-prediction-rules-v0.1"
        ),

        model_id=(
            "personal-monotonic-median-direction"
        ),
        model_version=model_version,

        predictor_key=FAMILY.predictor_key,
        response_key=FAMILY.response_key,

        information_cutoff_at=dt(10),
        prediction_at=dt(11),

        target_predictor_value=predictor_value,
        historical_response_median=3.0,

        predicted_response_direction=(
            PersonalResponsePredictionDirection
            .ABOVE_HISTORICAL_MEDIAN
        ),

        response_prediction_available=True,

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

        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash="",
    )

    digest = compute_content_hash(
        provisional,
        exclude_fields=(
            PERSONAL_RESPONSE_PREDICTION_ISSUANCE_HASH_EXCLUDE_FIELDS
        ),
    )

    return replace(
        provisional,
        issuance_id=(
            "pt-personal-response-prediction-issuance:"
            + digest
        ),
        content_hash=digest,
    )


def challenge(
    source,
    *,
    result=(
        ProspectiveResponseChallengeResult
        .DIRECTION_MATCHED
    ),
    issuance_persisted_at=dt(12),
):
    if (
        result
        == ProspectiveResponseChallengeResult
        .DIRECTION_MATCHED
    ):
        actual_direction = (
            ProspectiveResponseActualDirection
            .ABOVE_HISTORICAL_MEDIAN
        )
        actual_value = 4.0
        scored = True

    elif (
        result
        == ProspectiveResponseChallengeResult
        .DIRECTION_MISMATCHED
    ):
        actual_direction = (
            ProspectiveResponseActualDirection
            .BELOW_HISTORICAL_MEDIAN
        )
        actual_value = 2.0
        scored = True

    else:
        actual_direction = (
            ProspectiveResponseActualDirection
            .AT_HISTORICAL_MEDIAN
        )
        actual_value = 3.0
        scored = False

    provisional = ProspectiveResponseChallenge(
        binding_id=(
            personal_response_prediction_outcome_binding_id(
                source.issuance_id
            )
        ),
        schema_version=(
            PROSPECTIVE_RESPONSE_CHALLENGE_SCHEMA_V01
        ),
        rules_version=(
            PROSPECTIVE_RESPONSE_CHALLENGE_RULES_V01
        ),

        athlete_id=ATHLETE,
        workout_session_id=(
            source.workout_session_id
        ),

        source_issuance_id=source.issuance_id,
        source_issuance_content_hash=(
            source.content_hash
        ),

        source_candidate_id=(
            source.source_candidate_id
        ),
        source_candidate_content_hash=(
            source.source_candidate_content_hash
        ),

        source_response_artifact_id=(
            "pt-training-response-evidence:"
            + source.content_hash[:16]
        ),
        source_response_content_hash="b" * 64,

        source_executed_training_evidence_id=(
            "pt-executed-training-evidence:"
            f"session:{source.workout_session_id}"
        ),
        source_executed_training_evidence_hash="c" * 64,

        response_key=source.response_key,

        prediction_direction=(
            source.predicted_response_direction
        ),

        historical_response_median=3.0,
        actual_response_value=actual_value,

        actual_response_direction=actual_direction,

        result=result,

        issuance_persisted_at=(
            issuance_persisted_at
        ),

        response_observed_at=dt(13),
        response_available_at=dt(14),
        response_persisted_at=dt(15),

        prospective_challenge_established=True,
        directional_score_available=scored,

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

        created_at=dt(15),

        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash="",
    )

    digest = compute_content_hash(
        provisional,
        exclude_fields=(
            PROSPECTIVE_RESPONSE_CHALLENGE_HASH_EXCLUDE_FIELDS
        ),
    )

    return replace(
        provisional,
        content_hash=digest,
    )


def build(
    *,
    issuance_sources,
    outcome_sources,
    audit_scan_complete=True,
):
    return build_prospective_validation_cohort(
        athlete_id=ATHLETE,
        family_key=FAMILY,
        as_of=dt(20),
        issuance_sources=tuple(
            issuance_sources
        ),
        outcome_sources=tuple(
            outcome_sources
        ),
        audit_scan_complete=(
            audit_scan_complete
        ),
        created_at=dt(20),
    )


def test_complete_bound_cohort_is_structurally_eligible():
    first = issuance(
        session_id=SESSION_1,
    )
    second = issuance(
        session_id=SESSION_2,
    )

    cohort = build(
        issuance_sources=(
            ProspectiveIssuanceCohortSource(
                first,
                dt(12),
            ),
            ProspectiveIssuanceCohortSource(
                second,
                dt(12, 30),
            ),
        ),
        outcome_sources=(
            ProspectiveOutcomeCohortSource(
                challenge(first),
                dt(16),
            ),
            ProspectiveOutcomeCohortSource(
                challenge(
                    second,
                    result=(
                        ProspectiveResponseChallengeResult
                        .DIRECTION_MISMATCHED
                    ),
                    issuance_persisted_at=(
                        dt(12, 30)
                    ),
                ),
                dt(17),
            ),
        ),
    )

    assert cohort.issued_challenge_count == 2
    assert cohort.bound_challenge_count == 2
    assert cohort.directionally_scored_count == 2

    assert cohort.matched_count == 1
    assert cohort.mismatched_count == 1
    assert cohort.tied_unscorable_count == 0
    assert cohort.unbound_count == 0

    assert cohort.duplicate_session_count == 0
    assert cohort.selection_guard_passed is True

    assert (
        cohort.outcome_completeness_established
        is True
    )

    assert (
        cohort.validation_assessment_input_eligible
        is True
    )

    assert (
        cohort.prospective_validation_established
        is False
    )
    assert cohort.planning_authorized is False
    assert cohort.verify_content_hash()


def test_unbound_issuance_is_retained_and_blocks_validation_input():
    first = issuance(
        session_id=SESSION_1,
    )
    second = issuance(
        session_id=SESSION_2,
    )

    cohort = build(
        issuance_sources=(
            ProspectiveIssuanceCohortSource(
                first,
                dt(12),
            ),
            ProspectiveIssuanceCohortSource(
                second,
                dt(12, 30),
            ),
        ),
        outcome_sources=(
            ProspectiveOutcomeCohortSource(
                challenge(first),
                dt(16),
            ),
        ),
    )

    assert cohort.issued_challenge_count == 2
    assert cohort.bound_challenge_count == 1
    assert cohort.unbound_count == 1

    assert any(
        entry.outcome_status
        == ProspectiveCohortOutcomeStatus.UNBOUND
        for entry in cohort.entries
    )

    assert (
        cohort.outcome_completeness_established
        is False
    )

    assert (
        cohort.validation_assessment_input_eligible
        is False
    )


def test_tied_outcome_is_retained_but_not_directionally_scored():
    source = issuance()

    cohort = build(
        issuance_sources=(
            ProspectiveIssuanceCohortSource(
                source,
                dt(12),
            ),
        ),
        outcome_sources=(
            ProspectiveOutcomeCohortSource(
                challenge(
                    source,
                    result=(
                        ProspectiveResponseChallengeResult
                        .TIED_UNSCORABLE
                    ),
                ),
                dt(16),
            ),
        ),
    )

    assert cohort.bound_challenge_count == 1
    assert cohort.directionally_scored_count == 0
    assert cohort.tied_unscorable_count == 1

    assert (
        cohort.entries[0].outcome_status
        == ProspectiveCohortOutcomeStatus
        .TIED_UNSCORABLE
    )

    # Ties stay in the cohort. C3 will decide statistical sufficiency.
    assert (
        cohort.validation_assessment_input_eligible
        is True
    )


def test_duplicate_same_session_issuances_are_retained_and_flagged():
    first = issuance(
        predictor_value=4.5,
    )

    second = issuance(
        predictor_value=5.0,
    )

    assert (
        first.workout_session_id
        == second.workout_session_id
    )
    assert first.issuance_id != second.issuance_id

    cohort = build(
        issuance_sources=(
            ProspectiveIssuanceCohortSource(
                first,
                dt(12),
            ),
            ProspectiveIssuanceCohortSource(
                second,
                dt(12, 30),
            ),
        ),
        outcome_sources=(
            ProspectiveOutcomeCohortSource(
                challenge(first),
                dt(16),
            ),
            ProspectiveOutcomeCohortSource(
                challenge(
                    second,
                    issuance_persisted_at=(
                        dt(12, 30)
                    ),
                ),
                dt(17),
            ),
        ),
    )

    assert cohort.issued_challenge_count == 2
    assert cohort.duplicate_session_count == 1
    assert cohort.duplicate_issuance_count == 1

    assert all(
        entry.duplicate_session_issuance
        for entry in cohort.entries
    )

    assert cohort.selection_guard_passed is False

    assert (
        cohort.validation_assessment_input_eligible
        is False
    )


def test_outcome_must_hash_bind_exact_issuance():
    source = issuance()

    bad = replace(
        challenge(source),
        source_issuance_content_hash="f" * 64,
    )

    # Re-hash the tampered challenge so this tests lineage,
    # not merely hash verification.
    bad = replace(
        bad,
        content_hash=compute_content_hash(
            bad,
            exclude_fields=(
                PROSPECTIVE_RESPONSE_CHALLENGE_HASH_EXCLUDE_FIELDS
            ),
        ),
    )

    with pytest.raises(
        ValueError,
        match="does not hash-bind",
    ):
        build(
            issuance_sources=(
                ProspectiveIssuanceCohortSource(
                    source,
                    dt(12),
                ),
            ),
            outcome_sources=(
                ProspectiveOutcomeCohortSource(
                    bad,
                    dt(16),
                ),
            ),
        )


class FakeAuditRepository:
    def __init__(
        self,
        *,
        issuance_records=(),
        outcome_records=(),
    ):
        self.issuance_records = tuple(
            issuance_records
        )
        self.outcome_records = tuple(
            outcome_records
        )

    async def list_for_athlete(
        self,
        *,
        athlete_id,
        artifact_kind=None,
        limit=50,
    ):
        assert athlete_id == ATHLETE
        assert limit == 500

        if (
            artifact_kind
            == AuditArtifactKind
            .PERSONAL_RESPONSE_PREDICTION_ISSUANCE
        ):
            return self.issuance_records[
                :limit
            ]

        if (
            artifact_kind
            == AuditArtifactKind
            .PERSONAL_RESPONSE_PREDICTION_OUTCOME
        ):
            return self.outcome_records[
                :limit
            ]

        raise AssertionError(
            artifact_kind
        )


def issuance_record(
    source,
    *,
    persisted_at,
):
    return AuditArtifactRecord(
        artifact_kind=(
            AuditArtifactKind
            .PERSONAL_RESPONSE_PREDICTION_ISSUANCE
        ),
        artifact_id=source.issuance_id,
        athlete_id=source.athlete_id,
        schema_version=source.schema_version,
        created_at=source.prediction_at,
        content_hash_algorithm=(
            source.content_hash_algorithm
        ),
        content_hash=source.content_hash,
        contract_json="issuance-stub",
        persisted_at=persisted_at,
    )


def outcome_record(
    source,
    *,
    persisted_at,
):
    return AuditArtifactRecord(
        artifact_kind=(
            AuditArtifactKind
            .PERSONAL_RESPONSE_PREDICTION_OUTCOME
        ),
        artifact_id=source.binding_id,
        athlete_id=source.athlete_id,
        schema_version=source.schema_version,
        created_at=source.created_at,
        content_hash_algorithm=(
            source.content_hash_algorithm
        ),
        content_hash=source.content_hash,
        contract_json="outcome-stub",
        persisted_at=persisted_at,
    )


@pytest.mark.asyncio
async def test_application_as_of_excludes_future_durable_artifacts(
    monkeypatch,
):
    current = issuance(
        session_id=SESSION_1,
    )

    future = issuance(
        session_id=SESSION_2,
    )

    current_outcome = challenge(
        current
    )

    repository = FakeAuditRepository(
        issuance_records=(
            issuance_record(
                current,
                persisted_at=dt(12),
            ),
            issuance_record(
                future,
                persisted_at=dt(21),
            ),
        ),
        outcome_records=(
            outcome_record(
                current_outcome,
                persisted_at=dt(16),
            ),
        ),
    )

    issuance_map = {
        current.issuance_id: current,
        future.issuance_id: future,
    }

    outcome_map = {
        current_outcome.binding_id:
            current_outcome,
    }

    monkeypatch.setattr(
        assembler,
        "restore_personal_response_prediction_issuance_audit_artifact",
        lambda record: issuance_map[
            record.artifact_id
        ],
    )

    monkeypatch.setattr(
        assembler,
        "restore_personal_response_prediction_outcome_audit_artifact",
        lambda record: outcome_map[
            record.artifact_id
        ],
    )

    cohort = await (
        assembler.assemble_prospective_validation_cohort(
            athlete_id=ATHLETE,
            family_key=FAMILY,
            as_of=dt(20),
            created_at=dt(20),
            audit_repository=repository,
        )
    )

    assert cohort.issued_challenge_count == 1
    assert (
        cohort.entries[0].issuance_id
        == current.issuance_id
    )


@pytest.mark.asyncio
async def test_repository_scan_limit_blocks_completeness_claim(
    monkeypatch,
):
    future_records = tuple(
        AuditArtifactRecord(
            artifact_kind=(
                AuditArtifactKind
                .PERSONAL_RESPONSE_PREDICTION_ISSUANCE
            ),
            artifact_id=f"future-{index}",
            athlete_id=ATHLETE,
            schema_version="future",
            created_at=dt(21),
            content_hash_algorithm=(
                CONTENT_HASH_ALGORITHM
            ),
            content_hash="f" * 64,
            contract_json="{}",
            persisted_at=dt(21),
        )
        for index in range(500)
    )

    repository = FakeAuditRepository(
        issuance_records=future_records,
    )

    monkeypatch.setattr(
        assembler,
        "restore_personal_response_prediction_issuance_audit_artifact",
        lambda record: pytest.fail(
            "Future records must not be restored."
        ),
    )

    cohort = await (
        assembler.assemble_prospective_validation_cohort(
            athlete_id=ATHLETE,
            family_key=FAMILY,
            as_of=dt(20),
            created_at=dt(20),
            audit_repository=repository,
        )
    )

    assert cohort.audit_scan_complete is False
    assert cohort.issued_challenge_count == 0
    assert cohort.selection_guard_passed is False

    assert (
        cohort.validation_assessment_input_eligible
        is False
    )


@pytest.mark.asyncio
async def test_application_ignores_other_validation_family(
    monkeypatch,
):
    target = issuance(
        session_id=SESSION_1,
    )

    other = issuance(
        session_id=SESSION_3,
        model_version="9.9.9",
    )

    repository = FakeAuditRepository(
        issuance_records=(
            issuance_record(
                target,
                persisted_at=dt(12),
            ),
            issuance_record(
                other,
                persisted_at=dt(12, 30),
            ),
        ),
    )

    issuance_map = {
        target.issuance_id: target,
        other.issuance_id: other,
    }

    monkeypatch.setattr(
        assembler,
        "restore_personal_response_prediction_issuance_audit_artifact",
        lambda record: issuance_map[
            record.artifact_id
        ],
    )

    cohort = await (
        assembler.assemble_prospective_validation_cohort(
            athlete_id=ATHLETE,
            family_key=FAMILY,
            as_of=dt(20),
            created_at=dt(20),
            audit_repository=repository,
        )
    )

    assert cohort.issued_challenge_count == 1
    assert (
        cohort.entries[0].issuance_id
        == target.issuance_id
    )
