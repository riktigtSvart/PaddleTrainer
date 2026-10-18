from datetime import datetime, timezone
from itertools import count

import pytest

from app.planning.application.plan_adoption import (
    PlanAdoptionNotEligibleError,
    PlanAdoptionStalePreviewError,
    PlanAdoptionStatus,
    adopt_with_repository,
    evaluate_current_state_adoption,
    prepare_current_state_adoption,
)
from app.planning.domain.common.serialization import canonical_json, compute_content_hash
from app.planning.domain.integration.models import finalize_existing_workout_plan_capture
from app.planning.domain.plan_revision.persistence_contract import (
    PlanHistoryClaim,
    PlanRevisionOrigin,
    finalize_authoritative_plan_identity,
)


UTC = timezone.utc
NOW = datetime(2026, 10, 17, 16, 0, tzinfo=UTC)


def capture(*, source_kind="STORED_ORM_WORKOUT", differences=(), occurrences=("occ_external_1",)):
    plan = {
        "contract_type": "WorkoutPlanContract",
        "schema_version": "0.1",
        "plan_id": "legacy-workout:source:a01:capturehash",
        "plan_revision": 1,
        "athlete_id": "athlete-1",
        "planned_date": "2026-10-18",
        "planned_start_time": None,
        "sport": "KAYAK",
        "session_type": "UNKNOWN",
        "title": "Current source plan",
        "description": None,
        "blocks": [{"block_id": "legacy-block:block-1"}],
        "evidence": [],
    }
    source = {
        "status": "PLAN_CONTRACT_READ_WITH_LIMITATIONS",
        "adapter_result": {"plan": plan},
    }
    source_json = canonical_json(source)
    source_read_hash = compute_content_hash(source, exclude_fields=frozenset())
    return finalize_existing_workout_plan_capture(
        api_rules_version="plan-contract-read-api-0.1-draft1",
        contract_release="DRAFT1",
        capture_id="capture-1",
        captured_at=NOW,
        source_workout_id="workout-1",
        athlete_id="athlete-1",
        source_kind=source_kind,
        source_content_sha256="a" * 64,
        planning_logical_plan_id="planned-workout:workout-1",
        external_contract_plan_id=plan["plan_id"],
        external_contract_plan_revision=1,
        external_contract_schema_version="0.1",
        external_plan_content_hash="b" * 64,
        external_contract_snapshot_sha256="c" * 64,
        external_adapter_version="legacy-plan-adapter-0.1-draft1",
        contract_block_ids=("legacy-block:block-1",),
        external_occurrence_ids=tuple(occurrences),
        source_limitations=(
            "STATELESS_READ_CAPTURE_NOT_A_PERSISTED_PLAN_REVISION",
            "HISTORICAL_PLAN_CONTENT_UNVERIFIED",
        ),
        provider_orm_basic_field_differences=tuple(differences),
        source_read_json=source_json,
        source_read_content_hash=source_read_hash,
    )


def existing(*, current_revision_id="pt-plan-rev:existing"):
    return finalize_authoritative_plan_identity(
        logical_plan_id="planned-workout:workout-1",
        athlete_id="athlete-1",
        source_workout_id="workout-1",
        current_revision_id=current_revision_id,
        current_revision_number=0 if current_revision_id is None else 1,
        authority_established_at=None if current_revision_id is None else NOW,
    )


def sequential_ids():
    values = iter(["revision", "occ-1", "occ-2", "occ-3"])
    return lambda: next(values)


class FakeRepo:
    def __init__(self, plan=None):
        self.plan = plan
        self.adoptions = []

    async def get_plan(self, *, logical_plan_id):
        assert logical_plan_id == "planned-workout:workout-1"
        return self.plan

    async def adopt_current_state(self, *, binding, revision):
        self.adoptions.append((binding, revision))
        self.plan = finalize_authoritative_plan_identity(
            logical_plan_id=revision.logical_plan_id,
            athlete_id=revision.athlete_id,
            source_workout_id=binding.source_workout_id,
            current_revision_id=revision.revision_id,
            current_revision_number=revision.revision_number,
            authority_established_at=revision.authority_established_at,
        )
        return self.plan


class FakeSession:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


def test_ready_preview_makes_baseline_adoption_distinct_from_direct_promotion():
    preview = evaluate_current_state_adoption(capture=capture(), existing_plan=None)

    assert preview.status == PlanAdoptionStatus.READY
    assert preview.baseline_adoption_allowed is True
    assert preview.direct_external_id_promotion_allowed is False
    assert preview.external_plan_id_promoted is False
    assert preview.external_occurrence_ids_promoted is False
    assert preview.source_workout_mutated is False
    assert preview.history_claim == PlanHistoryClaim.CURRENT_STATE_BASELINE_ONLY
    assert preview.source_content_sha256 == "a" * 64
    assert preview.blockers == ()


def test_polar_capture_requires_reconciliation_before_authority_is_established():
    preview = evaluate_current_state_adoption(
        capture=capture(source_kind="STORED_POLAR_TARGET"),
        existing_plan=None,
    )
    assert preview.status == PlanAdoptionStatus.NOT_ELIGIBLE
    assert preview.baseline_adoption_allowed is False
    assert "POLAR_SOURCE_RECONCILIATION_REQUIRED" in preview.blockers


def test_provider_orm_difference_blocks_baseline_adoption():
    preview = evaluate_current_state_adoption(
        capture=capture(differences=("TITLE",)),
        existing_plan=None,
    )
    assert preview.status == PlanAdoptionStatus.NOT_ELIGIBLE
    assert "PROVIDER_ORM_VIEW_CONFLICT_REQUIRES_RECONCILIATION" in preview.blockers


def test_existing_authoritative_revision_is_not_silently_re_adopted():
    preview = evaluate_current_state_adoption(
        capture=capture(),
        existing_plan=existing(),
    )
    assert preview.status == PlanAdoptionStatus.ALREADY_ADOPTED
    assert preview.existing_current_revision_id == "pt-plan-rev:existing"
    assert preview.baseline_adoption_allowed is False


def test_prepare_adoption_mints_planning_owned_revision_and_occurrence_ids():
    prepared = prepare_current_state_adoption(
        capture=capture(occurrences=("external-a", "external-b")),
        authority_established_at=NOW,
        id_factory=sequential_ids(),
    )

    revision = prepared.revision
    binding = prepared.binding
    assert revision.revision_id == "pt-plan-rev:revision"
    assert revision.origin == PlanRevisionOrigin.ADOPTED_CURRENT_STATE
    assert revision.history_claim == PlanHistoryClaim.CURRENT_STATE_BASELINE_ONLY
    assert [item.occurrence_id for item in revision.occurrences] == [
        "pt-occ:occ-1",
        "pt-occ:occ-2",
    ]
    assert [item.source_capture_occurrence_id for item in revision.occurrences] == [
        "external-a",
        "external-b",
    ]
    assert revision.adoption_source.external_contract_plan_id.startswith(
        "legacy-workout:"
    )
    assert binding.external_plan_id_promoted is False
    assert binding.external_occurrence_ids_promoted is False
    assert binding.source_workout_mutated is False
    assert binding.expected_source_content_sha256 == "a" * 64


@pytest.mark.asyncio
async def test_explicit_adoption_requires_the_acknowledged_source_hash_before_write():
    repo = FakeRepo()
    session = FakeSession()
    with pytest.raises(PlanAdoptionStalePreviewError):
        await adopt_with_repository(
            capture=capture(),
            expected_source_content_sha256="9" * 64,
            repository=repo,
            session=session,
            authority_established_at=NOW,
            id_factory=sequential_ids(),
        )

    assert repo.adoptions == []
    assert session.commits == 0
    assert session.rollbacks == 0


@pytest.mark.asyncio
async def test_explicit_adoption_commits_once_after_repository_accepts_revision():
    repo = FakeRepo()
    session = FakeSession()
    result = await adopt_with_repository(
        capture=capture(),
        expected_source_content_sha256="a" * 64,
        repository=repo,
        session=session,
        authority_established_at=NOW,
        id_factory=sequential_ids(),
    )

    assert result.status == PlanAdoptionStatus.ADOPTED
    assert result.identity.current_revision_id == "pt-plan-rev:revision"
    assert result.revision.revision_number == 1
    assert len(repo.adoptions) == 1
    assert session.commits == 1
    assert session.rollbacks == 0


@pytest.mark.asyncio
async def test_not_eligible_capture_never_reaches_repository_write():
    repo = FakeRepo()
    session = FakeSession()
    with pytest.raises(PlanAdoptionNotEligibleError):
        await adopt_with_repository(
            capture=capture(source_kind="STORED_POLAR_TARGET"),
            expected_source_content_sha256="a" * 64,
            repository=repo,
            session=session,
            authority_established_at=NOW,
            id_factory=sequential_ids(),
        )
    assert repo.adoptions == []
    assert session.commits == 0


def _polar_reconciliation_for(capture_value, *, status="sync_projection_match"):
    from app.planning.domain.common.serialization import CONTENT_HASH_ALGORITHM
    from app.planning.domain.integration.polar_reconciliation import (
        FutureBaselineAdoptionSupport,
        POLAR_RECONCILIATION_HASH_EXCLUDE_FIELDS,
        PolarReconciliationStatus,
        PolarSourceReconciliationArtifact,
    )

    status_value = PolarReconciliationStatus(status)
    if status_value == PolarReconciliationStatus.SYNC_PROJECTION_MATCH:
        future_support = FutureBaselineAdoptionSupport.SUPPORTED_BY_RECONCILIATION
        current_edit = False
        provider_candidate = True
        blockers = ()
    elif status_value == PolarReconciliationStatus.MATERIAL_DIFFERENCE_REQUIRES_CLARIFICATION:
        future_support = FutureBaselineAdoptionSupport.CLARIFICATION_REQUIRED
        current_edit = True
        provider_candidate = False
        blockers = ("CURRENT_ORM_DIFFERS_FROM_STORED_POLAR_SYNC_PROJECTION",)
    else:
        future_support = FutureBaselineAdoptionSupport.NOT_SUPPORTED
        current_edit = None
        provider_candidate = False
        blockers = ("POLAR_SOURCE_UNSUPPORTED",)

    provisional = PolarSourceReconciliationArtifact(
        schema_version="0.2",
        rules_version="polar-source-reconciliation-0.2",
        capture_id=capture_value.capture_id,
        captured_at=capture_value.captured_at,
        logical_plan_id=capture_value.planning_logical_plan_id,
        athlete_id=capture_value.athlete_id,
        source_workout_id=capture_value.source_workout_id,
        source_content_sha256=capture_value.source_content_sha256,
        source_read_content_hash=capture_value.source_read_content_hash,
        external_contract_plan_id=capture_value.external_contract_plan_id,
        external_contract_plan_revision=capture_value.external_contract_plan_revision,
        timezone_context_name="Europe/Budapest",
        timezone_context_source="CURRENT_USER_PROFILE",
        status=status_value,
        future_baseline_adoption_support=future_support,
        semantic_equivalence_claimed=False,
        current_orm_edit_detected=current_edit,
        provider_snapshot_selected_as_future_authority_candidate=provider_candidate,
        adoption_gate_integrated=False,
        compared_fields=("/title",),
        differences=(),
        normalization_notes=("TEST_RECONCILIATION",),
        excluded_fields=("/status",),
        blockers=blockers,
        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash="",
    )
    digest = compute_content_hash(
        provisional,
        exclude_fields=POLAR_RECONCILIATION_HASH_EXCLUDE_FIELDS,
    )
    return PolarSourceReconciliationArtifact(
        **{**provisional.__dict__, "content_hash": digest}
    )


def test_polar_matching_reconciliation_satisfies_source_gate_but_write_stays_blocked_until_audit_persistence_exists():
    polar_capture = capture(source_kind="STORED_POLAR_TARGET")
    reconciliation = _polar_reconciliation_for(polar_capture)
    preview = evaluate_current_state_adoption(
        capture=polar_capture,
        existing_plan=None,
        polar_reconciliation=reconciliation,
    )

    assert preview.status == PlanAdoptionStatus.NOT_ELIGIBLE
    assert preview.polar_reconciliation_gate_satisfied is True
    assert preview.polar_reconciliation_status == "sync_projection_match"
    assert preview.polar_reconciliation_rules_version == "polar-source-reconciliation-0.2"
    assert preview.polar_reconciliation_content_hash == reconciliation.content_hash
    assert preview.polar_reconciliation_audit_persistence_ready is False
    assert preview.blockers == ("POLAR_RECONCILIATION_AUDIT_PERSISTENCE_REQUIRED",)
    assert "POLAR_SOURCE_RECONCILIATION_REQUIRED" not in preview.blockers
    assert preview.baseline_adoption_allowed is False


def test_polar_clarification_result_remains_fail_closed_and_does_not_reach_audit_persistence_gate():
    polar_capture = capture(source_kind="STORED_POLAR_TARGET")
    reconciliation = _polar_reconciliation_for(
        polar_capture,
        status="material_difference_requires_clarification",
    )
    preview = evaluate_current_state_adoption(
        capture=polar_capture,
        existing_plan=None,
        polar_reconciliation=reconciliation,
    )

    assert preview.polar_reconciliation_gate_satisfied is False
    assert "POLAR_SOURCE_RECONCILIATION_CLARIFICATION_REQUIRED" in preview.blockers
    assert "CURRENT_ORM_DIFFERS_FROM_STORED_POLAR_SYNC_PROJECTION" in preview.blockers
    assert "POLAR_RECONCILIATION_AUDIT_PERSISTENCE_REQUIRED" not in preview.blockers


def test_polar_reconciliation_must_bind_exactly_to_the_capture_being_adopted():
    polar_capture = capture(source_kind="STORED_POLAR_TARGET")
    reconciliation = _polar_reconciliation_for(polar_capture)
    from dataclasses import replace
    stale = replace(reconciliation, source_content_sha256="9" * 64)
    preview = evaluate_current_state_adoption(
        capture=polar_capture,
        existing_plan=None,
        polar_reconciliation=stale,
    )
    assert preview.polar_reconciliation_gate_satisfied is False
    assert preview.blockers == ("POLAR_SOURCE_RECONCILIATION_INVALID_OR_STALE",)


@pytest.mark.asyncio
async def test_polar_write_remains_disabled_even_after_successful_reconciliation_until_lineage_can_be_persisted():
    repo = FakeRepo()
    session = FakeSession()
    polar_capture = capture(source_kind="STORED_POLAR_TARGET")
    reconciliation = _polar_reconciliation_for(polar_capture)

    with pytest.raises(PlanAdoptionNotEligibleError) as exc_info:
        await adopt_with_repository(
            capture=polar_capture,
            expected_source_content_sha256="a" * 64,
            repository=repo,
            session=session,
            authority_established_at=NOW,
            polar_reconciliation=reconciliation,
            id_factory=sequential_ids(),
        )

    assert exc_info.value.blockers == ("POLAR_RECONCILIATION_AUDIT_PERSISTENCE_REQUIRED",)
    assert repo.adoptions == []
    assert session.commits == 0
