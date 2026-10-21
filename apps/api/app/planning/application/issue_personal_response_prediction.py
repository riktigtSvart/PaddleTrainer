from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..domain.common.serialization import (
    canonical_json,
)
from ..domain.common.time import to_utc
from ..domain.persistence.audit import (
    AuditArtifactKind,
    AuditArtifactRecord,
    AuditArtifactSaveStatus,
)
from ..domain.training_dynamics.prospective_issuance import (
    PersonalResponsePredictionIssuanceContract,
    build_personal_response_prediction_issuance_contract,
)
from ..domain.training_dynamics.prospective_prediction import (
    PersonalResponsePredictionCandidate,
)
from ..ports.audit import AsyncPlanningAuditRepository


class PersonalResponsePredictionIssuanceError(
    RuntimeError
):
    pass


@dataclass(frozen=True)
class DurablePersonalResponsePredictionIssuance:
    issuance: PersonalResponsePredictionIssuanceContract

    durable_issued_at: datetime

    reused_durable_issuance: bool

    issuance_proof_established: bool

    prospective_validation_established: bool
    planning_authorized: bool


def _audit_record(
    issuance: PersonalResponsePredictionIssuanceContract,
) -> AuditArtifactRecord:
    return AuditArtifactRecord(
        artifact_kind=(
            AuditArtifactKind
            .PERSONAL_RESPONSE_PREDICTION_ISSUANCE
        ),
        artifact_id=issuance.issuance_id,
        athlete_id=issuance.athlete_id,
        schema_version=issuance.schema_version,
        # Domain/model metadata only. This field does not
        # establish the durable issuance time.
        created_at=issuance.prediction_at,
        content_hash_algorithm=(
            issuance.content_hash_algorithm
        ),
        content_hash=issuance.content_hash,
        contract_json=canonical_json(
            issuance
        ),
    )


def _validate_durable_record(
    *,
    record: AuditArtifactRecord,
    issuance: PersonalResponsePredictionIssuanceContract,
    candidate: PersonalResponsePredictionCandidate,
) -> datetime:
    if (
        record.artifact_kind
        != AuditArtifactKind
        .PERSONAL_RESPONSE_PREDICTION_ISSUANCE
    ):
        raise PersonalResponsePredictionIssuanceError(
            "Durable prediction issuance kind mismatch."
        )

    if (
        record.artifact_id != issuance.issuance_id
        or record.athlete_id != issuance.athlete_id
        or record.schema_version != issuance.schema_version
        or record.content_hash_algorithm
        != issuance.content_hash_algorithm
        or record.content_hash != issuance.content_hash
        or record.contract_json
        != canonical_json(issuance)
    ):
        raise PersonalResponsePredictionIssuanceError(
            "Durable prediction issuance does not match "
            "the deterministic issuance contract."
        )

    if record.persisted_at is None:
        raise PersonalResponsePredictionIssuanceError(
            "Durable prediction issuance has no "
            "database persistence timestamp."
        )

    durable_time = to_utc(
        record.persisted_at,
        field_name="record.persisted_at",
    )

    # This is the actual prospective boundary asserted by A2.
    # Candidate.created_at is intentionally NOT used here because
    # A1 semantic identity excludes rematerialization time.
    if durable_time < candidate.prediction_at:
        raise PersonalResponsePredictionIssuanceError(
            "Durable prediction issuance predates prediction_at."
        )

    if durable_time < candidate.information_cutoff_at:
        raise PersonalResponsePredictionIssuanceError(
            "Durable prediction issuance predates "
            "the information cutoff."
        )

    return durable_time


async def issue_personal_response_prediction(
    *,
    candidate: PersonalResponsePredictionCandidate,
    audit_repository: AsyncPlanningAuditRepository,
    session,
) -> DurablePersonalResponsePredictionIssuance:
    """Freeze one P2.3A1 prediction exactly once.

    The first committed immutable audit row wins.

    `candidate.prediction_at` remains a model timestamp only.
    `durable_issued_at` comes from the first persisted audit row and
    becomes the prospective issuance boundary used by P2.3B.

    The authoritative issuance time is assigned inside the database
    persistence statement. Python callers cannot supply it.
    """

    issuance = (
        build_personal_response_prediction_issuance_contract(
            candidate
        )
    )

    try:
        existing = await audit_repository.get(
            artifact_kind=(
                AuditArtifactKind
                .PERSONAL_RESPONSE_PREDICTION_ISSUANCE
            ),
            artifact_id=issuance.issuance_id,
        )

        if existing is not None:
            durable_time = _validate_durable_record(
                record=existing,
                issuance=issuance,
                candidate=candidate,
            )

            await session.commit()

            return DurablePersonalResponsePredictionIssuance(
                issuance=issuance,
                durable_issued_at=durable_time,
                reused_durable_issuance=True,
                issuance_proof_established=True,
                prospective_validation_established=False,
                planning_authorized=False,
            )

        save_result = await audit_repository.save(
            _audit_record(
                issuance,
            )
        )

        if (
            save_result.artifact_kind
            != AuditArtifactKind
            .PERSONAL_RESPONSE_PREDICTION_ISSUANCE
            or save_result.artifact_id
            != issuance.issuance_id
            or save_result.content_hash
            != issuance.content_hash
        ):
            raise PersonalResponsePredictionIssuanceError(
                "Prediction issuance save result identity mismatch."
            )

        stored = await audit_repository.get(
            artifact_kind=(
                AuditArtifactKind
                .PERSONAL_RESPONSE_PREDICTION_ISSUANCE
            ),
            artifact_id=issuance.issuance_id,
        )

        if stored is None:
            raise PersonalResponsePredictionIssuanceError(
                "Prediction issuance did not round-trip "
                "after persistence."
            )

        durable_time = _validate_durable_record(
            record=stored,
            issuance=issuance,
            candidate=candidate,
        )

        await session.commit()

        return DurablePersonalResponsePredictionIssuance(
            issuance=issuance,
            durable_issued_at=durable_time,
            reused_durable_issuance=(
                save_result.status
                == AuditArtifactSaveStatus.ALREADY_PRESENT
            ),
            issuance_proof_established=True,
            prospective_validation_established=False,
            planning_authorized=False,
        )

    except Exception:
        await session.rollback()
        raise
