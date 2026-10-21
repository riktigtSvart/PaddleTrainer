from dataclasses import replace
from datetime import datetime, timezone

import pytest

from app.planning.application.issue_personal_response_prediction import (
    PersonalResponsePredictionIssuanceError,
    issue_personal_response_prediction,
)
from app.planning.domain.common.serialization import (
    CONTENT_HASH_ALGORITHM,
    canonical_json,
)
from app.planning.domain.persistence.audit import (
    AuditArtifactConflictError,
    AuditArtifactKind,
    AuditArtifactRecord,
    AuditArtifactSaveResult,
    AuditArtifactSaveStatus,
)
from app.planning.domain.response_evidence import (
    TrainingResponseTiming,
)
from app.planning.domain.training_dynamics import (
    EffectEvidenceLevel,
    PersonalAssociationPredictorKey,
    PersonalResponsePredictionCandidate,
    PersonalResponsePredictionDirection,
    PersonalResponsePredictionStatus,
    ResponseMetricReferenceKey,
)
from app.planning.domain.training_dynamics.prospective_issuance import (
    PERSONAL_RESPONSE_PREDICTION_ISSUANCE_SCHEMA_V01,
    build_personal_response_prediction_issuance_contract,
)
from app.planning.domain.training_dynamics.prospective_prediction import (
    PERSONAL_RESPONSE_PREDICTION_MODEL_ID_V01,
    PERSONAL_RESPONSE_PREDICTION_MODEL_VERSION_V01,
    PERSONAL_RESPONSE_PREDICTION_RULES_V01,
    PERSONAL_RESPONSE_PREDICTION_SCHEMA_V01,
    _prediction_content_hash,
)


UTC = timezone.utc
ATHLETE = "11111111-1111-4111-8111-111111111111"


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
    def __init__(self, *, database_clock=None):
        self.records = {}
        self.drop_after_save = False
        self.database_clock = (
            database_clock
            or (lambda: dt(12))
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
                existing.content_hash
                != record.content_hash
                or existing.contract_json
                != record.contract_json
                or existing.athlete_id
                != record.athlete_id
            ):
                raise AuditArtifactConflictError(
                    "Immutable audit artifact identity "
                    "already exists with different content."
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

        if self.drop_after_save:
            self.records.pop(key)

        return AuditArtifactSaveResult(
            status=AuditArtifactSaveStatus.CREATED,
            artifact_kind=record.artifact_kind,
            artifact_id=record.artifact_id,
            content_hash=record.content_hash,
        )

    async def list_for_athlete(
        self,
        *,
        athlete_id,
        artifact_kind=None,
        limit=50,
    ):
        values = [
            record
            for record in self.records.values()
            if record.athlete_id == athlete_id
            and (
                artifact_kind is None
                or record.artifact_kind
                == artifact_kind
            )
        ]

        return tuple(values[:limit])


def finalize(candidate):
    provisional = replace(
        candidate,
        candidate_id="PENDING",
        content_hash="PENDING",
    )

    digest = _prediction_content_hash(
        provisional
    )

    return replace(
        provisional,
        candidate_id=(
            "pt-personal-response-prediction:"
            + digest
        ),
        content_hash=digest,
    )


def candidate(
    *,
    created_at=None,
    status=(
        PersonalResponsePredictionStatus
        .PREDICTION_AVAILABLE
    ),
    direction=(
        PersonalResponsePredictionDirection
        .ABOVE_HISTORICAL_MEDIAN
    ),
    prediction_available=True,
    planning_authorized=False,
):
    value = PersonalResponsePredictionCandidate(
        candidate_id="PENDING",
        schema_version=(
            PERSONAL_RESPONSE_PREDICTION_SCHEMA_V01
        ),
        rules_version=(
            PERSONAL_RESPONSE_PREDICTION_RULES_V01
        ),

        model_id=(
            PERSONAL_RESPONSE_PREDICTION_MODEL_ID_V01
        ),
        model_version=(
            PERSONAL_RESPONSE_PREDICTION_MODEL_VERSION_V01
        ),

        athlete_id=ATHLETE,
        workout_session_id="future-session",

        source_dataset_id="dataset-1",
        source_dataset_content_hash="a" * 64,

        source_estimate_id="estimate-1",
        source_estimate_content_hash="b" * 64,

        source_support_assessment_id="support-1",
        source_support_assessment_content_hash="c" * 64,

        source_association_evidence_id="association-1",
        source_association_evidence_content_hash="d" * 64,

        target_predictor_observation_id="target-1",
        target_predictor_observation_content_hash="e" * 64,

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

        historical_pair_count=5,

        historical_predictor_min=1.0,
        historical_predictor_median=3.0,
        historical_predictor_max=5.0,

        historical_response_median=3.0,

        source_spearman_rho=1.0,

        target_predictor_value=4.5,

        predicted_response_direction=direction,

        status=status,
        limitation_codes=(),

        information_cutoff_at=dt(10),
        prediction_at=dt(11),

        response_prediction_available=prediction_available,

        issuance_proof_established=False,

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
        planning_authorized=planning_authorized,

        created_at=created_at or dt(11),
        content_hash="PENDING",
    )

    return finalize(value)


@pytest.mark.asyncio
async def test_first_issue_creates_durable_proof():
    source = candidate()

    repository = FakeAuditRepository()
    session = FakeSession()

    result = await issue_personal_response_prediction(
        candidate=source,
        audit_repository=repository,
        session=session,
    )

    assert result.issuance_proof_established is True
    assert result.durable_issued_at == dt(12)

    assert result.reused_durable_issuance is False

    assert (
        result.prospective_validation_established
        is False
    )
    assert result.planning_authorized is False

    assert source.issuance_proof_established is False

    assert session.commit_count == 1
    assert session.rollback_count == 0

    key = (
        AuditArtifactKind
        .PERSONAL_RESPONSE_PREDICTION_ISSUANCE,
        result.issuance.issuance_id,
    )

    stored = repository.records[key]

    assert stored.created_at == source.prediction_at
    assert stored.persisted_at == dt(12)
    assert (
        stored.schema_version
        == PERSONAL_RESPONSE_PREDICTION_ISSUANCE_SCHEMA_V01
    )
    assert stored.content_hash == result.issuance.content_hash
    assert (
        stored.contract_json
        == canonical_json(result.issuance)
    )


@pytest.mark.asyncio
async def test_retry_preserves_first_durable_issuance_time():
    source = candidate()

    repository = FakeAuditRepository()

    first_session = FakeSession()

    first = await issue_personal_response_prediction(
        candidate=source,
        audit_repository=repository,
        session=first_session,
    )

    second_session = FakeSession()

    second = await issue_personal_response_prediction(
        candidate=source,
        audit_repository=repository,
        session=second_session,
    )

    assert first.durable_issued_at == dt(12)
    assert second.durable_issued_at == dt(12)

    assert second.reused_durable_issuance is True

    assert len(repository.records) == 1


@pytest.mark.asyncio
async def test_rematerialized_candidate_reuses_same_issuance():
    first_candidate = candidate(
        created_at=dt(11)
    )

    later_candidate = replace(
        first_candidate,
        created_at=dt(14),
    )

    # A1 identity intentionally excludes materialization time.
    assert later_candidate.verify_content_hash()

    repository = FakeAuditRepository()

    first = await issue_personal_response_prediction(
        candidate=first_candidate,
        audit_repository=repository,
        session=FakeSession(),
    )

    second = await issue_personal_response_prediction(
        candidate=later_candidate,
        audit_repository=repository,
        session=FakeSession(),
    )

    assert (
        first.issuance.issuance_id
        == second.issuance.issuance_id
    )
    assert (
        first.issuance.content_hash
        == second.issuance.content_hash
    )

    assert second.durable_issued_at == dt(12)
    assert second.reused_durable_issuance is True


def test_issuance_contract_is_deterministic():
    first = candidate(
        created_at=dt(11)
    )

    second = replace(
        first,
        created_at=dt(14),
    )

    first_contract = (
        build_personal_response_prediction_issuance_contract(
            first
        )
    )

    second_contract = (
        build_personal_response_prediction_issuance_contract(
            second
        )
    )

    assert (
        first_contract.issuance_id
        == second_contract.issuance_id
    )

    assert (
        first_contract.content_hash
        == second_contract.content_hash
    )

    assert first_contract.verify_content_hash()
    assert second_contract.verify_content_hash()

    assert (
        first_contract.content_hash_algorithm
        == CONTENT_HASH_ALGORITHM
    )


@pytest.mark.asyncio
async def test_withheld_prediction_cannot_be_issued():
    source = candidate(
        status=PersonalResponsePredictionStatus.WITHHELD,
        direction=None,
        prediction_available=False,
    )

    repository = FakeAuditRepository()
    session = FakeSession()

    with pytest.raises(
        ValueError,
        match="requires an available prediction",
    ):
        await issue_personal_response_prediction(
            candidate=source,
            audit_repository=repository,
            session=session,
        )

    assert not repository.records


@pytest.mark.asyncio
async def test_tampered_candidate_fails_closed():
    source = replace(
        candidate(),
        content_hash="bad",
    )

    repository = FakeAuditRepository()

    with pytest.raises(
        ValueError,
        match="content hash does not verify",
    ):
        await issue_personal_response_prediction(
            candidate=source,
            audit_repository=repository,
            session=FakeSession(),
        )


@pytest.mark.asyncio
async def test_stronger_authority_candidate_fails_closed():
    source = candidate(
        planning_authorized=True,
    )

    repository = FakeAuditRepository()

    with pytest.raises(
        ValueError,
        match="unsupported stronger authority",
    ):
        await issue_personal_response_prediction(
            candidate=source,
            audit_repository=repository,
            session=FakeSession(),
        )


@pytest.mark.asyncio
async def test_database_timestamp_before_prediction_is_rejected():
    source = candidate()

    repository = FakeAuditRepository(
        database_clock=lambda: dt(10),
    )
    session = FakeSession()

    with pytest.raises(
        PersonalResponsePredictionIssuanceError,
        match="predates prediction_at",
    ):
        await issue_personal_response_prediction(
            candidate=source,
            audit_repository=repository,
            session=session,
        )

    assert session.commit_count == 0
    assert session.rollback_count == 1


@pytest.mark.asyncio
async def test_preexisting_mismatched_record_fails_closed():
    source = candidate()

    issuance = (
        build_personal_response_prediction_issuance_contract(
            source
        )
    )

    repository = FakeAuditRepository()

    key = (
        AuditArtifactKind
        .PERSONAL_RESPONSE_PREDICTION_ISSUANCE,
        issuance.issuance_id,
    )

    repository.records[key] = AuditArtifactRecord(
        artifact_kind=key[0],
        artifact_id=key[1],
        athlete_id=ATHLETE,
        schema_version=issuance.schema_version,
        created_at=dt(12),
        content_hash_algorithm=(
            issuance.content_hash_algorithm
        ),
        content_hash="f" * 64,
        contract_json="{}",
        persisted_at=dt(12),
    )

    session = FakeSession()

    with pytest.raises(
        PersonalResponsePredictionIssuanceError,
        match="does not match",
    ):
        await issue_personal_response_prediction(
            candidate=source,
            audit_repository=repository,
            session=session,
        )

    assert session.rollback_count == 1


@pytest.mark.asyncio
async def test_missing_read_after_write_fails_closed():
    source = candidate()

    repository = FakeAuditRepository()
    repository.drop_after_save = True

    session = FakeSession()

    with pytest.raises(
        PersonalResponsePredictionIssuanceError,
        match="did not round-trip",
    ):
        await issue_personal_response_prediction(
            candidate=source,
            audit_repository=repository,
            session=session,
        )

    assert session.commit_count == 0
    assert session.rollback_count == 1
