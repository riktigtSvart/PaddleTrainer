"""Durably bind an actual observed planner run without changing its runtime.

Writers accept only a trusted in-process ObservedPlannerRun receipt, never a
client-supplied/backdated decision. A separate read path verifies completed
bindings using exact source references and deterministic replay. Missing
bindings and orphan registrations never trigger a new decision.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

from ..domain.common.serialization import canonical_json, compute_content_hash
from ..domain.common.time import to_utc
from ..domain.context.models import AthletePlanningContextAggregate
from ..domain.decision.models import (
    CandidateActionSet,
    PlannerDecision,
    PlannerDecisionRequest,
    PlannerInputEnvelope,
)
from ..domain.persistence.audit import (
    AuditArtifactKind,
    AuditArtifactRecord,
    AuditArtifactSaveStatus,
)
from ..domain.planning_utility.decision_binding import (
    DECISION_BINDING_HASH_EXCLUDE_FIELDS,
    PlanningUtilityDecisionArtifactReference,
    PlanningUtilityDecisionBinding,
    build_planning_utility_decision_binding,
    planning_utility_decision_binding_id,
    restore_utility_contract,
)
from ..domain.planning_utility.observation import (
    PlanningUtilityEvidenceSource,
    PlanningUtilityObservation,
    build_planning_utility_observation,
    planning_utility_observation_id,
)
from ..domain.policy.models import PlanningPolicySet
from ..domain.rationale.models import DecisionRationale
from ..domain.replay.models import PlannerRunRecord
from ..ports.audit import PlanningAuditSession, SessionBoundAsyncPlanningAuditRepository
from . import auditable_planner_run as planner
from .make_observed_planner_run import ObservedPlannerRun, make_observed_planner_run
from .persist_audit import _record
from .persist_prospective_validation_evidence import (
    restore_prospective_validation_evidence_audit_artifact,
)
from .register_planning_utility_observation import (
    _require_registration_session,
    _validate_stored_record,
)
from .replay_planner_run import replay_planner_run


class PlanningUtilityDecisionBindingError(RuntimeError):
    pass


class PlanningUtilityDecisionBindingNotFound(LookupError):
    pass


@dataclass(frozen=True)
class DurablePlanningUtilityDecision:
    observation: PlanningUtilityObservation
    binding: PlanningUtilityDecisionBinding
    planner_run: planner.AuditablePlannerRun
    durable_bound_at: datetime
    reused_durable_binding: bool
    binding_committed: bool
    predecision_registration_established: bool
    utility_assessment_established: bool = False
    planning_utility_supported: bool = False
    prescription_change_authorized: bool = False
    planning_authorized: bool = False
    planner_runtime_modified: bool = False
    candidate_authority_modified: bool = False


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _binding_record(binding: PlanningUtilityDecisionBinding) -> AuditArtifactRecord:
    return _record(
        artifact_kind=AuditArtifactKind.PLANNING_UTILITY_DECISION_BINDING,
        artifact_id=binding.binding_id,
        athlete_id=binding.athlete_id,
        schema_version=binding.schema_version,
        created_at=binding.created_at,
        artifact=binding,
    )


def _run_records(athlete_id, run):
    # Audit rows are athlete-owned. In particular, policy content can be
    # identical across athletes without sharing one athlete-owned row.
    specifications = (
        (
            AuditArtifactKind.PLANNER_INPUT_ENVELOPE,
            "envelope:" + athlete_id + ":" + run.envelope.content_hash,
            "planner_input_envelope_v0.1",
            run.envelope,
        ),
        (
            AuditArtifactKind.CANDIDATE_ACTION_SET,
            "candidate_set:" + athlete_id + ":" + run.candidate_set.content_hash,
            "candidate_action_set_v0.1",
            run.candidate_set,
        ),
        (
            AuditArtifactKind.PLANNING_POLICY_SET,
            "policy_set:"
            + athlete_id
            + ":"
            + run.policy_set.policy_set_version
            + ":"
            + run.policy_set.content_hash,
            "planning_policy_set_v0.1",
            run.policy_set,
        ),
        (
            AuditArtifactKind.PLANNER_DECISION,
            run.decision.decision_id,
            "planner_decision_v0.1",
            run.decision,
        ),
        (
            AuditArtifactKind.DECISION_RATIONALE,
            run.rationale.rationale_id,
            run.rationale.rationale_version,
            run.rationale,
        ),
        (
            AuditArtifactKind.PLANNER_RUN_RECORD,
            run.run_record.run_id,
            "planner_run_record_v0.1",
            run.run_record,
        ),
    )
    return tuple(
        _record(
            artifact_kind=kind,
            artifact_id=identity,
            athlete_id=athlete_id,
            schema_version=schema,
            created_at=run.run_record.created_at,
            artifact=artifact,
        )
        for kind, identity, schema, artifact in specifications
    )


def _check_record(record, expected):
    if record is None:
        raise PlanningUtilityDecisionBindingError("Required durable audit artifact is missing.")
    # Input artifacts are shared by content hash. Their original metadata
    # may belong to an earlier run; their canonical content must still match.
    shared = expected.artifact_kind in (
        AuditArtifactKind.PLANNER_INPUT_ENVELOPE,
        AuditArtifactKind.CANDIDATE_ACTION_SET,
        AuditArtifactKind.PLANNING_POLICY_SET,
    )
    if (
        record.artifact_kind != expected.artifact_kind
        or record.artifact_id != expected.artifact_id
        or record.athlete_id != expected.athlete_id
        or record.schema_version != expected.schema_version
        or record.content_hash_algorithm != expected.content_hash_algorithm
        or record.content_hash != expected.content_hash
        or record.contract_json != expected.contract_json
        or (not shared and record.created_at != expected.created_at)
    ):
        raise PlanningUtilityDecisionBindingError(
            "Durable audit identity, metadata or contract differs."
        )
    if record.persisted_at is None:
        raise PlanningUtilityDecisionBindingError(
            "Audit artifact has no database persistence time."
        )
    persisted = to_utc(record.persisted_at, field_name="record.persisted_at")
    if persisted < to_utc(record.created_at, field_name="record.created_at"):
        raise PlanningUtilityDecisionBindingError("Audit persistence predates materialization.")
    return persisted


async def _load_registration(*, context, request, audit_repository):
    identity = planning_utility_observation_id(
        athlete_id=context.athlete_id, request_id=request.request_id
    )
    record = await audit_repository.get(
        artifact_kind=AuditArtifactKind.PLANNING_UTILITY_OBSERVATION, artifact_id=identity
    )
    if record is None:
        raise PlanningUtilityDecisionBindingError("Durable study registration is missing.")
    observation = restore_utility_contract(record.contract_json, PlanningUtilityObservation)
    sources = []
    # Restore the frozen source census, never today's eligible evidence list.
    for ref in observation.validation_evidence_refs:
        source_record = await audit_repository.get(
            artifact_kind=AuditArtifactKind.PROSPECTIVE_VALIDATION_EVIDENCE,
            artifact_id=ref.evidence_id,
        )
        if source_record is None or source_record.persisted_at != ref.persisted_at:
            raise PlanningUtilityDecisionBindingError(
                "Registered evidence source is missing or changed."
            )
        source = restore_prospective_validation_evidence_audit_artifact(source_record)
        sources.append(PlanningUtilityEvidenceSource(source, source_record.persisted_at))
    envelope = planner.build_planner_input_envelope(context=context, request=request)
    candidates = planner.generate_candidate_action_set(envelope=envelope)
    policy = planner.build_minimal_planning_policy_set()
    expected = build_planning_utility_observation(
        athlete_id=context.athlete_id,
        context_as_of=context.as_of,
        request=request,
        envelope=envelope,
        candidate_set=candidates,
        candidate_generation_version=planner.CANDIDATE_GENERATION_VERSION,
        policy_set_version=policy.policy_set_version,
        policy_set_content_hash=policy.content_hash,
        engine_version=observation.engine_version,
        planned_run_id=observation.planned_run_id,
        planned_decision_id=observation.planned_decision_id,
        planned_rationale_id=observation.planned_rationale_id,
        evidence_sources=tuple(sources),
        evidence_scan_complete=True,
        created_at=observation.created_at,
    )
    return _validate_stored_record(record=record, expected=expected)


def _check_run(*, context, request, observation, run):
    for artifact in (
        run.envelope,
        run.candidate_set,
        run.policy_set,
        run.decision,
        run.decision.policy_execution,
        run.rationale,
        run.run_record,
    ):
        if not artifact.verify_content_hash():
            raise PlanningUtilityDecisionBindingError("Actual-run source hash does not verify.")
    if (
        not context.verify_content_hash()
        or run.envelope.context_id != context.context_id
        or run.envelope.content_hash != observation.envelope_content_hash
        or canonical_json(run.candidate_set) != canonical_json(observation.candidate_set_snapshot)
        or run.policy_set.content_hash != observation.policy_set_content_hash
        or run.decision.created_at != run.decision.decision_time
    ):
        raise PlanningUtilityDecisionBindingError(
            "Actual run differs from registered planner inputs."
        )
    replay = replay_planner_run(
        record=run.run_record,
        context=context,
        request=request,
        replay_created_at=run.decision.created_at,
    )
    if replay.exact_replay_verified is not True:
        raise PlanningUtilityDecisionBindingError("Actual run does not verify by exact replay.")


def _attested(binding):
    attested = replace(binding, predecision_registration_established=True)
    return replace(
        attested,
        content_hash=compute_content_hash(
            attested, exclude_fields=DECISION_BINDING_HASH_EXCLUDE_FIELDS
        ),
    )


def _result(observation, binding, run, persisted_at, reused):
    return DurablePlanningUtilityDecision(
        observation=observation,
        binding=binding,
        planner_run=run,
        durable_bound_at=persisted_at,
        reused_durable_binding=reused,
        binding_committed=True,
        predecision_registration_established=True,
    )


async def persist_observed_planner_run_decision(
    *,
    context: AthletePlanningContextAggregate,
    request: PlannerDecisionRequest,
    observed_run: ObservedPlannerRun,
    audit_repository: SessionBoundAsyncPlanningAuditRepository,
    session: PlanningAuditSession,
) -> DurablePlanningUtilityDecision:
    """Own and commit actual-run artifacts plus one immutable binding.

    Retrying the same retained in-process receipt is idempotent, including
    recovery after an uncertain commit. This function never issues a decision.
    A caller-created historical run/timestamp is not a workflow receipt.
    """
    _require_registration_session(audit_repository=audit_repository, session=session)
    try:
        if (
            not isinstance(observed_run, ObservedPlannerRun)
            or observed_run.predecision_registration_established is not True
            or observed_run.registration.registration_committed is not True
            or observed_run.registration.reused_durable_observation is not False
            or any(
                getattr(item, name) is not False
                for item in (observed_run, observed_run.registration)
                for name in (
                    "utility_assessment_established",
                    "planning_utility_supported",
                    "prescription_change_authorized",
                    "planning_authorized",
                )
            )
            or observed_run.planner_runtime_modified is not False
            or observed_run.candidate_authority_modified is not False
        ):
            raise PlanningUtilityDecisionBindingError(
                "A completed observed-workflow receipt is required."
            )
        observation, registered = await _load_registration(
            context=context, request=request, audit_repository=audit_repository
        )
        if (
            canonical_json(observation) != canonical_json(observed_run.registration.observation)
            or registered != observed_run.registration.durable_registered_at
        ):
            raise PlanningUtilityDecisionBindingError(
                "Observed receipt differs from durable registration."
            )
        run = observed_run.planner_run
        _check_run(context=context, request=request, observation=observation, run=run)
        refs = []
        for expected in _run_records(context.athlete_id, run):
            saved = await audit_repository.save(expected)
            if (
                saved.status
                not in (AuditArtifactSaveStatus.CREATED, AuditArtifactSaveStatus.ALREADY_PRESENT)
                or saved.artifact_kind != expected.artifact_kind
                or saved.artifact_id != expected.artifact_id
                or saved.content_hash != expected.content_hash
            ):
                raise PlanningUtilityDecisionBindingError(
                    "Audit save receipt differs from actual run."
                )
            stored = await audit_repository.get(
                artifact_kind=expected.artifact_kind, artifact_id=expected.artifact_id
            )
            persisted = _check_record(stored, expected)
            refs.append(
                PlanningUtilityDecisionArtifactReference(
                    expected.artifact_kind,
                    expected.artifact_id,
                    expected.schema_version,
                    expected.content_hash,
                    persisted,
                )
            )
        identity = planning_utility_decision_binding_id(observation.observation_id)
        existing = await audit_repository.get(
            artifact_kind=AuditArtifactKind.PLANNING_UTILITY_DECISION_BINDING, artifact_id=identity
        )
        created_at = _utc_now() if existing is None else existing.created_at
        binding = _attested(
            build_planning_utility_decision_binding(
                observation=observation,
                observation_persisted_at=registered,
                decision=run.decision,
                rationale=run.rationale,
                run_record=run.run_record,
                artifact_refs=tuple(refs),
                created_at=created_at,
            )
        )
        expected = _binding_record(binding)
        saved = await audit_repository.save(expected)
        if (
            saved.status
            not in (AuditArtifactSaveStatus.CREATED, AuditArtifactSaveStatus.ALREADY_PRESENT)
            or saved.artifact_kind != expected.artifact_kind
            or saved.artifact_id != expected.artifact_id
            or saved.content_hash != expected.content_hash
        ):
            raise PlanningUtilityDecisionBindingError("Binding save receipt differs.")
        stored = await audit_repository.get(
            artifact_kind=expected.artifact_kind, artifact_id=expected.artifact_id
        )
        persisted = _check_record(stored, expected)
        await session.commit()
        if session.in_transaction() is not False:
            raise PlanningUtilityDecisionBindingError(
                "Binding commit left an active or unknown transaction."
            )
        return _result(
            observation,
            binding,
            run,
            persisted,
            saved.status == AuditArtifactSaveStatus.ALREADY_PRESENT,
        )
    except Exception:
        await session.rollback()
        raise


async def make_durable_observed_planner_run(
    *,
    context: AthletePlanningContextAggregate,
    request: PlannerDecisionRequest,
    run_id: str,
    decision_id: str,
    rationale_id: str,
    observation_created_at: datetime,
    audit_repository: SessionBoundAsyncPlanningAuditRepository,
    session: PlanningAuditSession,
    engine_version: str = "planner_engine_v0.1",
) -> DurablePlanningUtilityDecision:
    """Commit registration, execute once, then atomically commit its receipt.

    Post-decision failures retain the registration. Repeated orchestration
    fails closed; use load for a completed binding, or explicitly persist a
    retained genuine receipt. There is no automatic orphan recovery.
    """
    observed = await make_observed_planner_run(
        context=context,
        request=request,
        run_id=run_id,
        decision_id=decision_id,
        rationale_id=rationale_id,
        observation_created_at=observation_created_at,
        audit_repository=audit_repository,
        session=session,
        engine_version=engine_version,
    )
    return await persist_observed_planner_run_decision(
        context=context,
        request=request,
        observed_run=observed,
        audit_repository=audit_repository,
        session=session,
    )


async def load_planning_utility_decision(
    *,
    context: AthletePlanningContextAggregate,
    request: PlannerDecisionRequest,
    audit_repository: SessionBoundAsyncPlanningAuditRepository,
    session: PlanningAuditSession,
) -> DurablePlanningUtilityDecision:
    """Verify a completed receipt; perform no writes or new decision issuance.

    The original frozen context and request are required for exact replay.
    Read-only transaction ownership ends with rollback, never commit.
    """
    _require_registration_session(audit_repository=audit_repository, session=session)
    try:
        observation, registered = await _load_registration(
            context=context, request=request, audit_repository=audit_repository
        )
        identity = planning_utility_decision_binding_id(observation.observation_id)
        record = await audit_repository.get(
            artifact_kind=AuditArtifactKind.PLANNING_UTILITY_DECISION_BINDING, artifact_id=identity
        )
        if record is None:
            raise PlanningUtilityDecisionBindingNotFound(
                "No completed actual-decision binding exists."
            )
        binding = restore_utility_contract(record.contract_json, PlanningUtilityDecisionBinding)
        types = (
            PlannerInputEnvelope,
            CandidateActionSet,
            PlanningPolicySet,
            PlannerDecision,
            DecisionRationale,
            PlannerRunRecord,
        )
        if len(binding.artifact_refs) != len(types):
            raise PlanningUtilityDecisionBindingError(
                "Completed binding has incomplete artifact references."
            )
        artifacts, stored_records = [], []
        for ref, kind in zip(binding.artifact_refs, types):
            stored = await audit_repository.get(
                artifact_kind=ref.artifact_kind, artifact_id=ref.artifact_id
            )
            if stored is None or stored.persisted_at != ref.persisted_at:
                raise PlanningUtilityDecisionBindingError(
                    "Bound actual-run source is missing or changed."
                )
            artifacts.append(restore_utility_contract(stored.contract_json, kind))
            stored_records.append(stored)
        run = planner.AuditablePlannerRun(*artifacts)
        _check_run(context=context, request=request, observation=observation, run=run)
        for stored, expected in zip(stored_records, _run_records(context.athlete_id, run)):
            _check_record(stored, expected)
        expected = _attested(
            build_planning_utility_decision_binding(
                observation=observation,
                observation_persisted_at=registered,
                decision=run.decision,
                rationale=run.rationale,
                run_record=run.run_record,
                artifact_refs=binding.artifact_refs,
                created_at=record.created_at,
            )
        )
        persisted = _check_record(record, _binding_record(expected))
        result = _result(observation, expected, run, persisted, True)
    except Exception:
        await session.rollback()
        raise
    await session.rollback()
    return result
