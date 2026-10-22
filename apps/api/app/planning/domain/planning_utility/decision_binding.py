"""Immutable actual-decision receipt for a P2.4A shadow registration.

The pure builder checks contracts and chronology. Only the application
workflow can attest its commit-before-execution ordering; the builder leaves
that claim false. Neither binding nor replay measures planning utility.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import datetime
from enum import Enum
from types import UnionType
from typing import get_args, get_origin, get_type_hints

from ..common.serialization import CONTENT_HASH_ALGORITHM, canonical_json, compute_content_hash
from ..common.time import to_utc
from ..decision.models import PlannerActionCandidate, PlannerDecision, PlannerDecisionStatus
from ..persistence.audit import AuditArtifactKind
from ..rationale.models import DecisionRationale
from ..replay.models import PlannerRunRecord, ReplayMode
from .observation import (
    PLANNING_UTILITY_OBSERVATION_RULES_V01,
    PLANNING_UTILITY_OBSERVATION_SCHEMA_V01,
    PlanningUtilityObservation,
    planning_utility_observation_id,
)

PLANNING_UTILITY_DECISION_BINDING_SCHEMA_V01 = "planning-utility-decision-binding-v0.1"
PLANNING_UTILITY_DECISION_BINDING_RULES_V01 = "planning-utility-decision-binding-rules-v0.1"
DECISION_BINDING_HASH_EXCLUDE_FIELDS = frozenset({"binding_id", "created_at", "content_hash"})


@dataclass(frozen=True)
class PlanningUtilityDecisionArtifactReference:
    artifact_kind: AuditArtifactKind
    artifact_id: str
    schema_version: str
    content_hash: str
    persisted_at: datetime


@dataclass(frozen=True)
class PlanningUtilityDecisionBinding:
    binding_id: str
    schema_version: str
    rules_version: str
    athlete_id: str
    observation_id: str
    observation_content_hash: str
    observation_persisted_at: datetime
    request_id: str
    context_id: str
    context_hash: str
    run_id: str
    decision_id: str
    rationale_id: str
    artifact_refs: tuple[PlanningUtilityDecisionArtifactReference, ...]
    decision_time: datetime
    decision_status: PlannerDecisionStatus
    selected_action: PlannerActionCandidate | None
    predecision_registration_established: bool
    shadow_only: bool
    execution_binding_established: bool
    response_binding_established: bool
    utility_endpoint_preregistered: bool
    utility_assessment_established: bool
    planning_utility_supported: bool
    causal_attribution_established: bool
    prescription_change_authorized: bool
    planning_authorized: bool
    planner_runtime_modified: bool
    candidate_authority_modified: bool
    created_at: datetime
    content_hash_algorithm: str
    content_hash: str

    def verify_content_hash(self) -> bool:
        return (
            compute_content_hash(self, exclude_fields=DECISION_BINDING_HASH_EXCLUDE_FIELDS)
            == self.content_hash
        )


def planning_utility_decision_binding_id(observation_id: str) -> str:
    if not isinstance(observation_id, str) or not observation_id.strip():
        raise ValueError("observation_id must be non-empty.")
    digest = compute_content_hash(
        {
            "identity_version": "planning-utility-decision-binding-identity-v0.1",
            "observation_id": observation_id,
        }
    )
    return "pt-planning-utility-decision-binding:" + digest


def _decode(value, contract_type):
    """Strictly decode this module's fixed, trusted dataclass type graphs.

    Contract JSON never selects a Python type. Exact field sets, primitive
    types and tuple arity are checked before constructing frozen objects.
    """
    origin, args = get_origin(contract_type), get_args(contract_type)
    if origin is UnionType:
        if value is None and type(None) in args:
            return None
        remaining = tuple(item for item in args if item is not type(None))
        if len(remaining) == 1:
            return _decode(value, remaining[0])
    elif origin is tuple:
        if not isinstance(value, list):
            raise ValueError("Contract tuple must be a JSON array.")
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_decode(item, args[0]) for item in value)
        if len(value) == len(args):
            return tuple(_decode(item, kind) for item, kind in zip(value, args))
    elif contract_type is datetime:
        if isinstance(value, str):
            return to_utc(datetime.fromisoformat(value), field_name="contract datetime")
    elif isinstance(contract_type, type) and issubclass(contract_type, Enum):
        if isinstance(value, str):
            return contract_type(value)
    elif is_dataclass(contract_type):
        names = {field.name for field in fields(contract_type)}
        if isinstance(value, dict) and set(value) == names:
            hints = get_type_hints(contract_type)
            return contract_type(**{name: _decode(value[name], hints[name]) for name in names})
    elif contract_type in (str, bool, int) and type(value) is contract_type:
        return value
    raise ValueError("Contract field set, type or tuple arity differs from its schema.")


def restore_utility_contract(contract_json: str, contract_type):
    # Only internal callers supply contract_type; it is never client input.
    restored = _decode(json.loads(contract_json), contract_type)
    if canonical_json(restored) != contract_json:
        raise ValueError("Stored contract is not exact canonical JSON.")
    if (
        restored.content_hash_algorithm != CONTENT_HASH_ALGORITHM
        or not restored.verify_content_hash()
    ):
        raise ValueError("Stored contract content hash does not verify.")
    return restored


def build_planning_utility_decision_binding(
    *,
    observation: PlanningUtilityObservation,
    observation_persisted_at: datetime,
    decision: PlannerDecision,
    rationale: DecisionRationale,
    run_record: PlannerRunRecord,
    artifact_refs: tuple[PlanningUtilityDecisionArtifactReference, ...],
    created_at: datetime,
) -> PlanningUtilityDecisionBinding:
    registered = to_utc(observation_persisted_at, field_name="observation_persisted_at")
    created = to_utc(created_at, field_name="created_at")
    decision_time = to_utc(decision.decision_time, field_name="decision_time")
    for artifact in (
        observation,
        observation.candidate_set_snapshot,
        decision,
        decision.policy_execution,
        rationale,
        run_record,
    ):
        if (
            artifact.content_hash_algorithm != CONTENT_HASH_ALGORITHM
            or not artifact.verify_content_hash()
        ):
            raise ValueError("Decision-binding source content hash does not verify.")
    if (
        observation.schema_version != PLANNING_UTILITY_OBSERVATION_SCHEMA_V01
        or observation.rules_version != PLANNING_UTILITY_OBSERVATION_RULES_V01
        or observation.observation_id
        != planning_utility_observation_id(
            athlete_id=observation.athlete_id, request_id=observation.request_id
        )
    ):
        raise ValueError("Unsupported observation contract or identity.")
    if (
        observation.predecision_registration_established is not False
        or observation.shadow_only is not True
        or observation.shadow_action_selected is not False
        or observation.evidence_scan_complete is not True
        or any(
            flag is not False
            for flag in (
                observation.utility_assessment_established,
                observation.planning_utility_supported,
                observation.prescription_change_authorized,
                observation.planning_authorized,
                observation.planner_runtime_modified,
                observation.candidate_authority_modified,
            )
        )
    ):
        raise ValueError("Observation contains unsupported authority or workflow claims.")
    if not (
        observation.requested_at
        <= observation.created_at
        <= registered
        < decision_time
        <= decision.created_at
        <= created
    ):
        raise ValueError("Registration, actual decision and binding chronology differ.")
    if (
        decision.request_id != observation.request_id
        or decision.context_id != observation.context_id
        or decision.context_hash != observation.context_hash
        or decision.decision_id != observation.planned_decision_id
        or rationale.rationale_id != observation.planned_rationale_id
        or run_record.run_id != observation.planned_run_id
        or decision.envelope_hash != observation.envelope_content_hash
        or decision.candidate_set_hash != observation.candidate_set_content_hash
        or decision.engine_version != observation.engine_version
        or decision.policy_execution.policy_set_hash != observation.policy_set_content_hash
        or decision.policy_execution.policy_set_version != observation.policy_set_version
    ):
        raise ValueError("Actual decision identity or registered inputs differ.")
    selected = decision.selected_action
    if selected is not None and not any(
        canonical_json(selected) == canonical_json(candidate)
        for candidate in observation.candidate_set_snapshot.candidates
    ):
        raise ValueError("Selected action is outside the frozen candidate snapshot.")
    if (
        rationale.decision_hash != decision.content_hash
        or rationale.context_hash != observation.context_hash
        or rationale.selected_action_id != (None if selected is None else selected.action_id)
        or rationale.decision_status != decision.status.value
        or run_record.context_hash != observation.context_hash
        or run_record.envelope_hash != observation.envelope_content_hash
        or run_record.candidate_set_hash != observation.candidate_set_content_hash
        or run_record.policy_set_hash != observation.policy_set_content_hash
        or run_record.policy_set_version != observation.policy_set_version
        or run_record.policy_execution_hash != decision.policy_execution.content_hash
        or run_record.decision_hash != decision.content_hash
        or run_record.rationale_hash != rationale.content_hash
        or run_record.rationale_version != rationale.rationale_version
        or run_record.candidate_generation_version != observation.candidate_generation_version
        or run_record.engine_version != observation.engine_version
        or run_record.replay_mode != ReplayMode.DETERMINISTIC_EXACT
        or run_record.decision_time != decision_time
        or run_record.created_at != decision.created_at
        or rationale.created_at != decision.created_at
    ):
        raise ValueError("Actual run, decision and rationale do not bind each other.")
    expected_refs = (
        (
            AuditArtifactKind.PLANNER_INPUT_ENVELOPE,
            "envelope:" + observation.athlete_id + ":" + observation.envelope_content_hash,
            "planner_input_envelope_v0.1",
            observation.envelope_content_hash,
        ),
        (
            AuditArtifactKind.CANDIDATE_ACTION_SET,
            "candidate_set:"
            + observation.athlete_id
            + ":"
            + observation.candidate_set_content_hash,
            "candidate_action_set_v0.1",
            observation.candidate_set_content_hash,
        ),
        (
            AuditArtifactKind.PLANNING_POLICY_SET,
            "policy_set:"
            + observation.athlete_id
            + ":"
            + observation.policy_set_version
            + ":"
            + observation.policy_set_content_hash,
            "planning_policy_set_v0.1",
            observation.policy_set_content_hash,
        ),
        (
            AuditArtifactKind.PLANNER_DECISION,
            decision.decision_id,
            "planner_decision_v0.1",
            decision.content_hash,
        ),
        (
            AuditArtifactKind.DECISION_RATIONALE,
            rationale.rationale_id,
            rationale.rationale_version,
            rationale.content_hash,
        ),
        (
            AuditArtifactKind.PLANNER_RUN_RECORD,
            run_record.run_id,
            "planner_run_record_v0.1",
            run_record.content_hash,
        ),
    )
    if len(artifact_refs) != len(expected_refs):
        raise ValueError("Actual-decision audit references are incomplete.")
    for ref, expected in zip(artifact_refs, expected_refs):
        if (ref.artifact_kind, ref.artifact_id, ref.schema_version, ref.content_hash) != expected:
            raise ValueError("Actual-decision audit reference differs.")
        persisted = to_utc(ref.persisted_at, field_name="artifact_ref.persisted_at")
        if persisted > created or (
            ref.artifact_kind
            in (
                AuditArtifactKind.PLANNER_DECISION,
                AuditArtifactKind.DECISION_RATIONALE,
                AuditArtifactKind.PLANNER_RUN_RECORD,
            )
            and persisted < decision.created_at
        ):
            raise ValueError("Actual-decision audit persistence chronology differs.")
    binding = PlanningUtilityDecisionBinding(
        binding_id=planning_utility_decision_binding_id(observation.observation_id),
        schema_version=PLANNING_UTILITY_DECISION_BINDING_SCHEMA_V01,
        rules_version=PLANNING_UTILITY_DECISION_BINDING_RULES_V01,
        athlete_id=observation.athlete_id,
        observation_id=observation.observation_id,
        observation_content_hash=observation.content_hash,
        observation_persisted_at=registered,
        request_id=observation.request_id,
        context_id=observation.context_id,
        context_hash=observation.context_hash,
        run_id=run_record.run_id,
        decision_id=decision.decision_id,
        rationale_id=rationale.rationale_id,
        artifact_refs=tuple(artifact_refs),
        decision_time=decision_time,
        decision_status=decision.status,
        selected_action=selected,
        predecision_registration_established=False,
        shadow_only=True,
        execution_binding_established=False,
        response_binding_established=False,
        utility_endpoint_preregistered=False,
        utility_assessment_established=False,
        planning_utility_supported=False,
        causal_attribution_established=False,
        prescription_change_authorized=False,
        planning_authorized=False,
        planner_runtime_modified=False,
        candidate_authority_modified=False,
        created_at=created,
        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash="",
    )
    return replace(
        binding,
        content_hash=compute_content_hash(
            binding, exclude_fields=DECISION_BINDING_HASH_EXCLUDE_FIELDS
        ),
    )
