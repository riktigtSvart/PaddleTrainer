from datetime import datetime, timezone

from app.planning.domain.common.enums import (
    KnowledgeStatus,
    ProvenanceKind,
)
from app.planning.domain.evidence.models import (
    EvidenceQuality,
    SourceRecordRef,
    create_evidence_bundle,
    create_evidence_item,
)
from app.planning.domain.entry_gate.models import (
    AvailabilityConstraintStatus,
    EntryGatePolicy,
    EntryGateReasonCode,
    EntryMode,
    GlobalEntryGate,
    InterruptionStatus,
    ParticipationConstraintStatus,
    RecoveryConstraintStatus,
    StimulusGateSignal,
    StimulusGateStatus,
)
from app.planning.domain.entry_gate.resolver import assess_entry_gate
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


def _dt(day: int, hour: int = 12) -> datetime:
    return datetime(2026, 10, day, hour, tzinfo=timezone.utc)


def _session(evidence_id: str, day: int, duration_s: int = 3600):
    return create_evidence_item(
        evidence_id=evidence_id,
        athlete_id="athlete-1",
        evidence_type=EXECUTED_TRAINING_SESSION,
        observed_at=_dt(day),
        available_at=_dt(day),
        created_at=_dt(16, 20),
        source_ref=SourceRecordRef(
            source_system="history",
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
    session_days=(),
    *,
    recent_coverage=EvidenceCoverage.COMPLETE,
    anchor_coverage=EvidenceCoverage.COMPLETE,
):
    items = tuple(
        _session(f"s-{day}", day) for day in session_days
    )
    bundle = create_evidence_bundle(
        bundle_id="bundle-1",
        athlete_id="athlete-1",
        as_of=_dt(16, 18),
        information_cutoff_at=_dt(16, 18),
        created_at=_dt(16, 20),
        items=items,
    )
    return build_current_training_state(
        bundle=bundle,
        state_id="cts-1",
        schema_version="cts_v0.1",
        created_at=_dt(16, 21),
        recent_window=ObservationWindow(_dt(1, 0), _dt(16, 18)),
        load_anchor_window=ObservationWindow(_dt(1, 0), _dt(16, 18)),
        recent_training_coverage=recent_coverage,
        load_anchor_training_coverage=anchor_coverage,
    )


def _policy():
    return EntryGatePolicy(
        policy_version="entry_gate_policy_test_v0.1",
        recent_exposure_max_age_s_for_normal_start=3 * 24 * 3600,
    )


def _assess(state, **overrides):
    args = dict(
        current_state=state,
        decision_id="gate-1",
        schema_version="entry_gate_v0.1",
        created_at=_dt(16, 22),
        policy=_policy(),
        participation=ParticipationConstraintStatus.READY,
        recovery=RecoveryConstraintStatus.NONE,
        availability=AvailabilityConstraintStatus.AVAILABLE,
        interruption=InterruptionStatus.NONE,
        stimulus_keys=("AEROBIC", "STRENGTH"),
        stimulus_signals=(),
    )
    args.update(overrides)
    return assess_entry_gate(**args)


def test_recent_verified_exposure_supports_normal_start() -> None:
    gate = _assess(_state((15,)))

    assert gate.global_gate == GlobalEntryGate.OPEN
    assert gate.entry_mode == EntryMode.NORMAL_START
    assert gate.reason_codes == (
        EntryGateReasonCode.NORMAL_START_SUPPORTED,
    )
    assert gate.verify_content_hash()


def test_stale_but_verified_history_yields_conservative_reanchor() -> None:
    gate = _assess(_state((5,)))

    assert gate.global_gate == GlobalEntryGate.OPEN_WITH_CONSTRAINTS
    assert gate.entry_mode == EntryMode.CONSERVATIVE_REANCHOR
    assert EntryGateReasonCode.RECENT_EXPOSURE_STALE in gate.reason_codes
    assert EntryGateReasonCode.RECOVERY_FIRST_REQUIRED not in gate.reason_codes


def test_partial_history_yields_reanchor_not_fatigue_diagnosis() -> None:
    gate = _assess(
        _state(
            (15,),
            anchor_coverage=EvidenceCoverage.PARTIAL,
        )
    )

    assert gate.entry_mode == EntryMode.CONSERVATIVE_REANCHOR
    assert gate.reason_codes == (
        EntryGateReasonCode.LOAD_ANCHOR_PARTIAL,
    )


def test_unknown_empty_history_is_data_limited_not_reduce() -> None:
    gate = _assess(
        _state(
            (),
            recent_coverage=EvidenceCoverage.UNKNOWN,
            anchor_coverage=EvidenceCoverage.UNKNOWN,
        )
    )

    assert gate.global_gate == GlobalEntryGate.OPEN_WITH_CONSTRAINTS
    assert gate.entry_mode == EntryMode.DATA_LIMITED
    assert gate.reason_codes == (
        EntryGateReasonCode.RECENT_EXPOSURE_UNKNOWN,
    )


def test_professional_review_required_is_not_rewritten_as_blocked() -> None:
    gate = _assess(
        _state((15,)),
        participation=(
            ParticipationConstraintStatus.PROFESSIONAL_REVIEW_REQUIRED
        ),
    )

    assert gate.global_gate == GlobalEntryGate.REVIEW_REQUIRED
    assert gate.global_gate != GlobalEntryGate.BLOCKED


def test_explicit_participation_block_blocks() -> None:
    gate = _assess(
        _state((15,)),
        participation=ParticipationConstraintStatus.BLOCKED,
    )

    assert gate.global_gate == GlobalEntryGate.BLOCKED
    assert all(
        item.status == StimulusGateStatus.SUSPEND
        for item in gate.stimulus_gates
    )


def test_recovery_first_is_hold_without_fabricated_stimulus_reduction() -> None:
    gate = _assess(
        _state((15,)),
        recovery=RecoveryConstraintStatus.RECOVERY_FIRST_REQUIRED,
    )

    assert gate.global_gate == GlobalEntryGate.HOLD
    assert gate.entry_mode == EntryMode.RECOVERY_FIRST
    assert all(
        item.status == StimulusGateStatus.UNKNOWN
        for item in gate.stimulus_gates
    )


def test_no_training_window_is_constraint_hold() -> None:
    gate = _assess(
        _state((15,)),
        availability=AvailabilityConstraintStatus.NO_TRAINING_WINDOW,
    )

    assert gate.global_gate == GlobalEntryGate.HOLD
    assert gate.entry_mode == EntryMode.CONSTRAINT_LIMITED


def test_return_from_interruption_is_distinct_mode() -> None:
    gate = _assess(
        _state((15,)),
        interruption=InterruptionStatus.RETURNING,
    )

    assert gate.global_gate == GlobalEntryGate.OPEN_WITH_CONSTRAINTS
    assert gate.entry_mode == EntryMode.RETURN_FROM_INTERRUPTION


def test_missing_stimulus_signal_remains_unknown() -> None:
    gate = _assess(_state((15,)))

    aerobic = gate.stimulus_gates[0]
    assert aerobic.status == StimulusGateStatus.UNKNOWN


def test_unknown_signal_prevents_build_allowed_promotion() -> None:
    gate = _assess(
        _state((15,)),
        stimulus_signals=(
            StimulusGateSignal(
                "AEROBIC",
                StimulusGateStatus.BUILD_ALLOWED,
                "positive_response",
                "response-1",
            ),
            StimulusGateSignal(
                "AEROBIC",
                StimulusGateStatus.UNKNOWN,
                "state_uncertain",
                "state-1",
            ),
        ),
    )

    aerobic = gate.stimulus_gates[0]
    assert aerobic.status == StimulusGateStatus.UNKNOWN
    assert (
        EntryGateReasonCode.STIMULUS_SIGNAL_CONFLICT.value
        in aerobic.reason_codes
    )


def test_hold_signal_dominates_unknown_without_forcing_reduce() -> None:
    gate = _assess(
        _state((15,)),
        stimulus_signals=(
            StimulusGateSignal(
                "STRENGTH",
                StimulusGateStatus.HOLD_ONLY,
                "weak_evidence_hold",
            ),
            StimulusGateSignal(
                "STRENGTH",
                StimulusGateStatus.UNKNOWN,
                "missing_reference",
            ),
        ),
    )

    strength = gate.stimulus_gates[1]
    assert strength.status == StimulusGateStatus.HOLD_ONLY
    assert strength.status != StimulusGateStatus.REDUCE_REQUIRED


def test_build_allowed_is_permission_not_global_progression() -> None:
    gate = _assess(
        _state((15,)),
        stimulus_signals=(
            StimulusGateSignal(
                "AEROBIC",
                StimulusGateStatus.BUILD_ALLOWED,
                "sufficient_evidence",
            ),
        ),
    )

    assert gate.stimulus_gates[0].status == StimulusGateStatus.BUILD_ALLOWED
    assert gate.global_gate == GlobalEntryGate.OPEN


def test_semantic_hash_ignores_generated_decision_id_and_created_at() -> None:
    state = _state((15,))
    first = _assess(state)

    second = assess_entry_gate(
        current_state=state,
        decision_id="gate-2",
        schema_version="entry_gate_v0.1",
        created_at=_dt(16, 23),
        policy=_policy(),
        participation=ParticipationConstraintStatus.READY,
        recovery=RecoveryConstraintStatus.NONE,
        availability=AvailabilityConstraintStatus.AVAILABLE,
        interruption=InterruptionStatus.NONE,
        stimulus_keys=("AEROBIC", "STRENGTH"),
    )

    assert first.content_hash == second.content_hash
