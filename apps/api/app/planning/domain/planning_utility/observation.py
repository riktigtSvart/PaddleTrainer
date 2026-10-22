from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ..common.enums import (
    DecisionPurpose,
    PlanningScope,
)
from ..common.serialization import (
    CONTENT_HASH_ALGORITHM,
    compute_content_hash,
)
from ..common.time import to_utc
from ..decision.models import (
    CandidateActionSet,
    CandidateCoverageStatus,
    PlannerDecisionRequest,
    PlannerInputEnvelope,
)
from ..training_dynamics.models import (
    EffectEvidenceLevel,
)
from ..training_dynamics.prospective_cohort import (
    ProspectiveValidationFamilyKey,
)
from ..training_dynamics.prospective_validation_evidence import (
    PROSPECTIVE_VALIDATION_EVIDENCE_RULES_V01,
    PROSPECTIVE_VALIDATION_EVIDENCE_SCHEMA_V01,
    ProspectiveValidationEvidence,
    ProspectiveValidationEvidenceStatus,
)


PLANNING_UTILITY_OBSERVATION_SCHEMA_V01 = (
    "planning-utility-observation-v0.1"
)

PLANNING_UTILITY_OBSERVATION_RULES_V01 = (
    "planning-utility-observation-rules-v0.1"
)

PLANNING_UTILITY_OBSERVATION_IDENTITY_V01 = (
    "planning-utility-observation-identity-v0.1"
)

PLANNING_UTILITY_OBSERVATION_HASH_EXCLUDE_FIELDS = (
    frozenset(
        {
            "observation_id",
            "created_at",
            "content_hash",
        }
    )
)


class PlanningUtilityObservationStatus(StrEnum):
    REGISTERED_SHADOW_ONLY = (
        "registered_shadow_only"
    )


@dataclass(frozen=True)
class DurableValidationEvidenceReference:
    evidence_id: str
    evidence_content_hash: str

    evidence_schema_version: str
    evidence_rules_version: str

    family_key: ProspectiveValidationFamilyKey

    persisted_at: datetime


@dataclass(frozen=True)
class _PlanningUtilityObservationIdentity:
    identity_version: str

    athlete_id: str
    request_id: str


@dataclass(frozen=True)
class PlanningUtilityObservation:
    """Pre-decision, selection-free planning utility registration.

    This artifact records all durable prospectively validated evidence
    available at the decision-request boundary plus the deterministic
    planner input/candidate space.

    It does not choose a shadow action and cannot mutate planning.
    """

    observation_id: str
    schema_version: str
    rules_version: str

    athlete_id: str

    request_id: str
    context_id: str
    context_hash: str
    context_as_of: datetime

    decision_purpose: DecisionPurpose
    planning_scope: PlanningScope
    requested_at: datetime

    envelope_content_hash: str

    candidate_set_content_hash: str
    candidate_set_snapshot: CandidateActionSet
    candidate_coverage_status: CandidateCoverageStatus
    candidate_action_ids: tuple[str, ...]
    mutation_authorized_candidate_ids: tuple[str, ...]

    candidate_generation_version: str

    policy_set_version: str
    policy_set_content_hash: str

    engine_version: str

    planned_run_id: str
    planned_decision_id: str
    planned_rationale_id: str

    evidence_scan_complete: bool

    available_validation_evidence_count: int

    validation_evidence_refs: tuple[
        DurableValidationEvidenceReference,
        ...,
    ]

    status: PlanningUtilityObservationStatus

    predecision_registration_established: bool
    shadow_only: bool
    shadow_action_selected: bool

    utility_assessment_established: bool
    planning_utility_supported: bool

    prescription_change_authorized: bool
    planning_authorized: bool
    planner_runtime_modified: bool
    candidate_authority_modified: bool

    created_at: datetime

    content_hash_algorithm: str
    content_hash: str

    def verify_content_hash(self) -> bool:
        return (
            compute_content_hash(
                self,
                exclude_fields=(
                    PLANNING_UTILITY_OBSERVATION_HASH_EXCLUDE_FIELDS
                ),
            )
            == self.content_hash
        )


@dataclass(frozen=True)
class PlanningUtilityEvidenceSource:
    evidence: ProspectiveValidationEvidence
    persisted_at: datetime


def _require_non_empty(
    value: str,
    *,
    field_name: str,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"{field_name} must be a non-empty string."
        )

    return value


def _require_sha256(
    value: str,
    *,
    field_name: str,
) -> str:
    text = _require_non_empty(
        value,
        field_name=field_name,
    )

    if (
        len(text) != 64
        or any(
            char not in "0123456789abcdef"
            for char in text
        )
    ):
        raise ValueError(
            f"{field_name} must be a lowercase SHA-256 digest."
        )

    return text


def _validate_evidence(
    source: PlanningUtilityEvidenceSource,
    *,
    athlete_id: str,
    requested_at: datetime,
) -> DurableValidationEvidenceReference:
    evidence = source.evidence

    if not evidence.verify_content_hash():
        raise ValueError(
            "Planning utility source evidence hash "
            "does not verify."
        )

    if (
        evidence.schema_version
        != PROSPECTIVE_VALIDATION_EVIDENCE_SCHEMA_V01
        or evidence.rules_version
        != PROSPECTIVE_VALIDATION_EVIDENCE_RULES_V01
    ):
        raise ValueError(
            "Unsupported planning utility evidence contract."
        )

    if evidence.athlete_id != athlete_id:
        raise ValueError(
            "Planning utility evidence athlete differs."
        )

    if (
        evidence.status
        != ProspectiveValidationEvidenceStatus
        .PROSPECTIVELY_VALIDATED
        or evidence.evidence_level
        != EffectEvidenceLevel.PROSPECTIVELY_VALIDATED
        or evidence.association_supported is not True
        or evidence.prospective_validation_established
        is not True
    ):
        raise ValueError(
            "Planning utility requires prospectively "
            "validated source evidence."
        )

    if any(
        flag is not False
        for flag in (
            evidence.causal_attribution_established,
            evidence.effect_inference_authorized,
            evidence.readiness_inference_authorized,
            evidence.performance_prediction_authorized,
            evidence.prescription_change_authorized,
            evidence.planning_authorized,
        )
    ):
        raise ValueError(
            "Planning utility source evidence contains "
            "unsupported stronger authority."
        )

    persisted = to_utc(
        source.persisted_at,
        field_name="evidence.persisted_at",
    )

    if persisted < max(
        to_utc(evidence.created_at, field_name="evidence.created_at"),
        to_utc(evidence.as_of, field_name="evidence.as_of"),
    ):
        raise ValueError(
            "Planning utility evidence persistence predates "
            "its materialization or as_of boundary."
        )

    if persisted > requested_at:
        raise ValueError(
            "Planning utility evidence was not durably "
            "available by the decision-request boundary."
        )

    return DurableValidationEvidenceReference(
        evidence_id=evidence.evidence_id,
        evidence_content_hash=(
            evidence.content_hash
        ),
        evidence_schema_version=(
            evidence.schema_version
        ),
        evidence_rules_version=(
            evidence.rules_version
        ),
        family_key=evidence.family_key,
        persisted_at=persisted,
    )


def planning_utility_observation_id(
    *,
    athlete_id: str,
    request_id: str,
) -> str:
    """One immutable study-registration slot per athlete/request event.

    A new request ID is a new event, not proof of an independent trial.
    Same-request retries must preserve context, evidence and planned IDs.
    """
    identity = _PlanningUtilityObservationIdentity(
        identity_version=(
            PLANNING_UTILITY_OBSERVATION_IDENTITY_V01
        ),
        athlete_id=_require_non_empty(
            athlete_id,
            field_name="athlete_id",
        ),
        request_id=_require_non_empty(
            request_id,
            field_name="request_id",
        ),
    )

    digest = compute_content_hash(
        identity
    )

    return (
        "pt-planning-utility-observation:"
        + digest
    )


def build_planning_utility_observation(
    *,
    athlete_id: str,
    context_as_of: datetime,
    request: PlannerDecisionRequest,
    envelope: PlannerInputEnvelope,
    candidate_set: CandidateActionSet,
    candidate_generation_version: str,
    policy_set_version: str,
    policy_set_content_hash: str,
    engine_version: str,
    planned_run_id: str,
    planned_decision_id: str,
    planned_rationale_id: str,
    evidence_sources: tuple[
        PlanningUtilityEvidenceSource,
        ...,
    ],
    evidence_scan_complete: bool,
    created_at: datetime,
) -> PlanningUtilityObservation:
    athlete = _require_non_empty(
        athlete_id,
        field_name="athlete_id",
    )

    context_time = to_utc(
        context_as_of,
        field_name="context_as_of",
    )

    request_time = to_utc(
        request.requested_at,
        field_name="request.requested_at",
    )

    materialized = to_utc(
        created_at,
        field_name="created_at",
    )

    if request_time < context_time:
        raise ValueError(
            "Decision request predates planning context."
        )

    if materialized < request_time:
        raise ValueError(
            "Planning utility observation cannot predate "
            "the decision request."
        )

    if not envelope.verify_content_hash():
        raise ValueError(
            "PlannerInputEnvelope hash does not verify."
        )

    if not candidate_set.verify_content_hash():
        raise ValueError(
            "CandidateActionSet hash does not verify."
        )

    if (
        envelope.context_id != request.context_id
        or envelope.context_hash != request.context_hash
        or envelope.decision_purpose
        != request.decision_purpose
        or envelope.planning_scope
        != request.planning_scope
    ):
        raise ValueError(
            "Planning utility request/envelope context mismatch."
        )

    if (
        candidate_set.envelope_hash
        != envelope.content_hash
    ):
        raise ValueError(
            "Planning utility candidate set does not "
            "bind the observed envelope."
        )

    if not isinstance(
        evidence_scan_complete,
        bool,
    ):
        raise ValueError(
            "evidence_scan_complete must be boolean."
        )

    if not evidence_scan_complete:
        raise ValueError(
            "Planning utility evidence census must be complete."
        )

    refs = []

    seen_evidence_ids = set()

    for source in evidence_sources:
        ref = _validate_evidence(
            source,
            athlete_id=athlete,
            requested_at=request_time,
        )

        if ref.evidence_id in seen_evidence_ids:
            raise ValueError(
                "Duplicate validation evidence identity "
                "in planning utility observation."
            )

        seen_evidence_ids.add(
            ref.evidence_id
        )

        refs.append(
            ref
        )

    if not refs:
        raise ValueError(
            "Planning utility observation requires at "
            "least one durable prospectively validated "
            "evidence artifact."
        )

    ordered_refs = tuple(
        sorted(
            refs,
            key=lambda item: (
                item.persisted_at,
                item.evidence_id,
            ),
        )
    )

    candidate_ids = tuple(
        candidate.action_id
        for candidate in candidate_set.candidates
    )

    if len(set(candidate_ids)) != len(candidate_ids):
        raise ValueError(
            "Candidate action identities must be unique."
        )

    mutation_ids = tuple(
        candidate.action_id
        for candidate in candidate_set.candidates
        if candidate.plan_mutation_authorized
    )

    candidate_generation = _require_non_empty(
        candidate_generation_version,
        field_name="candidate_generation_version",
    )

    policy_version = _require_non_empty(
        policy_set_version,
        field_name="policy_set_version",
    )

    policy_hash = _require_sha256(
        policy_set_content_hash,
        field_name="policy_set_content_hash",
    )

    engine = _require_non_empty(
        engine_version,
        field_name="engine_version",
    )

    run_id = _require_non_empty(
        planned_run_id,
        field_name="planned_run_id",
    )

    decision_id = _require_non_empty(
        planned_decision_id,
        field_name="planned_decision_id",
    )

    rationale_id = _require_non_empty(
        planned_rationale_id,
        field_name="planned_rationale_id",
    )

    provisional = PlanningUtilityObservation(
        observation_id="PENDING",
        schema_version=(
            PLANNING_UTILITY_OBSERVATION_SCHEMA_V01
        ),
        rules_version=(
            PLANNING_UTILITY_OBSERVATION_RULES_V01
        ),

        athlete_id=athlete,

        request_id=request.request_id,
        context_id=request.context_id,
        context_hash=request.context_hash,
        context_as_of=context_time,

        decision_purpose=(
            request.decision_purpose
        ),
        planning_scope=request.planning_scope,
        requested_at=request_time,

        envelope_content_hash=(
            envelope.content_hash
        ),

        candidate_set_content_hash=(
            candidate_set.content_hash
        ),
        candidate_set_snapshot=candidate_set,
        candidate_coverage_status=(
            candidate_set.coverage_status
        ),
        candidate_action_ids=(
            candidate_ids
        ),
        mutation_authorized_candidate_ids=(
            mutation_ids
        ),

        candidate_generation_version=(
            candidate_generation
        ),

        policy_set_version=policy_version,
        policy_set_content_hash=policy_hash,

        engine_version=engine,

        planned_run_id=run_id,
        planned_decision_id=decision_id,
        planned_rationale_id=rationale_id,

        evidence_scan_complete=True,

        available_validation_evidence_count=(
            len(ordered_refs)
        ),

        validation_evidence_refs=(
            ordered_refs
        ),

        status=(
            PlanningUtilityObservationStatus
            .REGISTERED_SHADOW_ONLY
        ),

        # A pure builder cannot prove persistence or execution order.
        # The observed-run workflow reports that fact after commit and run.
        predecision_registration_established=False,
        shadow_only=True,
        shadow_action_selected=False,

        utility_assessment_established=False,
        planning_utility_supported=False,

        prescription_change_authorized=False,
        planning_authorized=False,
        planner_runtime_modified=False,
        candidate_authority_modified=False,

        created_at=materialized,

        content_hash_algorithm=(
            CONTENT_HASH_ALGORITHM
        ),
        content_hash="",
    )

    digest = compute_content_hash(
        provisional,
        exclude_fields=(
            PLANNING_UTILITY_OBSERVATION_HASH_EXCLUDE_FIELDS
        ),
    )

    return PlanningUtilityObservation(
        **{
            **provisional.__dict__,
            "observation_id": (
                planning_utility_observation_id(
                    athlete_id=athlete,
                    request_id=request.request_id,
                )
            ),
            "content_hash": digest,
        }
    )
