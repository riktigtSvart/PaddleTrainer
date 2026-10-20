from datetime import datetime, timedelta, timezone
import inspect

import pytest

import app.planning.application.ingest_authoritative_training_response as ingestion
from app.planning.application.build_authoritative_training_response import (
    assemble_authoritative_training_response_from_capture,
)
from app.planning.domain.common.enums import KnowledgeStatus
from app.planning.domain.common.serialization import canonical_json
from app.planning.domain.executed_training.models import (
    build_authoritative_executed_training_evidence,
)
from app.planning.domain.execution_link import (
    ExecutionLinkBasis,
    finalize_authoritative_plan_execution_link,
)
from app.planning.domain.persistence.audit import (
    AuditArtifactKind,
    AuditArtifactRecord,
)
from app.planning.domain.response_evidence import (
    TrainingResponseKind,
    TrainingResponseMeasurement,
    TrainingResponseTiming,
)
from app.planning.domain.response_evidence.source_capture import (
    build_training_response_source_capture,
)


UTC = timezone.utc

ATHLETE = "11111111-1111-4111-8111-111111111111"
SESSION = "22222222-2222-4222-8222-222222222222"
WORKOUT = "33333333-3333-4333-8333-333333333333"
RESPONSE = "44444444-4444-4444-8444-444444444444"

NOW = datetime(
    2026,
    10,
    20,
    12,
    0,
    tzinfo=UTC,
)

LATER = NOW + timedelta(hours=1)


def executed_artifact():
    link = finalize_authoritative_plan_execution_link(
        link_id="pt-exec-link:p1-8c",
        athlete_id=ATHLETE,
        logical_plan_id=f"planned-workout:{WORKOUT}",
        observed_revision_id="pt-plan-rev:p1-8c",
        workout_session_id=SESSION,
        source_workout_id=WORKOUT,
        link_basis=ExecutionLinkBasis.EXACT_PROVIDER_ID,
        provider_target_id="target-p1-8c",
        source_workout_content_hash="a" * 64,
        session_source_content_hash="b" * 64,
        observed_revision_content_hash="c" * 64,
        created_at=NOW - timedelta(hours=2),
    )

    return build_authoritative_executed_training_evidence(
        artifact_id=(
            "pt-executed-training-evidence:"
            f"session:{SESSION}"
        ),
        plan_execution_link=link,
        occurrence_execution_links=(),
        observed_at=NOW - timedelta(hours=3),
        modality_key="RUNNING",
        duration_status=KnowledgeStatus.KNOWN,
        duration_s=3600,
        created_at=NOW - timedelta(hours=2),
    )


def execution_record():
    artifact = executed_artifact()

    return AuditArtifactRecord(
        artifact_kind=(
            AuditArtifactKind.AUTHORITATIVE_EXECUTED_TRAINING
        ),
        artifact_id=artifact.artifact_id,
        athlete_id=artifact.athlete_id,
        schema_version=artifact.schema_version,
        created_at=artifact.created_at,
        content_hash_algorithm=artifact.content_hash_algorithm,
        content_hash=artifact.content_hash,
        contract_json=canonical_json(artifact),
    )


def response_capture():
    return build_training_response_source_capture(
        athlete_id=ATHLETE,
        workout_session_id=SESSION,
        response_source_id=RESPONSE,
        response_kind=TrainingResponseKind.SESSION_FEEDBACK,
        response_timing=TrainingResponseTiming.SAME_DAY,
        observed_at=NOW - timedelta(hours=1),
        available_at=NOW - timedelta(minutes=30),
        source_system="current_app_athlete_response",
        source_record_id=RESPONSE,
        source_record_version=(
            "current-app-athlete-response-source-v0.1"
        ),
        source_content_hash="d" * 64,
        measurements=(
            TrainingResponseMeasurement(
                metric_key="self_reported_fatigue_score",
                knowledge_status=KnowledgeStatus.KNOWN,
                value=6.0,
                unit=None,
            ),
        ),
    )


class FakeSession:
    def __init__(self, *, commit_error=None):
        self.commit_count = 0
        self.rollback_count = 0
        self.commit_error = commit_error

    async def commit(self):
        self.commit_count += 1

        if self.commit_error is not None:
            raise self.commit_error

    async def rollback(self):
        self.rollback_count += 1


class FakeAuditRepository:
    def __init__(self, *, save_error=None):
        self.records = {}
        self.saved = []
        self.get_calls = []
        self.save_error = save_error

    def preload(self, record):
        self.records[
            (
                record.artifact_kind,
                record.artifact_id,
            )
        ] = record

    async def get(
        self,
        *,
        artifact_kind,
        artifact_id,
    ):
        self.get_calls.append(
            (artifact_kind, artifact_id)
        )

        return self.records.get(
            (artifact_kind, artifact_id)
        )

    async def save(self, record):
        self.saved.append(record)

        if self.save_error is not None:
            raise self.save_error

        key = (
            record.artifact_kind,
            record.artifact_id,
        )

        if key in self.records:
            raise AssertionError(
                "Durable response artifact must not be rewritten."
            )

        self.records[key] = record
        return None


class FakeResponseSource:
    def __init__(self, value=None, *, error=None):
        self.value = value
        self.error = error
        self.calls = []

    async def lock_and_capture(
        self,
        session,
        *,
        athlete_id,
        response_source_id,
    ):
        self.calls.append(
            (athlete_id, response_source_id)
        )

        if self.error is not None:
            raise self.error

        return self.value


def test_b3_inner_assembler_is_transaction_neutral():
    source = inspect.getsource(
        assemble_authoritative_training_response_from_capture
    )

    assert "session.commit" not in source
    assert "session.rollback" not in source
    assert "lock_and_capture" not in source


def test_response_artifact_identity_is_source_stable():
    assert (
        ingestion.authoritative_training_response_artifact_id(
            RESPONSE
        )
        == (
            "pt-training-response-evidence:"
            f"athlete-response:{RESPONSE}"
        )
    )


@pytest.mark.asyncio
async def test_first_ingestion_saves_response_freeze_then_commits():
    audit = FakeAuditRepository()
    audit.preload(
        execution_record()
    )

    source = FakeResponseSource(
        response_capture()
    )

    session = FakeSession()

    result = await (
        ingestion.ingest_authoritative_training_response(
            athlete_id=ATHLETE,
            response_source_id=RESPONSE,
            response_source=source,
            audit_repository=audit,
            session=session,
            created_at=NOW,
        )
    )

    assert len(source.calls) == 1
    assert len(audit.saved) == 1

    saved = audit.saved[0]

    assert (
        saved.artifact_kind
        == AuditArtifactKind.AUTHORITATIVE_TRAINING_RESPONSE
    )

    assert (
        saved.artifact_id
        == (
            "pt-training-response-evidence:"
            f"athlete-response:{RESPONSE}"
        )
    )

    assert (
        saved.contract_json
        == canonical_json(result.artifact)
    )

    assert result.reused_durable_artifact is False

    assert session.commit_count == 1
    assert session.rollback_count == 0


@pytest.mark.asyncio
async def test_retry_reuses_durable_freeze_without_response_recapture():
    audit = FakeAuditRepository()
    audit.preload(
        execution_record()
    )

    session = FakeSession()

    first = await (
        ingestion.ingest_authoritative_training_response(
            athlete_id=ATHLETE,
            response_source_id=RESPONSE,
            response_source=FakeResponseSource(
                response_capture()
            ),
            audit_repository=audit,
            session=session,
            created_at=NOW,
        )
    )

    exploding_source = FakeResponseSource(
        error=AssertionError(
            "Retry must not recapture mutable AthleteResponse."
        )
    )

    second = await (
        ingestion.ingest_authoritative_training_response(
            athlete_id=ATHLETE,
            response_source_id=RESPONSE,
            response_source=exploding_source,
            audit_repository=audit,
            session=session,
            created_at=LATER,
        )
    )

    assert exploding_source.calls == []

    assert len(audit.saved) == 1

    assert second.reused_durable_artifact is True
    assert second.artifact == first.artifact

    assert session.commit_count == 2
    assert session.rollback_count == 0


@pytest.mark.asyncio
async def test_missing_durable_execution_rolls_back():
    audit = FakeAuditRepository()
    session = FakeSession()

    source = FakeResponseSource(
        response_capture()
    )

    with pytest.raises(
        ingestion.AuthoritativeTrainingResponseExecutionNotFound
    ):
        await ingestion.ingest_authoritative_training_response(
            athlete_id=ATHLETE,
            response_source_id=RESPONSE,
            response_source=source,
            audit_repository=audit,
            session=session,
            created_at=NOW,
        )

    assert len(source.calls) == 1
    assert len(audit.saved) == 0

    assert session.commit_count == 0
    assert session.rollback_count == 1


@pytest.mark.asyncio
async def test_response_audit_save_failure_rolls_back():
    error = RuntimeError(
        "response audit persistence failed"
    )

    audit = FakeAuditRepository(
        save_error=error
    )
    audit.preload(
        execution_record()
    )

    session = FakeSession()

    with pytest.raises(
        RuntimeError,
        match="response audit persistence failed",
    ):
        await ingestion.ingest_authoritative_training_response(
            athlete_id=ATHLETE,
            response_source_id=RESPONSE,
            response_source=FakeResponseSource(
                response_capture()
            ),
            audit_repository=audit,
            session=session,
            created_at=NOW,
        )

    assert len(audit.saved) == 1
    assert session.commit_count == 0
    assert session.rollback_count == 1


@pytest.mark.asyncio
async def test_commit_failure_rolls_back():
    audit = FakeAuditRepository()
    audit.preload(
        execution_record()
    )

    session = FakeSession(
        commit_error=RuntimeError("commit failed")
    )

    with pytest.raises(
        RuntimeError,
        match="commit failed",
    ):
        await ingestion.ingest_authoritative_training_response(
            athlete_id=ATHLETE,
            response_source_id=RESPONSE,
            response_source=FakeResponseSource(
                response_capture()
            ),
            audit_repository=audit,
            session=session,
            created_at=NOW,
        )

    assert session.commit_count == 1
    assert session.rollback_count == 1


@pytest.mark.asyncio
async def test_existing_cross_athlete_freeze_is_not_disclosed():
    audit = FakeAuditRepository()
    audit.preload(
        execution_record()
    )

    session = FakeSession()

    first = await (
        ingestion.ingest_authoritative_training_response(
            athlete_id=ATHLETE,
            response_source_id=RESPONSE,
            response_source=FakeResponseSource(
                response_capture()
            ),
            audit_repository=audit,
            session=session,
            created_at=NOW,
        )
    )

    key = (
        AuditArtifactKind.AUTHORITATIVE_TRAINING_RESPONSE,
        first.artifact.artifact_id,
    )

    record = audit.records[key]

    audit.records[key] = AuditArtifactRecord(
        artifact_kind=record.artifact_kind,
        artifact_id=record.artifact_id,
        athlete_id=(
            "99999999-9999-4999-8999-999999999999"
        ),
        schema_version=record.schema_version,
        created_at=record.created_at,
        content_hash_algorithm=(
            record.content_hash_algorithm
        ),
        content_hash=record.content_hash,
        contract_json=record.contract_json,
    )

    source = FakeResponseSource(
        error=AssertionError(
            "Cross-athlete freeze must not recapture source."
        )
    )

    with pytest.raises(
        ingestion.AuthoritativeTrainingResponseNotFound
    ):
        await ingestion.ingest_authoritative_training_response(
            athlete_id=ATHLETE,
            response_source_id=RESPONSE,
            response_source=source,
            audit_repository=audit,
            session=session,
            created_at=LATER,
        )

    assert source.calls == []
    assert session.rollback_count == 1


@pytest.mark.asyncio
async def test_tampered_persisted_response_contract_is_rejected():
    audit = FakeAuditRepository()
    audit.preload(
        execution_record()
    )

    session = FakeSession()

    first = await (
        ingestion.ingest_authoritative_training_response(
            athlete_id=ATHLETE,
            response_source_id=RESPONSE,
            response_source=FakeResponseSource(
                response_capture()
            ),
            audit_repository=audit,
            session=session,
            created_at=NOW,
        )
    )

    key = (
        AuditArtifactKind.AUTHORITATIVE_TRAINING_RESPONSE,
        first.artifact.artifact_id,
    )

    record = audit.records[key]

    audit.records[key] = AuditArtifactRecord(
        artifact_kind=record.artifact_kind,
        artifact_id=record.artifact_id,
        athlete_id=record.athlete_id,
        schema_version=record.schema_version,
        created_at=record.created_at,
        content_hash_algorithm=(
            record.content_hash_algorithm
        ),
        content_hash=record.content_hash,
        contract_json=record.contract_json.replace(
            '"descriptive_only"',
            '"tampered_interpretation"',
        ),
    )

    with pytest.raises(
        (ValueError,),
    ):
        await ingestion.ingest_authoritative_training_response(
            athlete_id=ATHLETE,
            response_source_id=RESPONSE,
            response_source=FakeResponseSource(
                error=AssertionError(
                    "Tampered durable freeze must not recapture."
                )
            ),
            audit_repository=audit,
            session=session,
            created_at=LATER,
        )

    assert session.rollback_count == 1
