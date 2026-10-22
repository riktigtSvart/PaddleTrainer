"""Freeze a complete descriptive execution/response census for one decision.

No source IDs, response timing or metrics can be selected by the caller.
Sources are read from committed immutable repositories; this service never
executes the planner, applies a plan, recaptures mutable source data or scores
utility. Historical plan content at execution remains unverified.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Protocol

from ..domain.common.enums import KnowledgeStatus
from ..domain.common.serialization import CONTENT_HASH_ALGORITHM, canonical_json
from ..domain.common.time import to_utc
from ..domain.context.models import AthletePlanningContextAggregate
from ..domain.decision.models import (
    PlannerActionType,
    PlannerDecisionRequest,
    PlannerDecisionStatus,
)
from ..domain.persistence.audit import AuditArtifactKind, AuditArtifactSaveStatus
from ..domain.plan_revision.models import PlanMutationInstruction
from ..domain.planning_utility.decision_binding import restore_utility_contract
from ..domain.planning_utility.followup import (
    FOLLOWUP_SOURCE_KINDS,
    PlanningUtilityExecutionObservation,
    PlanningUtilityFollowup,
    PlanningUtilityFollowupSourceReference,
    PlanningUtilityResponseAvailability,
    PlanningUtilityResponseObservation,
    PlanningUtilityRevisionReference,
    build_planning_utility_followup,
    planning_utility_followup_id,
)
from ..ports.audit import PlanningAuditSession, SessionBoundAsyncPlanningAuditRepository
from ..ports.authoritative_plan_revision import AuthoritativePlanRevisionRepository
from .apply_plan_revision import prepare_authoritative_plan_revision
from .audited_plan_mutation import load_audited_plan_mutation_instruction
from .bind_planning_utility_decision import (
    _check_record,
    load_planning_utility_decision,
)
from .ingest_authoritative_executed_training import (
    restore_authoritative_executed_training_audit_artifact,
)
from .ingest_authoritative_training_response import (
    restore_authoritative_training_response_audit_artifact,
)
from .persist_audit import _record
from .plan_mutation import build_plan_mutation_instruction
from .register_planning_utility_observation import _require_registration_session

PLANNING_UTILITY_FOLLOWUP_SCAN_LIMIT = 500


class SessionBoundPlanRevisionRepository(AuthoritativePlanRevisionRepository, Protocol):
    @property
    def session(self) -> PlanningAuditSession: ...


class PlanningUtilityFollowupError(RuntimeError):
    pass


class PlanningUtilityFollowupCompletenessUnknown(PlanningUtilityFollowupError):
    pass


class PlanningUtilityFollowupNotFound(LookupError):
    pass


@dataclass(frozen=True)
class DurablePlanningUtilityFollowup:
    followup: PlanningUtilityFollowup
    durable_available_at: datetime
    reused_durable_followup: bool
    followup_committed: bool
    utility_assessment_established: bool = False
    planning_utility_supported: bool = False
    prescription_change_authorized: bool = False
    planning_authorized: bool = False


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _require_sources_session(*, audit_repository, revision_repository, session):
    _require_registration_session(audit_repository=audit_repository, session=session)
    if getattr(revision_repository, "session", None) is not session:
        raise PlanningUtilityFollowupError(
            "Follow-up repositories must share the exact fresh session."
        )


def _audit_record(followup):
    return _record(
        artifact_kind=AuditArtifactKind.PLANNING_UTILITY_FOLLOWUP,
        artifact_id=followup.followup_id,
        athlete_id=followup.athlete_id,
        schema_version=followup.schema_version,
        created_at=followup.created_at,
        artifact=followup,
    )


def _reference(record):
    return PlanningUtilityFollowupSourceReference(
        record.artifact_kind,
        record.artifact_id,
        record.schema_version,
        record.content_hash,
        sha256(record.contract_json.encode("utf-8")).hexdigest(),
        record.persisted_at,
    )


async def _source_records(*, athlete_id, as_of, audit_repository, frozen):
    records = []
    if frozen is None:
        for kind in FOLLOWUP_SOURCE_KINDS:
            found = await audit_repository.list_for_athlete(
                athlete_id=athlete_id,
                artifact_kind=kind,
                limit=PLANNING_UTILITY_FOLLOWUP_SCAN_LIMIT,
            )
            if len(found) >= PLANNING_UTILITY_FOLLOWUP_SCAN_LIMIT:
                raise PlanningUtilityFollowupCompletenessUnknown(
                    "Follow-up source census completeness is unknown at the repository limit."
                )
            for record in found:
                if record.artifact_kind != kind or record.athlete_id != athlete_id:
                    raise PlanningUtilityFollowupError("Follow-up source census identity differs.")
                if record.persisted_at is None:
                    raise PlanningUtilityFollowupCompletenessUnknown(
                        "Follow-up source has no database persistence timestamp."
                    )
                if to_utc(record.persisted_at, field_name="source.persisted_at") <= as_of:
                    records.append(record)
    else:
        for ref in frozen.census_sources:
            if ref.artifact_kind not in FOLLOWUP_SOURCE_KINDS:
                raise PlanningUtilityFollowupError("Unexpected frozen source kind.")
            record = await audit_repository.get(
                artifact_kind=ref.artifact_kind, artifact_id=ref.artifact_id
            )
            if record is None or record.athlete_id != athlete_id or _reference(record) != ref:
                raise PlanningUtilityFollowupError("Frozen follow-up source is missing or changed.")
            records.append(record)
    keys = [(record.artifact_kind, record.artifact_id) for record in records]
    if len(keys) != len(set(keys)):
        raise PlanningUtilityFollowupError("Follow-up source census contains duplicate identities.")
    return tuple(
        sorted(records, key=lambda record: (record.artifact_kind.value, record.artifact_id))
    )


async def _materialize(
    *, decision, as_of, created_at, audit_repository, revision_repository, frozen
):
    binding = decision.binding
    records = await _source_records(
        athlete_id=binding.athlete_id, as_of=as_of, audit_repository=audit_repository, frozen=frozen
    )
    executions, responses, instructions = {}, [], {}
    sessions = set()
    for record in records:
        if record.artifact_kind == AuditArtifactKind.AUTHORITATIVE_EXECUTED_TRAINING:
            artifact = restore_authoritative_executed_training_audit_artifact(record)
            if artifact.workout_session_id in sessions:
                raise PlanningUtilityFollowupError(
                    "More than one execution source claims the same session."
                )
            sessions.add(artifact.workout_session_id)
            executions[artifact.artifact_id] = (artifact, _reference(record))
        elif record.artifact_kind == AuditArtifactKind.AUTHORITATIVE_TRAINING_RESPONSE:
            artifact = restore_authoritative_training_response_audit_artifact(record)
            responses.append((artifact, _reference(record)))
        else:
            decoded = restore_utility_contract(record.contract_json, PlanMutationInstruction)
            artifact = await load_audited_plan_mutation_instruction(
                instruction_id=record.artifact_id,
                expected_athlete_id=binding.athlete_id,
                expected_plan_id=decoded.plan_id,
                audit_repository=audit_repository,
            )
            instructions.setdefault(artifact.content_hash, []).append(
                (artifact, _reference(record))
            )
        identity = (
            artifact.instruction_id
            if isinstance(artifact, PlanMutationInstruction)
            else artifact.artifact_id
        )
        if artifact.content_hash_algorithm != CONTENT_HASH_ALGORITHM:
            raise PlanningUtilityFollowupError("Unsupported follow-up source hash algorithm.")
        schema = (
            "plan_mutation_instruction_v0.1"
            if isinstance(artifact, PlanMutationInstruction)
            else artifact.schema_version
        )
        _check_record(
            record,
            _record(
                artifact_kind=record.artifact_kind,
                artifact_id=identity,
                athlete_id=binding.athlete_id,
                schema_version=schema,
                created_at=artifact.created_at,
                artifact=artifact,
            ),
        )
        if artifact.created_at > as_of:
            raise PlanningUtilityFollowupError("Follow-up source materialization exceeds cutoff.")

    revision_cache, unavailable = {}, set()
    frozen_revisions = (
        {} if frozen is None else {ref.revision_id: ref for ref in frozen.revision_sources}
    )
    frozen_missing = set() if frozen is None else set(frozen.unavailable_revision_ids)

    async def revision(identity, *, optional=False):
        if identity in revision_cache:
            if revision_cache[identity] is None and not optional:
                raise PlanningUtilityFollowupCompletenessUnknown(
                    "Observed revision source is unavailable."
                )
            return revision_cache[identity]
        if frozen is not None and identity in frozen_missing:
            value = None
        else:
            if frozen is not None and identity not in frozen_revisions:
                raise PlanningUtilityFollowupError(
                    "Revision dependency is outside the frozen snapshot."
                )
            value = await revision_repository.get_revision(revision_id=identity)
        if value is None:
            if not optional:
                raise PlanningUtilityFollowupCompletenessUnknown(
                    "An observed revision is unavailable; execution census membership is unknown."
                )
            unavailable.add(identity)
        else:
            if (
                value.revision_id != identity
                or value.athlete_id != binding.athlete_id
                or value.content_hash_algorithm != CONTENT_HASH_ALGORITHM
                or not value.verify_content_hash()
                or not value.verify_contract_hash()
                or value.created_at > as_of
            ):
                raise PlanningUtilityFollowupError(
                    "Authoritative revision identity, hash or chronology differs."
                )
            if frozen is not None and frozen_revisions[identity].content_hash != value.content_hash:
                raise PlanningUtilityFollowupError("Frozen revision content changed.")
        revision_cache[identity] = value
        return value

    response_groups = {}
    response_ids = set()
    for response, ref in responses:
        pair = executions.get(response.executed_training_evidence_id)
        if pair is None:
            raise PlanningUtilityFollowupCompletenessUnknown(
                "A response execution source is absent from the cutoff-safe census."
            )
        executed, _ = pair
        if (
            response.workout_session_id != executed.workout_session_id
            or response.executed_training_evidence_hash != executed.content_hash
            or response.observed_at < executed.observed_at
            or response.available_at < executed.created_at
            or ref.persisted_at < pair[1].persisted_at
        ):
            raise PlanningUtilityFollowupError(
                "Response does not exactly bind its execution and chronology."
            )
        if response.source_record_id in response_ids:
            raise PlanningUtilityFollowupError("Response source identity is duplicated.")
        response_ids.add(response.source_record_id)
        response_groups.setdefault(executed.artifact_id, []).append(
            PlanningUtilityResponseObservation(
                source=ref,
                response_kind=response.response_kind,
                response_timing=response.response_timing,
                observed_at=response.observed_at,
                available_at=response.available_at,
                known_measurement_count=sum(
                    item.knowledge_status == KnowledgeStatus.KNOWN for item in response.measurements
                ),
                non_known_measurement_count=sum(
                    item.knowledge_status != KnowledgeStatus.KNOWN for item in response.measurements
                ),
            )
        )

    rows, unrelated_executions, unrelated_responses = [], [], []
    actual = decision.planner_run
    can_mutate = (
        actual.decision.status
        in (PlannerDecisionStatus.DECIDED, PlannerDecisionStatus.DECIDED_WITH_CONSTRAINTS)
        and actual.decision.selected_action is not None
        and actual.decision.selected_action.action_type == PlannerActionType.SELECT_WORKOUT_FAMILY
        and actual.decision.selected_action.plan_mutation_authorized is True
    )
    for executed, ref in executions.values():
        observed = await revision(executed.observed_revision_id)
        if (
            observed.content_hash != executed.observed_revision_content_hash
            or observed.logical_plan_id != executed.logical_plan_id
            or observed.created_at > executed.created_at
            or executed.created_at < executed.observed_at
        ):
            raise PlanningUtilityFollowupError(
                "Execution does not hash-bind its frozen observed revision."
            )
        lineage = observed.decision_lineage
        related = (
            lineage is not None
            and lineage.context_hash == binding.context_hash
            and lineage.decision_hash == actual.decision.content_hash
            and lineage.rationale_hash == actual.rationale.content_hash
        )
        row_responses = tuple(
            sorted(
                response_groups.get(executed.artifact_id, ()),
                key=lambda item: (item.observed_at, item.available_at, item.source.artifact_id),
            )
        )
        if not related:
            unrelated_executions.append(executed.artifact_id)
            unrelated_responses.extend(item.source.artifact_id for item in row_responses)
            continue
        blockers = []
        if not can_mutate:
            blockers.append("DECISION_DOES_NOT_AUTHORIZE_NEW_REVISION")
        if executed.observed_at <= binding.decision_time:
            blockers.append("EXECUTION_NOT_AFTER_DECISION")
        if executed.observed_at < max(observed.created_at, observed.effective_from):
            blockers.append("EXECUTION_BEFORE_REVISION_AUTHORITY")
        candidates = instructions.get(lineage.instruction_hash, ())
        instruction_ref = None
        if len(candidates) != 1:
            blockers.append(
                "AUDITED_INSTRUCTION_MISSING"
                if not candidates
                else "AUDITED_INSTRUCTION_IDENTITY_AMBIGUOUS"
            )
        else:
            instruction, instruction_ref = candidates[0]
            if instruction.created_at < binding.decision_time:
                blockers.append("INSTRUCTION_PREDATES_DECISION")
            previous = (
                None
                if observed.previous_revision_id is None
                else await revision(observed.previous_revision_id, optional=True)
            )
            if previous is None:
                blockers.append("PREVIOUS_REVISION_UNAVAILABLE")
            if can_mutate and previous is not None:
                expected_instruction = build_plan_mutation_instruction(
                    instruction_id=instruction.instruction_id,
                    decision=actual.decision,
                    rationale=actual.rationale,
                    operation=instruction.operation,
                    plan_id=instruction.plan_id,
                    expected_current_revision_id=instruction.expected_current_revision_id,
                    new_plan_artifact=instruction.new_plan_artifact,
                    effective_from=instruction.effective_from,
                    created_at=instruction.created_at,
                )
                expected_revision = prepare_authoritative_plan_revision(
                    current_revision=previous,
                    instruction=expected_instruction,
                    revision_id=observed.revision_id,
                )
                if canonical_json(expected_instruction) != canonical_json(
                    instruction
                ) or canonical_json(expected_revision) != canonical_json(observed):
                    raise PlanningUtilityFollowupError(
                        "Decision/instruction/revision replay differs."
                    )
        rows.append(
            PlanningUtilityExecutionObservation(
                source=ref,
                workout_session_id=executed.workout_session_id,
                logical_plan_id=executed.logical_plan_id,
                observed_revision_id=observed.revision_id,
                observed_revision_content_hash=observed.content_hash,
                plan_execution_link_id=executed.plan_execution_link_id,
                plan_execution_link_content_hash=executed.plan_execution_link_content_hash,
                instruction_source=instruction_ref,
                observed_at=executed.observed_at,
                modality_key=executed.modality_key,
                duration_status=executed.duration_status,
                duration_s=executed.duration_s,
                decision_execution_lineage_established=not blockers,
                lineage_blockers=tuple(blockers),
                plan_content_at_execution_status="unverified",
                response_availability=(
                    PlanningUtilityResponseAvailability.SOURCE_AVAILABLE
                    if row_responses
                    else PlanningUtilityResponseAvailability.NO_SOURCE_AVAILABLE_AS_OF
                ),
                responses=row_responses,
            )
        )
    return build_planning_utility_followup(
        binding=binding,
        binding_persisted_at=decision.durable_bound_at,
        as_of=as_of,
        census_sources=tuple(_reference(record) for record in records),
        revision_sources=tuple(
            PlanningUtilityRevisionReference(item.revision_id, item.content_hash)
            for item in revision_cache.values()
            if item is not None
        ),
        unavailable_revision_ids=tuple(unavailable),
        unrelated_execution_source_ids=tuple(unrelated_executions),
        unrelated_response_source_ids=tuple(unrelated_responses),
        executions=tuple(rows),
        source_census_complete=True,
        created_at=created_at,
    )


async def _followup_workflow(
    *, context, request, as_of, audit_repository, revision_repository, session, read_only
):
    _require_sources_session(
        audit_repository=audit_repository, revision_repository=revision_repository, session=session
    )
    cutoff = to_utc(as_of, field_name="as_of")
    if cutoff > to_utc(_utc_now(), field_name="now"):
        raise ValueError("Follow-up cutoff cannot be in the future.")
    # The B1 read workflow verifies all original inputs and closes its owned
    # read transaction before this service starts its own census transaction.
    decision = await load_planning_utility_decision(
        context=context, request=request, audit_repository=audit_repository, session=session
    )
    try:
        identity = planning_utility_followup_id(
            decision_binding_id=decision.binding.binding_id, as_of=cutoff
        )
        existing = await audit_repository.get(
            artifact_kind=AuditArtifactKind.PLANNING_UTILITY_FOLLOWUP, artifact_id=identity
        )
        if existing is None and read_only:
            raise PlanningUtilityFollowupNotFound(
                "No durable follow-up exists for this decision and cutoff."
            )
        frozen = (
            None
            if existing is None
            else restore_utility_contract(existing.contract_json, PlanningUtilityFollowup)
        )
        followup = await _materialize(
            decision=decision,
            as_of=cutoff,
            created_at=(_utc_now() if existing is None else existing.created_at),
            audit_repository=audit_repository,
            revision_repository=revision_repository,
            frozen=frozen,
        )
        expected = _audit_record(followup)
        if read_only:
            persisted = _check_record(existing, expected)
            await session.rollback()
        else:
            result = await audit_repository.save(expected)
            if (
                result.status
                not in (AuditArtifactSaveStatus.CREATED, AuditArtifactSaveStatus.ALREADY_PRESENT)
                or result.artifact_kind != expected.artifact_kind
                or result.artifact_id != expected.artifact_id
                or result.content_hash != expected.content_hash
            ):
                raise PlanningUtilityFollowupError("Follow-up save receipt differs.")
            stored = await audit_repository.get(
                artifact_kind=expected.artifact_kind, artifact_id=expected.artifact_id
            )
            persisted = _check_record(stored, expected)
            await session.commit()
            if session.in_transaction() is not False:
                raise PlanningUtilityFollowupError(
                    "Follow-up commit left an active or unknown transaction."
                )
        return DurablePlanningUtilityFollowup(
            followup=followup,
            durable_available_at=persisted,
            reused_durable_followup=existing is not None,
            followup_committed=True,
        )
    except Exception:
        await session.rollback()
        raise


async def bind_planning_utility_followup(
    *,
    context: AthletePlanningContextAggregate,
    request: PlannerDecisionRequest,
    as_of: datetime,
    audit_repository: SessionBoundAsyncPlanningAuditRepository,
    revision_repository: SessionBoundPlanRevisionRepository,
    session: PlanningAuditSession,
) -> DurablePlanningUtilityFollowup:
    """Own a fresh transaction and commit one immutable cutoff-bound census.

    Same-decision/same-cutoff retries restore the original frozen census,
    including observed absences. Later cutoffs are separate snapshots of the
    same event, never evidence of independent trials or preregistered utility.
    """
    return await _followup_workflow(
        context=context,
        request=request,
        as_of=as_of,
        audit_repository=audit_repository,
        revision_repository=revision_repository,
        session=session,
        read_only=False,
    )


async def load_planning_utility_followup(
    *,
    context: AthletePlanningContextAggregate,
    request: PlannerDecisionRequest,
    as_of: datetime,
    audit_repository: SessionBoundAsyncPlanningAuditRepository,
    revision_repository: SessionBoundPlanRevisionRepository,
    session: PlanningAuditSession,
) -> DurablePlanningUtilityFollowup:
    """Read and revalidate exact frozen dependencies; never refresh the census."""
    return await _followup_workflow(
        context=context,
        request=request,
        as_of=as_of,
        audit_repository=audit_repository,
        revision_repository=revision_repository,
        session=session,
        read_only=True,
    )
