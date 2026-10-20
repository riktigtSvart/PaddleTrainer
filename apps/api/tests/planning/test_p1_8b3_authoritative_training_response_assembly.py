from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.planning.application.build_authoritative_training_response import (
    AuthoritativeTrainingResponseExecutionInvalid,
    AuthoritativeTrainingResponseIdentityMismatch,
    AuthoritativeTrainingResponseTemporalInvalid,
    assemble_authoritative_training_response,
)
from app.planning.domain.common.enums import (
    KnowledgeStatus,
)
from app.planning.domain.executed_training.models import (
    AUTHORITATIVE_EXECUTED_TRAINING_SCHEMA_VERSION,
)
from app.planning.domain.response_evidence import (
    TrainingResponseInterpretation,
    TrainingResponseKind,
    TrainingResponseLinkBasis,
    TrainingResponseMeasurement,
    TrainingResponseTiming,
)
from app.planning.domain.response_evidence.source_capture import (
    build_training_response_source_capture,
)


UTC = timezone.utc

ATHLETE_ID = (
    "11111111-1111-4111-8111-111111111111"
)

OTHER_ATHLETE_ID = (
    "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
)

SESSION_ID = (
    "22222222-2222-4222-8222-222222222222"
)

OTHER_SESSION_ID = (
    "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
)

RESPONSE_ID = (
    "33333333-3333-4333-8333-333333333333"
)

EXECUTED_ID = (
    "pt-executed-training-evidence:"
    "session:22222222-2222-4222-8222-222222222222"
)


def dt(hour: int) -> datetime:
    return datetime(
        2026,
        10,
        20,
        hour,
        tzinfo=UTC,
    )


def executed(**updates):
    values = dict(
        artifact_id=EXECUTED_ID,
        schema_version=(
            AUTHORITATIVE_EXECUTED_TRAINING_SCHEMA_VERSION
        ),
        athlete_id=ATHLETE_ID,
        workout_session_id=SESSION_ID,
        observed_at=dt(8),
        created_at=dt(9),
        content_hash="a" * 64,
        plan_identity_linked=True,
        plan_content_at_execution_status="unverified",
        occurrence_alignment_verified=False,
        phase_alignment_verified=False,
        provider_event_verified=False,
        clock_alignment_verified=False,
        actual_boundary_verified=False,
        temporal_match_used=False,
        verify_content_hash=lambda: True,
    )
    values.update(updates)
    return SimpleNamespace(**values)


def capture(**updates):
    values = dict(
        athlete_id=ATHLETE_ID,
        workout_session_id=SESSION_ID,
        response_source_id=RESPONSE_ID,
        response_kind=(
            TrainingResponseKind.SESSION_FEEDBACK
        ),
        response_timing=(
            TrainingResponseTiming.SAME_DAY
        ),
        observed_at=dt(10),
        available_at=dt(11),
        source_system="current_app_athlete_response",
        source_record_id=RESPONSE_ID,
        source_record_version=(
            "current-app-athlete-response-source-v0.1"
        ),
        source_content_hash="b" * 64,
        measurements=(
            TrainingResponseMeasurement(
                metric_key=(
                    "self_reported_fatigue_score"
                ),
                knowledge_status=KnowledgeStatus.KNOWN,
                value=6.0,
                unit=None,
            ),
        ),
    )
    values.update(updates)

    return build_training_response_source_capture(
        **values
    )


class FakeResponseSource:
    def __init__(self, value):
        self.value = value
        self.calls = []

    async def lock_and_capture(
        self,
        session,
        *,
        athlete_id,
        response_source_id,
    ):
        self.calls.append(
            {
                "session": session,
                "athlete_id": athlete_id,
                "response_source_id": response_source_id,
            }
        )
        return self.value


@pytest.mark.asyncio
async def test_assembles_response_against_authoritative_execution_identity():
    source = FakeResponseSource(
        capture()
    )

    artifact = await assemble_authoritative_training_response(
        athlete_id=ATHLETE_ID,
        response_source_id=RESPONSE_ID,
        executed_training=executed(),
        response_source=source,
        session="db",
        created_at=dt(12),
    )

    assert artifact.artifact_id == (
        "pt-training-response-evidence:"
        f"athlete-response:{RESPONSE_ID}"
    )

    assert artifact.athlete_id == ATHLETE_ID
    assert artifact.workout_session_id == SESSION_ID

    assert (
        artifact.executed_training_evidence_id
        == EXECUTED_ID
    )
    assert (
        artifact.executed_training_evidence_hash
        == "a" * 64
    )

    assert (
        artifact.session_link_basis
        == TrainingResponseLinkBasis
        .SOURCE_EXPLICIT_SESSION_ID
    )

    assert (
        artifact.interpretation
        == TrainingResponseInterpretation.DESCRIPTIVE_ONLY
    )

    assert artifact.causal_attribution_established is False
    assert artifact.readiness_inference_authorized is False
    assert artifact.fatigue_diagnosis_authorized is False
    assert artifact.performance_prediction_authorized is False
    assert artifact.prescription_change_authorized is False

    assert artifact.verify_content_hash()

    assert source.calls == [
        {
            "session": "db",
            "athlete_id": ATHLETE_ID,
            "response_source_id": RESPONSE_ID,
        }
    ]


@pytest.mark.asyncio
async def test_execution_authority_delays_response_availability():
    artifact = await assemble_authoritative_training_response(
        athlete_id=ATHLETE_ID,
        response_source_id=RESPONSE_ID,
        executed_training=executed(
            created_at=dt(12),
        ),
        response_source=FakeResponseSource(
            capture(
                available_at=dt(11),
            )
        ),
        session=object(),
        created_at=dt(13),
    )

    assert artifact.observed_at == dt(10)
    assert artifact.available_at == dt(12)


@pytest.mark.asyncio
async def test_late_response_source_controls_response_availability():
    artifact = await assemble_authoritative_training_response(
        athlete_id=ATHLETE_ID,
        response_source_id=RESPONSE_ID,
        executed_training=executed(
            created_at=dt(9),
        ),
        response_source=FakeResponseSource(
            capture(
                available_at=dt(12),
            )
        ),
        session=object(),
        created_at=dt(13),
    )

    assert artifact.available_at == dt(12)


@pytest.mark.asyncio
async def test_rejects_cross_athlete_execution_evidence():
    with pytest.raises(
        AuthoritativeTrainingResponseIdentityMismatch,
        match="athlete",
    ):
        await assemble_authoritative_training_response(
            athlete_id=ATHLETE_ID,
            response_source_id=RESPONSE_ID,
            executed_training=executed(
                athlete_id=OTHER_ATHLETE_ID,
            ),
            response_source=FakeResponseSource(
                capture()
            ),
            session=object(),
            created_at=dt(12),
        )


@pytest.mark.asyncio
async def test_rejects_response_session_different_from_execution_session():
    with pytest.raises(
        AuthoritativeTrainingResponseIdentityMismatch,
        match="session",
    ):
        await assemble_authoritative_training_response(
            athlete_id=ATHLETE_ID,
            response_source_id=RESPONSE_ID,
            executed_training=executed(
                workout_session_id=OTHER_SESSION_ID,
            ),
            response_source=FakeResponseSource(
                capture()
            ),
            session=object(),
            created_at=dt(12),
        )


@pytest.mark.asyncio
async def test_rejects_execution_artifact_with_invalid_hash():
    with pytest.raises(
        AuthoritativeTrainingResponseExecutionInvalid,
        match="hash",
    ):
        await assemble_authoritative_training_response(
            athlete_id=ATHLETE_ID,
            response_source_id=RESPONSE_ID,
            executed_training=executed(
                verify_content_hash=lambda: False,
            ),
            response_source=FakeResponseSource(
                capture()
            ),
            session=object(),
            created_at=dt(12),
        )


@pytest.mark.asyncio
async def test_rejects_execution_authority_escalation():
    with pytest.raises(
        AuthoritativeTrainingResponseExecutionInvalid,
        match="stronger",
    ):
        await assemble_authoritative_training_response(
            athlete_id=ATHLETE_ID,
            response_source_id=RESPONSE_ID,
            executed_training=executed(
                phase_alignment_verified=True,
            ),
            response_source=FakeResponseSource(
                capture()
            ),
            session=object(),
            created_at=dt(12),
        )


@pytest.mark.asyncio
async def test_response_observation_cannot_predate_executed_training():
    with pytest.raises(
        AuthoritativeTrainingResponseTemporalInvalid,
        match="cannot predate",
    ):
        await assemble_authoritative_training_response(
            athlete_id=ATHLETE_ID,
            response_source_id=RESPONSE_ID,
            executed_training=executed(
                observed_at=dt(10),
            ),
            response_source=FakeResponseSource(
                capture(
                    observed_at=dt(8),
                    available_at=dt(11),
                )
            ),
            session=object(),
            created_at=dt(12),
        )


@pytest.mark.asyncio
async def test_artifact_creation_cannot_precede_required_authority():
    with pytest.raises(
        AuthoritativeTrainingResponseTemporalInvalid,
        match="cannot predate",
    ):
        await assemble_authoritative_training_response(
            athlete_id=ATHLETE_ID,
            response_source_id=RESPONSE_ID,
            executed_training=executed(
                created_at=dt(12),
            ),
            response_source=FakeResponseSource(
                capture(
                    available_at=dt(11),
                )
            ),
            session=object(),
            created_at=dt(10),
        )
