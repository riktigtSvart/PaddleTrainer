from datetime import datetime, timezone

import pytest

from app.planning.domain.plan_revision.persistence_contract import (
    AdoptionSourceRef,
    OccurrenceLineageKind,
    PlanHistoryClaim,
    PlanRevisionOrigin,
    RevisionDecisionLineage,
    RevisionOccurrence,
    finalize_authoritative_plan_identity,
    finalize_authoritative_plan_revision,
    finalize_current_state_adoption_binding,
    validate_revision_transition,
)


def dt(hour: int) -> datetime:
    return datetime(2026, 10, 17, hour, tzinfo=timezone.utc)


def source() -> AdoptionSourceRef:
    return AdoptionSourceRef(
        capture_id='capture-1',
        capture_content_hash='a' * 64,
        source_read_content_hash='b' * 64,
        source_content_sha256='c' * 64,
        external_contract_plan_id='capture-plan-1',
        external_contract_plan_revision=1,
    )


def baseline():
    return finalize_authoritative_plan_revision(
        revision_id='pt-plan-rev:r1',
        logical_plan_id='planned-workout:w1',
        athlete_id='athlete-1',
        revision_number=1,
        previous_revision_id=None,
        origin=PlanRevisionOrigin.ADOPTED_CURRENT_STATE,
        history_claim=PlanHistoryClaim.CURRENT_STATE_BASELINE_ONLY,
        authority_established_at=dt(9),
        effective_from=dt(10),
        created_at=dt(9),
        contract_schema_version='0.1',
        contract_json='{"blocks":[],"plan":"x"}',
        occurrences=(
            RevisionOccurrence(
                occurrence_id='pt-occ:o1',
                ordinal=0,
                lineage_kind=OccurrenceLineageKind.NEW,
                source_capture_occurrence_id='external-occ-1',
            ),
            RevisionOccurrence(
                occurrence_id='pt-occ:o2',
                ordinal=1,
                lineage_kind=OccurrenceLineageKind.NEW,
                source_capture_occurrence_id='external-occ-2',
            ),
        ),
        adoption_source=source(),
        decision_lineage=None,
    )


def planner_revision(*, preserved='pt-occ:o1', new='pt-occ:o3'):
    return finalize_authoritative_plan_revision(
        revision_id='pt-plan-rev:r2',
        logical_plan_id='planned-workout:w1',
        athlete_id='athlete-1',
        revision_number=2,
        previous_revision_id='pt-plan-rev:r1',
        origin=PlanRevisionOrigin.PLANNER_CREATED,
        history_claim=PlanHistoryClaim.VERIFIED_FROM_AUTHORITY_START,
        authority_established_at=dt(9),
        effective_from=dt(11),
        created_at=dt(10),
        contract_schema_version='0.1',
        contract_json='{"blocks":[],"plan":"y"}',
        occurrences=(
            RevisionOccurrence(
                occurrence_id=preserved,
                ordinal=0,
                lineage_kind=OccurrenceLineageKind.PRESERVED,
            ),
            RevisionOccurrence(
                occurrence_id=new,
                ordinal=1,
                lineage_kind=OccurrenceLineageKind.NEW,
            ),
        ),
        adoption_source=None,
        decision_lineage=RevisionDecisionLineage(
            context_hash='d' * 64,
            decision_hash='e' * 64,
            rationale_hash='f' * 64,
            instruction_hash='1' * 64,
        ),
    )


def test_unadopted_identity_has_no_revision_or_authority_time() -> None:
    identity = finalize_authoritative_plan_identity(
        logical_plan_id='planned-workout:w1',
        athlete_id='athlete-1',
        source_workout_id='w1',
        current_revision_id=None,
        current_revision_number=0,
        authority_established_at=None,
    )
    assert identity.current_revision_id is None
    assert identity.verify_content_hash()


def test_adopted_baseline_is_current_state_only_not_retroactive_history() -> None:
    revision = baseline()
    assert revision.history_claim == PlanHistoryClaim.CURRENT_STATE_BASELINE_ONLY
    assert revision.authority_established_at == dt(9)
    assert revision.verify_contract_hash()
    assert revision.verify_content_hash()


def test_adoption_cannot_promote_capture_scoped_ids() -> None:
    binding = finalize_current_state_adoption_binding(
        logical_plan_id='planned-workout:w1',
        source_workout_id='w1',
        expected_source_content_sha256='c' * 64,
        adopted_revision_id='pt-plan-rev:r1',
        authority_established_at=dt(9),
    )
    assert binding.external_plan_id_promoted is False
    assert binding.external_occurrence_ids_promoted is False
    assert binding.source_workout_mutated is False
    assert binding.verify_content_hash()


def test_adoption_occurrence_ids_must_be_planning_owned() -> None:
    with pytest.raises(ValueError, match='pt-occ'):
        RevisionOccurrence(
            occurrence_id='capture-occurrence-id',
            ordinal=0,
            lineage_kind=OccurrenceLineageKind.NEW,
            source_capture_occurrence_id='capture-occurrence-id',
        )


def test_adoption_baseline_cannot_claim_verified_history() -> None:
    with pytest.raises(ValueError, match='pre-adoption'):
        finalize_authoritative_plan_revision(
            revision_id='pt-plan-rev:r1',
            logical_plan_id='planned-workout:w1',
            athlete_id='athlete-1',
            revision_number=1,
            previous_revision_id=None,
            origin=PlanRevisionOrigin.ADOPTED_CURRENT_STATE,
            history_claim=PlanHistoryClaim.VERIFIED_FROM_AUTHORITY_START,
            authority_established_at=dt(9),
            effective_from=dt(10),
            created_at=dt(9),
            contract_schema_version='0.1',
            contract_json='{"plan":"x"}',
            occurrences=(RevisionOccurrence(
                occurrence_id='pt-occ:o1', ordinal=0,
                lineage_kind=OccurrenceLineageKind.NEW,
                source_capture_occurrence_id='external-1',
            ),),
            adoption_source=source(),
            decision_lineage=None,
        )


def test_planner_revision_requires_decision_lineage() -> None:
    with pytest.raises(ValueError, match='decision_lineage'):
        finalize_authoritative_plan_revision(
            revision_id='pt-plan-rev:r2',
            logical_plan_id='planned-workout:w1',
            athlete_id='athlete-1',
            revision_number=2,
            previous_revision_id='pt-plan-rev:r1',
            origin=PlanRevisionOrigin.PLANNER_CREATED,
            history_claim=PlanHistoryClaim.VERIFIED_FROM_AUTHORITY_START,
            authority_established_at=dt(9),
            effective_from=dt(11),
            created_at=dt(10),
            contract_schema_version='0.1',
            contract_json='{"plan":"y"}',
            occurrences=(RevisionOccurrence(
                occurrence_id='pt-occ:o1', ordinal=0,
                lineage_kind=OccurrenceLineageKind.PRESERVED,
            ),),
            adoption_source=None,
            decision_lineage=None,
        )


def test_valid_revision_transition_preserves_and_mints_occurrence_identity() -> None:
    first = baseline()
    second = planner_revision()
    validate_revision_transition(previous=first, candidate=second)
    assert second.occurrences[0].occurrence_id == 'pt-occ:o1'
    assert second.occurrences[1].occurrence_id == 'pt-occ:o3'


def test_preserved_occurrence_must_exist_in_previous_revision() -> None:
    with pytest.raises(ValueError, match='PRESERVED'):
        validate_revision_transition(
            previous=baseline(),
            candidate=planner_revision(preserved='pt-occ:missing'),
        )


def test_new_occurrence_cannot_reuse_previous_identity() -> None:
    with pytest.raises(ValueError, match='NEW occurrence'):
        validate_revision_transition(
            previous=baseline(),
            candidate=planner_revision(new='pt-occ:o2'),
        )


def test_revision_number_must_increment_exactly_one() -> None:
    second = finalize_authoritative_plan_revision(
        revision_id='pt-plan-rev:r3',
        logical_plan_id='planned-workout:w1',
        athlete_id='athlete-1',
        revision_number=3,
        previous_revision_id='pt-plan-rev:r1',
        origin=PlanRevisionOrigin.PLANNER_CREATED,
        history_claim=PlanHistoryClaim.VERIFIED_FROM_AUTHORITY_START,
        authority_established_at=dt(9),
        effective_from=dt(11),
        created_at=dt(10),
        contract_schema_version='0.1',
        contract_json='{"plan":"z"}',
        occurrences=(RevisionOccurrence(
            occurrence_id='pt-occ:o1', ordinal=0,
            lineage_kind=OccurrenceLineageKind.PRESERVED,
        ),),
        adoption_source=None,
        decision_lineage=RevisionDecisionLineage(
            context_hash='d'*64, decision_hash='e'*64,
            rationale_hash='f'*64, instruction_hash='1'*64,
        ),
    )
    with pytest.raises(ValueError, match='exactly by one'):
        validate_revision_transition(previous=baseline(), candidate=second)


def test_contract_json_is_canonicalized_before_hashing() -> None:
    first = baseline()
    assert first.canonical_contract_json == '{"blocks":[],"plan":"x"}'
