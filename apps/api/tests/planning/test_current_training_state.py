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
from app.planning.domain.training_state.evidence import (
    EXECUTED_TRAINING_SESSION,
    MEASUREMENT_OBSERVATION,
    SESSION_FEEDBACK,
)
from app.planning.domain.training_state.models import (
    DomainCoverageDeclaration,
    EvidenceCoverage,
    EvidenceDomain,
    LoadAnchorStatus,
    ObservationWindow,
)
from app.planning.domain.training_state.resolver import (
    build_current_training_state,
)


def _dt(day: int, hour: int = 12) -> datetime:
    return datetime(2026, 10, day, hour, tzinfo=timezone.utc)


def _training(
    evidence_id: str,
    day: int,
    *,
    modality: str = "KAYAK",
    duration_s: int | None = 3600,
    duration_status: KnowledgeStatus = KnowledgeStatus.KNOWN,
):
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
            "modality_key": modality,
            "duration_status": duration_status.value,
            "duration_s": duration_s,
        },
    )


def _generic(evidence_id: str, evidence_type: str, day: int):
    return create_evidence_item(
        evidence_id=evidence_id,
        athlete_id="athlete-1",
        evidence_type=evidence_type,
        observed_at=_dt(day),
        available_at=_dt(day),
        created_at=_dt(16, 20),
        source_ref=SourceRecordRef(
            source_system="test",
            source_record_id=evidence_id,
        ),
        provenance=ProvenanceKind.SOURCE,
        knowledge_status=KnowledgeStatus.KNOWN,
        quality=EvidenceQuality.MODERATE,
        payload={"value": "observed"},
    )


def _bundle(items):
    return create_evidence_bundle(
        bundle_id="bundle-1",
        athlete_id="athlete-1",
        as_of=_dt(16, 18),
        information_cutoff_at=_dt(16, 18),
        created_at=_dt(16, 20),
        items=tuple(items),
    )


def _build(
    items,
    *,
    recent_coverage=EvidenceCoverage.COMPLETE,
    anchor_coverage=EvidenceCoverage.COMPLETE,
):
    return build_current_training_state(
        bundle=_bundle(items),
        state_id="cts-1",
        schema_version="cts_v0.1",
        created_at=_dt(16, 21),
        recent_window=ObservationWindow(
            _dt(9, 0),
            _dt(16, 18),
        ),
        load_anchor_window=ObservationWindow(
            _dt(10, 0),
            _dt(16, 18),
        ),
        recent_training_coverage=recent_coverage,
        load_anchor_training_coverage=anchor_coverage,
        domain_coverage=(
            DomainCoverageDeclaration(
                EvidenceDomain.RESPONSE,
                EvidenceCoverage.PARTIAL,
            ),
            DomainCoverageDeclaration(
                EvidenceDomain.MEASUREMENT,
                EvidenceCoverage.PARTIAL,
            ),
        ),
    )


def test_complete_known_window_yields_verified_exposure_anchor() -> None:
    state = _build(
        [
            _training("s1", 11, duration_s=3600),
            _training("s2", 14, modality="RUN", duration_s=1800),
        ]
    )

    assert state.load_anchor.status == LoadAnchorStatus.VERIFIED_EXPOSURE
    assert state.load_anchor.exposure.complete_window_total_duration_s == 5400
    assert state.load_anchor.prescription_target is False
    assert state.verify_content_hash()


def test_partial_source_coverage_never_promotes_observed_sum_to_total() -> None:
    state = _build(
        [_training("s1", 14, duration_s=3600)],
        anchor_coverage=EvidenceCoverage.PARTIAL,
    )

    assert state.load_anchor.status == LoadAnchorStatus.PARTIAL_EXPOSURE
    assert state.load_anchor.exposure.complete_window_total_duration_s is None
    assert state.load_anchor.exposure.observed_known_duration_s == 3600


def test_complete_empty_window_is_verified_zero_not_unknown() -> None:
    state = _build([])

    assert state.load_anchor.status == LoadAnchorStatus.VERIFIED_ZERO_EXPOSURE
    assert state.load_anchor.exposure.complete_window_total_duration_s == 0


def test_unknown_empty_window_remains_unknown() -> None:
    state = _build(
        [],
        recent_coverage=EvidenceCoverage.UNKNOWN,
        anchor_coverage=EvidenceCoverage.UNKNOWN,
    )

    assert state.load_anchor.status == LoadAnchorStatus.UNKNOWN
    assert state.load_anchor.exposure.complete_window_total_duration_s is None


def test_unknown_session_duration_makes_anchor_partial() -> None:
    state = _build(
        [
            _training(
                "s1",
                14,
                duration_s=None,
                duration_status=KnowledgeStatus.UNKNOWN,
            )
        ]
    )

    assert state.load_anchor.status == LoadAnchorStatus.PARTIAL_EXPOSURE
    assert state.load_anchor.exposure.complete_window_total_duration_s is None


def test_recent_exposure_summarizes_modalities_without_equating_them() -> None:
    state = _build(
        [
            _training("k1", 11, modality="KAYAK", duration_s=3600),
            _training("r1", 12, modality="RUN", duration_s=1800),
            _training("k2", 14, modality="KAYAK", duration_s=2400),
        ]
    )

    summaries = {
        item.modality_key: item
        for item in state.recent_exposure.modality_summaries
    }

    assert summaries["KAYAK"].observed_session_count == 2
    assert summaries["KAYAK"].observed_known_duration_s == 6000
    assert summaries["RUN"].observed_known_duration_s == 1800


def test_evidence_domains_preserve_observability_not_readiness() -> None:
    state = _build(
        [
            _training("s1", 11),
            _generic("feedback-1", SESSION_FEEDBACK, 15),
            _generic("measurement-1", MEASUREMENT_OBSERVATION, 13),
        ]
    )

    domains = {
        summary.domain: summary
        for summary in state.evidence_domains
    }

    assert domains[EvidenceDomain.RESPONSE].observed_item_count == 1
    assert domains[EvidenceDomain.MEASUREMENT].observed_item_count == 1
    assert domains[EvidenceDomain.PERFORMANCE].observed_item_count == 0
    assert not hasattr(state, "entry_gate")


def test_semantic_state_hash_ignores_state_id_and_created_at() -> None:
    bundle = _bundle([_training("s1", 14)])

    common = dict(
        bundle=bundle,
        schema_version="cts_v0.1",
        recent_window=ObservationWindow(_dt(9, 0), _dt(16, 18)),
        load_anchor_window=ObservationWindow(_dt(10, 0), _dt(16, 18)),
        recent_training_coverage=EvidenceCoverage.COMPLETE,
        load_anchor_training_coverage=EvidenceCoverage.COMPLETE,
    )

    first = build_current_training_state(
        state_id="cts-a",
        created_at=_dt(16, 20),
        **common,
    )
    second = build_current_training_state(
        state_id="cts-b",
        created_at=_dt(16, 21),
        **common,
    )

    assert first.content_hash == second.content_hash


def test_window_after_cutoff_is_rejected() -> None:
    with pytest.raises(ValueError, match="past evidence cutoff"):
        build_current_training_state(
            bundle=_bundle([]),
            state_id="cts-1",
            schema_version="cts_v0.1",
            created_at=_dt(16, 21),
            recent_window=ObservationWindow(
                _dt(9, 0),
                _dt(16, 20),
            ),
            load_anchor_window=ObservationWindow(
                _dt(10, 0),
                _dt(16, 18),
            ),
            recent_training_coverage=EvidenceCoverage.UNKNOWN,
            load_anchor_training_coverage=EvidenceCoverage.UNKNOWN,
        )
