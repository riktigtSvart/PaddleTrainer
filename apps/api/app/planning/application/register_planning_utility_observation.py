from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from ..domain.common.serialization import (
    canonical_json,
)
from ..domain.common.time import to_utc
from ..domain.context.models import (
    AthletePlanningContextAggregate,
)
from ..domain.decision.engine import (
    build_planner_input_envelope,
    generate_candidate_action_set,
)
from ..domain.decision.models import (
    PlannerDecisionRequest,
)
from ..domain.persistence.audit import (
    AuditArtifactKind,
    AuditArtifactRecord,
    AuditArtifactSaveStatus,
)
from ..domain.planning_utility.observation import (
    PLANNING_UTILITY_OBSERVATION_SCHEMA_V01,
    PlanningUtilityEvidenceSource,
    PlanningUtilityObservation,
    build_planning_utility_observation,
)
from ..domain.policy.builtins import (
    build_minimal_planning_policy_set,
)
from ..ports.audit import (
    PlanningAuditSession,
    SessionBoundAsyncPlanningAuditRepository,
)
from .auditable_planner_run import (
    CANDIDATE_GENERATION_VERSION,
)
from .persist_prospective_validation_evidence import (
    restore_prospective_validation_evidence_audit_artifact,
)


PLANNING_UTILITY_EVIDENCE_SCAN_LIMIT = 500


class PlanningUtilityObservationError(
    RuntimeError
):
    pass


def _require_registration_session(
    *,
    audit_repository: SessionBoundAsyncPlanningAuditRepository,
    session: PlanningAuditSession,
) -> None:
    if session is None or getattr(audit_repository, "session", None) is not session:
        raise PlanningUtilityObservationError(
            "Planning utility registration requires the repository's "
            "same transaction-owning session."
        )
    inspect_transaction = getattr(session, "in_transaction", None)
    if not callable(inspect_transaction) or inspect_transaction() is not False:
        raise PlanningUtilityObservationError(
            "Planning utility registration requires a fresh session "
            "with no existing transaction."
        )


async def _commit_registration(session: PlanningAuditSession) -> None:
    await session.commit()
    if session.in_transaction() is not False:
        raise PlanningUtilityObservationError(
            "Planning utility registration commit left an active or "
            "unknown transaction."
        )


@dataclass(frozen=True)
class DurablePlanningUtilityObservation:
    observation: PlanningUtilityObservation

    durable_registered_at: datetime

    reused_durable_observation: bool
    registration_committed: bool

    utility_assessment_established: bool
    planning_utility_supported: bool

    prescription_change_authorized: bool
    planning_authorized: bool


def _audit_record(
    observation: PlanningUtilityObservation,
) -> AuditArtifactRecord:
    return AuditArtifactRecord(
        artifact_kind=(
            AuditArtifactKind
            .PLANNING_UTILITY_OBSERVATION
        ),
        artifact_id=observation.observation_id,
        athlete_id=observation.athlete_id,
        schema_version=observation.schema_version,
        created_at=observation.created_at,
        content_hash_algorithm=(
            observation.content_hash_algorithm
        ),
        content_hash=observation.content_hash,
        contract_json=canonical_json(
            observation
        ),
    )


def _validate_stored_record(
    *,
    record: AuditArtifactRecord,
    expected: PlanningUtilityObservation,
) -> tuple[
    PlanningUtilityObservation,
    datetime,
]:
    if (
        record.artifact_kind
        != AuditArtifactKind
        .PLANNING_UTILITY_OBSERVATION
        or record.artifact_id
        != expected.observation_id
        or record.athlete_id
        != expected.athlete_id
        or record.schema_version
        != PLANNING_UTILITY_OBSERVATION_SCHEMA_V01
        or record.content_hash_algorithm
        != expected.content_hash_algorithm
        or record.content_hash
        != expected.content_hash
    ):
        raise PlanningUtilityObservationError(
            "Durable planning utility observation differs "
            "from the deterministic registration."
        )

    stored_created_at = to_utc(
        record.created_at,
        field_name="record.created_at",
    )

    stored_observation = replace(
        expected,
        created_at=stored_created_at,
    )

    if not stored_observation.verify_content_hash():
        raise PlanningUtilityObservationError(
            "Stored planning utility observation hash "
            "does not verify."
        )

    if (
        canonical_json(
            stored_observation
        )
        != record.contract_json
    ):
        raise PlanningUtilityObservationError(
            "Stored planning utility observation contract "
            "does not replay canonically."
        )

    if record.persisted_at is None:
        raise PlanningUtilityObservationError(
            "Planning utility observation has no "
            "database persistence timestamp."
        )

    durable_time = to_utc(
        record.persisted_at,
        field_name="record.persisted_at",
    )

    if durable_time < stored_observation.created_at:
        raise PlanningUtilityObservationError(
            "Planning utility observation persistence "
            "predates materialization."
        )

    if durable_time < stored_observation.requested_at:
        raise PlanningUtilityObservationError(
            "Planning utility observation persistence "
            "predates the decision-request boundary."
        )

    latest_evidence_time = max(
        ref.persisted_at
        for ref in stored_observation
        .validation_evidence_refs
    )

    if durable_time < latest_evidence_time:
        raise PlanningUtilityObservationError(
            "Planning utility observation persistence "
            "predates source evidence availability."
        )

    return (
        stored_observation,
        durable_time,
    )


async def register_planning_utility_observation(
    *,
    context: AthletePlanningContextAggregate,
    request: PlannerDecisionRequest,

    planned_run_id: str,
    planned_decision_id: str,
    planned_rationale_id: str,

    created_at: datetime,

    audit_repository: SessionBoundAsyncPlanningAuditRepository,
    session: PlanningAuditSession,

    engine_version: str = "planner_engine_v0.1",
) -> DurablePlanningUtilityObservation:
    """Durably register the complete pre-decision utility study input.

    All prospectively validated evidence durably available by
    request.requested_at is included. Caller selection is not allowed.

    No planner decision is executed here.
    The repository must be bound to this exact fresh session. This service
    owns the transaction and rolls back failures after the ownership guard.
    """

    _require_registration_session(
        audit_repository=audit_repository,
        session=session,
    )

    try:
        envelope = build_planner_input_envelope(
            context=context,
            request=request,
        )

        candidate_set = generate_candidate_action_set(
            envelope=envelope,
        )

        policy_set = build_minimal_planning_policy_set()

        records = await audit_repository.list_for_athlete(
            athlete_id=context.athlete_id,
            artifact_kind=(
                AuditArtifactKind
                .PROSPECTIVE_VALIDATION_EVIDENCE
            ),
            limit=(
                PLANNING_UTILITY_EVIDENCE_SCAN_LIMIT
            ),
        )

        if (
            len(records)
            >= PLANNING_UTILITY_EVIDENCE_SCAN_LIMIT
        ):
            raise PlanningUtilityObservationError(
                "Prospective-validation evidence scan "
                "completeness is unknown at the repository limit."
            )

        request_time = to_utc(
            request.requested_at,
            field_name="request.requested_at",
        )

        evidence_sources = []

        for record in records:
            if record.athlete_id != context.athlete_id:
                raise PlanningUtilityObservationError(
                    "Audit repository returned cross-athlete "
                    "validation evidence."
                )

            if record.persisted_at is None:
                raise PlanningUtilityObservationError(
                    "Prospective-validation evidence has no "
                    "database persistence timestamp."
                )

            persisted = to_utc(
                record.persisted_at,
                field_name="evidence_record.persisted_at",
            )

            if persisted > request_time:
                continue

            evidence = (
                restore_prospective_validation_evidence_audit_artifact(
                    record
                )
            )

            evidence_sources.append(
                PlanningUtilityEvidenceSource(
                    evidence=evidence,
                    persisted_at=persisted,
                )
            )

        observation = build_planning_utility_observation(
            athlete_id=context.athlete_id,
            context_as_of=context.as_of,

            request=request,
            envelope=envelope,
            candidate_set=candidate_set,

            candidate_generation_version=(
                CANDIDATE_GENERATION_VERSION
            ),

            policy_set_version=(
                policy_set.policy_set_version
            ),
            policy_set_content_hash=(
                policy_set.content_hash
            ),

            engine_version=engine_version,

            planned_run_id=planned_run_id,
            planned_decision_id=planned_decision_id,
            planned_rationale_id=planned_rationale_id,

            evidence_sources=tuple(
                evidence_sources
            ),
            evidence_scan_complete=True,

            created_at=created_at,
        )

        existing = await audit_repository.get(
            artifact_kind=(
                AuditArtifactKind
                .PLANNING_UTILITY_OBSERVATION
            ),
            artifact_id=observation.observation_id,
        )

        if existing is not None:
            (
                stored_observation,
                durable_time,
            ) = _validate_stored_record(
                record=existing,
                expected=observation,
            )

            await _commit_registration(session)

            return DurablePlanningUtilityObservation(
                observation=stored_observation,
                durable_registered_at=durable_time,
                reused_durable_observation=True,
                registration_committed=True,

                utility_assessment_established=False,
                planning_utility_supported=False,

                prescription_change_authorized=False,
                planning_authorized=False,
            )

        save_result = await audit_repository.save(
            _audit_record(
                observation
            )
        )

        if (
            save_result.artifact_kind
            != AuditArtifactKind
            .PLANNING_UTILITY_OBSERVATION
            or save_result.artifact_id
            != observation.observation_id
            or save_result.content_hash
            != observation.content_hash
        ):
            raise PlanningUtilityObservationError(
                "Planning utility observation save result "
                "identity mismatch."
            )

        stored = await audit_repository.get(
            artifact_kind=(
                AuditArtifactKind
                .PLANNING_UTILITY_OBSERVATION
            ),
            artifact_id=observation.observation_id,
        )

        if stored is None:
            raise PlanningUtilityObservationError(
                "Planning utility observation did not "
                "round-trip after persistence."
            )

        (
            stored_observation,
            durable_time,
        ) = _validate_stored_record(
            record=stored,
            expected=observation,
        )

        await _commit_registration(session)

        return DurablePlanningUtilityObservation(
            observation=stored_observation,
            durable_registered_at=durable_time,
            reused_durable_observation=(
                save_result.status
                == AuditArtifactSaveStatus.ALREADY_PRESENT
            ),
            registration_committed=True,

            utility_assessment_established=False,
            planning_utility_supported=False,

            prescription_change_authorized=False,
            planning_authorized=False,
        )

    except Exception:
        await session.rollback()
        raise
