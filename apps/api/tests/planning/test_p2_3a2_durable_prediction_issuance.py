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
from app.planning.domain.training_dynamics.prospective_challenge_slot import (
    build_personal_response_prediction_challenge_slot,
    personal_response_prediction_challenge_slot_id,
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
        self.fail_issuance_save = False
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

        if (
            self.fail_issuance_save
            and record.artifact_kind
            == AuditArtifactKind
            .PERSONAL_RESPONSE_PREDICTION_ISSUANCE
        ):
            raise RuntimeError(
                "synthetic issuance save failure"
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
    workout_session_id="future-session",
    response_metric_key="self_reported_fatigue_score",
    target_predictor_value=4.5,
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
        workout_session_id=workout_session_id,

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
            metric_key=response_metric_key,
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

        target_predictor_value=target_predictor_value,

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

    assert len(repository.records) == 2

    assert sum(
        1
        for kind, _ in repository.records
        if (
            kind
            == AuditArtifactKind
            .PERSONAL_RESPONSE_PREDICTION_ISSUANCE
        )
    ) == 1

    assert sum(
        1
        for kind, _ in repository.records
        if (
            kind
            == AuditArtifactKind
            .PERSONAL_RESPONSE_PREDICTION_CHALLENGE_SLOT
        )
    ) == 1


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



def _durable_issuance_record(
    source,
    *,
    persisted_at=None,
):
    issuance = (
        build_personal_response_prediction_issuance_contract(
            source
        )
    )

    return (
        issuance,
        AuditArtifactRecord(
            artifact_kind=(
                AuditArtifactKind
                .PERSONAL_RESPONSE_PREDICTION_ISSUANCE
            ),
            artifact_id=issuance.issuance_id,
            athlete_id=issuance.athlete_id,
            schema_version=issuance.schema_version,
            created_at=issuance.prediction_at,
            content_hash_algorithm=(
                issuance.content_hash_algorithm
            ),
            content_hash=issuance.content_hash,
            contract_json=canonical_json(
                issuance
            ),
            persisted_at=(
                persisted_at or dt(12)
            ),
        ),
    )


def _slot_record(
    issuance,
    *,
    persisted_at=None,
):
    slot = (
        build_personal_response_prediction_challenge_slot(
            issuance
        )
    )

    return (
        slot,
        AuditArtifactRecord(
            artifact_kind=(
                AuditArtifactKind
                .PERSONAL_RESPONSE_PREDICTION_CHALLENGE_SLOT
            ),
            artifact_id=slot.slot_id,
            athlete_id=slot.athlete_id,
            schema_version=slot.schema_version,
            created_at=issuance.prediction_at,
            content_hash_algorithm=(
                slot.content_hash_algorithm
            ),
            content_hash=slot.content_hash,
            contract_json=canonical_json(
                slot
            ),
            persisted_at=(
                persisted_at or dt(12)
            ),
        ),
    )


def test_p2_3e_candidate_specific_changes_share_same_slot_identity():
    first = (
        build_personal_response_prediction_issuance_contract(
            candidate(
                target_predictor_value=4.5,
            )
        )
    )

    second = (
        build_personal_response_prediction_issuance_contract(
            candidate(
                target_predictor_value=4.0,
            )
        )
    )

    assert first.issuance_id != second.issuance_id

    first_slot = (
        build_personal_response_prediction_challenge_slot(
            first
        )
    )

    second_slot = (
        build_personal_response_prediction_challenge_slot(
            second
        )
    )

    assert first_slot.slot_id == second_slot.slot_id

    # Same stable identity, different binding content:
    # immutable persistence therefore conflicts rather than
    # creating a second issuance for the same challenge.
    assert (
        first_slot.content_hash
        != second_slot.content_hash
    )


def test_p2_3e_different_response_context_gets_different_slot():
    first = (
        build_personal_response_prediction_issuance_contract(
            candidate()
        )
    )

    second = (
        build_personal_response_prediction_issuance_contract(
            candidate(
                response_metric_key="recovery_score",
            )
        )
    )

    assert (
        personal_response_prediction_challenge_slot_id(
            first
        )
        != personal_response_prediction_challenge_slot_id(
            second
        )
    )


@pytest.mark.asyncio
async def test_p2_3e_first_issue_persists_slot_and_issuance_together():
    source = candidate()

    repository = FakeAuditRepository()
    session = FakeSession()

    result = await issue_personal_response_prediction(
        candidate=source,
        audit_repository=repository,
        session=session,
    )

    slot = (
        build_personal_response_prediction_challenge_slot(
            result.issuance
        )
    )

    assert (
        (
            AuditArtifactKind
            .PERSONAL_RESPONSE_PREDICTION_CHALLENGE_SLOT,
            slot.slot_id,
        )
        in repository.records
    )

    assert (
        (
            AuditArtifactKind
            .PERSONAL_RESPONSE_PREDICTION_ISSUANCE,
            result.issuance.issuance_id,
        )
        in repository.records
    )

    assert session.commit_count == 1
    assert session.rollback_count == 0


@pytest.mark.asyncio
async def test_p2_3e_same_slot_different_issuance_fails_closed():
    first = candidate(
        target_predictor_value=4.5,
    )

    second = candidate(
        target_predictor_value=4.0,
    )

    repository = FakeAuditRepository()

    await issue_personal_response_prediction(
        candidate=first,
        audit_repository=repository,
        session=FakeSession(),
    )

    session = FakeSession()

    with pytest.raises(
        PersonalResponsePredictionIssuanceError,
        match="already reserved",
    ):
        await issue_personal_response_prediction(
            candidate=second,
            audit_repository=repository,
            session=session,
        )

    assert session.commit_count == 0
    assert session.rollback_count == 1

    assert sum(
        1
        for kind, _ in repository.records
        if (
            kind
            == AuditArtifactKind
            .PERSONAL_RESPONSE_PREDICTION_ISSUANCE
        )
    ) == 1


@pytest.mark.asyncio
async def test_p2_3e_different_response_context_can_use_separate_slot():
    first = candidate()

    second = candidate(
        response_metric_key="recovery_score",
    )

    repository = FakeAuditRepository()

    await issue_personal_response_prediction(
        candidate=first,
        audit_repository=repository,
        session=FakeSession(),
    )

    await issue_personal_response_prediction(
        candidate=second,
        audit_repository=repository,
        session=FakeSession(),
    )

    assert sum(
        1
        for kind, _ in repository.records
        if (
            kind
            == AuditArtifactKind
            .PERSONAL_RESPONSE_PREDICTION_ISSUANCE
        )
    ) == 2

    assert sum(
        1
        for kind, _ in repository.records
        if (
            kind
            == AuditArtifactKind
            .PERSONAL_RESPONSE_PREDICTION_CHALLENGE_SLOT
        )
    ) == 2


@pytest.mark.asyncio
async def test_p2_3e_legacy_same_issuance_is_lazily_reserved():
    source = candidate()

    issuance, record = _durable_issuance_record(
        source
    )

    repository = FakeAuditRepository()

    repository.records[
        (
            record.artifact_kind,
            record.artifact_id,
        )
    ] = record

    result = await issue_personal_response_prediction(
        candidate=source,
        audit_repository=repository,
        session=FakeSession(),
    )

    assert result.reused_durable_issuance is True
    assert result.durable_issued_at == dt(12)

    slot = (
        build_personal_response_prediction_challenge_slot(
            issuance
        )
    )

    assert (
        (
            AuditArtifactKind
            .PERSONAL_RESPONSE_PREDICTION_CHALLENGE_SLOT,
            slot.slot_id,
        )
        in repository.records
    )


@pytest.mark.asyncio
async def test_p2_3e_legacy_different_issuance_same_slot_blocks_new_issue():
    legacy_source = candidate(
        target_predictor_value=4.0,
    )

    requested = candidate(
        target_predictor_value=4.5,
    )

    legacy, record = _durable_issuance_record(
        legacy_source
    )

    requested_issuance = (
        build_personal_response_prediction_issuance_contract(
            requested
        )
    )

    assert (
        personal_response_prediction_challenge_slot_id(
            legacy
        )
        == personal_response_prediction_challenge_slot_id(
            requested_issuance
        )
    )

    assert (
        legacy.issuance_id
        != requested_issuance.issuance_id
    )

    repository = FakeAuditRepository()

    repository.records[
        (
            record.artifact_kind,
            record.artifact_id,
        )
    ] = record

    session = FakeSession()

    with pytest.raises(
        PersonalResponsePredictionIssuanceError,
        match="already occupies",
    ):
        await issue_personal_response_prediction(
            candidate=requested,
            audit_repository=repository,
            session=session,
        )

    assert session.commit_count == 0
    assert session.rollback_count == 1

    assert not any(
        kind
        == AuditArtifactKind
        .PERSONAL_RESPONSE_PREDICTION_CHALLENGE_SLOT
        for kind, _ in repository.records
    )


@pytest.mark.asyncio
async def test_p2_3e_multiple_legacy_issuances_same_slot_are_ambiguous():
    first_source = candidate(
        target_predictor_value=4.0,
    )

    second_source = candidate(
        target_predictor_value=4.5,
    )

    requested = candidate(
        target_predictor_value=4.2,
    )

    _, first_record = _durable_issuance_record(
        first_source
    )

    _, second_record = _durable_issuance_record(
        second_source
    )

    repository = FakeAuditRepository()

    for record in (
        first_record,
        second_record,
    ):
        repository.records[
            (
                record.artifact_kind,
                record.artifact_id,
            )
        ] = record

    with pytest.raises(
        PersonalResponsePredictionIssuanceError,
        match="Multiple legacy",
    ):
        await issue_personal_response_prediction(
            candidate=requested,
            audit_repository=repository,
            session=FakeSession(),
        )


@pytest.mark.asyncio
async def test_p2_3e_repository_scan_limit_fails_closed():
    repository = FakeAuditRepository()

    for index in range(500):
        record = AuditArtifactRecord(
            artifact_kind=(
                AuditArtifactKind
                .PERSONAL_RESPONSE_PREDICTION_ISSUANCE
            ),
            artifact_id=f"legacy-{index}",
            athlete_id=ATHLETE,
            schema_version="legacy",
            created_at=dt(9),
            content_hash_algorithm=(
                CONTENT_HASH_ALGORITHM
            ),
            content_hash="f" * 64,
            contract_json="{}",
            persisted_at=dt(9),
        )

        repository.records[
            (
                record.artifact_kind,
                record.artifact_id,
            )
        ] = record

    session = FakeSession()

    with pytest.raises(
        PersonalResponsePredictionIssuanceError,
        match="scan completeness is unknown",
    ):
        await issue_personal_response_prediction(
            candidate=candidate(),
            audit_repository=repository,
            session=session,
        )

    assert session.commit_count == 0
    assert session.rollback_count == 1


@pytest.mark.asyncio
async def test_p2_3e_reservation_without_bound_issuance_fails_closed():
    source = candidate()

    issuance = (
        build_personal_response_prediction_issuance_contract(
            source
        )
    )

    slot, slot_record = _slot_record(
        issuance
    )

    repository = FakeAuditRepository()

    repository.records[
        (
            slot_record.artifact_kind,
            slot_record.artifact_id,
        )
    ] = slot_record

    session = FakeSession()

    with pytest.raises(
        PersonalResponsePredictionIssuanceError,
        match="bound issuance is missing",
    ):
        await issue_personal_response_prediction(
            candidate=source,
            audit_repository=repository,
            session=session,
        )

    assert session.commit_count == 0
    assert session.rollback_count == 1
class TransactionalFakeSession(FakeSession):
    def __init__(self, repository):
        super().__init__()
        self.repository = repository
        self.snapshot = dict(
            repository.records
        )

    async def rollback(self):
        await super().rollback()

        self.repository.records = dict(
            self.snapshot
        )


@pytest.mark.asyncio
async def test_p2_3e_issuance_save_failure_rolls_back_slot_reservation():
    repository = FakeAuditRepository()
    repository.fail_issuance_save = True

    session = TransactionalFakeSession(
        repository
    )

    with pytest.raises(
        RuntimeError,
        match="synthetic issuance save failure",
    ):
        await issue_personal_response_prediction(
            candidate=candidate(),
            audit_repository=repository,
            session=session,
        )

    assert session.commit_count == 0
    assert session.rollback_count == 1

    # Reservation was flushed first, but transaction rollback
    # removes it together with the failed issuance attempt.
    assert repository.records == {}
