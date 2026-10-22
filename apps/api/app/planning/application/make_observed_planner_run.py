from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from ..domain.common.serialization import canonical_json
from ..domain.common.time import to_utc
from ..domain.context.models import AthletePlanningContextAggregate
from ..domain.decision.models import (
    CandidateActionSet,
    PlannerDecisionRequest,
    PlannerInputEnvelope,
)
from ..domain.planning_utility.observation import PlanningUtilityObservation
from ..domain.policy.models import PlanningPolicySet
from ..ports.audit import PlanningAuditSession, SessionBoundAsyncPlanningAuditRepository
from . import auditable_planner_run as planner
from .register_planning_utility_observation import (
    DurablePlanningUtilityObservation,
    register_planning_utility_observation,
)


class ObservedPlannerRunError(RuntimeError):
    pass


@dataclass(frozen=True)
class ObservedPlannerRun:
    registration: DurablePlanningUtilityObservation
    planner_run: planner.AuditablePlannerRun
    predecision_registration_established: bool
    utility_assessment_established: bool
    planning_utility_supported: bool
    prescription_change_authorized: bool
    planning_authorized: bool
    planner_runtime_modified: bool
    candidate_authority_modified: bool


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _check_planner_inputs(
    *,
    observation: PlanningUtilityObservation,
    envelope: PlannerInputEnvelope,
    candidate_set: CandidateActionSet,
    policy_set: PlanningPolicySet,
) -> None:
    if (
        not envelope.verify_content_hash()
        or not candidate_set.verify_content_hash()
        or envelope.content_hash != observation.envelope_content_hash
        or candidate_set.content_hash != observation.candidate_set_content_hash
        or candidate_set.envelope_hash != envelope.content_hash
        or canonical_json(candidate_set)
        != canonical_json(observation.candidate_set_snapshot)
        or policy_set.policy_set_version != observation.policy_set_version
        or policy_set.content_hash != observation.policy_set_content_hash
    ):
        raise ObservedPlannerRunError(
            "Planner inputs differ from the committed study registration."
        )


async def make_observed_planner_run(
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
) -> ObservedPlannerRun:
    """Commit a shadow study registration before calling the existing planner.

    Registration requires the repository's exact bound session, initially
    without a transaction. The registration service owns its commit.

    Decision time is sampled inside this workflow after commit. The existing
    planner still determines its action and authority without study input.

    An existing registration is retained but never automatically re-executed:
    it may belong to a completed run or a crash after registration commit.
    Recovery requires a separate auditable binding/recovery workflow.
    The returned run is in memory; later durable outcome binding is separate.
    """
    registration = await register_planning_utility_observation(
        context=context,
        request=request,
        planned_run_id=run_id,
        planned_decision_id=decision_id,
        planned_rationale_id=rationale_id,
        created_at=observation_created_at,
        audit_repository=audit_repository,
        session=session,
        engine_version=engine_version,
    )

    if registration.registration_committed is not True:
        raise ObservedPlannerRunError("Study registration was not committed.")

    if registration.reused_durable_observation:
        raise ObservedPlannerRunError(
            "Existing study registration requires explicit recovery; "
            "automatic planner re-execution is not authorized."
        )

    observation = registration.observation
    if (
        not observation.verify_content_hash()
        or not observation.candidate_set_snapshot.verify_content_hash()
        or observation.athlete_id != context.athlete_id
        or observation.request_id != request.request_id
        or observation.context_id != request.context_id
        or observation.context_id != context.context_id
        or observation.context_hash != request.context_hash
        or observation.context_hash != context.content_hash
        or observation.context_as_of != to_utc(context.as_of, field_name="context.as_of")
        or observation.decision_purpose != request.decision_purpose
        or observation.planning_scope != request.planning_scope
        or observation.requested_at != request.requested_at
        or observation.planned_run_id != run_id
        or observation.planned_decision_id != decision_id
        or observation.planned_rationale_id != rationale_id
        or observation.engine_version != engine_version
        or observation.candidate_generation_version != planner.CANDIDATE_GENERATION_VERSION
        or observation.predecision_registration_established is not False
        or observation.shadow_only is not True
        or observation.shadow_action_selected is not False
        or any(
            flag is not False
            for flag in (
                observation.utility_assessment_established,
                observation.planning_utility_supported,
                observation.prescription_change_authorized,
                observation.planning_authorized,
                observation.planner_runtime_modified,
                observation.candidate_authority_modified,
                registration.utility_assessment_established,
                registration.planning_utility_supported,
                registration.prescription_change_authorized,
                registration.planning_authorized,
            )
        )
    ):
        raise ObservedPlannerRunError(
            "Committed study registration does not bind the requested planner run."
        )

    # Replay deterministic preparation before entering the decision engine.
    # A drift detected here retains the registration as an unexecuted event.
    envelope = planner.build_planner_input_envelope(context=context, request=request)
    candidate_set = planner.generate_candidate_action_set(envelope=envelope)
    policy_set = planner.build_minimal_planning_policy_set()
    _check_planner_inputs(
        observation=observation,
        envelope=envelope,
        candidate_set=candidate_set,
        policy_set=policy_set,
    )

    decision_time = to_utc(_utc_now(), field_name="decision_time")
    if decision_time <= registration.durable_registered_at:
        raise ObservedPlannerRunError(
            "Decision time must strictly follow durable study registration."
        )

    run = planner.make_auditable_planner_run(
        context=context,
        request=request,
        run_id=run_id,
        decision_id=decision_id,
        rationale_id=rationale_id,
        decision_time=decision_time,
        created_at=decision_time,
        engine_version=engine_version,
    )
    _check_planner_inputs(
        observation=observation,
        envelope=run.envelope,
        candidate_set=run.candidate_set,
        policy_set=run.policy_set,
    )
    decision = run.decision
    if (
        not decision.verify_content_hash()
        or decision.decision_id != decision_id
        or decision.request_id != request.request_id
        or decision.context_id != observation.context_id
        or decision.context_hash != observation.context_hash
        or decision.envelope_hash != observation.envelope_content_hash
        or decision.candidate_set_hash != observation.candidate_set_content_hash
        or decision.engine_version != engine_version
        or decision.decision_time != decision_time
        or decision.created_at < decision_time
    ):
        raise ObservedPlannerRunError(
            "Planner decision does not bind the committed study inputs and time."
        )

    return ObservedPlannerRun(
        registration=registration,
        planner_run=run,
        predecision_registration_established=True,
        utility_assessment_established=False,
        planning_utility_supported=False,
        prescription_change_authorized=False,
        planning_authorized=False,
        planner_runtime_modified=False,
        candidate_authority_modified=False,
    )
