from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import math
from uuid import UUID

from ..domain.common.serialization import (
    CONTENT_HASH_ALGORITHM,
    canonical_json,
)
from ..domain.common.time import to_utc
from ..domain.persistence.audit import (
    AuditArtifactKind,
    AuditArtifactRecord,
    AuditArtifactSaveStatus,
)
from ..domain.response_evidence import (
    TrainingResponseTiming,
)
from ..domain.training_dynamics.association_dataset import (
    PersonalAssociationPredictorKey,
)
from ..domain.training_dynamics.models import (
    EffectEvidenceLevel,
)
from ..domain.training_dynamics.prospective_issuance import (
    PERSONAL_RESPONSE_PREDICTION_ISSUANCE_RULES_V01,
    PERSONAL_RESPONSE_PREDICTION_ISSUANCE_SCHEMA_V01,
    PersonalResponsePredictionIssuanceContract,
)
from ..domain.training_dynamics.prospective_outcome import (
    PROSPECTIVE_RESPONSE_CHALLENGE_SCHEMA_V01,
    ProspectiveResponseChallenge,
    build_prospective_response_challenge,
)
from ..domain.training_dynamics.prospective_prediction import (
    PersonalResponsePredictionDirection,
)
from ..domain.training_dynamics.response_reference import (
    ResponseMetricReferenceKey,
)
from ..ports.audit import AsyncPlanningAuditRepository
from .ingest_authoritative_executed_training import (
    restore_authoritative_executed_training_audit_artifact,
)
from .ingest_authoritative_training_response import (
    restore_authoritative_training_response_audit_artifact,
)


@dataclass(frozen=True)
class DurableProspectiveResponseBindingResult:
    challenge: ProspectiveResponseChallenge

    binding_persisted_at: datetime

    reused_durable_binding: bool

    prospective_challenge_established: bool
    prospective_validation_established: bool
    planning_authorized: bool


class ProspectiveResponseBindingNotFound(LookupError):
    pass


class ProspectiveResponseBindingError(RuntimeError):
    pass


class ProspectiveResponseBindingConflictError(
    ProspectiveResponseBindingError
):
    pass


def _require_string(
    value: object,
    *,
    field_name: str,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"{field_name} must be a non-empty string."
        )

    return value


def _optional_string(
    value: object,
    *,
    field_name: str,
) -> str | None:
    if value is None:
        return None

    return _require_string(
        value,
        field_name=field_name,
    )


def _require_bool(
    value: object,
    *,
    field_name: str,
) -> bool:
    if not isinstance(value, bool):
        raise ValueError(
            f"{field_name} must be boolean."
        )

    return value


def _require_datetime(
    value: object,
    *,
    field_name: str,
) -> datetime:
    if not isinstance(value, str):
        raise ValueError(
            f"{field_name} must be an ISO datetime string."
        )

    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(
            f"{field_name} must be an ISO datetime string."
        ) from exc

    return to_utc(
        parsed,
        field_name=field_name,
    )


def _require_sha256(
    value: object,
    *,
    field_name: str,
) -> str:
    digest = _require_string(
        value,
        field_name=field_name,
    )

    if (
        len(digest) != 64
        or any(
            char not in "0123456789abcdef"
            for char in digest
        )
    ):
        raise ValueError(
            f"{field_name} must be a lowercase SHA-256 digest."
        )

    return digest


def _require_number(
    value: object,
    *,
    field_name: str,
) -> int | float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise ValueError(
            f"{field_name} must be a finite numeric value."
        )

    # Preserve JSON int-vs-float representation for canonical replay.
    return value


def _require_mapping(
    value: object,
    *,
    field_name: str,
) -> dict:
    if not isinstance(value, dict):
        raise ValueError(
            f"{field_name} must be an object."
        )

    return value


def _uuid_text(
    value: str,
    *,
    field_name: str,
) -> str:
    try:
        parsed = UUID(value)
    except (
        TypeError,
        ValueError,
        AttributeError,
    ) as exc:
        raise ValueError(
            f"{field_name} must be a UUID string."
        ) from exc

    canonical = str(parsed)

    if canonical != value:
        raise ValueError(
            f"{field_name} must be a canonical UUID string."
        )

    return canonical


def restore_personal_response_prediction_issuance_audit_artifact(
    record: AuditArtifactRecord,
) -> PersonalResponsePredictionIssuanceContract:
    """Restore and fully verify one durable P2.3A2 issuance."""

    if (
        record.artifact_kind
        != AuditArtifactKind
        .PERSONAL_RESPONSE_PREDICTION_ISSUANCE
    ):
        raise ValueError(
            "Unexpected prediction issuance audit artifact kind."
        )

    try:
        raw = json.loads(
            record.contract_json
        )
    except json.JSONDecodeError as exc:
        raise ValueError(
            "Prediction issuance audit contract is not valid JSON."
        ) from exc

    raw = _require_mapping(
        raw,
        field_name="issuance",
    )

    raw_predictor = _require_mapping(
        raw.get("predictor_key"),
        field_name="predictor_key",
    )

    raw_response = _require_mapping(
        raw.get("response_key"),
        field_name="response_key",
    )

    issuance = PersonalResponsePredictionIssuanceContract(
        issuance_id=_require_string(
            raw.get("issuance_id"),
            field_name="issuance_id",
        ),
        schema_version=_require_string(
            raw.get("schema_version"),
            field_name="schema_version",
        ),
        rules_version=_require_string(
            raw.get("rules_version"),
            field_name="rules_version",
        ),

        athlete_id=_require_string(
            raw.get("athlete_id"),
            field_name="athlete_id",
        ),
        workout_session_id=_require_string(
            raw.get("workout_session_id"),
            field_name="workout_session_id",
        ),

        source_candidate_id=_require_string(
            raw.get("source_candidate_id"),
            field_name="source_candidate_id",
        ),
        source_candidate_content_hash=_require_sha256(
            raw.get("source_candidate_content_hash"),
            field_name="source_candidate_content_hash",
        ),
        source_candidate_schema_version=_require_string(
            raw.get("source_candidate_schema_version"),
            field_name="source_candidate_schema_version",
        ),
        source_candidate_rules_version=_require_string(
            raw.get("source_candidate_rules_version"),
            field_name="source_candidate_rules_version",
        ),

        model_id=_require_string(
            raw.get("model_id"),
            field_name="model_id",
        ),
        model_version=_require_string(
            raw.get("model_version"),
            field_name="model_version",
        ),

        predictor_key=PersonalAssociationPredictorKey(
            metric_key=_require_string(
                raw_predictor.get("metric_key"),
                field_name="predictor_key.metric_key",
            ),
            unit=_optional_string(
                raw_predictor.get("unit"),
                field_name="predictor_key.unit",
            ),
        ),

        response_key=ResponseMetricReferenceKey(
            metric_key=_require_string(
                raw_response.get("metric_key"),
                field_name="response_key.metric_key",
            ),
            unit=_optional_string(
                raw_response.get("unit"),
                field_name="response_key.unit",
            ),
            response_timing=TrainingResponseTiming(
                _require_string(
                    raw_response.get("response_timing"),
                    field_name=(
                        "response_key.response_timing"
                    ),
                )
            ),
            stimulus_modality_key=_require_string(
                raw_response.get(
                    "stimulus_modality_key"
                ),
                field_name=(
                    "response_key.stimulus_modality_key"
                ),
            ),
        ),

        information_cutoff_at=_require_datetime(
            raw.get("information_cutoff_at"),
            field_name="information_cutoff_at",
        ),
        prediction_at=_require_datetime(
            raw.get("prediction_at"),
            field_name="prediction_at",
        ),

        target_predictor_value=_require_number(
            raw.get("target_predictor_value"),
            field_name="target_predictor_value",
        ),
        historical_response_median=_require_number(
            raw.get("historical_response_median"),
            field_name="historical_response_median",
        ),

        predicted_response_direction=(
            PersonalResponsePredictionDirection(
                _require_string(
                    raw.get(
                        "predicted_response_direction"
                    ),
                    field_name=(
                        "predicted_response_direction"
                    ),
                )
            )
        ),

        response_prediction_available=_require_bool(
            raw.get("response_prediction_available"),
            field_name=(
                "response_prediction_available"
            ),
        ),

        evidence_level_ceiling=EffectEvidenceLevel(
            _require_string(
                raw.get("evidence_level_ceiling"),
                field_name="evidence_level_ceiling",
            )
        ),
        association_supported=_require_bool(
            raw.get("association_supported"),
            field_name="association_supported",
        ),

        prospective_validation_established=_require_bool(
            raw.get(
                "prospective_validation_established"
            ),
            field_name=(
                "prospective_validation_established"
            ),
        ),
        causal_attribution_established=_require_bool(
            raw.get(
                "causal_attribution_established"
            ),
            field_name=(
                "causal_attribution_established"
            ),
        ),
        effect_inference_authorized=_require_bool(
            raw.get(
                "effect_inference_authorized"
            ),
            field_name=(
                "effect_inference_authorized"
            ),
        ),
        readiness_inference_authorized=_require_bool(
            raw.get(
                "readiness_inference_authorized"
            ),
            field_name=(
                "readiness_inference_authorized"
            ),
        ),
        performance_prediction_authorized=_require_bool(
            raw.get(
                "performance_prediction_authorized"
            ),
            field_name=(
                "performance_prediction_authorized"
            ),
        ),
        prescription_change_authorized=_require_bool(
            raw.get(
                "prescription_change_authorized"
            ),
            field_name=(
                "prescription_change_authorized"
            ),
        ),
        planning_authorized=_require_bool(
            raw.get("planning_authorized"),
            field_name="planning_authorized",
        ),

        content_hash_algorithm=_require_string(
            raw.get("content_hash_algorithm"),
            field_name="content_hash_algorithm",
        ),
        content_hash=_require_sha256(
            raw.get("content_hash"),
            field_name="content_hash",
        ),
    )

    if (
        issuance.schema_version
        != PERSONAL_RESPONSE_PREDICTION_ISSUANCE_SCHEMA_V01
        or issuance.rules_version
        != PERSONAL_RESPONSE_PREDICTION_ISSUANCE_RULES_V01
    ):
        raise ValueError(
            "Unsupported persisted prediction issuance contract."
        )

    if (
        issuance.content_hash_algorithm
        != CONTENT_HASH_ALGORITHM
    ):
        raise ValueError(
            "Unsupported prediction issuance hash algorithm."
        )

    if (
        issuance.issuance_id != record.artifact_id
        or issuance.athlete_id != record.athlete_id
        or issuance.schema_version
        != record.schema_version
        or issuance.content_hash_algorithm
        != record.content_hash_algorithm
        or issuance.content_hash
        != record.content_hash
        or issuance.prediction_at
        != to_utc(
            record.created_at,
            field_name="record.created_at",
        )
    ):
        raise ValueError(
            "Prediction issuance audit metadata does not "
            "match its canonical contract."
        )

    if not issuance.verify_content_hash():
        raise ValueError(
            "Persisted prediction issuance content hash "
            "does not verify."
        )

    if canonical_json(issuance) != record.contract_json:
        raise ValueError(
            "Persisted prediction issuance contract "
            "does not round-trip canonically."
        )

    return issuance


def _binding_audit_record(
    challenge: ProspectiveResponseChallenge,
) -> AuditArtifactRecord:
    if not challenge.verify_content_hash():
        raise ValueError(
            "Prospective challenge content hash does not verify."
        )

    return AuditArtifactRecord(
        artifact_kind=(
            AuditArtifactKind
            .PERSONAL_RESPONSE_PREDICTION_OUTCOME
        ),
        artifact_id=challenge.binding_id,
        athlete_id=challenge.athlete_id,
        schema_version=challenge.schema_version,

        # Domain materialization time. The actual durable insertion
        # time remains DB-assigned AuditArtifactRecord.persisted_at.
        created_at=challenge.created_at,

        content_hash_algorithm=(
            challenge.content_hash_algorithm
        ),
        content_hash=challenge.content_hash,
        contract_json=canonical_json(
            challenge
        ),
    )


def _validate_binding_record(
    *,
    record: AuditArtifactRecord,
    expected: ProspectiveResponseChallenge,
) -> datetime:
    if (
        record.artifact_kind
        != AuditArtifactKind
        .PERSONAL_RESPONSE_PREDICTION_OUTCOME
        or record.artifact_id
        != expected.binding_id
        or record.athlete_id
        != expected.athlete_id
        or record.schema_version
        != PROSPECTIVE_RESPONSE_CHALLENGE_SCHEMA_V01
        or record.content_hash_algorithm
        != expected.content_hash_algorithm
        or record.content_hash
        != expected.content_hash
        or record.contract_json
        != canonical_json(expected)
        or to_utc(
            record.created_at,
            field_name="record.created_at",
        )
        != expected.created_at
    ):
        raise ProspectiveResponseBindingConflictError(
            "Durable prospective-response binding differs "
            "from deterministic source replay."
        )

    if record.persisted_at is None:
        raise ProspectiveResponseBindingError(
            "Durable prospective-response binding has no "
            "database persistence timestamp."
        )

    persisted = to_utc(
        record.persisted_at,
        field_name="record.persisted_at",
    )

    if persisted < expected.response_persisted_at:
        raise ProspectiveResponseBindingError(
            "Outcome binding persistence predates its "
            "authoritative response persistence."
        )

    return persisted


async def bind_personal_response_prediction_outcome(
    *,
    athlete_id: str,
    issuance_id: str,
    response_artifact_id: str,
    audit_repository: AsyncPlanningAuditRepository,
    session,
) -> DurableProspectiveResponseBindingResult:
    """Durably bind one issued prediction to one later response.

    Source objects are always restored from immutable audit records.

    The binding ID is stable per issuance. Therefore an issuance cannot
    silently acquire multiple alternative response outcomes.

    A durable B2 binding remains a single prospective challenge only.
    It does not establish prospective validation or planning authority.
    """

    canonical_athlete = _uuid_text(
        athlete_id,
        field_name="athlete_id",
    )

    canonical_issuance_id = _require_string(
        issuance_id,
        field_name="issuance_id",
    )

    canonical_response_id = _require_string(
        response_artifact_id,
        field_name="response_artifact_id",
    )

    try:
        issuance_record = await audit_repository.get(
            artifact_kind=(
                AuditArtifactKind
                .PERSONAL_RESPONSE_PREDICTION_ISSUANCE
            ),
            artifact_id=canonical_issuance_id,
        )

        if (
            issuance_record is None
            or issuance_record.athlete_id
            != canonical_athlete
        ):
            raise ProspectiveResponseBindingNotFound(
                "Prediction issuance not found."
            )

        issuance = (
            restore_personal_response_prediction_issuance_audit_artifact(
                issuance_record
            )
        )

        if issuance.athlete_id != canonical_athlete:
            raise ProspectiveResponseBindingNotFound(
                "Prediction issuance not found."
            )

        if issuance_record.persisted_at is None:
            raise ProspectiveResponseBindingError(
                "Prediction issuance has no database "
                "persistence timestamp."
            )

        issuance_persisted_at = to_utc(
            issuance_record.persisted_at,
            field_name="issuance_record.persisted_at",
        )

        response_record = await audit_repository.get(
            artifact_kind=(
                AuditArtifactKind
                .AUTHORITATIVE_TRAINING_RESPONSE
            ),
            artifact_id=canonical_response_id,
        )

        if (
            response_record is None
            or response_record.athlete_id
            != canonical_athlete
        ):
            raise ProspectiveResponseBindingNotFound(
                "Authoritative training response not found."
            )

        if response_record.persisted_at is None:
            raise ProspectiveResponseBindingError(
                "Authoritative training response has no "
                "database persistence timestamp."
            )

        response = (
            restore_authoritative_training_response_audit_artifact(
                response_record
            )
        )

        if (
            response.athlete_id != canonical_athlete
            or response.artifact_id
            != canonical_response_id
        ):
            raise ProspectiveResponseBindingNotFound(
                "Authoritative training response not found."
            )

        response_persisted_at = to_utc(
            response_record.persisted_at,
            field_name="response_record.persisted_at",
        )

        executed_record = await audit_repository.get(
            artifact_kind=(
                AuditArtifactKind
                .AUTHORITATIVE_EXECUTED_TRAINING
            ),
            artifact_id=(
                response.executed_training_evidence_id
            ),
        )

        if (
            executed_record is None
            or executed_record.athlete_id
            != canonical_athlete
        ):
            raise ProspectiveResponseBindingNotFound(
                "Authoritative executed-training evidence "
                "not found."
            )

        executed = (
            restore_authoritative_executed_training_audit_artifact(
                executed_record
            )
        )

        if (
            executed.athlete_id != canonical_athlete
            or executed.artifact_id
            != response.executed_training_evidence_id
            or executed.content_hash
            != response.executed_training_evidence_hash
            or executed.workout_session_id
            != response.workout_session_id
        ):
            raise ProspectiveResponseBindingError(
                "Authoritative response does not exactly "
                "hash-bind its executed-training evidence."
            )

        challenge = build_prospective_response_challenge(
            issuance=issuance,
            issuance_persisted_at=issuance_persisted_at,
            response=response,
            response_persisted_at=(
                response_persisted_at
            ),
            executed_training=executed,
        )

        existing = await audit_repository.get(
            artifact_kind=(
                AuditArtifactKind
                .PERSONAL_RESPONSE_PREDICTION_OUTCOME
            ),
            artifact_id=challenge.binding_id,
        )

        if existing is not None:
            if existing.athlete_id != canonical_athlete:
                raise ProspectiveResponseBindingNotFound(
                    "Prospective response binding not found."
                )

            binding_persisted_at = (
                _validate_binding_record(
                    record=existing,
                    expected=challenge,
                )
            )

            await session.commit()

            return DurableProspectiveResponseBindingResult(
                challenge=challenge,
                binding_persisted_at=(
                    binding_persisted_at
                ),
                reused_durable_binding=True,
                prospective_challenge_established=True,
                prospective_validation_established=False,
                planning_authorized=False,
            )

        save_result = await audit_repository.save(
            _binding_audit_record(
                challenge
            )
        )

        if (
            save_result.artifact_kind
            != AuditArtifactKind
            .PERSONAL_RESPONSE_PREDICTION_OUTCOME
            or save_result.artifact_id
            != challenge.binding_id
            or save_result.content_hash
            != challenge.content_hash
        ):
            raise ProspectiveResponseBindingError(
                "Prospective-response binding save result "
                "identity mismatch."
            )

        stored = await audit_repository.get(
            artifact_kind=(
                AuditArtifactKind
                .PERSONAL_RESPONSE_PREDICTION_OUTCOME
            ),
            artifact_id=challenge.binding_id,
        )

        if stored is None:
            raise ProspectiveResponseBindingError(
                "Prospective-response binding did not "
                "round-trip after persistence."
            )

        binding_persisted_at = (
            _validate_binding_record(
                record=stored,
                expected=challenge,
            )
        )

        await session.commit()

        return DurableProspectiveResponseBindingResult(
            challenge=challenge,
            binding_persisted_at=(
                binding_persisted_at
            ),
            reused_durable_binding=(
                save_result.status
                == AuditArtifactSaveStatus.ALREADY_PRESENT
            ),
            prospective_challenge_established=True,
            prospective_validation_established=False,
            planning_authorized=False,
        )

    except Exception:
        await session.rollback()
        raise
