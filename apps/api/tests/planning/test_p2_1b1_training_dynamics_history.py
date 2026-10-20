from datetime import datetime, timezone

import pytest

from app.planning.application.build_training_dynamics_history import (
    build_training_dynamics_history_from_evidence,
    build_training_dynamics_history_from_repository,
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
from app.planning.domain.training_dynamics import (
    ResponseIsolationStatus,
)
from app.planning.domain.training_dynamics.history import (
    TRAINING_DYNAMICS_HISTORY_SCHEMA_V01,
    TrainingDynamicsHistoryCoverage,
)
from app.planning.domain.training_state.evidence import (
    EXECUTED_TRAINING_SESSION,
    EXECUTED_TRAINING_SESSION_SCHEMA_V02,
    SESSION_FEEDBACK,
    SESSION_FEEDBACK_SCHEMA_V01,
)


UTC = timezone.utc

ATHLETE = "11111111-1111-4111-8111-111111111111"

SESSION_A = "22222222-2222-4222-8222-222222222222"
SESSION_B = "33333333-3333-4333-8333-333333333333"
SESSION_C = "44444444-4444-4444-8444-444444444444"


def dt(
    day: int,
    hour: int,
) -> datetime:
    return datetime(
        2026,
        10,
        day,
        hour,
        tzinfo=UTC,
    )


def executed(
    *,
    session_id: str,
    observed_at: datetime,
    digest_char: str,
    duration_s: int = 3600,
):
    artifact_hash = digest_char * 64

    return create_evidence_item(
        evidence_id=(
            "pt-evidence:executed-training:"
            f"{artifact_hash}"
        ),
        athlete_id=ATHLETE,
        evidence_type=EXECUTED_TRAINING_SESSION,
        observed_at=observed_at,
        available_at=observed_at,
        created_at=observed_at,
        source_ref=SourceRecordRef(
            source_system=(
                "planning_authoritative_executed_training"
            ),
            source_record_id=(
                "pt-executed-training-evidence:"
                f"session:{session_id}"
            ),
            source_version=(
                "authoritative-executed-training-evidence-v0.1"
            ),
            source_content_hash=artifact_hash,
        ),
        provenance=ProvenanceKind.DERIVED,
        knowledge_status=KnowledgeStatus.KNOWN,
        quality=EvidenceQuality.HIGH,
        payload={
            "schema_version":
                EXECUTED_TRAINING_SESSION_SCHEMA_V02,
            "session_id": session_id,
            "modality_key": "RUNNING",
            "duration_status": "known",
            "duration_s": duration_s,

            "authoritative_execution_evidence_id": (
                "pt-executed-training-evidence:"
                f"session:{session_id}"
            ),
            "authoritative_execution_evidence_hash":
                artifact_hash,

            "plan_execution_link_id":
                f"pt-exec-link:{session_id}",
            "plan_identity_linked": True,

            "occurrence_association_count": 0,
            "occurrence_alignment_status": "none",
            "plan_content_at_execution_status": "unverified",

            "occurrence_alignment_verified": False,
            "phase_alignment_verified": False,
            "provider_event_verified": False,
            "clock_alignment_verified": False,
            "actual_boundary_verified": False,
            "temporal_match_used": False,
        },
    )


def response(
    *,
    session_id: str,
    execution_hash_char: str,
    response_hash_char: str,
    observed_at: datetime,
    available_at: datetime | None = None,
):
    execution_hash = execution_hash_char * 64
    response_artifact_hash = response_hash_char * 64

    return create_evidence_item(
        evidence_id=(
            "pt-evidence:session-feedback:"
            f"{response_artifact_hash}"
        ),
        athlete_id=ATHLETE,
        evidence_type=SESSION_FEEDBACK,
        observed_at=observed_at,
        available_at=available_at or observed_at,
        created_at=available_at or observed_at,
        source_ref=SourceRecordRef(
            source_system=(
                "planning_authoritative_training_response"
            ),
            source_record_id=(
                "pt-training-response-evidence:"
                f"test:{response_hash_char}"
            ),
            source_version=(
                "authoritative-training-response-evidence-v0.2"
            ),
            source_content_hash=response_artifact_hash,
        ),
        provenance=ProvenanceKind.DERIVED,
        knowledge_status=KnowledgeStatus.KNOWN,
        quality=EvidenceQuality.MODERATE,
        payload={
            "schema_version":
                SESSION_FEEDBACK_SCHEMA_V01,
            "session_id": session_id,
            "response_timing": "same_day",
            "measurements": (
                {
                    "metric_key":
                        "self_reported_fatigue_score",
                    "knowledge_status": "known",
                    "value": 6.0,
                    "unit": None,
                },
            ),

            "authoritative_response_evidence_id": (
                "pt-training-response-evidence:"
                f"test:{response_hash_char}"
            ),
            "authoritative_response_evidence_hash":
                response_artifact_hash,

            "executed_training_evidence_id": (
                "pt-executed-training-evidence:"
                f"session:{session_id}"
            ),
            "executed_training_evidence_hash":
                execution_hash,

            "session_link_basis":
                "source_explicit_session_id",
            "session_identity_linked": True,
            "interpretation": "descriptive_only",

            "causal_attribution_established": False,
            "readiness_inference_authorized": False,
            "fatigue_diagnosis_authorized": False,
            "performance_prediction_authorized": False,
            "prescription_change_authorized": False,
        },
    )


def build(
    items,
    *,
    stimulus_coverage=(
        TrainingDynamicsHistoryCoverage.PARTIAL
    ),
):
    return build_training_dynamics_history_from_evidence(
        items=tuple(items),
        history_id="pt-training-dynamics-history:test",
        athlete_id=ATHLETE,
        window_start_at=dt(18, 0),
        as_of=dt(20, 23),
        information_cutoff_at=dt(20, 23),
        stimulus_coverage=stimulus_coverage,
        response_coverage=(
            TrainingDynamicsHistoryCoverage.PARTIAL
        ),
        created_at=dt(20, 23),
    )


def test_builds_ordered_multi_session_history():
    a = executed(
        session_id=SESSION_A,
        observed_at=dt(19, 8),
        digest_char="a",
    )

    b = executed(
        session_id=SESSION_B,
        observed_at=dt(20, 8),
        digest_char="b",
    )

    response_a = response(
        session_id=SESSION_A,
        execution_hash_char="a",
        response_hash_char="c",
        observed_at=dt(19, 14),
    )

    response_b = response(
        session_id=SESSION_B,
        execution_hash_char="b",
        response_hash_char="d",
        observed_at=dt(20, 14),
    )

    history = build(
        (
            response_b,
            b,
            response_a,
            a,
        )
    )

    assert (
        history.schema_version
        == TRAINING_DYNAMICS_HISTORY_SCHEMA_V01
    )

    assert tuple(
        entry.stimulus.workout_session_id
        for entry in history.entries
    ) == (
        SESSION_A,
        SESSION_B,
    )

    assert (
        history.entries[0]
        .responses[0]
        .response_evidence_id
        == response_a.evidence_id
    )

    assert (
        history.entries[1]
        .responses[0]
        .response_evidence_id
        == response_b.evidence_id
    )

    assert history.effect_inference_authorized is False
    assert history.causal_attribution_established is False
    assert history.performance_prediction_authorized is False
    assert history.prescription_change_authorized is False

    assert history.verify_content_hash()


def test_partial_coverage_keeps_no_intervening_case_unknown():
    a = executed(
        session_id=SESSION_A,
        observed_at=dt(19, 8),
        digest_char="a",
    )

    r = response(
        session_id=SESSION_A,
        execution_hash_char="a",
        response_hash_char="c",
        observed_at=dt(19, 14),
    )

    history = build(
        (a, r),
        stimulus_coverage=(
            TrainingDynamicsHistoryCoverage.PARTIAL
        ),
    )

    association = history.entries[0].responses[0]

    assert (
        association.isolation_status
        == ResponseIsolationStatus.UNKNOWN
    )


def test_complete_coverage_allows_no_intervening_observed():
    a = executed(
        session_id=SESSION_A,
        observed_at=dt(19, 8),
        digest_char="a",
    )

    r = response(
        session_id=SESSION_A,
        execution_hash_char="a",
        response_hash_char="c",
        observed_at=dt(19, 14),
    )

    history = build(
        (a, r),
        stimulus_coverage=(
            TrainingDynamicsHistoryCoverage.COMPLETE
        ),
    )

    association = history.entries[0].responses[0]

    assert (
        association.isolation_status
        == ResponseIsolationStatus
        .NO_INTERVENING_STIMULUS_OBSERVED
    )


def test_visible_intervening_stimulus_is_explicit_even_with_partial_coverage():
    a = executed(
        session_id=SESSION_A,
        observed_at=dt(19, 8),
        digest_char="a",
    )

    b = executed(
        session_id=SESSION_B,
        observed_at=dt(19, 11),
        digest_char="b",
    )

    r = response(
        session_id=SESSION_A,
        execution_hash_char="a",
        response_hash_char="c",
        observed_at=dt(19, 14),
    )

    history = build(
        (r, b, a),
        stimulus_coverage=(
            TrainingDynamicsHistoryCoverage.PARTIAL
        ),
    )

    association = history.entries[0].responses[0]

    assert (
        association.isolation_status
        == ResponseIsolationStatus
        .INTERVENING_STIMULUS_OBSERVED
    )

    assert association.intervening_stimulus_ids == (
        history.entries[1].stimulus.stimulus_id,
    )


def test_response_is_linked_by_session_and_execution_identity_not_time():
    a = executed(
        session_id=SESSION_A,
        observed_at=dt(19, 8),
        digest_char="a",
    )

    b = executed(
        session_id=SESSION_B,
        observed_at=dt(19, 9),
        digest_char="b",
    )

    r = response(
        session_id=SESSION_A,
        execution_hash_char="a",
        response_hash_char="c",
        observed_at=dt(19, 10),
    )

    history = build((b, r, a))

    assert (
        history.entries[0]
        .stimulus.workout_session_id
        == SESSION_A
    )

    assert len(
        history.entries[0].responses
    ) == 1

    assert len(
        history.entries[1].responses
    ) == 0


def test_mismatched_execution_reference_fails_closed():
    a = executed(
        session_id=SESSION_A,
        observed_at=dt(19, 8),
        digest_char="a",
    )

    r = response(
        session_id=SESSION_A,
        execution_hash_char="f",
        response_hash_char="c",
        observed_at=dt(19, 14),
    )

    with pytest.raises(
        ValueError,
        match="execution reference",
    ):
        build((a, r))


def test_legacy_executed_training_is_not_promoted_into_p2_history():
    artifact_hash = "a" * 64

    legacy = create_evidence_item(
        evidence_id="legacy-executed",
        athlete_id=ATHLETE,
        evidence_type=EXECUTED_TRAINING_SESSION,
        observed_at=dt(19, 8),
        available_at=dt(19, 8),
        created_at=dt(19, 8),
        source_ref=SourceRecordRef(
            source_system="legacy",
            source_record_id=SESSION_A,
        ),
        provenance=ProvenanceKind.SOURCE,
        knowledge_status=KnowledgeStatus.KNOWN,
        quality=EvidenceQuality.HIGH,
        payload={
            "schema_version":
                "executed_training_session_evidence_v0.1",
            "session_id": SESSION_A,
            "modality_key": "RUNNING",
            "duration_status": "known",
            "duration_s": 3600,
        },
    )

    history = build((legacy,))

    assert history.entries == ()
    assert history.source_evidence_ids == ()


def test_stimulus_before_window_is_not_added_to_history():
    old = executed(
        session_id=SESSION_A,
        observed_at=dt(17, 8),
        digest_char="a",
    )

    current = executed(
        session_id=SESSION_B,
        observed_at=dt(19, 8),
        digest_char="b",
    )

    history = build((old, current))

    assert tuple(
        entry.stimulus.workout_session_id
        for entry in history.entries
    ) == (SESSION_B,)


def test_response_to_stimulus_outside_window_is_not_pulled_in():
    old = executed(
        session_id=SESSION_A,
        observed_at=dt(17, 8),
        digest_char="a",
    )

    r = response(
        session_id=SESSION_A,
        execution_hash_char="a",
        response_hash_char="c",
        observed_at=dt(18, 8),
    )

    history = build((old, r))

    assert history.entries == ()


def test_input_order_does_not_change_history_hash():
    a = executed(
        session_id=SESSION_A,
        observed_at=dt(19, 8),
        digest_char="a",
    )

    b = executed(
        session_id=SESSION_B,
        observed_at=dt(20, 8),
        digest_char="b",
    )

    r = response(
        session_id=SESSION_A,
        execution_hash_char="a",
        response_hash_char="c",
        observed_at=dt(19, 14),
    )

    first = build((a, b, r))
    second = build((r, b, a))

    assert first.content_hash == second.content_hash


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


@pytest.mark.asyncio
async def test_repository_history_is_cutoff_safe():
    a = executed(
        session_id=SESSION_A,
        observed_at=dt(19, 8),
        digest_char="a",
    )

    visible = response(
        session_id=SESSION_A,
        execution_hash_char="a",
        response_hash_char="c",
        observed_at=dt(19, 14),
    )

    future = response(
        session_id=SESSION_A,
        execution_hash_char="a",
        response_hash_char="d",
        observed_at=dt(20, 14),
        available_at=dt(21, 8),
    )

    repository = Repository(
        (
            future,
            visible,
            a,
        )
    )

    history = (
        await build_training_dynamics_history_from_repository(
            repository=repository,
            bundle_id="bundle:p2-history",
            history_id="pt-training-dynamics-history:repo",
            athlete_id=ATHLETE,
            window_start_at=dt(18, 0),
            as_of=dt(20, 23),
            information_cutoff_at=dt(20, 23),
            stimulus_coverage=(
                TrainingDynamicsHistoryCoverage.PARTIAL
            ),
            response_coverage=(
                TrainingDynamicsHistoryCoverage.PARTIAL
            ),
            created_at=dt(21, 23),
        )
    )

    assert repository.calls == [
        (
            ATHLETE,
            dt(20, 23),
        )
    ]

    assert len(history.entries) == 1
    assert len(history.entries[0].responses) == 1

    assert (
        history.entries[0]
        .responses[0]
        .response_evidence_id
        == visible.evidence_id
    )


def test_duplicate_authoritative_session_fails_closed():
    first = executed(
        session_id=SESSION_A,
        observed_at=dt(19, 8),
        digest_char="a",
    )

    second = executed(
        session_id=SESSION_A,
        observed_at=dt(19, 9),
        digest_char="b",
    )

    with pytest.raises(
        ValueError,
        match="Duplicate authoritative stimulus session",
    ):
        build((first, second))


def test_history_contains_no_effect_or_planning_authority():
    a = executed(
        session_id=SESSION_A,
        observed_at=dt(19, 8),
        digest_char="a",
    )

    history = build((a,))

    assert history.effect_inference_authorized is False
    assert history.causal_attribution_established is False
    assert history.performance_prediction_authorized is False
    assert history.prescription_change_authorized is False

    assert not hasattr(
        history,
        "fatigue_effect",
    )
    assert not hasattr(
        history,
        "adaptation_effect",
    )
