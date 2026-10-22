"""Cutoff-bound descriptive follow-up census for one observed decision.

One later cutoff is another snapshot of the same decision, not another
independent trial. Counts describe available sources, never zero exposure
or treatment effects. All response values remain in their immutable sources.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from ..common.enums import KnowledgeStatus
from ..common.serialization import CONTENT_HASH_ALGORITHM, compute_content_hash
from ..common.time import to_utc
from ..persistence.audit import AuditArtifactKind
from ..response_evidence.models import TrainingResponseKind, TrainingResponseTiming
from .decision_binding import PlanningUtilityDecisionBinding

PLANNING_UTILITY_FOLLOWUP_SCHEMA_V01 = "planning-utility-followup-v0.1"
PLANNING_UTILITY_FOLLOWUP_RULES_V01 = "planning-utility-followup-rules-v0.1"
FOLLOWUP_HASH_EXCLUDE_FIELDS = frozenset({"followup_id", "created_at", "content_hash"})
FOLLOWUP_SOURCE_KINDS = (
    AuditArtifactKind.AUTHORITATIVE_EXECUTED_TRAINING,
    AuditArtifactKind.AUTHORITATIVE_TRAINING_RESPONSE,
    AuditArtifactKind.PLAN_MUTATION_INSTRUCTION,
)


class PlanningUtilityResponseAvailability(StrEnum):
    SOURCE_AVAILABLE = "source_available"
    NO_SOURCE_AVAILABLE_AS_OF = "no_source_available_as_of"


@dataclass(frozen=True)
class PlanningUtilityFollowupSourceReference:
    artifact_kind: AuditArtifactKind
    artifact_id: str
    schema_version: str
    content_hash: str
    canonical_contract_sha256: str
    persisted_at: datetime


@dataclass(frozen=True)
class PlanningUtilityRevisionReference:
    revision_id: str
    content_hash: str


@dataclass(frozen=True)
class PlanningUtilityResponseObservation:
    source: PlanningUtilityFollowupSourceReference
    response_kind: TrainingResponseKind
    response_timing: TrainingResponseTiming
    observed_at: datetime
    available_at: datetime
    known_measurement_count: int
    non_known_measurement_count: int


@dataclass(frozen=True)
class PlanningUtilityExecutionObservation:
    source: PlanningUtilityFollowupSourceReference
    workout_session_id: str
    logical_plan_id: str
    observed_revision_id: str
    observed_revision_content_hash: str
    plan_execution_link_id: str
    plan_execution_link_content_hash: str
    instruction_source: PlanningUtilityFollowupSourceReference | None
    observed_at: datetime
    modality_key: str
    duration_status: KnowledgeStatus
    duration_s: int | None
    decision_execution_lineage_established: bool
    lineage_blockers: tuple[str, ...]
    plan_content_at_execution_status: str
    response_availability: PlanningUtilityResponseAvailability
    responses: tuple[PlanningUtilityResponseObservation, ...]


@dataclass(frozen=True)
class PlanningUtilityFollowup:
    followup_id: str
    schema_version: str
    rules_version: str
    athlete_id: str
    request_id: str
    observation_id: str
    decision_binding_id: str
    decision_binding_content_hash: str
    decision_binding_persisted_at: datetime
    as_of: datetime
    source_census_complete: bool
    census_sources: tuple[PlanningUtilityFollowupSourceReference, ...]
    revision_sources: tuple[PlanningUtilityRevisionReference, ...]
    unavailable_revision_ids: tuple[str, ...]
    unrelated_execution_source_ids: tuple[str, ...]
    unrelated_response_source_ids: tuple[str, ...]
    executions: tuple[PlanningUtilityExecutionObservation, ...]
    matched_execution_source_count: int
    established_execution_lineage_count: int
    response_source_count: int
    shadow_only: bool
    selected_action_execution_verified: bool
    plan_content_at_execution_verified: bool
    utility_endpoint_preregistered: bool
    utility_assessment_established: bool
    planning_utility_supported: bool
    causal_attribution_established: bool
    readiness_inference_authorized: bool
    fatigue_diagnosis_authorized: bool
    performance_prediction_authorized: bool
    prescription_change_authorized: bool
    planning_authorized: bool
    planner_runtime_modified: bool
    candidate_authority_modified: bool
    created_at: datetime
    content_hash_algorithm: str
    content_hash: str

    def verify_content_hash(self) -> bool:
        return (
            compute_content_hash(self, exclude_fields=FOLLOWUP_HASH_EXCLUDE_FIELDS)
            == self.content_hash
        )


def planning_utility_followup_id(*, decision_binding_id: str, as_of: datetime) -> str:
    if not isinstance(decision_binding_id, str) or not decision_binding_id.strip():
        raise ValueError("decision_binding_id must be non-empty.")
    return "pt-planning-utility-followup:" + compute_content_hash(
        {
            "identity_version": "planning-utility-followup-identity-v0.1",
            "decision_binding_id": decision_binding_id,
            "as_of": to_utc(as_of, field_name="as_of"),
        }
    )


def build_planning_utility_followup(
    *,
    binding: PlanningUtilityDecisionBinding,
    binding_persisted_at: datetime,
    as_of: datetime,
    census_sources: tuple[PlanningUtilityFollowupSourceReference, ...],
    revision_sources: tuple[PlanningUtilityRevisionReference, ...],
    unavailable_revision_ids: tuple[str, ...],
    unrelated_execution_source_ids: tuple[str, ...],
    unrelated_response_source_ids: tuple[str, ...],
    executions: tuple[PlanningUtilityExecutionObservation, ...],
    source_census_complete: bool,
    created_at: datetime,
) -> PlanningUtilityFollowup:
    cutoff = to_utc(as_of, field_name="as_of")
    created = to_utc(created_at, field_name="created_at")
    bound = to_utc(binding_persisted_at, field_name="binding_persisted_at")
    if (
        binding.content_hash_algorithm != CONTENT_HASH_ALGORITHM
        or not binding.verify_content_hash()
        or binding.predecision_registration_established is not True
        or binding.shadow_only is not True
    ):
        raise ValueError("Follow-up requires a verified observed-workflow binding.")
    if source_census_complete is not True:
        raise ValueError("Follow-up source census completeness is unknown.")
    if not (binding.decision_time <= binding.created_at <= bound <= cutoff <= created):
        raise ValueError("Follow-up cutoff or materialization chronology differs.")
    by_key = {}
    for ref in census_sources:
        key = (ref.artifact_kind, ref.artifact_id)
        if ref.artifact_kind not in FOLLOWUP_SOURCE_KINDS or key in by_key:
            raise ValueError("Duplicate or unexpected follow-up census source.")
        if to_utc(ref.persisted_at, field_name="source.persisted_at") > cutoff:
            raise ValueError("Follow-up source was not durably available by cutoff.")
        by_key[key] = ref
    revisions = {ref.revision_id: ref for ref in revision_sources}
    if (
        len(revisions) != len(revision_sources)
        or len(set(unavailable_revision_ids)) != len(unavailable_revision_ids)
        or set(revisions) & set(unavailable_revision_ids)
    ):
        raise ValueError("Revision source identity is ambiguous.")
    execution_ids, response_ids, session_ids = set(), set(), set()
    for row in executions:
        key = (AuditArtifactKind.AUTHORITATIVE_EXECUTED_TRAINING, row.source.artifact_id)
        if by_key.get(key) != row.source or row.source.artifact_id in execution_ids:
            raise ValueError("Execution row is not an exact unique census source.")
        if row.workout_session_id in session_ids:
            raise ValueError("Execution session identity is duplicated.")
        execution_ids.add(row.source.artifact_id)
        session_ids.add(row.workout_session_id)
        if (
            row.observed_revision_id not in revisions
            or revisions[row.observed_revision_id].content_hash
            != row.observed_revision_content_hash
            or row.plan_content_at_execution_status != "unverified"
            or type(row.decision_execution_lineage_established) is not bool
            or row.decision_execution_lineage_established != (not row.lineage_blockers)
        ):
            raise ValueError("Execution lineage contract or authority differs.")
        if row.duration_status == KnowledgeStatus.KNOWN:
            if type(row.duration_s) is not int or row.duration_s < 0:
                raise ValueError("Known duration requires a non-negative integer.")
        elif row.duration_s is not None:
            raise ValueError("Non-known duration must remain null.")
        if row.instruction_source is not None:
            ref = row.instruction_source
            if by_key.get((AuditArtifactKind.PLAN_MUTATION_INSTRUCTION, ref.artifact_id)) != ref:
                raise ValueError("Execution instruction is outside the frozen census.")
        if row.decision_execution_lineage_established and row.instruction_source is None:
            raise ValueError("Established execution lineage requires an audited instruction.")
        expected_availability = (
            PlanningUtilityResponseAvailability.SOURCE_AVAILABLE
            if row.responses
            else PlanningUtilityResponseAvailability.NO_SOURCE_AVAILABLE_AS_OF
        )
        if row.response_availability != expected_availability:
            raise ValueError("Response availability does not match its sources.")
        for response in row.responses:
            ref = response.source
            if (
                by_key.get((AuditArtifactKind.AUTHORITATIVE_TRAINING_RESPONSE, ref.artifact_id))
                != ref
                or ref.artifact_id in response_ids
            ):
                raise ValueError("Response row is not an exact unique census source.")
            if not (
                row.observed_at <= response.observed_at <= response.available_at <= ref.persisted_at
            ):
                raise ValueError("Response observation/availability chronology differs.")
            if any(
                type(count) is not int or count < 0
                for count in (
                    response.known_measurement_count,
                    response.non_known_measurement_count,
                )
            ):
                raise ValueError("Response measurement counts must be non-negative integers.")
            response_ids.add(ref.artifact_id)
    for kind, included, unrelated in (
        (
            AuditArtifactKind.AUTHORITATIVE_EXECUTED_TRAINING,
            execution_ids,
            unrelated_execution_source_ids,
        ),
        (
            AuditArtifactKind.AUTHORITATIVE_TRAINING_RESPONSE,
            response_ids,
            unrelated_response_source_ids,
        ),
    ):
        all_ids = {ref.artifact_id for ref in census_sources if ref.artifact_kind == kind}
        if (
            len(set(unrelated)) != len(unrelated)
            or included & set(unrelated)
            or included | set(unrelated) != all_ids
        ):
            raise ValueError("Follow-up census has dropped or duplicated a source.")
    ordered_rows = tuple(
        sorted(executions, key=lambda row: (row.observed_at, row.workout_session_id))
    )
    followup = PlanningUtilityFollowup(
        followup_id=planning_utility_followup_id(
            decision_binding_id=binding.binding_id, as_of=cutoff
        ),
        schema_version=PLANNING_UTILITY_FOLLOWUP_SCHEMA_V01,
        rules_version=PLANNING_UTILITY_FOLLOWUP_RULES_V01,
        athlete_id=binding.athlete_id,
        request_id=binding.request_id,
        observation_id=binding.observation_id,
        decision_binding_id=binding.binding_id,
        decision_binding_content_hash=binding.content_hash,
        decision_binding_persisted_at=bound,
        as_of=cutoff,
        source_census_complete=True,
        census_sources=tuple(
            sorted(census_sources, key=lambda ref: (ref.artifact_kind.value, ref.artifact_id))
        ),
        revision_sources=tuple(sorted(revision_sources, key=lambda ref: ref.revision_id)),
        unavailable_revision_ids=tuple(sorted(unavailable_revision_ids)),
        unrelated_execution_source_ids=tuple(sorted(unrelated_execution_source_ids)),
        unrelated_response_source_ids=tuple(sorted(unrelated_response_source_ids)),
        executions=ordered_rows,
        matched_execution_source_count=len(ordered_rows),
        established_execution_lineage_count=sum(
            row.decision_execution_lineage_established for row in ordered_rows
        ),
        response_source_count=sum(len(row.responses) for row in ordered_rows),
        shadow_only=True,
        selected_action_execution_verified=False,
        plan_content_at_execution_verified=False,
        utility_endpoint_preregistered=False,
        utility_assessment_established=False,
        planning_utility_supported=False,
        causal_attribution_established=False,
        readiness_inference_authorized=False,
        fatigue_diagnosis_authorized=False,
        performance_prediction_authorized=False,
        prescription_change_authorized=False,
        planning_authorized=False,
        planner_runtime_modified=False,
        candidate_authority_modified=False,
        created_at=created,
        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash="",
    )
    return replace(
        followup,
        content_hash=compute_content_hash(followup, exclude_fields=FOLLOWUP_HASH_EXCLUDE_FIELDS),
    )
