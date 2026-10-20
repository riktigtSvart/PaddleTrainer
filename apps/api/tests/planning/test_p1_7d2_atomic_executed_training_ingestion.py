from datetime import datetime, timedelta, timezone

import inspect
import pytest

import app.planning.application.ingest_authoritative_executed_training as ingestion
from app.planning.application.build_authoritative_executed_training import (
    assemble_authoritative_executed_training_with_repository,
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
)


UTC = timezone.utc

ATHLETE = "11111111-1111-4111-8111-111111111111"
SESSION = "22222222-2222-4222-8222-222222222222"
WORKOUT = "33333333-3333-4333-8333-333333333333"

NOW = datetime(
    2026,
    10,
    20,
    7,
    0,
    tzinfo=UTC,
)

LATER = NOW + timedelta(hours=1)


def source_artifact():
    link = finalize_authoritative_plan_execution_link(
        link_id="pt-exec-link:d2-test",
        athlete_id=ATHLETE,
        logical_plan_id=f"planned-workout:{WORKOUT}",
        observed_revision_id="pt-plan-rev:d2-test",
        workout_session_id=SESSION,
        source_workout_id=WORKOUT,
        link_basis=ExecutionLinkBasis.EXACT_PROVIDER_ID,
        provider_target_id="target-d2",
        source_workout_content_hash="a" * 64,
        session_source_content_hash="b" * 64,
        observed_revision_content_hash="c" * 64,
        created_at=NOW - timedelta(minutes=5),
    )

    return build_authoritative_executed_training_evidence(
        artifact_id=(
            "pt-executed-training-evidence:"
            f"session:{SESSION}"
        ),
        plan_execution_link=link,
        occurrence_execution_links=(),
        observed_at=NOW - timedelta(hours=1),
        modality_key="RUNNING",
        duration_status=KnowledgeStatus.KNOWN,
        duration_s=3600,
        created_at=NOW,
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
    def __init__(self):
        self.record = None
        self.saved = []
        self.get_calls = []

    async def get(
        self,
        *,
        artifact_kind,
        artifact_id,
    ):
        self.get_calls.append(
            (artifact_kind, artifact_id)
        )

        if self.record is None:
            return None

        if (
            self.record.artifact_kind == artifact_kind
            and self.record.artifact_id == artifact_id
        ):
            return self.record

        return None

    async def save(self, record):
        self.saved.append(record)

        if self.record is not None:
            raise AssertionError(
                "Durable artifact must not be rewritten."
            )

        self.record = record
        return None


class FakeEvidenceRepository:
    def __init__(self, *, error=None):
        self.error = error
        self.items = {}
        self.save_calls = []

    async def save(self, item):
        self.save_calls.append(item)

        if self.error is not None:
            raise self.error

        existing = self.items.get(item.evidence_id)

        if existing is None:
            self.items[item.evidence_id] = item
            return item

        assert existing.content_hash == item.content_hash
        assert existing.source_ref == item.source_ref
        assert existing.payload == item.payload

        return existing


def test_p1_7b_transaction_neutral_assembler_has_no_commit_or_rollback():
    source = inspect.getsource(
        assemble_authoritative_executed_training_with_repository
    )

    assert "session.commit" not in source
    assert "session.rollback" not in source


def test_durable_artifact_identity_is_session_stable():
    assert (
        ingestion.authoritative_executed_training_artifact_id(
            SESSION
        )
        == (
            "pt-executed-training-evidence:"
            f"session:{SESSION}"
        )
    )


@pytest.mark.asyncio
async def test_first_ingestion_saves_artifact_and_projection_then_commits(
    monkeypatch,
):
    artifact = source_artifact()
    assemble_calls = []

    async def assemble(**kwargs):
        assemble_calls.append(kwargs)

        assert kwargs["created_at"] == NOW
        assert (
            kwargs["id_factory"]()
            == f"session:{SESSION}"
        )

        return artifact

    monkeypatch.setattr(
        ingestion,
        "assemble_authoritative_executed_training_with_repository",
        assemble,
    )

    audit = FakeAuditRepository()
    evidence = FakeEvidenceRepository()
    session = FakeSession()

    result = await ingestion.ingest_authoritative_executed_training(
        athlete_id=ATHLETE,
        workout_session_id=SESSION,
        execution_link_repository=object(),
        occurrence_execution_repository=object(),
        execution_source=object(),
        audit_repository=audit,
        evidence_repository=evidence,
        session=session,
        created_at=NOW,
    )

    assert len(assemble_calls) == 1
    assert len(audit.saved) == 1
    assert len(evidence.save_calls) == 1

    record = audit.saved[0]

    assert (
        record.artifact_kind
        == AuditArtifactKind.AUTHORITATIVE_EXECUTED_TRAINING
    )
    assert record.artifact_id == artifact.artifact_id
    assert record.content_hash == artifact.content_hash
    assert record.contract_json == canonical_json(artifact)

    assert (
        result.evidence.source_ref.source_record_id
        == artifact.artifact_id
    )
    assert (
        result.evidence.source_ref.source_content_hash
        == artifact.content_hash
    )

    assert result.reused_durable_artifact is False
    assert session.commit_count == 1
    assert session.rollback_count == 0


@pytest.mark.asyncio
async def test_retry_reuses_durable_freeze_without_mutable_recapture(
    monkeypatch,
):
    artifact = source_artifact()

    async def first_assemble(**kwargs):
        return artifact

    monkeypatch.setattr(
        ingestion,
        "assemble_authoritative_executed_training_with_repository",
        first_assemble,
    )

    audit = FakeAuditRepository()
    evidence = FakeEvidenceRepository()
    session = FakeSession()

    first = await ingestion.ingest_authoritative_executed_training(
        athlete_id=ATHLETE,
        workout_session_id=SESSION,
        execution_link_repository=object(),
        occurrence_execution_repository=object(),
        execution_source=object(),
        audit_repository=audit,
        evidence_repository=evidence,
        session=session,
        created_at=NOW,
    )

    async def explode(**kwargs):
        raise AssertionError(
            "Retry must not recapture mutable execution source."
        )

    monkeypatch.setattr(
        ingestion,
        "assemble_authoritative_executed_training_with_repository",
        explode,
    )

    second = await ingestion.ingest_authoritative_executed_training(
        athlete_id=ATHLETE,
        workout_session_id=SESSION,
        execution_link_repository=object(),
        occurrence_execution_repository=object(),
        execution_source=object(),
        audit_repository=audit,
        evidence_repository=evidence,
        session=session,
        created_at=LATER,
    )

    assert len(audit.saved) == 1
    assert len(evidence.items) == 1

    assert second.reused_durable_artifact is True
    assert second.artifact == first.artifact
    assert second.evidence == first.evidence

    assert session.commit_count == 2
    assert session.rollback_count == 0


@pytest.mark.asyncio
async def test_projection_persistence_failure_rolls_back_transaction(
    monkeypatch,
):
    artifact = source_artifact()

    async def assemble(**kwargs):
        return artifact

    monkeypatch.setattr(
        ingestion,
        "assemble_authoritative_executed_training_with_repository",
        assemble,
    )

    error = RuntimeError("evidence persistence failed")

    audit = FakeAuditRepository()
    evidence = FakeEvidenceRepository(
        error=error
    )
    session = FakeSession()

    with pytest.raises(
        RuntimeError,
        match="evidence persistence failed",
    ):
        await ingestion.ingest_authoritative_executed_training(
            athlete_id=ATHLETE,
            workout_session_id=SESSION,
            execution_link_repository=object(),
            occurrence_execution_repository=object(),
            execution_source=object(),
            audit_repository=audit,
            evidence_repository=evidence,
            session=session,
            created_at=NOW,
        )

    assert len(audit.saved) == 1
    assert session.commit_count == 0
    assert session.rollback_count == 1


@pytest.mark.asyncio
async def test_commit_failure_rolls_back(
    monkeypatch,
):
    artifact = source_artifact()

    async def assemble(**kwargs):
        return artifact

    monkeypatch.setattr(
        ingestion,
        "assemble_authoritative_executed_training_with_repository",
        assemble,
    )

    audit = FakeAuditRepository()
    evidence = FakeEvidenceRepository()
    session = FakeSession(
        commit_error=RuntimeError("commit failed")
    )

    with pytest.raises(
        RuntimeError,
        match="commit failed",
    ):
        await ingestion.ingest_authoritative_executed_training(
            athlete_id=ATHLETE,
            workout_session_id=SESSION,
            execution_link_repository=object(),
            occurrence_execution_repository=object(),
            execution_source=object(),
            audit_repository=audit,
            evidence_repository=evidence,
            session=session,
            created_at=NOW,
        )

    assert session.commit_count == 1
    assert session.rollback_count == 1


@pytest.mark.asyncio
async def test_existing_cross_athlete_freeze_is_not_disclosed(
    monkeypatch,
):
    artifact = source_artifact()

    async def assemble(**kwargs):
        return artifact

    monkeypatch.setattr(
        ingestion,
        "assemble_authoritative_executed_training_with_repository",
        assemble,
    )

    audit = FakeAuditRepository()
    evidence = FakeEvidenceRepository()
    session = FakeSession()

    await ingestion.ingest_authoritative_executed_training(
        athlete_id=ATHLETE,
        workout_session_id=SESSION,
        execution_link_repository=object(),
        occurrence_execution_repository=object(),
        execution_source=object(),
        audit_repository=audit,
        evidence_repository=evidence,
        session=session,
        created_at=NOW,
    )

    audit.record = type(audit.record)(
        artifact_kind=audit.record.artifact_kind,
        artifact_id=audit.record.artifact_id,
        athlete_id="99999999-9999-4999-8999-999999999999",
        schema_version=audit.record.schema_version,
        created_at=audit.record.created_at,
        content_hash_algorithm=(
            audit.record.content_hash_algorithm
        ),
        content_hash=audit.record.content_hash,
        contract_json=audit.record.contract_json,
    )

    async def explode(**kwargs):
        raise AssertionError(
            "Cross-athlete durable evidence must not recapture."
        )

    monkeypatch.setattr(
        ingestion,
        "assemble_authoritative_executed_training_with_repository",
        explode,
    )

    with pytest.raises(
        ingestion.AuthoritativeExecutedTrainingNotFound
    ):
        await ingestion.ingest_authoritative_executed_training(
            athlete_id=ATHLETE,
            workout_session_id=SESSION,
            execution_link_repository=object(),
            occurrence_execution_repository=object(),
            execution_source=object(),
            audit_repository=audit,
            evidence_repository=evidence,
            session=session,
            created_at=LATER,
        )

    assert session.rollback_count == 1
