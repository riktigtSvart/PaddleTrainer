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
from ..domain.training_dynamics.prospective_challenge_slot import (
    PersonalResponsePredictionChallengeSlot,
    build_personal_response_prediction_challenge_slot,
    personal_response_prediction_challenge_slot_id,
)
from ..domain.training_dynamics.prospective_issuance import (
    PersonalResponsePredictionIssuanceContract,
    build_personal_response_prediction_issuance_contract,
)
from ..domain.training_dynamics.prospective_prediction import (
    PersonalResponsePredictionCandidate,
)
from ..ports.audit import AsyncPlanningAuditRepository


LEGACY_ISSUANCE_SCAN_LIMIT = 500


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


def _slot_audit_record(
    *,
    slot: PersonalResponsePredictionChallengeSlot,
    issuance: PersonalResponsePredictionIssuanceContract,
) -> AuditArtifactRecord:
    return AuditArtifactRecord(
        artifact_kind=(
            AuditArtifactKind
            .PERSONAL_RESPONSE_PREDICTION_CHALLENGE_SLOT
        ),
        artifact_id=slot.slot_id,
        athlete_id=slot.athlete_id,
        schema_version=slot.schema_version,

        # Stable semantic slot has no independent model timestamp.
        # Reuse the prediction timestamp as audit metadata only.
        created_at=issuance.prediction_at,

        content_hash_algorithm=(
            slot.content_hash_algorithm
        ),
        content_hash=slot.content_hash,
        contract_json=canonical_json(
            slot
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


def _validate_slot_record(
    *,
    record: AuditArtifactRecord,
    slot: PersonalResponsePredictionChallengeSlot,
    issuance: PersonalResponsePredictionIssuanceContract,
) -> datetime:
    if (
        record.artifact_kind
        != AuditArtifactKind
        .PERSONAL_RESPONSE_PREDICTION_CHALLENGE_SLOT
    ):
        raise PersonalResponsePredictionIssuanceError(
            "Prediction challenge-slot kind mismatch."
        )

    if (
        record.artifact_id != slot.slot_id
        or record.athlete_id != slot.athlete_id
        or record.schema_version != slot.schema_version
        or record.content_hash_algorithm
        != slot.content_hash_algorithm
        or record.content_hash != slot.content_hash
        or record.contract_json
        != canonical_json(slot)
        or record.created_at
        != issuance.prediction_at
    ):
        raise PersonalResponsePredictionIssuanceError(
            "Prediction challenge slot is already reserved "
            "for a different issuance."
        )

    if record.persisted_at is None:
        raise PersonalResponsePredictionIssuanceError(
            "Prediction challenge-slot reservation has no "
            "database persistence timestamp."
        )

    persisted = to_utc(
        record.persisted_at,
        field_name="slot_record.persisted_at",
    )

    if persisted < issuance.prediction_at:
        raise PersonalResponsePredictionIssuanceError(
            "Prediction challenge-slot reservation predates "
            "prediction_at."
        )

    if persisted < issuance.information_cutoff_at:
        raise PersonalResponsePredictionIssuanceError(
            "Prediction challenge-slot reservation predates "
            "the information cutoff."
        )

    return persisted


def _validate_save_result(
    *,
    save_result,
    expected_kind: AuditArtifactKind,
    expected_id: str,
    expected_hash: str,
    label: str,
) -> None:
    if (
        save_result.artifact_kind
        != expected_kind
        or save_result.artifact_id
        != expected_id
        or save_result.content_hash
        != expected_hash
    ):
        raise PersonalResponsePredictionIssuanceError(
            f"{label} save result identity mismatch."
        )


async def _find_legacy_slot_issuances(
    *,
    audit_repository: AsyncPlanningAuditRepository,
    issuance: PersonalResponsePredictionIssuanceContract,
    slot: PersonalResponsePredictionChallengeSlot,
) -> tuple[
    tuple[
        AuditArtifactRecord,
        PersonalResponsePredictionIssuanceContract,
    ],
    ...,
]:
    """Find pre-P2.3E issuances occupying this slot.

    A bounded scan can prove absence only when fewer than the repository
    maximum are returned. Exactly 500 therefore fails closed.
    """

    records = await audit_repository.list_for_athlete(
        athlete_id=issuance.athlete_id,
        artifact_kind=(
            AuditArtifactKind
            .PERSONAL_RESPONSE_PREDICTION_ISSUANCE
        ),
        limit=LEGACY_ISSUANCE_SCAN_LIMIT,
    )

    if len(records) >= LEGACY_ISSUANCE_SCAN_LIMIT:
        raise PersonalResponsePredictionIssuanceError(
            "Legacy prediction issuance scan completeness "
            "is unknown at the repository limit."
        )

    # Kept local to avoid changing the published A2 v0.1 contract.
    from .bind_personal_response_prediction_outcome import (
        restore_personal_response_prediction_issuance_audit_artifact,
    )

    matches = []

    for record in records:
        restored = (
            restore_personal_response_prediction_issuance_audit_artifact(
                record
            )
        )

        restored_slot_id = (
            personal_response_prediction_challenge_slot_id(
                restored
            )
        )

        if restored_slot_id == slot.slot_id:
            matches.append(
                (
                    record,
                    restored,
                )
            )

    return tuple(matches)


async def issue_personal_response_prediction(
    *,
    candidate: PersonalResponsePredictionCandidate,
    audit_repository: AsyncPlanningAuditRepository,
    session,
) -> DurablePersonalResponsePredictionIssuance:
    """Freeze one P2.3A1 prediction exactly once per challenge slot.

    P2.3E adds a stable immutable reservation keyed only by:
    athlete + session + model + predictor + response context.

    The A2 issuance contract remains v0.1 and replay-compatible.

    Existing pre-P2.3E issuances are scanned and lazily reserved when
    unambiguous. Different or multiple legacy issuances occupying the
    same slot fail closed.

    Reservation and issuance persistence share the caller-owned database
    transaction; any exception rolls both back.
    """

    issuance = (
        build_personal_response_prediction_issuance_contract(
            candidate
        )
    )

    slot = (
        build_personal_response_prediction_challenge_slot(
            issuance
        )
    )

    try:
        existing_slot = await audit_repository.get(
            artifact_kind=(
                AuditArtifactKind
                .PERSONAL_RESPONSE_PREDICTION_CHALLENGE_SLOT
            ),
            artifact_id=slot.slot_id,
        )

        existing_issuance = await audit_repository.get(
            artifact_kind=(
                AuditArtifactKind
                .PERSONAL_RESPONSE_PREDICTION_ISSUANCE
            ),
            artifact_id=issuance.issuance_id,
        )

        # Once a P2.3E slot reservation exists, it is authoritative.
        if existing_slot is not None:
            _validate_slot_record(
                record=existing_slot,
                slot=slot,
                issuance=issuance,
            )

            if existing_issuance is None:
                raise PersonalResponsePredictionIssuanceError(
                    "Prediction challenge slot is reserved but "
                    "its bound issuance is missing."
                )

            durable_time = _validate_durable_record(
                record=existing_issuance,
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

        # Preserve A2's exact-record corruption behavior before scanning
        # other legacy issuances.
        exact_durable_time = None

        if existing_issuance is not None:
            exact_durable_time = _validate_durable_record(
                record=existing_issuance,
                issuance=issuance,
                candidate=candidate,
            )

        legacy_matches = await _find_legacy_slot_issuances(
            audit_repository=audit_repository,
            issuance=issuance,
            slot=slot,
        )

        if len(legacy_matches) > 1:
            raise PersonalResponsePredictionIssuanceError(
                "Multiple legacy prediction issuances occupy "
                "the same challenge slot."
            )

        if len(legacy_matches) == 1:
            legacy_record, legacy_issuance = (
                legacy_matches[0]
            )

            if (
                legacy_issuance.issuance_id
                != issuance.issuance_id
                or legacy_issuance.content_hash
                != issuance.content_hash
            ):
                raise PersonalResponsePredictionIssuanceError(
                    "Legacy prediction issuance already occupies "
                    "this challenge slot with different content."
                )

            durable_time = _validate_durable_record(
                record=legacy_record,
                issuance=issuance,
                candidate=candidate,
            )

            if (
                exact_durable_time is not None
                and exact_durable_time != durable_time
            ):
                raise PersonalResponsePredictionIssuanceError(
                    "Exact and legacy issuance persistence "
                    "boundaries disagree."
                )

            slot_save = await audit_repository.save(
                _slot_audit_record(
                    slot=slot,
                    issuance=issuance,
                )
            )

            _validate_save_result(
                save_result=slot_save,
                expected_kind=(
                    AuditArtifactKind
                    .PERSONAL_RESPONSE_PREDICTION_CHALLENGE_SLOT
                ),
                expected_id=slot.slot_id,
                expected_hash=slot.content_hash,
                label="Prediction challenge-slot reservation",
            )

            stored_slot = await audit_repository.get(
                artifact_kind=(
                    AuditArtifactKind
                    .PERSONAL_RESPONSE_PREDICTION_CHALLENGE_SLOT
                ),
                artifact_id=slot.slot_id,
            )

            if stored_slot is None:
                raise PersonalResponsePredictionIssuanceError(
                    "Prediction challenge-slot reservation "
                    "did not round-trip after persistence."
                )

            _validate_slot_record(
                record=stored_slot,
                slot=slot,
                issuance=issuance,
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

        if existing_issuance is not None:
            raise PersonalResponsePredictionIssuanceError(
                "Exact prediction issuance was not found in "
                "the complete legacy issuance scan."
            )

        # New P2.3E path: reserve the stable slot first, then persist the
        # issuance. Both writes remain in the same transaction.
        slot_save = await audit_repository.save(
            _slot_audit_record(
                slot=slot,
                issuance=issuance,
            )
        )

        _validate_save_result(
            save_result=slot_save,
            expected_kind=(
                AuditArtifactKind
                .PERSONAL_RESPONSE_PREDICTION_CHALLENGE_SLOT
            ),
            expected_id=slot.slot_id,
            expected_hash=slot.content_hash,
            label="Prediction challenge-slot reservation",
        )

        issuance_save = await audit_repository.save(
            _audit_record(
                issuance
            )
        )

        _validate_save_result(
            save_result=issuance_save,
            expected_kind=(
                AuditArtifactKind
                .PERSONAL_RESPONSE_PREDICTION_ISSUANCE
            ),
            expected_id=issuance.issuance_id,
            expected_hash=issuance.content_hash,
            label="Prediction issuance",
        )

        stored_slot = await audit_repository.get(
            artifact_kind=(
                AuditArtifactKind
                .PERSONAL_RESPONSE_PREDICTION_CHALLENGE_SLOT
            ),
            artifact_id=slot.slot_id,
        )

        if stored_slot is None:
            raise PersonalResponsePredictionIssuanceError(
                "Prediction challenge-slot reservation "
                "did not round-trip after persistence."
            )

        _validate_slot_record(
            record=stored_slot,
            slot=slot,
            issuance=issuance,
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
                issuance_save.status
                == AuditArtifactSaveStatus.ALREADY_PRESENT
            ),
            issuance_proof_established=True,
            prospective_validation_established=False,
            planning_authorized=False,
        )

    except Exception:
        await session.rollback()
        raise
