from ..entry_gate.models import (
    EntryGateDecision,
    GlobalEntryGate,
    StimulusGateStatus,
)
from .models import (
    FamilyEntryGateAssessment,
    FamilyEntryGateStatus,
    WorkoutFamilyDefinition,
)


def assess_family_entry_gate(
    *,
    family: WorkoutFamilyDefinition,
    entry_gate: EntryGateDecision,
) -> FamilyEntryGateAssessment:
    """Assess only the EntryGate contribution to family usability.

    This is deliberately not the final available training space. Sport-entry
    readiness, environment, equipment, availability and planning authority are
    separate intersections that later planning-context layers must apply.
    """
    if not entry_gate.verify_content_hash():
        raise ValueError("EntryGateDecision hash does not verify.")

    if entry_gate.global_gate == GlobalEntryGate.BLOCKED:
        return FamilyEntryGateAssessment(
            family_ref=family.family_ref,
            entry_gate_decision_hash=entry_gate.content_hash,
            status=FamilyEntryGateStatus.NOT_ELIGIBLE,
            stimulus_gate_statuses=(),
            reason_codes=("GLOBAL_ENTRY_GATE_BLOCKED",),
            build_authorized=False,
            dose_reduction_required=False,
        )

    if entry_gate.global_gate == GlobalEntryGate.HOLD:
        return FamilyEntryGateAssessment(
            family_ref=family.family_ref,
            entry_gate_decision_hash=entry_gate.content_hash,
            status=FamilyEntryGateStatus.DEFERRED_BY_GLOBAL_GATE,
            stimulus_gate_statuses=(),
            reason_codes=("GLOBAL_ENTRY_GATE_HOLD",),
            build_authorized=False,
            dose_reduction_required=False,
        )

    if entry_gate.global_gate == GlobalEntryGate.REVIEW_REQUIRED:
        return FamilyEntryGateAssessment(
            family_ref=family.family_ref,
            entry_gate_decision_hash=entry_gate.content_hash,
            status=FamilyEntryGateStatus.REVIEW_REQUIRED,
            stimulus_gate_statuses=(),
            reason_codes=("GLOBAL_ENTRY_GATE_REVIEW_REQUIRED",),
            build_authorized=False,
            dose_reduction_required=False,
        )

    gates_by_key = {
        gate.stimulus_key: gate
        for gate in entry_gate.stimulus_gates
    }

    required = []
    missing = []
    for key in family.required_stimulus_keys:
        gate = gates_by_key.get(key)
        if gate is None:
            missing.append(key)
        else:
            required.append(gate)

    statuses = {gate.status for gate in required}
    status_pairs = tuple(
        (gate.stimulus_key, gate.status.value)
        for gate in sorted(
            required,
            key=lambda item: item.stimulus_key,
        )
    )

    if StimulusGateStatus.SUSPEND in statuses:
        status = FamilyEntryGateStatus.NOT_ELIGIBLE
        build_authorized = False
        reduction_required = False
        reason_codes = ("REQUIRED_STIMULUS_SUSPENDED",)
    elif StimulusGateStatus.REDUCE_REQUIRED in statuses:
        status = FamilyEntryGateStatus.REDUCTION_ONLY
        build_authorized = False
        reduction_required = True
        reason_codes = ("REQUIRED_STIMULUS_REDUCTION_REQUIRED",)
    else:
        build_authorized = (
            not missing
            and bool(required)
            and all(
                gate.status == StimulusGateStatus.BUILD_ALLOWED
                for gate in required
            )
            and entry_gate.global_gate == GlobalEntryGate.OPEN
        )
        reduction_required = False

        constrained_statuses = {
            StimulusGateStatus.HOLD_ONLY,
            StimulusGateStatus.CONSOLIDATE,
            StimulusGateStatus.UNKNOWN,
        }

        if (
            missing
            or statuses.intersection(constrained_statuses)
            or entry_gate.global_gate
            == GlobalEntryGate.OPEN_WITH_CONSTRAINTS
        ):
            status = FamilyEntryGateStatus.ELIGIBLE_WITH_CONSTRAINTS
            reason_codes = tuple(
                sorted(
                    {
                        *(
                            f"MISSING_STIMULUS_GATE:{key}"
                            for key in missing
                        ),
                        *(
                            f"STIMULUS_GATE:{gate.stimulus_key}:"
                            f"{gate.status.value}"
                            for gate in required
                            if gate.status in constrained_statuses
                        ),
                        *(
                            ("GLOBAL_OPEN_WITH_CONSTRAINTS",)
                            if entry_gate.global_gate
                            == GlobalEntryGate.OPEN_WITH_CONSTRAINTS
                            else ()
                        ),
                    }
                )
            )
        else:
            status = FamilyEntryGateStatus.ELIGIBLE
            reason_codes = ("ENTRY_GATE_ELIGIBLE",)

    return FamilyEntryGateAssessment(
        family_ref=family.family_ref,
        entry_gate_decision_hash=entry_gate.content_hash,
        status=status,
        stimulus_gate_statuses=status_pairs,
        reason_codes=reason_codes,
        build_authorized=build_authorized,
        dose_reduction_required=reduction_required,
    )
