from datetime import datetime, timezone

import pytest

from app.planning.application.build_current_state import (
    build_current_training_state_from_repository,
)
from app.planning.application.collect_evidence import (
    collect_available_evidence_async,
)
from app.planning.application.project_authoritative_training_response import (
    project_authoritative_training_response_evidence,
)
from app.planning.domain.common.enums import (
    KnowledgeStatus,
    ProvenanceKind,
)
from app.planning.domain.evidence.models import (
    EvidenceQuality,
    SourceRecordRef,
    create_evidence_item,
)
from app.planning.domain.response_evidence import (
    TrainingResponseKind,
    TrainingResponseLinkBasis,
    TrainingResponseMeasurement,
    TrainingResponseTiming,
    build_authoritative_training_response_evidence,
)
from app.planning.domain.training_state.evidence import (
    EXECUTED_TRAINING_SESSION,
)
from app.planning.domain.training_state.models import (
    DomainCoverageDeclaration,
    EvidenceCoverage,
    EvidenceDomain,
    LoadAnchorStatus,
    ObservationWindow,
)


UTC = timezone.utc

ATHLETE = "11111111-1111-4111-8111-111111111111"
SESSION = "22222222-2222-4222-8222-222222222222"
RESPONSE = "33333333-3333-4333-8333-333333333333"


def dt(hour: int, minute: int = 0) -> datetime:
    return datetime(
        2026,
        10,
        20,
        hour,
        minute,
        tzinfo=UTC,
    )


def executed_training_item():
    return create_evidence_item(
        evidence_id="pt-evidence:test-training",
        athlete_id=ATHLETE,
        evidence_type=EXECUTED_TRAINING_SESSION,
        observed_at=dt(7),
        available_at=dt(7, 30),
        created_at=dt(7, 30),
        source_ref=SourceRecordRef(
            source_system="test_history",
            source_record_id="training-source-1",
        ),
        provenance=ProvenanceKind.SOURCE,
        knowledge_status=KnowledgeStatus.KNOWN,
        quality=EvidenceQuality.HIGH,
        payload={
            "schema_version":
                "executed_training_session_evidence_v0.1",
            "session_id": SESSION,
            "modality_key": "RUNNING",
            "duration_status": "known",
            "duration_s": 3600,
        },
    )


def authoritative_response():
    return build_authoritative_training_response_evidence(
        artifact_id=(
            "pt-training-response-evidence:"
            f"athlete-response:{RESPONSE}"
        ),
        athlete_id=ATHLETE,
        workout_session_id=SESSION,
        executed_training_evidence_id=(
            "pt-executed-training-evidence:"
            f"session:{SESSION}"
        ),
        executed_training_evidence_hash="a" * 64,
        response_kind=(
            TrainingResponseKind.SESSION_FEEDBACK
        ),
        response_timing=(
            TrainingResponseTiming.SAME_DAY
        ),
        session_link_basis=(
            TrainingResponseLinkBasis
            .SOURCE_EXPLICIT_SESSION_ID
        ),
        observed_at=dt(8),
        available_at=dt(9),
        source_system="current_app_athlete_response",
        source_record_id=RESPONSE,
        source_record_version=(
            "current-app-athlete-response-source-v0.1"
        ),
        source_content_hash="b" * 64,
        provenance=ProvenanceKind.SOURCE,
        quality=EvidenceQuality.MODERATE,
        measurements=(
            TrainingResponseMeasurement(
                metric_key="self_reported_fatigue_score",
                knowledge_status=KnowledgeStatus.KNOWN,
                value=6.0,
                unit=None,
            ),
        ),
        created_at=dt(10),
    )


def durable_response_item():
    return project_authoritative_training_response_evidence(
        authoritative_response(),
        created_at=dt(10),
    )


class Repository:
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


class BrokenRepository:
    def __init__(self, items):
        self.items = tuple(items)

    async def list_available(
        self,
        *,
        athlete_id,
        information_cutoff_at,
    ):
        # Deliberately violates the repository cutoff contract.
        return tuple(
            item
            for item in self.items
            if item.athlete_id == athlete_id
        )


def response_summary(state):
    return next(
        summary
        for summary in state.evidence_domains
        if summary.domain == EvidenceDomain.RESPONSE
    )


async def build_state(
    repository,
    *,
    cutoff,
    suffix,
):
    return await build_current_training_state_from_repository(
        repository=repository,
        bundle_id=f"bundle-{suffix}",
        state_id=f"state-{suffix}",
        athlete_id=ATHLETE,
        schema_version="current-training-state-v0.1",
        as_of=cutoff,
        information_cutoff_at=cutoff,
        created_at=dt(12),
        recent_window=ObservationWindow(
            start_at=dt(6),
            end_at=cutoff,
        ),
        load_anchor_window=ObservationWindow(
            start_at=dt(6),
            end_at=cutoff,
        ),

        # Database retrieval completeness does not establish complete
        # scientific source coverage.
        recent_training_coverage=(
            EvidenceCoverage.PARTIAL
        ),
        load_anchor_training_coverage=(
            EvidenceCoverage.PARTIAL
        ),
        domain_coverage=(
            DomainCoverageDeclaration(
                domain=EvidenceDomain.RESPONSE,
                coverage=EvidenceCoverage.PARTIAL,
            ),
        ),
    )


@pytest.mark.asyncio
async def test_durable_response_enters_state_only_after_projection_availability():
    training = executed_training_item()
    response = durable_response_item()

    # The athlete report was observed at 08:00 and the authoritative
    # response says its underlying information was available at 09:00,
    # but the durable authoritative artifact did not exist until 10:00.
    assert response.observed_at == dt(8)
    assert response.available_at == dt(10)

    repository = Repository(
        (
            training,
            response,
        )
    )

    before = await build_state(
        repository,
        cutoff=dt(9, 30),
        suffix="before-response",
    )

    after = await build_state(
        repository,
        cutoff=dt(11),
        suffix="after-response",
    )

    before_response = response_summary(before)
    after_response = response_summary(after)

    assert before_response.observed_item_count == 0
    assert before_response.first_observed_at is None
    assert before_response.latest_observed_at is None
    assert before_response.latest_available_at is None
    assert before_response.source_evidence_ids == ()

    assert after_response.observed_item_count == 1
    assert after_response.first_observed_at == dt(8)
    assert after_response.latest_observed_at == dt(8)
    assert after_response.latest_available_at == dt(10)
    assert (
        after_response.source_evidence_ids
        == (response.evidence_id,)
    )

    assert (
        after_response.source_coverage
        == EvidenceCoverage.PARTIAL
    )

    assert repository.calls == [
        (
            ATHLETE,
            dt(9, 30),
        ),
        (
            ATHLETE,
            dt(11),
        ),
    ]

    assert before.verify_content_hash()
    assert after.verify_content_hash()


@pytest.mark.asyncio
async def test_response_evidence_does_not_change_training_exposure_or_load_anchor():
    training = executed_training_item()
    response = durable_response_item()

    training_only = await build_state(
        Repository(
            (training,)
        ),
        cutoff=dt(11),
        suffix="training-only",
    )

    with_response = await build_state(
        Repository(
            (
                training,
                response,
            )
        ),
        cutoff=dt(11),
        suffix="with-response",
    )

    # Response evidence enters only the RESPONSE domain summary.
    assert (
        response_summary(training_only).observed_item_count
        == 0
    )
    assert (
        response_summary(with_response).observed_item_count
        == 1
    )

    # Training exposure remains sourced only from executed-training
    # evidence.
    assert (
        with_response.recent_exposure.observed_session_count
        == training_only.recent_exposure.observed_session_count
        == 1
    )

    assert (
        with_response.recent_exposure
        .known_duration_session_count
        == training_only.recent_exposure
        .known_duration_session_count
        == 1
    )

    assert (
        with_response.recent_exposure
        .observed_known_duration_s
        == training_only.recent_exposure
        .observed_known_duration_s
        == 3600
    )

    assert (
        with_response.recent_exposure
        .complete_window_total_duration_s
        is None
    )
    assert (
        training_only.recent_exposure
        .complete_window_total_duration_s
        is None
    )

    assert (
        with_response.recent_exposure.source_evidence_ids
        == training_only.recent_exposure.source_evidence_ids
        == (training.evidence_id,)
    )

    assert (
        with_response.load_anchor.status
        == training_only.load_anchor.status
        == LoadAnchorStatus.PARTIAL_EXPOSURE
    )

    assert (
        with_response.load_anchor.prescription_target
        is False
    )
    assert (
        training_only.load_anchor.prescription_target
        is False
    )

    # P1.8E1 does not add a readiness/fatigue interpretation surface.
    assert not hasattr(
        with_response,
        "readiness_score",
    )
    assert not hasattr(
        with_response,
        "fatigue_score",
    )


@pytest.mark.asyncio
async def test_bundle_boundary_rejects_future_response_repository_leakage():
    response = durable_response_item()

    repository = BrokenRepository(
        (response,)
    )

    with pytest.raises(
        ValueError,
        match="unavailable at information cutoff",
    ):
        await collect_available_evidence_async(
            repository=repository,
            bundle_id="bundle-response-leak",
            athlete_id=ATHLETE,
            as_of=dt(9, 30),
            information_cutoff_at=dt(9, 30),
            created_at=dt(12),
        )
