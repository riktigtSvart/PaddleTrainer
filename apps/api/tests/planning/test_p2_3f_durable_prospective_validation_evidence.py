from dataclasses import replace
from datetime import datetime, timezone

import pytest

import app.planning.application.persist_prospective_validation_evidence as persistence

from app.planning.domain.common.serialization import (
    CONTENT_HASH_ALGORITHM,
    canonical_json,
    compute_content_hash,
)
from app.planning.domain.persistence.audit import (
    AuditArtifactConflictError,
    AuditArtifactKind,
    AuditArtifactSaveResult,
    AuditArtifactSaveStatus,
)
from app.planning.domain.response_evidence import (
    TrainingResponseTiming,
)
from app.planning.domain.training_dynamics import (
    EffectEvidenceLevel,
    PersonalAssociationPredictorKey,
    ResponseMetricReferenceKey,
)
from app.planning.domain.training_dynamics.prospective_cohort import (
    ProspectiveValidationFamilyKey,
)
from app.planning.domain.training_dynamics.prospective_validation import (
    ProspectiveValidationAssessmentStatus,
)
from app.planning.domain.training_dynamics.prospective_validation_evidence import (
    PROSPECTIVE_VALIDATION_EVIDENCE_HASH_EXCLUDE_FIELDS,
    PROSPECTIVE_VALIDATION_EVIDENCE_RULES_V01,
    PROSPECTIVE_VALIDATION_EVIDENCE_SCHEMA_V01,
    ProspectiveValidationEvidence,
    ProspectiveValidationEvidenceStatus,
)


UTC = timezone.utc

ATHLETE = "11111111-1111-4111-8111-111111111111"


def dt(
    hour: int,
) -> datetime:
    return datetime(
        2026,
        10,
        21,
        hour,
        tzinfo=UTC,
    )


FAMILY = ProspectiveValidationFamilyKey(
    model_id="personal-monotonic-median-direction",
    model_version="0.1.0",
    predictor_key=PersonalAssociationPredictorKey(
        metric_key="training_load_index",
        unit="au",
    ),
    response_key=ResponseMetricReferenceKey(
        metric_key="fatigue",
        unit="score_0_10",
        response_timing=TrainingResponseTiming.SAME_DAY,
        stimulus_modality_key="RUNNING",
    ),
)


def evidence(
    *,
    created_at=None,
    validated=True,
):
    if validated:
        status = (
            ProspectiveValidationEvidenceStatus
            .PROSPECTIVELY_VALIDATED
        )
        level = (
            EffectEvidenceLevel
            .PROSPECTIVELY_VALIDATED
        )
        assessment_status = (
            ProspectiveValidationAssessmentStatus
            .VALIDATION_CRITERIA_MET
        )
        criteria_met = True
        validation_established = True
    else:
        status = (
            ProspectiveValidationEvidenceStatus
            .UNESTABLISHED
        )
        level = (
            EffectEvidenceLevel
            .ASSOCIATION_SUPPORTED
        )
        assessment_status = (
            ProspectiveValidationAssessmentStatus
            .VALIDATION_UNESTABLISHED
        )
        criteria_met = False
        validation_established = False

    provisional = ProspectiveValidationEvidence(
        evidence_id="PENDING",
        schema_version=(
            PROSPECTIVE_VALIDATION_EVIDENCE_SCHEMA_V01
        ),
        rules_version=(
            PROSPECTIVE_VALIDATION_EVIDENCE_RULES_V01
        ),

        athlete_id=ATHLETE,
        family_key=FAMILY,
        as_of=dt(20),

        source_cohort_id="cohort-1",
        source_cohort_content_hash="a" * 64,
        source_cohort_schema_version=(
            "prospective-validation-cohort-v0.1"
        ),
        source_cohort_rules_version=(
            "prospective-validation-cohort-rules-v0.1"
        ),

        source_multiplicity_guard_id="guard-1",
        source_multiplicity_guard_content_hash="b" * 64,
        source_multiplicity_guard_schema_version=(
            "prospective-multiplicity-guard-v0.1"
        ),
        source_multiplicity_guard_rules_version=(
            "prospective-multiplicity-guard-rules-v0.1"
        ),

        source_assessment_id="assessment-1",
        source_assessment_content_hash="c" * 64,
        source_assessment_schema_version=(
            "prospective-validation-assessment-v0.1"
        ),
        source_assessment_rules_version=(
            "prospective-validation-assessment-rules-v0.1"
        ),

        issued_challenge_count=5,
        directionally_scored_count=5,
        matched_count=5 if validated else 4,
        mismatched_count=0 if validated else 1,
        tied_unscorable_count=0,

        exact_one_sided_p_numerator=(
            1 if validated else 3
        ),
        exact_one_sided_p_denominator=(
            32 if validated else 16
        ),

        adjusted_alpha_numerator=1,
        adjusted_alpha_denominator=20,

        assessment_status=assessment_status,
        validation_criteria_met=criteria_met,

        status=status,

        evidence_level=level,
        association_supported=True,
        prospective_validation_established=(
            validation_established
        ),

        causal_attribution_established=False,
        effect_inference_authorized=False,
        readiness_inference_authorized=False,
        performance_prediction_authorized=False,
        prescription_change_authorized=False,
        planning_authorized=False,

        created_at=(
            created_at or dt(21)
        ),

        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash="",
    )

    digest = compute_content_hash(
        provisional,
        exclude_fields=(
            PROSPECTIVE_VALIDATION_EVIDENCE_HASH_EXCLUDE_FIELDS
        ),
    )

    return replace(
        provisional,
        evidence_id=(
            "pt-prospective-validation-evidence:"
            + digest
        ),
        content_hash=digest,
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
            or (lambda: dt(22))
        )
        self.drop_after_save = False
        self.fail_save = False

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

    async def save(
        self,
        record,
    ):
        if record.persisted_at is not None:
            raise ValueError(
                "persisted_at must be database-assigned."
            )

        if self.fail_save:
            raise RuntimeError(
                "synthetic durable-evidence save failure"
            )

        key = (
            record.artifact_kind,
            record.artifact_id,
        )

        existing = self.records.get(
            key
        )

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
                    "immutable conflict"
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

        self.records[
            key
        ] = stored

        if self.drop_after_save:
            self.records.pop(
                key
            )

        return AuditArtifactSaveResult(
            status=(
                AuditArtifactSaveStatus.CREATED
            ),
            artifact_kind=record.artifact_kind,
            artifact_id=record.artifact_id,
            content_hash=record.content_hash,
        )


def install_assembler(
    monkeypatch,
    source,
):
    async def fake_assemble(
        *,
        athlete_id,
        family_key,
        as_of,
        created_at,
        audit_repository,
    ):
        assert athlete_id == ATHLETE
        assert family_key == FAMILY
        assert as_of == dt(20)

        # Rematerialization time may differ while semantic hash
        # remains identical.
        return replace(
            source,
            created_at=created_at,
        )

    monkeypatch.setattr(
        persistence,
        "assemble_prospective_validation_evidence",
        fake_assemble,
    )


@pytest.mark.asyncio
async def test_first_persistence_establishes_database_availability(
    monkeypatch,
):
    source = evidence()

    install_assembler(
        monkeypatch,
        source,
    )

    repository = FakeAuditRepository(
        database_clock=lambda: dt(22),
    )
    session = FakeSession()

    result = await (
        persistence
        .persist_prospective_validation_evidence(
            athlete_id=ATHLETE,
            family_key=FAMILY,
            as_of=dt(20),
            created_at=dt(21),
            audit_repository=repository,
            session=session,
        )
    )

    assert result.evidence == source
    assert result.durable_available_at == dt(22)

    assert result.reused_durable_evidence is False

    assert (
        result.prospective_validation_established
        is True
    )

    assert (
        result.prescription_change_authorized
        is False
    )
    assert result.planning_authorized is False

    assert session.commit_count == 1
    assert session.rollback_count == 0


@pytest.mark.asyncio
async def test_retry_reuses_original_durable_artifact_and_timestamp(
    monkeypatch,
):
    source = evidence()

    install_assembler(
        monkeypatch,
        source,
    )

    repository = FakeAuditRepository(
        database_clock=lambda: dt(22),
    )

    first = await (
        persistence
        .persist_prospective_validation_evidence(
            athlete_id=ATHLETE,
            family_key=FAMILY,
            as_of=dt(20),
            created_at=dt(21),
            audit_repository=repository,
            session=FakeSession(),
        )
    )

    second = await (
        persistence
        .persist_prospective_validation_evidence(
            athlete_id=ATHLETE,
            family_key=FAMILY,
            as_of=dt(20),
            created_at=dt(23),
            audit_repository=repository,
            session=FakeSession(),
        )
    )

    assert first.evidence.evidence_id == second.evidence.evidence_id
    assert first.evidence.content_hash == second.evidence.content_hash

    # Durable immutable artifact retains original materialization.
    assert second.evidence.created_at == dt(21)
    assert second.durable_available_at == dt(22)

    assert second.reused_durable_evidence is True

    assert len(repository.records) == 1


@pytest.mark.asyncio
async def test_unestablished_d_evidence_cannot_cross_durable_bridge(
    monkeypatch,
):
    source = evidence(
        validated=False,
    )

    install_assembler(
        monkeypatch,
        source,
    )

    session = FakeSession()

    with pytest.raises(
        persistence
        .DurableProspectiveValidationEvidenceError,
        match="Only successfully",
    ):
        await (
            persistence
            .persist_prospective_validation_evidence(
                athlete_id=ATHLETE,
                family_key=FAMILY,
                as_of=dt(20),
                created_at=dt(21),
                audit_repository=FakeAuditRepository(),
                session=session,
            )
        )

    # Validation fails before entering persistence transaction.
    assert session.commit_count == 0
    assert session.rollback_count == 0


@pytest.mark.asyncio
async def test_database_time_cannot_predate_evidence_materialization(
    monkeypatch,
):
    source = evidence()

    install_assembler(
        monkeypatch,
        source,
    )

    repository = FakeAuditRepository(
        database_clock=lambda: dt(19),
    )

    session = FakeSession()

    with pytest.raises(
        persistence
        .DurableProspectiveValidationEvidenceError,
        match="predates its materialization",
    ):
        await (
            persistence
            .persist_prospective_validation_evidence(
                athlete_id=ATHLETE,
                family_key=FAMILY,
                as_of=dt(20),
                created_at=dt(21),
                audit_repository=repository,
                session=session,
            )
        )

    assert session.commit_count == 0
    assert session.rollback_count == 1


@pytest.mark.asyncio
async def test_missing_round_trip_fails_closed(
    monkeypatch,
):
    source = evidence()

    install_assembler(
        monkeypatch,
        source,
    )

    repository = FakeAuditRepository()
    repository.drop_after_save = True

    session = FakeSession()

    with pytest.raises(
        persistence
        .DurableProspectiveValidationEvidenceError,
        match="did not round-trip",
    ):
        await (
            persistence
            .persist_prospective_validation_evidence(
                athlete_id=ATHLETE,
                family_key=FAMILY,
                as_of=dt(20),
                created_at=dt(21),
                audit_repository=repository,
                session=session,
            )
        )

    assert session.commit_count == 0
    assert session.rollback_count == 1


@pytest.mark.asyncio
async def test_save_failure_rolls_back(
    monkeypatch,
):
    source = evidence()

    install_assembler(
        monkeypatch,
        source,
    )

    repository = FakeAuditRepository()
    repository.fail_save = True

    session = FakeSession()

    with pytest.raises(
        RuntimeError,
        match="synthetic durable-evidence save failure",
    ):
        await (
            persistence
            .persist_prospective_validation_evidence(
                athlete_id=ATHLETE,
                family_key=FAMILY,
                as_of=dt(20),
                created_at=dt(21),
                audit_repository=repository,
                session=session,
            )
        )

    assert session.commit_count == 0
    assert session.rollback_count == 1


@pytest.mark.asyncio
async def test_tampered_stored_contract_is_rejected_on_retry(
    monkeypatch,
):
    source = evidence()

    install_assembler(
        monkeypatch,
        source,
    )

    repository = FakeAuditRepository()

    await (
        persistence
        .persist_prospective_validation_evidence(
            athlete_id=ATHLETE,
            family_key=FAMILY,
            as_of=dt(20),
            created_at=dt(21),
            audit_repository=repository,
            session=FakeSession(),
        )
    )

    key = (
        AuditArtifactKind
        .PROSPECTIVE_VALIDATION_EVIDENCE,
        source.evidence_id,
    )

    stored = repository.records[
        key
    ]

    raw = stored.contract_json.replace(
        '"planning_authorized":false',
        '"planning_authorized":true',
    )

    assert raw != stored.contract_json

    repository.records[
        key
    ] = replace(
        stored,
        contract_json=raw,
    )

    session = FakeSession()

    with pytest.raises(
        (
            ValueError,
            persistence
            .DurableProspectiveValidationEvidenceError,
        )
    ):
        await (
            persistence
            .persist_prospective_validation_evidence(
                athlete_id=ATHLETE,
                family_key=FAMILY,
                as_of=dt(20),
                created_at=dt(23),
                audit_repository=repository,
                session=session,
            )
        )

    assert session.commit_count == 0
    assert session.rollback_count == 1
