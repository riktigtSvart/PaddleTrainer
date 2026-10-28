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
    AUTHORITATIVE_EXECUTED_TRAINING = "authoritative_executed_training"
    AUTHORITATIVE_TRAINING_RESPONSE = "authoritative_training_response"
    PERSONAL_RESPONSE_PREDICTION_ISSUANCE = "personal_response_prediction_issuance"
    PERSONAL_RESPONSE_PREDICTION_CHALLENGE_SLOT = "personal_response_prediction_challenge_slot"
    PERSONAL_RESPONSE_PREDICTION_OUTCOME = "personal_response_prediction_outcome"
    PROSPECTIVE_VALIDATION_EVIDENCE = "prospective_validation_evidence"
    PLANNING_UTILITY_OBSERVATION = "planning_utility_observation"
    PLANNING_UTILITY_DECISION_BINDING = "planning_utility_decision_binding"
    PLANNING_UTILITY_FOLLOWUP = "planning_utility_followup"
    MACROCYCLE_CAPABILITY_PLAN = "macrocycle_capability_plan"
    MESOCYCLE_GOAL_PROTOCOL = "mesocycle_goal_protocol"
    MESOCYCLE_GOAL_ASSESSMENT = "mesocycle_goal_assessment"
    GOAL_MEASUREMENT_REGISTRATION = "goal_measurement_registration"
    CYCLE_PROGRAM_REGISTRATION = "cycle_program_registration"
    CYCLE_MESOCYCLE_BOUNDARY_REVISION = "cycle_mesocycle_boundary_revision"
    CYCLE_COMPETITION_REVISION = "cycle_competition_revision"
    ATHLETE_PROFILE = "athlete_profile"
    ATHLETE_AVAILABILITY = "athlete_availability"
    ATHLETE_POLAR_IMPORT = "athlete_polar_import"
    WORKOUT_GOAL_TAG = "workout_goal_tag"
    CALENDAR_WORKOUT_MOVE = "calendar_workout_move"
    CALENDAR_CONSTRAINT_REVISION = "calendar_constraint_revision"
    SESSION_FEEDBACK = "session_feedback"
    DATA_SYNC_STARTED = "data_sync_started"
    DATA_SYNC_SUCCEEDED = "data_sync_succeeded"
    DATA_SYNC_FAILED = "data_sync_failed"


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

    # Persistence metadata assigned by the durable store.
    # None means no authoritative DB insertion time is proven.
    persisted_at: datetime | None = None


@dataclass(frozen=True)
class AuditArtifactSaveResult:
    status: AuditArtifactSaveStatus
    artifact_kind: AuditArtifactKind
    artifact_id: str
    content_hash: str
