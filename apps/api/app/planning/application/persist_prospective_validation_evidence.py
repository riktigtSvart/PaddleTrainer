from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json

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
from ..domain.training_dynamics.prospective_cohort import (
    ProspectiveValidationFamilyKey,
)
from ..domain.training_dynamics.prospective_validation import (
    ProspectiveValidationAssessmentStatus,
)
from ..domain.training_dynamics.prospective_validation_evidence import (
    PROSPECTIVE_VALIDATION_EVIDENCE_RULES_V01,
    PROSPECTIVE_VALIDATION_EVIDENCE_SCHEMA_V01,
    ProspectiveValidationEvidence,
    ProspectiveValidationEvidenceStatus,
)
from ..domain.training_dynamics.response_reference import (
    ResponseMetricReferenceKey,
)
from ..ports.audit import AsyncPlanningAuditRepository
from .assemble_prospective_validation_evidence import (
    assemble_prospective_validation_evidence,
)


class DurableProspectiveValidationEvidenceError(
    RuntimeError
):
    pass


@dataclass(frozen=True)
class DurableProspectiveValidationEvidence:
    evidence: ProspectiveValidationEvidence

    durable_available_at: datetime

    reused_durable_evidence: bool

    prospective_validation_established: bool

    prescription_change_authorized: bool
    planning_authorized: bool


def _require_mapping(
    value,
    *,
    field_name: str,
) -> dict:
    if not isinstance(value, dict):
        raise ValueError(
            f"{field_name} must be an object."
        )

    return value


def _require_string(
    value,
    *,
    field_name: str,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"{field_name} must be a non-empty string."
        )

    return value


def _optional_string(
    value,
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
    value,
    *,
    field_name: str,
) -> bool:
    if not isinstance(value, bool):
        raise ValueError(
            f"{field_name} must be boolean."
        )

    return value


def _require_int(
    value,
    *,
    field_name: str,
) -> int:
    if isinstance(value, bool) or not isinstance(
        value,
        int,
    ):
        raise ValueError(
            f"{field_name} must be an integer."
        )

    return value


def _optional_int(
    value,
    *,
    field_name: str,
) -> int | None:
    if value is None:
        return None

    return _require_int(
        value,
        field_name=field_name,
    )


def _require_sha256(
    value,
    *,
    field_name: str,
) -> str:
    text = _require_string(
        value,
        field_name=field_name,
    )

    if (
        len(text) != 64
        or any(
            character not in "0123456789abcdef"
            for character in text
        )
    ):
        raise ValueError(
            f"{field_name} must be a lowercase SHA-256 hex digest."
        )

    return text


def _require_datetime(
    value,
    *,
    field_name: str,
) -> datetime:
    text = _require_string(
        value,
        field_name=field_name,
    )

    try:
        parsed = datetime.fromisoformat(
            text.replace(
                "Z",
                "+00:00",
            )
        )
    except ValueError as exc:
        raise ValueError(
            f"{field_name} must be an ISO-8601 datetime."
        ) from exc

    return to_utc(
        parsed,
        field_name=field_name,
    )


def _validate_promotable_evidence(
    evidence: ProspectiveValidationEvidence,
) -> None:
    if not evidence.verify_content_hash():
        raise DurableProspectiveValidationEvidenceError(
            "Prospective-validation evidence content hash "
            "does not verify."
        )

    if (
        evidence.schema_version
        != PROSPECTIVE_VALIDATION_EVIDENCE_SCHEMA_V01
        or evidence.rules_version
        != PROSPECTIVE_VALIDATION_EVIDENCE_RULES_V01
    ):
        raise DurableProspectiveValidationEvidenceError(
            "Unsupported prospective-validation "
            "evidence contract."
        )

    if (
        evidence.evidence_id
        != "pt-prospective-validation-evidence:"
        + evidence.content_hash
    ):
        raise DurableProspectiveValidationEvidenceError(
            "Prospective-validation evidence identity "
            "does not match its content hash."
        )

    if (
        evidence.status
        != ProspectiveValidationEvidenceStatus
        .PROSPECTIVELY_VALIDATED
        or evidence.evidence_level
        != EffectEvidenceLevel.PROSPECTIVELY_VALIDATED
        or evidence.association_supported is not True
        or evidence.prospective_validation_established
        is not True
        or evidence.validation_criteria_met is not True
        or evidence.assessment_status
        != ProspectiveValidationAssessmentStatus
        .VALIDATION_CRITERIA_MET
    ):
        raise DurableProspectiveValidationEvidenceError(
            "Only successfully prospectively validated "
            "P2.3D evidence may cross the durable "
            "planning-study bridge."
        )

    if any(
        (
            evidence.causal_attribution_established,
            evidence.effect_inference_authorized,
            evidence.readiness_inference_authorized,
            evidence.performance_prediction_authorized,
            evidence.prescription_change_authorized,
            evidence.planning_authorized,
        )
    ):
        raise DurableProspectiveValidationEvidenceError(
            "P2.3F evidence contains unsupported "
            "stronger authority."
        )


def _audit_record(
    evidence: ProspectiveValidationEvidence,
) -> AuditArtifactRecord:
    return AuditArtifactRecord(
        artifact_kind=(
            AuditArtifactKind
            .PROSPECTIVE_VALIDATION_EVIDENCE
        ),
        artifact_id=evidence.evidence_id,
        athlete_id=evidence.athlete_id,
        schema_version=evidence.schema_version,
        created_at=evidence.created_at,
        content_hash_algorithm=(
            evidence.content_hash_algorithm
        ),
        content_hash=evidence.content_hash,
        contract_json=canonical_json(
            evidence
        ),
    )


def restore_prospective_validation_evidence_audit_artifact(
    record: AuditArtifactRecord,
) -> ProspectiveValidationEvidence:
    """Restore and verify one durable P2.3F evidence artifact."""

    if (
        record.artifact_kind
        != AuditArtifactKind
        .PROSPECTIVE_VALIDATION_EVIDENCE
    ):
        raise ValueError(
            "Unexpected prospective-validation "
            "evidence audit kind."
        )

    try:
        raw = json.loads(
            record.contract_json
        )
    except json.JSONDecodeError as exc:
        raise ValueError(
            "Prospective-validation evidence contract "
            "is not valid JSON."
        ) from exc

    raw = _require_mapping(
        raw,
        field_name="evidence",
    )

    family_raw = _require_mapping(
        raw.get("family_key"),
        field_name="family_key",
    )

    predictor_raw = _require_mapping(
        family_raw.get("predictor_key"),
        field_name="family_key.predictor_key",
    )

    response_raw = _require_mapping(
        family_raw.get("response_key"),
        field_name="family_key.response_key",
    )

    evidence = ProspectiveValidationEvidence(
        evidence_id=_require_string(
            raw.get("evidence_id"),
            field_name="evidence_id",
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

        family_key=ProspectiveValidationFamilyKey(
            model_id=_require_string(
                family_raw.get("model_id"),
                field_name="family_key.model_id",
            ),
            model_version=_require_string(
                family_raw.get("model_version"),
                field_name="family_key.model_version",
            ),
            predictor_key=PersonalAssociationPredictorKey(
                metric_key=_require_string(
                    predictor_raw.get("metric_key"),
                    field_name=(
                        "family_key.predictor_key.metric_key"
                    ),
                ),
                unit=_optional_string(
                    predictor_raw.get("unit"),
                    field_name=(
                        "family_key.predictor_key.unit"
                    ),
                ),
            ),
            response_key=ResponseMetricReferenceKey(
                metric_key=_require_string(
                    response_raw.get("metric_key"),
                    field_name=(
                        "family_key.response_key.metric_key"
                    ),
                ),
                unit=_optional_string(
                    response_raw.get("unit"),
                    field_name=(
                        "family_key.response_key.unit"
                    ),
                ),
                response_timing=TrainingResponseTiming(
                    _require_string(
                        response_raw.get(
                            "response_timing"
                        ),
                        field_name=(
                            "family_key.response_key."
                            "response_timing"
                        ),
                    )
                ),
                stimulus_modality_key=_require_string(
                    response_raw.get(
                        "stimulus_modality_key"
                    ),
                    field_name=(
                        "family_key.response_key."
                        "stimulus_modality_key"
                    ),
                ),
            ),
        ),

        as_of=_require_datetime(
            raw.get("as_of"),
            field_name="as_of",
        ),

        source_cohort_id=_require_string(
            raw.get("source_cohort_id"),
            field_name="source_cohort_id",
        ),
        source_cohort_content_hash=_require_sha256(
            raw.get("source_cohort_content_hash"),
            field_name="source_cohort_content_hash",
        ),
        source_cohort_schema_version=_require_string(
            raw.get("source_cohort_schema_version"),
            field_name="source_cohort_schema_version",
        ),
        source_cohort_rules_version=_require_string(
            raw.get("source_cohort_rules_version"),
            field_name="source_cohort_rules_version",
        ),

        source_multiplicity_guard_id=_require_string(
            raw.get(
                "source_multiplicity_guard_id"
            ),
            field_name=(
                "source_multiplicity_guard_id"
            ),
        ),
        source_multiplicity_guard_content_hash=_require_sha256(
            raw.get(
                "source_multiplicity_guard_content_hash"
            ),
            field_name=(
                "source_multiplicity_guard_content_hash"
            ),
        ),
        source_multiplicity_guard_schema_version=_require_string(
            raw.get(
                "source_multiplicity_guard_schema_version"
            ),
            field_name=(
                "source_multiplicity_guard_schema_version"
            ),
        ),
        source_multiplicity_guard_rules_version=_require_string(
            raw.get(
                "source_multiplicity_guard_rules_version"
            ),
            field_name=(
                "source_multiplicity_guard_rules_version"
            ),
        ),

        source_assessment_id=_require_string(
            raw.get("source_assessment_id"),
            field_name="source_assessment_id",
        ),
        source_assessment_content_hash=_require_sha256(
            raw.get(
                "source_assessment_content_hash"
            ),
            field_name=(
                "source_assessment_content_hash"
            ),
        ),
        source_assessment_schema_version=_require_string(
            raw.get(
                "source_assessment_schema_version"
            ),
            field_name=(
                "source_assessment_schema_version"
            ),
        ),
        source_assessment_rules_version=_require_string(
            raw.get(
                "source_assessment_rules_version"
            ),
            field_name=(
                "source_assessment_rules_version"
            ),
        ),

        issued_challenge_count=_require_int(
            raw.get("issued_challenge_count"),
            field_name="issued_challenge_count",
        ),
        directionally_scored_count=_require_int(
            raw.get(
                "directionally_scored_count"
            ),
            field_name=(
                "directionally_scored_count"
            ),
        ),
        matched_count=_require_int(
            raw.get("matched_count"),
            field_name="matched_count",
        ),
        mismatched_count=_require_int(
            raw.get("mismatched_count"),
            field_name="mismatched_count",
        ),
        tied_unscorable_count=_require_int(
            raw.get("tied_unscorable_count"),
            field_name="tied_unscorable_count",
        ),

        exact_one_sided_p_numerator=_require_int(
            raw.get(
                "exact_one_sided_p_numerator"
            ),
            field_name=(
                "exact_one_sided_p_numerator"
            ),
        ),
        exact_one_sided_p_denominator=_require_int(
            raw.get(
                "exact_one_sided_p_denominator"
            ),
            field_name=(
                "exact_one_sided_p_denominator"
            ),
        ),

        adjusted_alpha_numerator=_optional_int(
            raw.get(
                "adjusted_alpha_numerator"
            ),
            field_name=(
                "adjusted_alpha_numerator"
            ),
        ),
        adjusted_alpha_denominator=_optional_int(
            raw.get(
                "adjusted_alpha_denominator"
            ),
            field_name=(
                "adjusted_alpha_denominator"
            ),
        ),

        assessment_status=(
            ProspectiveValidationAssessmentStatus(
                _require_string(
                    raw.get("assessment_status"),
                    field_name="assessment_status",
                )
            )
        ),
        validation_criteria_met=_require_bool(
            raw.get(
                "validation_criteria_met"
            ),
            field_name=(
                "validation_criteria_met"
            ),
        ),

        status=ProspectiveValidationEvidenceStatus(
            _require_string(
                raw.get("status"),
                field_name="status",
            )
        ),

        evidence_level=EffectEvidenceLevel(
            _require_string(
                raw.get("evidence_level"),
                field_name="evidence_level",
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

        created_at=_require_datetime(
            raw.get("created_at"),
            field_name="created_at",
        ),

        content_hash_algorithm=_require_string(
            raw.get(
                "content_hash_algorithm"
            ),
            field_name=(
                "content_hash_algorithm"
            ),
        ),
        content_hash=_require_sha256(
            raw.get("content_hash"),
            field_name="content_hash",
        ),
    )

    if (
        evidence.evidence_id
        != record.artifact_id
        or evidence.athlete_id
        != record.athlete_id
        or evidence.schema_version
        != record.schema_version
        or evidence.created_at
        != to_utc(
            record.created_at,
            field_name="record.created_at",
        )
        or evidence.content_hash_algorithm
        != record.content_hash_algorithm
        or evidence.content_hash
        != record.content_hash
    ):
        raise ValueError(
            "Prospective-validation evidence audit "
            "metadata does not match its contract."
        )

    if (
        evidence.content_hash_algorithm
        != CONTENT_HASH_ALGORITHM
    ):
        raise ValueError(
            "Unsupported prospective-validation "
            "evidence hash algorithm."
        )

    _validate_promotable_evidence(
        evidence
    )

    if (
        canonical_json(evidence)
        != record.contract_json
    ):
        raise ValueError(
            "Prospective-validation evidence does not "
            "round-trip canonically."
        )

    return evidence


def _validate_durable_record(
    *,
    record: AuditArtifactRecord,
    expected_evidence:
        ProspectiveValidationEvidence,
) -> tuple[
    ProspectiveValidationEvidence,
    datetime,
]:
    restored = (
        restore_prospective_validation_evidence_audit_artifact(
            record
        )
    )

    # created_at is deliberately excluded from the P2.3D semantic hash.
    # Therefore retries may rematerialize the same semantic evidence at
    # another Python time. The durable stored artifact remains authoritative.
    if (
        restored.evidence_id
        != expected_evidence.evidence_id
        or restored.content_hash
        != expected_evidence.content_hash
        or restored.athlete_id
        != expected_evidence.athlete_id
    ):
        raise DurableProspectiveValidationEvidenceError(
            "Durable prospective-validation evidence "
            "does not match the replayed P2.3D semantics."
        )

    if record.persisted_at is None:
        raise DurableProspectiveValidationEvidenceError(
            "Durable prospective-validation evidence "
            "has no database persistence timestamp."
        )

    durable_time = to_utc(
        record.persisted_at,
        field_name="record.persisted_at",
    )

    if durable_time < restored.created_at:
        raise DurableProspectiveValidationEvidenceError(
            "Durable prospective-validation evidence "
            "predates its materialization time."
        )

    if durable_time < restored.as_of:
        raise DurableProspectiveValidationEvidenceError(
            "Durable prospective-validation evidence "
            "predates its evidence as_of boundary."
        )

    return (
        restored,
        durable_time,
    )


async def persist_prospective_validation_evidence(
    *,
    athlete_id: str,
    family_key: ProspectiveValidationFamilyKey,
    as_of: datetime,
    created_at: datetime,
    audit_repository: AsyncPlanningAuditRepository,
    session,
) -> DurableProspectiveValidationEvidence:
    """Persist successful P2.3D evidence with DB-assigned availability.

    This establishes only durable temporal availability for later
    planning-utility study.

    It does NOT authorize prescription change or planning.
    """

    evidence = await assemble_prospective_validation_evidence(
        athlete_id=athlete_id,
        family_key=family_key,
        as_of=as_of,
        created_at=created_at,
        audit_repository=audit_repository,
    )

    _validate_promotable_evidence(
        evidence
    )

    try:
        existing = await audit_repository.get(
            artifact_kind=(
                AuditArtifactKind
                .PROSPECTIVE_VALIDATION_EVIDENCE
            ),
            artifact_id=evidence.evidence_id,
        )

        if existing is not None:
            (
                restored,
                durable_time,
            ) = _validate_durable_record(
                record=existing,
                expected_evidence=evidence,
            )

            await session.commit()

            return DurableProspectiveValidationEvidence(
                evidence=restored,
                durable_available_at=durable_time,
                reused_durable_evidence=True,
                prospective_validation_established=True,
                prescription_change_authorized=False,
                planning_authorized=False,
            )

        save_result = await audit_repository.save(
            _audit_record(
                evidence
            )
        )

        if (
            save_result.artifact_kind
            != AuditArtifactKind
            .PROSPECTIVE_VALIDATION_EVIDENCE
            or save_result.artifact_id
            != evidence.evidence_id
            or save_result.content_hash
            != evidence.content_hash
        ):
            raise DurableProspectiveValidationEvidenceError(
                "Prospective-validation evidence save "
                "result identity mismatch."
            )

        stored = await audit_repository.get(
            artifact_kind=(
                AuditArtifactKind
                .PROSPECTIVE_VALIDATION_EVIDENCE
            ),
            artifact_id=evidence.evidence_id,
        )

        if stored is None:
            raise DurableProspectiveValidationEvidenceError(
                "Prospective-validation evidence did not "
                "round-trip after persistence."
            )

        (
            restored,
            durable_time,
        ) = _validate_durable_record(
            record=stored,
            expected_evidence=evidence,
        )

        await session.commit()

        return DurableProspectiveValidationEvidence(
            evidence=restored,
            durable_available_at=durable_time,
            reused_durable_evidence=(
                save_result.status
                == AuditArtifactSaveStatus.ALREADY_PRESENT
            ),
            prospective_validation_established=True,
            prescription_change_authorized=False,
            planning_authorized=False,
        )

    except Exception:
        await session.rollback()
        raise
