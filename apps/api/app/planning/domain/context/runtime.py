from datetime import datetime

from ..common.enums import (
    DecisionPurpose,
    DecisionRelevance,
    PlanningScope,
)
from ..common.refs import SourceSnapshotRef, VersionRef
from ..common.time import to_utc
from ..entry_gate.models import (
    EntryGateDecision,
    GlobalEntryGate,
    StimulusGateStatus,
)
from ..training_state.models import (
    CurrentTrainingState,
    LoadAnchorStatus,
)
from ..workout_family.eligibility import assess_family_entry_gate
from ..workout_family.models import (
    FamilyEntryGateStatus,
    WorkoutFamilyRegistry,
)
from .models import (
    CriticalUnknown,
    CurrentStateContextProjection,
    EntryGateContextProjection,
    RuntimePlanningProjection,
    StimulusGateContextProjection,
    TrainingSpaceProjection,
    TrainingSpaceStatus,
    UnresolvedPlanningDimension,
    WorkoutFamilySpaceItem,
    create_planning_context,
)


DEFAULT_UNRESOLVED_DIMENSIONS = (
    UnresolvedPlanningDimension.GOAL_PRIORITY,
    UnresolvedPlanningDimension.OBJECTIVE_REGIME,
    UnresolvedPlanningDimension.SPORT_READINESS,
    UnresolvedPlanningDimension.PLANNING_AUTHORITY,
    UnresolvedPlanningDimension.DETAILED_AVAILABILITY,
    UnresolvedPlanningDimension.ENVIRONMENT,
)


def _state_source_ref(
    state: CurrentTrainingState,
) -> SourceSnapshotRef:
    return SourceSnapshotRef(
        domain="CURRENT_TRAINING_STATE",
        object_id=state.state_id,
        object_version=state.schema_version,
        as_of=state.as_of,
        information_cutoff_at=state.information_cutoff_at,
        available_at=state.created_at,
        content_hash=state.content_hash,
    )


def _gate_source_ref(
    gate: EntryGateDecision,
) -> SourceSnapshotRef:
    return SourceSnapshotRef(
        domain="ENTRY_GATE_DECISION",
        object_id=gate.decision_id,
        object_version=gate.schema_version,
        as_of=gate.as_of,
        information_cutoff_at=gate.information_cutoff_at,
        available_at=gate.created_at,
        content_hash=gate.content_hash,
    )


def _training_space_status(
    gate: EntryGateDecision,
    family_statuses: tuple[FamilyEntryGateStatus, ...],
) -> TrainingSpaceStatus:
    if gate.global_gate == GlobalEntryGate.BLOCKED:
        return TrainingSpaceStatus.ENTRY_GATE_BLOCKED
    if gate.global_gate == GlobalEntryGate.REVIEW_REQUIRED:
        return TrainingSpaceStatus.ENTRY_GATE_REVIEW_REQUIRED
    if gate.global_gate == GlobalEntryGate.HOLD:
        return TrainingSpaceStatus.ENTRY_GATE_HOLD

    if gate.global_gate == GlobalEntryGate.OPEN_WITH_CONSTRAINTS:
        return TrainingSpaceStatus.ENTRY_GATE_CONSTRAINED

    if any(
        status != FamilyEntryGateStatus.ELIGIBLE
        for status in family_statuses
    ):
        return TrainingSpaceStatus.ENTRY_GATE_CONSTRAINED

    return TrainingSpaceStatus.ENTRY_GATE_OPEN


def _derived_unknowns(
    state: CurrentTrainingState,
    gate: EntryGateDecision,
) -> tuple[CriticalUnknown, ...]:
    unknowns: list[CriticalUnknown] = []

    if state.load_anchor.status == LoadAnchorStatus.UNKNOWN:
        unknowns.append(
            CriticalUnknown(
                domain="CURRENT_LOAD_ANCHOR",
                question=(
                    "Current executable exposure anchor is unknown."
                ),
                decision_relevance=DecisionRelevance.HIGH,
                fallback_policy="CONSERVATIVE_OR_DATA_LIMITED",
            )
        )
    elif state.load_anchor.status == LoadAnchorStatus.PARTIAL_EXPOSURE:
        unknowns.append(
            CriticalUnknown(
                domain="CURRENT_LOAD_ANCHOR",
                question=(
                    "Current exposure anchor has partial source coverage or "
                    "partial duration coverage."
                ),
                decision_relevance=DecisionRelevance.MODERATE,
                fallback_policy="CONSERVATIVE_REANCHOR",
            )
        )

    for stimulus_gate in gate.stimulus_gates:
        if stimulus_gate.status == StimulusGateStatus.UNKNOWN:
            unknowns.append(
                CriticalUnknown(
                    domain=f"STIMULUS_GATE:{stimulus_gate.stimulus_key}",
                    question=(
                        "Stimulus-specific build authorization is unknown."
                    ),
                    decision_relevance=DecisionRelevance.HIGH,
                    fallback_policy="NO_BUILD_ESCALATION",
                )
            )

    # Preserve order but prevent duplicate domains/questions.
    deduplicated: dict[tuple[str, str], CriticalUnknown] = {}
    for item in unknowns:
        deduplicated[(item.domain, item.question)] = item
    return tuple(deduplicated.values())


def build_runtime_planning_context(
    *,
    current_state: CurrentTrainingState,
    entry_gate: EntryGateDecision,
    workout_family_registry: WorkoutFamilyRegistry,
    context_id: str,
    schema_version: str,
    as_of: datetime,
    created_at: datetime,
    planning_scope: PlanningScope,
    decision_purpose: DecisionPurpose,
    engine_version: VersionRef,
    rules_version: VersionRef,
    evidence_pack_version: VersionRef,
    sport_profile_versions: tuple[VersionRef, ...] = (),
    additional_policy_versions: tuple[VersionRef, ...] = (),
    additional_critical_unknowns: tuple[CriticalUnknown, ...] = (),
    unresolved_dimensions: tuple[
        UnresolvedPlanningDimension, ...
    ] = DEFAULT_UNRESOLVED_DIMENSIONS,
):
    """Build the P0.7 frozen runtime projection.

    This projection intersects CurrentTrainingState, EntryGate and the workout
    family registry. It is deliberately *not* final workout authorization:
    sport readiness, detailed availability/environment, goal priority and
    planning authority are explicitly left unresolved until their runtimes are
    integrated.
    """
    if not current_state.verify_content_hash():
        raise ValueError("CurrentTrainingState hash does not verify.")
    if not entry_gate.verify_content_hash():
        raise ValueError("EntryGateDecision hash does not verify.")
    if not workout_family_registry.verify_content_hash():
        raise ValueError("WorkoutFamilyRegistry hash does not verify.")

    if entry_gate.athlete_id != current_state.athlete_id:
        raise ValueError(
            "EntryGateDecision and CurrentTrainingState athlete IDs differ."
        )
    if (
        entry_gate.current_training_state_hash
        != current_state.content_hash
    ):
        raise ValueError(
            "EntryGateDecision does not reference the supplied "
            "CurrentTrainingState content hash."
        )
    if (
        entry_gate.information_cutoff_at
        != current_state.information_cutoff_at
    ):
        raise ValueError(
            "EntryGateDecision and CurrentTrainingState information cutoffs "
            "must match in P0.7."
        )

    as_of_utc = to_utc(as_of, field_name="as_of")
    created_utc = to_utc(created_at, field_name="created_at")
    cutoff = current_state.information_cutoff_at

    latest_component_created_at = max(
        current_state.created_at,
        entry_gate.created_at,
    )
    if latest_component_created_at > as_of_utc:
        raise ValueError(
            "Runtime planning context as_of precedes a required derived "
            "component."
        )
    if created_utc < as_of_utc:
        raise ValueError(
            "Planning context created_at must not precede as_of."
        )

    assessments = tuple(
        assess_family_entry_gate(
            family=family,
            entry_gate=entry_gate,
        )
        for family in workout_family_registry.families
    )

    family_by_ref = {
        (
            family.family_ref.family_key,
            family.family_ref.family_version,
        ): family
        for family in workout_family_registry.families
    }

    family_items = []
    for assessment in assessments:
        key = (
            assessment.family_ref.family_key,
            assessment.family_ref.family_version,
        )
        family = family_by_ref[key]
        family_items.append(
            WorkoutFamilySpaceItem(
                family_key=assessment.family_ref.family_key,
                family_version=assessment.family_ref.family_version,
                modality_key=family.modality_key.key,
                sport_key=(
                    family.sport_key.key
                    if family.sport_key is not None
                    else None
                ),
                entry_gate_status=assessment.status,
                build_authorized_by_entry_gate=(
                    assessment.build_authorized
                ),
                dose_reduction_required=(
                    assessment.dose_reduction_required
                ),
                reason_codes=assessment.reason_codes,
            )
        )

    family_items_tuple = tuple(
        sorted(
            family_items,
            key=lambda item: (
                item.family_key,
                item.family_version,
            ),
        )
    )

    runtime_projection = RuntimePlanningProjection(
        current_state=CurrentStateContextProjection(
            current_training_state_hash=current_state.content_hash,
            load_anchor_status=current_state.load_anchor.status,
            recent_source_coverage=(
                current_state.recent_exposure.source_coverage
            ),
            recent_observed_session_count=(
                current_state.recent_exposure.observed_session_count
            ),
            recent_known_duration_s=(
                current_state.recent_exposure.observed_known_duration_s
            ),
            recent_complete_window_duration_s=(
                current_state.recent_exposure.complete_window_total_duration_s
            ),
            latest_training_observed_at=(
                current_state.recent_exposure.last_training_observed_at
            ),
        ),
        entry_gate=EntryGateContextProjection(
            entry_gate_decision_hash=entry_gate.content_hash,
            global_gate=entry_gate.global_gate,
            entry_mode=entry_gate.entry_mode,
            reason_codes=tuple(
                reason.value for reason in entry_gate.reason_codes
            ),
            stimulus_gates=tuple(
                StimulusGateContextProjection(
                    stimulus_key=gate.stimulus_key,
                    status=gate.status,
                    reason_codes=gate.reason_codes,
                )
                for gate in entry_gate.stimulus_gates
            ),
        ),
        workout_family_registry_version=(
            workout_family_registry.registry_version
        ),
        workout_family_registry_hash=(
            workout_family_registry.content_hash
        ),
        training_space=TrainingSpaceProjection(
            projection_scope="ENTRY_GATE_FAMILY_SPACE_V0.1",
            status=_training_space_status(
                entry_gate,
                tuple(item.entry_gate_status for item in family_items_tuple),
            ),
            families=family_items_tuple,
            unresolved_dimensions=tuple(unresolved_dimensions),
            # P0.7 has not yet intersected authority, sport readiness,
            # detailed availability or environment, so it must never claim
            # final executable authorization.
            final_authorization=False,
        ),
    )

    derived_unknowns = _derived_unknowns(current_state, entry_gate)
    critical_unknowns = tuple(
        {
            (item.domain, item.question): item
            for item in (
                *derived_unknowns,
                *additional_critical_unknowns,
            )
        }.values()
    )

    policy_versions = (
        VersionRef(
            namespace="entry_gate_policy",
            version=entry_gate.policy_version,
        ),
        VersionRef(
            namespace="workout_family_registry",
            version=workout_family_registry.registry_version,
        ),
        *additional_policy_versions,
    )

    return create_planning_context(
        context_id=context_id,
        athlete_id=current_state.athlete_id,
        schema_version=schema_version,
        as_of=as_of_utc,
        information_cutoff_at=cutoff,
        created_at=created_utc,
        planning_scope=planning_scope,
        decision_purpose=decision_purpose,
        source_snapshot_refs=(
            _state_source_ref(current_state),
            _gate_source_ref(entry_gate),
        ),
        engine_version=engine_version,
        rules_version=rules_version,
        evidence_pack_version=evidence_pack_version,
        sport_profile_versions=sport_profile_versions,
        policy_versions=tuple(policy_versions),
        critical_unknowns=critical_unknowns,
        runtime_projection=runtime_projection,
    )
