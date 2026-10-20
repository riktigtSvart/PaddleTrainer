# P1_7D3_V02_CONTRACT_TESTS

from datetime import datetime, timezone

import pytest

from app.planning.domain.common.enums import (
    KnowledgeStatus,
    ProvenanceKind,
)
from app.planning.domain.evidence.models import (
    EvidenceQuality,
    SourceRecordRef,
    create_evidence_item,
)
from app.planning.domain.training_state.evidence import (
    EXECUTED_TRAINING_SESSION,
    training_exposure_from_evidence,
)


UTC = timezone.utc


def _item(**overrides):
    payload = {
        "schema_version":
            "executed_training_session_evidence_v0.2",
        "session_id": "session-d3",
        "modality_key": "RUNNING",
        "duration_status": "known",
        "duration_s": 4200,

        "authoritative_execution_evidence_id":
            "pt-executed-training-evidence:session-d3",
        "authoritative_execution_evidence_hash":
            "a" * 64,
        "plan_execution_link_id":
            "pt-exec-link:d3",

        "plan_identity_linked": True,
        "occurrence_association_count": 0,
        "occurrence_alignment_status": "none",

        "plan_content_at_execution_status":
            "unverified",

        "occurrence_alignment_verified": False,
        "phase_alignment_verified": False,
        "provider_event_verified": False,
        "clock_alignment_verified": False,
        "actual_boundary_verified": False,
        "temporal_match_used": False,
    }

    payload.update(overrides)

    observed = datetime(
        2026, 10, 20, 7,
        tzinfo=UTC,
    )
    available = datetime(
        2026, 10, 20, 8,
        tzinfo=UTC,
    )

    return create_evidence_item(
        evidence_id="evidence-d3",
        athlete_id="athlete-d3",
        evidence_type=EXECUTED_TRAINING_SESSION,
        observed_at=observed,
        available_at=available,
        created_at=available,
        source_ref=SourceRecordRef(
            source_system=(
                "planning_authoritative_executed_training"
            ),
            source_record_id=(
                "pt-executed-training-evidence:session-d3"
            ),
            source_version=(
                "authoritative-executed-training-evidence-v0.1"
            ),
            source_content_hash="a" * 64,
        ),
        provenance=ProvenanceKind.DERIVED,
        knowledge_status=KnowledgeStatus.KNOWN,
        quality=EvidenceQuality.HIGH,
        payload=payload,
    )


def test_v02_projects_into_descriptive_training_exposure():
    observation = training_exposure_from_evidence(
        _item()
    )

    assert observation is not None
    assert observation.session_id == "session-d3"
    assert observation.modality_key == "RUNNING"
    assert observation.duration_s == 4200
    assert (
        observation.duration_status
        == KnowledgeStatus.KNOWN
    )


def test_v02_rejects_silent_phase_authority_upgrade():
    with pytest.raises(
        ValueError,
        match="phase_alignment_verified must remain false",
    ):
        training_exposure_from_evidence(
            _item(
                phase_alignment_verified=True
            )
        )


def test_v02_rejects_verified_historical_plan_content():
    with pytest.raises(
        ValueError,
        match="cannot claim verified historical plan content",
    ):
        training_exposure_from_evidence(
            _item(
                plan_content_at_execution_status="verified"
            )
        )


def test_v02_rejects_source_hash_mismatch():
    item = _item(
        authoritative_execution_evidence_hash="b" * 64
    )

    with pytest.raises(
        ValueError,
        match="source content hash does not match",
    ):
        training_exposure_from_evidence(item)


def test_v02_rejects_occurrence_status_without_association():
    with pytest.raises(
        ValueError,
        match="Zero occurrence associations",
    ):
        training_exposure_from_evidence(
            _item(
                occurrence_alignment_status=(
                    "user_confirmed_candidate_segment"
                )
            )
        )


# P1_7D3_ASYNC_COLLECTION_TESTS

from app.planning.application.build_current_state import (
    build_current_training_state_from_repository,
)
from app.planning.application.collect_evidence import (
    collect_available_evidence_async,
)
from app.planning.domain.training_state.models import (
    EvidenceCoverage,
    LoadAnchorStatus,
    ObservationWindow,
)


def _hour(hour: int) -> datetime:
    return datetime(
        2026,
        10,
        20,
        hour,
        tzinfo=UTC,
    )


def _repository_item(
    evidence_id: str,
    *,
    observed_hour: int,
    available_hour: int,
    duration_s: int,
):
    artifact_id = (
        "pt-executed-training-evidence:"
        f"{evidence_id}"
    )
    artifact_hash = "b" * 64

    payload = {
        "schema_version":
            "executed_training_session_evidence_v0.2",
        "session_id":
            f"session-{evidence_id}",
        "modality_key": "RUNNING",
        "duration_status": "known",
        "duration_s": duration_s,

        "authoritative_execution_evidence_id":
            artifact_id,
        "authoritative_execution_evidence_hash":
            artifact_hash,
        "plan_execution_link_id":
            f"pt-exec-link:{evidence_id}",

        "plan_identity_linked": True,
        "occurrence_association_count": 0,
        "occurrence_alignment_status": "none",
        "plan_content_at_execution_status":
            "unverified",

        "occurrence_alignment_verified": False,
        "phase_alignment_verified": False,
        "provider_event_verified": False,
        "clock_alignment_verified": False,
        "actual_boundary_verified": False,
        "temporal_match_used": False,
    }

    return create_evidence_item(
        evidence_id=evidence_id,
        athlete_id="athlete-d3",
        evidence_type=EXECUTED_TRAINING_SESSION,
        observed_at=_hour(observed_hour),
        available_at=_hour(available_hour),
        created_at=_hour(available_hour),
        source_ref=SourceRecordRef(
            source_system=(
                "planning_authoritative_executed_training"
            ),
            source_record_id=artifact_id,
            source_version=(
                "authoritative-executed-training-evidence-v0.1"
            ),
            source_content_hash=artifact_hash,
        ),
        provenance=ProvenanceKind.DERIVED,
        knowledge_status=KnowledgeStatus.KNOWN,
        quality=EvidenceQuality.HIGH,
        payload=payload,
    )


class _AsyncEvidenceRepository:
    def __init__(self, items):
        self.items = tuple(items)
        self.calls = []

    async def list_available(
        self,
        *,
        athlete_id,
        information_cutoff_at,
    ):
        self.calls.append(
            (
                athlete_id,
                information_cutoff_at,
            )
        )

        return tuple(
            item
            for item in self.items
            if item.athlete_id == athlete_id
            and item.observed_at
            <= information_cutoff_at
            and item.available_at
            <= information_cutoff_at
        )


class _BrokenAsyncEvidenceRepository:
    def __init__(self, items):
        self.items = tuple(items)

    async def list_available(
        self,
        *,
        athlete_id,
        information_cutoff_at,
    ):
        # Deliberately violates the repository contract. The application
        # boundary must still fail closed through EvidenceBundle validation.
        return self.items


@pytest.mark.asyncio
async def test_async_collector_passes_exact_cutoff_and_excludes_future():
    early = _repository_item(
        "early",
        observed_hour=7,
        available_hour=8,
        duration_s=3600,
    )

    future_available = _repository_item(
        "future-available",
        observed_hour=7,
        available_hour=13,
        duration_s=7200,
    )

    future_observed = _repository_item(
        "future-observed",
        observed_hour=13,
        available_hour=13,
        duration_s=5400,
    )

    repository = _AsyncEvidenceRepository(
        (
            future_available,
            future_observed,
            early,
        )
    )

    bundle = await collect_available_evidence_async(
        repository=repository,
        bundle_id="bundle-d3",
        athlete_id="athlete-d3",
        as_of=_hour(12),
        information_cutoff_at=_hour(12),
        created_at=_hour(14),
    )

    assert repository.calls == [
        (
            "athlete-d3",
            _hour(12),
        )
    ]

    assert tuple(
        item.evidence_id
        for item in bundle.items
    ) == ("early",)

    assert (
        bundle.information_cutoff_at
        == _hour(12)
    )
    assert bundle.verify_content_hash()


@pytest.mark.asyncio
async def test_bundle_boundary_rejects_repository_future_leakage():
    future = _repository_item(
        "future",
        observed_hour=7,
        available_hour=13,
        duration_s=3600,
    )

    repository = _BrokenAsyncEvidenceRepository(
        (future,)
    )

    with pytest.raises(
        ValueError,
        match="unavailable at information cutoff",
    ):
        await collect_available_evidence_async(
            repository=repository,
            bundle_id="bundle-broken-d3",
            athlete_id="athlete-d3",
            as_of=_hour(12),
            information_cutoff_at=_hour(12),
            created_at=_hour(14),
        )


@pytest.mark.asyncio
async def test_repository_to_current_state_is_cutoff_safe():
    included = _repository_item(
        "included",
        observed_hour=7,
        available_hour=8,
        duration_s=3600,
    )

    future_available = _repository_item(
        "future-available-state",
        observed_hour=7,
        available_hour=13,
        duration_s=7200,
    )

    future_observed = _repository_item(
        "future-observed-state",
        observed_hour=13,
        available_hour=13,
        duration_s=5400,
    )

    repository = _AsyncEvidenceRepository(
        (
            included,
            future_available,
            future_observed,
        )
    )

    state = (
        await build_current_training_state_from_repository(
            repository=repository,
            bundle_id="bundle-state-d3",
            state_id="state-d3",
            athlete_id="athlete-d3",
            schema_version=(
                "current-training-state-v0.1"
            ),
            as_of=_hour(12),
            information_cutoff_at=_hour(12),
            created_at=_hour(14),
            recent_window=ObservationWindow(
                start_at=_hour(0),
                end_at=_hour(12),
            ),
            load_anchor_window=ObservationWindow(
                start_at=_hour(0),
                end_at=_hour(12),
            ),

            # Database retrieval completeness does NOT prove scientific
            # source completeness.
            recent_training_coverage=(
                EvidenceCoverage.PARTIAL
            ),
            load_anchor_training_coverage=(
                EvidenceCoverage.PARTIAL
            ),
        )
    )

    assert (
        state.information_cutoff_at
        == _hour(12)
    )

    assert (
        state.recent_exposure
        .observed_session_count
        == 1
    )

    assert (
        state.recent_exposure
        .observed_known_duration_s
        == 3600
    )

    assert (
        state.recent_exposure
        .complete_window_total_duration_s
        is None
    )

    assert (
        state.load_anchor.status
        == LoadAnchorStatus.PARTIAL_EXPOSURE
    )

    assert (
        state.load_anchor.prescription_target
        is False
    )

    assert (
        state.recent_exposure
        .source_evidence_ids
        == ("included",)
    )

    assert state.verify_content_hash()


@pytest.mark.asyncio
async def test_unknown_coverage_does_not_turn_missing_into_zero():
    repository = _AsyncEvidenceRepository(())

    state = (
        await build_current_training_state_from_repository(
            repository=repository,
            bundle_id="bundle-empty-d3",
            state_id="state-empty-d3",
            athlete_id="athlete-d3",
            schema_version=(
                "current-training-state-v0.1"
            ),
            as_of=_hour(12),
            information_cutoff_at=_hour(12),
            created_at=_hour(14),
            recent_window=ObservationWindow(
                start_at=_hour(0),
                end_at=_hour(12),
            ),
            load_anchor_window=ObservationWindow(
                start_at=_hour(0),
                end_at=_hour(12),
            ),
            recent_training_coverage=(
                EvidenceCoverage.UNKNOWN
            ),
            load_anchor_training_coverage=(
                EvidenceCoverage.UNKNOWN
            ),
        )
    )

    assert (
        state.load_anchor.status
        == LoadAnchorStatus.UNKNOWN
    )

    assert (
        state.load_anchor.exposure
        .complete_window_total_duration_s
        is None
    )

    assert (
        state.load_anchor.prescription_target
        is False
    )

