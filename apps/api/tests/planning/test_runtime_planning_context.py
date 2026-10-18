from dataclasses import replace
from datetime import datetime, timezone

import pytest

from app.planning.domain.common.enums import (
    DecisionPurpose,
    KnowledgeStatus,
    PlanningScope,
    ProvenanceKind,
)
from app.planning.domain.common.refs import SourceSnapshotRef, VersionRef
from app.planning.domain.context.models import (
    TrainingSpaceStatus,
    UnresolvedPlanningDimension,
    create_planning_context,
)
from app.planning.domain.context.runtime import build_runtime_planning_context
from app.planning.domain.entry_gate import (
    AvailabilityConstraintStatus,
    EntryGatePolicy,
    InterruptionStatus,
    ParticipationConstraintStatus,
    RecoveryConstraintStatus,
    StimulusGateSignal,
    StimulusGateStatus,
    assess_entry_gate,
)
from app.planning.domain.evidence.models import (
    EvidenceQuality,
    SourceRecordRef,
    create_evidence_bundle,
    create_evidence_item,
)
from app.planning.domain.persistence.snapshot_codec import (
    decode_planning_context,
    encode_planning_context,
)
from app.planning.domain.training_state.evidence import (
    EXECUTED_TRAINING_SESSION,
)
from app.planning.domain.training_state.models import (
    EvidenceCoverage,
    ObservationWindow,
)
from app.planning.domain.training_state.resolver import (
    build_current_training_state,
)
from app.planning.domain.workout_family import (
    KAYAK_EASY_TECHNICAL_KEY,
    STRENGTH_REFERENCE_AND_DEVELOPMENT_KEY,
    builtin_workout_family_registry_v0_1,
)
from app.planning.domain.workout_family.models import (
    FamilyEntryGateStatus,
)


def _dt(day: int, hour: int = 12) -> datetime:
    return datetime(2026, 10, day, hour, tzinfo=timezone.utc)


def _training_item(
    *,
    evidence_id: str = "session-1",
    day: int = 16,
    duration_s: int = 3600,
):
    return create_evidence_item(
        evidence_id=evidence_id,
        athlete_id="athlete-1",
        evidence_type=EXECUTED_TRAINING_SESSION,
        observed_at=_dt(day, 8),
        available_at=_dt(day, 8),
        created_at=_dt(17, 5),
        source_ref=SourceRecordRef(
            source_system="test_history",
            source_record_id=evidence_id,
        ),
        provenance=ProvenanceKind.SOURCE,
        knowledge_status=KnowledgeStatus.KNOWN,
        quality=EvidenceQuality.HIGH,
        payload={
            "schema_version":
                "executed_training_session_evidence_v0.1",
            "session_id": evidence_id,
            "modality_key": "KAYAK",
            "duration_status": "known",
            "duration_s": duration_s,
        },
    )


def _state(
    *,
    state_id: str = "cts-1",
    coverage: EvidenceCoverage = EvidenceCoverage.COMPLETE,
):
    bundle = create_evidence_bundle(
        bundle_id="bundle-1",
        athlete_id="athlete-1",
        as_of=_dt(17, 5),
        information_cutoff_at=_dt(17, 5),
        created_at=_dt(17, 5),
        items=(_training_item(),),
    )
    return build_current_training_state(
        bundle=bundle,
        state_id=state_id,
        schema_version="cts_v0.1",
        created_at=_dt(17, 5),
        recent_window=ObservationWindow(
            _dt(10, 0),
            _dt(17, 5),
        ),
        load_anchor_window=ObservationWindow(
            _dt(10, 0),
            _dt(17, 5),
        ),
        recent_training_coverage=coverage,
        load_anchor_training_coverage=coverage,
    )


def _gate(
    state,
    *,
    decision_id: str = "gate-1",
    aerobic_status: StimulusGateStatus = StimulusGateStatus.BUILD_ALLOWED,
    strength_status: StimulusGateStatus = StimulusGateStatus.HOLD_ONLY,
):
    return assess_entry_gate(
        current_state=state,
        decision_id=decision_id,
        schema_version="entry_gate_v0.1",
        created_at=_dt(17, 6),
        policy=EntryGatePolicy(
            policy_version="entry_gate_policy_v0.1",
            recent_exposure_max_age_s_for_normal_start=7 * 24 * 3600,
        ),
        participation=ParticipationConstraintStatus.READY,
        recovery=RecoveryConstraintStatus.NONE,
        availability=AvailabilityConstraintStatus.AVAILABLE,
        interruption=InterruptionStatus.NONE,
        stimulus_keys=("AEROBIC", "STRENGTH"),
        stimulus_signals=(
            StimulusGateSignal(
                stimulus_key="AEROBIC",
                status=aerobic_status,
                reason_code="TEST_AEROBIC",
                source_ref="test:aerobic",
            ),
            StimulusGateSignal(
                stimulus_key="STRENGTH",
                status=strength_status,
                reason_code="TEST_STRENGTH",
                source_ref="test:strength",
            ),
        ),
    )


def _context(
    state=None,
    gate=None,
    **overrides,
):
    state = state or _state()
    gate = gate or _gate(state)
    values = dict(
        current_state=state,
        entry_gate=gate,
        workout_family_registry=builtin_workout_family_registry_v0_1(),
        context_id="apc-runtime-1",
        schema_version="apc_v0.1",
        as_of=_dt(17, 7),
        created_at=_dt(17, 7),
        planning_scope=PlanningScope.MICROCYCLE,
        decision_purpose=DecisionPurpose.CREATE_MICROCYCLE,
        engine_version=VersionRef("planner_engine", "planner_engine_v0.1"),
        rules_version=VersionRef("planning_rules", "planning_rules_v0.1"),
        evidence_pack_version=VersionRef(
            "evidence_pack", "training_planning_evidence_v0.1"
        ),
    )
    values.update(overrides)
    return build_runtime_planning_context(**values)


def test_runtime_context_links_state_gate_and_family_registry() -> None:
    state = _state()
    gate = _gate(state)
    registry = builtin_workout_family_registry_v0_1()
    context = _context(
        state=state,
        gate=gate,
        workout_family_registry=registry,
    )

    projection = context.runtime_projection
    assert projection is not None
    assert (
        projection.current_state.current_training_state_hash
        == state.content_hash
    )
    assert (
        projection.entry_gate.entry_gate_decision_hash
        == gate.content_hash
    )
    assert projection.workout_family_registry_hash == registry.content_hash
    assert context.verify_content_hash()


def test_runtime_context_projects_all_builtin_families() -> None:
    context = _context()
    projection = context.runtime_projection
    assert projection is not None

    keys = {item.family_key for item in projection.training_space.families}
    assert len(keys) == 4
    assert KAYAK_EASY_TECHNICAL_KEY in keys
    assert STRENGTH_REFERENCE_AND_DEVELOPMENT_KEY in keys


def test_build_allowed_aerobic_and_hold_strength_remain_distinct() -> None:
    context = _context()
    projection = context.runtime_projection
    assert projection is not None

    families = {
        item.family_key: item
        for item in projection.training_space.families
    }

    assert (
        families[KAYAK_EASY_TECHNICAL_KEY].entry_gate_status
        == FamilyEntryGateStatus.ELIGIBLE
    )
    assert (
        families[KAYAK_EASY_TECHNICAL_KEY].build_authorized_by_entry_gate
        is True
    )
    assert (
        families[STRENGTH_REFERENCE_AND_DEVELOPMENT_KEY]
        .entry_gate_status
        == FamilyEntryGateStatus.ELIGIBLE_WITH_CONSTRAINTS
    )
    assert (
        families[STRENGTH_REFERENCE_AND_DEVELOPMENT_KEY]
        .build_authorized_by_entry_gate
        is False
    )
    assert (
        projection.training_space.status
        == TrainingSpaceStatus.ENTRY_GATE_CONSTRAINED
    )


def test_runtime_training_space_is_not_final_authorization() -> None:
    context = _context()
    projection = context.runtime_projection
    assert projection is not None

    assert projection.training_space.final_authorization is False
    assert (
        UnresolvedPlanningDimension.PLANNING_AUTHORITY
        in projection.training_space.unresolved_dimensions
    )
    assert (
        UnresolvedPlanningDimension.SPORT_READINESS
        in projection.training_space.unresolved_dimensions
    )


def test_unknown_stimulus_gate_becomes_explicit_critical_unknown() -> None:
    state = _state()
    gate = _gate(
        state,
        strength_status=StimulusGateStatus.UNKNOWN,
    )
    context = _context(state=state, gate=gate)

    assert any(
        item.domain == "STIMULUS_GATE:STRENGTH"
        for item in context.critical_unknowns
    )


def test_partial_load_anchor_becomes_explicit_critical_unknown() -> None:
    state = _state(coverage=EvidenceCoverage.PARTIAL)
    gate = _gate(state)
    context = _context(state=state, gate=gate)

    assert any(
        item.domain == "CURRENT_LOAD_ANCHOR"
        for item in context.critical_unknowns
    )


def test_gate_must_reference_supplied_state_hash() -> None:
    state = _state()
    different_state = _state(coverage=EvidenceCoverage.PARTIAL)
    wrong_gate = _gate(different_state)

    with pytest.raises(ValueError, match="does not reference"):
        _context(state=state, gate=wrong_gate)


def test_tampered_registry_is_rejected() -> None:
    registry = builtin_workout_family_registry_v0_1()
    tampered = replace(registry, content_hash="0" * 64)

    with pytest.raises(ValueError, match="Registry hash"):
        _context(workout_family_registry=tampered)


def test_runtime_context_round_trips_through_snapshot_codec() -> None:
    context = _context()
    record = encode_planning_context(context)
    restored = decode_planning_context(record)

    assert restored == context
    assert restored.runtime_projection is not None
    assert restored.verify_content_hash()


def test_same_semantic_sources_with_different_ids_keep_context_hash() -> None:
    first_state = _state(state_id="state-a")
    second_state = _state(state_id="state-b")
    assert first_state.content_hash == second_state.content_hash

    first_gate = _gate(first_state, decision_id="gate-a")
    second_gate = _gate(second_state, decision_id="gate-b")
    assert first_gate.content_hash == second_gate.content_hash

    first = _context(
        state=first_state,
        gate=first_gate,
        context_id="context-a",
    )
    second = _context(
        state=second_state,
        gate=second_gate,
        context_id="context-b",
    )

    assert first.content_hash == second.content_hash


def test_derived_snapshot_may_be_created_after_information_cutoff() -> None:
    source = SourceSnapshotRef(
        domain="CURRENT_TRAINING_STATE",
        object_id="cts-1",
        object_version="cts_v0.1",
        as_of=_dt(17, 5),
        information_cutoff_at=_dt(17, 5),
        available_at=_dt(17, 6),
        content_hash="a" * 64,
    )

    context = create_planning_context(
        context_id="context-derived",
        athlete_id="athlete-1",
        schema_version="apc_v0.1",
        as_of=_dt(17, 7),
        information_cutoff_at=_dt(17, 5),
        created_at=_dt(17, 7),
        planning_scope=PlanningScope.MICROCYCLE,
        decision_purpose=DecisionPurpose.CREATE_MICROCYCLE,
        source_snapshot_refs=(source,),
        engine_version=VersionRef("engine", "v0.1"),
        rules_version=VersionRef("rules", "v0.1"),
        evidence_pack_version=VersionRef("evidence", "v0.1"),
    )

    assert context.verify_content_hash()


def test_source_snapshot_after_context_as_of_is_rejected() -> None:
    source = SourceSnapshotRef(
        domain="CURRENT_TRAINING_STATE",
        object_id="cts-1",
        object_version="cts_v0.1",
        as_of=_dt(17, 5),
        information_cutoff_at=_dt(17, 5),
        available_at=_dt(17, 8),
        content_hash="a" * 64,
    )

    with pytest.raises(ValueError, match="as_of time"):
        create_planning_context(
            context_id="context-derived",
            athlete_id="athlete-1",
            schema_version="apc_v0.1",
            as_of=_dt(17, 7),
            information_cutoff_at=_dt(17, 5),
            created_at=_dt(17, 7),
            planning_scope=PlanningScope.MICROCYCLE,
            decision_purpose=DecisionPurpose.CREATE_MICROCYCLE,
            source_snapshot_refs=(source,),
            engine_version=VersionRef("engine", "v0.1"),
            rules_version=VersionRef("rules", "v0.1"),
            evidence_pack_version=VersionRef("evidence", "v0.1"),
        )
