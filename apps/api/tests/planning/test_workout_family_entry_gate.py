from datetime import datetime, timezone

from app.planning.domain.entry_gate.models import (
    EntryMode,
    GlobalEntryGate,
    StimulusGateDecision,
    StimulusGateStatus,
    finalize_entry_gate_decision,
)
from app.planning.domain.workout_family.builtins import (
    KAYAK_EASY_TECHNICAL_KEY,
    STRENGTH_REFERENCE_AND_DEVELOPMENT_KEY,
    builtin_workout_family_registry_v0_1,
)
from app.planning.domain.workout_family.eligibility import (
    assess_family_entry_gate,
)
from app.planning.domain.workout_family.models import (
    FamilyEntryGateStatus,
)


def _dt(hour: int) -> datetime:
    return datetime(2026, 10, 17, hour, tzinfo=timezone.utc)


def _gate(
    *,
    global_gate=GlobalEntryGate.OPEN,
    mode=EntryMode.NORMAL_START,
    aerobic=StimulusGateStatus.BUILD_ALLOWED,
    strength=StimulusGateStatus.BUILD_ALLOWED,
):
    return finalize_entry_gate_decision(
        decision_id="gate-1",
        athlete_id="athlete-1",
        schema_version="entry_gate_v0.1",
        as_of=_dt(5),
        information_cutoff_at=_dt(5),
        created_at=_dt(6),
        global_gate=global_gate,
        entry_mode=mode,
        stimulus_gates=(
            StimulusGateDecision(
                stimulus_key="AEROBIC",
                status=aerobic,
                reason_codes=("test",),
                source_refs=(),
            ),
            StimulusGateDecision(
                stimulus_key="STRENGTH",
                status=strength,
                reason_codes=("test",),
                source_refs=(),
            ),
        ),
        reason_codes=(),
        current_training_state_hash="a" * 64,
        policy_version="entry_gate_policy_v0.1",
    )


def test_open_build_allowed_family_is_entry_gate_eligible() -> None:
    family = builtin_workout_family_registry_v0_1().get(
        KAYAK_EASY_TECHNICAL_KEY
    )
    assessment = assess_family_entry_gate(
        family=family,
        entry_gate=_gate(),
    )

    assert assessment.status == FamilyEntryGateStatus.ELIGIBLE
    assert assessment.build_authorized is True
    assert assessment.dose_reduction_required is False


def test_open_with_constraints_never_promotes_build_authority() -> None:
    family = builtin_workout_family_registry_v0_1().get(
        KAYAK_EASY_TECHNICAL_KEY
    )
    assessment = assess_family_entry_gate(
        family=family,
        entry_gate=_gate(
            global_gate=GlobalEntryGate.OPEN_WITH_CONSTRAINTS,
            mode=EntryMode.CONSERVATIVE_REANCHOR,
        ),
    )

    assert (
        assessment.status
        == FamilyEntryGateStatus.ELIGIBLE_WITH_CONSTRAINTS
    )
    assert assessment.build_authorized is False


def test_unknown_required_stimulus_is_constrained_not_reduced() -> None:
    family = builtin_workout_family_registry_v0_1().get(
        KAYAK_EASY_TECHNICAL_KEY
    )
    assessment = assess_family_entry_gate(
        family=family,
        entry_gate=_gate(aerobic=StimulusGateStatus.UNKNOWN),
    )

    assert (
        assessment.status
        == FamilyEntryGateStatus.ELIGIBLE_WITH_CONSTRAINTS
    )
    assert assessment.build_authorized is False
    assert assessment.dose_reduction_required is False


def test_reduce_required_yields_reduction_only() -> None:
    family = builtin_workout_family_registry_v0_1().get(
        STRENGTH_REFERENCE_AND_DEVELOPMENT_KEY
    )
    assessment = assess_family_entry_gate(
        family=family,
        entry_gate=_gate(
            strength=StimulusGateStatus.REDUCE_REQUIRED
        ),
    )

    assert assessment.status == FamilyEntryGateStatus.REDUCTION_ONLY
    assert assessment.build_authorized is False
    assert assessment.dose_reduction_required is True


def test_suspended_required_stimulus_makes_family_not_eligible() -> None:
    family = builtin_workout_family_registry_v0_1().get(
        KAYAK_EASY_TECHNICAL_KEY
    )
    assessment = assess_family_entry_gate(
        family=family,
        entry_gate=_gate(aerobic=StimulusGateStatus.SUSPEND),
    )

    assert assessment.status == FamilyEntryGateStatus.NOT_ELIGIBLE


def test_global_hold_defers_training_family() -> None:
    family = builtin_workout_family_registry_v0_1().get(
        KAYAK_EASY_TECHNICAL_KEY
    )
    assessment = assess_family_entry_gate(
        family=family,
        entry_gate=_gate(
            global_gate=GlobalEntryGate.HOLD,
            mode=EntryMode.RECOVERY_FIRST,
        ),
    )

    assert (
        assessment.status
        == FamilyEntryGateStatus.DEFERRED_BY_GLOBAL_GATE
    )


def test_global_block_makes_family_not_eligible() -> None:
    family = builtin_workout_family_registry_v0_1().get(
        KAYAK_EASY_TECHNICAL_KEY
    )
    assessment = assess_family_entry_gate(
        family=family,
        entry_gate=_gate(global_gate=GlobalEntryGate.BLOCKED),
    )

    assert assessment.status == FamilyEntryGateStatus.NOT_ELIGIBLE


def test_review_required_stays_review_required() -> None:
    family = builtin_workout_family_registry_v0_1().get(
        KAYAK_EASY_TECHNICAL_KEY
    )
    assessment = assess_family_entry_gate(
        family=family,
        entry_gate=_gate(
            global_gate=GlobalEntryGate.REVIEW_REQUIRED
        ),
    )

    assert assessment.status == FamilyEntryGateStatus.REVIEW_REQUIRED


def test_assessment_is_only_entry_gate_component_not_final_authorization() -> None:
    family = builtin_workout_family_registry_v0_1().get(
        KAYAK_EASY_TECHNICAL_KEY
    )
    assessment = assess_family_entry_gate(
        family=family,
        entry_gate=_gate(),
    )

    assert not hasattr(assessment, "environment_authorized")
    assert not hasattr(assessment, "sport_readiness_authorized")
    assert not hasattr(assessment, "planning_authority_authorized")
