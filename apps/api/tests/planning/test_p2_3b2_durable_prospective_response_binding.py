from dataclasses import dataclass, replace
from datetime import datetime, timezone

import pytest

import app.planning.application.bind_personal_response_prediction_outcome as binder

from app.planning.domain.common.enums import (
    KnowledgeStatus,
)
from app.planning.domain.common.serialization import (
    CONTENT_HASH_ALGORITHM,
    canonical_json,
    compute_content_hash,
)
from app.planning.domain.persistence.audit import (
    AuditArtifactConflictError,
    AuditArtifactKind,
    AuditArtifactRecord,
    AuditArtifactSaveResult,
    AuditArtifactSaveStatus,
)
from app.planning.domain.response_evidence import (
    TRAINING_RESPONSE_EVIDENCE_SCHEMA_V02,
    TrainingResponseInterpretation,
    TrainingResponseKind,
    TrainingResponseLinkBasis,
    TrainingResponseMeasurement,
    TrainingResponseTiming,
)
from app.planning.domain.executed_training import (
    AUTHORITATIVE_EXECUTED_TRAINING_SCHEMA_VERSION,
)
from app.planning.domain.training_dynamics import (
    EffectEvidenceLevel,
    PersonalAssociationPredictorKey,
    PersonalResponsePredictionDirection,
    ProspectiveResponseChallengeResult,
    ResponseMetricReferenceKey,
)
from app.planning.domain.training_dynamics.prospective_issuance import (
    PERSONAL_RESPONSE_PREDICTION_ISSUANCE_HASH_EXCLUDE_FIELDS,
    PERSONAL_RESPONSE_PREDICTION_ISSUANCE_RULES_V01,
    PERSONAL_RESPONSE_PREDICTION_ISSUANCE_SCHEMA_V01,
    PersonalResponsePredictionIssuanceContract,
)


UTC = timezone.utc

ATHLETE = "11111111-1111-4111-8111-111111111111"
SESSION = "22222222-2222-4222-8222-222222222222"


def dt(hour: int) -> datetime:
    return datetime(
        2026,
        10,
        21,
        hour,
        tzinfo=UTC,
    )


class FakeSession:
    def __init__(self):
        self.commit_count = 0
        self.rollback_count = 0

    async def commit(self):
        self.commit_count += 1

    async def rollback(self):
        self.rollback_count += 1


class FakeAuditRepository:
    def __init__(
        self,
        *,
        database_clock=None,
    ):
        self.records = {}
        self.database_clock = (
            database_clock
            or (lambda: dt(16))
        )

    async def get(
        self,
        *,
        artifact_kind,
        artifact_id,
    ):
        return self.records.get(
            (
                artifact_kind,
                artifact_id,
            )
        )

    async def save(self, record):
        if record.persisted_at is not None:
            raise ValueError(
                "persisted_at must be database-assigned."
            )

        key = (
            record.artifact_kind,
            record.artifact_id,
        )

        existing = self.records.get(key)

        if existing is not None:
            if (
                existing.athlete_id
                != record.athlete_id
                or existing.content_hash
                != record.content_hash
                or existing.contract_json
                != record.contract_json
            ):
                raise AuditArtifactConflictError(
                    "Immutable audit artifact conflict."
                )

            return AuditArtifactSaveResult(
                status=(
                    AuditArtifactSaveStatus
                    .ALREADY_PRESENT
                ),
                artifact_kind=record.artifact_kind,
                artifact_id=record.artifact_id,
                content_hash=record.content_hash,
            )

        stored = replace(
            record,
            persisted_at=self.database_clock(),
        )

        self.records[key] = stored

        return AuditArtifactSaveResult(
            status=AuditArtifactSaveStatus.CREATED,
            artifact_kind=record.artifact_kind,
            artifact_id=record.artifact_id,
            content_hash=record.content_hash,
        )


def issuance():
    provisional = PersonalResponsePredictionIssuanceContract(
        issuance_id="PENDING",
        schema_version=(
            PERSONAL_RESPONSE_PREDICTION_ISSUANCE_SCHEMA_V01
        ),
        rules_version=(
            PERSONAL_RESPONSE_PREDICTION_ISSUANCE_RULES_V01
        ),

        athlete_id=ATHLETE,
        workout_session_id=SESSION,

        source_candidate_id="candidate-1",
        source_candidate_content_hash="a" * 64,
        source_candidate_schema_version=(
            "personal-response-prediction-candidate-v0.1"
        ),
        source_candidate_rules_version=(
            "personal-response-prediction-rules-v0.1"
        ),

        model_id="personal-monotonic-median-direction",
        model_version="0.1.0",

        predictor_key=PersonalAssociationPredictorKey(
            metric_key="training_load_index",
            unit="au",
        ),

        response_key=ResponseMetricReferenceKey(
            metric_key="self_reported_fatigue_score",
            unit="score_0_10",
            response_timing=TrainingResponseTiming.SAME_DAY,
            stimulus_modality_key="RUNNING",
        ),

        information_cutoff_at=dt(10),
        prediction_at=dt(11),

        target_predictor_value=4.5,
        historical_response_median=3.0,

        predicted_response_direction=(
            PersonalResponsePredictionDirection
            .ABOVE_HISTORICAL_MEDIAN
        ),

        response_prediction_available=True,

        evidence_level_ceiling=(
            EffectEvidenceLevel.ASSOCIATION_SUPPORTED
        ),
        association_supported=True,

        prospective_validation_established=False,
        causal_attribution_established=False,
        effect_inference_authorized=False,
        readiness_inference_authorized=False,
        performance_prediction_authorized=False,
        prescription_change_authorized=False,
        planning_authorized=False,

        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash="",
    )

    digest = compute_content_hash(
        provisional,
        exclude_fields=(
            PERSONAL_RESPONSE_PREDICTION_ISSUANCE_HASH_EXCLUDE_FIELDS
        ),
    )

    return replace(
        provisional,
        issuance_id=(
            "pt-personal-response-prediction-issuance:"
            + digest
        ),
        content_hash=digest,
    )


@dataclass(frozen=True)
class ExecutedStub:
    artifact_id: str
    schema_version: str

    athlete_id: str
    workout_session_id: str

    modality_key: str

    plan_identity_linked: bool
    plan_content_at_execution_status: str

    occurrence_alignment_verified: bool
    phase_alignment_verified: bool
    provider_event_verified: bool
    clock_alignment_verified: bool
    actual_boundary_verified: bool
    temporal_match_used: bool

    created_at: datetime

    content_hash: str
    hash_valid: bool = True

    def verify_content_hash(self):
        return self.hash_valid


@dataclass(frozen=True)
class ResponseStub:
    artifact_id: str
    schema_version: str

    athlete_id: str
    workout_session_id: str

    executed_training_evidence_id: str
    executed_training_evidence_hash: str

    response_kind: TrainingResponseKind
    response_timing: TrainingResponseTiming
    session_link_basis: TrainingResponseLinkBasis

    observed_at: datetime
    available_at: datetime

    measurements: tuple[
        TrainingResponseMeasurement,
        ...,
    ]

    interpretation: TrainingResponseInterpretation
    session_identity_linked: bool

    causal_attribution_established: bool
    readiness_inference_authorized: bool
    fatigue_diagnosis_authorized: bool
    performance_prediction_authorized: bool
    prescription_change_authorized: bool

    created_at: datetime

    content_hash: str
    hash_valid: bool = True

    def verify_content_hash(self):
        return self.hash_valid


def executed(
    *,
    content_hash="b" * 64,
):
    return ExecutedStub(
        artifact_id=(
            "pt-executed-training-evidence:"
            f"session:{SESSION}"
        ),
        schema_version=(
            AUTHORITATIVE_EXECUTED_TRAINING_SCHEMA_VERSION
        ),

        athlete_id=ATHLETE,
        workout_session_id=SESSION,

        modality_key="RUNNING",

        plan_identity_linked=True,
        plan_content_at_execution_status="unverified",

        occurrence_alignment_verified=False,
        phase_alignment_verified=False,
        provider_event_verified=False,
        clock_alignment_verified=False,
        actual_boundary_verified=False,
        temporal_match_used=False,

        created_at=dt(9),

        content_hash=content_hash,
    )


def response(
    *,
    artifact_id=(
        "pt-training-response-evidence:response-1"
    ),
    content_hash="c" * 64,
    value=4.0,
    observed_at=None,
    available_at=None,
    executed_hash="b" * 64,
):
    execution = executed(
        content_hash=executed_hash
    )

    return ResponseStub(
        artifact_id=artifact_id,
        schema_version=(
            TRAINING_RESPONSE_EVIDENCE_SCHEMA_V02
        ),

        athlete_id=ATHLETE,
        workout_session_id=SESSION,

        executed_training_evidence_id=(
            execution.artifact_id
        ),
        executed_training_evidence_hash=(
            executed_hash
        ),

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

        observed_at=(
            observed_at or dt(13)
        ),
        available_at=(
            available_at or dt(14)
        ),

        measurements=(
            TrainingResponseMeasurement(
                metric_key=(
                    "self_reported_fatigue_score"
                ),
                knowledge_status=(
                    KnowledgeStatus.KNOWN
                ),
                value=value,
                unit="score_0_10",
            ),
        ),

        interpretation=(
            TrainingResponseInterpretation
            .DESCRIPTIVE_ONLY
        ),
        session_identity_linked=True,

        causal_attribution_established=False,
        readiness_inference_authorized=False,
        fatigue_diagnosis_authorized=False,
        performance_prediction_authorized=False,
        prescription_change_authorized=False,

        created_at=dt(14),

        content_hash=content_hash,
    )


def issuance_record(
    source,
    *,
    persisted_at=dt(12),
):
    return AuditArtifactRecord(
        artifact_kind=(
            AuditArtifactKind
            .PERSONAL_RESPONSE_PREDICTION_ISSUANCE
        ),
        artifact_id=source.issuance_id,
        athlete_id=source.athlete_id,
        schema_version=source.schema_version,
        created_at=source.prediction_at,
        content_hash_algorithm=(
            source.content_hash_algorithm
        ),
        content_hash=source.content_hash,
        contract_json=canonical_json(source),
        persisted_at=persisted_at,
    )


def response_record(
    source,
    *,
    persisted_at=dt(15),
):
    return AuditArtifactRecord(
        artifact_kind=(
            AuditArtifactKind
            .AUTHORITATIVE_TRAINING_RESPONSE
        ),
        artifact_id=source.artifact_id,
        athlete_id=source.athlete_id,
        schema_version=source.schema_version,
        created_at=source.created_at,
        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash=source.content_hash,
        contract_json="response-stub",
        persisted_at=persisted_at,
    )


def executed_record(source):
    return AuditArtifactRecord(
        artifact_kind=(
            AuditArtifactKind
            .AUTHORITATIVE_EXECUTED_TRAINING
        ),
        artifact_id=source.artifact_id,
        athlete_id=source.athlete_id,
        schema_version=source.schema_version,
        created_at=source.created_at,
        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash=source.content_hash,
        contract_json="executed-stub",
        persisted_at=dt(10),
    )


def install_restorers(
    monkeypatch,
    *,
    responses,
    executions,
):
    def restore_response(record):
        return responses[
            record.artifact_id
        ]

    def restore_execution(record):
        return executions[
            record.artifact_id
        ]

    monkeypatch.setattr(
        binder,
        "restore_authoritative_training_response_audit_artifact",
        restore_response,
    )

    monkeypatch.setattr(
        binder,
        "restore_authoritative_executed_training_audit_artifact",
        restore_execution,
    )


def repository_with_sources(
    *,
    response_value=None,
    issuance_persisted_at=dt(12),
    response_persisted_at=dt(15),
    database_clock=None,
):
    prediction = issuance()

    response_source = (
        response_value
        if response_value is not None
        else response()
    )

    execution = executed(
        content_hash=(
            response_source
            .executed_training_evidence_hash
        )
    )

    repository = FakeAuditRepository(
        database_clock=database_clock,
    )

    records = (
        issuance_record(
            prediction,
            persisted_at=issuance_persisted_at,
        ),
        response_record(
            response_source,
            persisted_at=response_persisted_at,
        ),
        executed_record(
            execution
        ),
    )

    for record in records:
        repository.records[
            (
                record.artifact_kind,
                record.artifact_id,
            )
        ] = record

    return (
        repository,
        prediction,
        response_source,
        execution,
    )


@pytest.mark.asyncio
async def test_first_binding_persists_replayed_prospective_challenge(
    monkeypatch,
):
    (
        repository,
        prediction,
        response_source,
        execution,
    ) = repository_with_sources()

    install_restorers(
        monkeypatch,
        responses={
            response_source.artifact_id:
                response_source,
        },
        executions={
            execution.artifact_id:
                execution,
        },
    )

    session = FakeSession()

    result = await (
        binder.bind_personal_response_prediction_outcome(
            athlete_id=ATHLETE,
            issuance_id=prediction.issuance_id,
            response_artifact_id=(
                response_source.artifact_id
            ),
            audit_repository=repository,
            session=session,
        )
    )

    assert (
        result.challenge.result
        == ProspectiveResponseChallengeResult
        .DIRECTION_MATCHED
    )

    assert (
        result.binding_persisted_at
        == dt(16)
    )

    assert result.reused_durable_binding is False
    assert result.prospective_challenge_established is True

    assert (
        result.prospective_validation_established
        is False
    )
    assert result.planning_authorized is False

    assert session.commit_count == 1
    assert session.rollback_count == 0

    key = (
        AuditArtifactKind
        .PERSONAL_RESPONSE_PREDICTION_OUTCOME,
        result.challenge.binding_id,
    )

    stored = repository.records[key]

    assert stored.persisted_at == dt(16)
    assert (
        stored.contract_json
        == canonical_json(result.challenge)
    )
    assert (
        stored.content_hash
        == result.challenge.content_hash
    )


@pytest.mark.asyncio
async def test_retry_replays_sources_and_preserves_first_binding_time(
    monkeypatch,
):
    (
        repository,
        prediction,
        response_source,
        execution,
    ) = repository_with_sources()

    install_restorers(
        monkeypatch,
        responses={
            response_source.artifact_id:
                response_source,
        },
        executions={
            execution.artifact_id:
                execution,
        },
    )

    first = await (
        binder.bind_personal_response_prediction_outcome(
            athlete_id=ATHLETE,
            issuance_id=prediction.issuance_id,
            response_artifact_id=(
                response_source.artifact_id
            ),
            audit_repository=repository,
            session=FakeSession(),
        )
    )

    repository.database_clock = (
        lambda: dt(18)
    )

    second = await (
        binder.bind_personal_response_prediction_outcome(
            athlete_id=ATHLETE,
            issuance_id=prediction.issuance_id,
            response_artifact_id=(
                response_source.artifact_id
            ),
            audit_repository=repository,
            session=FakeSession(),
        )
    )

    assert (
        second.challenge.content_hash
        == first.challenge.content_hash
    )
    assert (
        second.binding_persisted_at
        == dt(16)
    )
    assert second.reused_durable_binding is True


@pytest.mark.asyncio
async def test_missing_issuance_database_timestamp_fails_closed(
    monkeypatch,
):
    (
        repository,
        prediction,
        response_source,
        execution,
    ) = repository_with_sources(
        issuance_persisted_at=None,
    )

    install_restorers(
        monkeypatch,
        responses={
            response_source.artifact_id:
                response_source,
        },
        executions={
            execution.artifact_id:
                execution,
        },
    )

    session = FakeSession()

    with pytest.raises(
        binder.ProspectiveResponseBindingError,
        match="Prediction issuance has no database",
    ):
        await (
            binder.bind_personal_response_prediction_outcome(
                athlete_id=ATHLETE,
                issuance_id=prediction.issuance_id,
                response_artifact_id=(
                    response_source.artifact_id
                ),
                audit_repository=repository,
                session=session,
            )
        )

    assert session.commit_count == 0
    assert session.rollback_count == 1


@pytest.mark.asyncio
async def test_missing_response_database_timestamp_fails_closed(
    monkeypatch,
):
    (
        repository,
        prediction,
        response_source,
        execution,
    ) = repository_with_sources(
        response_persisted_at=None,
    )

    install_restorers(
        monkeypatch,
        responses={
            response_source.artifact_id:
                response_source,
        },
        executions={
            execution.artifact_id:
                execution,
        },
    )

    with pytest.raises(
        binder.ProspectiveResponseBindingError,
        match="training response has no database",
    ):
        await (
            binder.bind_personal_response_prediction_outcome(
                athlete_id=ATHLETE,
                issuance_id=prediction.issuance_id,
                response_artifact_id=(
                    response_source.artifact_id
                ),
                audit_repository=repository,
                session=FakeSession(),
            )
        )


@pytest.mark.asyncio
async def test_response_observed_at_or_before_issuance_is_not_prospective(
    monkeypatch,
):
    response_source = response(
        observed_at=dt(12),
    )

    (
        repository,
        prediction,
        _,
        execution,
    ) = repository_with_sources(
        response_value=response_source,
    )

    install_restorers(
        monkeypatch,
        responses={
            response_source.artifact_id:
                response_source,
        },
        executions={
            execution.artifact_id:
                execution,
        },
    )

    session = FakeSession()

    with pytest.raises(
        ValueError,
        match="strictly predate response observation",
    ):
        await (
            binder.bind_personal_response_prediction_outcome(
                athlete_id=ATHLETE,
                issuance_id=prediction.issuance_id,
                response_artifact_id=(
                    response_source.artifact_id
                ),
                audit_repository=repository,
                session=session,
            )
        )

    assert session.rollback_count == 1

    assert not any(
        kind
        == AuditArtifactKind
        .PERSONAL_RESPONSE_PREDICTION_OUTCOME
        for kind, _ in repository.records
    )


@pytest.mark.asyncio
async def test_response_must_hash_bind_restored_execution(
    monkeypatch,
):
    response_source = response(
        executed_hash="b" * 64,
    )

    execution = executed(
        content_hash="e" * 64,
    )

    prediction = issuance()

    repository = FakeAuditRepository()

    for record in (
        issuance_record(prediction),
        response_record(response_source),
        executed_record(execution),
    ):
        repository.records[
            (
                record.artifact_kind,
                record.artifact_id,
            )
        ] = record

    install_restorers(
        monkeypatch,
        responses={
            response_source.artifact_id:
                response_source,
        },
        executions={
            execution.artifact_id:
                execution,
        },
    )

    with pytest.raises(
        binder.ProspectiveResponseBindingError,
        match="hash-bind",
    ):
        await (
            binder.bind_personal_response_prediction_outcome(
                athlete_id=ATHLETE,
                issuance_id=prediction.issuance_id,
                response_artifact_id=(
                    response_source.artifact_id
                ),
                audit_repository=repository,
                session=FakeSession(),
            )
        )


@pytest.mark.asyncio
async def test_tampered_existing_binding_fails_replay(
    monkeypatch,
):
    (
        repository,
        prediction,
        response_source,
        execution,
    ) = repository_with_sources()

    install_restorers(
        monkeypatch,
        responses={
            response_source.artifact_id:
                response_source,
        },
        executions={
            execution.artifact_id:
                execution,
        },
    )

    first = await (
        binder.bind_personal_response_prediction_outcome(
            athlete_id=ATHLETE,
            issuance_id=prediction.issuance_id,
            response_artifact_id=(
                response_source.artifact_id
            ),
            audit_repository=repository,
            session=FakeSession(),
        )
    )

    key = (
        AuditArtifactKind
        .PERSONAL_RESPONSE_PREDICTION_OUTCOME,
        first.challenge.binding_id,
    )

    repository.records[key] = replace(
        repository.records[key],
        contract_json="{}",
    )

    session = FakeSession()

    with pytest.raises(
        binder.ProspectiveResponseBindingConflictError,
        match="differs from deterministic source replay",
    ):
        await (
            binder.bind_personal_response_prediction_outcome(
                athlete_id=ATHLETE,
                issuance_id=prediction.issuance_id,
                response_artifact_id=(
                    response_source.artifact_id
                ),
                audit_repository=repository,
                session=session,
            )
        )

    assert session.rollback_count == 1


@pytest.mark.asyncio
async def test_second_response_for_same_issuance_conflicts(
    monkeypatch,
):
    (
        repository,
        prediction,
        first_response,
        execution,
    ) = repository_with_sources()

    second_response = response(
        artifact_id=(
            "pt-training-response-evidence:response-2"
        ),
        content_hash="d" * 64,
        value=2.0,
    )

    repository.records[
        (
            AuditArtifactKind
            .AUTHORITATIVE_TRAINING_RESPONSE,
            second_response.artifact_id,
        )
    ] = response_record(
        second_response,
        persisted_at=dt(17),
    )

    install_restorers(
        monkeypatch,
        responses={
            first_response.artifact_id:
                first_response,
            second_response.artifact_id:
                second_response,
        },
        executions={
            execution.artifact_id:
                execution,
        },
    )

    first = await (
        binder.bind_personal_response_prediction_outcome(
            athlete_id=ATHLETE,
            issuance_id=prediction.issuance_id,
            response_artifact_id=(
                first_response.artifact_id
            ),
            audit_repository=repository,
            session=FakeSession(),
        )
    )

    session = FakeSession()

    with pytest.raises(
        binder.ProspectiveResponseBindingConflictError,
        match="differs from deterministic source replay",
    ):
        await (
            binder.bind_personal_response_prediction_outcome(
                athlete_id=ATHLETE,
                issuance_id=prediction.issuance_id,
                response_artifact_id=(
                    second_response.artifact_id
                ),
                audit_repository=repository,
                session=session,
            )
        )

    # Stable identity is issuance-based, so the alternative response
    # cannot become a second challenge for this issuance.
    assert first.challenge.binding_id

    assert session.rollback_count == 1



@pytest.mark.asyncio
async def test_persisted_binding_contract_restores_canonically(
    monkeypatch,
):
    (
        repository,
        prediction,
        response_source,
        execution,
    ) = repository_with_sources()

    install_restorers(
        monkeypatch,
        responses={
            response_source.artifact_id:
                response_source,
        },
        executions={
            execution.artifact_id:
                execution,
        },
    )

    result = await (
        binder.bind_personal_response_prediction_outcome(
            athlete_id=ATHLETE,
            issuance_id=prediction.issuance_id,
            response_artifact_id=(
                response_source.artifact_id
            ),
            audit_repository=repository,
            session=FakeSession(),
        )
    )

    stored = repository.records[
        (
            AuditArtifactKind
            .PERSONAL_RESPONSE_PREDICTION_OUTCOME,
            result.challenge.binding_id,
        )
    ]

    restored = (
        binder.restore_personal_response_prediction_outcome_audit_artifact(
            stored
        )
    )

    assert restored == result.challenge
    assert restored.verify_content_hash()
