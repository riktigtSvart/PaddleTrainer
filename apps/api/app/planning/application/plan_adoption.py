from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
import json
from typing import Callable
from uuid import uuid4

from ..domain.common.serialization import canonical_json
from ..domain.integration.models import ExistingWorkoutPlanCapture
from ..domain.integration.polar_reconciliation import (
    FutureBaselineAdoptionSupport,
    PolarReconciliationStatus,
    PolarSourceReconciliationArtifact,
)
from ..domain.plan_revision.reconciliation_audit import (
    PolarReconciliationAuditRecord,
    finalize_polar_reconciliation_audit,
)
from ..domain.plan_revision.persistence_contract import (
    AdoptionSourceRef,
    AuthoritativePlanConflictError,
    AuthoritativePlanIdentity,
    AuthoritativePlanRevision,
    CurrentStateAdoptionBinding,
    OccurrenceLineageKind,
    PlanHistoryClaim,
    PlanRevisionOrigin,
    RevisionOccurrence,
    finalize_authoritative_plan_revision,
    finalize_current_state_adoption_binding,
)
from ..ports.authoritative_plan_revision import AuthoritativePlanRevisionRepository
from ..ports.reconciliation_audit import PlanReconciliationAuditRepository


class PlanAdoptionStatus(StrEnum):
    READY = "ready"
    ALREADY_ADOPTED = "already_adopted"
    NOT_ELIGIBLE = "not_eligible"
    ADOPTED = "adopted"


class PlanAdoptionError(RuntimeError):
    pass


class PlanAdoptionStalePreviewError(PlanAdoptionError):
    pass


class PlanAdoptionNotEligibleError(PlanAdoptionError):
    def __init__(self, blockers: tuple[str, ...]):
        super().__init__("Plan is not eligible for current-state baseline adoption.")
        self.blockers = blockers


class PlanAlreadyAdoptedError(PlanAdoptionError):
    pass


@dataclass(frozen=True)
class PlanAdoptionPreview:
    status: PlanAdoptionStatus
    logical_plan_id: str
    athlete_id: str
    source_workout_id: str
    source_kind: str
    source_content_sha256: str
    capture_id: str
    capture_content_hash: str
    source_read_content_hash: str
    external_contract_plan_id: str
    external_contract_plan_revision: int
    external_occurrence_count: int
    history_claim: PlanHistoryClaim
    direct_external_id_promotion_allowed: bool
    baseline_adoption_allowed: bool
    external_plan_id_promoted: bool
    external_occurrence_ids_promoted: bool
    source_workout_mutated: bool
    existing_current_revision_id: str | None
    blockers: tuple[str, ...]
    polar_reconciliation_status: str | None = None
    polar_reconciliation_rules_version: str | None = None
    polar_reconciliation_content_hash: str | None = None
    polar_reconciliation_gate_satisfied: bool = False
    polar_reconciliation_audit_persistence_ready: bool = False


@dataclass(frozen=True)
class PreparedPlanAdoption:
    binding: CurrentStateAdoptionBinding
    revision: AuthoritativePlanRevision
    polar_reconciliation_audit: PolarReconciliationAuditRecord | None = None


@dataclass(frozen=True)
class PlanAdoptionResult:
    status: PlanAdoptionStatus
    identity: AuthoritativePlanIdentity
    revision: AuthoritativePlanRevision
    polar_reconciliation_audit: PolarReconciliationAuditRecord | None = None


def _validated_capture(capture: ExistingWorkoutPlanCapture) -> None:
    if not capture.verify_content_hash():
        raise ValueError("ExistingWorkoutPlanCapture content hash does not verify.")
    if not capture.verify_source_read_hash():
        raise ValueError("ExistingWorkoutPlanCapture source-read hash does not verify.")
    if capture.planning_logical_plan_id != f"planned-workout:{capture.source_workout_id}":
        raise ValueError("Unexpected logical plan binding for current app capture.")


def _polar_reconciliation_summary(
    artifact: PolarSourceReconciliationArtifact | None,
) -> dict[str, object]:
    if artifact is None:
        return {
            "polar_reconciliation_status": None,
            "polar_reconciliation_rules_version": None,
            "polar_reconciliation_content_hash": None,
            "polar_reconciliation_gate_satisfied": False,
            "polar_reconciliation_audit_persistence_ready": False,
        }
    return {
        "polar_reconciliation_status": artifact.status.value,
        "polar_reconciliation_rules_version": artifact.rules_version,
        "polar_reconciliation_content_hash": artifact.content_hash,
        "polar_reconciliation_gate_satisfied": False,
        "polar_reconciliation_audit_persistence_ready": False,
    }


def _evaluate_polar_reconciliation_gate(
    *,
    capture: ExistingWorkoutPlanCapture,
    artifact: PolarSourceReconciliationArtifact | None,
    audit_persistence_ready: bool,
) -> tuple[tuple[str, ...], dict[str, object]]:
    summary = _polar_reconciliation_summary(artifact)
    if artifact is None:
        return ("POLAR_SOURCE_RECONCILIATION_REQUIRED",), summary

    binding_matches = (
        artifact.verify_content_hash()
        and artifact.capture_id == capture.capture_id
        and artifact.logical_plan_id == capture.planning_logical_plan_id
        and artifact.athlete_id == capture.athlete_id
        and artifact.source_workout_id == capture.source_workout_id
        and artifact.source_content_sha256 == capture.source_content_sha256
        and artifact.source_read_content_hash == capture.source_read_content_hash
        and artifact.external_contract_plan_id == capture.external_contract_plan_id
        and artifact.external_contract_plan_revision
        == capture.external_contract_plan_revision
    )
    if not binding_matches:
        return ("POLAR_SOURCE_RECONCILIATION_INVALID_OR_STALE",), summary

    supported = (
        artifact.status == PolarReconciliationStatus.SYNC_PROJECTION_MATCH
        and artifact.future_baseline_adoption_support
        == FutureBaselineAdoptionSupport.SUPPORTED_BY_RECONCILIATION
        and artifact.current_orm_edit_detected is False
        and artifact.provider_snapshot_selected_as_future_authority_candidate is True
        and not artifact.blockers
    )
    if supported:
        summary["polar_reconciliation_gate_satisfied"] = True
        summary["polar_reconciliation_audit_persistence_ready"] = (
            audit_persistence_ready
        )
        if audit_persistence_ready:
            return (), summary
        return ("POLAR_RECONCILIATION_AUDIT_PERSISTENCE_REQUIRED",), summary

    if (
        artifact.status
        == PolarReconciliationStatus.MATERIAL_DIFFERENCE_REQUIRES_CLARIFICATION
        or artifact.future_baseline_adoption_support
        == FutureBaselineAdoptionSupport.CLARIFICATION_REQUIRED
    ):
        return (
            "POLAR_SOURCE_RECONCILIATION_CLARIFICATION_REQUIRED",
            *artifact.blockers,
        ), summary

    return (
        "POLAR_SOURCE_RECONCILIATION_NOT_SUPPORTED",
        *artifact.blockers,
    ), summary


def evaluate_current_state_adoption(
    *,
    capture: ExistingWorkoutPlanCapture,
    existing_plan: AuthoritativePlanIdentity | None,
    polar_reconciliation: PolarSourceReconciliationArtifact | None = None,
    polar_reconciliation_audit_persistence_ready: bool = False,
) -> PlanAdoptionPreview:
    """Evaluate whether a current application plan can become revision 1.

    This is not promotion of the capture-scoped DRAFT1 plan/occurrence IDs.
    Adoption establishes a new planning-owned authority window beginning now,
    while retaining the external capture only as provenance.
    """
    _validated_capture(capture)
    blockers: list[str] = []

    if existing_plan is not None:
        if existing_plan.logical_plan_id != capture.planning_logical_plan_id:
            blockers.append("LOGICAL_PLAN_ID_CONFLICT")
        if existing_plan.athlete_id != capture.athlete_id:
            blockers.append("ATHLETE_BINDING_CONFLICT")
        if (
            existing_plan.source_workout_id is not None
            and existing_plan.source_workout_id != capture.source_workout_id
        ):
            blockers.append("SOURCE_WORKOUT_BINDING_CONFLICT")
        if blockers:
            return PlanAdoptionPreview(
                status=PlanAdoptionStatus.NOT_ELIGIBLE,
                logical_plan_id=capture.planning_logical_plan_id,
                athlete_id=capture.athlete_id,
                source_workout_id=capture.source_workout_id,
                source_kind=capture.source_kind,
                source_content_sha256=capture.source_content_sha256,
                capture_id=capture.capture_id,
                capture_content_hash=capture.content_hash,
                source_read_content_hash=capture.source_read_content_hash,
                external_contract_plan_id=capture.external_contract_plan_id,
                external_contract_plan_revision=capture.external_contract_plan_revision,
                external_occurrence_count=len(capture.external_occurrence_ids),
                history_claim=PlanHistoryClaim.CURRENT_STATE_BASELINE_ONLY,
                direct_external_id_promotion_allowed=False,
                baseline_adoption_allowed=False,
                external_plan_id_promoted=False,
                external_occurrence_ids_promoted=False,
                source_workout_mutated=False,
                existing_current_revision_id=existing_plan.current_revision_id,
                blockers=tuple(blockers),
            )
        if existing_plan.current_revision_id is not None:
            return PlanAdoptionPreview(
                status=PlanAdoptionStatus.ALREADY_ADOPTED,
                logical_plan_id=capture.planning_logical_plan_id,
                athlete_id=capture.athlete_id,
                source_workout_id=capture.source_workout_id,
                source_kind=capture.source_kind,
                source_content_sha256=capture.source_content_sha256,
                capture_id=capture.capture_id,
                capture_content_hash=capture.content_hash,
                source_read_content_hash=capture.source_read_content_hash,
                external_contract_plan_id=capture.external_contract_plan_id,
                external_contract_plan_revision=capture.external_contract_plan_revision,
                external_occurrence_count=len(capture.external_occurrence_ids),
                history_claim=PlanHistoryClaim.CURRENT_STATE_BASELINE_ONLY,
                direct_external_id_promotion_allowed=False,
                baseline_adoption_allowed=False,
                external_plan_id_promoted=False,
                external_occurrence_ids_promoted=False,
                source_workout_mutated=False,
                existing_current_revision_id=existing_plan.current_revision_id,
                blockers=("LOGICAL_PLAN_ALREADY_HAS_AUTHORITATIVE_REVISION",),
            )

    if not capture.external_occurrence_ids:
        blockers.append("CAPTURE_HAS_NO_EXPANDED_OCCURRENCES")

    reconciliation_summary = _polar_reconciliation_summary(None)
    if capture.source_kind == "STORED_POLAR_TARGET":
        polar_blockers, reconciliation_summary = _evaluate_polar_reconciliation_gate(
            capture=capture,
            artifact=polar_reconciliation,
            audit_persistence_ready=polar_reconciliation_audit_persistence_ready,
        )
        blockers.extend(polar_blockers)
    elif capture.provider_orm_basic_field_differences:
        blockers.append("PROVIDER_ORM_VIEW_CONFLICT_REQUIRES_RECONCILIATION")

    status = PlanAdoptionStatus.NOT_ELIGIBLE if blockers else PlanAdoptionStatus.READY
    return PlanAdoptionPreview(
        status=status,
        logical_plan_id=capture.planning_logical_plan_id,
        athlete_id=capture.athlete_id,
        source_workout_id=capture.source_workout_id,
        source_kind=capture.source_kind,
        source_content_sha256=capture.source_content_sha256,
        capture_id=capture.capture_id,
        capture_content_hash=capture.content_hash,
        source_read_content_hash=capture.source_read_content_hash,
        external_contract_plan_id=capture.external_contract_plan_id,
        external_contract_plan_revision=capture.external_contract_plan_revision,
        external_occurrence_count=len(capture.external_occurrence_ids),
        history_claim=PlanHistoryClaim.CURRENT_STATE_BASELINE_ONLY,
        direct_external_id_promotion_allowed=False,
        baseline_adoption_allowed=not blockers,
        external_plan_id_promoted=False,
        external_occurrence_ids_promoted=False,
        source_workout_mutated=False,
        existing_current_revision_id=(
            None if existing_plan is None else existing_plan.current_revision_id
        ),
        blockers=tuple(blockers),
        **reconciliation_summary,
    )


def _external_plan_contract_json(capture: ExistingWorkoutPlanCapture) -> str:
    source = json.loads(capture.source_read_json)
    try:
        plan = source["adapter_result"]["plan"]
    except (KeyError, TypeError) as exc:
        raise ValueError("Capture does not contain adapter_result.plan.") from exc
    return canonical_json(plan)


def prepare_current_state_adoption(
    *,
    capture: ExistingWorkoutPlanCapture,
    authority_established_at: datetime,
    existing_plan: AuthoritativePlanIdentity | None = None,
    polar_reconciliation: PolarSourceReconciliationArtifact | None = None,
    polar_reconciliation_audit_persistence_ready: bool = False,
    id_factory: Callable[[], object] = uuid4,
) -> PreparedPlanAdoption:
    preview = evaluate_current_state_adoption(
        capture=capture,
        existing_plan=existing_plan,
        polar_reconciliation=polar_reconciliation,
        polar_reconciliation_audit_persistence_ready=(
            polar_reconciliation_audit_persistence_ready
        ),
    )
    if preview.status == PlanAdoptionStatus.ALREADY_ADOPTED:
        raise PlanAlreadyAdoptedError("Logical plan is already authoritative.")
    if preview.status != PlanAdoptionStatus.READY:
        raise PlanAdoptionNotEligibleError(preview.blockers)

    established = authority_established_at
    if established.tzinfo is None or established.utcoffset() is None:
        raise ValueError("authority_established_at must be offset-aware.")
    established = established.astimezone(timezone.utc)

    revision_id = f"pt-plan-rev:{id_factory()}"
    occurrences = tuple(
        RevisionOccurrence(
            occurrence_id=f"pt-occ:{id_factory()}",
            ordinal=ordinal,
            lineage_kind=OccurrenceLineageKind.NEW,
            source_capture_occurrence_id=external_id,
        )
        for ordinal, external_id in enumerate(capture.external_occurrence_ids)
    )

    source_ref = AdoptionSourceRef(
        capture_id=capture.capture_id,
        capture_content_hash=capture.content_hash,
        source_read_content_hash=capture.source_read_content_hash,
        source_content_sha256=capture.source_content_sha256,
        external_contract_plan_id=capture.external_contract_plan_id,
        external_contract_plan_revision=capture.external_contract_plan_revision,
    )
    revision = finalize_authoritative_plan_revision(
        revision_id=revision_id,
        logical_plan_id=capture.planning_logical_plan_id,
        athlete_id=capture.athlete_id,
        revision_number=1,
        previous_revision_id=None,
        origin=PlanRevisionOrigin.ADOPTED_CURRENT_STATE,
        history_claim=PlanHistoryClaim.CURRENT_STATE_BASELINE_ONLY,
        authority_established_at=established,
        effective_from=established,
        created_at=established,
        contract_schema_version=capture.external_contract_schema_version,
        contract_json=_external_plan_contract_json(capture),
        occurrences=occurrences,
        adoption_source=source_ref,
        decision_lineage=None,
    )
    binding = finalize_current_state_adoption_binding(
        logical_plan_id=capture.planning_logical_plan_id,
        source_workout_id=capture.source_workout_id,
        expected_source_content_sha256=capture.source_content_sha256,
        adopted_revision_id=revision.revision_id,
        authority_established_at=established,
    )
    reconciliation_audit = None
    if capture.source_kind == "STORED_POLAR_TARGET":
        if polar_reconciliation is None:
            raise PlanAdoptionNotEligibleError(("POLAR_SOURCE_RECONCILIATION_REQUIRED",))
        reconciliation_audit = finalize_polar_reconciliation_audit(
            binding=binding,
            revision=revision,
            artifact=polar_reconciliation,
            created_at=established,
        )
    return PreparedPlanAdoption(
        binding=binding,
        revision=revision,
        polar_reconciliation_audit=reconciliation_audit,
    )


async def preview_with_repository(
    *,
    capture: ExistingWorkoutPlanCapture,
    repository: AuthoritativePlanRevisionRepository,
    polar_reconciliation: PolarSourceReconciliationArtifact | None = None,
    polar_reconciliation_audit_persistence_ready: bool = False,
) -> PlanAdoptionPreview:
    existing = await repository.get_plan(
        logical_plan_id=capture.planning_logical_plan_id,
    )
    return evaluate_current_state_adoption(
        capture=capture,
        existing_plan=existing,
        polar_reconciliation=polar_reconciliation,
        polar_reconciliation_audit_persistence_ready=(
            polar_reconciliation_audit_persistence_ready
        ),
    )


async def adopt_with_repository(
    *,
    capture: ExistingWorkoutPlanCapture,
    expected_source_content_sha256: str,
    repository: AuthoritativePlanRevisionRepository,
    session,
    authority_established_at: datetime | None = None,
    polar_reconciliation: PolarSourceReconciliationArtifact | None = None,
    reconciliation_audit_repository: PlanReconciliationAuditRepository | None = None,
    id_factory: Callable[[], object] = uuid4,
) -> PlanAdoptionResult:
    """Explicitly adopt one current source plan and commit the transaction.

    The caller must have obtained an explicit user/API request. This function
    never bulk-adopts and never treats a read capture as authority by itself.
    """
    if capture.source_content_sha256 != expected_source_content_sha256:
        raise PlanAdoptionStalePreviewError(
            "Current source hash differs from the explicitly acknowledged preview."
        )

    existing = await repository.get_plan(
        logical_plan_id=capture.planning_logical_plan_id,
    )
    prepared = prepare_current_state_adoption(
        capture=capture,
        authority_established_at=(
            authority_established_at or datetime.now(timezone.utc)
        ),
        existing_plan=existing,
        polar_reconciliation=polar_reconciliation,
        polar_reconciliation_audit_persistence_ready=(
            reconciliation_audit_repository is not None
        ),
        id_factory=id_factory,
    )

    try:
        identity = await repository.adopt_current_state(
            binding=prepared.binding,
            revision=prepared.revision,
        )
        if prepared.polar_reconciliation_audit is not None:
            if reconciliation_audit_repository is None:
                raise PlanAdoptionNotEligibleError(
                    ("POLAR_RECONCILIATION_AUDIT_PERSISTENCE_REQUIRED",)
                )
            await reconciliation_audit_repository.persist_polar_audit(
                record=prepared.polar_reconciliation_audit,
            )
        await session.commit()
    except Exception:
        await session.rollback()
        raise

    return PlanAdoptionResult(
        status=PlanAdoptionStatus.ADOPTED,
        identity=identity,
        revision=prepared.revision,
        polar_reconciliation_audit=prepared.polar_reconciliation_audit,
    )


__all__ = [
    "PlanAdoptionStatus",
    "PlanAdoptionError",
    "PlanAdoptionStalePreviewError",
    "PlanAdoptionNotEligibleError",
    "PlanAlreadyAdoptedError",
    "PlanAdoptionPreview",
    "PreparedPlanAdoption",
    "PlanAdoptionResult",
    "evaluate_current_state_adoption",
    "prepare_current_state_adoption",
    "preview_with_repository",
    "adopt_with_repository",
    "AuthoritativePlanConflictError",
]
