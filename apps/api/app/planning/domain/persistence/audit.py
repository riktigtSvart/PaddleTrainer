from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class AuditArtifactKind(StrEnum):
    PLANNER_INPUT_ENVELOPE = "planner_input_envelope"
    CANDIDATE_ACTION_SET = "candidate_action_set"
    PLANNING_POLICY_SET = "planning_policy_set"
    PLANNER_DECISION = "planner_decision"
    DECISION_RATIONALE = "decision_rationale"
    PLANNER_RUN_RECORD = "planner_run_record"
    PLAN_MUTATION_INSTRUCTION = "plan_mutation_instruction"
    PLAN_REVISION_LINK = "plan_revision_link"


class AuditArtifactSaveStatus(StrEnum):
    CREATED = "created"
    ALREADY_PRESENT = "already_present"


class AuditArtifactConflictError(RuntimeError):
    """Stable audit artifact identity was reused for different content."""


@dataclass(frozen=True)
class AuditArtifactRecord:
    artifact_kind: AuditArtifactKind
    artifact_id: str
    athlete_id: str
    schema_version: str
    created_at: datetime
    content_hash_algorithm: str
    content_hash: str
    contract_json: str


@dataclass(frozen=True)
class AuditArtifactSaveResult:
    status: AuditArtifactSaveStatus
    artifact_kind: AuditArtifactKind
    artifact_id: str
    content_hash: str
