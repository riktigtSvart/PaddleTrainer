from collections import defaultdict
from datetime import datetime

from ..training_state.models import (
    CurrentTrainingState,
    EvidenceDomain,
    LoadAnchorStatus,
)
from .models import (
    AvailabilityConstraintStatus,
    EntryGateDecision,
    EntryGatePolicy,
    EntryGateReasonCode,
    EntryMode,
    GlobalEntryGate,
    InterruptionStatus,
    ParticipationConstraintStatus,
    RecoveryConstraintStatus,
    StimulusGateDecision,
    StimulusGateSignal,
    StimulusGateStatus,
    finalize_entry_gate_decision,
)


def _training_age_s(
    state: CurrentTrainingState,
) -> int | None:
    for summary in state.evidence_domains:
        if summary.domain == EvidenceDomain.TRAINING_EXPOSURE:
            return summary.age_s_at_cutoff
    return None


def _resolve_stimulus_gate(
    stimulus_key: str,
    signals: tuple[StimulusGateSignal, ...],
    *,
    global_gate: GlobalEntryGate,
) -> StimulusGateDecision:
    selected = tuple(
        signal for signal in signals if signal.stimulus_key == stimulus_key
    )

    if global_gate == GlobalEntryGate.BLOCKED:
        return StimulusGateDecision(
            stimulus_key=stimulus_key,
            status=StimulusGateStatus.SUSPEND,
            reason_codes=(
                EntryGateReasonCode.GLOBAL_BLOCK_APPLIED_TO_STIMULUS.value,
            ),
            source_refs=tuple(
                sorted(
                    {
                        signal.source_ref
                        for signal in selected
                        if signal.source_ref is not None
                    }
                )
            ),
        )

    if not selected:
        return StimulusGateDecision(
            stimulus_key=stimulus_key,
            status=StimulusGateStatus.UNKNOWN,
            reason_codes=(
                EntryGateReasonCode.STIMULUS_SIGNAL_UNKNOWN.value,
            ),
            source_refs=(),
        )

    statuses = {signal.status for signal in selected}
    reason_codes = [signal.reason_code for signal in selected]

    # Restrictive evidence dominates permissive evidence. UNKNOWN cannot grant
    # BUILD_ALLOWED; this preserves uncertainty without automatically reducing.
    if StimulusGateStatus.SUSPEND in statuses:
        resolved = StimulusGateStatus.SUSPEND
    elif StimulusGateStatus.REDUCE_REQUIRED in statuses:
        resolved = StimulusGateStatus.REDUCE_REQUIRED
    elif StimulusGateStatus.CONSOLIDATE in statuses:
        resolved = StimulusGateStatus.CONSOLIDATE
    elif StimulusGateStatus.HOLD_ONLY in statuses:
        resolved = StimulusGateStatus.HOLD_ONLY
    elif StimulusGateStatus.UNKNOWN in statuses:
        resolved = StimulusGateStatus.UNKNOWN
    else:
        resolved = StimulusGateStatus.BUILD_ALLOWED

    if len(statuses) > 1:
        reason_codes.append(
            EntryGateReasonCode.STIMULUS_SIGNAL_CONFLICT.value
        )

    return StimulusGateDecision(
        stimulus_key=stimulus_key,
        status=resolved,
        reason_codes=tuple(dict.fromkeys(reason_codes)),
        source_refs=tuple(
            sorted(
                {
                    signal.source_ref
                    for signal in selected
                    if signal.source_ref is not None
                }
            )
        ),
    )


def _resolve_global(
    *,
    state: CurrentTrainingState,
    policy: EntryGatePolicy,
    participation: ParticipationConstraintStatus,
    recovery: RecoveryConstraintStatus,
    availability: AvailabilityConstraintStatus,
    interruption: InterruptionStatus,
) -> tuple[
    GlobalEntryGate,
    EntryMode,
    tuple[EntryGateReasonCode, ...],
]:
    reasons: list[EntryGateReasonCode] = []

    # Explicit upstream safety/readiness decisions have precedence. The gate
    # does not diagnose or reinterpret their medical meaning.
    if participation == ParticipationConstraintStatus.BLOCKED:
        return (
            GlobalEntryGate.BLOCKED,
            EntryMode.CONSTRAINT_LIMITED,
            (EntryGateReasonCode.PARTICIPATION_BLOCKED,),
        )

    if (
        participation
        == ParticipationConstraintStatus.PROFESSIONAL_REVIEW_REQUIRED
    ):
        return (
            GlobalEntryGate.REVIEW_REQUIRED,
            EntryMode.CONSTRAINT_LIMITED,
            (EntryGateReasonCode.PARTICIPATION_REVIEW_REQUIRED,),
        )

    if availability == AvailabilityConstraintStatus.NO_TRAINING_WINDOW:
        return (
            GlobalEntryGate.HOLD,
            EntryMode.CONSTRAINT_LIMITED,
            (EntryGateReasonCode.NO_TRAINING_WINDOW,),
        )

    if recovery == RecoveryConstraintStatus.RECOVERY_FIRST_REQUIRED:
        return (
            GlobalEntryGate.HOLD,
            EntryMode.RECOVERY_FIRST,
            (EntryGateReasonCode.RECOVERY_FIRST_REQUIRED,),
        )

    if interruption == InterruptionStatus.RETURNING:
        return (
            GlobalEntryGate.OPEN_WITH_CONSTRAINTS,
            EntryMode.RETURN_FROM_INTERRUPTION,
            (EntryGateReasonCode.RETURN_FROM_INTERRUPTION,),
        )

    if recovery == RecoveryConstraintStatus.REDUCE_REQUIRED:
        reasons.append(EntryGateReasonCode.RECOVERY_REDUCTION_REQUIRED)
        return (
            GlobalEntryGate.OPEN_WITH_CONSTRAINTS,
            EntryMode.RECOVERY_FIRST,
            tuple(reasons),
        )

    if (
        participation
        == ParticipationConstraintStatus.READY_WITH_CONSTRAINTS
    ):
        reasons.append(
            EntryGateReasonCode.PARTICIPATION_READY_WITH_CONSTRAINTS
        )
        return (
            GlobalEntryGate.OPEN_WITH_CONSTRAINTS,
            EntryMode.CONSTRAINT_LIMITED,
            tuple(reasons),
        )

    if participation == ParticipationConstraintStatus.OBSERVATION_FIRST:
        reasons.append(EntryGateReasonCode.PARTICIPATION_OBSERVATION_FIRST)
        return (
            GlobalEntryGate.OPEN_WITH_CONSTRAINTS,
            EntryMode.DATA_LIMITED,
            tuple(reasons),
        )

    if availability == AvailabilityConstraintStatus.LIMITED:
        reasons.append(EntryGateReasonCode.AVAILABILITY_LIMITED)
        return (
            GlobalEntryGate.OPEN_WITH_CONSTRAINTS,
            EntryMode.CONSTRAINT_LIMITED,
            tuple(reasons),
        )

    # Unknown upstream context constrains confidence but does not become a
    # fatigue diagnosis, reduction order, or automatic block.
    if participation == ParticipationConstraintStatus.UNKNOWN:
        reasons.append(EntryGateReasonCode.PARTICIPATION_UNKNOWN)
    if recovery == RecoveryConstraintStatus.UNKNOWN:
        reasons.append(EntryGateReasonCode.RECOVERY_UNKNOWN)
    if availability == AvailabilityConstraintStatus.UNKNOWN:
        reasons.append(EntryGateReasonCode.AVAILABILITY_UNKNOWN)
    if interruption == InterruptionStatus.UNKNOWN:
        reasons.append(EntryGateReasonCode.INTERRUPTION_UNKNOWN)

    if reasons:
        return (
            GlobalEntryGate.OPEN_WITH_CONSTRAINTS,
            EntryMode.DATA_LIMITED,
            tuple(reasons),
        )

    training_age_s = _training_age_s(state)
    anchor = state.load_anchor.status

    if anchor == LoadAnchorStatus.PARTIAL_EXPOSURE:
        return (
            GlobalEntryGate.OPEN_WITH_CONSTRAINTS,
            EntryMode.CONSERVATIVE_REANCHOR,
            (EntryGateReasonCode.LOAD_ANCHOR_PARTIAL,),
        )

    if anchor == LoadAnchorStatus.UNKNOWN:
        reason = (
            EntryGateReasonCode.RECENT_EXPOSURE_UNKNOWN
            if training_age_s is None
            else EntryGateReasonCode.LOAD_ANCHOR_UNKNOWN
        )
        return (
            GlobalEntryGate.OPEN_WITH_CONSTRAINTS,
            EntryMode.DATA_LIMITED,
            (reason,),
        )

    if anchor == LoadAnchorStatus.VERIFIED_ZERO_EXPOSURE:
        return (
            GlobalEntryGate.OPEN_WITH_CONSTRAINTS,
            EntryMode.DATA_LIMITED,
            (EntryGateReasonCode.VERIFIED_ZERO_EXPOSURE,),
        )

    if training_age_s is None:
        return (
            GlobalEntryGate.OPEN_WITH_CONSTRAINTS,
            EntryMode.DATA_LIMITED,
            (EntryGateReasonCode.RECENT_EXPOSURE_UNKNOWN,),
        )

    if (
        training_age_s
        > policy.recent_exposure_max_age_s_for_normal_start
    ):
        return (
            GlobalEntryGate.OPEN_WITH_CONSTRAINTS,
            EntryMode.CONSERVATIVE_REANCHOR,
            (EntryGateReasonCode.RECENT_EXPOSURE_STALE,),
        )

    if (
        policy.require_verified_load_anchor_for_normal_start
        and anchor != LoadAnchorStatus.VERIFIED_EXPOSURE
    ):
        return (
            GlobalEntryGate.OPEN_WITH_CONSTRAINTS,
            EntryMode.DATA_LIMITED,
            (EntryGateReasonCode.LOAD_ANCHOR_UNKNOWN,),
        )

    return (
        GlobalEntryGate.OPEN,
        EntryMode.NORMAL_START,
        (EntryGateReasonCode.NORMAL_START_SUPPORTED,),
    )


def assess_entry_gate(
    *,
    current_state: CurrentTrainingState,
    decision_id: str,
    schema_version: str,
    created_at: datetime,
    policy: EntryGatePolicy,
    participation: ParticipationConstraintStatus,
    recovery: RecoveryConstraintStatus,
    availability: AvailabilityConstraintStatus,
    interruption: InterruptionStatus,
    stimulus_keys: tuple[str, ...] = (),
    stimulus_signals: tuple[StimulusGateSignal, ...] = (),
) -> EntryGateDecision:
    if not current_state.verify_content_hash():
        raise ValueError("CurrentTrainingState hash does not verify.")

    if len(set(stimulus_keys)) != len(stimulus_keys):
        raise ValueError("stimulus_keys must be unique.")

    declared = set(stimulus_keys)
    undeclared = {
        signal.stimulus_key
        for signal in stimulus_signals
        if signal.stimulus_key not in declared
    }
    if undeclared:
        raise ValueError(
            "Stimulus signal supplied for undeclared stimulus key: "
            + ", ".join(sorted(undeclared))
        )

    global_gate, entry_mode, reasons = _resolve_global(
        state=current_state,
        policy=policy,
        participation=participation,
        recovery=recovery,
        availability=availability,
        interruption=interruption,
    )

    stimulus_gates = tuple(
        _resolve_stimulus_gate(
            stimulus_key,
            stimulus_signals,
            global_gate=global_gate,
        )
        for stimulus_key in stimulus_keys
    )

    return finalize_entry_gate_decision(
        decision_id=decision_id,
        athlete_id=current_state.athlete_id,
        schema_version=schema_version,
        as_of=current_state.as_of,
        information_cutoff_at=current_state.information_cutoff_at,
        created_at=created_at,
        global_gate=global_gate,
        entry_mode=entry_mode,
        stimulus_gates=stimulus_gates,
        reason_codes=reasons,
        current_training_state_hash=current_state.content_hash,
        policy_version=policy.policy_version,
    )
