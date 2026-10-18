from datetime import datetime, timezone

import pytest

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
    InterruptionStatus,
    ParticipationConstraintStatus,
    RecoveryConstraintStatus,
    StimulusGateSignal,
    StimulusGateStatus,
)
from app.planning.domain.entry_gate.resolver import assess_entry_gate
from app.planning.domain.training_state.evidence import EXECUTED_TRAINING_SESSION
from app.planning.domain.training_state.models import EvidenceCoverage, ObservationWindow
from app.planning.domain.training_state.resolver import build_current_training_state


def _dt(day: int, hour: int = 12):
    return datetime(2026, 10, day, hour, tzinfo=timezone.utc)


def _state():
    item = create_evidence_item(
        evidence_id="s1",
        athlete_id="athlete-1",
        evidence_type=EXECUTED_TRAINING_SESSION,
        observed_at=_dt(15),
        available_at=_dt(15),
        created_at=_dt(16, 20),
        source_ref=SourceRecordRef("test", "s1"),
        provenance=ProvenanceKind.SOURCE,
        knowledge_status=KnowledgeStatus.KNOWN,
        quality=EvidenceQuality.HIGH,
        payload={
            "schema_version": "executed_training_session_evidence_v0.1",
            "session_id": "s1",
            "modality_key": "KAYAK",
            "duration_status": "known",
            "duration_s": 3600,
        },
    )
    bundle = create_evidence_bundle(
        bundle_id="b1",
        athlete_id="athlete-1",
        as_of=_dt(16, 18),
        information_cutoff_at=_dt(16, 18),
        created_at=_dt(16, 20),
        items=(item,),
    )
    return build_current_training_state(
        bundle=bundle,
        state_id="cts-1",
        schema_version="cts_v0.1",
        created_at=_dt(16, 21),
        recent_window=ObservationWindow(_dt(10, 0), _dt(16, 18)),
        load_anchor_window=ObservationWindow(_dt(10, 0), _dt(16, 18)),
        recent_training_coverage=EvidenceCoverage.COMPLETE,
        load_anchor_training_coverage=EvidenceCoverage.COMPLETE,
    )


def _base():
    return dict(
        current_state=_state(),
        decision_id="gate-1",
        schema_version="entry_gate_v0.1",
        created_at=_dt(16, 22),
        policy=EntryGatePolicy("policy-v1", 3 * 24 * 3600),
        participation=ParticipationConstraintStatus.READY,
        recovery=RecoveryConstraintStatus.NONE,
        availability=AvailabilityConstraintStatus.AVAILABLE,
        interruption=InterruptionStatus.NONE,
        stimulus_keys=("AEROBIC",),
    )


def test_duplicate_stimulus_keys_are_rejected() -> None:
    args = _base()
    args["stimulus_keys"] = ("AEROBIC", "AEROBIC")
    with pytest.raises(ValueError, match="unique"):
        assess_entry_gate(**args)


def test_signal_for_undeclared_stimulus_is_rejected() -> None:
    args = _base()
    args["stimulus_signals"] = (
        StimulusGateSignal(
            "STRENGTH",
            StimulusGateStatus.HOLD_ONLY,
            "reason",
        ),
    )
    with pytest.raises(ValueError, match="undeclared"):
        assess_entry_gate(**args)


def test_policy_rejects_negative_freshness_threshold() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        EntryGatePolicy("policy-v1", -1)
