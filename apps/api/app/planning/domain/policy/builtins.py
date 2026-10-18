from dataclasses import dataclass

from ..context.models import TrainingSpaceStatus
from ..decision.models import (
    PlannerActionCandidate,
    PlannerActionType,
    PlannerInputEnvelope,
)
from .models import (
    ActionPolicyEvaluation,
    PlanningPolicyDefinition,
    PlanningPolicyFamily,
    PolicyEffect,
    PolicyStrength,
    finalize_policy_set,
)


@dataclass(frozen=True)
class GlobalEntryGatePolicy:
    definition: PlanningPolicyDefinition = PlanningPolicyDefinition(
        policy_key="GLOBAL_ENTRY_GATE_BOUNDARY",
        policy_version="v0.1",
        family=PlanningPolicyFamily.ENTRY_GATE,
        strength=PolicyStrength.HARD,
        description=(
            "Constrains planner actions when the global entry gate is "
            "HOLD, BLOCKED or REVIEW_REQUIRED."
        ),
    )

    def evaluate(
        self,
        *,
        envelope: PlannerInputEnvelope,
        candidate: PlannerActionCandidate,
    ) -> ActionPolicyEvaluation:
        status = envelope.training_space_status
        effect = PolicyEffect.NO_EFFECT
        reasons: tuple[str, ...] = ()

        if status == TrainingSpaceStatus.ENTRY_GATE_BLOCKED:
            if candidate.action_type == PlannerActionType.DEFER:
                effect = PolicyEffect.REQUIRE
                reasons = ("GLOBAL_ENTRY_GATE_BLOCKED",)
            elif candidate.action_type == PlannerActionType.SELECT_WORKOUT_FAMILY:
                effect = PolicyEffect.PROHIBIT
                reasons = ("GLOBAL_ENTRY_GATE_BLOCKED",)
        elif status == TrainingSpaceStatus.ENTRY_GATE_HOLD:
            if candidate.action_type == PlannerActionType.DEFER:
                effect = PolicyEffect.REQUIRE
                reasons = ("GLOBAL_ENTRY_GATE_HOLD",)
            elif candidate.action_type == PlannerActionType.SELECT_WORKOUT_FAMILY:
                effect = PolicyEffect.PROHIBIT
                reasons = ("GLOBAL_ENTRY_GATE_HOLD",)
        elif status == TrainingSpaceStatus.ENTRY_GATE_REVIEW_REQUIRED:
            if candidate.action_type == PlannerActionType.REQUEST_REVIEW:
                effect = PolicyEffect.REQUIRE
                reasons = ("GLOBAL_ENTRY_GATE_REVIEW_REQUIRED",)
            elif candidate.action_type == PlannerActionType.SELECT_WORKOUT_FAMILY:
                effect = PolicyEffect.PROHIBIT
                reasons = ("GLOBAL_ENTRY_GATE_REVIEW_REQUIRED",)

        return ActionPolicyEvaluation(
            action_id=candidate.action_id,
            policy_key=self.definition.policy_key,
            policy_version=self.definition.policy_version,
            strength=self.definition.strength,
            effect=effect,
            reason_codes=reasons,
        )


@dataclass(frozen=True)
class FinalAuthorizationBoundaryPolicy:
    definition: PlanningPolicyDefinition = PlanningPolicyDefinition(
        policy_key="FINAL_AUTHORIZATION_BOUNDARY",
        policy_version="v0.1",
        family=PlanningPolicyFamily.AUTHORIZATION,
        strength=PolicyStrength.HARD,
        description=(
            "Requires deferral while final training-space authorization "
            "remains unresolved."
        ),
    )

    def evaluate(
        self,
        *,
        envelope: PlannerInputEnvelope,
        candidate: PlannerActionCandidate,
    ) -> ActionPolicyEvaluation:
        effect = PolicyEffect.NO_EFFECT
        reasons: tuple[str, ...] = ()

        if not envelope.final_authorization:
            if candidate.action_type == PlannerActionType.DEFER:
                effect = PolicyEffect.REQUIRE
                reasons = ("FINAL_AUTHORIZATION_NOT_RESOLVED",)
            elif candidate.action_type == PlannerActionType.SELECT_WORKOUT_FAMILY:
                effect = PolicyEffect.PROHIBIT
                reasons = ("FINAL_AUTHORIZATION_NOT_RESOLVED",)

        return ActionPolicyEvaluation(
            action_id=candidate.action_id,
            policy_key=self.definition.policy_key,
            policy_version=self.definition.policy_version,
            strength=self.definition.strength,
            effect=effect,
            reason_codes=reasons,
        )


@dataclass(frozen=True)
class CriticalUnknownInformationPolicy:
    definition: PlanningPolicyDefinition = PlanningPolicyDefinition(
        policy_key="CRITICAL_UNKNOWN_INFORMATION",
        policy_version="v0.1",
        family=PlanningPolicyFamily.UNCERTAINTY,
        strength=PolicyStrength.SOFT,
        description=(
            "Prefers explicit information acquisition when high-relevance "
            "critical unknowns are present."
        ),
    )

    def evaluate(
        self,
        *,
        envelope: PlannerInputEnvelope,
        candidate: PlannerActionCandidate,
    ) -> ActionPolicyEvaluation:
        effect = PolicyEffect.NO_EFFECT
        reasons: tuple[str, ...] = ()

        if (
            envelope.high_relevance_unknowns
            and candidate.action_type == PlannerActionType.REQUEST_INFORMATION
        ):
            effect = PolicyEffect.PREFER
            reasons = ("HIGH_RELEVANCE_UNKNOWN_PRESENT",)

        return ActionPolicyEvaluation(
            action_id=candidate.action_id,
            policy_key=self.definition.policy_key,
            policy_version=self.definition.policy_version,
            strength=self.definition.strength,
            effect=effect,
            reason_codes=reasons,
        )


def build_minimal_planning_policy_runtime():
    return (
        GlobalEntryGatePolicy(),
        FinalAuthorizationBoundaryPolicy(),
        CriticalUnknownInformationPolicy(),
    )


def build_minimal_planning_policy_set():
    runtime = build_minimal_planning_policy_runtime()
    return finalize_policy_set(
        policy_set_version="minimal_planner_policy_set_v0.1",
        policies=tuple(policy.definition for policy in runtime),
    )
