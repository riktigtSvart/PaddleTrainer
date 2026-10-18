from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, TYPE_CHECKING

from ..common.serialization import CONTENT_HASH_ALGORITHM, compute_content_hash

if TYPE_CHECKING:
    from ..decision.models import PlannerActionCandidate, PlannerInputEnvelope


POLICY_SET_HASH_EXCLUDE_FIELDS = frozenset({"content_hash"})
POLICY_EXECUTION_HASH_EXCLUDE_FIELDS = frozenset({"content_hash"})


class PlanningPolicyFamily(StrEnum):
    ENTRY_GATE = "entry_gate"
    AUTHORIZATION = "authorization"
    UNCERTAINTY = "uncertainty"
    CONTINUITY = "continuity"
    FALLBACK = "fallback"


class PolicyStrength(StrEnum):
    HARD = "hard"
    STRONG = "strong"
    SOFT = "soft"
    ADVISORY = "advisory"


class PolicyEffect(StrEnum):
    PROHIBIT = "prohibit"
    REQUIRE = "require"
    RESTRICT = "restrict"
    ALLOW = "allow"
    PREFER = "prefer"
    DISFAVOR = "disfavor"
    REQUEST_INFORMATION = "request_information"
    NO_EFFECT = "no_effect"


@dataclass(frozen=True)
class PlanningPolicyDefinition:
    policy_key: str
    policy_version: str
    family: PlanningPolicyFamily
    strength: PolicyStrength
    description: str

    def __post_init__(self) -> None:
        for field_name, value in (
            ("policy_key", self.policy_key),
            ("policy_version", self.policy_version),
            ("description", self.description),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} must be non-empty.")


@dataclass(frozen=True)
class PlanningPolicySet:
    policy_set_version: str
    policies: tuple[PlanningPolicyDefinition, ...]
    content_hash_algorithm: str
    content_hash: str

    def verify_content_hash(self) -> bool:
        return (
            compute_content_hash(
                self,
                exclude_fields=POLICY_SET_HASH_EXCLUDE_FIELDS,
            )
            == self.content_hash
        )


def finalize_policy_set(
    *,
    policy_set_version: str,
    policies: tuple[PlanningPolicyDefinition, ...],
) -> PlanningPolicySet:
    if not policy_set_version.strip():
        raise ValueError("policy_set_version must be non-empty.")

    ordered = tuple(
        sorted(
            policies,
            key=lambda policy: (policy.policy_key, policy.policy_version),
        )
    )
    refs = tuple((p.policy_key, p.policy_version) for p in ordered)
    if len(refs) != len(set(refs)):
        raise ValueError("Policy refs must be unique.")

    provisional = PlanningPolicySet(
        policy_set_version=policy_set_version,
        policies=ordered,
        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash="",
    )
    digest = compute_content_hash(
        provisional,
        exclude_fields=POLICY_SET_HASH_EXCLUDE_FIELDS,
    )
    return PlanningPolicySet(
        policy_set_version=provisional.policy_set_version,
        policies=provisional.policies,
        content_hash_algorithm=provisional.content_hash_algorithm,
        content_hash=digest,
    )


@dataclass(frozen=True)
class ActionPolicyEvaluation:
    action_id: str
    policy_key: str
    policy_version: str
    strength: PolicyStrength
    effect: PolicyEffect
    reason_codes: tuple[str, ...]
    constraints: tuple[str, ...] = ()


@dataclass(frozen=True)
class PolicyExecutionRecord:
    policy_set_version: str
    policy_set_hash: str
    evaluations: tuple[ActionPolicyEvaluation, ...]
    content_hash_algorithm: str
    content_hash: str

    def verify_content_hash(self) -> bool:
        return (
            compute_content_hash(
                self,
                exclude_fields=POLICY_EXECUTION_HASH_EXCLUDE_FIELDS,
            )
            == self.content_hash
        )


def finalize_policy_execution_record(
    *,
    policy_set: PlanningPolicySet,
    evaluations: tuple[ActionPolicyEvaluation, ...],
) -> PolicyExecutionRecord:
    if not policy_set.verify_content_hash():
        raise ValueError("PlanningPolicySet hash does not verify.")

    ordered = tuple(
        sorted(
            evaluations,
            key=lambda item: (
                item.action_id,
                item.policy_key,
                item.policy_version,
            ),
        )
    )
    provisional = PolicyExecutionRecord(
        policy_set_version=policy_set.policy_set_version,
        policy_set_hash=policy_set.content_hash,
        evaluations=ordered,
        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash="",
    )
    digest = compute_content_hash(
        provisional,
        exclude_fields=POLICY_EXECUTION_HASH_EXCLUDE_FIELDS,
    )
    return PolicyExecutionRecord(
        policy_set_version=provisional.policy_set_version,
        policy_set_hash=provisional.policy_set_hash,
        evaluations=provisional.evaluations,
        content_hash_algorithm=provisional.content_hash_algorithm,
        content_hash=digest,
    )


class ExecutablePlanningPolicy(Protocol):
    @property
    def definition(self) -> PlanningPolicyDefinition:
        ...

    def evaluate(
        self,
        *,
        envelope: "PlannerInputEnvelope",
        candidate: "PlannerActionCandidate",
    ) -> ActionPolicyEvaluation:
        ...
