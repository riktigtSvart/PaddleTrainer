from dataclasses import replace
from datetime import datetime, timezone

import pytest

import app.planning.application.assemble_prospective_multiplicity_guard as assembler

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
    ProspectiveIssuanceCohortSource,
    ProspectiveValidationFamilyKey,
)
from app.planning.domain.training_dynamics.prospective_issuance import (
    PERSONAL_RESPONSE_PREDICTION_ISSUANCE_HASH_EXCLUDE_FIELDS,
    PERSONAL_RESPONSE_PREDICTION_ISSUANCE_RULES_V01,
    PERSONAL_RESPONSE_PREDICTION_ISSUANCE_SCHEMA_V01,
    PersonalResponsePredictionIssuanceContract,
)
from app.planning.domain.training_dynamics.prospective_multiplicity import (
    ProspectiveMultiplicityMethod,
    build_prospective_validation_multiplicity_guard,
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


TARGET_FAMILY = ProspectiveValidationFamilyKey(
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
    model_version="0.1.0",
    predictor_metric="training_load_index",
    response_metric="self_reported_fatigue_score",
    predictor_value=4.5,
):
    predictor = PersonalAssociationPredictorKey(
        metric_key=predictor_metric,
        unit="au",
    )

    response = ResponseMetricReferenceKey(
        metric_key=response_metric,
        unit="score_0_10",
        response_timing=(
            TrainingResponseTiming.SAME_DAY
        ),
        stimulus_modality_key="RUNNING",
    )

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
            f"candidate:{session_id}:"
            f"{model_version}:"
            f"{predictor_metric}:"
            f"{response_metric}:"
            f"{predictor_value}"
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

        predictor_key=predictor,
        response_key=response,

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


def source(
    issuance_value,
    *,
    persisted_at,
):
    return ProspectiveIssuanceCohortSource(
        issuance=issuance_value,
        persisted_at=persisted_at,
    )


def build(
    *sources,
    target_family=TARGET_FAMILY,
    audit_scan_complete=True,
):
    return build_prospective_validation_multiplicity_guard(
        athlete_id=ATHLETE,
        target_family_key=target_family,
        as_of=dt(20),
        issuance_sources=tuple(
            sources
        ),
        audit_scan_complete=(
            audit_scan_complete
        ),
        created_at=dt(20),
    )


def test_one_family_gets_full_familywise_alpha_budget():
    first = issuance()

    guard = build(
        source(
            first,
            persisted_at=dt(12),
        )
    )

    assert guard.family_count == 1
    assert guard.target_family_present is True
    assert guard.target_family_issuance_count == 1

    assert (
        guard.multiplicity_method
        == ProspectiveMultiplicityMethod
        .BONFERRONI_FWER
    )

    assert guard.familywise_alpha_numerator == 1
    assert guard.familywise_alpha_denominator == 20

    assert guard.adjusted_alpha_numerator == 1
    assert guard.adjusted_alpha_denominator == 20

    assert guard.anti_selection_guard_passed is True
    assert guard.multiplicity_guard_passed is True

    assert (
        guard.validation_assessment_input_eligible
        is True
    )

    assert guard.prospective_validation_established is False
    assert guard.planning_authorized is False
    assert guard.verify_content_hash()


def test_three_exact_families_get_bonferroni_one_over_sixty():
    target = issuance(
        session_id=SESSION_1,
    )

    other_predictor = issuance(
        session_id=SESSION_2,
        predictor_metric="duration_s",
    )

    other_response = issuance(
        session_id=SESSION_3,
        response_metric="recovery_score",
    )

    guard = build(
        source(
            target,
            persisted_at=dt(12),
        ),
        source(
            other_predictor,
            persisted_at=dt(12, 10),
        ),
        source(
            other_response,
            persisted_at=dt(12, 20),
        ),
    )

    assert guard.family_count == 3
    assert guard.adjusted_alpha_numerator == 1
    assert guard.adjusted_alpha_denominator == 60

    assert len(guard.family_census) == 3


def test_multiple_issuances_same_family_do_not_inflate_family_count():
    first = issuance(
        session_id=SESSION_1,
        predictor_value=4.5,
    )

    second = issuance(
        session_id=SESSION_2,
        predictor_value=5.0,
    )

    guard = build(
        source(
            first,
            persisted_at=dt(12),
        ),
        source(
            second,
            persisted_at=dt(13),
        ),
    )

    assert guard.family_count == 1
    assert guard.target_family_issuance_count == 2

    assert (
        guard.family_census[0].issuance_count
        == 2
    )

    assert (
        guard.family_census[0].issuance_ids
        == (
            first.issuance_id,
            second.issuance_id,
        )
    )

    assert (
        guard.family_census[0].issuance_content_hashes
        == (
            first.content_hash,
            second.content_hash,
        )
    )

    assert guard.adjusted_alpha_denominator == 20


def test_different_model_version_is_separate_validation_family():
    target = issuance(
        session_id=SESSION_1,
    )

    alternate_model = issuance(
        session_id=SESSION_2,
        model_version="0.2.0",
    )

    guard = build(
        source(
            target,
            persisted_at=dt(12),
        ),
        source(
            alternate_model,
            persisted_at=dt(13),
        ),
    )

    assert guard.family_count == 2
    assert guard.adjusted_alpha_denominator == 40


def test_target_family_absence_fails_anti_selection_guard():
    other = issuance(
        model_version="9.9.9",
    )

    guard = build(
        source(
            other,
            persisted_at=dt(12),
        )
    )

    assert guard.family_count == 1
    assert guard.target_family_present is False
    assert guard.target_family_issuance_count == 0

    assert guard.anti_selection_guard_passed is False
    assert guard.multiplicity_guard_passed is False

    assert (
        guard.validation_assessment_input_eligible
        is False
    )


def test_incomplete_audit_scan_fails_closed_even_with_target_present():
    target = issuance()

    guard = build(
        source(
            target,
            persisted_at=dt(12),
        ),
        audit_scan_complete=False,
    )

    assert guard.target_family_present is True
    assert guard.audit_scan_complete is False

    assert guard.anti_selection_guard_passed is False
    assert guard.multiplicity_guard_passed is False

    assert (
        guard.validation_assessment_input_eligible
        is False
    )


def test_census_and_hash_are_independent_of_repository_order():
    first = issuance(
        session_id=SESSION_1,
    )

    second = issuance(
        session_id=SESSION_2,
        predictor_metric="duration_s",
    )

    third = issuance(
        session_id=SESSION_3,
        model_version="0.2.0",
    )

    a = build(
        source(
            first,
            persisted_at=dt(12),
        ),
        source(
            second,
            persisted_at=dt(13),
        ),
        source(
            third,
            persisted_at=dt(14),
        ),
    )

    b = build(
        source(
            third,
            persisted_at=dt(14),
        ),
        source(
            first,
            persisted_at=dt(12),
        ),
        source(
            second,
            persisted_at=dt(13),
        ),
    )

    assert a.family_census == b.family_census
    assert a.content_hash == b.content_hash
    assert a.guard_id == b.guard_id


class FakeAuditRepository:
    def __init__(
        self,
        records,
    ):
        self.records = tuple(records)

    async def list_for_athlete(
        self,
        *,
        athlete_id,
        artifact_kind=None,
        limit=50,
    ):
        assert athlete_id == ATHLETE

        assert (
            artifact_kind
            == AuditArtifactKind
            .PERSONAL_RESPONSE_PREDICTION_ISSUANCE
        )

        assert limit == 500

        return self.records[
            :limit
        ]


def record(
    source_value,
    *,
    persisted_at,
):
    return AuditArtifactRecord(
        artifact_kind=(
            AuditArtifactKind
            .PERSONAL_RESPONSE_PREDICTION_ISSUANCE
        ),
        artifact_id=(
            source_value.issuance_id
        ),
        athlete_id=(
            source_value.athlete_id
        ),
        schema_version=(
            source_value.schema_version
        ),
        created_at=(
            source_value.prediction_at
        ),
        content_hash_algorithm=(
            source_value.content_hash_algorithm
        ),
        content_hash=(
            source_value.content_hash
        ),
        contract_json="issuance-stub",
        persisted_at=persisted_at,
    )


@pytest.mark.asyncio
async def test_application_excludes_future_issuances_but_counts_all_current_families(
    monkeypatch,
):
    target = issuance(
        session_id=SESSION_1,
    )

    current_other = issuance(
        session_id=SESSION_2,
        predictor_metric="duration_s",
    )

    future_other = issuance(
        session_id=SESSION_3,
        response_metric="recovery_score",
    )

    repository = FakeAuditRepository(
        (
            record(
                target,
                persisted_at=dt(12),
            ),
            record(
                current_other,
                persisted_at=dt(13),
            ),
            record(
                future_other,
                persisted_at=dt(21),
            ),
        )
    )

    issuance_map = {
        target.issuance_id: target,
        current_other.issuance_id:
            current_other,
        future_other.issuance_id:
            future_other,
    }

    restored_ids = []

    def restore(record_value):
        restored_ids.append(
            record_value.artifact_id
        )

        return issuance_map[
            record_value.artifact_id
        ]

    monkeypatch.setattr(
        assembler,
        "restore_personal_response_prediction_issuance_audit_artifact",
        restore,
    )

    guard = await (
        assembler
        .assemble_prospective_validation_multiplicity_guard(
            athlete_id=ATHLETE,
            target_family_key=TARGET_FAMILY,
            as_of=dt(20),
            created_at=dt(20),
            audit_repository=repository,
        )
    )

    assert guard.family_count == 2
    assert guard.adjusted_alpha_denominator == 40

    assert future_other.issuance_id not in restored_ids


@pytest.mark.asyncio
async def test_application_scan_limit_marks_multiplicity_universe_incomplete(
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
        future_records
    )

    monkeypatch.setattr(
        assembler,
        "restore_personal_response_prediction_issuance_audit_artifact",
        lambda record_value: pytest.fail(
            "Future records must not be restored."
        ),
    )

    guard = await (
        assembler
        .assemble_prospective_validation_multiplicity_guard(
            athlete_id=ATHLETE,
            target_family_key=TARGET_FAMILY,
            as_of=dt(20),
            created_at=dt(20),
            audit_repository=repository,
        )
    )

    assert guard.audit_scan_complete is False
    assert guard.family_count == 0
    assert guard.target_family_present is False

    assert guard.anti_selection_guard_passed is False
    assert guard.multiplicity_guard_passed is False

    assert (
        guard.validation_assessment_input_eligible
        is False
    )
